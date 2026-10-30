#!/usr/bin/env python3
"""A2 native complete cleanup/exit functions: reporting and unchanged action gates only."""
import argparse
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-root-errors'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import once, variants

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-root-rollback')
BASE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/ROOT-A1-CANDIDATE-20261030-r2')
PROFILES = [(False, False), (False, True), (True, False), (True, True)]


def require(ok, marker):
    source.require(ok, marker)


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def case(name, fal=(0,), phy=(0,), emu=0, registered=0, flow='cleanup'):
    require(len(fal) == len(phy), 'case-domain')
    return {'name': name, 'fal': list(fal), 'phy': list(phy),
            'emu': emu, 'registered': registered, 'flow': flow}


def cases(errors):
    rows = [case('clean'), case('emulation-clean', emu=1),
            case('fal-only', fal=(-1,)), case('phy-only', phy=(-23,)),
            case('both-distinct', fal=(-4,), phy=(-23,)),
            case('emulation-error', fal=(-4,), phy=(-23,), emu=1)]
    # Exercise the actual enum's entire value domain in both component positions.
    for code in sorted(set(errors.values())):
        for emu in (0, 1):
            for partner in (0, -23):
                rows.append(case(f'fal-domain-{code}-{emu}-{partner}', fal=(code,), phy=(partner,), emu=emu))
                rows.append(case(f'phy-domain-{code}-{emu}-{partner}', fal=(partner,), phy=(code,), emu=emu))
    rows += [case('zero-device', (), (), flow='exit'),
             case('three-clean', (0, 0, 0), (0, 0, 0), registered=1, flow='exit'),
             case('three-first-error', (-1, 0, 0), (0, 0, 0), registered=5, flow='exit'),
             case('three-middle-error', (0, -4, 0), (0, 0, 0), registered=2, flow='exit'),
             case('three-distinct-errors', (-4, 0, -26), (-23, -1, -8), registered=5, flow='exit')]
    for device in range(3):
        for component in ('fal', 'phy'):
            for code in sorted(set(errors.values()) - {0}):
                fal, phy = [0] * 3, [0] * 3
                (fal if component == 'fal' else phy)[device] = code
                rows.append(case(f'device-{device}-{component}-{code}', fal, phy,
                                 registered=(1 << device), flow='exit'))
    for emu, registered in itertools.product(range(8), repeat=2):
        rows.append(case(f'mixed-gates-{emu}-{registered}', (-4, 0, -26), (-23, -1, -8),
                         emu=emu, registered=registered, flow='exit'))
    return rows


def oracle(c, profile, revised=True):
    switch, sfp = profile
    events = []

    def action(name, device=-1):
        events.append(f'A {name} {device}\n')

    def log(text, level='E'):
        events.append(f'L {level} {text}\n')

    def cleanup(device):
        action('cache-stop')
        action('retire-controls')
        action('fal', device)
        fal, phy = c['fal'][device], c['phy'][device]
        if revised and fal:
            log(f'ssdk FAL cleanup failed for device {device}: {fal}')
        action('emulation', device)
        emulation = c['emu'] & (1 << device)
        if not emulation:
            action('phy', device)
            if revised and phy:
                log(f'ssdk PHY cleanup failed for device {device}: {phy}')
        return fal if emulation else (fal or phy if revised else phy)

    if c['flow'] == 'cleanup':
        result = cleanup(0)
        return f'RESULT {result}\n' + ''.join(events)
    action('notifier-unregister')
    action('retire-controls')
    action('device-count')
    results = []
    for device in range(len(c['fal'])):
        action('driver-unregister', device)
        if switch and c['registered'] & (1 << device):
            action('switch-unregister', device)
        if sfp:
            action('sfp-exit', device)
        code = cleanup(device)
        results.append(code)
        if revised and code:
            log(f'qca-ssdk device {device} cleanup failed! (code: {code})')
    summary = next((code for code in results if code), 0) if revised else (results[-1] if results else 0)
    if summary:
        log(f'qca-ssdk module exit failed! (code: {summary})')
    else:
        log('qca-ssdk module exit  done!', 'I')
    for device in range(len(c['fal'])):
        action('platform-exit', device)
    action('free-priv')
    return 'RESULT void\n' + ''.join(events)


def actions(text):
    return [line for line in text.splitlines() if line.startswith('A ')]


def positive(code, stdout, stderr, expected):
    require(code == 0 and stderr == b'' and stdout == expected, 'positive-exact-events')


def negative(code, stdout, stderr, marker):
    require(code == 86 and stdout == b'' and stderr == ('SSDK_A2 ' + marker + '\n').encode(),
            'negative-exact-diagnostic')


