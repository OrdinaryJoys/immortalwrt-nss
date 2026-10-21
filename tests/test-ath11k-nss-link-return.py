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


def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after, 1)


variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in
        ('plain-unlock', 'double-enable', 'missing-unlock', 'early-enable', 'missing-access-end', 'missing-descriptor',
         'bh-enable-before-unlock', 'publish-before-descriptor', 'omit-source-module', 'unlock-window')]
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
    setter = tree.function(relative + 'nss.c', 'ath11k_nss_wifili_link_desc_set')
    returning = tree.function(relative + 'nss.c', 'ath11k_nss_wifili_link_desc_return')
    if label not in ('candidate', 'baseline'):
        original = 'spin_unlock_bh(&srng->lock);'
        if label == 'plain-unlock':
            returning = replace_once(returning, original, 'spin_unlock(&srng->lock);')
        elif label == 'double-enable':
            returning = replace_once(returning, original, original + '\n\tlocal_bh_enable();')
        elif label == 'missing-unlock':
            returning = replace_once(returning, original, '(void)srng;')
        elif label == 'early-enable':
            returning = replace_once(returning, 'spin_lock_bh(&srng->lock);', 'spin_lock(&srng->lock);')
        elif label == 'missing-access-end':
            returning = replace_once(returning, 'ath11k_hal_srng_access_end(ab, srng);', '(void)ab;')
        elif label == 'missing-descriptor':
            before = 'ath11k_nss_wifili_link_desc_set(ab, desc, buf_addr_info, HAL_WBM_REL_BM_ACT_PUT_IN_IDLE);'
            returning = replace_once(returning, before, '(void)desc; (void)buf_addr_info;')
        elif label == 'bh-enable-before-unlock':
            returning = replace_once(returning, original, 'local_bh_enable();\n\tspin_unlock(&srng->lock);')
        elif label == 'publish-before-descriptor':
            end = '\tath11k_hal_srng_access_end(ab, srng);'
            before = '\tdesc = ath11k_hal_srng_src_get_next_entry(ab, srng);'
            returning = replace_once(returning, end, '')
            returning = replace_once(returning, before, before + '\n' + end)
        elif label == 'omit-source-module':
            before = ('FIELD_PREP(HAL_WBM_RELEASE_INFO0_REL_SRC_MODULE,\n'
                      '\t\t\t\t      HAL_WBM_REL_SRC_MODULE_SW) |\n\t\t\t   ')
            setter = replace_once(setter, before, '')
        elif label == 'unlock-window':
            before = '\tdesc = ath11k_hal_srng_src_get_next_entry(ab, srng);'
            returning = replace_once(returning, before, before + '\n\tspin_unlock(&srng->lock);')
            before = 'exit:\n\tath11k_hal_srng_access_end(ab, srng);'
            returning = replace_once(returning, before,
                'exit:\n\tspin_lock(&srng->lock);\n\tath11k_hal_srng_access_end(ab, srng);')
    code = assets[fixture].decode().replace('HOST_STRUCTURES', structures).replace('HOST_FUNCTIONS', source + setter + returning)
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
    assert ran.returncode == (0 if expected else 1), (label, ran.returncode)
    assert (result['failures'] == 0) == expected, (label, result)
    if label == 'bh-enable-before-unlock':
        assert result['bh_order_failures'] > 0, (label, result)
    if label in ('publish-before-descriptor', 'omit-source-module'):
        assert result['publication_failures'] > 0, (label, result)
    if label == 'unlock-window':
        assert result['failures'] == result['unlock_window_failures'] == result['calls'], (label, result)
        assert result['transaction_state_failures'] == result['bh_order_failures'] == result['publication_failures'] == 0, (label, result)
    records.append(dict(label=label, command=command, generated_sha256=hashlib.sha256(code.encode()).hexdigest(),
        **result, **tree.manifest()))
if args.baseline:
    assert records[0]['normal_signature'] == records[1]['normal_signature'], 'normal ring/descriptor behavior changed'
for row in records[1:]:
    if row['label'] not in ('missing-descriptor', 'omit-source-module'):
        assert row['normal_signature'] == records[0]['normal_signature'], (row['label'], 'normal signature changed')
    else:
        assert row['normal_signature'] != records[0]['normal_signature'], (row['label'], 'descriptor mutation was masked')
assert all(path.read_bytes() == data for path, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    assets={str(path): hashlib.sha256(data).hexdigest() for path, data in assets.items()},
    baseline_signature_compared=args.baseline is not None,
    scope='Three complete prepared functions and exact SRNG/descriptor declarations. Host contracts reject unlocking the selected ring between access_begin/access_end, check the last BH enable against held locks and inspect an independent expected descriptor/slot at access_end, across 68 seeds. The extracted setter is not instrumented. These are not a Linux scheduler, concurrency, DMA or firmware. Not callback-lifetime, target or throughput qualification.',
    hardware_accessed=False, target_compiled=False), indent=2) + '\n')
print(json.dumps([{key: row[key] for key in ('label', 'seeds', 'scenarios', 'calls', 'checks', 'failures',
    'bh_order_failures', 'publication_failures', 'transaction_state_failures', 'unlock_window_failures',
    'normal_signature')} for row in records], indent=2))
