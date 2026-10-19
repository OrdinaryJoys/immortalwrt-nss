#!/usr/bin/env python3
"""Compile actual prepared DP C against host API substitutes; no network/kernel actions."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from extract_prepared_c import Prepared

HERE = Path(__file__).resolve().parent
API = 'exports/nss_dp_api_if.h'
PRIVATE = 'include/nss_dp_dev.h'
HAL = 'hal/include/nss_dp_hal_if.h'


def declarations(prepared):
    return ''.join([
        '#define HOST_DP_STATS_CACHE 1\n' if 'nss_dp_collect_stats' in prepared.read('nss_dp_main.c') else '',
        prepared.structure(API, 'nss_dp_data_plane_ctx'),
        prepared.structure(API, 'nss_dp_gmac_stats'),
        prepared.structure(API, 'nss_dp_vlan_append_info'),
        prepared.structure(API, 'nss_dp_data_plane_ops'),
        prepared.structure(HAL, 'nss_gmac_hal_dev'),
        prepared.structure(HAL, 'nss_gmac_hal_ops'),
        prepared.structure(PRIVATE, 'nss_dp_dev'),
        prepared.structure(PRIVATE, 'nss_dp_link_state', 'enum'),
        prepared.structure(PRIVATE, 'nss_dp_state', 'enum'),
        prepared.structure(PRIVATE, 'nss_dp_priv_flags', 'enum'),
        'static inline int test_bit(unsigned n,unsigned long *v) { return !!(__atomic_load_n(v,__ATOMIC_SEQ_CST)&(1UL<<n)); }\n',
        'static inline void set_bit(unsigned n,unsigned long *v) { __atomic_fetch_or(v,1UL<<n,__ATOMIC_SEQ_CST); }\n',
        'static inline void clear_bit(unsigned n,unsigned long *v) { __atomic_fetch_and(v,~(1UL<<n),__ATOMIC_SEQ_CST); }\n',
    ])


def baseline_program(prepared, *, other_soc=False):
    functions = []
    if 'nss_dp_collect_stats' in prepared.read('nss_dp_main.c'):
        functions.append(prepared.function('nss_dp_main.c', 'nss_dp_collect_stats'))
    for name in ('nss_dp_xmit', 'nss_dp_close', 'nss_dp_open', 'nss_dp_adjust_link', 'nss_dp_rx_flow_steer'):
        functions.append(prepared.function('nss_dp_main.c', name))
    functions.append(prepared.function('nss_dp_main.c', 'nss_dp_get_stats64', occurrence=-1))
    for name in ('nss_dp_reset_netdev_features', 'nss_dp_is_in_open_state', 'nss_dp_override_data_plane',
                 'nss_dp_start_data_plane', 'nss_dp_restore_data_plane'):
        functions.append(prepared.function('nss_dp_attach.c', name))
    cases = (HERE / 'host_baseline_cases.c').read_text()
    structs = declarations(prepared)
    if other_soc:
        structs += prepared.structure(PRIVATE, 'nss_dp_plane_ref')
        for name in ('nss_dp_plane_init', 'nss_dp_plane_get', 'nss_dp_plane_put', 'nss_dp_plane_is_quarantined'):
            structs += prepared.function(PRIVATE, name)
    program = (HERE / 'host_kernel_stubs.h').read_text() + structs + cases.replace('HOST_EXTRACTED_FUNCTIONS', '\n'.join(functions))
    notices = [row['text'].split('*/', 1)[0] + '*/\n' for row in prepared.files.values() if row['text'].startswith('/*')]
    return '\n'.join(notices) + program


def candidate_program(prepared):
    functions = [prepared.function('nss_dp_attach.c', 'nss_dp_reset_netdev_features')]
    for name in ('nss_dp_quarantine_init', 'nss_dp_quarantine_open', 'nss_dp_quarantine_noop',
                 'nss_dp_quarantine_value', 'nss_dp_quarantine_mac', 'nss_dp_quarantine_xmit', 'nss_dp_quarantine_features'):
        functions.append(prepared.function('nss_dp_attach.c', name))
    functions.append(prepared.variable('nss_dp_attach.c', 'nss_dp_quarantine_ops'))
    for name in ('nss_dp_plane_init', 'nss_dp_plane_get', 'nss_dp_plane_put', 'nss_dp_plane_is_quarantined',
                 'nss_dp_plane_stop_phy', 'nss_dp_plane_quiesce', 'nss_dp_plane_quarantine', 'nss_dp_plane_resume'):
        functions.append(prepared.function('nss_dp_attach.c', name))
    for name in ('nss_dp_close_data_plane', 'nss_dp_open_data_plane', 'nss_dp_activate_data_plane',
                 'nss_dp_xmit', 'nss_dp_close', 'nss_dp_open', 'nss_dp_adjust_link', 'nss_dp_rx_flow_steer'):
        functions.append(prepared.function('nss_dp_main.c', name))
    functions.append(prepared.function('nss_dp_ethtools.c', 'nss_dp_get_ethtool_stats'))
    for name in ('nss_dp_is_in_open_state', 'nss_dp_override_data_plane', 'nss_dp_start_data_plane', 'nss_dp_restore_data_plane'):
        functions.append(prepared.function('nss_dp_attach.c', name))
    functions.append(prepared.function('nss_dp_attach.c', 'nss_dp_receive'))
    cases = (HERE / 'host_candidate_cases.c').read_text()
    program = ((HERE / 'host_kernel_stubs.h').read_text() + declarations(prepared) +
               prepared.structure(PRIVATE, 'nss_dp_plane_ref') + cases.replace('HOST_EXTRACTED_FUNCTIONS', '\n'.join(functions)))
    notices = [row['text'].split('*/', 1)[0] + '*/\n' for row in prepared.files.values() if row['text'].startswith('/*')]
    return '\n'.join(notices) + program


def run(program, prepared, cc, output, label, *, ipq=False, expected=5):
    source = output / (label + '.c')
    binary = output / (label + '.host')
    source.write_text(program)
    command = [cc, '-std=gnu11', '-O0', '-g', '-pthread', '-Wall', '-Werror=implicit-function-declaration',
               '-Wno-unused-function', '-Wno-unused-variable', str(source), '-o', str(binary)]
    if ipq:
        command.insert(1, '-DNSS_DP_IPQ807X=1')
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
    if compiled.returncode:
        raise RuntimeError('host compilation failed:\n' + compiled.stderr[:16000])
    executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30)
    if executed.returncode:
        raise RuntimeError('host assertions failed:\n' + executed.stdout + executed.stderr)
    cases = [line.removeprefix('PASS ') for line in executed.stdout.splitlines() if line.startswith('PASS ')]
    if len(cases) != expected or len(cases) != len(set(cases)):
        raise ValueError('missing/duplicate host case results')
    role = {'baseline-controls': 'ORIGINAL_PREPARED_BASELINE_CONTROL',
            'candidate-ipq807x': 'ACTUAL_PREPARED_CANDIDATE_IPQ807X',
            'candidate-other-soc-controls': 'ACTUAL_PREPARED_CANDIDATE_OTHER_SOC_CONTROL'}[label]
    return {'status': 'PASS_HOST_SUBSTITUTES_ONLY', 'input_role': role, 'cases': cases, 'count': len(cases),
            'compile_command': command, 'compiler_diagnostics': compiled.stderr,
            'execution_stdout': executed.stdout, 'execution_stderr': executed.stderr,
            'compiled_binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'generated_c_sha256': hashlib.sha256(program.encode()).hexdigest(), **prepared.manifest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='original baseline with package 001–008 already applied (required unless --candidate-only)')
    parser.add_argument('--candidate', type=Path, help='candidate with actual quarantine patch already applied')
    parser.add_argument('--candidate-only', action='store_true', help='run only actual candidate IPQ807X 21 + other-SoC 5; never claim the original baseline 5')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.candidate_only:
        if args.candidate is None:
            parser.error('--candidate-only requires --candidate')
        if args.baseline is not None:
            parser.error('--candidate-only forbids --baseline')
    elif args.baseline is None:
        parser.error('--baseline is required unless explicit --candidate-only is selected')
    cc = shutil.which(args.cc)
    if cc is None:
        raise ValueError('native host compiler is required')
    output = args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nss-dp-host-check-'))
    if args.output:
        output.mkdir(mode=0o700)
    report = {'scope': 'ACTUAL_PREPARED_C_HOST_API_SUBSTITUTES_ONLY', 'kernel_or_ax6_acceptance': False,
              'mode': 'CANDIDATE_ONLY_26' if args.candidate_only else ('BASELINE_AND_CANDIDATE_31' if args.candidate else 'BASELINE_ONLY_5_CANDIDATE_INCOMPLETE'),
              'original_baseline_executed': not args.candidate_only,
              'selected_inputs': {'baseline': str(args.baseline.resolve()) if args.baseline else None,
                                  'candidate': str(args.candidate.resolve()) if args.candidate else None},
              'network_access': False, 'compiler': subprocess.run([cc, '--version'], text=True, capture_output=True, timeout=10).stdout,
              'host_platform': platform.platform(), 'python_version': platform.python_version(),
              'test_assets': [{'path': name, 'sha256': hashlib.sha256((HERE / name).read_bytes()).hexdigest()}
                              for name in (Path(__file__).name, 'extract_prepared_c.py',
                                           'host_kernel_stubs.h', 'host_baseline_cases.c', 'host_candidate_cases.c')],
              'runs': []}
    if args.baseline:
        prepared = Prepared(args.baseline)
        report['runs'].append(run(baseline_program(prepared), prepared, cc, output, 'baseline-controls'))
    if args.candidate:
        prepared = Prepared(args.candidate)
        candidate_run = run(candidate_program(prepared), prepared, cc, output, 'candidate-ipq807x', ipq=True, expected=21)
        report['runs'].append(candidate_run)
        prepared = Prepared(args.candidate)
        other_soc_run = run(baseline_program(prepared, other_soc=True), prepared, cc, output, 'candidate-other-soc-controls')
        report['runs'].append(other_soc_run)
        first = {row['path']: row['sha256'] for row in candidate_run['sources']}
        second = {row['path']: row['sha256'] for row in other_soc_run['sources']}
        if any(first[path] != second[path] for path in first.keys() & second.keys()):
            raise ValueError('candidate changed between IPQ807X and other-SoC runs')
        report['candidate_status'] = 'PASS_EXTRACTED_C_HOST_SUBSTITUTES_ONLY'
    else:
        report['candidate_status'] = 'INCOMPLETE_NO_CANDIDATE_EXECUTED'
    report['total_cases'] = sum(row['count'] for row in report['runs'])
    report['expected_cases'] = 26 if args.candidate_only else (31 if args.candidate else 5)
    if report['total_cases'] != report['expected_cases']:
        raise ValueError('mode case count mismatch')
    (output / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
