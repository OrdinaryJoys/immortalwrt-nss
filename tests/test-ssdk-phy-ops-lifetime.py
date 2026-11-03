#!/usr/bin/env python3
"""Actual 049 C under observable host substitutes, never target or router approval."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-phy-ops-lifetime'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import variants

CASES = ('registration', 'invalid-registration', 'unregister-live', 'prepare-slot', 'getters',
         'old-phy-no-own', 'old-phy-own', 'borrowed-heap', 'empty-device', 'invalid-cleanup',
         'callback-exit', 'aqua-repeated', 'aqua-retry', 'aqua-foreign', 'aqua-hw-error',
         'irq-restore', 'concurrent-writers')
EXPECTED = ''.join('PASS ' + case + '\n' for case in CASES)
PROFILES = {'full': [], 'mini': ['-DIN_PORTCONTROL_MINI'],
            'full-i2c': ['-DIN_PHY_I2C_MODE'],
            'mini-i2c': ['-DIN_PORTCONTROL_MINI', '-DIN_PHY_I2C_MODE']}
MUTANT_NAMES = ('overwrite-foreign', 'same-object-not-idempotent', 'unregister-matching-live',
                'unregister-ignores-identity', 'prepare-clears-borrowed', 'prepare-frees-borrowed',
                'cleanup-clears-global', 'cleanup-frees-global', 'cleanup-clears-peer',
                'cleanup-keeps-local-bitmap', 'cleanup-clears-before-exit', 'register-without-lock',
                'getter-without-lock', 'prepare-without-lock', 'unregister-without-lock',
                'getter-rejects-last-port', 'ignore-registration-error', 'discard-hw-error',
                'failed-once-latch', 'wrong-field-mapping')
BASE_FLAGS = ('-std=gnu11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
              '-Wno-unused-parameter', '-DIN_AQUANTIA_PHY')
CANARY_PROGRAMS = {
    'asan': '#include <stdlib.h>\nint main(void){volatile int i=2;volatile int *p=malloc(sizeof(int));p[i]=1;free((void*)p);return 0;}\n',
    'ubsan': '#include <limits.h>\nint main(void){volatile int n=INT_MAX;volatile int r=n+1;(void)r;return 0;}\n',
}


def host_flags(sanitizers):
    source.require(sanitizers in (None, 'address', 'undefined', 'address,undefined'),
                   'known host instrumentation')
    flags = list(BASE_FLAGS)
    if sanitizers:
        flags += ['-fsanitize=' + sanitizers, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    return flags


def sanitizer_result(record, kind):
    source.require(kind in CANARY_PROGRAMS, 'known sanitizer canary')
    if (type(record['returncode']) is not int or record['returncode'] != {'asan': 97, 'ubsan': 98}[kind]
            or record['stdout'] != '' or not isinstance(record['stderr'], str)):
        return False
    diagnostic = record['stderr']
    if kind == 'asan':
        return ('ERROR: AddressSanitizer: heap-buffer-overflow' in diagnostic and
                'WRITE of size 4' in diagnostic and 'runtime error:' not in diagnostic and
                'DEADLYSIGNAL' not in diagnostic)
    return ('runtime error: signed integer overflow:' in diagnostic and
            '2147483647 + 1' in diagnostic and 'AddressSanitizer' not in diagnostic)


def sanitizer_oracle_controls():
    examples = {
        'asan': dict(returncode=97, stdout='', stderr='ERROR: AddressSanitizer: heap-buffer-overflow\nWRITE of size 4\n'),
        'ubsan': dict(returncode=98, stdout='', stderr='runtime error: signed integer overflow: 2147483647 + 1\n'),
    }
    controls = []
    for kind, good in examples.items():
        source.require(sanitizer_result(good, kind), 'valid sanitizer oracle ' + kind)
        for key, value in [('returncode', 0), ('returncode', 1), ('returncode', -6),
                           ('returncode', 86), ('returncode', True), ('returncode', str(good['returncode'])),
                           ('returncode', 'timeout'), ('stdout', 'noise\n'), ('stderr', ''),
                           ('stderr', 'runtime error: unrelated\n'),
                           ('stderr', 'AddressSanitizer: DEADLYSIGNAL\n'),
                           ('stderr', examples['ubsan' if kind == 'asan' else 'asan']['stderr'])]:
            row = dict(good); row[key] = value
            source.require(not sanitizer_result(row, kind), 'polluted sanitizer oracle ' + kind)
            controls.append(dict(kind=kind, field=key, value=value))
    return dict(valid=2, rejected_pollution=len(controls), controls=controls)


def semantic(record, marker):
    return (type(record['returncode']) is int and record['returncode'] == 86 and
            record['stdout'] == '' and record['stderr'] == 'PHY_OPS ' + marker + '\n')


def positive(record):
    return (type(record['returncode']) is int and record['returncode'] == 0 and
            record['stdout'] == EXPECTED and record['stderr'] == '')


def oracle_controls():
    valid = dict(returncode=86, stdout='', stderr='PHY_OPS guard\n')
    source.require(semantic(valid, 'guard'), 'valid negative gate')
    controls = []
    for key, value in [('returncode', 1), ('returncode', -6), ('returncode', 97),
                       ('returncode', 98), ('returncode', 'timeout'), ('returncode', True),
                       ('stdout', 'PASS fake\n'), ('stderr', 'PHY_OPS wrong\n'),
                       ('stderr', 'PHY_OPS guard\nnoise\n'), ('stderr', 'runtime error:\n')]:
        changed = dict(valid); changed[key] = value
        source.require(not semantic(changed, 'guard'), 'reject polluted negative gate')
        controls.append([key, value])
    good = dict(returncode=0, stdout=EXPECTED, stderr='')
    source.require(positive(good), 'valid positive gate')
    for key, value in [('returncode', False), ('returncode', 86), ('stdout', ''),
                       ('stdout', EXPECTED.replace('registration\n', 'unrelated\n', 1)),
                       ('stdout', EXPECTED + 'noise\n'), ('stderr', 'warning\n')]:
        changed = dict(good); changed[key] = value
        source.require(not positive(changed), 'reject polluted positive gate')
        controls.append([key, value])
    return {'valid': 2, 'rejected_pollution': len(controls), 'controls': controls}


def invoke(command, out, label, env=None):
    try:
        p = subprocess.run([str(s) for s in command], capture_output=True, text=True,
                           timeout=60, env=env)
        row = dict(command=[str(s) for s in command], returncode=p.returncode,
                   stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired as error:
        row = dict(command=[str(s) for s in command], returncode='timeout',
                   stdout=(error.stdout or b'').decode() if isinstance(error.stdout, bytes) else error.stdout or '',
                   stderr=(error.stderr or b'').decode() if isinstance(error.stderr, bytes) else error.stderr or '')
    (out / (label + '.stdout')).write_text(row['stdout'])
    (out / (label + '.stderr')).write_text(row['stderr'])
    (out / (label + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    return row


def compile_program(cc, out, label, c, profile, sanitizers):
    path = out / (label + '.c'); binary = out / (label + '.host'); path.write_text(c)
    record = invoke([cc, *host_flags(sanitizers), *PROFILES[profile], path, '-o', binary],
                    out, label + '.compile')
    source.require(record['returncode'] == 0 and not record['stdout'] and not record['stderr'],
                   'clean compile required: ' + label)
    return binary, {'generated_c_sha256': source.sha(c.encode()),
                    'binary_sha256': source.sha(binary.read_bytes()), 'compile': record}


def verify_sanitizer_canaries(cc, out, env):
    rows = {}
    for kind, sanitizers, code in [('asan', 'address', 97), ('ubsan', 'undefined', 98)]:
        # A combined canary may stop in UBSan before ASan sees the same access.
        binary, record = compile_program(cc, out, 'canary-' + kind,
                                         CANARY_PROGRAMS[kind], 'full', sanitizers)
        canary_env = dict(env, ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}',
                          UBSAN_OPTIONS=f'halt_on_error=1:abort_on_error=0:exitcode={code}')
        run = invoke([binary], out, 'canary-' + kind + '.run', canary_env)
        source.require(sanitizer_result(run, kind), 'precise sanitizer activation ' + kind)
        rows[kind] = dict(instrumentation=sanitizers,
                          environment={k: canary_env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')},
                          run=run, **record)
    return rows


def metadata_controls(out):
    root = out / 'metadata-controls'; root.mkdir()
    rows = []
    specimens = [
        ('version-valid', {'version.date': b'1700000000\n'}, None),
        ('marker-valid', {'.prepared_deadbeef': b''}, None),
        ('both-valid', {'version.date': b'123\n', '.prepared_deadbeef': b''}, None),
        ('version-no-newline', {'version.date': b'123'}, 'dirty version.date'),
        ('version-nondigit', {'version.date': b'12x\n'}, 'dirty version.date'),
        ('version-extra-newline', {'version.date': b'123\n\n'}, 'dirty version.date'),
        ('version-empty', {'version.date': b''}, 'dirty version.date'),
        ('marker-nonempty', {'.prepared_deadbeef': b'x'}, 'dirty .prepared marker'),
        ('other-extra', {'unexpected.txt': b''},
         'actual prepared37 must equal frozen36 plus049, every file'),
        ('nested-version', {'sub/version.date': b'123\n'}, 'unexpected prepared directory'),
    ]
    for name, files, rejection in specimens:
        tree = root / name; tree.mkdir()
        (tree / 'code.c').write_bytes(b'fixed\n')
        expected = {'code.c': source.sha(b'fixed\n')}
        for rel, raw in files.items():
            path = tree / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        try:
            code, metadata = source.check_prepared(tree, expected)
        except RuntimeError as error:
            source.require(rejection is not None and str(error) == rejection,
                           'precise metadata control ' + name)
            rows.append({'name': name, 'status': 'REJECTED_EXPECTED_INPUT', 'marker': rejection})
        else:
            source.require(rejection is None and code == expected and set(metadata) == set(files),
                           'metadata positive control ' + name)
            rows.append({'name': name, 'status': 'ACCEPTED_METADATA_ONLY', 'metadata': metadata})
    return {'scope': 'INPUT_PARSER_CONTROLS_NOT_SDK_NATIVE_CASES', 'positive': 3,
            'negative': 7, 'records': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True,
                        help='actual complete37 source tree; extraction uses this input, not the derived copy')
    parser.add_argument('--cc', required=True)
    parser.add_argument('--patch-tool', default='patch', help='text patch engine; cloud uses PATH GNU patch')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'scope': 'ACTUAL_FUNCTIONS_HOST_SUBSTITUTES_ONLY',
              'target_kernel_runtime_approved': False, 'profiles': PROFILES,
              'expected_case_names': CASES, 'oracle_controls': oracle_controls(),
              'sanitizer_oracle_controls': sanitizer_oracle_controls(),
              'positives': [], 'negatives': [], 'old_counterexamples': [],
              'remaining_open': ['UK shared endpoint cohort', 'metadata concurrent retirement',
                                 'borrowed provider/code lifetime', 'raw getter reader drain',
                                 'module exit and root failure rollback', 'hardware/MDIO/target ABI']}
    source.require({p.name for p in SUPPORT.iterdir()} ==
                   {'source.py', 'mutations.py', 'fixture.c', 'README.md'}, 'complete support inventory')
    assets = [Path(__file__), source.PATCH, source.EXTRACTOR, source.CONTEXT,
              source.REPO / 'tests/test-ssdk-phy-sanitizer-canaries.py',
              source.REPO / 'tests/SSDK_PHY_OPS_LIFETIME_2026-11-03.md', *sorted(SUPPORT.glob('*'))]
    source.require(all(p.is_file() for p in assets), 'complete runner input assets')
    inputs = {str(p): source.sha(p.read_bytes()) for p in assets}
    report['inputs'] = inputs
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
               UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode=97')
    report['runtime_environment'] = {k: env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
    report['leak_sanitizer'] = 'DISABLED_BY_TEST_POLICY; no leak-detector qualification'
    report['python_optimize'] = sys.flags.optimize
    def save():
        (out / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        report['patch_tool'] = invoke([a.patch_tool, '--version'], out, 'patch-tool')
        source.require(report['patch_tool']['returncode'] == 0, 'patch tool version')
        candidate, before, declared = source.prepare(a.baseline.resolve(), out, a.patch_tool)
        report['patch_parser_controls'] = {'complete_declared_context': 'PASS',
                                          'truncated_tail': 'REJECTED_EXACT_truncated hunk'}
        prepared = a.prepared.resolve(strict=True)
        derived = source.inventory(candidate)
        actual, metadata = source.check_prepared(prepared, derived)
        source.require(len(actual) == 692, 'exact code692 after metadata classification')
        report['metadata_controls'] = metadata_controls(out)
        report['prepared_recipe_metadata'] = metadata
        receipt = {'status': 'PASS_TEXT_EQUALITY_ONLY', 'baseline_path': str(a.baseline.resolve()),
                   'baseline_inventory_sha256': source.inventory_hash(before),
                   'patch_sha256': source.PATCH_SHA, 'actual_prepared_path': str(prepared),
                   'derived_path': str(candidate), 'files': actual,
                   'recipe_metadata': metadata,
                   'declared_context': declared,
                   'actual_inventory_sha256': source.inventory_hash(actual),
                   'extraction_source': 'CLI_ACTUAL_PREPARED_NOT_DERIVED_COPY'}
        receipt_file = out / 'PREPARED-COMPARISON.json'
        receipt_file.write_text(json.dumps(receipt, indent=2) + '\n')
        data = source.fragments(a.baseline.resolve(), prepared)
        source.require(tuple(row[0] for row in variants(data)) == MUTANT_NAMES,
                       'complete independent mutant inventory')
        report['baseline_files'] = before
        report['candidate_files'] = actual
        report['prepared_path'] = str(prepared)
        report['derived_candidate_path'] = str(candidate)
        report['comparison_receipt_sha256'] = source.sha(receipt_file.read_bytes())
        report['receipt_mode'] = 'ACTUAL_PREPARED37_EQUALS_FROZEN36_PLUS049_ALL692_TEXT_ONLY'
        report['mapping'] = [{'field': f, 'function': n, 'mini_excluded': m} for f, n, m in data['pairs']]
        report['functions'] = {n: source.sha(c.encode()) for n, c in data['funcs'].items()}
        report['compiler'] = invoke([a.cc, '--version'], out, 'compiler')
        sanitizers = 'address,undefined' if a.sanitize else None
        if a.sanitize:
            report['canaries'] = verify_sanitizer_canaries(a.cc, out, env)
        def build(label, c, profile):
            return compile_program(a.cc, out, label, c, profile, sanitizers)
        for profile in PROFILES:
            label = profile + '-positive'
            binary, record = build(label, source.program(data), profile)
            run = invoke([binary], out, label + '.run', env)
            source.require(positive(run), 'complete independent positive oracle: ' + label)
            report['positives'].append(dict(profile=profile, cases=len(CASES), run=run, **record)); save()
            if profile == 'full':
                blocked = invoke([a.cc, '-std=gnu11', '-DIN_AQUANTIA_PHY', '-DNDEBUG',
                                  '-Wno-unused-parameter', '-fsyntax-only', out / (label + '.c')],
                                 out, 'ndebug-rejection')
                source.require(blocked['returncode'] == 1 and not blocked['stdout'] and
                               blocked['stderr'].count('error:') == 1 and
                               'Fixture checks cannot be disabled' in blocked['stderr'],
                               'precise NDEBUG compile control, not semantic credit')
                report['ndebug_control'] = blocked
            for name, funcs, table, case, marker in variants(data):
                label = profile + '-mutant-' + name
                binary, record = build(label, source.program(data, funcs, table), profile)
                run = invoke([binary, case], out, label + '.run', env)
                source.require(semantic(run, marker), 'precise runtime mutant rejection: ' + label)
                report['negatives'].append(dict(profile=profile, name=name, case=case, marker=marker,
                                               run=run, **record)); save()
            old = dict(data['funcs']); old.update(data['old'])
            binary, record = build(profile + '-old36', source.program(data, old), profile)
            for case in ('old-phy-no-own', 'old-phy-own'):
                run = invoke([binary, case], out, profile + '-old36-' + case + '.run', env)
                source.require(semantic(run, 'ops-not-owned'), 'old whole-function counterexample ' + case)
                report['old_counterexamples'].append(dict(profile=profile, case=case,
                                                         marker='ops-not-owned', run=run, **record))
            save()
        source.require(source.inventory(a.baseline.resolve()) == before, 'baseline end stability')
        source.require(source.inventory(candidate) == report['candidate_files'], 'candidate end stability')
        source.require(source.check_prepared(prepared, actual) == (actual, metadata),
                       'actual prepared code and recipe metadata end stability')
        source.require(source.sha(receipt_file.read_bytes()) == report['comparison_receipt_sha256'],
                       'comparison receipt end stability')
        source.require(all(source.sha(Path(p).read_bytes()) == h for p, h in inputs.items()), 'asset end stability')
        source.require(len(report['positives']) == 4 and len(report['negatives']) == 80 and
                       len(report['old_counterexamples']) == 8, 'complete campaign inventory')
        report['generated_files'] = {k: v for k, v in source.inventory(out).items() if k != 'RESULTS.json'}
        report.update(status='PASS_SCOPED_HOST_ONLY', positive_cases=sum(p['cases'] for p in report['positives']),
                      runtime_mutants=len(report['negatives']), old_counterexample_runs=len(report['old_counterexamples']),
                      UK_witness='KNOWN_OPEN_NOT_REPAIRED_NOT_EXECUTED_OR_RECLASSIFIED')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        save()
    print(json.dumps({k: report[k] for k in ('status', 'positive_cases', 'runtime_mutants', 'old_counterexample_runs', 'prepared_path')}))


if __name__ == '__main__':
    main()
