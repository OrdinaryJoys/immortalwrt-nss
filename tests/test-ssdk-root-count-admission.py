#!/usr/bin/env python3
"""COUNT21 complete-function native fixture; no old native PASS is reused."""
import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-root-count'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import once, variants

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-root-admission')
BASE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/ROOT-A2-CANDIDATE-20261030-r2')
POINTER = ctypes.sizeof(ctypes.c_void_p)
NODE_SIZE = 2 * ctypes.sizeof(ctypes.c_int) + 24


def require(ok, marker):
    source.require(ok, marker)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def case(name, flow='topology', node=1, length=4, count=3, fault=0, existing=0, repeat=0):
    return {'name': name, 'flow': flow, 'node': node, 'length': length,
            'count': count, 'fault': fault, 'existing': existing, 'repeat': repeat}


def cases():
    rows = [case('default-no-node', node=0, count=4294967295),
            case('default-no-property', length=-1, count=7),
            case('zero', count=0), case('one', count=1), case('two', count=2), case('three'),
            case('three-extra-cell', length=8),
            case('over-four', count=4), case('over-seven', count=7),
            case('over-uint32-max', count=4294967295),
            case('over-before-fault', count=4, fault=1),
            case('malformed-empty-over', length=0, count=7),
            case('malformed-short-over', length=1, count=4294967295),
            case('malformed-short-two', length=2, count=4),
            case('malformed-short-three', length=3, count=7),
            case('foreign-pointer', existing=1), case('foreign-count', existing=2),
            case('foreign-over', existing=3, count=7),
            case('foreign-malformed-over', existing=3, length=1, count=4294967295),
            case('repeat-zero', count=0, repeat=1), case('repeat-three', repeat=1),
            case('null-private-zero', flow='null-private', count=0),
            case('null-private-three', flow='null-private')]
    for n, word in enumerate(('zero', 'one', 'two', 'three')):
        rows += [case(f'{word}-fault-{i}', count=n, fault=i) for i in range(1, n + 2)]
        rows.append(case(f'root-private-{word}', flow='root-alloc', count=n, fault=n + 2))
        rows += [case(f'root-{word}-fault-{i}', flow='root', count=n, fault=i)
                 for i in range(1, n + 2)]
    rows += [case('root-over-four', flow='root', count=4),
             case('root-over-seven', flow='root', count=7),
             case('root-over-max', flow='root', count=4294967295),
             case('root-foreign-over', flow='root', count=7, existing=3),
             case('root-malformed-over', flow='root', count=4294967295, length=1),
             case('root-default-private', flow='root-alloc', node=0, count=7, fault=3)]
    for label, node, length in [('no-node', 0, 4), ('no-property', 1, -1)]:
        for flow in ('topology', 'root'):
            rows += [case(f'default-{label}-{flow}-fault-{i}', flow=flow,
                          node=node, length=length, count=7, fault=i)
                     for i in (1, 2)]
    rows.append(case('root-no-property-private', flow='root-alloc',
                     length=-1, count=7, fault=3))
    return rows


