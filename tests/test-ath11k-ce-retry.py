#!/usr/bin/env python3
"""Execute extracted CE cleanup/stop/recovery C with modeled timer/IRQ APIs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-ce-retry/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}


def change(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after, 1)


records = []
variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in (
        'mutant-no-drain', 'mutant-late-drain', 'mutant-permanent-stop', 'mutant-ahb-only')]
for label, root, expected in variants:
    prepared = extract.Prepared(root)
    directory = 'drivers/net/wireless/ath/ath11k/'
    pieces = []
    for file, names in (
        ('ce.c', ('ath11k_ce_cleanup_pipes', 'ath11k_ce_rx_post_buf', 'ath11k_ce_rx_replenish_retry')),
        ('ahb.c', ('ath11k_ahb_start', 'ath11k_ahb_stop')),
        ('pcic.c', ('ath11k_pcic_start', 'ath11k_pcic_stop')),
        ('core.c', ('ath11k_core_reconfigure_on_crash',))):
        pieces += [prepared.function(directory + file, name) for name in names]
    functions = '\n'.join(pieces)
    marker = '\ttimer_delete_sync(&ab->rx_replenish_retry);\n'
    if label == 'mutant-no-drain':
        functions = change(functions, marker, '')
    elif label == 'mutant-permanent-stop':
        functions = change(functions, marker, marker.replace('timer_delete_sync', 'timer_shutdown_sync'))
    elif label == 'mutant-late-drain':
        functions = change(functions, marker, '')
        cleanup = extract.function(functions, 'ath11k_ce_cleanup_pipes')
        functions = change(functions, cleanup, cleanup.rstrip()[:-1] + marker + '}\n')
    elif label == 'mutant-ahb-only':
        functions = change(functions, marker, '')
        functions = change(functions, '\tath11k_ahb_ce_irq_disable_sync(ab);\n',
                           '\tath11k_ahb_ce_irq_disable_sync(ab);\n' + marker)
    fixture = assets[HERE / 'ath11k-ce-retry/host-fixture.c'].decode()
    program = fixture.replace('HOST_DRIVER_FUNCTIONS', functions)
    path = args.output / (label + '.c')
    path.write_text(program)
    command = [shutil.which('cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-function', str(path), '-o', str(path.with_suffix('.host'))]
    if args.sanitize:
        command[1:1] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compile_result = subprocess.run(command, capture_output=True, timeout=45)
    (args.output / (label + '-compile.stderr')).write_bytes(compile_result.stderr)
    if compile_result.returncode:
        raise SystemExit(compile_result.stderr.decode())
    result = subprocess.run([str(path.with_suffix('.host'))], capture_output=True, timeout=30)
    (args.output / (label + '.stdout')).write_bytes(result.stdout)
    (args.output / (label + '.stderr')).write_bytes(result.stderr)
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', result.stderr):
        raise SystemExit('sanitizer failure is not a valid assertion negative control: ' + label)
    summary = json.loads(result.stdout)
    if (result.returncode == 0) != expected or (summary['failures'] == 0) != expected:
        raise SystemExit('unexpected result: ' + label + ' ' + str(summary))
    records.append(dict(label=label, expected_pass=expected, returncode=result.returncode, **summary,
        command=command, generated_sha256=hashlib.sha256(program.encode()).hexdigest(), **prepared.manifest()))
for path, data in assets.items():
    assert path.read_bytes() == data
if args.baseline:
    assert records[0]['native_signatures'] == records[1]['native_signatures'], 'native stop trace regression'
(args.output / 'RESULT.json').write_text(json.dumps(dict(results=records,
    timer_irq_and_firmware_apis_modeled=True, real_kernel_concurrency_tested=False,
    full_qmi_or_remove_teardown_tested=False, hardware_tested=False, target_compiled=False,
    sanitizer=args.sanitize, test_assets=[dict(path=str(p), sha256=hashlib.sha256(d).hexdigest())
                                        for p, d in assets.items()]), indent=2) + '\n')
print(json.dumps([dict(label=r['label'], checks=r['checks'], failures=r['failures']) for r in records]))
