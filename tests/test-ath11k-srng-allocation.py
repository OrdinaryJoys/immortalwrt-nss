#!/usr/bin/env python3
"""Full prepared SRNG setup/cleanup; DMA and HAL are deterministic host models."""
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
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-dp-allocation/srng-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}
variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in (
        'leak-hal-error', 'leak-invalid-type', 'stale-cached', 'no-pointer-clear', 'hide-error')]
records = []


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('ambiguous mutation: ' + old)
    return text.replace(old, new, 1)


for name, root, expected in variants:
    tree = extract.Prepared(root)
    directory = 'drivers/net/wireless/ath/ath11k/'
    hal = tree.read(directory + 'hal.h')
    constants = []
    for symbol in ('HAL_RING_BASE_ALIGN', 'HAL_SRNG_FLAGS_LOW_THRESH_INTR_EN', 'HAL_SRNG_FLAGS_CACHED',
                   'HAL_SRNG_INT_BATCH_THRESHOLD_TX', 'HAL_SRNG_INT_BATCH_THRESHOLD_RX', 'HAL_SRNG_INT_BATCH_THRESHOLD_OTHER',
                   'HAL_SRNG_INT_TIMER_THRESHOLD_TX', 'HAL_SRNG_INT_TIMER_THRESHOLD_RX', 'HAL_SRNG_INT_TIMER_THRESHOLD_OTHER'):
        found = re.findall(r'^#define\s+' + symbol + r'\s+[^\n]+', hal, re.M)
        if len(found) != 1:
            raise ValueError('missing/ambiguous constant: ' + symbol)
        constants.append(found[0])
    types = tree.structure(directory + 'hal.h', 'hal_ring_type', kind='enum')
    types += tree.structure(directory + 'hal.h', 'hal_srng_params')
    types += tree.structure(directory + 'dp.h', 'dp_srng')
    cleanup = tree.function(directory + 'dp.c', 'ath11k_dp_srng_cleanup')
    setup = tree.function(directory + 'dp.c', 'ath11k_dp_srng_setup')
    if name == 'leak-hal-error':
        setup = replace_once(setup, '    ret, ring_num);\n\t\tgoto err_free;', '    ret, ring_num);\n\t\treturn ret;')
    if name == 'leak-invalid-type':
        setup = replace_once(setup, '\t\tret = -EINVAL;\n\t\tgoto err_free;', '\t\treturn -EINVAL;')
    if name == 'stale-cached':
        setup = replace_once(setup, '\tring->cached = cached;\n', '')
    if name == 'no-pointer-clear':
        cleanup = replace_once(cleanup, '\tring->vaddr_unaligned = NULL;', '\t(void)ring;')
    if name == 'hide-error':
        setup = replace_once(setup, 'err_free:\n\tath11k_dp_srng_cleanup(ab, ring);\n\treturn ret;',
            'err_free:\n\tath11k_dp_srng_cleanup(ab, ring);\n\treturn 0;')
    code = assets[HERE / 'ath11k-dp-allocation/srng-fixture.c'].decode().replace(
        'HOST_CONSTANTS', '\n'.join(constants)).replace('HOST_TYPES', types).replace('HOST_FUNCTIONS', cleanup + setup)
    c = args.output / (name + '.c')
    c.write_text(code)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(c.with_suffix('.host'))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / (name + '-compile.stderr')).write_bytes(compiled.stderr)
    if compiled.returncode:
        raise SystemExit(compiled.stderr.decode())
    ran = subprocess.run([str(c.with_suffix('.host'))], capture_output=True, timeout=30)
    (args.output / (name + '.stdout')).write_bytes(ran.stdout)
    (args.output / (name + '.stderr')).write_bytes(ran.stderr)
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', ran.stderr):
        raise SystemExit('sanitizer error is not a valid negative control: ' + name)
    result = json.loads(ran.stdout)
    if (ran.returncode == 0) != expected or (result['failures'] == 0) != expected:
        raise SystemExit('unexpected result: ' + name + ' ' + str(result))
    records.append(dict(variant=name, expected_pass=expected, command=command,
        generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **result, **tree.manifest()))
assert len({r['normal_signature'] for r in records}) == 1
assert all(p.read_bytes() == data for p, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    test_assets={str(p): hashlib.sha256(b).hexdigest() for p, b in assets.items()},
    scope='Full prepared SRNG setup/cleanup, scalar HAL/DMA model; no device, DMA concurrency or complete HAL lifecycle qualification.',
    target_compiled=False, hardware_accessed=False), indent=2) + '\n')
print(json.dumps([{k: r[k] for k in ('variant', 'checks', 'failures')} for r in records]))
