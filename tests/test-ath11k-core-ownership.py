#!/usr/bin/env python3
"""Compile complete prepared core startup functions against explicit API contracts."""
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
parser.add_argument('--expect-failure', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-core-ownership/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}
variants = [('candidate', args.prepared, not args.expect_failure)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in
        ('skip-dbs-cleanup', 'destroy-borrowed-start', 'unregister-borrowed-mac',
         'unregister-skipped-thermal', 'destroy-borrowed-ready')]
records = []
for name, root, expected in variants:
    tree = extract.Prepared(root)
    path = 'drivers/net/wireless/ath/ath11k/core.c'
    functions = {symbol: tree.function(path, symbol) for symbol in (
        'ath11k_core_stop', 'ath11k_core_pdev_create', 'ath11k_core_start', 'ath11k_core_qmi_firmware_ready')}
    edits = {
        'skip-dbs-cleanup': ('ath11k_core_start', '"failed to send dbs mode: %d\\n", ret);\n\t\t\tgoto err_reo_cleanup;',
                            '"failed to send dbs mode: %d\\n", ret);\n\t\t\tgoto err_hif_stop;'),
        'destroy-borrowed-start': ('ath11k_core_start', 'if (!mac_registered)\n\t\tath11k_mac_destroy(ab);', 'ath11k_mac_destroy(ab);'),
        'unregister-borrowed-mac': ('ath11k_core_pdev_create', 'if (!mac_registered)\n\t\tath11k_mac_unregister(ab);', 'ath11k_mac_unregister(ab);'),
        'unregister-skipped-thermal': ('ath11k_core_pdev_create', 'if (!mac_registered)\n\t\tath11k_thermal_unregister(ab);', 'ath11k_thermal_unregister(ab);'),
        'destroy-borrowed-ready': ('ath11k_core_qmi_firmware_ready', 'if (!mac_registered)\n\t\tath11k_mac_destroy(ab);', 'ath11k_mac_destroy(ab);'),
    }
    if name in edits:
        symbol, before, after = edits[name]
        assert functions[symbol].count(before) == 1
        if name != 'skip-dbs-cleanup':
            after = '(void)mac_registered;\n\t' + after
        functions[symbol] = functions[symbol].replace(before, after, 1)
    code = assets[HERE / 'ath11k-core-ownership/host-fixture.c'].decode().replace('HOST_FUNCTIONS', ''.join(functions.values()))
    source = args.output / (name + '.c')
    source.write_text(code)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(source.with_suffix('.host'))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / (name + '-compile.stderr')).write_bytes(compiled.stderr)
    if compiled.returncode:
        raise SystemExit(compiled.stderr.decode())
    ran = subprocess.run([str(source.with_suffix('.host'))], capture_output=True, timeout=30)
    (args.output / (name + '.stdout')).write_bytes(ran.stdout)
    (args.output / (name + '.stderr')).write_bytes(ran.stderr)
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', ran.stderr):
        raise SystemExit('sanitizer failure is not an assertion-based negative control')
    result = json.loads(ran.stdout)
    assert (ran.returncode == 0) == expected and (result['failures'] == 0) == expected, (name, result)
    records.append(dict(variant=name, expected_pass=expected, command=command,
        generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **result, **tree.manifest()))
assert len({r['normal_signature'] for r in records}) == 1
assert all(p.read_bytes() == data for p, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    assets={str(p): hashlib.sha256(b).hexdigest() for p, b in assets.items()},
    scope='Four complete prepared core functions; child/API resource ownership modeled. CE, thermal restoration, NSS internals and real concurrency remain outside scope.',
    target_compiled=False, hardware_accessed=False), indent=2) + '\n')
print(json.dumps([{k: r[k] for k in ('variant', 'scenarios', 'checks', 'failures')} for r in records]))