def oracle(c, capacity):
    foreign = c['existing'] != 0
    has, present = c['node'] != 0, c['length'] >= 0
    n = c['count'] if has and present else 1
    malformed = has and present and c['length'] < 4
    prep = (-errno.ENODATA if c['length'] == 0 else -errno.EOVERFLOW) if malformed else 0
    ret = -errno.EBUSY if foreign else prep or (-errno.EINVAL if n > capacity else
                                               -errno.ENOMEM if c['fault'] else 0)
    lines = []
    add = lines.append
    if not foreign:
        add(f'OF_FIND {int(has)}\n')
        if has:
            add(f'OF_PROPERTY {c["length"]}\n')
            if present:
                add(f'OF_READ {prep} {0 if prep else c["count"]}\n')
            add('OF_PUT 0\n')
    if not foreign and not prep and n <= capacity:
        specs = [(1, n, POINTER)] + [(2, 1, NODE_SIZE) for _ in range(n)]
        if c['flow'] == 'root-alloc':
            specs.append((2, 1, n * POINTER))
        for i, (kind, count, size) in enumerate(specs, 1):
            ok = i != c['fault']
            add(f'ALLOC {kind} {count} {size} {i} {int(ok)}\n')
            if not ok:
                if c['flow'] == 'root-alloc':
                    add(f'LOG qca-ssdk module init failed! (code: {-errno.ENOMEM})\n')
                    add('CONTROL cache\n')
                    add('CONTROL retire\n')
                    free_ids = list(range(2, n + 2)) + [1]
                else:
                    free_ids = list(range(i - 1, 1, -1)) + ([1] if i > 1 else [])
                for ident in free_ids:
                    add(f'FREE {ident}\n')
                break
    if foreign:
        add(f'STATE return {int(bool(c["existing"] & 2))} {int(bool(c["existing"] & 1))}\n')
    elif not ret:
        add(f'STATE return {n} 1\n')
        for i in range(n):
            add(f'NODE {i} 0 0 1\n')
        if c['repeat']:
            add(f'REENTRY {-errno.EBUSY}\n')
        if c['flow'] == 'null-private':
            add('CONTROL cache\n')
            add('CONTROL retire\n')
        for ident in list(range(2, n + 2)) + [1]:
            add(f'FREE {ident}\n')
    else:
        add('STATE return 0 0\n')
    if not foreign:
        add('STATE exit 0 0\n')
        add('STATE repeat-exit 0 0\n')
    return ret, ''.join(lines)


def positive(code, stdout, stderr, expected):
    require(code == 0 and stdout == expected and stderr == b'', 'positive-exact-trace')


def negative(code, stdout, stderr, marker):
    require(code == 86 and stdout == b'' and stderr == ('SSDK_COUNT ' + marker + '\n').encode(),
            'negative-exact-marker')


def controls():
    positive(0, b'exact\n', b'', b'exact\n')
    negative(86, b'', b'SSDK_COUNT gate\n', 'gate')
    checks = [
        ('positive-exit', lambda: positive(86, b'exact\n', b'', b'exact\n')),
        ('positive-noise', lambda: positive(0, b'exact\nnoise', b'', b'exact\n')),
        ('positive-stderr', lambda: positive(0, b'exact\n', b'warning', b'exact\n')),
        ('negative-code', lambda: negative(1, b'', b'SSDK_COUNT gate\n', 'gate')),
        ('negative-signal', lambda: negative(-6, b'', b'SSDK_COUNT gate\n', 'gate')),
        ('negative-timeout', lambda: negative(None, b'', b'SSDK_COUNT gate\n', 'gate')),
        ('negative-stdout', lambda: negative(86, b'noise', b'SSDK_COUNT gate\n', 'gate')),
        ('negative-extra-line', lambda: negative(86, b'', b'SSDK_COUNT gate\nnoise\n', 'gate')),
        ('negative-duplicate', lambda: negative(86, b'', b'SSDK_COUNT gate\nSSDK_COUNT gate\n', 'gate')),
        ('negative-sanitizer', lambda: negative(86, b'', b'SSDK_COUNT gate\nERROR: AddressSanitizer\n', 'gate')),
        ('negative-wrong-marker', lambda: negative(86, b'', b'SSDK_COUNT other\n', 'gate')),
    ]
    for name, call in checks:
        try:
            call()
        except RuntimeError as error:
            require(str(error) in ('positive-exact-trace', 'negative-exact-marker'), 'control-wrong-failure')
        else:
            raise RuntimeError('pollution-accepted:' + name)
    return {'valid': 2, 'rejected': len(checks), 'names': [name for name, _ in checks]}


