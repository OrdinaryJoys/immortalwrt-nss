#!/usr/bin/env python3
"""Bounded real-source module-readiness host model; not kernel concurrency.

Only an explicitly invoked runner compiles/runs host C. Import has no main side
effects. No firmware, network, target, threads, IRQ or archived programs.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
EXTRACTOR = HERE / 'nss-dp-containment/extract_prepared_c.py'
HELPER = HERE / 'test-nss-igs-sync-completion.py'
MIRRED = 'nss_qdisc/igs/nss_mirred.c'
IFB = 'nss_qdisc/igs/nss_ifb.c'
INIT = 'nss_mirred_init_module'
CLEANUP = 'nss_mirred_cleanup_module'
VERSIONS = {'4.19': (4, 19, 0), '5.4': (5, 4, 0), '6.18.38': (6, 18, 38)}
# Author-read baseline18 extraction, including extractor's trailing newline.
CLEANUP_SHA256 = '8d824447dcf7c7de41f044eaa05ac73876bf5f162925f78dd3120ae9b671e8f2'
OPEN = ['owner-late-publication', 'cleanup-clears-owner-first',
        'S08-same-pair-late-reply', 'late-callback/app_data-lifetime',
        'whole-module-lifetime', 'firmware-compensation', 'real-concurrency']
CASES = ('success', 'notifier_fail_retry', 'action_fail_retry', 'nf_fail_retry')
EDGES = ('notifier.entry', 'notifier.publish', 'action.entry', 'action.publish',
         'nf.entry', 'nf.publish')
READY_CHECKS = {edge + '.' + field for edge in EDGES
                for field in ('sem_ready', 'lock_ready', 'done_ready', 'pending_idle')}
SNAP_KEYS = {'type', 'case', 'attempt', 'event', 'api', 'notifier', 'action', 'nf',
             'owner_observed', 'sem_ready', 'sem_count', 'lock_ready', 'done_ready',
             'done_tokens', 'pending', 'response', 'expected_interface',
             'expected_type', 'sem_inits', 'lock_inits', 'done_inits', 'returncode'}
INT_KEYS = SNAP_KEYS - {'type', 'case', 'event'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load(path, name):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_edit(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError('mutation/source context count drift: ' + repr(old))
    return text.replace(old, new)


def normalized(text, extract):
    return re.sub(r'\s+', '', extract.code_mask(text))


def extract_input(root, directory, extract, helper, registry, candidate):
    prepared = extract.Prepared(root)
    registry.append(prepared)
    fragments = {INIT: prepared.function(MIRRED, INIT),
                 CLEANUP: prepared.function(MIRRED, CLEANUP),
                 'nss_ifb_init': prepared.function(IFB, 'nss_ifb_init'),
                 'msg_response': helper.actual_declaration(prepared, extract)}
    field_shape = (r'static\s+struct\s+nss_ifb_msg_response\s*\{\s*'
                   r'struct\s+semaphore\s+sem\s*;\s*'
                   r'struct\s+completion\s+done\s*;\s*spinlock_t\s+lock\s*;\s*'
                   r'enum\s+nss_cmn_response\s+response\s*;\s*'
                   r'uint32_t\s+expected_interface\s*;\s*'
                   r'uint32_t\s+expected_type\s*;\s*bool\s+pending\s*;\s*'
                   r'\}\s+msg_response\s*;\s*')
    if not re.fullmatch(field_shape, extract.code_mask(fragments['msg_response'])):
        raise ValueError('real guard field layout drift')
    expected_ifb = ('void nss_ifb_init() { sema_init(&msg_response.sem, 1); '
                    'spin_lock_init(&msg_response.lock); msg_response.pending = false; '
                    'init_completion(&msg_response.done); }')
    if normalized(fragments['nss_ifb_init'], extract) != normalized(expected_ifb, extract):
        raise ValueError('private init is no longer the bounded void/no-allocation helper')
    if sha(fragments[CLEANUP].encode()) != CLEANUP_SHA256:
        raise ValueError('cleanup differs from author-read baseline18 bytes')
    init = fragments[INIT]
    if init.count('\tnss_ifb_init();\n') != 1:
        raise ValueError('expected one real IFB init call')
    first_register = init.index('register_netdevice_notifier(')
    if candidate != (init.index('nss_ifb_init();') < first_register):
        raise ValueError('unexpected candidate19/baseline18 init placement')
    directory.mkdir()
    for name, fragment in fragments.items():
        (directory / (name + '.c')).write_bytes(fragment.encode())
    # Keep complete input snapshots as well as complete extracted definitions.
    for row in prepared.files.values():
        target = directory / 'input' / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row['text'].encode())
    return fragments


PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define __init
#define __exit
#define KERNEL_VERSION(a,b,c) (((a) << 16) + ((b) << 8) + (c))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
struct semaphore { int initialized, count; };
struct completion { int initialized, tokens; };
typedef struct { int initialized; } spinlock_t;
/* API objects/types are opaque substitutes, not kernel/NSS ABI. */
struct notifier_block { int model; };
struct tc_action_ops { int model; };
struct nf_hook_ops { int model; };
static struct notifier_block nss_mirred_device_notifier;
static struct tc_action_ops nss_mirred_act_ops;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
static struct nf_hook_ops nss_mirred_igs_nf_ops[2];
#define NSS_MIRRED_TAB_MASK 15
#else
struct pernet_operations { int model; };
static struct pernet_operations nss_mirred_net_ops;
#endif
static int module_token;
#define THIS_MODULE (&module_token)
'''


MODEL = r'''
static const char *case_name;
static unsigned checks, failures, case_checks, case_failures, case_count;
static int attempt, fail_at, notifier_live, action_live, nf_live, owner_observed;
static int sem_inits, lock_inits, done_inits, attempt_sem_start, last_return;
static const char *expected[32];
static unsigned expected_count, api_index, case_events, case_attempts;

static void check(bool ok, const char *label)
{
    ++checks; ++case_checks;
    if (!ok) {
        ++failures; ++case_failures;
        printf("{\"type\":\"failure\",\"case\":\"%s\",\"attempt\":%d,"
               "\"check\":\"%s\"}\n", case_name, attempt, label);
    }
}
static void snapshot(const char *event, bool api)
{
    if (api) {
        check(api_index < expected_count && !strcmp(event, expected[api_index]),
              "api.sequence");
        ++api_index;
    }
    ++case_events;
    printf("{\"type\":\"state\",\"case\":\"%s\",\"attempt\":%d,"
           "\"event\":\"%s\",\"api\":%d,\"notifier\":%d,\"action\":%d,\"nf\":%d,"
           "\"owner_observed\":%d,\"sem_ready\":%d,\"sem_count\":%d,"
           "\"lock_ready\":%d,\"done_ready\":%d,\"done_tokens\":%d,"
           "\"pending\":%d,\"response\":%d,\"expected_interface\":%u,"
           "\"expected_type\":%u,\"sem_inits\":%d,\"lock_inits\":%d,"
           "\"done_inits\":%d,\"returncode\":%d}\n",
           case_name, attempt, event, api, notifier_live, action_live, nf_live,
           owner_observed, msg_response.sem.initialized, msg_response.sem.count,
           msg_response.lock.initialized, msg_response.done.initialized,
           msg_response.done.tokens, msg_response.pending, (int)msg_response.response,
           msg_response.expected_interface, msg_response.expected_type,
           sem_inits, lock_inits, done_inits, last_return);
}
static void probe(const char *edge)
{
    char label[80];
    (void)snprintf(label, sizeof(label), "%s.probe", edge);
    snapshot(label, false);
#define READY(suffix, condition) do { \
    (void)snprintf(label, sizeof(label), "%s.%s", edge, suffix); \
    check((condition), label); \
} while (0)
    READY("sem_ready", msg_response.sem.initialized && msg_response.sem.count == 1);
    READY("lock_ready", msg_response.lock.initialized);
    READY("done_ready", msg_response.done.initialized && !msg_response.done.tokens);
    READY("pending_idle", !msg_response.pending);
#undef READY
}
static bool published(void) { return notifier_live || action_live || nf_live; }
void sema_init(struct semaphore *sem, int count)
{
    check(!published(), "init.not_published");
    check(sem == &msg_response.sem && count == 1, "init.sem_arguments");
    ++sem_inits; sem->initialized = 1; sem->count = count;
    snapshot("init.sem", false);
}
void spin_lock_init(spinlock_t *lock)
{
    check(!published(), "init.not_published");
    check(lock == &msg_response.lock, "init.lock_arguments");
    ++lock_inits; lock->initialized = 1;
    snapshot("init.lock", false);
}
void init_completion(struct completion *done)
{
    check(!published(), "init.not_published");
    check(done == &msg_response.done, "init.done_arguments");
    ++done_inits; done->initialized = 1; done->tokens = 0;
    snapshot("init.done", false);
}
static int register_netdevice_notifier(struct notifier_block *block)
{
    check(block == &nss_mirred_device_notifier, "api.notifier_argument");
    snapshot("notifier.enter", true); probe("notifier.entry");
    if (fail_at == 1) { snapshot("notifier.reject", true); return -41; }
    check(!notifier_live, "ledger.notifier_unique"); notifier_live = 1;
    snapshot("notifier.publish", true); probe("notifier.publish");
    return 0;
}
static void unregister_netdevice_notifier(struct notifier_block *block)
{
    check(block == &nss_mirred_device_notifier, "api.notifier_argument");
    check(notifier_live == 1, "ledger.notifier_owned"); notifier_live = 0;
    snapshot("notifier.unregister", true);
}
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
static int tcf_register_action(struct tc_action_ops *ops, int mask)
{
    check(mask == NSS_MIRRED_TAB_MASK, "api.legacy_mask");
#else
static int tcf_register_action(struct tc_action_ops *ops, struct pernet_operations *net)
{
    check(net == &nss_mirred_net_ops, "api.modern_net_ops");
#endif
    check(ops == &nss_mirred_act_ops, "api.action_argument");
    snapshot("action.enter", true); probe("action.entry");
    if (fail_at == 2) { snapshot("action.reject", true); return -52; }
    check(!action_live, "ledger.action_unique"); action_live = 1;
    snapshot("action.publish", true); probe("action.publish");
    /* Modern pernet/NF internals are NOT executed or asserted by this model. */
    return 0;
}
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
static void tcf_unregister_action(struct tc_action_ops *ops)
{
#else
static void tcf_unregister_action(struct tc_action_ops *ops, struct pernet_operations *net)
{
    check(net == &nss_mirred_net_ops, "api.modern_net_ops");
#endif
    check(ops == &nss_mirred_act_ops, "api.action_argument");
    check(action_live == 1, "ledger.action_owned"); action_live = 0;
    snapshot("action.unregister", true);
}
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
static int nf_register_hooks(struct nf_hook_ops *ops, size_t count)
{
    check(ops == nss_mirred_igs_nf_ops && count == 2, "api.nf_arguments");
    snapshot("nf.enter", true); probe("nf.entry");
    if (fail_at == 3) { snapshot("nf.reject", true); return -73; }
    check(!nf_live, "ledger.nf_unique"); nf_live = 1;
    snapshot("nf.publish", true); probe("nf.publish"); return 0;
}
static void nf_unregister_hooks(struct nf_hook_ops *ops, size_t count)
{
    check(ops == nss_mirred_igs_nf_ops && count == 2, "api.nf_arguments");
    check(nf_live == 1, "ledger.nf_owned"); nf_live = 0;
    snapshot("nf.unregister", true);
}
static void nss_igs_error(const char *format, ...)
{
    (void)format; snapshot("nf.error", true);
}
#endif
static void nss_igs_module_save(struct tc_action_ops *ops, void *module)
{
    check(ops == &nss_mirred_act_ops && (module == THIS_MODULE || !module),
          "api.owner_arguments");
    /* Record only. No modeled get/put, try_module_get, refcount or lifetime gate. */
    owner_observed = module != NULL;
    snapshot(module ? "owner.save" : "owner.clear", true);
}
'''


MAIN = r'''
static void plan(int failure)
{
    expected_count = api_index = 0; fail_at = failure;
    attempt_sem_start = sem_inits; last_return = 999;
#define EXPECT(event) do { expected[expected_count++] = event; } while (0)
    EXPECT("notifier.enter");
    if (failure == 1) { EXPECT("notifier.reject"); goto returned; }
    EXPECT("notifier.publish"); EXPECT("action.enter");
    if (failure == 2) {
        EXPECT("action.reject"); EXPECT("notifier.unregister"); goto returned;
    }
    EXPECT("action.publish");
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
    EXPECT("nf.enter");
    if (failure == 3) {
        EXPECT("nf.reject"); EXPECT("nf.error"); EXPECT("action.unregister");
        EXPECT("notifier.unregister"); goto returned;
    }
    EXPECT("nf.publish");
#endif
    EXPECT("owner.save");
returned:
    EXPECT("init.return");
    if (!failure) {
        EXPECT("owner.clear");
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
        EXPECT("nf.unregister");
#endif
        EXPECT("action.unregister"); EXPECT("notifier.unregister"); EXPECT("cleanup.return");
    }
#undef EXPECT
}
static void run_attempt(int failure)
{
    ++attempt; ++case_attempts; plan(failure);
    snapshot("attempt.begin", false);
    /* Keeps the complete void helper referenced even in omit-init negative control. */
    (void)&nss_ifb_init;
    int ret = nss_mirred_init_module();
    last_return = ret; snapshot("init.return", true);
    int expected_ret = failure == 1 ? -41 : failure == 2 ? -52 : failure == 3 ? -73 : 0;
    check(ret == expected_ret, "attempt.returncode");
    if (!failure) {
        check(notifier_live == 1 && action_live == 1 &&
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
              nf_live == 1 &&
#else
              nf_live == 0 &&
#endif
              owner_observed == 1, "attempt.success_ledger");
        check(sem_inits - attempt_sem_start == 1, "attempt.init_once");
    }
    /* Only successful init owns module cleanup; failures must unwind themselves. */
    if (ret == 0) { nss_mirred_cleanup_module(); snapshot("cleanup.return", true); }
    check(!notifier_live && !action_live && !nf_live, "attempt.resources_balanced");
    check(!owner_observed, "attempt.owner_record_clear");
    check(sem_inits == lock_inits && sem_inits == done_inits, "init.primitive_counts");
    check(api_index == expected_count, "api.complete");
    snapshot("attempt.end", false);
}
static void run_case(const char *name, int failure)
{
    case_name = name; case_checks = case_failures = case_events = case_attempts = 0;
    attempt = 0; notifier_live = action_live = nf_live = owner_observed = 0;
    sem_inits = lock_inits = done_inits = 0;
    memset(&msg_response, 0, sizeof(msg_response));
    /* Poison pending: the real private helper must explicitly establish idle. */
    msg_response.pending = true; msg_response.response = NSS_CMN_RESPONSE_EMSG;
    msg_response.expected_interface = 0xa5; msg_response.expected_type = 0x5a;
    run_attempt(failure);
    if (failure) run_attempt(0);
    ++case_count;
    printf("{\"type\":\"case\",\"case\":\"%s\",\"checks\":%u,\"failures\":%u,"
           "\"events\":%u,\"attempts\":%u,\"verdict\":\"%s\"}\n",
           name, case_checks, case_failures, case_events, case_attempts,
           case_failures ? "FAIL" : "PASS");
}
int main(void)
{
    run_case("success", 0);
    run_case("notifier_fail_retry", 1);
    run_case("action_fail_retry", 2);
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,4,0)
    run_case("nf_fail_retry", 3);
#endif
    printf("{\"type\":\"summary\",\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",
           case_count, checks, failures);
    return failures ? 1 : 0;
}
'''


def generated(fragments, response_enum, version):
    number = (version[0] << 16) + (version[1] << 8) + version[2]
    return ('/* Actual definitions are unmodified except explicitly labeled mutations. */\n'
            f'#define LINUX_VERSION_CODE {number}\n' + PREFIX + response_enum +
            fragments['msg_response'] + MODEL + fragments['nss_ifb_init'] +
            fragments[INIT] + fragments[CLEANUP] + MAIN)


def mutations(fragments):
    call = '\tnss_ifb_init();\n'
    original = fragments[INIT]
    removed = exact_edit(original, call, '')
    notifier_end = ('\terr = register_netdevice_notifier(&nss_mirred_device_notifier);\n'
                    '\tif (err) {\n\t\treturn err;\n\t}\n')
    action_end = ('\tif (err) {\n'
                  '\t\tunregister_netdevice_notifier(&nss_mirred_device_notifier);\n'
                  '\t\treturn err;\n\t}\n')
    save = '\tnss_igs_module_save(&nss_mirred_act_ops, THIS_MODULE);\n'
    success = '\treturn 0;\n}'
    specs = [
        ('omit_init', removed, 'success', 'notifier.entry.sem_ready', False),
        ('after_notifier', exact_edit(removed, notifier_end, notifier_end + call),
         'success', 'notifier.entry.sem_ready', False),
        ('after_action', exact_edit(removed, action_end, action_end + call, 2),
         'success', 'action.publish.sem_ready', False),
        ('success_tail', exact_edit(removed, success, call + success),
         'success', 'notifier.entry.sem_ready', False),
        ('reinit_published', exact_edit(original, save, save + call),
         'success', 'init.not_published', False),
        ('omit_action_failure_unwind', exact_edit(original, action_end,
            action_end.replace('\t\tunregister_netdevice_notifier(&nss_mirred_device_notifier);\n', ''), 2),
         'action_fail_retry', 'attempt.resources_balanced', False),
        ('wrong_action_failure_return', exact_edit(original, action_end,
            action_end.replace('return err;', 'return 0;'), 2),
         'action_fail_retry', 'attempt.returncode', False),
        ('omit_nf_failure_unwind', exact_edit(original,
            '\t\ttcf_unregister_action(&nss_mirred_act_ops);\n', ''),
         'nf_fail_retry', 'attempt.resources_balanced', True),
    ]
    for name, changed, case, check, legacy_only in specs:
        yield name, dict(fragments, **{INIT: changed}), {
            'case': case, 'check': check, 'attempt': 1, 'legacy_only': legacy_only,
            'before_sha256': sha(original.encode()), 'after_sha256': sha(changed.encode()),
            'original': original, 'replacement': changed,
            'requires': 'compile=0; normal run=1; empty stderr; complete JSON; designated assertion',
        }


def command(directory, label, argv, timeout, environment=None):
    try:
        process = subprocess.run(argv, capture_output=True, timeout=timeout, env=environment)
        stdout, stderr = process.stdout, process.stderr
        row = {'argv': argv, 'returncode': process.returncode, 'timeout': False}
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b'', error.stderr or b''
        row = {'argv': argv, 'returncode': None, 'timeout': True}
    except OSError as error:
        stdout, stderr = b'', str(error).encode()
        row = {'argv': argv, 'returncode': None, 'timeout': False, 'error': str(error)}
    for stream, data in [('stdout', stdout), ('stderr', stderr)]:
        path = directory / (label + '.' + stream)
        path.write_bytes(data)
        row[stream + '_file'] = path.name
        row[stream + '_sha256'] = sha(data)
    write_json(directory / (label + '.result.json'), row)
    return row, stdout.decode('utf-8', errors='strict'), stderr.decode('utf-8', errors='strict')


def expected_api(failure, legacy):
    events = ['notifier.enter']
    if failure == 1:
        return events + ['notifier.reject', 'init.return']
    events += ['notifier.publish', 'action.enter']
    if failure == 2:
        return events + ['action.reject', 'notifier.unregister', 'init.return']
    events += ['action.publish']
    if legacy:
        events += ['nf.enter']
        if failure == 3:
            return events + ['nf.reject', 'nf.error', 'action.unregister',
                             'notifier.unregister', 'init.return']
        events += ['nf.publish']
    return events + ['owner.save', 'init.return', 'owner.clear'] + (
        ['nf.unregister'] if legacy else []) + [
            'action.unregister', 'notifier.unregister', 'cleanup.return']


def parse_output(stdout, legacy):
    rows = [json.loads(line) for line in stdout.splitlines()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError('missing/nonobject JSON')
    names = CASES if legacy else CASES[:-1]
    cases, failed, states, summaries = [], [], [], []
    case_index = 0
    for row in rows:
        kind = row.get('type')
        if kind == 'summary':
            summaries.append(row)
            continue
        if summaries or case_index >= len(names) or row.get('case') != names[case_index]:
            raise ValueError('interleaved/reordered/extra case records')
        if kind == 'case':
            cases.append(row)
            case_index += 1
        elif kind == 'failure':
            if set(row) != {'type', 'case', 'attempt', 'check'} or not isinstance(row['check'], str):
                raise ValueError('invalid failure record')
            failed.append(row)
        elif kind == 'state':
            if set(row) != SNAP_KEYS or any(type(row[key]) is not int for key in INT_KEYS):
                raise ValueError('incomplete raw state')
            states.append(row)
        else:
            raise ValueError('unknown output record')
    if (case_index != len(names) or len(summaries) != 1 or rows[-1] != summaries[0] or
            set(summaries[0]) != {'type', 'cases', 'checks', 'failures'}):
        raise ValueError('missing/final/duplicate summary')
    total = summaries[0]
    if (any(type(total[key]) is not int for key in ('cases', 'checks', 'failures')) or
            total['cases'] != len(names) or total['checks'] != sum(row['checks'] for row in cases) or
            total['failures'] != len(failed) or total['failures'] != sum(row['failures'] for row in cases)):
        raise ValueError('summary totals disagree')
    signatures = {}
    for index, case in enumerate(cases):
        name = names[index]
        selected = [row for row in states if row['case'] == name]
        assertions = [row for row in failed if row['case'] == name]
        attempts = 1 if index == 0 else 2
        if (set(case) != {'type', 'case', 'checks', 'failures', 'events', 'attempts', 'verdict'} or
                any(type(case[key]) is not int for key in ('checks', 'failures', 'events', 'attempts')) or
                case['checks'] <= 0 or case['failures'] != len(assertions) or
                case['events'] != len(selected) or case['attempts'] != attempts or
                case['verdict'] != ('FAIL' if assertions else 'PASS')):
            raise ValueError('incomplete case summary: ' + name)
        if any(type(row['attempt']) is not int or row['attempt'] not in range(1, attempts + 1)
               for row in assertions + selected):
            raise ValueError('invalid attempt identity')
        if [row['attempt'] for row in selected] != sorted(row['attempt'] for row in selected):
            raise ValueError('interleaved attempts')
        signatures[name] = []
        for number in range(1, attempts + 1):
            items = [row for row in selected if row['attempt'] == number]
            if (not items or items[0]['event'] != 'attempt.begin' or
                    items[-1]['event'] != 'attempt.end' or
                    sum(row['event'] == 'attempt.begin' for row in items) != 1 or
                    sum(row['event'] == 'attempt.end' for row in items) != 1 or
                    sum(row['event'] == 'init.return' for row in items) != 1):
                raise ValueError('incomplete attempt: ' + name)
            non_api = {'attempt.begin', 'attempt.end', 'init.sem', 'init.lock', 'init.done'} | {
                edge + '.probe' for edge in EDGES}
            allowed_events = set(expected_api(0, legacy) + expected_api(index, legacy)) | non_api
            if any(row['event'] not in allowed_events or row['api'] not in (0, 1) or
                   bool(row['api']) != (row['event'] not in non_api)
                   for row in items):
                raise ValueError('unknown state event/API classification')
            api = [row['event'] for row in items if row['api']]
            signatures[name].append(api)
            # Independent oracles use the raw snapshots, not just a failure label.
            observed = Counter(row['check'] for row in assertions if row['attempt'] == number)
            probes = {edge + '.probe': edge for edge in EDGES}
            probe_after = {edge.replace('.entry', '.enter'): edge + '.probe' for edge in EDGES}
            derived = Counter()
            for position, state in enumerate(items):
                if state['api'] and state['event'] in probe_after:
                    if position + 1 >= len(items) or items[position + 1]['event'] != probe_after[state['event']]:
                        raise ValueError('missing/improperly ordered registration probe')
                if state['event'] in probes:
                    edge = probes[state['event']]
                    if position == 0 or not items[position - 1]['api'] or probe_after.get(
                            items[position - 1]['event']) != state['event']:
                        raise ValueError('orphaned/duplicate registration probe')
                    readiness = {
                        'sem_ready': state['sem_ready'] and state['sem_count'] == 1,
                        'lock_ready': state['lock_ready'],
                        'done_ready': state['done_ready'] and state['done_tokens'] == 0,
                        'pending_idle': not state['pending'],
                    }
                    for field, ready in readiness.items():
                        if not ready:
                            derived[edge + '.' + field] += 1
                if state['event'] in ('init.sem', 'init.lock', 'init.done') and any(
                        state[key] for key in ('notifier', 'action', 'nf')):
                    derived['init.not_published'] += 1
                if any(state[key] not in (0, 1) for key in (
                        'notifier', 'action', 'nf', 'owner_observed', 'sem_ready',
                        'lock_ready', 'done_ready', 'pending')):
                    raise ValueError('nonboolean modeled state')
            for check_name in READY_CHECKS | {'init.not_published'}:
                if observed[check_name] != derived[check_name]:
                    raise ValueError('readiness assertion does not match raw state: ' + check_name)
            ret = next(row for row in items if row['event'] == 'init.return')['returncode']
            failure = index if number == 1 else 0
            wanted = (0, -41, -52, -73)[failure]
            expected = expected_api(failure, legacy)
            independent = {
                'attempt.returncode': int(ret != wanted),
                'attempt.resources_balanced': int(any(items[-1][key] for key in ('notifier', 'action', 'nf'))),
                'attempt.owner_record_clear': int(bool(items[-1]['owner_observed'])),
                'attempt.init_once': int(not failure and items[-1]['sem_inits'] - items[0]['sem_inits'] != 1),
                'api.sequence': sum(position >= len(expected) or event != expected[position]
                                    for position, event in enumerate(api)),
                'api.complete': int(len(api) != len(expected)),
            }
            if any(observed[key] != value for key, value in independent.items()):
                raise ValueError('assertions disagree with independently checked state/API trace')
    return {'cases': cases, 'states': states, 'assertion_failures': failed,
            'summary': total, 'observable_signatures': signatures}


def qualify(row, role, mutation, legacy):
    failures = row['assertion_failures']
    pairs = {(item['case'], item['attempt'], item['check']) for item in failures}
    if role == 'candidate' and not mutation:
        return row['run']['returncode'] == 0 and not failures
    if row['run']['returncode'] != 1:
        return False
    readiness = READY_CHECKS | {'init.not_published', 'attempt.init_once'}
    if role == 'baseline':
        required = {(name, 1, 'notifier.entry.' + field)
                    for name in (CASES if legacy else CASES[:-1])
                    for field in ('sem_ready', 'lock_ready', 'done_ready', 'pending_idle')}
        return required <= pairs and all(item['check'] in readiness for item in failures)
    required = (mutation['case'], mutation['attempt'], mutation['check'])
    if mutation['case'] == 'success':
        allowed = readiness
        return required in pairs and all(item['check'] in allowed for item in failures)
    allowed = {'api.sequence', 'api.complete', 'attempt.resources_balanced',
               'ledger.notifier_unique', 'ledger.action_unique', 'init.not_published'}
    if mutation['check'] == 'attempt.returncode':
        allowed |= {'attempt.returncode', 'ledger.action_owned', 'ledger.nf_owned',
                    'ledger.notifier_owned'}
    return required in pairs and all(item['case'] == mutation['case'] and item['check'] in allowed
                                     for item in failures)


def execute(output, label, fragments, response_enum, version, args, role, mutation=None):
    directory = output / label
    directory.mkdir()
    source = directory / 'generated.c'
    code = generated(fragments, response_enum, version)
    source.write_bytes(code.encode())
    row = {'name': label, 'role': role, 'version': list(version), 'accepted': False,
           'generated_c': str(source), 'sha256': sha(code.encode()), 'mutation': mutation,
           'actual_cleanup_sha256': sha(fragments[CLEANUP].encode())}
    flags = ['-std=gnu11', '-O0', '-g', '-Wall', '-Wextra', '-Werror']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
    binary = directory / 'host-regression'
    compiled, _, _ = command(directory, 'compile', [args.cc, *flags, str(source), '-o', str(binary)], 120)
    row['compile'] = compiled
    if compiled['timeout'] or compiled['returncode'] != 0:
        row['error'] = 'compile failure is never negative-control evidence'
        return row
    if sha(source.read_bytes()) != row['sha256']:
        row['error'] = 'generated C changed during compilation'
        return row
    row['binary_sha256'] = sha(binary.read_bytes())
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    if args.sanitize:
        env['ASAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    row['run_environment'] = {key: env.get(key) for key in ('LC_ALL', 'ASAN_OPTIONS', 'UBSAN_OPTIONS')}
    run, stdout, stderr = command(directory, 'run', [str(binary)], 30, env)
    row['run'] = run
    if sha(source.read_bytes()) != row['sha256'] or sha(binary.read_bytes()) != row['binary_sha256']:
        row['error'] = 'generated C or binary changed during run'
        return row
    if run['timeout'] or run['returncode'] not in (0, 1) or stderr:
        row['error'] = 'timeout/signal/stderr/sanitizer/abnormal exit is not assertion evidence'
        return row
    try:
        legacy = version < (5, 4, 0)
        row.update(parse_output(stdout, legacy))
        if run['returncode'] != int(row['summary']['failures'] != 0):
            raise ValueError('exit code and explicit assertions disagree')
        row['accepted'] = qualify(row, role, mutation, legacy)
        if not row['accepted']:
            row['error'] = 'designated case/check or allowed-failure contract missed'
    except (ValueError, KeyError, TypeError) as error:
        row['error'] = 'incomplete/invalid evidence: ' + str(error)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clients', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--driver', type=Path, help='default: clients sibling prepared-driver; enum only')
    parser.add_argument('--cc', default='cc', help='one executable, not a shell command')
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True, help='new directory; never reused')
    args = parser.parse_args()
    args.clients = args.clients.resolve(strict=True)
    args.baseline = args.baseline.resolve(strict=True) if args.baseline else None
    args.driver = (args.driver or args.clients.parent / 'prepared-driver').resolve(strict=True)
    if args.baseline == args.clients:
        parser.error('baseline and candidate must be distinct roots')
    if not args.cc or not shutil.which(args.cc):
        parser.error('--cc must name an available executable')
    args.cc = str(Path(shutil.which(args.cc)).resolve(strict=True))
    output = args.output.absolute()
    if os.path.lexists(output):
        parser.error('--output already exists (including symlinks)')
    resolved = output.resolve()
    protected = [args.clients, args.driver, HERE.parent]
    if args.baseline:
        protected.append(args.baseline)
    if any(resolved == root or root in resolved.parents or resolved in root.parents for root in protected):
        parser.error('--output must be outside source, driver and repository trees')
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 1, 'status': 'FAIL', 'open': OPEN,
              'scope': 'deterministic host conditional/control-flow and early-publication readiness only',
              'not_claimed': 'kernel compatibility/concurrency, actual callbacks, module owner acquisition/lifetime, FW safety',
              'arguments': {key: str(value) if isinstance(value, Path) else value
                            for key, value in vars(args).items()} | {'output': str(output)},
              'provenance': {}, 'inputs': [], 'variants': [],
              'cleanup_baseline18_pinned_sha256': CLEANUP_SHA256,
              'versions': VERSIONS, 'case_inventory': {
                  version: list(CASES if number < (5, 4, 0) else CASES[:-1])
                  for version, number in VERSIONS.items()},
              'adaptations': ['Complete actual init/cleanup/IFB-init/declaration/response enum retained.',
                              'Original CPP envelopes retained; three host branches, NOT kernel builds.',
                              'Opaque API/type/registration stand-ins; modern pernet/NF internals excluded.',
                              'Probes at register entry and successful publication, before API return.',
                              'Sem/lock/completion are flags/counters; pending poisoned before each scenario.',
                              'Owner save/clear observed in sequence only; never a lifetime gate.',
                              'No body adaptation outside separately archived exact mutations.']}
    registry = []
    try:
        dependency_dir = output / 'dependencies'
        dependency_dir.mkdir()
        for label, path in [('script', Path(__file__).resolve()), ('extractor', EXTRACTOR), ('helper', HELPER)]:
            data = path.read_bytes()
            result['provenance'][label] = {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}
            (dependency_dir / (label + '.py')).write_bytes(data)
        extract = load(EXTRACTOR, 'igs_module_extract')
        helper = load(HELPER, 'igs_module_sync_helper')
        # Imported helper only supplies actual_declaration; its main/load_extractor never run.
        fragments = extract_input(args.clients, output / 'candidate-original', extract, helper, registry, True)
        driver = extract.Prepared(args.driver)
        registry.append(driver)
        response_enum = driver.structure('exports/nss_cmn.h', 'nss_cmn_response', 'enum')
        expected_enum = ('enum nss_cmn_response { NSS_CMN_RESPONSE_ACK, NSS_CMN_RESPONSE_EVERSION, '
                         'NSS_CMN_RESPONSE_EINTERFACE, NSS_CMN_RESPONSE_ELENGTH, NSS_CMN_RESPONSE_EMSG, '
                         'NSS_CMN_RESPONSE_NOTIFY, NSS_CMN_RESPONSE_LAST };')
        if normalized(response_enum, extract) != normalized(expected_enum, extract):
            raise ValueError('real response enum drift')
        (output / 'actual-response-enum.c').write_bytes(response_enum.encode())
        (output / 'input-nss_cmn.h').write_bytes(driver.read('exports/nss_cmn.h').encode())
        old = None
        if args.baseline:
            old = extract_input(args.baseline, output / 'baseline-original', extract, helper, registry, False)
            if any(fragments[key] != old[key] for key in (CLEANUP, 'nss_ifb_init', 'msg_response')):
                raise ValueError('baseline/candidate differ outside module init')
            # Exact bytes, including error-message literals and CPP envelopes:
            # permit only the observed 019 declaration split/comment/call move.
            before = exact_edit(old[INIT], '\tnss_ifb_init();\n\treturn 0;', '\treturn 0;')
            before = exact_edit(before, '\tint err = register_netdevice_notifier(',
                '\tint err;\n\n'
                '\t/* Initialize private synchronization before publishing any entry point. */\n'
                '\tnss_ifb_init();\n\terr = register_netdevice_notifier(')
            if before != fragments[INIT]:
                raise ValueError('module init differs beyond permitted relocation/declaration split')
            result['baseline_byte_comparison'] = {'cleanup_equal': True, 'ifb_init_equal': True,
                                                   'declaration_equal': True, 'only_exact_019_edit': True}
        selected_mutations = list(mutations(fragments)) if args.mutations else []
        for version, number in VERSIONS.items():
            result['variants'].append(execute(output, 'candidate-' + version, fragments,
                                               response_enum, number, args, 'candidate'))
            if old is not None:
                result['variants'].append(execute(output, 'baseline-' + version, old,
                                                   response_enum, number, args, 'baseline'))
            for name, changed, metadata in selected_mutations:
                if metadata['legacy_only'] and number >= (5, 4, 0):
                    continue
                result['variants'].append(execute(output, name + '-' + version, changed,
                                                   response_enum, number, args, 'mutation', metadata))
        comparisons = []
        for version, number in VERSIONS.items():
            candidate = next(row for row in result['variants'] if row['name'] == 'candidate-' + version)
            if old is not None:
                baseline = next(row for row in result['variants'] if row['name'] == 'baseline-' + version)
                for name in (CASES if number < (5, 4, 0) else CASES[:-1]):
                    a = candidate.get('observable_signatures', {}).get(name)
                    b = baseline.get('observable_signatures', {}).get(name)
                    comparisons.append({'version': version, 'case': name, 'candidate': a, 'baseline': b,
                                        'equal': a is not None and b is not None and a == b})
        result['observable_signature_comparison'] = comparisons
        expected_variants = 3 + (3 if old is not None else 0) + (22 if args.mutations else 0)
        if (len(result['variants']) == expected_variants and
                all(row['accepted'] for row in result['variants']) and
                all(row['equal'] for row in comparisons)):
            result['status'] = 'PASS_BOUNDED_HOST_MODEL_ONLY'
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        try:
            result['inputs'] = [prepared.manifest() for prepared in registry]
            for row in result['provenance'].values():
                if sha(Path(row['path']).read_bytes()) != row['sha256']:
                    raise ValueError('dependency changed during run: ' + row['path'])
        except Exception as error:
            result['status'] = 'FAIL'
            result['provenance_error'] = type(error).__name__ + ': ' + str(error)
        # Every generated source/evidence file has a content digest in the final inventory.
        result['artifacts'] = [{'path': str(path.relative_to(output)), 'bytes': path.stat().st_size,
                                'sha256': sha(path.read_bytes())}
                               for path in sorted(output.rglob('*')) if path.is_file()]
        write_json(output / 'RESULT.json', result)
    print(json.dumps({'status': result['status'], 'result': str(output / 'RESULT.json'), 'open': OPEN}))
    return 0 if result['status'] == 'PASS_BOUNDED_HOST_MODEL_ONLY' else 1


if __name__ == '__main__':
    sys.exit(main())
