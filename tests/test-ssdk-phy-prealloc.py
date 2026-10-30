#!/usr/bin/env python3
"""Fresh exact22 native allocation contract, explicitly not target/module runtime."""
import argparse
import errno
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-phy-prealloc'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import once, variants

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-phy-prealloc')
OLD_ROOT = AUDIT.parent / 'ssdk-dp-retirement'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def case(name, flow, count=1, fault=0, scenario=0):
    row = dict(name=name, flow=flow, count=count, fault=fault, scenario=scenario)
    if scenario in (5, 6, 62):
        row['foreign_slot'] = 0 if scenario == 5 else 2
        row['foreign_relation'] = 'inside' if row['foreign_slot'] < count else 'outside'
    return row


def cases():
    rows = [case('prepare-ok', 'prepare'), case('prepare-enomem', 'prepare', fault=1),
            case('prepare-null-out', 'prepare', scenario=1), case('prepare-null-map', 'prepare', scenario=2),
            case('prepare-owned', 'prepare', scenario=3)]
    for n in range(4):
        for flow in ('alloc', 'root'):
            rows.append(case(f'{flow}-{n}-ok', flow, n))
            rows += [case(f'{flow}-{n}-fault-{i}', flow, n, i) for i in range(1, 2 * n + 2)]
            for label, scenario in [('foreign-inside', 5), ('foreign-outside', 6), ('private', 60)]:
                rows.append(case(f'{flow}-{n}-{label}', flow, n, scenario=scenario))
            if n:
                rows += [case(f'{flow}-{n}-late-private', flow, n, scenario=61),
                         case(f'{flow}-{n}-late-meta', flow, n, scenario=62)]
        rows.append(case(f'publish-{n}-ok', 'publish', n))
        for label, scenario in [('null-array', 1), ('null-maps', 2), ('foreign-inside', 5),
                                ('foreign-outside', 6)]:
            rows.append(case(f'publish-{n}-{label}', 'publish', n, scenario=scenario))
        if n:
            rows.append(case(f'publish-{n}-missing', 'publish', n, scenario=3))
        if n > 1:
            rows.append(case(f'publish-{n}-duplicate', 'publish', n, scenario=4))
        rows.append(case(f'legacy-{n}-ok', 'legacy', n))
        if n < 3:
            rows += [case(f'legacy-{n}-busy', 'legacy', n, scenario=3),
                     case(f'legacy-{n}-enomem', 'legacy', n, fault=1)]
    rows += [case('alloc-over', 'alloc', 4), case('publish-over', 'publish', 4),
             case('legacy-max', 'legacy', 4294967295)]
    return rows