def invoke(command, prefix, env, timeout=30):
    save(prefix.with_suffix('.command.json'), {'argv': command,
         'ASAN_OPTIONS': env.get('ASAN_OPTIONS'), 'UBSAN_OPTIONS': env.get('UBSAN_OPTIONS')})
    try:
        run = subprocess.run(command, env=env, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        prefix.with_suffix('.stdout').write_bytes(error.stdout or b'')
        prefix.with_suffix('.stderr').write_bytes(error.stderr or b'')
        save(prefix.with_suffix('.exit.json'), {'returncode': None, 'timeout': True})
        raise RuntimeError('timeout-not-semantic-credit:' + str(prefix)) from error
    prefix.with_suffix('.stdout').write_bytes(run.stdout)
    prefix.with_suffix('.stderr').write_bytes(run.stderr)
    save(prefix.with_suffix('.exit.json'), {'returncode': run.returncode, 'timeout': False})
    return run


def san_env(env, code):
    result = dict(env)
    result['ASAN_OPTIONS'] = f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    result['UBSAN_OPTIONS'] = f'halt_on_error=1:print_stacktrace=1:exitcode={code}'
    return result


def canaries(cc, flags, output, env, generated):
    rows = [
        ('asan', 97, '#include <stdlib.h>\nint main(int argc,char **argv) { (void)argv; volatile int i=argc; char *p=malloc(1); p[i]=1; volatile char x=p[i]; free(p); return x; }\n',
         rb'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan', 98, '#include <limits.h>\nint main(int argc,char **argv) { (void)argv; volatile int x=INT_MAX; return x+argc; }\n',
         rb'runtime error: signed integer overflow')]
    records = []
    for name, code, text, pattern in rows:
        path = output / ('canary-' + name + '.c')
        path.write_text(text)
        generated[str(path)] = source.identity(path)
        binary = output / ('canary-' + name)
        build = invoke([cc, *flags, str(path), '-o', str(binary)], output / (name + '-compile'), env)
        require(build.returncode == 0 and build.stdout == build.stderr == b'', 'canary-compile')
        per_case = san_env(env, code)
        run = invoke([str(binary)], output / (name + '-run'), per_case)
        require(run.returncode == code and run.stdout == b'' and re.search(pattern, run.stderr), 'canary-activation')
        records.append({'name': name, 'exit': code, 'ASAN_OPTIONS': per_case['ASAN_OPTIONS'],
                        'UBSAN_OPTIONS': per_case['UBSAN_OPTIONS'], 'diagnostic_pattern': pattern.decode()})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='Frozen21 receipt directory')
    parser.add_argument('--candidate-receipt-sha', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.parent == AUDIT and output.name.startswith('COUNT-TEST-') and not output.exists(), 'fresh-output')
    output.mkdir(parents=True)
    result = {'status': 'INCOMPLETE', 'qualification': 'HOST_MODEL_ONLY_COUNT_ADMISSION',
              'positives': [], 'old20_counterexamples': [], 'runtime_mutants': [], 'failures': 0,
              'open': ['target ABI/build/device', 'Linux OF/RCU/concurrency', 'FAL/PHY and partial private slots',
                       'full root lifecycle and cleanup safety', 'LSan', 'old A1/A2 qualification not upgraded']}
    inputs = None
    generated = {}
    try:
        inputs = source.prepare(args.base.resolve(), args.candidate.resolve(), args.candidate_receipt_sha, output)
        result['gate_controls'] = controls()
        cc = shutil.which(args.cc)
        require(cc is not None, 'compiler-path')
        cc = str(Path(cc).resolve())
        result['compiler'] = {'path': cc, 'sha256': source.identity(cc)}
        env = dict(os.environ)
        env.pop('ASAN_OPTIONS', None)
        env.pop('UBSAN_OPTIONS', None)
        if args.sanitize:
            env = san_env(env, 97)
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wformat=2', '-Wno-unused-function']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
        result['flags'] = flags
        result['environment'] = {name: env.get(name) for name in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
        version = invoke([cc, '--version'], output / 'compiler-version', env)
        require(version.returncode == 0 and version.stderr == b'', 'compiler-version')
        if args.sanitize:
            result['canaries'] = canaries(cc, flags, output, env, generated)
        template = (SUPPORT / 'fixture.c').read_text()
        current, records, capacity = source.render(args.candidate / 'prepared', template)
        old, old_records, old_capacity = source.render(args.base / 'prepared', template)
        require(capacity == old_capacity == inputs['actual_capacity'], 'same-actual-capacity')
        save(output / 'EXTRACTED.json', {'candidate': records, 'baseline': old_records,
             'capacity': capacity, 'capacity_header': 'include/common/sw_config.h',
             'native_OS_struct_models': True, 'root_late_leaves': 'fail-fast, not success models'})
        matrix = {c['name']: c for c in cases()}
        require(len(matrix) == len(cases()), 'unique-cases')
        save(output / 'CASES.json', [{**c, 'expected_return': oracle(c, capacity)[0],
             'expected_trace': oracle(c, capacity)[1]} for c in matrix.values()])

        def compile_variant(name, text):
            path = output / (name + '.c')
            path.write_text(text)
            generated[str(path)] = source.identity(path)
            binary = output / name
            build = invoke([cc, *flags, str(path), '-o', str(binary)], output / (name + '-compile'), env)
            require(build.returncode == 0 and build.stdout == build.stderr == b'', 'compile-not-runtime-credit:' + name)
            return binary

        def execute(binary, c, label, marker=None):
            ret, trace = oracle(c, capacity)
            path = output / (label + '.oracle')
            path.write_text(trace)
            generated[str(path)] = source.identity(path)
            command = [str(binary), c['flow'], str(c['node']), str(c['length']), str(c['count']),
                       str(c['fault']), str(c['existing']), str(c['repeat']), str(ret), str(path)]
            run = invoke(command, output / label, env)
            if marker:
                negative(run.returncode, run.stdout, run.stderr, marker)
                return {'name': label, 'case': c['name'], 'marker': marker, 'exit': 86,
                        'compile_clean': True, 'empty_stdout': True, 'unique_exact_stderr': True}
            positive(run.returncode, run.stdout, run.stderr, (f'RESULT {ret}\n' + trace).encode())
            return {'name': c['name'], 'exact_return_and_full_trace': True}

        binary = compile_variant('candidate21', current)
        for c in matrix.values():
            result['positives'].append(execute(binary, c, 'positive-' + c['name']))
        baseline = compile_variant('baseline20', old)
        for name in ('over-four', 'over-seven', 'over-uint32-max', 'root-over-four'):
            result['old20_counterexamples'].append(execute(baseline, matrix[name], 'old20-' + name,
                                                         'count-admitted-to-allocator'))
        bodies = source.extract(args.candidate / 'prepared')[0]
        for name, function, before, after, witness, marker in variants():
            changed = once(bodies[function], before, after)
            mutant = compile_variant('mutant-' + name, once(current, bodies[function], changed))
            result['runtime_mutants'].append(execute(mutant, matrix[witness], 'negative-' + name, marker))
        require(source.identity(cc) == result['compiler']['sha256'], 'end-compiler-drift')
        for name, expected in generated.items():
            require(source.identity(name) == expected, 'end-generated-or-oracle-drift')
        result['generated'] = generated
        result['input_stability'] = source.stable(inputs)
        result['status'] = 'PASS'
    except Exception as error:
        result['status'] = 'FAIL'
        result['failures'] = 1
        result['error'] = str(error)
        if inputs:
            try:
                result['input_stability_after_failure'] = source.stable(inputs)
            except Exception as drift:
                result['input_stability_after_failure'] = str(drift)
    for key in ('positives', 'old20_counterexamples', 'runtime_mutants'):
        result[key + '_count'] = len(result[key])
    save(output / 'RESULTS.json', result)
    print(json.dumps({name: result[name] for name in ('status', 'qualification', 'positives_count',
                     'old20_counterexamples_count', 'runtime_mutants_count')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
