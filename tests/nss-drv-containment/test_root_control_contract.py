#!/usr/bin/env python3
"""Actual HAL source mutations must compile, then fail a specific host assertion.

No prepared input is changed. These are API-boundary ordering/retirement tests,
not execution of the complete real root, coredump or frequency implementation.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import resource
import shutil
import signal
import sys
import traceback

from extract_prepared_c import Prepared, function

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('drv_runner', HERE / 'test-nss-drv-containment.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('negative-control replacement is not exact: ' + old)
    return text.replace(old, new, 1)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def mutations(program, actual_definition):
    name = '__nss_hal_quiesce_control_group'
    original = function(program, name)
    if original != actual_definition:
        raise ValueError('generated HAL definition differs from actual prepared source')
    for label, old, new, assertion, where in (
        ('omit-root-join', '\tnss_root_controls_stop();', '',
         '!host_controls[kind-1].accepting && !host_controls[kind-1].active', 'host_control_stop'),
        ('omit-frequency-join', '\tnss_freq_work_quiesce();', '',
         '!host_controls[kind-1].accepting && !host_controls[kind-1].active', 'host_control_stop'),
        ('omit-coredump-join', '\tnss_coredump_quiesce();', '',
         '!host_controls[kind].accepting && !host_controls[kind].active && host_controls[kind].stops==1',
         'host_controls_assert_drained'),
        ('frequency-before-root', '\tnss_root_controls_stop();\n\tnss_freq_work_quiesce();',
         '\tnss_freq_work_quiesce();\n\tnss_root_controls_stop();',
         '!host_controls[kind-1].accepting && !host_controls[kind-1].active', 'host_control_stop'),
        ('repeat-control-retirement', '\tif (nss_hal_control_group_stopped)', '\tif (false)',
         'host_controls[kind].stops++==0', 'host_control_stop'),
        ('join-under-rtnl', '\tnss_root_controls_stop();',
         '\trtnl_lock();\n\tnss_root_controls_stop();\n\trtnl_unlock();',
         '!host_holds_rtnl', 'host_control_stop'),
    ):
        changed = replace_once(original, old, new)
        yield {'mutation': label, 'program': replace_once(program, original, changed),
               'expected_assertion': assertion, 'expected_assertion_function': where,
               'unmutated_generated_c_sha256': digest(program),
               'source_mutation': {'source': RUNNER.HAL, 'function': name,
                                   'original_definition_sha256': digest(original),
                                   'mutated_definition_sha256': digest(changed),
                                   'old': old, 'new': new, 'replacement_count': 1}}


def exact_assertion(stderr, expression, where):
    # Darwin/glibc diagnostics differ. Match the whole expression and function.
    darwin = 'Assertion failed: (' + expression + '), function ' + where + ','
    linux = ': ' + where + ": Assertion `" + expression + "' failed."
    return any(line.startswith(darwin) or line.endswith(linux) for line in stderr.splitlines())


def verdict(row, *, expected_cases=None, assertion=None, where=None):
    if row['compile']['status'] != 'COMPLETED' or row['compile']['returncode'] != 0 or row['compile']['stderr']:
        return 'FAIL_CLEAN_COMPILE'
    if not row['artifact_integrity'] or row['compiled_binary'] is None:
        return 'FAIL_ARTIFACT_INTEGRITY'
    if row['execute']['status'] != 'COMPLETED':
        return 'FAIL_EXECUTION'
    if assertion is not None:
        if row['execute']['returncode'] != -signal.SIGABRT or not exact_assertion(row['execute']['stderr'], assertion, where):
            return 'FAIL_EXACT_RUNTIME_ASSERTION'
        return 'PASS_EXACT_RUNTIME_ASSERTION'
    if row['execute']['returncode'] != 0 or row['execute']['stderr']:
        return 'FAIL_POSITIVE_EXECUTION'
    if row['count'] != expected_cases or len(set(row['cases'])) != expected_cases:
        return 'FAIL_POSITIVE_CASES'
    return 'PASS_HOST_SUBSTITUTES_ONLY'


def persist(output, report, *, final=False):
    encoded = json.dumps(report, indent=2) + '\n'
    (output / 'RESULT.partial.json').write_text(encoded)
    if final:
        (output / 'RESULT.json').write_text(encoded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args(argv)
    output = args.output.absolute()
    output.mkdir(mode=0o700)
    report = {'scope': 'ACTUAL_HAL_SOURCE_MUTATIONS_HOST_BOUNDARIES_ONLY',
              'status': 'RUNNING', 'kernel_or_firmware_retirement_proof': False,
              'network_access': False, 'host': platform.platform(),
              'limitations': ['Only selected actual HAL orchestration is executed.',
                              'Root, frequency and coredump are blocking host API substitutes, not their real implementations.',
                              'No Linux ordering/RCU/lockdep, firmware retirement, target build or AX6 runtime acceptance.'],
              'candidate': str(args.candidate.absolute()), 'requested_compiler': args.cc,
              'runner': RUNNER.file_binding(Path(__file__)),
              'test_assets': RUNNER.asset_manifest(), 'compiler': None,
              'positive_runs': [], 'negative_runs': [], 'errors': [],
              'expected_positive_cases': 23, 'expected_exact_runtime_negatives': 12}
    snapshots = []
    persist(output, report)
    try:
        # Expected aborts must not produce core files outside the result tree.
        resource.setrlimit(resource.RLIMIT_CORE, (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))
        cc = shutil.which(args.cc)
        if cc is None:
            raise ValueError('native C compiler is required')
        report['compiler'] = RUNNER.compiler_binding(cc)
        compiler_hash = digest(json.dumps(report['compiler'], sort_keys=True))
        if report['compiler']['version']['returncode'] != 0:
            report['errors'].append({'stage': 'compiler-version', 'message': 'compiler --version failed'})
        persist(output, report)
        for generic, case_file, expected in (
            (True, 'driver_candidate_cases.c', 20),
            (False, 'driver_nongeneric_cases.c', 3),
        ):
            label = 'generic' if generic else 'nongeneric'
            prepared = Prepared(args.candidate)
            snapshots.append(prepared)
            actual = RUNNER.program(prepared, candidate=True, cases=case_file)
            source_manifest = prepared.manifest()
            actual_definition = function(prepared.read(RUNNER.HAL), '__nss_hal_quiesce_control_group')
            row = {**source_manifest, 'compiler_binding_sha256': compiler_hash,
                   'expected_cases': expected, 'input_role': 'ACTUAL_029_CONTROL_GROUP_HOST_BOUNDARY'}
            report['positive_runs'].append(row)
            persist(output, report)
            row.update(RUNNER.compile_and_execute(actual, cc, output, label + '-positive',
                       soc='NSS_HAL_IPQ807x_SUPPORT', generic=generic))
            row['status'] = verdict(row, expected_cases=expected)
            persist(output, report)
            for mutation in mutations(actual, actual_definition):
                changed = mutation.pop('program')
                row = {**source_manifest, **mutation, 'compiler_binding_sha256': compiler_hash,
                       'generic_support': generic}
                report['negative_runs'].append(row)
                persist(output, report)
                row.update(RUNNER.compile_and_execute(changed, cc, output, label + '-' + row['mutation'],
                           soc='NSS_HAL_IPQ807x_SUPPORT', generic=generic))
                row['status'] = verdict(row, assertion=row['expected_assertion'], where=row['expected_assertion_function'])
                persist(output, report)
        for prepared in snapshots:
            prepared.manifest()
        report['compiler_after'] = RUNNER.compiler_binding(cc)
        if report['compiler_after'] != report['compiler']:
            raise ValueError('compiler changed during controls')
        if RUNNER.asset_manifest() != report['test_assets'] or RUNNER.file_binding(Path(__file__)) != report['runner']:
            raise ValueError('test assets changed during controls')
        by_root = {}
        for row in report['positive_runs'] + report['negative_runs']:
            sources = {entry['path']: entry['sha256'] for entry in row['sources']}
            root = row['prepared_root']
            if root in by_root and by_root[root] != sources:
                raise ValueError('prepared input differs between control variants')
            by_root[root] = sources
            if RUNNER.file_binding(Path(row['generated_source']['path'])) != row['generated_source']:
                raise ValueError('generated source changed during controls')
            if row['compiled_binary'] and RUNNER.file_binding(Path(row['compiled_binary']['path'])) != row['compiled_binary']:
                raise ValueError('binary changed during controls')
    except Exception as error:
        report['errors'].append({'type': type(error).__name__, 'message': str(error),
                                 'traceback': traceback.format_exc()})
    finally:
        report['positive_cases'] = sum(row.get('count', 0) for row in report['positive_runs']
                                       if row.get('status') == 'PASS_HOST_SUBSTITUTES_ONLY')
        report['exact_runtime_negatives'] = sum(row.get('status') == 'PASS_EXACT_RUNTIME_ASSERTION'
                                                for row in report['negative_runs'])
        passed = (not report['errors'] and len(report['positive_runs']) == 2 and
                  report['positive_cases'] == 23 and len(report['negative_runs']) == 12 and
                  report['exact_runtime_negatives'] == 12)
        report['status'] = 'PASS_HOST_SUBSTITUTES_ONLY' if passed else 'FAIL'
        persist(output, report, final=True)
    print(json.dumps({'status': report['status'], 'positive_cases': report['positive_cases'],
                      'exact_runtime_negatives': report['exact_runtime_negatives'],
                      'result': str(output / 'RESULT.json')}))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