def oracle(c):
    """Independent action/owner trace model; no candidate function parsing here."""
    f, n, fault, s = (c[k] for k in ('flow', 'count', 'fault', 'scenario'))
    events, live = [], []
    emit = events.append
    attempt = 0

    def allocate(kind):
        nonlocal attempt
        attempt += 1
        ok = attempt != fault
        emit(f'ALLOC {attempt} {kind} {int(ok)}\n')
        if ok:
            live.append(attempt)
        if not ok and kind == 'M':
            emit('LOG META_ENOMEM\n')
        return ok

    def release():
        while live:
            emit(f'FREE {live.pop()}\n')

    ret = 0
    if f in ('alloc', 'root'):
        if f == 'root':
            emit(f'TOPO INIT {n}\n')
        if n > 3:
            ret = -errno.EINVAL
        elif s == 60:
            ret = -errno.EBUSY
        elif not allocate('V'):
            ret = -errno.ENOMEM
        else:
            for _ in range(n):
                if not allocate('P') or not allocate('M'):
                    ret = -errno.ENOMEM
                    break
                emit('SETUP FDB\n'); emit('SETUP IRQ\n')
            if not ret and s in (61, 62):
                emit('INJECT ' + ('PRIVATE\n' if s == 61 else 'META\n'))
            if not ret and s in (5, 6, 61, 62):
                ret = -errno.EBUSY
            if ret:
                release()
        if f == 'root':
            if ret:
                emit('TOPO EXIT\n')
            elif n:
                emit('CFG LEAF\n'); emit('STOP DT\n')
            else:
                emit('STOP ZERO_SYSFS\n')
        if not ret:
            for d in range(n): emit(f'META {d} FULL_BASELINE_MATCH\n')
            emit(f'TRANSFER {n}\n')
    elif f == 'prepare':
        if s in (1, 2): ret = -errno.EINVAL
        elif s == 3: ret = -errno.EBUSY
        elif not allocate('M'): ret = -errno.ENOMEM
        else: emit('META 1 FULL_BASELINE_MATCH\n')
    elif f == 'legacy':
        if n >= 3: ret = -errno.EINVAL
        elif s == 3: ret = -errno.EBUSY
        elif not allocate('M'): ret = -errno.ENOMEM
        else: emit(f'META {n} FULL_BASELINE_MATCH\n')
    elif f == 'publish':
        for _ in range(n):
            source.require(allocate('M'), 'oracle-publish-preparation')
        if s in (1, 2) or n > 3: ret = -errno.EINVAL
        elif s in (5, 6): ret = -errno.EBUSY
        elif s == 3 and n or s == 4 and n > 1: ret = -errno.EINVAL
        else:
            for d in range(n): emit(f'META {d} FULL_BASELINE_MATCH\n')
            emit(f'PUBLISH {n}\n')
    else: raise RuntimeError('oracle-flow')
    emit(f'RETURN {ret}\n'); emit('MODEL_CLEANUP\n'); release(); emit('END CLEAN\n')
    return ret, ''.join(events).encode()


def positive(code, out, err, expected):
    source.require(code == 0 and out == expected and err == b'', 'positive-exact-output')


def negative(code, out, err, marker):
    source.require(code == 86 and out == b'' and err == f'SSDK_PHY {marker}\n'.encode(),
                   'negative-exact-marker')


def gates():
    positive(0, b'exact\n', b'', b'exact\n'); negative(86, b'', b'SSDK_PHY X\n', 'X')
    polluted = [
        lambda: positive(1, b'exact\n', b'', b'exact\n'),
        lambda: positive(0, b'exact\nnoise', b'', b'exact\n'),
        lambda: positive(0, b'exact\n', b'warning', b'exact\n')]
    polluted += [lambda code=code, out=out, err=err: negative(code, out, err, 'X')
                 for code, out, err in [(1, b'', b'SSDK_PHY X\n'), (-6, b'', b'SSDK_PHY X\n'),
                 (None, b'', b'SSDK_PHY X\n'), (86, b'noise', b'SSDK_PHY X\n'),
                 (86, b'', b'SSDK_PHY Y\n'), (86, b'', b'SSDK_PHY X\nSSDK_PHY X\n'),
                 (86, b'', b'SSDK_PHY X\nERROR: AddressSanitizer\n')]]
    for call in polluted:
        try: call()
        except RuntimeError: pass
        else: raise RuntimeError('gate-accepted-pollution')
    return {'valid': 2, 'rejects': len(polluted)}


def invoke(argv, prefix, env):
    save(prefix.with_suffix('.command.json'), {'argv': argv, 'environment': {
        k: env.get(k) for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}})
    try:
        run = subprocess.run(argv, capture_output=True, env=env, timeout=60)
    except subprocess.TimeoutExpired as e:
        prefix.with_suffix('.stdout').write_bytes(e.stdout or b'')
        prefix.with_suffix('.stderr').write_bytes(e.stderr or b'')
        save(prefix.with_suffix('.exit.json'), {'returncode': None, 'timeout': True})
        raise RuntimeError('timeout-is-not-semantic-credit') from e
    prefix.with_suffix('.stdout').write_bytes(run.stdout)
    prefix.with_suffix('.stderr').write_bytes(run.stderr)
    save(prefix.with_suffix('.exit.json'), {'returncode': run.returncode, 'timeout': False})
    return run


