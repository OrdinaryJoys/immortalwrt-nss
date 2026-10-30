#!/usr/bin/env python3
"""Bounded native S2 oracle. No kernel, target, make, or archived program execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
import ssdk_source_prepare as source

HERE = Path(__file__).resolve()
FIX = HERE.parent / 'ssdk-fdb-retirement'
PATCH = source.PACKAGE / 'patches/029-ssdk-fdb-retirement.patch'
FROZEN_029 = 'a0e19f941d404525dd21bc4c374e577ac3ca8d6663425e2a5a437d36adcf8cd5'
# The new final barrier adds six model checks on each of80 final drains.
EXPECTED_SUMMARY = b'cases=34 checks=12048 scans=7 notifications=4 irq_frees=4 cancels=168\n'
LAST_LEAVE_SUMMARY = b'PASS last-leave-window wake-before-free=1\n'
GROUPS = {
    'src/init/ssdk_init.c': '''qca_fdb_sw_sync_supported qca_fdb_sw_sync_enter
qca_fdb_sw_sync_leave qca_fdb_sw_sync_work_task qca_fdb_sw_sync_work_setup
qca_fdb_sw_sync_work_init qca_fdb_sw_sync_work_start qca_fdb_sw_sync_work_stop
qca_fdb_sw_sync_work_fini ssdk_fdb_retire_controls ssdk_alloc_priv ssdk_free_priv
ssdk_cleanup'''.split(),
    'src/ref/ref_fdb.c': '''_ref_fdb_sw_table_update _ref_fdb_notify_mac
ref_fdb_sw_sync_reset ref_fdb_sw_sync_fini ref_fdb_sw_sync_task'''.split(),
    'src/init/ssdk_interrupt.c': '''qca_phy_disable_intr qca_switch_disable_intr
qca_phy_enable_intr qca_switch_enable_intr qca_phy_clean_intr qca_switch_clean_intr
qca_link_change_task qca_intr_workqueue_task qca_intr_handle qca_intr_work_init
qca_intr_work_pause qca_intr_work_resume qca_intr_deinit qca_intr_init'''.split(),
    'src/init/ssdk_netlink.c': '''ssdk_genl_stop_controls ssdk_new_mac ssdk_expire_mac
ssdk_poll_mac ssdk_genl_send_mac_info ssdk_genl_notify_mac_info ssdk_genl_init
ssdk_genl_deinit'''.split(),
    'src/init/ssdk_plat.c': 'ssdk_sysfs_remove_locked ssdk_sysfs_init ssdk_sysfs_exit'.split(),
}


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def positive_ok(rc, stdout, stderr, timed_out=False, expected=EXPECTED_SUMMARY):
    return not timed_out and rc == 0 and not stderr and stdout == expected


def negative_ok(rc, stdout, stderr, marker, timed_out=False):
    return (not timed_out and rc == 86 and not stdout and
            stderr == ('SSDK_FDB ' + marker + '\n').encode())


def oracle_controls():
    marker = 'example'
    valid = b'SSDK_FDB example\n'
    require(positive_ok(0, EXPECTED_SUMMARY, b''), 'positive oracle control')
    require(negative_ok(86, b'', valid, marker), 'negative oracle control')
    controls = [(0, b'', valid, False), (1, b'', valid, False),
                (86, b'', b'', False), (86, b'', b'SSDK_FDB wrong\n', False),
                (86, b'', valid + valid, False), (86, b'noise', valid, False),
                (86, b'', valid + b'noise', False), (-11, b'', valid, False),
                (97, b'', valid, False), (98, b'', valid, False),
                (86, b'', valid + b'AddressSanitizer: fault\n', False),
                (86, b'', valid + b'runtime error: fault\n', False),
                (86, b'', valid, True)]
    for rc, stdout, stderr, timeout in controls:
        require(not negative_ok(rc, stdout, stderr, marker, timeout), 'negative oracle pollution')
    for stdout in [b'', EXPECTED_SUMMARY + EXPECTED_SUMMARY,
                   EXPECTED_SUMMARY.replace(b'cases=34', b'cases=33'),
                   EXPECTED_SUMMARY.replace(b'checks=12048', b'checks=1'),
                   EXPECTED_SUMMARY.replace(b'cancels=168', b'cancels=167'),
                   EXPECTED_SUMMARY + b'extra=0\n']:
        require(not positive_ok(0, stdout, b''), 'positive summary pollution')
    for rc, stderr, timeout in [(86, b'', False), (-11, b'', False),
                                (0, b'noise', False), (0, b'', True)]:
        require(not positive_ok(rc, EXPECTED_SUMMARY, stderr, timeout), 'positive result pollution')
    return {'valid_controls': 2, 'negative_rejections': len(controls), 'positive_rejections': 10}


def masked(text):
    # Preserve byte positions and line numbers while excluding C literals/comments.
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def close_brace(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
    raise RuntimeError('unclosed C definition')


def function(text, name):
    clean = masked(text)
    found = list(re.finditer(r'(?m)^(?:static\s+)?(?:void|int|bool|sw_error_t|irqreturn_t)\s+' +
                            re.escape(name) + r'\s*\([^;{}]*\)\s*\{', clean))
    require(len(found) == 1, 'definition cardinality: ' + name)
    match = found[0]
    end = close_brace(clean, clean.index('{', match.start()))
    return text[match.start():end], text.count('\n', 0, match.start()) + 1


def aggregate(text, pattern):
    clean = masked(text)
    hits = list(re.finditer(pattern, clean, re.M))
    require(len(hits) == 1, 'aggregate cardinality: ' + pattern)
    start = hits[0].start()
    end = close_brace(clean, clean.index('{', start))
    require(clean[end:].lstrip().startswith(';'), 'aggregate terminator')
    return text[start:clean.index(';', end) + 1]


def extract(tree, dest):
    dest.mkdir()
    funcs, records = {}, []
    for relative, names in GROUPS.items():
        text = (tree / relative).read_text()
        for name in names:
            body, line = function(text, name)
            funcs[name] = body
            (dest / (name + '.c.txt')).write_text(body + '\n')
            records.append({'function': name, 'path': relative, 'line': line,
                            'sha256': sha(body.encode()), 'complete_definition': True})
    header = (tree / 'include/init/ssdk_plat.h').read_text()
    full = aggregate(header, r'^struct qca_phy_priv\s*\{')
    (dest / 'qca_phy_priv.full.h.txt').write_text(full + '\n')
    fields = []
    wanted = '''version revision device_id ports interrupt_no intr_gpio_num interrupt_flag
intr_name link_polling_required fdb_sync qca_ssdk_sw_dev_registered qm_lock
intr_workqueue intr_ctrl_lock intr_rearm_lock intr_state_lock intr_work_initialized
intr_requested intr_stopping intr_paused intr_masked intr_gpio_requested
fdb_sw_sync_lock fdb_ctrl_lock fdb_wait fdb_work_initialized fdb_ready fdb_stopping
fdb_draining fdb_users fdb_sw_sync_dwork fdb_sw_sync_port_map sw_fdb_tbl
fdb_polling_started'''.split()
    for name in wanted:
        hits = re.findall(r'(?m)^\s*[^;{}\n]+\b' + name + r'(?:\[[^\]]+\])?\s*;', full)
        require(len(hits) == 1, 'field cardinality: ' + name)
        fields.append(hits[0].strip())
    enums = re.findall(r'enum\s*\{[^{}]*\};', header)
    enum = [e for e in enums if 'QCA_VER_HPPE' in e]
    require(len(enum) == 1, 'version enum')
    fdb_type = re.findall(r'typedef enum\s*\{[^{}]*\}\s*fdb_sync_t;', header)
    require(len(fdb_type) == 1, 'actual fdb_sync_t')
    net = (tree / 'src/init/ssdk_netlink.c').read_text()
    globals_ = 'struct qca_phy_priv **qca_phy_priv_global;\n'
    globals_ += net[net.index('static DEFINE_MUTEX(ssdk_genl_lifecycle_lock)'):
                    net.index('void ssdk_genl_stop_controls')]
    for name, kind in [('ssdk_genl_policy', 'nla_policy'), ('ssdk_genl_ops', 'genl_ops'),
                       ('ssdk_genl_mcgrp', 'genl_multicast_group'), ('ssdk_family', 'genl_family')]:
        globals_ += aggregate(net, r'^struct ' + kind + r' ' + name + r'(?:\[\])?\s*=\s*\{') + '\n'
    plat = (tree / 'src/init/ssdk_plat.c').read_text()
    attrs = plat[plat.index('static const struct device_attribute ssdk_dev_id_attr ='):
                 plat.index('struct kobject *ssdk_sys = NULL;')]
    globals_ += attrs
    globals_ += plat[plat.index('struct kobject *ssdk_sys = NULL;'):
                     plat.index('static void ssdk_sysfs_remove_locked')]
    (dest / 'actual-globals.c.txt').write_text(globals_)
    save(dest / 'MANIFEST.json', {'functions': records, 'host_struct_fields': wanted,
                                 'full_struct_saved_not_target_ABI': True,
                                 'attribute_callback_bodies': 'mocked, not extracted'})
    template = (FIX / 'fixture.c').read_text()
    def render(selected):
        replacements = {
            'ACTUAL_ENUM': enum[0] + '\n' + fdb_type[0], 'ACTUAL_FIELDS': '\n'.join(fields),
            'ACTUAL_PROTOTYPES': '\n'.join(b[:b.index('{')].rstrip() + ';' for b in selected.values()),
            'ACTUAL_GLOBALS': globals_, 'ACTUAL_FUNCTIONS': '\n\n'.join(selected.values())}
        result = template
        for name, value in replacements.items():
            require(result.count('/* ' + name + ' */') == 1, 'fixture marker')
            result = result.replace('/* ' + name + ' */', value)
        return result
    return funcs, render


def mutants(original):
    result = []
    def add(label, fn, before, after, marker, mode='suite'):
        require(original[fn].count(before) == 1, 'mutant cardinality: ' + label)
        changed = dict(original)
        changed[fn] = changed[fn].replace(before, after)
        result.append((label, changed, marker, mode))
    add('missing-mht', 'qca_fdb_sw_sync_supported', 'priv->version == QCA_VER_MHT',
        'false', 'supported-start')
    add('unsupported-success', 'qca_fdb_sw_sync_work_start', 'return -EOPNOTSUPP;',
        'return 0;', 'unsupported-start')
    fn = 'qca_fdb_sw_sync_work_stop'
    changed = dict(original)
    changed[fn] = original[fn].replace('mutex_lock(&priv->fdb_ctrl_lock);', '').replace(
        'mutex_unlock(&priv->fdb_ctrl_lock);', '')
    result.append(('partial-without-controller', changed, 'controller-serialization', 'suite'))
    add('worker-tail-unchecked', 'qca_fdb_sw_sync_work_task',
        'if (priv->fdb_polling_started && !priv->fdb_stopping && !priv->fdb_draining)',
        'if (true)', 'queue-after-stop')
    add('no-final-latch', 'qca_fdb_sw_sync_work_fini', 'priv->fdb_stopping = true;',
        'priv->fdb_stopping = false;', 'queue-after-stop')
    add('shared-no-admission', 'ref_fdb_sw_sync_task',
        'if (!qca_fdb_sw_sync_enter(priv))\n\t\treturn SW_BUSY;', '', 'shared-fdb-admission', 'direct')
    add('shared-no-leave', 'ref_fdb_sw_sync_task', 'qca_fdb_sw_sync_leave(priv);',
        '', 'fdb-reference-balance', 'direct')
    changed = dict(original)
    changed['ref_fdb_sw_sync_reset'] = original['ref_fdb_sw_sync_reset'].replace(
        'aos_lock_bh(&priv->fdb_sw_sync_lock);', '').replace('aos_unlock_bh(&priv->fdb_sw_sync_lock);', '')
    result.append(('reset-without-state-lock', changed, 'fdb-list-lock', 'suite'))
    add('irq-drain-before-free', 'qca_intr_deinit', 'if (priv->intr_requested) {\n\t\tfree_irq',
        'cancel_work_sync(&priv->intr_workqueue);\n\tif (priv->intr_requested) {\n\t\tfree_irq', 'irq-free-before-drain')
    add('irq-request-failure-owned', 'qca_intr_init', 'if (ret) {',
        'if (ret) {\n\t\tpriv->intr_requested = true;', 'irq-failure-ledger')
    add('irq-no-final-admission', 'qca_intr_deinit', 'priv->intr_stopping = true;',
        'priv->intr_stopping = false;', 'irq-close-before-free')
    add('irq-tail-unchecked', 'qca_intr_workqueue_task',
        'if (!priv->intr_stopping && !priv->intr_paused && priv->intr_masked)',
        'if (priv->intr_masked)', 'enable-owned-irq')
    add('poll-no-admission', 'ssdk_poll_mac', 'if (!ssdk_genl_accepting)',
        'if (false)', 'control-admission', 'control')
    add('poll-hides-start-error', 'ssdk_poll_mac',
        'ret = qca_fdb_sw_sync_work_start(priv, BIT(port_id));',
        '(void)qca_fdb_sw_sync_work_start(priv, BIT(port_id));', 'poll-start-errno')
    add('notify-no-user', 'ssdk_genl_notify_mac_info', '++ssdk_genl_notify_users;',
        '', 'notify-user-ledger', 'sender-direct')
    add('notify-no-leave', 'ssdk_genl_notify_mac_info', 'drained = --ssdk_genl_notify_users == 0;',
        'drained = ssdk_genl_notify_users == 0;', 'notify-user-balance', 'sender')
    add('sysfs-null-success', 'ssdk_sysfs_init', 'ret = -ENOMEM;',
        'ret = 0;', 'sysfs-alloc-errno')
    add('hardware-free-before-controls', 'ssdk_cleanup', 'ssdk_fdb_retire_controls();',
        '', 'free-after-controls', 'roots')
    add('private-free-before-controls', 'ssdk_free_priv', 'ssdk_fdb_retire_controls();',
        '', 'free-after-controls', 'roots')
    add('family-before-producers', 'ssdk_fdb_retire_controls', 'ssdk_sysfs_exit();',
        'ssdk_sysfs_exit();\n\tssdk_genl_deinit();', 'family-after-producers', 'roots')
    add('wake-after-state-unlock', 'qca_fdb_sw_sync_leave',
        'if (drained)\n\t\twake_up_all(&priv->fdb_wait);\n\taos_unlock_bh(&priv->fdb_sw_sync_lock);',
        'aos_unlock_bh(&priv->fdb_sw_sync_lock);\n\tif (drained)\n\t\twake_up_all(&priv->fdb_wait);',
        'wake-after-private-free', 'last-leave-window')
    return result


def final_barrier_contract(funcs):
    body = masked(funcs['qca_fdb_sw_sync_work_fini'])
    return re.search(r'wait_event\(priv->fdb_wait, !READ_ONCE\(priv->fdb_users\)\);\s*'
                     r'aos_lock_bh\(&priv->fdb_sw_sync_lock\);\s*'
                     r'aos_unlock_bh\(&priv->fdb_sw_sync_lock\);\s*#ifdef IN_FDB', body) is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--frozen-029-sha256', required=True)
    parser.add_argument('--baseline-data', type=Path, default=source.AUDIT / 'SSDK-FDB-baseline-r1')
    args = parser.parse_args()
    require(args.frozen_029_sha256 == FROZEN_029, 'unexpected authorized frozen029 hash')
    require(sha(PATCH.read_bytes()) == args.frozen_029_sha256, '029 freeze mismatch')
    patches = source.patch_inventory()
    require(len(patches) == 17 and patches[-1] == PATCH, 'expected exact 16 plus frozen029')
    receipt_path = source.AUDIT / 'SSDK-FDB-SOURCE-FREEZE-r2.json'
    receipt = json.loads(receipt_path.read_text())
    require(receipt['patch_sha256'] == FROZEN_029 and
            [(p.name, sha(p.read_bytes())) for p in patches] ==
            [(p['name'], p['sha256']) for p in receipt['patches']], 'frozen entire chain drift')
    require((FIX / 'README.md').is_file(), 'required fixture README missing')
    out = args.output.resolve()
    require(out.parent == source.AUDIT and out.name.startswith('SSDK-FDB-ADOPT-') and not out.exists(),
            'fresh SSDK-FDB output required')
    bound = [HERE, *sorted(p for p in FIX.rglob('*') if p.is_file()),
             Path(source.__file__), HERE.parent / 'edma_patch_context.py', receipt_path,
             source.AUDIT / 'SSDK-TEST-QUALITY-PLAN.json', *patches]
    identities = {str(p): sha(p.read_bytes()) for p in bound}
    out.mkdir()
    result = {'status': 'INCOMPLETE', 'scope': 'S2_NATIVE_MODEL_NOT_FULL_MODULE_PHY_DSA',
              'frozen_029_sha256': args.frozen_029_sha256, 'command': sys.argv,
              'inputs': identities, 'sanitize': args.sanitize, 'executions': [], 'compilations': [],
              'expected_positive_summary': EXPECTED_SUMMARY.decode().strip(),
              'oracle_controls': oracle_controls()}
    def checkpoint():
        save(out / 'RESULTS.json', result)
    checkpoint()
    try:
        tree, prepared = source.prepare(args.upstream_cache, out / 'source')
        result['source_result'] = str(out / 'source/RESULTS.json')
        result['pin'] = prepared['pin']
        funcs, render = extract(tree, out / 'extracted')
        result['extracted_functions'] = len(funcs)
        require(final_barrier_contract(funcs), 'unconditional final state-lock barrier')
        barrier = '\taos_lock_bh(&priv->fdb_sw_sync_lock);\n\taos_unlock_bh(&priv->fdb_sw_sync_lock);'
        body = funcs['qca_fdb_sw_sync_work_fini']
        require(body.count(barrier) == 1, 'unique final barrier')
        for changed in [body.replace(barrier, ''),
                        body.replace(barrier, '#ifdef IN_FDB\n' + barrier + '\n#endif'),
                        body.replace(barrier, '/* ' + barrier + ' */')]:
            require(not final_barrier_contract({**funcs, 'qca_fdb_sw_sync_work_fini': changed}),
                    'static barrier poison accepted')
        result['final_barrier_static_controls'] = {'valid': 1, 'rejected': 3,
            'scope': 'Source position/guard checks, not semantic runtime negative cases'}
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
                   UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode=97')
        result['sanitizer_environment'] = {k: env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
        flags = ['-std=gnu11', '-pthread', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-unused-variable',
                 '-DIN_FDB', '-DIN_NETLINK', '-DMHT', '-DHPPE',
                 '-DISISC', '-DIN_PTP']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        version = subprocess.run([str(args.compiler), '--version'], capture_output=True, timeout=20)
        require(version.returncode == 0 and not version.stderr, 'compiler identity')
        result['compiler'] = version.stdout.decode()
        def compile_run(label, code, mode, expected=None, canary=None,
                        positive_expected=EXPECTED_SUMMARY, no_fdb=False):
            path = out / (label + '.c')
            binary = out / label
            path.write_text(code)
            selected_flags = [f for f in flags if not (no_fdb and f == '-DIN_FDB')]
            cmd = [str(args.compiler), *selected_flags, str(path), '-o', str(binary)]
            compiled = subprocess.run(cmd, capture_output=True, timeout=90)
            (out / (label + '.compile.stdout')).write_bytes(compiled.stdout)
            (out / (label + '.compile.stderr')).write_bytes(compiled.stderr)
            result['compilations'].append({'label': label, 'command': cmd,
                'returncode': compiled.returncode, 'stdout_sha256': sha(compiled.stdout),
                'stderr_sha256': sha(compiled.stderr), 'source_sha256': sha(path.read_bytes())})
            checkpoint()
            require(compiled.returncode == 0 and not compiled.stdout and not compiled.stderr,
                    'clean compile required: ' + label)
            run_env = dict(env)
            if label == 'ubsan-canary':
                # exitcode is shared by the combined sanitizer runtime.
                run_env = {k: v.replace('exitcode=97', 'exitcode=98')
                           if k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS') else v
                           for k, v in run_env.items()}
            try:
                run = subprocess.run([str(binary), mode], capture_output=True, env=run_env, timeout=30)
            except subprocess.TimeoutExpired as error:
                (out / (label + '.stdout')).write_bytes(error.stdout or b'')
                (out / (label + '.stderr')).write_bytes(error.stderr or b'')
                result['executions'].append({'label': label, 'status': 'FAIL_TIMEOUT',
                                              'timed_out': True, 'run_command': [str(binary), mode]})
                raise
            (out / (label + '.stdout')).write_bytes(run.stdout)
            (out / (label + '.stderr')).write_bytes(run.stderr)
            entry = {'label': label, 'source_sha256': sha(path.read_bytes()),
                     'sanitizer_environment': {k: run_env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')},
                     'binary_sha256': sha(binary.read_bytes()), 'compile_command': cmd,
                     'returncode': run.returncode, 'run_command': [str(binary), mode],
                     'stdout_sha256': sha(run.stdout),
                     'stderr_sha256': sha(run.stderr)}
            result['executions'].append(entry)
            checkpoint()
            if canary:
                require(run.returncode == (97 if label == 'asan-canary' else 98) and
                        not run.stdout and canary in run.stderr,
                        'positive sanitizer stderr/exit gate: ' + label)
                require((b'SUMMARY: AddressSanitizer: heap-buffer-overflow' in run.stderr and
                         b'runtime error:' not in run.stderr) if label == 'asan-canary' else
                        (b'SUMMARY: UndefinedBehaviorSanitizer:' in run.stderr and
                         b'AddressSanitizer:' not in run.stderr), 'isolated sanitizer diagnostic: ' + label)
                entry['status'] = 'PASS_DIAGNOSTIC_CANARY'
            elif expected:
                require(negative_ok(run.returncode, run.stdout, run.stderr, expected),
                        'exact semantic negative gate: ' + label)
                entry['status'] = 'PASS_SEMANTIC_NEGATIVE'
            else:
                require(positive_ok(run.returncode, run.stdout, run.stderr, expected=positive_expected),
                        'clean positive gate: ' + label)
                entry['summary'] = run.stdout.decode().strip()
                entry['status'] = 'PASS_NATIVE_MODEL'
            checkpoint()
        compile_run('candidate', render(funcs), 'suite')
        compile_run('candidate-last-leave-window', render(funcs), 'last-leave-window',
                    positive_expected=LAST_LEAVE_SUMMARY)
        compile_run('candidate-no-fdb-last-leave-window', render(funcs), 'last-leave-window',
                    positive_expected=LAST_LEAVE_SUMMARY, no_fdb=True)
        result['prior_source_gap'] = 'Freeze1 failing unmutated schedule retained; r2 tests last wake before final private free.'
        checkpoint()
        for label, selected, marker, mode in mutants(funcs):
            compile_run('negative-' + label, render(selected), mode, marker)
        baseline = args.baseline_data.resolve()
        require(baseline.is_relative_to(source.AUDIT), 'baseline outside evidence')
        old_result = json.loads((baseline / 'RESULTS.json').read_text())
        require(old_result['status'] == 'PASS_TEXT_ONLY' and old_result['patches'] == prepared['patches'][:16],
                'baseline does not bind current exact first16')
        require(source.inventory(baseline / 'prepared') == old_result['prepared_files'], 'baseline data drift')
        oldtext = (baseline / 'prepared/src/init/ssdk_init.c').read_text()
        oldnames = ['qca_fdb_sw_sync_work_task', 'qca_fdb_sw_sync_work_init',
                    'qca_fdb_sw_sync_work_start', 'qca_fdb_sw_sync_work_stop']
        oldfuncs = [function(oldtext, n)[0] for n in oldnames]
        old = (FIX / 'baseline.c').read_text().replace('/* OLD_FUNCTIONS */', '\n\n'.join(oldfuncs))
        result['old_source'] = {'data': str(baseline), 'source_sha256': sha(oldtext.encode()),
                                'function_sha256': {n: sha(b.encode()) for n, b in zip(oldnames, oldfuncs)}}
        compile_run('old-source-counterexample', old, 'suite', 'old-mht-still-running')
        if args.sanitize:
            compile_run('asan-canary', '#include <stdlib.h>\nint main(void){volatile int *p=malloc(sizeof(int)); p[1]=7; free((void*)p);return 0;}\n',
                        'suite', canary=b'AddressSanitizer: heap-buffer-overflow')
            compile_run('ubsan-canary', '#include <limits.h>\nint main(void){volatile int a=INT_MAX,b=1;return a+b;}\n',
                        'suite', canary=b'runtime error: signed integer overflow')
        result['source_input_stability'] = source.check_stable_inputs(out / 'source', prepared)
        require({str(p) for p in FIX.rglob('*') if p.is_file()} ==
                {str(p) for p in bound if p.is_relative_to(FIX)}, 'test inventory drift')
        for name, digest in identities.items():
            require(sha(Path(name).read_bytes()) == digest, 'test/live input drift: ' + name)
        result['artifacts'] = {str(p.relative_to(out)): sha(p.read_bytes())
                               for p in out.rglob('*') if p.is_file() and p.name != 'RESULTS.json'
                               and not p.is_relative_to(out / 'source')}
        result['status'] = 'PASS_S2_NATIVE_MODEL_ONLY'
        result['ordinary_suite_status'] = 'PASS_S2_NATIVE_MODEL_ONLY'
        result['semantic_negatives'] = len(mutants(funcs))
        checkpoint()
        print(json.dumps({'status': result['status'], 'result': str(out / 'RESULTS.json'),
                          'summary': result['executions'][0]['summary'],
                          'semantic_negatives': result['semantic_negatives']}))
    except Exception as error:
        result['error'] = str(error)
        checkpoint()
        raise


if __name__ == '__main__':
    main()
