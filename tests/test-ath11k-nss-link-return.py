#!/usr/bin/env python3
"""Actual prepared NSS return/set and SRNG source functions; host BH/MMIO contracts."""
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
fixture = HERE / 'ath11k-nss-link-return/host-fixture.c'
assets = {path: path.read_bytes() for path in (Path(__file__), fixture, HERE / 'nss-dp-containment/extract_prepared_c.py')}
relative = 'drivers/net/wireless/ath/ath11k/'


def packed_structure(text, name):
    matches = list(re.finditer(r'^struct ' + re.escape(name) + r'\s*\{', extract.code_mask(text), re.M))
    assert len(matches) == 1, name
    start = matches[0].start()
    end = extract.block_end(text, matches[0].end() - 1)
    suffix = re.match(r'\s*__packed;', text[end:])
    assert suffix, name
    return text[start:end + suffix.end()] + '\n'


def macro(text, name):
    matches = re.findall(r'^#define\s+' + re.escape(name) + r'\s+[^\n]+$', text, re.M)
    assert len(matches) == 1, name
    assert '\\' not in matches[0], name
    return matches[0] + '\n'


variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in
        ('plain-unlock', 'double-enable', 'missing-unlock', 'early-enable', 'missing-access-end', 'missing-descriptor')]
records = []
for label, root, expected in variants:
    tree = extract.Prepared(root)
    desc = tree.read(relative + 'hal_desc.h')
    hal = tree.read(relative + 'hal.h')
    structures = ''.join(packed_structure(desc, name) for name in
        ('ath11k_buffer_addr', 'hal_tx_rate_stats', 'hal_wbm_release_ring'))
    structures += ''.join(extract.structure(desc, name, 'enum') for name in
        ('hal_wbm_rel_src_module', 'hal_wbm_rel_desc_type', 'hal_wbm_rel_bm_act'))
    structures += extract.structure(hal, 'hal_srng_dir', 'enum')
    structures += macro(hal, 'HAL_SRNG_NUM_REG_GRP') + extract.structure(hal, 'hal_srng')
    structures += ''.join(macro(desc, name) for name in
        ('HAL_WBM_RELEASE_INFO0_REL_SRC_MODULE', 'HAL_WBM_RELEASE_INFO0_BM_ACTION', 'HAL_WBM_RELEASE_INFO0_DESC_TYPE'))
    source = tree.function(relative + 'hal.c', 'ath11k_hal_srng_src_get_next_entry')
    source += tree.function(relative + 'nss.c', 'ath11k_nss_wifili_link_desc_set')
    returning = tree.function(relative + 'nss.c', 'ath11k_nss_wifili_link_desc_return')
    if label not in ('candidate', 'baseline'):
        original = 'spin_unlock_bh(&srng->lock);'
        assert returning.count(original) == 1
        if label == 'plain-unlock':
            returning = returning.replace(original, 'spin_unlock(&srng->lock);', 1)
        elif label == 'double-enable':
            returning = returning.replace(original, original + '\n\tlocal_bh_enable();', 1)
        elif label == 'missing-unlock':
            returning = returning.replace(original, '(void)srng;', 1)
        elif label == 'early-enable':
            returning = returning.replace('spin_lock_bh(&srng->lock);', 'spin_lock(&srng->lock);', 1)
        elif label == 'missing-access-end':
            returning = returning.replace('ath11k_hal_srng_access_end(ab, srng);', '(void)ab;', 1)
        elif label == 'missing-descriptor':
            before = 'ath11k_nss_wifili_link_desc_set(ab, desc, buf_addr_info, HAL_WBM_REL_BM_ACT_PUT_IN_IDLE);'
            assert returning.count(before) == 1
            returning = returning.replace(before, '(void)desc; (void)buf_addr_info;', 1)
    code = assets[fixture].decode().replace('HOST_STRUCTURES', structures).replace('HOST_FUNCTIONS', source + returning)
    file = args.output / (label + '.c')
    file.write_text(code)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-Wno-unused-function', str(file), '-o', str(file.with_suffix('.host'))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / (label + '.compile.stderr')).write_bytes(compiled.stderr)
    assert compiled.returncode == 0, (label, compiled.stderr.decode())
    ran = subprocess.run([str(file.with_suffix('.host'))], capture_output=True, timeout=60)
    (args.output / (label + '.stdout')).write_bytes(ran.stdout)
    (args.output / (label + '.stderr')).write_bytes(ran.stderr)
    assert not ran.stderr, (label, ran.stderr.decode())
    result = json.loads(ran.stdout)
    assert (ran.returncode == 0 and result['failures'] == 0) == expected, (label, result)
    assert ran.returncode in (0, 1), label
    records.append(dict(label=label, command=command, generated_sha256=hashlib.sha256(code.encode()).hexdigest(),
        **result, **tree.manifest()))
if args.baseline:
    assert records[0]['normal_signature'] == records[1]['normal_signature'], 'normal ring/descriptor behavior changed'
assert all(path.read_bytes() == data for path, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    assets={str(path): hashlib.sha256(data).hexdigest() for path, data in assets.items()},
    scope='Three complete prepared functions and exact SRNG/descriptor declarations. BH/spinlock/lockdep and MMIO begin/end are explicit contracts, not a Linux scheduler, DMA or firmware. Not callback-lifetime, target or throughput qualification.',
    hardware_accessed=False, target_compiled=False), indent=2) + '\n')
print(json.dumps([{key: row[key] for key in ('label', 'scenarios', 'calls', 'checks', 'failures', 'normal_signature')} for row in records], indent=2))
