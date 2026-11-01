#!/usr/bin/env python3
"""Compile actual prepared DP C against host API substitutes; no network/kernel actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

from extract_prepared_c import Prepared, code_mask

HERE = Path(__file__).resolve().parent
API = 'exports/nss_dp_api_if.h'
PRIVATE = 'include/nss_dp_dev.h'
HAL = 'hal/include/nss_dp_hal_if.h'
EDMA = 'hal/dp_ops/edma_dp/edma_v1/edma_data_plane.c'
EDMA_HEADER = 'hal/dp_ops/edma_dp/edma_v1/edma_data_plane.h'
EDMA_REGS = 'hal/dp_ops/edma_dp/edma_v1/edma_regs.h'
ARCH = 'hal/soc_ops/ipq807x/nss_ipq807x.h'
EDMA_FUNCTIONS = ('edma_disable_interrupts', 'edma_stop_napi', 'edma_close_member', 'edma_retire_port')
BASELINE_CASES = (
    'baseline_down_restore_preserves_stale_four_masks_control',
    'baseline_up_restore_resets_four_masks_control',
    'baseline_ignored_close_failure_retains_up_control',
    'baseline_failed_init_leaves_partial_override_control',
    'baseline_initial_override_control',
)
IPQ_CASES = (
    'candidate_down_detach_clears_four_masks_without_hardware_callback',
    'candidate_up_detach_clears_four_masks_without_nss_close_or_link',
    'permanent_latch_refuses_reopen_restart_reoverride_resume',
    'repeated_detach_idempotent_no_hardware_callback',
    'two_ordered_teardown_callers_same_port_no_reactivation',
    'normal_close_failure_quarantines_after_reader_release',
    'normal_close_link_failure_quarantines',
    'initial_takeover_init_failure_quarantines_and_uses_old_deinit_context',
    'initial_takeover_close_failure_never_initializes_new_plane',
    'ndo_open_init_failure_quarantines_without_up_publication',
    'normal_initial_up_takeover_reopens_only_after_readiness',
    'normal_initial_down_takeover_preserves_admin_down_then_opens',
    'readiness_open_failure_quarantines',
    'readiness_wrong_context_quarantines',
    'externally_woken_queue_still_drops_xmit_exactly_once',
    'quarantined_actual_receive_refused_counted_and_freed_once',
    'inflight_xmit_drains_and_new_xmit_is_refused',
    'inflight_rfs_pair_drains_and_new_rfs_is_refused',
    'inflight_phy_link_drains_and_carrier_is_reasserted_off',
    'inflight_actual_ethtool_dp_stats_drains_and_new_reader_is_refused',
    'inflight_actual_receive_delivery_drains_and_new_receive_is_refused',
)
RETIREMENT_CASES = (
    'actual_edma_rejects_invalid_and_foreign_owner_without_effects',
    'actual_edma_retirement_preserves_peer_and_repeated_retirement_is_inert',
    'actual_edma_closed_member_unpublishes_without_active_underflow',
    'quarantine_does_not_retire_foreign_edma_instance',
    'actual_edma_last_valid_macid_retires_only_its_slot',
) + IPQ_CASES + (
    'host_edma_xmit_reader_drains_before_retirement',
    'host_edma_rfs_reader_drains_before_retirement',
    'host_edma_phy_reader_drains_before_retirement',
    'host_edma_stats_reader_drains_before_retirement',
    'host_edma_receive_reader_drains_before_retirement',
)
RETIREMENT_MUTATIONS = {
    'quarantine-omits-retirement': 'quarantine-must-retire',
    'retire-before-plane-drain': 'retire-after-plane-drain',
    'skip-admitted-reader-drain': 'retire-after-plane-drain',
    'retire-wrong-netdev': 'retire-identity',
    'retire-wrong-macid': 'retire-identity',
    'retire-foreign-owner': 'reject-invalid-or-foreign',
    'retire-wrong-slot': 'retire-result',
    'retire-without-close': 'retire-active',
    'retire-without-unpublish': 'retire-unpublish',
    'retire-without-grace': 'retire-grace',
    'closed-member-decrements-again': 'retire-active',
    'last-member-without-napi-stop': 'retire-grace',
    'stop-peer-napi': 'retire-grace',
    'skip-napi-disable': 'last-member-stops-napi',
    'omit-final-interrupt-mask': 'last-member-masks-twice',
    'grace-before-unpublish': 'retirement-event-order',
    'retire-changes-override-accounting': 'only-owned-membership-state-changed',
    'retire-clears-mmio': 'only-owned-membership-state-changed',
    'retire-clears-static-context': 'only-owned-membership-state-changed',
    'invalid-return-writes-accounting': 'rejected-retirement-keeps-complete-state',
    'foreign-return-clears-mmio': 'rejected-retirement-keeps-complete-state',
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('mutation anchor changed; review required: ' + old)
    return text.replace(old, new, 1)


def positive_result(code, stdout, stderr, expected, expected_names=None):
    cases = [line[5:] for line in stdout.splitlines() if line.startswith('PASS ')]
    return (type(code) is int and code == 0 and not stderr and len(cases) == expected and
            len(cases) == len(set(cases)) and
            (expected_names is None or tuple(cases) == tuple(expected_names)) and
            stdout == ''.join('PASS ' + name + '\n' for name in cases))


def semantic_rejection(code, stdout, stderr, marker, positive_stdout):
    return (type(code) is int and code == 86 and stderr == 'DP_RETIRE ' + marker + '\n' and
            positive_stdout is not None and positive_stdout.startswith(stdout) and
            (not stdout or stdout.endswith('\n')) and
            all(line.startswith('PASS ') for line in stdout.splitlines()))


def check_result_oracles():
    reference = 'PASS one\nPASS two\n'
    if not positive_result(0, reference, '', 2) or not semantic_rejection(86, '', 'DP_RETIRE check\n', 'check', reference):
        raise ValueError('valid result oracle controls failed')
    negatives = [(1, '', 'DP_RETIRE check\n'), (-6, '', 'DP_RETIRE check\n'),
                 (97, '', 'DP_RETIRE check\n'), (98, '', 'DP_RETIRE check\n'),
                 ('timeout', '', 'DP_RETIRE check\n'), (True, '', 'DP_RETIRE check\n'),
                 (86, '', 'DP_RETIRE unrelated\n'), (86, '', 'DP_RETIRE check\nnoise\n'),
                 (86, 'PASS not-the-reference\n', 'DP_RETIRE check\n'),
                 (86, 'PASS o', 'DP_RETIRE check\n')]
    if any(semantic_rejection(*row, 'check', reference) for row in negatives):
        raise ValueError('polluted mutation result accepted')
    positives = [(0, '', ''), (0, reference, 'warning\n'), (1, reference, ''),
                 (False, reference, ''), (0, reference + 'noise\n', ''),
                 (0, 'PASS one\nPASS one\n', '')]
    if any(positive_result(*row, 2) for row in positives):
        raise ValueError('polluted positive result accepted')
    return {'valid': 2, 'rejected_pollution': len(negatives) + len(positives)}


def sanitizer_environment(code=97):
    # compiler-rt shares common flags: use the same exit policy in both options.
    return dict(os.environ,
                ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}',
                UBSAN_OPTIONS=f'halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode={code}')


def sanitizer_checks(cc, output):
    probes = {
        'asan': ('#include <stdlib.h>\nint main(void) { volatile int i=2; '
                 'volatile int *p=malloc(sizeof(int)); p[i]=1; free((void *)p); return 0; }\n',
                 97, 'AddressSanitizer'),
        'ubsan': ('int main(void) { volatile unsigned i=32; return 1U << i; }\n',
                  98, 'runtime error:'),
    }
    rows = {}
    for name, (text, code, marker) in probes.items():
        source, binary = output / ('canary-' + name + '.c'), output / ('canary-' + name + '.host')
        source.write_text(text)
        command = [cc, '-std=gnu11', '-O0', '-g', '-fsanitize=address,undefined',
                   '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(source), '-o', str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (output / ('canary-' + name + '.compile.stdout')).write_text(compiled.stdout)
        (output / ('canary-' + name + '.compile.stderr')).write_text(compiled.stderr)
        if compiled.returncode or compiled.stdout or compiled.stderr:
            raise RuntimeError('sanitizer canary compilation failed: ' + name + '\n' + compiled.stderr)
        executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30,
                                  env=sanitizer_environment(code))
        (output / ('canary-' + name + '.run.stdout')).write_text(executed.stdout)
        (output / ('canary-' + name + '.run.stderr')).write_text(executed.stderr)
        rows[name] = {'command': command, 'returncode': executed.returncode,
                      'stderr_sha256': hashlib.sha256(executed.stderr.encode()).hexdigest()}
        (output / ('canary-' + name + '.json')).write_text(json.dumps(rows[name], indent=2) + '\n')
        if executed.returncode != code or executed.stdout or marker not in executed.stderr:
            raise RuntimeError('sanitizer canary did not reject injected fault: ' + name)
    return rows


def mutate_retirement(functions, edma, name):
    changes = {
        'quarantine-omits-retirement': ('nss_dp_plane_quarantine',
            'edma_retire_port(dp->netdev, dp->macid);', '(void)0;'),
        'skip-admitted-reader-drain': ('nss_dp_plane_quiesce',
            'wait_event(dp->plane_wait, !READ_ONCE(dp->plane_readers));', '(void)0;'),
        'retire-wrong-netdev': ('nss_dp_plane_quarantine',
            'edma_retire_port(dp->netdev, dp->macid);', 'edma_retire_port(NULL, dp->macid);'),
        'retire-wrong-macid': ('nss_dp_plane_quarantine',
            'edma_retire_port(dp->netdev, dp->macid);', 'edma_retire_port(dp->netdev, dp->macid + 1);'),
        'retire-foreign-owner': ('edma_retire_port',
            'if (rcu_access_pointer(edma_hw.netdev_arr[index]) != netdev)', 'if (false)'),
        'retire-wrong-slot': ('edma_retire_port', 'index = macid - 1;', 'index = macid;'),
        'retire-without-close': ('edma_retire_port', 'edma_close_member(index);', '(void)0;'),
        'retire-without-unpublish': ('edma_retire_port',
            'rcu_assign_pointer(edma_hw.netdev_arr[index], NULL);', '(void)0;'),
        'retire-without-grace': ('edma_retire_port', 'synchronize_net();', '(void)0;'),
        'closed-member-decrements-again': ('edma_close_member',
            'if (!edma_hw.host_open[index])\n\t\treturn;', '(void)0;'),
        'last-member-without-napi-stop': ('edma_close_member', 'edma_stop_napi();', '(void)0;'),
        'stop-peer-napi': ('edma_close_member', 'if (--edma_hw.active == 0)', 'if (--edma_hw.active >= 0)'),
        'skip-napi-disable': ('edma_stop_napi', 'napi_disable(&edma_hw.napi);', '(void)0;'),
        'omit-final-interrupt-mask': ('edma_stop_napi',
            'synchronize_net();\n\tedma_disable_interrupts();', 'synchronize_net();'),
        'grace-before-unpublish': ('edma_retire_port',
            'rcu_assign_pointer(edma_hw.netdev_arr[index], NULL);\n\tsynchronize_net();',
            'synchronize_net();\n\trcu_assign_pointer(edma_hw.netdev_arr[index], NULL);'),
        'retire-changes-override-accounting': ('edma_retire_port',
            'edma_close_member(index);', 'edma_hw.dp_override_cnt++;\n\tedma_close_member(index);'),
        'retire-clears-mmio': ('edma_retire_port',
            'edma_close_member(index);', 'edma_hw.reg_base = NULL;\n\tedma_close_member(index);'),
        'retire-clears-static-context': ('edma_retire_port',
            'edma_close_member(index);', 'dp_global_data_plane_ctx[index].dev = NULL;\n\tedma_close_member(index);'),
        'invalid-return-writes-accounting': ('edma_retire_port',
            'if (!netdev || macid < EDMA_START_GMACS || macid > EDMA_MAX_GMACS)\n\t\treturn false;',
            'if (!netdev || macid < EDMA_START_GMACS || macid > EDMA_MAX_GMACS) {\n'
            '\t\tedma_hw.dp_override_cnt++;\n\t\treturn false;\n\t}'),
        'foreign-return-clears-mmio': ('edma_retire_port',
            'if (rcu_access_pointer(edma_hw.netdev_arr[index]) != netdev)\n\t\treturn false;',
            'if (rcu_access_pointer(edma_hw.netdev_arr[index]) != netdev) {\n'
            '\t\tedma_hw.reg_base = NULL;\n\t\treturn false;\n\t}'),
    }
    if name == 'retire-before-plane-drain':
        changes[name] = ('nss_dp_plane_quarantine', 'nss_dp_plane_quiesce(dp);',
            'edma_retire_port(dp->netdev, dp->macid);\n\tnss_dp_plane_quiesce(dp);')
    target, old, new = changes[name]
    groups = [list(functions), list(edma)]
    matches = 0
    for group in groups:
        for i, text in enumerate(group):
            if re.match(r'^[^{]*\b' + re.escape(target) + r'\s*\(', code_mask(text)):
                if name == 'retire-before-plane-drain':
                    text = replace_once(text, 'edma_retire_port(dp->netdev, dp->macid);', '(void)0;')
                group[i] = replace_once(text, old, new)
                matches += 1
    if matches != 1:
        raise ValueError('one extracted function must receive mutation ' + name)
    return groups


def has_retirement(prepared):
    # Detect the provider/header too: deleting the caller must not disable tests.
    return any(re.search(r'\bedma_retire_port\b', code_mask(prepared.read(path)))
               for path in (ARCH, EDMA, 'nss_dp_attach.c'))


def retirement_header(prepared):
    arch = prepared.read(ARCH)
    matches = list(re.finditer(r'^bool\s+edma_retire_port\([^;{}]*\);', code_mask(arch), re.M))
    if len(matches) != 1:
        raise ValueError('one actual bool retirement ABI declaration is required')
    prototype = arch[matches[0].start():matches[0].end()]
    expected = 'bool edma_retire_port(struct net_device *netdev, uint32_t macid);'
    if re.sub(r'\s+', '', prototype) != re.sub(r'\s+', '', expected):
        raise ValueError('retirement ABI changed; fixture review required')
    start = list(re.finditer(r'^#define\s+NSS_DP_HAL_START_IFNUM\s+1\s*$', arch, re.M))
    if len(start) != 1:
        raise ValueError('IPQ807X start-ifnum contract changed')
    headers = [prepared.read(path) for path in (EDMA_HEADER, EDMA_REGS)]
    return ('#define HOST_EDMA_RETIREMENT 1\n' + arch[start[0].start():start[0].end()] +
            '\n' + prototype + '\n' + '\n'.join(
                re.sub(r'^#include[^\n]*\n', '', text, flags=re.M) for text in headers))


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


def candidate_program(prepared, mutation=None):
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
    headers, support = '', ''
    if has_retirement(prepared):
        headers = retirement_header(prepared)
        edma = [prepared.function(EDMA, name) for name in EDMA_FUNCTIONS]
        if mutation is not None:
            functions, edma = mutate_retirement(functions, edma, mutation)
        support = (HERE / 'host_edma_retirement.h').read_text().replace('HOST_EDMA_FUNCTIONS', '\n'.join(edma))
    elif mutation is not None:
        raise ValueError('retirement mutation requires the actual provider')
    cases = cases.replace('HOST_EDMA_SUPPORT', support).replace('HOST_EXTRACTED_FUNCTIONS', '\n'.join(functions))
    program = ((HERE / 'host_kernel_stubs.h').read_text() + declarations(prepared) +
               prepared.structure(PRIVATE, 'nss_dp_plane_ref') + headers + cases)
    notices = [row['text'].split('*/', 1)[0] + '*/\n' for row in prepared.files.values() if row['text'].startswith('/*')]
    return '\n'.join(notices) + program


def run(program, prepared, cc, output, label, *, ipq=False, expected=5, sanitize=False,
        negative=None, positive_stdout=None, expected_names=BASELINE_CASES):
    source = output / (label + '.c')
    binary = output / (label + '.host')
    source.write_text(program)
    command = [cc, '-std=gnu11', '-O0', '-g', '-pthread', '-Wall', '-Werror=implicit-function-declaration',
               '-Wno-unused-function', '-Wno-unused-variable', str(source), '-o', str(binary)]
    if ipq:
        command.insert(1, '-DNSS_DP_IPQ807X=1')
    if sanitize:
        command[1:1] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
    (output / (label + '.compile.stdout')).write_text(compiled.stdout)
    (output / (label + '.compile.stderr')).write_text(compiled.stderr)
    (output / (label + '.compile.json')).write_text(json.dumps(
        {'command': command, 'returncode': compiled.returncode}, indent=2) + '\n')
    if compiled.returncode or compiled.stdout or compiled.stderr:
        raise RuntimeError('host compilation failed:\n' + compiled.stderr[:16000])
    executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30,
                              env=sanitizer_environment())
    (output / (label + '.run.stdout')).write_text(executed.stdout)
    (output / (label + '.run.stderr')).write_text(executed.stderr)
    (output / (label + '.run.json')).write_text(json.dumps(
        {'returncode': executed.returncode}, indent=2) + '\n')
    if negative is not None:
        if not semantic_rejection(executed.returncode, executed.stdout, executed.stderr, negative, positive_stdout):
            raise RuntimeError('expected specific runtime mutation rejection:\n' + executed.stdout + executed.stderr)
        return {'status': 'REJECTED_EXPECTED_RUNTIME_MUTATION', 'returncode': 86,
                'marker': negative, 'compile_command': command, 'compiler_diagnostics': compiled.stderr,
                'execution_stdout': executed.stdout, 'execution_stderr': executed.stderr,
                'compiled_binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'generated_c_sha256': hashlib.sha256(program.encode()).hexdigest(), **prepared.manifest()}
    if executed.returncode:
        raise RuntimeError('host assertions failed:\n' + executed.stdout + executed.stderr)
    cases = [line.removeprefix('PASS ') for line in executed.stdout.splitlines() if line.startswith('PASS ')]
    if not positive_result(executed.returncode, executed.stdout, executed.stderr, expected, expected_names):
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
    parser.add_argument('--sanitize', action='store_true', help='ASan/UBSan host checks, not kernel instrumentation')
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
              'mode': 'CANDIDATE_ONLY' if args.candidate_only else ('BASELINE_AND_CANDIDATE' if args.candidate else 'BASELINE_ONLY_5_CANDIDATE_INCOMPLETE'),
              'original_baseline_executed': not args.candidate_only,
              'selected_inputs': {'baseline': str(args.baseline.resolve()) if args.baseline else None,
                                  'candidate': str(args.candidate.resolve()) if args.candidate else None},
              'network_access': False, 'compiler': subprocess.run([cc, '--version'], text=True, capture_output=True, timeout=10).stdout,
              'host_platform': platform.platform(), 'python_version': platform.python_version(),
              'result_gate_controls': check_result_oracles(),
              'test_assets': [{'path': name, 'sha256': hashlib.sha256((HERE / name).read_bytes()).hexdigest()}
                              for name in (Path(__file__).name, 'extract_prepared_c.py',
                                           'host_kernel_stubs.h', 'host_baseline_cases.c', 'host_candidate_cases.c',
                                           'host_edma_retirement.h')],
              'runs': []}
    report['status'] = 'INCOMPLETE'
    def save_progress():
        (output / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    save_progress()
    if args.sanitize:
        report['sanitizer_canaries'] = sanitizer_checks(cc, output)
        save_progress()
    if args.baseline:
        prepared = Prepared(args.baseline)
        report['runs'].append(run(baseline_program(prepared), prepared, cc, output, 'baseline-controls', sanitize=args.sanitize))
        save_progress()
    if args.candidate:
        prepared = Prepared(args.candidate)
        retirement = has_retirement(prepared)
        candidate_expected = 31 if retirement else 21
        report['mode'] = ('CANDIDATE_ONLY_' + str(candidate_expected + 5) if args.candidate_only else
                          'BASELINE_AND_CANDIDATE_' + str(candidate_expected + 10))
        candidate_run = run(candidate_program(prepared), prepared, cc, output, 'candidate-ipq807x',
                            ipq=True, expected=candidate_expected, sanitize=args.sanitize,
                            expected_names=RETIREMENT_CASES if retirement else IPQ_CASES)
        report['runs'].append(candidate_run)
        save_progress()
        prepared = Prepared(args.candidate)
        other_soc_run = run(baseline_program(prepared, other_soc=True), prepared, cc, output,
                            'candidate-other-soc-controls', sanitize=args.sanitize)
        report['runs'].append(other_soc_run)
        save_progress()
        first = {row['path']: row['sha256'] for row in candidate_run['sources']}
        second = {row['path']: row['sha256'] for row in other_soc_run['sources']}
        if any(first[path] != second[path] for path in first.keys() & second.keys()):
            raise ValueError('candidate changed between IPQ807X and other-SoC runs')
        report['candidate_status'] = 'PASS_EXTRACTED_C_HOST_SUBSTITUTES_ONLY'
        report['retirement_profile'] = 'ACTUAL_EDMA_FUNCTIONS' if retirement else 'PRE_015_NO_RETIREMENT_PROVIDER'
        report['retirement_mutations'] = []
        if retirement:
            for name, marker in RETIREMENT_MUTATIONS.items():
                prepared = Prepared(args.candidate)
                report['retirement_mutations'].append(run(candidate_program(prepared, name), prepared, cc,
                    output, 'mutation-' + name, ipq=True, sanitize=args.sanitize, negative=marker,
                    positive_stdout=candidate_run['execution_stdout']))
                row = report['retirement_mutations'][-1]
                if {item['path']: item['sha256'] for item in row['sources']} != first:
                    raise ValueError('candidate source changed before mutation run')
                save_progress()
    else:
        report['candidate_status'] = 'INCOMPLETE_NO_CANDIDATE_EXECUTED'
    report['total_cases'] = sum(row['count'] for row in report['runs'])
    report['expected_cases'] = (5 if args.baseline else 0) + (candidate_expected + 5 if args.candidate else 0)
    if report['total_cases'] != report['expected_cases']:
        raise ValueError('mode case count mismatch')
    for asset in report['test_assets']:
        if hashlib.sha256((HERE / asset['path']).read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('test asset changed during run: ' + asset['path'])
    report['status'] = 'PASS_HOST_SUBSTITUTES_ONLY'
    save_progress()
    print(json.dumps({'status': report['status'], 'cases': report['total_cases'],
                      'retirement_profile': report.get('retirement_profile'),
                      'runtime_mutations_rejected': len(report.get('retirement_mutations', [])),
                      'kernel_or_ax6_acceptance': False}))


if __name__ == '__main__':
    main()