def gate_controls():
    positive(0, b'expected\n', b'', b'expected\n')
    negative(86, b'', b'SSDK_A2 gate\n', 'gate')
    controls = [
        ('positive-code', lambda: positive(86, b'expected\n', b'', b'expected\n')),
        ('positive-extra-output', lambda: positive(0, b'expected\nnoise', b'', b'expected\n')),
        ('positive-stderr', lambda: positive(0, b'expected\n', b'warning', b'expected\n')),
        ('negative-code', lambda: negative(1, b'', b'SSDK_A2 gate\n', 'gate')),
        ('negative-signal', lambda: negative(-6, b'', b'SSDK_A2 gate\n', 'gate')),
        ('negative-timeout', lambda: negative(None, b'', b'SSDK_A2 gate\n', 'gate')),
        ('negative-stdout', lambda: negative(86, b'noise', b'SSDK_A2 gate\n', 'gate')),
        ('negative-extra-diagnostic', lambda: negative(86, b'', b'SSDK_A2 gate\nnoise\n', 'gate')),
        ('negative-duplicate', lambda: negative(86, b'', b'SSDK_A2 gate\nSSDK_A2 gate\n', 'gate')),
        ('negative-sanitizer', lambda: negative(86, b'', b'SSDK_A2 gate\nERROR: AddressSanitizer\n', 'gate')),
        ('negative-wrong-marker', lambda: negative(86, b'', b'SSDK_A2 other\n', 'gate')),
    ]
    for name, call in controls:
        try:
            call()
        except RuntimeError as error:
            require(str(error) in ('positive-exact-events', 'negative-exact-diagnostic'),
                    'unexpected-control-error')
        else:
            raise RuntimeError('pollution-accepted:' + name)
    return {'valid': 2, 'rejected': len(controls), 'names': [name for name, _ in controls]}


