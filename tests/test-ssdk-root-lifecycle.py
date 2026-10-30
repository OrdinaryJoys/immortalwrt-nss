#!/usr/bin/env python3
"""A1 complete-function native fixture. Not a target build or lifetime proof."""
import argparse
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-root-lifecycle'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import replace_once, variants

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-root-rollback')
BASE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/ROOT-BASELINE-20261030-r1')
PATCH_SHA = '581d0a796edc3fe5564656a9294d42074f0b499ca2d5cdff586fdd90e67f86e8'
POINTER = ctypes.sizeof(ctypes.c_void_p)
NODE_SIZE = 2 * ctypes.sizeof(ctypes.c_int) + 24


def case(name, flow='topology', node=1, length=4, count=3, fault=0, existing=0, repeat=0):
    return {'name': name, 'flow': flow, 'node': node, 'length': length,
            'count': count, 'fault': fault, 'existing': existing, 'repeat': repeat}


def cases():
    rows = [case('no-node', node=0), case('missing-property', length=-1),
            case('present-zero', count=0), case('valid-one', count=1),
            case('valid-three'), case('valid-seven', count=7),
            case('valid-extra-cell', length=8), case('empty-property', length=0),
            *(case('short-' + name, length=i) for i, name in
              [(1, 'one'), (2, 'two'), (3, 'three')]),
            case('foreign-pointer', existing=1), case('foreign-count', existing=2),
            case('foreign-both', existing=3), case('repeat-zero', count=0, repeat=1),
            case('repeat-three', repeat=1), case('null-private-three', flow='null-private'),
            case('null-private-zero', flow='null-private', count=0),
            case('fail-array', fault=1), case('fail-child-one', fault=2),
            case('fail-child-two', fault=3), case('fail-child-three', fault=4),
            case('uint32-max-no-cap', count=4294967295, fault=1)]
    rows += [case('seven-fault-' + str(i), count=7, fault=i) for i in range(1, 9)]
    rows += [case('root-fail-array', flow='root', fault=1),
             case('root-no-node-fail-array', flow='root', node=0, fault=1),
             case('root-foreign', flow='root', existing=3),
             case('root-foreign-count', flow='root', existing=2),
             case('root-empty', flow='root', length=0),
             case('root-short', flow='root', length=2)]
    rows += [case('root-fail-child-' + str(i), flow='root', fault=i + 1)
             for i in range(1, 4)]
    rows += [case('root-private-array-' + str(n), flow='root-alloc', count=n, fault=n + 2)
             for n in (0, 1, 3, 7)]
    return rows


def expected(c):
    foreign = c['existing'] != 0
    has = c['node'] != 0
    present = c['length'] >= 0
    bad = has and present and c['length'] < 4
    count = c['count'] if has and present else 1
    ret = -errno.EBUSY if foreign else (
        -errno.ENODATA if bad and c['length'] == 0 else -errno.EOVERFLOW if bad else
        -errno.ENOMEM if c['fault'] else 0)
    out = {'ret': ret, 'find': int(not foreign), 'property': int(has and not foreign),
           'read': int(has and present and not foreign), 'raw': 0,
           'put': int(has and not foreign), 'refs': 0, 'stop': 0, 'retire': 0, 'logs': 0,
           'count': 1 if c['existing'] & 2 else 0,
           'table': bool(c['existing'] & 1), 'alloc': [], 'free': [],
           'node_size': NODE_SIZE, 'pointer_size': POINTER}
    if foreign or bad:
        return out
    allocation_shapes = [[1, count, POINTER]]
    if count <= 7:
        allocation_shapes += [[2, 1, NODE_SIZE] for _ in range(count)]
    if c['flow'] == 'root-alloc':
        allocation_shapes.append([2, 1, count * POINTER])
    fault = c['fault']
    for i, shape in enumerate(allocation_shapes, 1):
        out['alloc'].append(shape + [i != fault])
        if i == fault:
            break
    if fault:
        if c['flow'] == 'root-alloc':
            out['stop'] = out['retire'] = out['logs'] = 1
            out['free'] = list(range(2, count + 2)) + [1]
        elif fault > 1:
            out['free'] = list(range(fault - 1, 1, -1)) + [1]
    else:
        out['free'] = list(range(2, count + 2)) + [1]
        if c['flow'] == 'null-private':
            out['stop'] = out['retire'] = 1
    return out


