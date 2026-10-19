#!/usr/bin/env python3
"""Run full prepared DP allocation and cleanup helpers with modeled allocation APIs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cc', default='cc')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-dp-allocation/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}
directory = 'drivers/net/wireless/ath/ath11k/'


def declaration(text, name):
    matches = list(re.finditer(r'^struct\s+' + re.escape(name) + r'\s*\{', extract.code_mask(text), re.M))
    if len(matches) != 1:
        raise ValueError('missing/ambiguous declaration: ' + name)
    start = matches[0].start()
    end = extract.block_end(text, matches[0].end() - 1)
    tail = re.match(r'\s*(?:__packed\s*)?;', text[end:])
    if tail is None:
        raise ValueError('unterminated declaration: ' + name)
    return text[start:end + tail.end()] + '\n'


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('ambiguous mutation: ' + before)
    return text.replace(before, after, 1)


variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in (
        'leak-idle-ring', 'skip-tx-free', 'no-tx-null', 'skip-first-tx')]
records = []
for name, root, expected in variants:
    tree = extract.Prepared(root)
    dp = tree.read(directory + 'dp.h')
    hal = tree.read(directory + 'hal.h')
    hw = tree.read(directory + 'hw.h')
    desc = tree.read(directory + 'hal_desc.h')
    constants = []
    for text, names in ((dp, ('DP_TCL_NUM_RING_MAX', 'DP_LINK_DESC_BANKS_MAX', 'DP_IDLE_SCATTER_BUFS_MAX', 'DP_TX_COMP_RING_SIZE')),
                        (hal, ('HAL_WBM_IDLE_SCATTER_BUF_SIZE_MAX', 'HAL_DSCP_TID_MAP_TBL_NUM_ENTRIES_MAX'))):
        for symbol in names:
            found = re.findall(r'^#define\s+' + symbol + r'\s+[^\n]+', text, re.M)
            if len(found) != 1:
                raise ValueError('missing/ambiguous constant: ' + symbol)
            constants.append(found[0])
    profiles = re.findall(r'^#define\s+ATH11K_DP_TX_COMP_RING_SIZE\s+(\d+)\s*$', hw, re.M)
    if len(profiles) != 2 or '#ifdef CPTCFG_ATH11K_MEM_PROFILE_512M' not in hw:
        raise ValueError('review new memory profile definitions before running test')
    constants += ['#ifdef CPTCFG_ATH11K_MEM_PROFILE_512M', '#define ATH11K_DP_TX_COMP_RING_SIZE ' + profiles[0],
                  '#else', '#define ATH11K_DP_TX_COMP_RING_SIZE ' + profiles[1], '#endif']
    types = ''.join(declaration(text, symbol) for text, symbol in (
        (desc, 'ath11k_buffer_addr'), (desc, 'hal_tx_rate_stats'), (desc, 'hal_wbm_link_desc'),
        (desc, 'hal_wbm_release_ring'), (dp, 'dp_srng'), (dp, 'dp_link_desc_bank'),
        (hal, 'hal_wbm_idle_scatter_list')))
    functions = ''.join(tree.function(directory + 'dp.c', symbol) for symbol in (
        'ath11k_dp_srng_cleanup', 'ath11k_dp_scatter_idle_link_desc_cleanup',
        'ath11k_dp_link_desc_bank_free', 'ath11k_dp_link_desc_cleanup', 'ath11k_dp_alloc'))
    if name == 'leak-idle-ring':
        functions = replace_once(functions, '"failed to setup link desc: %d\\n", ret);\n\t\tgoto fail_link_desc_cleanup;',
            '"failed to setup link desc: %d\\n", ret);\n\t\treturn ret;')
    if name == 'skip-tx-free':
        functions = replace_once(functions, '\t\tkfree(dp->tx_ring[i].tx_status);', '\t\t(void)dp->tx_ring[i].tx_status;')
    if name == 'no-tx-null':
        functions = replace_once(functions, '\t\tdp->tx_ring[i].tx_status = NULL;\n', '')
    if name == 'skip-first-tx':
        functions = replace_once(functions, '\twhile (i--) {', '\twhile (i-- > 1) {')
    code = assets[HERE / 'ath11k-dp-allocation/host-fixture.c'].decode().replace(
        'HOST_CONSTANTS', '\n'.join(constants)).replace('HOST_TYPES', types).replace('HOST_FUNCTIONS', functions)
    for profile in ('default', '512M'):
        label = name + '-' + profile
        c = args.output / (label + '.c')
        c.write_text(code)
        command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(c.with_suffix('.host'))]
        if profile == '512M':
            command.append('-DCPTCFG_ATH11K_MEM_PROFILE_512M')
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        compiled = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '-compile.stderr')).write_bytes(compiled.stderr)
        if compiled.returncode:
            raise SystemExit(compiled.stderr.decode())
        ran = subprocess.run([str(c.with_suffix('.host'))], capture_output=True, timeout=30)
        (args.output / (label + '.stdout')).write_bytes(ran.stdout)
        (args.output / (label + '.stderr')).write_bytes(ran.stderr)
        if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', ran.stderr):
            raise SystemExit('sanitizer error is not a valid negative control: ' + label)
        result = json.loads(ran.stdout)
        if (ran.returncode == 0) != expected or (result['failures'] == 0) != expected:
            raise SystemExit('unexpected result: ' + label + ' ' + str(result))
        records.append(dict(variant=name, profile=profile, expected_pass=expected,
            command=command, generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **result, **tree.manifest()))
for profile in ('default', '512M'):
    assert len({r['normal_signature'] for r in records if r['profile'] == profile}) == 1
for path, data in assets.items():
    assert path.read_bytes() == data
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    test_assets={str(p): hashlib.sha256(b).hexdigest() for p, b in assets.items()},
    scope='Full prepared dp_alloc and actual guarded cleanup helpers; setup, DMA, IRQ and allocator APIs modeled.',
    real_kernel_concurrency=False, target_compiled=False, hardware_accessed=False), indent=2) + '\n')
print(json.dumps([{k: r[k] for k in ('variant', 'profile', 'checks', 'failures')} for r in records]))