def invoke(command, prefix, env, timeout=30):
    save(prefix.with_suffix('.command.json'), {'argv': command,
         'ASAN_OPTIONS': env.get('ASAN_OPTIONS'), 'UBSAN_OPTIONS': env.get('UBSAN_OPTIONS')})
    try:
        run = subprocess.run(command, capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        prefix.with_suffix('.stdout').write_bytes(error.stdout or b'')
        prefix.with_suffix('.stderr').write_bytes(error.stderr or b'')
        save(prefix.with_suffix('.exit.json'), {'returncode': None, 'timeout': True})
        raise RuntimeError('timeout-not-negative-credit:' + str(prefix)) from error
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
    records = []
    inputs = [
        ('asan', 97, '#include <stdlib.h>\nint main(int argc,char **argv) { (void)argv; volatile int i=argc; char *p=malloc(1); p[i]=1; volatile char x=p[i]; free(p); return x; }\n',
         rb'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan', 98, '#include <limits.h>\nint main(int argc,char **argv) { (void)argv; volatile int x=INT_MAX; return x+argc; }\n',
         rb'runtime error: signed integer overflow'),
    ]
    for name, code, text, pattern in inputs:
        path = output / ('canary-' + name + '.c')
        path.write_text(text)
        generated[str(path)] = source.identity(path)
        binary = output / ('canary-' + name)
        build = invoke([cc, *flags, str(path), '-o', str(binary)], output / (name + '-compile'), env)
        require(build.returncode == 0 and build.stdout == build.stderr == b'', 'canary-compile')
        per_case = san_env(env, code)
        run = invoke([str(binary)], output / (name + '-run'), per_case)
        require(run.returncode == code and run.stdout == b'' and re.search(pattern, run.stderr),
                'canary-exact-code-and-diagnostic')
        records.append({'name': name, 'exit': code, 'ASAN_OPTIONS': per_case['ASAN_OPTIONS'],
                        'UBSAN_OPTIONS': per_case['UBSAN_OPTIONS'], 'diagnostic_pattern': pattern.decode()})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='Final20 receipt directory')
    parser.add_argument('--candidate-receipt-sha', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.parent == AUDIT and output.name.startswith('A2-TEST-') and not output.exists(),
            'fresh-authorized-output')
    output.mkdir(parents=True)
    result = {'status': 'INCOMPLETE', 'qualification': 'HOST_MODEL_ONLY_A2_REPORTING',
              'positives': [], 'baseline_compatibility': [], 'baseline_counterexamples': [],
              'runtime_mutants': [], 'failures': 0,
              'open': ['Leaf cleanup safety and FAL/PHY resources', 'partial init/rollback',
                       'all target ABI/build/device/hardware', 'kernel concurrency/RCU/lockdep',
                       'unload prevention: regi_exit remains void', 'LSan']}
    inputs = None
    generated = {}
    try:
        inputs = source.prepare(args.base.resolve(), args.candidate.resolve(),
                                args.candidate_receipt_sha, output)
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
        result['gate_controls'] = gate_controls()
        version = invoke([cc, '--version'], output / 'compiler-version', env)
        require(version.returncode == 0 and version.stderr == b'', 'compiler-version')
        if args.sanitize:
            result['canaries'] = canaries(cc, flags, output, env, generated)
        template = (SUPPORT / 'fixture.c').read_text()
        current, records, errors = source.render(args.candidate / 'prepared', template)
        baseline, old_records, old_errors = source.render(args.base / 'prepared', template)
        require(errors == old_errors, 'error-enum-preserved')
        save(output / 'EXTRACTED.json', {'candidate': records, 'baseline': old_records,
             'sw_error_t': errors, 'native_model': True, 'only_two_actual_functions_compiled': True})
        matrix = cases(errors)
        named = {c['name']: c for c in matrix}
        require(len(matrix) == len(named), 'unique-cases')
        save(output / 'CASES.json', matrix)

        def compile_variant(name, text, profile):
            path = output / (name + '.c')
            path.write_text(text)
            generated[str(path)] = source.identity(path)
            binary = output / name
            defines = (['-DHPPE'] if profile[0] else []) + (['-DIN_SFP_PHY'] if profile[1] else [])
            build = invoke([cc, *flags, *defines, str(path), '-o', str(binary)], output / (name + '-compile'), env)
            require(build.returncode == 0 and build.stdout == build.stderr == b'',
                    'compile-not-runtime-credit:' + name)
            return binary

        def execute(binary, c, profile, label, revised=True, marker=None, expected_override=None):
            text = oracle(c, profile, revised) if expected_override is None else expected_override
            oracle_path = output / (label + '.oracle')
            oracle_path.write_text(text)
            generated[str(oracle_path)] = source.identity(oracle_path)
            csv = lambda values: ','.join(str(v) for v in values) if values else '-'
            command = [str(binary), c['flow'], str(len(c['fal'])), str(c['registered']),
                       str(c['emu']), csv(c['fal']), csv(c['phy']), str(oracle_path)]
            run = invoke(command, output / label, env)
            if marker:
                negative(run.returncode, run.stdout, run.stderr, marker)
                return {'name': label, 'case': c['name'], 'marker': marker, 'exit': 86,
                        'compile_clean': True, 'empty_stdout': True, 'unique_exact_stderr': True}
            positive(run.returncode, run.stdout, run.stderr, text.encode())
            return {'name': label, 'case': c['name'], 'profile': list(profile), 'exact_events': True}

        binaries = {}
        for profile in PROFILES:
            tag = f'switch{int(profile[0])}-sfp{int(profile[1])}'
            new_bin = compile_variant('candidate-' + tag, current, profile)
            old_bin = compile_variant('baseline-' + tag, baseline, profile)
            binaries[profile] = (new_bin, old_bin)
            for c in matrix:
                # Direct cleanup has no compile-time branch; execute once, not inflate4x.
                if c['flow'] == 'cleanup' and profile != (True, True):
                    continue
                new_oracle, old_oracle = oracle(c, profile), oracle(c, profile, revised=False)
                require(actions(new_oracle) == actions(old_oracle), 'independent-action-projection')
                result['positives'].append(execute(new_bin, c, profile, 'positive-' + tag + '-' + c['name']))
                result['baseline_compatibility'].append(execute(old_bin, c, profile,
                    'baseline-' + tag + '-' + c['name'], revised=False))
                # Both actual emitted action streams already matched their independent
                # full oracles; equality is not inferred from source/log silence.
        profile = (True, True)
        new_bin, old_bin = binaries[profile]
        for name in ('fal-only', 'both-distinct'):
            result['baseline_counterexamples'].append(execute(old_bin, named[name], profile,
                'old-reject-' + name, marker='cleanup-first-error'))
        result['baseline_counterexamples'].append(execute(old_bin, named['phy-only'], profile,
            'old-reject-phy-log', marker='phy-error-log'))
        # Isolate the baseline module accumulator using unchanged full regi_exit
        # with candidate cleanup; accept old absence of per-device log ONLY here.
        old_bodies = source.extract(args.base / 'prepared')[0]
        new_bodies = source.extract(args.candidate / 'prepared')[0]
        isolated = compile_variant('baseline-module-accumulator',
            once(current, new_bodies['regi_exit'], old_bodies['regi_exit']), profile)
        witness = named['three-distinct-errors']
        isolated_expected = ''.join(line for line in oracle(witness, profile).splitlines(True)
                                    if not line.startswith('L E qca-ssdk device '))
        result['baseline_counterexamples'].append(execute(isolated, witness, profile,
            'old-reject-module-first', marker='module-first-error-log', expected_override=isolated_expected))
        for name, function, old, new, witness, marker in variants():
            altered = once(new_bodies[function], old, new)
            binary = compile_variant('mutant-' + name, once(current, new_bodies[function], altered), profile)
            result['runtime_mutants'].append(execute(binary, named[witness], profile,
                'negative-' + name, marker=marker))
        require(source.identity(cc) == result['compiler']['sha256'], 'end-compiler-drift')
        for path, expected_sha in generated.items():
            require(source.identity(path) == expected_sha, 'end-generated-or-oracle-drift')
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
    for key in ('positives', 'baseline_compatibility', 'baseline_counterexamples', 'runtime_mutants'):
        result[key + '_count'] = len(result[key])
    save(output / 'RESULTS.json', result)
    print(json.dumps({name: result[name] for name in ('status', 'qualification', 'positives_count',
                     'baseline_compatibility_count', 'baseline_counterexamples_count', 'runtime_mutants_count')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