def optimization_controls(output, env):
    script = r'''
import pathlib, sys
path, variant = sys.argv[1:]
text = pathlib.Path(path).read_text()
if variant == 'old_assert':
    before = '\n' + ' ' * 12 + "source.require(allocate('M'), 'oracle-publish-preparation')" + '\n'
    if text.count(before) != 1:
        raise RuntimeError('old-assert-control-occurrence')
    text = text.replace(before, '\n' + ' ' * 12 + "assert allocate('M')" + '\n', 1)
namespace = {'__file__': path, '__name__': 'phy_oracle_control'}
exec(compile(text, path, 'exec'), namespace)
expected = (b'ALLOC 1 M 1\nALLOC 2 M 1\n'
            b'META 0 FULL_BASELINE_MATCH\nMETA 1 FULL_BASELINE_MATCH\n'
            b'PUBLISH 2\nRETURN 0\nMODEL_CLEANUP\nFREE 2\nFREE 1\nEND CLEAN\n')
actual = namespace['oracle'](namespace['case']('probe', 'publish', 2))
if variant == 'old_assert' and sys.flags.optimize:
    broken = expected.replace(b'ALLOC 1 M 1\nALLOC 2 M 1\n', b'').replace(b'FREE 2\nFREE 1\n', b'')
    if actual != (0, broken):
        raise RuntimeError('unexpected-old-assert-control-result')
    sys.stderr.write('SSDK_PHY PYTHON_ASSERT_SIDE_EFFECT\n')
    sys.exit(86)
if actual != (0, expected):
    raise RuntimeError('optimization-oracle-mismatch')
print(f'PYTHON_ORACLE_OK {variant} optimize={sys.flags.optimize}')
'''
    used = dict(env)
    used.pop('PYTHONOPTIMIZE', None)
    rows = []
    for variant in ('current', 'old_assert'):
        for level, flags in [(0, []), (1, ['-O']), (2, ['-OO'])]:
            prefix = output / f'python-{variant}-O{level}'
            p = invoke([sys.executable, '-B', *flags, '-c', script,
                        str(Path(__file__).resolve()), variant], prefix, used)
            reject = variant == 'old_assert' and level > 0
            if reject:
                negative(p.returncode, p.stdout, p.stderr, 'PYTHON_ASSERT_SIDE_EFFECT')
            else:
                expected = f'PYTHON_ORACLE_OK {variant} optimize={level}\n'.encode()
                positive(p.returncode, p.stdout, p.stderr, expected)
            rows.append({'variant': variant, 'optimization': level,
                         'outcome': 'EXACT_OLD_ASSERT_COUNTEREXAMPLE' if reject else 'EXACT_CURRENT_ORACLE'})
    return rows


def write_expected(path, expected, generated):
    path.write_bytes(expected)
    generated[str(path)] = source.digest(expected)


def verify_generated(generated):
    for name, sha in generated.items():
        path = Path(name)
        source.require(path.is_file() and not path.is_symlink(), 'generated-shape:' + name)
        source.require(source.identity(path) == sha, 'generated-drift:' + name)


def expected_controls(output):
    rows = []
    for kind in ('unchanged', 'modified', 'truncated', 'deleted', 'renamed'):
        folder = output / ('expected-control-' + kind)
        folder.mkdir()
        path = folder / 'trace.expected'
        bound = {}
        write_expected(path, b'exact\n', bound)
        if kind == 'modified':
            path.write_bytes(b'wrong\n')
        elif kind == 'truncated':
            path.write_bytes(b'')
        elif kind == 'deleted':
            path.unlink()
        elif kind == 'renamed':
            path.rename(folder / 'renamed.expected')
        marker = ('generated-drift:' if kind in ('modified', 'truncated')
                  else 'generated-shape:') + str(path)
        try:
            verify_generated(bound)
        except RuntimeError as e:
            source.require(kind != 'unchanged' and str(e) == marker, 'expected-control-wrong-rejection')
        else:
            source.require(kind == 'unchanged', 'expected-control-accepted-pollution')
        rows.append({'kind': kind, 'outcome': 'ACCEPT' if kind == 'unchanged' else 'EXACT_REJECTION',
                     'binding': bound})
    return rows


