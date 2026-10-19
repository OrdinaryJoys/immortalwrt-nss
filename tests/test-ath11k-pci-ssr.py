#!/usr/bin/env python3
"""Full prepared PCI shutdown/MHI callback, pthread API models, not kernel qualification."""
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
sanitizers = parser.add_mutually_exclusive_group()
sanitizers.add_argument('--sanitize', action='store_true')
sanitizers.add_argument('--thread-sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-pci-ssr/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}

variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in (
        'no-producer-lock', 'no-shutdown-lock', 'no-unregistering',
        'no-reset-drain', 'no-dump-drain', 'late-drain')]

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('missing or ambiguous mutation: ' + old)
    return text.replace(old, new, 1)

records = []
for name, root, expected in variants:
    tree = extract.Prepared(root)
    directory = 'drivers/net/wireless/ath/ath11k/'
    callback = tree.function(directory + 'mhi.c', 'ath11k_mhi_op_status_cb')
    shutdown = tree.function(directory + 'pci.c', 'ath11k_pci_shutdown')
    if name == 'no-producer-lock':
        callback = replace_once(callback, '\t\tspin_lock_bh(&ab->base_lock);\n', '')
        callback = replace_once(callback, '\t\tspin_unlock_bh(&ab->base_lock);\n', '')
    if name == 'no-shutdown-lock':
        shutdown = replace_once(shutdown, '\tspin_lock_bh(&ab->base_lock);\n', '')
        shutdown = replace_once(shutdown, '\tspin_unlock_bh(&ab->base_lock);\n', '')
    if name == 'no-unregistering':
        shutdown = replace_once(shutdown, '\tset_bit(ATH11K_FLAG_UNREGISTERING, &ab->dev_flags);\n', '')
    if name == 'no-reset-drain':
        shutdown = replace_once(shutdown, '\tcancel_work_sync(&ab->reset_work);\n', '')
    if name == 'no-dump-drain':
        shutdown = replace_once(shutdown, '\tcancel_work_sync(&ab->dump_work);\n', '')
    if name == 'late-drain':
        drain = '\tcancel_work_sync(&ab->reset_work);\n\tcancel_work_sync(&ab->dump_work);\n'
        shutdown = replace_once(shutdown, drain, '')
        marker = '\tath11k_pci_power_down(ab, false);\n'
        shutdown = replace_once(shutdown, marker, marker + drain)
    code = assets[HERE / 'ath11k-pci-ssr/host-fixture.c'].decode().replace('HOST_DRIVER_FUNCTIONS', callback + shutdown)
    c = args.output / (name + '.c')
    c.write_text(code)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread', str(c), '-o', str(c.with_suffix('.host'))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    if args.thread_sanitize:
        command += ['-fsanitize=thread', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True, timeout=50)
    (args.output / (name + '-compile.stderr')).write_bytes(compiled.stderr)
    if compiled.returncode:
        raise SystemExit(compiled.stderr.decode())
    ran = subprocess.run([str(c.with_suffix('.host'))], capture_output=True, timeout=30)
    (args.output / (name + '.stdout')).write_bytes(ran.stdout)
    (args.output / (name + '.stderr')).write_bytes(ran.stderr)
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|ThreadSanitizer|runtime error:', ran.stderr):
        raise SystemExit('sanitizer failure is not a valid negative control: ' + name)
    result = json.loads(ran.stdout)
    if (ran.returncode == 0) != expected or (result['failures'] == 0) != expected:
        raise SystemExit('unexpected result: ' + name + ' ' + str(result))
    records.append(dict(variant=name, expected_pass=expected, command=command, **result,
        generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **tree.manifest()))
for path, before in assets.items():
    assert path.read_bytes() == before
assert len({r['normal_signature'] for r in records}) == 1
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    test_assets={str(p): hashlib.sha256(b).hexdigest() for p, b in assets.items()},
    scope='Actual complete callback/shutdown C with controlled pthread schedules. Workqueue, MHI, DMA and IRQ primitives are models.',
    real_kernel_concurrency=False, hardware_accessed=False, target_compiled=False), indent=2) + '\n')
print(json.dumps([dict(variant=r['variant'], checks=r['checks'], failures=r['failures']) for r in records]))