def require(ok, message):
    source.require(ok, message)


def exact_positive(code, stdout, stderr, want):
    # Canonical bytes also reject duplicate JSON keys, extra lines and noise.
    require(code == 0 and stderr == b'', 'positive-process')
    actual = json.loads(stdout)
    require(actual == want, 'positive-ledger')
    require(stdout == (json.dumps(want, separators=(',', ':')) + '\n').encode(),
            'positive-exact-summary')


def exact_negative(code, stdout, stderr, marker):
    require(code == 86 and stdout == b'' and
            stderr == ('SSDK_A1 ' + marker + '\n').encode(), 'negative-exact-diagnostic')


def oracle_controls():
    passed = []
    summary = expected(cases()[0])
    good = (json.dumps(summary, separators=(',', ':')) + '\n').encode()
    exact_positive(0, good, b'', summary)
    exact_negative(86, b'', b'SSDK_A1 gate\n', 'gate')
    passed += ['positive-valid', 'negative-valid']
    controls = [
        ('positive-stderr', lambda: exact_positive(0, good, b'warning\n', summary)),
        ('positive-exit', lambda: exact_positive(86, good, b'', summary)),
        ('positive-extra-line', lambda: exact_positive(0, good + b'noise\n', b'', summary)),
        ('positive-count', lambda: exact_positive(0, good.replace(b'"find":1', b'"find":2'), b'', summary)),
        ('negative-exit', lambda: exact_negative(1, b'', b'SSDK_A1 gate\n', 'gate')),
        ('negative-signal', lambda: exact_negative(-6, b'', b'SSDK_A1 gate\n', 'gate')),
        ('negative-stdout', lambda: exact_negative(86, b'noise', b'SSDK_A1 gate\n', 'gate')),
        ('negative-extra-line', lambda: exact_negative(86, b'', b'SSDK_A1 gate\nnoise\n', 'gate')),
        ('negative-duplicate-line', lambda: exact_negative(86, b'', b'SSDK_A1 gate\nSSDK_A1 gate\n', 'gate')),
        ('negative-sanitizer', lambda: exact_negative(86, b'', b'SSDK_A1 gate\nERROR: AddressSanitizer\n', 'gate')),
        ('negative-wrong-marker', lambda: exact_negative(86, b'', b'SSDK_A1 other\n', 'gate')),
        ('negative-timeout', lambda: exact_negative(None, b'', b'SSDK_A1 gate\n', 'gate')),
    ]
    for name, control in controls:
        try:
            control()
        except (RuntimeError, ValueError, json.JSONDecodeError):
            passed.append(name)
        else:
            raise RuntimeError('oracle-pollution-accepted:' + name)
    return {'valid': 2, 'rejected': len(controls), 'names': passed}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def invoke(command, prefix, env, timeout=30):
    save_json(prefix.with_suffix('.command.json'), {'argv': command,
              'ASAN_OPTIONS': env.get('ASAN_OPTIONS'), 'UBSAN_OPTIONS': env.get('UBSAN_OPTIONS')})
    try:
        process = subprocess.run(command, capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        prefix.with_suffix('.stdout').write_bytes(error.stdout or b'')
        prefix.with_suffix('.stderr').write_bytes(error.stderr or b'')
        save_json(prefix.with_suffix('.exit.json'), {'returncode': None, 'timeout': True})
        raise RuntimeError('timeout-not-semantic-negative:' + str(prefix)) from error
    prefix.with_suffix('.stdout').write_bytes(process.stdout)
    prefix.with_suffix('.stderr').write_bytes(process.stderr)
    save_json(prefix.with_suffix('.exit.json'), {'returncode': process.returncode, 'timeout': False})
    return process


def sanitizer_env(base, code):
    env = dict(base)
    env['ASAN_OPTIONS'] = f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    env['UBSAN_OPTIONS'] = f'halt_on_error=1:print_stacktrace=1:exitcode={code}'
    return env


def sanitizer_controls(cc, flags, output, env):
    records = []
    canaries = [
        ('asan', 97, '#include <stdlib.h>\nint main(int argc,char **argv) { (void)argv; volatile int i=argc; char *p=malloc(1); p[i]=1; volatile char x=p[i]; free(p); return x; }\n',
         rb'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan', 98, '#include <limits.h>\nint main(int argc,char **argv) { (void)argv; volatile int x=INT_MAX; return x+argc; }\n',
         rb'runtime error: signed integer overflow'),
    ]
    for name, code, body, diagnostic in canaries:
        path = output / ('canary-' + name + '.c')
        path.write_text(body)
        binary = output / ('canary-' + name)
        build = invoke([cc, *flags, str(path), '-o', str(binary)], output / (name + '-compile'), env)
        require(build.returncode == 0 and build.stdout == build.stderr == b'', 'canary-compile')
        per_env = sanitizer_env(env, code)
        run = invoke([str(binary)], output / (name + '-run'), per_env)
        require(run.returncode == code and run.stdout == b'' and
                re.search(diagnostic, run.stderr), 'sanitizer-canary-activation')
        records.append({'name': name, 'exit': code, 'ASAN_OPTIONS': per_env['ASAN_OPTIONS'],
                        'UBSAN_OPTIONS': per_env['UBSAN_OPTIONS'], 'diagnostic_pattern': diagnostic.decode()})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True,
                        help='Fresh19 receipt directory, data only')
    parser.add_argument('--candidate-receipt-sha', required=True)
    parser.add_argument('--integration', type=Path,
                        help='Optional current20/release10 receipt, exact032 only')
    parser.add_argument('--integration-receipt-sha')
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require((args.integration is None) == (args.integration_receipt_sha is None),
            'integration-path-and-sha-pair')
    output = args.output.resolve()
    require(output.parent == AUDIT and output.name.startswith('A1-TEST-') and
            not output.exists(), 'fresh-authorized-output')
    output.mkdir(parents=True)
    result = {'status': 'INCOMPLETE', 'qualification': 'HOST_MODEL_ONLY_A1',
              'patch_sha256': PATCH_SHA, 'positives': [], 'negatives': [],
              'baseline_counterexamples': [], 'failures': 0,
              'scope': 'DT topology, actual regi_init early barrier, actual alloc_priv first-array failure and free_priv NULL boundary only',
              'open': ['A2', 'FAL/PHY and partial private slots', 'all target ABI/link/build/hardware',
                       'Linux OF execution, concurrency, RCU/lockdep, full module lifetime', 'LSan']}
    generated = {}
    bound = None
    try:
        bound = source.prepare(args.base.resolve(), args.candidate.resolve(),
                               args.candidate_receipt_sha, PATCH_SHA, output,
                               args.integration.resolve() if args.integration else None,
                               args.integration_receipt_sha)
        result['oracle_controls'] = oracle_controls()
        cc = shutil.which(args.cc)
        require(cc is not None, 'compiler-not-found')
        cc = str(Path(cc).resolve())
        result['compiler'] = {'path': cc, 'sha256': source.file_hash(cc)}
        env = dict(os.environ)
        env.pop('ASAN_OPTIONS', None)
        env.pop('UBSAN_OPTIONS', None)
        if args.sanitize:
            env = sanitizer_env(env, 97)
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
        result['flags'] = flags
        result['environment'] = {k: env.get(k) for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
        version = invoke([cc, '--version'], output / 'compiler-version', env)
        require(version.returncode == 0 and version.stderr == b'', 'compiler-version')
        if args.sanitize:
            result['sanitizer_canaries'] = sanitizer_controls(cc, flags, output, env)
        template = (SUPPORT / 'fixture.c').read_text()
        candidate_c, records = source.render(args.candidate / 'prepared', template)
        baseline_c, baseline_records = source.render(args.base / 'prepared', template)
        save_json(output / 'EXTRACTED.json', {'candidate': records, 'baseline': baseline_records,
                  'struct_OS_models': True, 'root_late_leaves': 'fail-fast, never exercised as success'})
        all_cases = {c['name']: c for c in cases()}
        save_json(output / 'CASES.json', [{**c, 'expected': expected(c)} for c in all_cases.values()])

        def compile_variant(name, text):
            path = output / (name + '.c')
            path.write_text(text)
            generated[str(path)] = source.file_hash(path)
            binary = output / name
            build = invoke([cc, *flags, str(path), '-o', str(binary)], output / (name + '-compile'), env)
            require(build.returncode == 0 and build.stdout == build.stderr == b'',
                    'compile-not-runtime-negative:' + name)
            return binary

        def run_case(binary, c, label, marker=None):
            command = [str(binary), c['flow'], str(c['node']), str(c['length']), str(c['count']),
                       str(c['fault']), str(c['existing']), str(c['repeat']), 'A1']
            run = invoke(command, output / label, env)
            if marker:
                exact_negative(run.returncode, run.stdout, run.stderr, marker)
                return {'name': label, 'case': c['name'], 'exit': 86, 'marker': marker,
                        'compile_clean': True, 'exact_stderr': True, 'empty_stdout': True}
            exact_positive(run.returncode, run.stdout, run.stderr, expected(c))
            return {'name': c['name'], 'exact_ledger': True, 'exit': 0}

        binary = compile_variant('candidate', candidate_c)
        for c in all_cases.values():
            result['positives'].append(run_case(binary, c, 'positive-' + c['name']))
        baseline = compile_variant('baseline18', baseline_c)
        for name, marker in [('present-zero', 'of-put-before-allocation'),
                             ('foreign-pointer', 'reentry-side-effect'),
                             ('no-node', 'publication-before-complete'),
                             ('root-no-node-fail-array', 'early-root-private')]:
            result['baseline_counterexamples'].append(run_case(
                baseline, all_cases[name], 'baseline-' + name, marker))
        # No-node witness isolates old NULL-private behavior from the old OF leak.
        old_null = case('baseline-null-private', flow='null-private', node=0)
        # The old early global publication is detected before reaching free_priv;
        # isolate only that complete baseline function with candidate DT/root.
        old_free = source.extract(args.base / 'prepared')[0]['ssdk_free_priv']
        new_free = source.extract(args.candidate / 'prepared')[0]['ssdk_free_priv']
        isolated = compile_variant('baseline-free-priv', replace_once(candidate_c, new_free, old_free))
        result['baseline_counterexamples'].append(run_case(
            isolated, old_null, 'baseline-null-private', 'null-private-topology'))
        bodies = source.extract(args.candidate / 'prepared')[0]
        for name, function, old, new, witness, marker in variants():
            body = bodies[function]
            altered = replace_once(body, old, new)
            mutant = compile_variant('mutant-' + name, replace_once(candidate_c, body, altered))
            result['negatives'].append(run_case(mutant, all_cases[witness], 'negative-' + name, marker))
        require(source.file_hash(cc) == result['compiler']['sha256'], 'end-compiler-drift')
        for path, identity in generated.items():
            require(source.file_hash(path) == identity, 'end-generated-drift')
        result['input_stability'] = source.stable(bound)
        result['generated'] = generated
        result['status'] = 'PASS'
    except Exception as error:
        result['status'] = 'FAIL'
        result['failures'] = 1
        result['error'] = str(error)
        if bound:
            try:
                result['input_stability_after_failure'] = source.stable(bound)
            except Exception as drift:
                result['input_stability_after_failure'] = str(drift)
    result['positive_count'] = len(result['positives'])
    result['runtime_mutant_count'] = len(result['negatives'])
    result['baseline_counterexample_count'] = len(result['baseline_counterexamples'])
    save_json(output / 'RESULTS.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'qualification', 'positive_count',
                                          'runtime_mutant_count', 'baseline_counterexample_count')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