def san_env(env, code):
    result = dict(env)
    result['ASAN_OPTIONS'] = f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    result['UBSAN_OPTIONS'] = f'halt_on_error=1:print_stacktrace=1:exitcode={code}'
    return result


def compile_c(cc, flags, text, prefix, env, generated):
    c, binary = prefix.with_suffix('.c'), prefix.with_suffix('.bin')
    c.write_text(text); generated[str(c)] = source.identity(c)
    p = invoke([cc, *flags, str(c), '-o', str(binary)], prefix.with_name(prefix.name + '-compile'), env)
    source.require(p.returncode == 0 and p.stdout == p.stderr == b'', 'clean-compile:' + str(prefix))
    generated[str(binary)] = source.identity(binary)
    return binary


def canaries(cc, flags, output, env, generated):
    rows = [('asan', 97, '#include <stdlib.h>\nint main(int n,char **v){(void)v;volatile int i=n;char*p=malloc(1);p[i]=1;volatile char x=p[i];free(p);return x;}\n', b'ERROR: AddressSanitizer: heap-buffer-overflow'),
            ('ubsan', 98, '#include <limits.h>\nint main(int n,char **v){(void)v;volatile int x=INT_MAX;return x+n;}\n', b'runtime error: signed integer overflow')]
    result = []
    for name, code, text, diagnostic in rows:
        binary = compile_c(cc, flags, text, output / ('canary-' + name), env, generated)
        used = san_env(env, code)
        p = invoke([str(binary)], output / ('canary-' + name + '-run'), used)
        source.require(p.returncode == code and p.stdout == b'' and diagnostic in p.stderr,
                       'sanitizer-activation:' + name)
        result.append({'name': name, 'exit': code, 'environment': {k: used[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=OLD_ROOT / 'ROOT-COUNT-CANDIDATE-20261030-r1')
    parser.add_argument('--candidate', type=Path, default=OLD_ROOT / 'PHY-PREALLOC-CANDIDATE-20261030-r2')
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    source.require(out.parent == AUDIT and out.name.startswith('PHY-TEST-') and not out.exists(), 'fresh-output')
    out.mkdir(parents=True)
    result = {'status': 'INCOMPLETE', 'qualification': 'HOST_MODEL_ONLY_PRE_DT_PHY_ALLOCATION',
              'positives': [], 'negatives': [], 'owner_guard_controls': [], 'open': ['target ABI/runtime/RCU/work/IRQ',
              'topology is explicit leaf not actual OF', 'post-DT and normal driver cleanup',
              'live re-entry/concurrent writers/module admission', 'LSan not verified']}
    inputs, generated = None, {}
    try:
        tree, inputs = source.prepare(args.base.resolve(), args.candidate.resolve(), out)
        save(out / 'INPUTS.json', inputs)
        result['gates'] = gates()
        cc = shutil.which(args.cc); source.require(cc is not None, 'compiler-path')
        cc = str(Path(cc).resolve()); result['compiler'] = {'path': cc, 'sha256': source.identity(cc)}
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wformat=2', '-Wno-unused-function']
        env = dict(os.environ); env.pop('ASAN_OPTIONS', None); env.pop('UBSAN_OPTIONS', None)
        result['python'] = {'executable': sys.executable, 'optimization': sys.flags.optimize}
        result['python_optimization_controls'] = optimization_controls(out, env)
        result['expected_integrity_controls'] = expected_controls(out)
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
            env = san_env(env, 97)
        result['flags'] = flags
        result['environment'] = {k: env.get(k) for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
        version = invoke([cc, '--version'], out / 'compiler-version', env)
        source.require(version.returncode == 0 and version.stderr == b'', 'compiler-version')
        if args.sanitize: result['canaries'] = canaries(cc, flags, out, env, generated)
        template = (SUPPORT / 'fixture.c').read_text().replace('@LINUX_ENUM_PATH@', str(SUPPORT / 'linux-phy-interface.h'))
        text, extracted, new, old = source.render(tree, args.base / 'prepared', template)
        save(out / 'EXTRACTED.json', extracted)
        matrix = {c['name']: c for c in cases()}
        save(out / 'MATRIX.json', list(matrix.values()))
        for qca, i2c in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            profile = f'qca{qca}-i2c{i2c}'; folder = out / profile; folder.mkdir()
            pf = flags + (['-DQCA808X_PORTS_INFO'] if qca else []) + (['-DIN_PHY_I2C_MODE'] if i2c else [])
            binary = compile_c(cc, pf, text, folder / 'positive', env, generated)
            for name, c in matrix.items():
                ret, expected = oracle(c)
                write_expected(folder / (name + '.expected'), expected, generated)
                p = invoke([str(binary), c['flow'], str(c['count']), str(c['fault']), str(c['scenario']), str(ret)], folder / name, env)
                positive(p.returncode, p.stdout, p.stderr, expected)
                result['positives'].append({'profile': profile, 'case': name, 'stdout_sha256': source.digest(p.stdout)})
            for v in variants(new, old, qca):
                mutated = once(text, v['before'], v['after'])
                mb = compile_c(cc, pf, mutated, folder / v['name'], env, generated)
                c = matrix[v['case']]; ret, _ = oracle(c)
                p = invoke([str(mb), c['flow'], str(c['count']), str(c['fault']), str(c['scenario']), str(ret)], folder / (v['name'] + '-run'), env)
                negative(p.returncode, p.stdout, p.stderr, v['marker'])
                result['negatives'].append({'profile': profile, **{k: v[k] for k in ('name', 'symbol', 'case', 'marker', 'classification')}, 'mutant_sha256': source.digest(mutated.encode())})
                if v.get('owner_guard_counterexample'):
                    weak = once(mutated, '            root_transfer_owners();', '            (void)0;')
                    wb = compile_c(cc, pf, weak, folder / (v['name'] + '-weak'), env, generated)
                    ret, expected = oracle(c)
                    p = invoke([str(wb), c['flow'], str(c['count']), str(c['fault']), str(c['scenario']), str(ret)],
                               folder / (v['name'] + '-weak-run'), env)
                    positive(p.returncode, p.stdout, p.stderr, expected)
                    result['owner_guard_controls'].append({'profile': profile, 'case': v['case'],
                        'mutation': v['name'], 'outcome': 'WRONG_TRANSFER_ACCEPTED_ONLY_WITH_OWNER_PROOF_REMOVED',
                        'weak_fixture_sha256': source.digest(weak.encode())})
            save(out / 'RESULTS.json', result)
        result['end_input_stability'] = source.stable(inputs)
        verify_generated(generated)
        source.require(source.identity(cc) == result['compiler']['sha256'], 'compiler-drift')
        result['generated'] = generated
        result['positive_count'] = len(result['positives']); result['negative_count'] = len(result['negatives'])
        result['status'] = 'HOST_MODEL_ONLY'
        result['outcome'] = 'PASSED_WITHIN_PRE_DT_ALLOCATION_MODEL'
    except Exception as e:
        result['status'] = 'FAILED'; result['error'] = str(e)
        raise
    finally:
        save(out / 'RESULTS.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'positive_count', 'negative_count')}))


if __name__ == '__main__':
    main()
