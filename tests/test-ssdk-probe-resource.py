#!/usr/bin/env python3
"""SSDK40 complete-probe host contract, not target ABI or shared retirement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
FIXTURE = HERE.parent / 'ssdk-probe-resource/fixture.c'
REL = 'src/init/ssdk_init.c'
OLD = '09f8a1d036ed63bce56ba1d69653870710865c9fcc68957bf92d82ca0d9ded4d'
CURRENT = '9590d2c01638765d4600984abe48f652f11cefb9d8fd43fc781acab7e7fb53b8'


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def extract(raw):
    text = raw.decode()
    rows = list(re.finditer(r'^static int ssdk_probe\(struct platform_device \*pdev\)\n\{.*?^\}', text, re.M | re.S))
    need(len(rows) == 1, 'one complete actual probe')
    return rows[0].group(), text[:rows[0].start()], text[rows[0].end():]


def replace(body, before, after):
    need(body.count(before) == 1, 'exact mutant anchor')
    return body.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--baseline39', type=Path)
    parser.add_argument('--functions-only', action='store_true', help='Frozen complete-function preflight, not SDK qualification')
    parser.add_argument('--cc', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    need(not out.exists(), 'fresh output')
    out.mkdir(parents=True)
    need((args.functions_only and args.prepared is None and args.baseline39 is None) or
         (not args.functions_only and args.prepared is not None and args.baseline39 is not None), 'explicit input mode')
    current_path = FIXTURE.parent / 'current40-probe.c' if args.functions_only else args.prepared / REL
    old_path = FIXTURE.parent / 'prefix39-probe.c' if args.functions_only else args.baseline39 / REL
    paths = [HERE, FIXTURE, FIXTURE.parent / 'README.md', current_path, old_path]
    inputs = {str(p.resolve()): sha(p.read_bytes()) for p in paths}
    result = {'status': 'INCOMPLETE', 'scope': 'HOST_MODEL_ONLY_NOT_SHARED_ROOT_OR_TARGET_ABI',
              'runtime_approved': False, 'of_reference_model': 'DYNAMIC_MODEL_NOT_CURRENT_AX6_LEAK_PROOF',
              'positive': [], 'negative': [], 'old_witnesses': [], 'inputs': inputs, 'commands': []}

    def put(name, raw):
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw.encode() if isinstance(raw, str) else raw)
        return path

    def invoke(name, argv):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
                   UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode=98')
        row = {'argv': argv, 'ASAN_OPTIONS': env['ASAN_OPTIONS'], 'UBSAN_OPTIONS': env['UBSAN_OPTIONS']}
        try:
            process = subprocess.run(argv, capture_output=True, env=env, timeout=30)
        except subprocess.TimeoutExpired as error:
            row.update(returncode=None, timeout=True)
            put(name + '.stdout', error.stdout or b''); put(name + '.stderr', error.stderr or b'')
            put(name + '.json', json.dumps(row, indent=2) + '\n')
            raise ValueError('timeout not a semantic failure') from error
        row.update(returncode=process.returncode, timeout=False)
        put(name + '.stdout', process.stdout); put(name + '.stderr', process.stderr)
        put(name + '.json', json.dumps(row, indent=2) + '\n')
        result['commands'].append(row)
        return process

    try:
        raw, previous = current_path.read_bytes(), old_path.read_bytes()
        if not args.functions_only:
            need(sha(raw) == CURRENT and sha(previous) == OLD, 'frozen complete current40 and prefix39 files')
        body, start, end = extract(raw)
        before, old_start, old_end = extract(previous)
        need(sha(body.encode()) == '520b877bb83bf62f7a033416e0800f445da7185931d662a95e657bab2a675084' and
             sha(before.encode()) == 'cf4f54e388d0230e0a50c294290e0310929d8b1d88942195582c39658e0d1c82', 'fixed actual probe bodies')
        need((start, end) == (old_start, old_end), 'no change outside complete probe')
        variants = {
            'missing-put': (replace(body, '\tof_node_put(np);', '\t/* source mutant: no put */'), 1, 'NODE_REF'),
            'double-put': (replace(body, '\tof_node_put(np);', '\tof_node_put(np);\n\tof_node_put(np);'), 1, 'NODE_REF'),
            'missing-oom-check': (replace(body, '\tif (!priv) {\n\t\trv = -ENOMEM;\n\t\tgoto out;\n\t}', ''), 5, 'NULL_PRIVATE'),
            'lost-populate-error': (replace(body, 'rv = of_platform_populate(np, NULL, NULL, &pdev->dev);', 'rv = of_platform_populate(np, NULL, NULL, &pdev->dev);\n\t\trv = 0;'), 9, 'RETURN_VALUE'),
            'missing-publication': (replace(body, '\tplatform_set_drvdata(pdev, priv);', '\t/* source mutant: no publication */'), 1, 'PUBLISHED_POINTER'),
            'lost-device-id': (replace(body, '\tof_property_read_u32(np, "device_id", &(priv->dev_id));', '\t/* source mutant: no property */'), 1, 'PROPERTY_PATH'),
            'wrong-oom-result': (replace(body, '\t\trv = -ENOMEM;', '\t\trv = 0;'), 5, 'RETURN_VALUE'),
        }
        cc = shutil.which(args.cc)
        need(cc is not None, 'host compiler')
        cc = str(Path(cc).resolve())
        flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        result['compiler'] = {'path': cc, 'sha256': sha(Path(cc).read_bytes()), 'flags': flags}

        def compile_one(label, code):
            put(label + '/actual.c', code + '\n')
            fixture = put(label + '/fixture.c', FIXTURE.read_bytes())
            binary = out / label / 'fixture'
            process = invoke(label + '/compile', [cc, *flags, str(fixture), '-o', str(binary)])
            need(process.returncode == 0 and process.stdout == process.stderr == b'', 'clean compilation: ' + label)
            return binary

        current = compile_one('current40', body)
        for index in range(12):
            process = invoke('current40/case-' + str(index), [str(current), str(index)])
            need(process.returncode == 0 and process.stdout == b'PROBE:PASS\n' and not process.stderr, 'exact positive')
            result['positive'].append(index)
        for label, (variant, index, marker) in variants.items():
            binary = compile_one('negative/' + label, variant)
            process = invoke('negative/' + label + '/run', [str(binary), str(index)])
            need(process.returncode == 86 and not process.stdout and process.stderr == ('PROBE:' + marker + '\n').encode(), 'exact source negative: ' + label)
            result['negative'].append({'name': label, 'case': index, 'marker': marker})
        old = compile_one('prefix39', before)
        for index, marker in [(1, 'NODE_REF'), (5, 'NULL_PRIVATE'), (9, 'NODE_REF')]:
            process = invoke('prefix39/case-' + str(index), [str(old), str(index)])
            need(process.returncode == 86 and not process.stdout and process.stderr == ('PROBE:' + marker + '\n').encode(), 'exact old witness')
            result['old_witnesses'].append({'case': index, 'marker': marker})
        need(all(sha(Path(p).read_bytes()) == value for p, value in inputs.items()), 'end input identity')
        result.update(status=('PASS_PROBE_FUNCTION_PREFLIGHT_NOT_PREPARED_SSDK' if args.functions_only else 'PASS_SSDK40_PROBE_HOST_ONLY'), positive_count=12, negative_count=7, old_witness_count=3,
                      actual_source_sha256=sha(raw), prefix39_source_sha256=sha(previous),
                      open=['UK/SD/PHY root rollback and shared lifetime', 'populate child rollback',
                            'real OF/devres/module concurrency', 'target ABI and performance'])
    except Exception as error:
        result['error'] = str(error)
    put('RESULTS.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'positive_count', 'negative_count', 'old_witness_count', 'error') if key in result}))
    return 0 if result['status'] in ('PASS_SSDK40_PROBE_HOST_ONLY', 'PASS_PROBE_FUNCTION_PREFLIGHT_NOT_PREPARED_SSDK') else 1


if __name__ == '__main__':
    raise SystemExit(main())
