#!/usr/bin/env python3
"""Offline actual-source IGS sync control-flow regression, not kernel concurrency.

Only the runner invoked by the owner compiles/runs generated host C. No network,
device, firmware, kernel, RTNL, threads, or archived executable helpers are used.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


HERE = Path(__file__).resolve().parent
EXTRACTOR = HERE / 'nss-dp-containment/extract_prepared_c.py'
SOURCE = 'nss_qdisc/igs/nss_ifb.c'
HEADER = 'nss_qdisc/igs/nss_ifb.h'
FUNCTIONS = ('nss_ifb_init', 'nss_ifb_wake_up_cb', 'nss_ifb_config_msg_tx_sync')
OPEN = ('S01', 'S03', 'S05', 'S06', 'S08-same-pair-late-ACK-association',
        'PBUF', 'SQM', 'callback/app_data-lifetime')
ADAPTATIONS = [
    'Three whole actual function definitions and static msg_response declaration '
    'are byte-preserved, including comments; no function-body adaptation in normal runs.',
    'Actual config enum and timeout define retained; HZ=100 in model; no real time elapses.',
    'Reduced net_device/message/context, symbolic response/status/type values: not NSS ABI. '
    'cm.interface and cm.type have real envelope semantics; request_id is diagnostic only.',
    'config_msg_fill is a named bool-return model, not actual fill: only sync control '
    'flow for both SET_IGS_NODE and SET_NEXTHOP consumers is exercised. Actual fill is archived as context only. '
    'Original 495-interface model remains a separate parent-owned regression.',
    'Semaphore, completion counter, irqsave lock ownership/pairing, TX and callback '
    'schedules are explicit deterministic single-thread substitutes, not kernel '
    'concurrency, IRQ, memory-ordering or barrier proofs. Baseline is real 017 completion.',
    'TX_RETURN_EDGE is inside an API wrapper after modeled TX returns, before the '
    'caller assigns ret. WAIT_ENTRY is after the status branch, before wait evaluation. '
    'No source-instruction hook or actual firmware timing is claimed.',
    'Completion wait consumes one model token; reply oracle uses only active state, '
    'interface/type and response < NOTIFY, never host-only request_id for admission.',
    'nss_igs_error forwards to a variadic no-output model; arguments are evaluated.',
    '-Wno-unused-parameter only suppresses unused parameters (notably actual callback '
    'app_data); -Wall -Wextra -Werror otherwise retained. No body edits to silence warnings.',
    'Mutation runs alone deliberately alter one or two exact unique source contexts; '
    'each original/replacement and hash is recorded separately from unmodified runs.',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load_extractor():
    # Do not write into the extractor's directory when imported by the runner.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('igs_sync_extract', EXTRACTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def actual_declaration(prepared, extract):
    """Extend the shared lexical reader for a struct-with-instance declaration."""
    text = prepared.read(SOURCE)
    masked = extract.code_mask(text)
    matches = list(re.finditer(
        r'^static[ \t]+struct[ \t]+nss_ifb_msg_response\b[ \t\r\n]*\{', masked, re.M))
    if len(matches) != 1:
        raise ValueError('expected unique static struct nss_ifb_msg_response definition')
    match = matches[0]
    end = extract.block_end(text, match.end() - 1)
    tail = re.match(r'[ \t\r\n]+msg_response\b[ \t\r\n]*;', masked[end:])
    if tail is None:
        raise ValueError('expected exact msg_response instance after struct body')
    fragment = text[match.start():end + tail.end()] + '\n'
    prepared.extracted.append({'source': SOURCE, 'variable': 'msg_response',
                               'bytes': len(fragment.encode()),
                               'sha256': digest(fragment.encode()),
                               'reader': 'code_mask + block_end + strict instance tail'})
    return fragment


def extract_input(root, directory, extract, candidate, registry):
    prepared = extract.Prepared(root)
    registry.append(prepared)
    declaration = actual_declaration(prepared, extract)
    fragments = {name: prepared.function(SOURCE, name) for name in FUNCTIONS}
    fragments['msg_response'] = declaration
    fragments['nss_ifb_config_msg_fill.context-only'] = prepared.function(
        SOURCE, 'nss_ifb_config_msg_fill')
    fragments['nss_ifb_if_config'] = prepared.structure(HEADER, 'nss_ifb_if_config', 'enum')
    header = prepared.read(HEADER)
    masked = extract.code_mask(header)
    matches = list(re.finditer(r'^#define[ \t]+NSS_IFB_MSG_TIMEOUT\b[^\n]*', masked, re.M))
    if len(matches) != 1:
        raise ValueError('expected one timeout define')
    match = matches[0]
    if not re.fullmatch(r'#define[ \t]+NSS_IFB_MSG_TIMEOUT[ \t]+\(600\s*\*\s*HZ\)[ \t\r]*',
                        match.group()):
        raise ValueError('timeout expression is not unchanged 600*HZ')
    fragments['NSS_IFB_MSG_TIMEOUT'] = header[match.start():match.end()] + '\n'
    prepared.extracted.append({'source': HEADER, 'define': 'NSS_IFB_MSG_TIMEOUT',
                               'bytes': len(fragments['NSS_IFB_MSG_TIMEOUT'].encode()),
                               'sha256': digest(fragments['NSS_IFB_MSG_TIMEOUT'].encode())})
    fields = extract.code_mask(declaration)
    expected = (r'static\s+struct\s+nss_ifb_msg_response\s*\{\s*'
                r'struct\s+semaphore\s+sem\s*;\s*' +
                r'struct\s+completion\s+done\s*;\s*' +
                (r'spinlock_t\s+lock\s*;\s*' if candidate else '') +
                r'enum\s+nss_cmn_response\s+response\s*;\s*' +
                (r'uint32_t\s+expected_interface\s*;\s*'
                 r'uint32_t\s+expected_type\s*;\s*'
                 r'bool\s+pending\s*;\s*' if candidate else '') +
                r'\}\s+msg_response\s*;\s*')
    if not re.fullmatch(expected, fields):
        raise ValueError('unexpected real msg_response field layout')
    directory.mkdir()
    for name, value in fragments.items():
        (directory / (name + '.c')).write_text(value, encoding='utf-8')
    return prepared, fragments


PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define HZ 100
/* Model symbols only, not extracted NSS/kernel types or numeric ABI. */
enum nss_cmn_response { NSS_CMN_RESPONSE_ACK, NSS_CMN_RESPONSE_EVERSION,
    NSS_CMN_RESPONSE_EINTERFACE, NSS_CMN_RESPONSE_ELENGTH, NSS_CMN_RESPONSE_EMSG,
    NSS_CMN_RESPONSE_NOTIFY, NSS_CMN_RESPONSE_LAST };
#define MODEL_INVALID_RESPONSE ((enum nss_cmn_response)19)
enum { NSS_IF_SET_IGS_NODE = 11, NSS_IF_SET_NEXTHOP = 23 };
enum { NSS_TX_SUCCESS = 0, MODEL_TX_FAILURE = 1, MODEL_TX_QUEUE = 2,
       MODEL_TX_NOT_READY = 3, MODEL_TX_OTHER = 17 };
struct semaphore { int count; bool initialized; };
struct completion { unsigned tokens; bool initialized; };
typedef struct { bool initialized, held; unsigned long cookie; } spinlock_t;
struct net_device { int model_only; };
struct nss_if_msg {
    struct { enum nss_cmn_response response; uint32_t interface, type; } cm;
    void (*callback)(void *, struct nss_if_msg *);
    void *app_data;
    unsigned request_id;
};
enum point { NONE, TX_BEFORE_RETURN, TX_RETURN_EDGE, WAIT_ENTRY, WAIT_DURING };
static void nss_ifb_wake_up_cb(void *, struct nss_if_msg *);
static const char *case_name;
static unsigned checks, failures, case_checks, case_failures, case_count;
static unsigned txs, waits, downs, ups, received, timeouts, callbacks;
static unsigned sem_inits, done_inits, lock_inits, resets, fills, completes;
static unsigned locks, unlocks, accepted, ignored, expected_accepts, expected_ignores;
static unsigned next_id, last_reply_id, repeats, call_number;
static unsigned selected_config, selected_source;
static int tx_status;
static bool fill_failure, fired, use_old, following_match, second_terminal;
static bool oracle_pending;
static enum point schedule;
static enum nss_cmn_response response;
static enum nss_cmn_response following_response;
static struct nss_if_msg current_message, old_message;
static uint64_t signature;
static void check(bool ok, const char *label)
{
    ++checks; ++case_checks;
    if (!ok) {
        ++failures; ++case_failures;
        printf("{\"type\":\"failure\",\"case\":\"%s\",\"check\":\"%s\"}\n",
               case_name, label);
    }
}
static void mix(unsigned value)
{
    signature ^= value;
    signature *= UINT64_C(1099511628211);
}
void model_error(const char *format, ...) { (void)format; }
#define nss_igs_error(...) model_error(__VA_ARGS__)
'''


MODELS = r'''
/* Explicit synchronous substitutes; held/flags only observe modeled ownership. */
#if MODEL_REPLY_GUARD
void spin_lock_init(spinlock_t *lock)
{
    ++lock_inits; lock->initialized = true; lock->held = false; lock->cookie = 0;
}
unsigned long model_lock(spinlock_t *lock)
{
    ++locks;
    check(lock == &msg_response.lock && lock->initialized, "lock_initialized_before_use");
    check(!lock->held, "lock_not_recursive"); lock->held = true;
    lock->cookie = 0x1aUL + locks;
    return lock->cookie;
}
void model_unlock(spinlock_t *lock, unsigned long flags)
{
    ++unlocks;
    check(lock == &msg_response.lock && lock->held, "unlock_owned");
    check(flags == lock->cookie, "irqsave_restore_pair"); lock->held = false;
}
#define spin_lock_irqsave(lock, flags) do { (flags) = model_lock(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) model_unlock((lock), (flags))
#endif
void sema_init(struct semaphore *sem, int count)
{
    ++sem_inits; sem->count = count; sem->initialized = true;
}
void down(struct semaphore *sem)
{
    ++downs;
    check(sem->initialized && sem->count == 1, "down_available");
    --sem->count;
}
void up(struct semaphore *sem)
{
#if MODEL_REPLY_GUARD
    check(!msg_response.lock.held, "up_outside_guard_lock");
    check(!msg_response.pending, "retired_before_up");
#endif
    ++ups; check(sem->initialized && sem->count == 0, "up_owned"); ++sem->count;
}
void init_completion(struct completion *done)
{
    ++done_inits; done->initialized = true; done->tokens = 0;
}
void reinit_completion(struct completion *done)
{
    ++resets;
    check(msg_response.sem.count == 0, "reinit_under_sem");
#if MODEL_REPLY_GUARD
    check(msg_response.lock.held, "reinit_under_guard_lock");
#endif
    check(done->initialized, "reinit_initialized"); done->tokens = 0;
}
void complete(struct completion *done)
{
#if MODEL_REPLY_GUARD
    check(msg_response.lock.held, "complete_under_guard_lock");
    check(!msg_response.pending, "complete_after_pending_claim");
#endif
    ++completes;
    check(done->initialized, "complete_initialized"); ++done->tokens;
}
void deliver(struct nss_if_msg message)
{
    unsigned before_tokens = msg_response.done.tokens, before_completes = completes;
    unsigned before_locks = locks, before_unlocks = unlocks;
    enum nss_cmn_response before_response = msg_response.response;
    int pending_before = -1, pending_after = -1, held_after = -1;
#if MODEL_REPLY_GUARD
    bool before_pending = msg_response.pending;
    pending_before = before_pending;
#endif
    ++callbacks; last_reply_id = message.request_id;
    message.cm.response = response;
    bool admit = oracle_pending && message.cm.interface == current_message.cm.interface &&
        message.cm.type == current_message.cm.type && response < NSS_CMN_RESPONSE_NOTIFY;
    if (admit) { ++expected_accepts; oracle_pending = false; }
    else ++expected_ignores;
    check(message.callback == nss_ifb_wake_up_cb, "modeled_callback_route");
    if (message.callback) message.callback(message.app_data, &message);
#if MODEL_REPLY_GUARD
    pending_after = msg_response.pending; held_after = msg_response.lock.held;
#endif
    bool completed = completes != before_completes;
    if (completed) ++accepted;
    else if (msg_response.done.tokens == before_tokens &&
             msg_response.response == before_response) ++ignored;
    if (admit) {
        check(completes == before_completes + 1 &&
              msg_response.done.tokens == before_tokens + 1, "accepted_one_completion");
        check(msg_response.response == response, "accepted_response");
#if MODEL_REPLY_GUARD
        check(!msg_response.pending, "accepted_claims_pending");
#endif
    } else {
        check(completes == before_completes && msg_response.done.tokens == before_tokens,
              "ignored_no_completion");
        check(msg_response.response == before_response, "ignored_preserves_response");
#if MODEL_REPLY_GUARD
        check(msg_response.pending == before_pending, "ignored_preserves_pending");
#endif
    }
#if MODEL_REPLY_GUARD
    check(locks == before_locks + 1 && unlocks == before_unlocks + 1 &&
          !msg_response.lock.held, "callback_lock_pair");
#endif
    if (!oracle_pending && !admit)
        check(msg_response.done.tokens == before_tokens, "inactive_no_token");
    printf("{\"type\":\"reply\",\"case\":\"%s\",\"reply\":%u,\"request_id\":%u,"
           "\"interface\":%u,\"message_type\":%u,\"response\":%u,\"expected_admit\":%s,"
           "\"observed_complete\":%s,\"tokens_before\":%u,\"tokens_after\":%u,"
           "\"response_before\":%u,\"response_after\":%u,\"locks\":%u,\"unlocks\":%u,"
           "\"pending_before\":%d,\"pending_after\":%d,\"lock_held_after\":%d}\n",
           case_name, callbacks, message.request_id, message.cm.interface, message.cm.type,
           (unsigned)response, admit ? "true" : "false", completed ? "true" : "false",
           before_tokens, msg_response.done.tokens, (unsigned)before_response,
           (unsigned)msg_response.response, locks-before_locks, unlocks-before_unlocks,
           pending_before, pending_after, held_after);
}
void inject(enum point point)
{
    if (schedule != point || fired) return;
    fired = true;
    for (unsigned i = 0; i < repeats; ++i)
        deliver(use_old ? old_message : current_message);
    if (following_match || second_terminal) {
        response = following_response;
        deliver(current_message);
    }
}
void *nss_igs_get_context(void) { return &txs; }
int model_tx(void *ctx, struct nss_if_msg *message)
{
    ++txs;
    check(ctx == &txs && msg_response.sem.count == 0, "tx_under_sem");
#if MODEL_REPLY_GUARD
    check(!msg_response.lock.held, "tx_outside_guard_lock");
    check(msg_response.pending, "pending_before_tx");
    check(msg_response.expected_interface == message->cm.interface &&
          msg_response.expected_type == message->cm.type, "envelope_before_tx");
    check(msg_response.response == NSS_CMN_RESPONSE_LAST, "default_last_before_tx");
#endif
    current_message = *message;
    oracle_pending = true;
    inject(TX_BEFORE_RETURN);
    return tx_status;
}
int model_tx_boundary(void *ctx, struct nss_if_msg *message)
{
    int status = model_tx(ctx, message);
    inject(TX_RETURN_EDGE);
    return status;
}
#define nss_if_tx_msg(ctx, message) model_tx_boundary((ctx), (message))
bool nss_ifb_config_msg_fill(struct nss_if_msg *message, struct net_device *dev,
                            int32_t ifb_num, enum nss_ifb_if_config config, void *cb)
{
    ++fills;
    check(dev != NULL && ifb_num == 42 && config == selected_config &&
          (config == NSS_IFB_SET_IGS_NODE || config == NSS_IFB_SET_NEXTHOP),
          "fill_model_inputs");
    if (fill_failure) return true;
    memset(message, 0, sizeof(*message));
    message->callback = nss_ifb_wake_up_cb;
    message->app_data = cb; message->request_id = ++next_id;
    message->cm.interface = selected_source;
    message->cm.type = config == NSS_IFB_SET_IGS_NODE ?
        NSS_IF_SET_IGS_NODE : NSS_IF_SET_NEXTHOP;
    return false;
}
void model_wait_begin(unsigned long timeout)
{
    ++waits;
    check(timeout == 600UL * HZ, "timeout_600_HZ");
    check(msg_response.sem.count == 0, "wait_under_sem");
#if MODEL_REPLY_GUARD
    check(!msg_response.lock.held, "wait_outside_guard_lock");
#endif
    inject(WAIT_ENTRY);
}
unsigned long model_wait_finish(bool ready)
{
    if (ready) ++received; else ++timeouts;
    return ready ? 1UL : 0UL;
}
unsigned long model_completion_wait(struct completion *done, unsigned long timeout)
{
    model_wait_begin(timeout);
    check(done->initialized, "wait_initialized");
    if (!done->tokens) inject(WAIT_DURING);
    bool ready = done->tokens != 0;
    if (ready) --done->tokens;
    return model_wait_finish(ready);
}
#define wait_for_completion_timeout(done, timeout) model_completion_wait((done), (timeout))
'''


MAIN = r'''
static void plan(enum point point, enum nss_cmn_response reply)
{
    schedule = point; response = reply; fired = false; repeats = 1;
    tx_status = NSS_TX_SUCCESS; fill_failure = false; use_old = false;
    following_match = second_terminal = false;
}
static void begin_case(const char *name)
{
    case_name = name; case_checks = case_failures = call_number = 0;
    signature = UINT64_C(1469598103934665603);
    memset(&msg_response, 0, sizeof(msg_response));
    memset(&current_message, 0, sizeof(current_message));
    memset(&old_message, 0, sizeof(old_message));
    txs = waits = downs = ups = received = timeouts = callbacks = 0;
    sem_inits = done_inits = lock_inits = resets = fills = completes = 0;
    locks = unlocks = accepted = ignored = expected_accepts = expected_ignores = 0;
    oracle_pending = false;
    next_id = last_reply_id = 0;
    selected_config = NSS_IFB_SET_IGS_NODE;
    selected_source = 77;
    plan(NONE, NSS_CMN_RESPONSE_ACK);
#if MODEL_REPLY_GUARD
    /* A nonzero pre-init sentinel checks explicit pending initialization. */
    msg_response.pending = true;
#endif
    nss_ifb_init();
}
static void end_case(bool open)
{
    ++case_count;
    printf("{\"type\":\"case\",\"case\":\"%s\",\"checks\":%u,\"failures\":%u,"
           "\"signature\":\"%016llx\",\"calls\":%u,\"replies\":%u,"
           "\"accepted\":%u,\"ignored\":%u,\"expected_accepts\":%u,\"expected_ignores\":%u,"
           "\"locks\":%u,\"unlocks\":%u,\"open\":%s,\"verdict\":\"%s\"}\n",
           case_name, case_checks, case_failures, (unsigned long long)signature,
           call_number, callbacks, accepted, ignored, expected_accepts, expected_ignores,
           locks, unlocks, open ? "true" : "false",
           open ? "OPEN_DIAGNOSTIC" : case_failures ? "FAIL" : "PASS");
}
static void request(int expected_return, unsigned expected_tx, unsigned expected_wait,
                    unsigned expected_received, unsigned expected_timeouts,
                    unsigned expected_callbacks)
{
    static struct net_device dev;
    unsigned t = txs, w = waits, d = downs, u = ups, r = received;
    unsigned o = timeouts, c = callbacks, f = fills;
    unsigned a = accepted, i = ignored, ea = expected_accepts, ei = expected_ignores;
    unsigned l = locks, ul = unlocks;
    int pending_after = -1, held_after = -1;
    int actual = nss_ifb_config_msg_tx_sync(&dev, 42,
                         (enum nss_ifb_if_config)selected_config, &dev);
    oracle_pending = false;
    ++call_number;
    check(actual == expected_return, "return");
    check(fills - f == 1, "fill_once");
    check(txs - t == expected_tx, "tx_count");
    check(waits - w == expected_wait, "wait_count");
    check(received - r == expected_received, "wait_consumed");
    check(timeouts - o == expected_timeouts, "timeouts");
    check(callbacks - c == expected_callbacks, "callback_count");
    check(accepted - a == expected_accepts - ea, "accepted_count");
    check(ignored - i == expected_ignores - ei, "ignored_count");
    check(downs - d == expected_tx && ups - u == expected_tx &&
          msg_response.sem.count == 1, "sem_balance");
#if MODEL_REPLY_GUARD
    pending_after = msg_response.pending; held_after = msg_response.lock.held;
    check(!msg_response.pending, "pending_false_on_return");
    check(!msg_response.lock.held && locks-l == unlocks-ul, "request_lock_balance");
#endif
    mix((unsigned)actual); mix(txs - t); mix(waits - w); mix(received - r);
    mix(timeouts - o); mix(callbacks - c); mix(downs - d); mix(ups - u);
    printf("{\"type\":\"call\",\"case\":\"%s\",\"call\":%u,\"return\":%d,"
           "\"expected_return\":%d,\"tx\":%u,\"wait\":%u,\"received\":%u,"
           "\"timeouts\":%u,\"callbacks\":%u,\"last_reply_id\":%u,"
           "\"current_request_id\":%u,\"accepted\":%u,\"ignored\":%u,"
           "\"expected_accepts\":%u,\"expected_ignores\":%u,\"locks\":%u,\"unlocks\":%u,"
           "\"pending_after\":%d,\"lock_held_after\":%d}\n",
           case_name, call_number, actual,
           expected_return, txs-t, waits-w, received-r, timeouts-o, callbacks-c,
           last_reply_id, current_message.request_id, accepted-a, ignored-i,
           expected_accepts-ea, expected_ignores-ei, locks-l, unlocks-ul, pending_after, held_after);
}
static void reply_case(const char *name, enum point point, enum nss_cmn_response reply)
{
    begin_case(name); plan(point, reply);
    request(reply == NSS_CMN_RESPONSE_ACK ? 0 : -1, 1, 1, 1, 0, 1);
    check(msg_response.response == reply, "stored_response");
    end_case(false);
}
static void nexthop_case(const char *name, enum point point, enum nss_cmn_response reply)
{
    begin_case(name); selected_config = NSS_IFB_SET_NEXTHOP; plan(point, reply);
    request(reply == NSS_CMN_RESPONSE_ACK ? 0 : -1, 1, 1, 1, 0, 1);
    check(msg_response.response == reply, "stored_response");
    end_case(false);
}
static void stale_pair_case(const char *name, bool wrong_type, bool wrong_interface,
                            enum nss_cmn_response stale_response, bool matching,
                            enum nss_cmn_response matching_response)
{
    begin_case(name); request(-1, 1, 1, 0, 1, 0);
    old_message = current_message;
    if (wrong_type) selected_config = NSS_IFB_SET_NEXTHOP;
    if (wrong_interface) selected_source = 88;
    plan(WAIT_DURING, stale_response); use_old = true;
    following_match = matching; following_response = matching_response;
    request(matching && matching_response == NSS_CMN_RESPONSE_ACK ? 0 : -1,
            1, 1, matching ? 1 : 0, matching ? 0 : 1, matching ? 2 : 1);
    end_case(false);
}
static void rejected_response_case(const char *name, enum nss_cmn_response rejected,
                                   bool matching, enum nss_cmn_response reply)
{
    begin_case(name); plan(WAIT_DURING, rejected);
    following_match = matching; following_response = reply;
    request(matching && reply == NSS_CMN_RESPONSE_ACK ? 0 : -1,
            1, 1, matching ? 1 : 0, matching ? 0 : 1, matching ? 2 : 1);
    end_case(false);
}
static void retired_case(const char *name, enum nss_cmn_response terminal)
{
    begin_case(name); plan(WAIT_DURING, terminal);
    request(terminal == NSS_CMN_RESPONSE_ACK ? 0 : -1, 1, 1, 1, 0, 1);
    response = terminal == NSS_CMN_RESPONSE_ACK ? NSS_CMN_RESPONSE_EMSG : NSS_CMN_RESPONSE_ACK;
    deliver(current_message);
    check(msg_response.response == terminal, "retired_reply_preserves_terminal");
    end_case(false);
}
static void first_terminal_case(const char *name, enum nss_cmn_response first,
                                enum nss_cmn_response second)
{
    begin_case(name); plan(WAIT_DURING, first);
    second_terminal = true; following_response = second;
    request(first == NSS_CMN_RESPONSE_ACK ? 0 : -1, 1, 1, 1, 0, 2);
    check(msg_response.response == first, "first_terminal_response");
    end_case(false);
}
static void tx_failure_late_case(const char *name, bool matching)
{
    begin_case(name); tx_status = MODEL_TX_FAILURE;
    request(-1, 1, 0, 0, 0, 0);
    response = NSS_CMN_RESPONSE_ACK; deliver(current_message);
    check(msg_response.response == NSS_CMN_RESPONSE_LAST, "failed_tx_reply_ignored");
    plan(matching ? WAIT_DURING : NONE, NSS_CMN_RESPONSE_ACK);
    request(matching ? 0 : -1, 1, 1, matching ? 1 : 0, matching ? 0 : 1, matching ? 1 : 0);
    end_case(false);
}
int main(void)
{
    begin_case("init");
    check(sem_inits == 1 && msg_response.sem.initialized &&
          msg_response.sem.count == 1, "semaphore_initialized");
    check(done_inits == 1 && msg_response.done.initialized &&
          msg_response.done.tokens == 0 && resets == 0, "completion_initialized");
#if MODEL_REPLY_GUARD
    check(lock_inits == 1 && msg_response.lock.initialized &&
          !msg_response.lock.held, "lock_initialized");
    check(!msg_response.pending, "pending_initialized_false");
#endif
    end_case(false);
    reply_case("ack_tx_before_return", TX_BEFORE_RETURN, NSS_CMN_RESPONSE_ACK);
    reply_case("nack_tx_before_return", TX_BEFORE_RETURN, NSS_CMN_RESPONSE_EMSG);
    reply_case("ack_tx_return_edge", TX_RETURN_EDGE, NSS_CMN_RESPONSE_ACK);
    reply_case("nack_tx_return_edge", TX_RETURN_EDGE, NSS_CMN_RESPONSE_EMSG);
    reply_case("ack_wait_entry", WAIT_ENTRY, NSS_CMN_RESPONSE_ACK);
    reply_case("nack_wait_entry", WAIT_ENTRY, NSS_CMN_RESPONSE_EMSG);
    reply_case("ack_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_ACK);
    reply_case("nack_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_EMSG);
    nexthop_case("ack_nexthop_tx_before_return", TX_BEFORE_RETURN, NSS_CMN_RESPONSE_ACK);
    nexthop_case("nack_nexthop_tx_before_return", TX_BEFORE_RETURN, NSS_CMN_RESPONSE_EMSG);
    nexthop_case("ack_nexthop_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_ACK);
    nexthop_case("nack_nexthop_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_EMSG);
    begin_case("timeout"); request(-1, 1, 1, 0, 1, 0); end_case(false);
    begin_case("fill_failure"); fill_failure = true;
    request(-1, 0, 0, 0, 0, 0); end_case(false);
    static const int statuses[] = {
        MODEL_TX_FAILURE, MODEL_TX_QUEUE, MODEL_TX_NOT_READY, MODEL_TX_OTHER
    };
    static const char *names[] = {
        "tx_failure_1", "tx_failure_2", "tx_failure_3", "tx_failure_17"
    };
    for (unsigned i = 0; i < sizeof(statuses)/sizeof(statuses[0]); ++i) {
        begin_case(names[i]); tx_status = statuses[i];
        request(-1, 1, 0, 0, 0, 0); end_case(false);
    }
    begin_case("tx_failure_then_success"); tx_status = MODEL_TX_QUEUE;
    request(-1, 1, 0, 0, 0, 0);
    plan(WAIT_DURING, NSS_CMN_RESPONSE_ACK);
    request(0, 1, 1, 1, 0, 1); end_case(false);
    begin_case("nack_then_success"); plan(WAIT_DURING, NSS_CMN_RESPONSE_EMSG);
    request(-1, 1, 1, 1, 0, 1); plan(WAIT_DURING, NSS_CMN_RESPONSE_ACK);
    request(0, 1, 1, 1, 0, 1); end_case(false);
    begin_case("timeout_late_before_reinit"); request(-1, 1, 1, 0, 1, 0);
    deliver(current_message); /* Late A reply before B resets; B has no reply. */
    plan(NONE, NSS_CMN_RESPONSE_ACK);
    request(-1, 1, 1, 0, 1, 0); end_case(false);
    begin_case("duplicate_ack_next_timeout"); plan(WAIT_DURING, NSS_CMN_RESPONSE_ACK);
    repeats = 2; request(0, 1, 1, 1, 0, 2);
    plan(NONE, NSS_CMN_RESPONSE_ACK); request(-1, 1, 1, 0, 1, 0); end_case(false);
    begin_case("late_ack_misattribution_OPEN"); request(-1, 1, 1, 0, 1, 0);
    old_message = current_message;
    plan(WAIT_DURING, NSS_CMN_RESPONSE_ACK); use_old = true;
    /* Deliberately EXPECT the unsafe observed success: a diagnostic, not a fix gate. */
    request(0, 1, 1, 1, 0, 1);
    check(last_reply_id == old_message.request_id &&
          last_reply_id != current_message.request_id, "OPEN_old_ACK_satisfied_new_request");
    check(old_message.cm.interface == current_message.cm.interface &&
          old_message.cm.type == current_message.cm.type, "OPEN_same_envelope_without_identity");
    end_case(true);
    stale_pair_case("stale_wrong_type_ack_only", true, false, NSS_CMN_RESPONSE_ACK, false, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_type_nack_only", true, false, NSS_CMN_RESPONSE_EMSG, false, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_interface_ack_only", false, true, NSS_CMN_RESPONSE_ACK, false, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_interface_nack_only", false, true, NSS_CMN_RESPONSE_EMSG, false, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_both_ack_only", true, true, NSS_CMN_RESPONSE_ACK, false, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_both_nack_only", true, true, NSS_CMN_RESPONSE_EMSG, false, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("notify_only", NSS_CMN_RESPONSE_NOTIFY, false, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("notify_then_matching_ack", NSS_CMN_RESPONSE_NOTIFY, true, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("notify_then_matching_nack", NSS_CMN_RESPONSE_NOTIFY, true, NSS_CMN_RESPONSE_EMSG);
    begin_case("isolated_inactive_reply");
    current_message.callback = nss_ifb_wake_up_cb;
    current_message.cm.interface = selected_source;
    current_message.cm.type = NSS_IF_SET_IGS_NODE;
    response = NSS_CMN_RESPONSE_EMSG; deliver(current_message); end_case(false);
    retired_case("retired_after_ack", NSS_CMN_RESPONSE_ACK);
    retired_case("retired_after_nack", NSS_CMN_RESPONSE_EMSG);
    first_terminal_case("ack_then_nack_first_only", NSS_CMN_RESPONSE_ACK, NSS_CMN_RESPONSE_EMSG);
    first_terminal_case("nack_then_ack_first_only", NSS_CMN_RESPONSE_EMSG, NSS_CMN_RESPONSE_ACK);
    tx_failure_late_case("tx_failure_late_then_success", true);
    tx_failure_late_case("tx_failure_late_then_timeout", false);
    begin_case("tx_failure_inline_ack_then_timeout"); plan(TX_BEFORE_RETURN, NSS_CMN_RESPONSE_ACK);
    tx_status = MODEL_TX_FAILURE; request(-1, 1, 0, 0, 0, 1);
    plan(NONE, NSS_CMN_RESPONSE_ACK); request(-1, 1, 1, 0, 1, 0); end_case(false);
    stale_pair_case("stale_wrong_type_then_matching_ack", true, false, NSS_CMN_RESPONSE_EMSG, true, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_type_then_matching_nack", true, false, NSS_CMN_RESPONSE_ACK, true, NSS_CMN_RESPONSE_EMSG);
    stale_pair_case("stale_wrong_interface_then_matching_ack", false, true, NSS_CMN_RESPONSE_EMSG, true, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_interface_then_matching_nack", false, true, NSS_CMN_RESPONSE_ACK, true, NSS_CMN_RESPONSE_EMSG);
    stale_pair_case("stale_wrong_both_then_matching_ack", true, true, NSS_CMN_RESPONSE_EMSG, true, NSS_CMN_RESPONSE_ACK);
    stale_pair_case("stale_wrong_both_then_matching_nack", true, true, NSS_CMN_RESPONSE_ACK, true, NSS_CMN_RESPONSE_EMSG);
    reply_case("eversion_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_EVERSION);
    reply_case("einterface_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_EINTERFACE);
    reply_case("elength_wait_during", WAIT_DURING, NSS_CMN_RESPONSE_ELENGTH);
    rejected_response_case("last_only", NSS_CMN_RESPONSE_LAST, false, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("last_then_matching_ack", NSS_CMN_RESPONSE_LAST, true, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("last_then_matching_nack", NSS_CMN_RESPONSE_LAST, true, NSS_CMN_RESPONSE_EMSG);
    rejected_response_case("invalid_high_only", MODEL_INVALID_RESPONSE, false, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("invalid_high_then_matching_ack", MODEL_INVALID_RESPONSE, true, NSS_CMN_RESPONSE_ACK);
    rejected_response_case("invalid_high_then_matching_nack", MODEL_INVALID_RESPONSE, true, NSS_CMN_RESPONSE_EMSG);
    printf("{\"type\":\"summary\",\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",
           case_count, checks, failures);
    return failures ? 1 : 0;
}
'''


CASE_NAMES = (
    'init', 'ack_tx_before_return', 'nack_tx_before_return', 'ack_tx_return_edge',
    'nack_tx_return_edge', 'ack_wait_entry', 'nack_wait_entry', 'ack_wait_during',
    'nack_wait_during', 'ack_nexthop_tx_before_return', 'nack_nexthop_tx_before_return',
    'ack_nexthop_wait_during', 'nack_nexthop_wait_during',
    'timeout', 'fill_failure', 'tx_failure_1', 'tx_failure_2',
    'tx_failure_3', 'tx_failure_17', 'tx_failure_then_success', 'nack_then_success',
    'timeout_late_before_reinit', 'duplicate_ack_next_timeout',
    'late_ack_misattribution_OPEN',
    'stale_wrong_type_ack_only', 'stale_wrong_type_nack_only',
    'stale_wrong_interface_ack_only', 'stale_wrong_interface_nack_only',
    'stale_wrong_both_ack_only', 'stale_wrong_both_nack_only',
    'notify_only', 'notify_then_matching_ack', 'notify_then_matching_nack',
    'isolated_inactive_reply', 'retired_after_ack', 'retired_after_nack',
    'ack_then_nack_first_only', 'nack_then_ack_first_only',
    'tx_failure_late_then_success', 'tx_failure_late_then_timeout',
    'tx_failure_inline_ack_then_timeout',
    'stale_wrong_type_then_matching_ack', 'stale_wrong_type_then_matching_nack',
    'stale_wrong_interface_then_matching_ack', 'stale_wrong_interface_then_matching_nack',
    'stale_wrong_both_then_matching_ack', 'stale_wrong_both_then_matching_nack',
    'eversion_wait_during', 'einterface_wait_during', 'elength_wait_during',
    'last_only', 'last_then_matching_ack', 'last_then_matching_nack',
    'invalid_high_only', 'invalid_high_then_matching_ack', 'invalid_high_then_matching_nack',
)
CALL_COUNTS = {name: (0 if name in ('init', 'isolated_inactive_reply') else 2 if name in (
    'tx_failure_then_success', 'nack_then_success', 'timeout_late_before_reinit',
    'duplicate_ack_next_timeout', 'late_ack_misattribution_OPEN',
    'tx_failure_late_then_success', 'tx_failure_late_then_timeout',
    'tx_failure_inline_ack_then_timeout') or name.startswith('stale_wrong_') else 1)
    for name in CASE_NAMES}
GUARD_SENSITIVE = tuple(name for name in CASE_NAMES if name.startswith('stale_wrong_')) + (
    'notify_only', 'notify_then_matching_ack', 'notify_then_matching_nack',
    'isolated_inactive_reply', 'retired_after_ack', 'retired_after_nack',
    'ack_then_nack_first_only', 'nack_then_ack_first_only',
    'tx_failure_late_then_success', 'tx_failure_late_then_timeout',
    'last_only', 'last_then_matching_ack', 'last_then_matching_nack',
    'invalid_high_only', 'invalid_high_then_matching_ack', 'invalid_high_then_matching_nack',
)
NORMAL_SIGNATURES = (
    'ack_tx_before_return', 'nack_tx_before_return', 'ack_tx_return_edge',
    'nack_tx_return_edge', 'ack_wait_entry', 'nack_wait_entry', 'ack_wait_during',
    'nack_wait_during', 'ack_nexthop_tx_before_return', 'nack_nexthop_tx_before_return',
    'ack_nexthop_wait_during', 'nack_nexthop_wait_during',
    'eversion_wait_during', 'einterface_wait_during', 'elength_wait_during',
)


def generated(fragments, candidate):
    return (PREFIX + '\n#define MODEL_REPLY_GUARD ' + str(int(candidate)) + '\n' +
            fragments['nss_ifb_if_config'] + fragments['NSS_IFB_MSG_TIMEOUT'] +
            fragments['msg_response'] + MODELS +
            ''.join(fragments[name] for name in FUNCTIONS) + MAIN)


def mutate(fragments, name, edits, extract):
    changed = dict(fragments)
    records = []
    for function, before, after in edits:
        body = changed[function]
        if body.count(before) != 1:
            raise ValueError(name + ': mutation context must match exactly once in ' + function)
        offset = body.index(before) + len(before) - len(before.lstrip())
        if extract.code_mask(body)[offset] != body[offset]:
            raise ValueError(name + ': mutation starts inside a comment or literal')
        changed[function] = body.replace(before, after, 1)
        records.append({'function': function, 'before': before, 'after': after,
                        'before_sha256': digest(body.encode()),
                        'after_sha256': digest(changed[function].encode()),
                        'matches': 1})
    return changed, records


def mutations():
    sync, wake, init = FUNCTIONS[2], FUNCTIONS[1], FUNCTIONS[0]
    reset = '\treinit_completion(&msg_response.done);\n'
    tx = '\tret = nss_if_tx_msg(nss_igs_get_context(), &nim);\n'
    timeout_tail = ('\t\tnss_igs_error("config for attach interface msg timeout\\n");\n'
                    '\t\tret = -1;\n')
    nack_tail = ('\t\tnss_igs_error("config for attach interface msg return with response: '
                 '%d\\n", response);\n\t\tret = -1;')
    notify = 'nim->cm.response >= NSS_CMN_RESPONSE_NOTIFY'
    claim = '\tmsg_response.pending = false;\n'
    complete_unlock = ('\tcomplete(&msg_response.done);\n'
                       '\tspin_unlock_irqrestore(&msg_response.lock, flags);\n')
    return [
        ('M01_no_reinit', 'tx_failure_inline_ack_then_timeout', 'wait_consumed',
         [(sync, reset, '')]),
        ('M02_reinit_after_send', 'ack_tx_before_return', 'return',
         [(sync, reset, ''), (sync, tx, tx + reset)]),
        ('M03_no_complete', 'ack_wait_during', 'return',
         [(wake, '\tcomplete(&msg_response.done);\n', '')]),
        ('M04_force_ACK', 'nack_wait_during', 'return',
         [(wake, '\tmsg_response.response = nim->cm.response;\n',
           '\tmsg_response.response = NSS_CMN_RESPONSE_ACK;\n')]),
        ('M05_timeout_success', 'timeout', 'return',
         [(sync, timeout_tail, timeout_tail.replace(
             'ret = -1;', 'up(&msg_response.sem);\n\t\treturn 0;'))]),
        ('M06_TX_failure_sem_leak', 'tx_failure_1', 'sem_balance',
         [(sync, '\tup(&msg_response.sem);\n', '')]),
        ('M07_no_init_completion', 'init', 'completion_initialized',
         [(init, '\tinit_completion(&msg_response.done);\n', '')]),
        ('M08_NACK_success', 'nack_wait_during', 'return',
         [(sync, nack_tail, nack_tail.replace('ret = -1;', 'ret = 0;'))]),
        ('M09_no_interface_check', 'stale_wrong_interface_ack_only', 'ignored_no_completion',
         [(wake, '\t\t\tnim->cm.interface != msg_response.expected_interface ||\n', '')]),
        ('M10_no_type_check', 'stale_wrong_type_ack_only', 'ignored_no_completion',
         [(wake, '\t\t\tnim->cm.type != msg_response.expected_type ||\n', '')]),
        ('M11_no_response_bound', 'notify_only', 'ignored_no_completion',
         [(wake, notify, 'false')]),
        ('M12_no_pending_check', 'retired_after_ack', 'ignored_no_completion',
         [(wake, '!msg_response.pending', 'false')]),
        ('M13_callback_no_claim', 'ack_then_nack_first_only', 'ignored_no_completion',
         [(wake, claim, '')]),
        ('M14_sender_no_retire', 'timeout', 'pending_false_on_return', [(sync, claim, '')]),
        ('M15_complete_outside_lock', 'ack_wait_during', 'complete_under_guard_lock',
         [(wake, complete_unlock,
           '\tspin_unlock_irqrestore(&msg_response.lock, flags);\n'
           '\tcomplete(&msg_response.done);\n')]),
        ('M16_pending_after_TX', 'ack_tx_before_return', 'pending_before_tx',
         [(sync, '\tmsg_response.pending = true;\n', ''),
          (sync, tx, tx + '\tmsg_response.pending = true;\n')]),
        ('M17_no_lock_init', 'init', 'lock_initialized',
         [(init, '\tspin_lock_init(&msg_response.lock);\n', '')]),
        ('M18_NOTIFY_equality_only', 'last_only', 'ignored_no_completion',
         [(wake, notify, 'nim->cm.response == NSS_CMN_RESPONSE_NOTIFY')]),
    ]


def command(directory, label, argv, timeout, env=None):
    write_json(directory / (label + '.command.json'), argv)
    (directory / (label + '.command.txt')).write_text(shlex.join(argv) + '\n', encoding='utf-8')
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, env=env, check=False)
        stdout, stderr = result.stdout, result.stderr
        row = {'argv': argv, 'returncode': result.returncode, 'timeout': False}
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
        row[stream + '_sha256'] = digest(data)
    write_json(directory / (label + '.result.json'), row)
    return row, stdout.decode('utf-8', errors='strict'), stderr.decode('utf-8', errors='replace')


def parse_summary(stdout):
    rows = [json.loads(line) for line in stdout.splitlines()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError('missing/invalid JSON output')
    if any(row.get('type') not in ('case', 'call', 'reply', 'failure', 'summary') for row in rows):
        raise ValueError('unknown output row')
    cases = [row for row in rows if row['type'] == 'case']
    summaries = [row for row in rows if row['type'] == 'summary']
    if [row['case'] for row in cases] != list(CASE_NAMES):
        raise ValueError('missing, duplicate, reordered, or unexpected cases')
    if len(summaries) != 1 or rows[-1] is not summaries[0]:
        raise ValueError('missing/duplicate/nonfinal summary')
    total = summaries[0]
    failed = [row for row in rows if row['type'] == 'failure']
    calls = [row for row in rows if row['type'] == 'call']
    replies = [row for row in rows if row['type'] == 'reply']
    if (total['cases'] != len(CASE_NAMES) or
            total['checks'] != sum(row['checks'] for row in cases) or
            total['failures'] != sum(row['failures'] for row in cases) or
            total['failures'] != len(failed)):
        raise ValueError('inconsistent totals')
    if any(row.get('case') not in CASE_NAMES for row in calls + replies + failed):
        raise ValueError('unknown case in detail records')
    for row in cases:
        name = row['case']
        selected = [call for call in calls if call['case'] == name]
        delivered = [reply for reply in replies if reply['case'] == name]
        if (row['calls'] != CALL_COUNTS[name] or
                [call['call'] for call in selected] != list(range(1, CALL_COUNTS[name] + 1)) or
                row['replies'] != len(delivered) or
                [reply['reply'] for reply in delivered] != list(range(1, len(delivered) + 1)) or
                row['accepted'] != sum(reply['observed_complete'] for reply in delivered) or
                row['ignored'] != sum(not reply['observed_complete'] and
                                      reply['tokens_before'] == reply['tokens_after'] and
                                      reply['response_before'] == reply['response_after']
                                      for reply in delivered) or
                row['expected_accepts'] != sum(reply['expected_admit'] for reply in delivered) or
                row['expected_ignores'] != sum(not reply['expected_admit'] for reply in delivered) or
                sum(call['callbacks'] for call in selected) > len(delivered) or
                row['failures'] != sum(item['case'] == name for item in failed) or
                row['checks'] <= 0 or
                row['open'] != (name == 'late_ack_misattribution_OPEN') or
                row['verdict'] != ('OPEN_DIAGNOSTIC' if row['open'] else
                                   'FAIL' if row['failures'] else 'PASS') or
                not re.fullmatch('[0-9a-f]{16}', row['signature'])):
            raise ValueError('incomplete case details: ' + name)
    return {'cases': cases, 'calls': calls, 'replies': replies,
            'assertion_failures': failed, 'summary': total}


def execute_variant(output, name, fragments, candidate, args, mutation=None):
    directory = output / name
    directory.mkdir()
    code = generated(fragments, candidate)
    source = directory / 'generated.c'
    source.write_text(code, encoding='utf-8')
    row = {'name': name, 'generated_c': str(source), 'sha256': digest(code.encode()),
           'mutation': mutation, 'model_reply_guard': candidate, 'accepted': False}
    flags = ['-std=gnu11', '-O0', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-parameter']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                  '-fno-sanitize-recover=all']
    binary = directory / 'host-regression'
    compiled, _, _ = command(directory, 'compile', [args.cc, *flags, str(source), '-o', str(binary)], 120)
    row['compile'] = compiled
    if compiled['returncode'] != 0 or compiled['timeout']:
        row['error'] = 'compilation failed; never a successful negative control'
        return row
    env = os.environ.copy()
    if args.sanitize:
        env['ASAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    row['sanitizer_environment'] = {key: env.get(key) for key in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')}
    run, stdout, stderr = command(directory, 'run', [str(binary)], 30, env)
    row['run'] = run
    if run['returncode'] not in (0, 1) or run['timeout'] or stderr:
        row['error'] = 'abnormal run, stderr, timeout, signal or sanitizer is not assertion evidence'
        return row
    try:
        row.update(parse_summary(stdout))
    except (ValueError, KeyError, TypeError) as error:
        row['error'] = 'incomplete/invalid case summary: ' + str(error)
        return row
    failures = row['summary']['failures']
    row['open_diagnostics'] = [dict(item, repair_pass=False)
                               for item in row['cases'] if item['open']]
    if run['returncode'] != int(failures != 0):
        row['error'] = 'exit code and explicit assertions disagree'
        return row
    if mutation:
        row['accepted'] = run['returncode'] == 1 and any(
            item['case'] == mutation['sensitive_case'] and item['check'] == mutation['sensitive_check']
            for item in row['assertion_failures'])
        if not row['accepted']:
            row['error'] = 'negative control missed designated behavioral assertion'
    elif candidate:
        row['accepted'] = run['returncode'] == 0 and failures == 0
    else:
        sensitive = set(GUARD_SENSITIVE) | {
            'timeout_late_before_reinit', 'duplicate_ack_next_timeout'}
        by_name = {item['case']: item for item in row['cases']}
        row['accepted'] = (run['returncode'] == 1 and
                           all(by_name[name]['failures'] > 0 for name in sensitive) and
                           all(item['failures'] == 0 for item in row['cases']
                               if item['case'] not in sensitive) and
                           all(any(item['case'] == name and item['check'] == 'ignored_no_completion'
                                   for item in row['assertion_failures']) for name in GUARD_SENSITIVE))
        row['role'] = '017 completion: expected reply-admission diagnostic, NOT candidate qualification'
        row['required_guard_failures'] = list(GUARD_SENSITIVE)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clients', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='new directory; existing paths rejected')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.absolute()
    if os.path.lexists(output):
        parser.error('--output must not already exist (including symlinks)')
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 2, 'status': 'FAIL', 'scope': 'offline deterministic host control-flow only',
              'open': list(OPEN), 'adaptations': ADAPTATIONS,
              'qualification': '018 bounded reply envelope control flow only; NOT full shutdown/FW safety',
              'source_roles': {'candidate': '018 guarded completion (v3)',
                               'baseline': '017 completion without reply guard'},
              'case_inventory': [{'case': name, 'expected_calls': CALL_COUNTS[name]}
                                 for name in CASE_NAMES],
              'arguments': vars(args) | {'clients': str(args.clients), 'output': str(output),
                                         'baseline': str(args.baseline) if args.baseline else None},
              'provenance': {}, 'variants': [], 'inputs': []}
    prepared_inputs = []
    try:
        for label, path in [('script', Path(__file__).resolve()), ('extractor', EXTRACTOR)]:
            data = path.read_bytes()
            result['provenance'][label] = {'path': str(path), 'sha256': digest(data), 'bytes': len(data)}
        extract = load_extractor()
        _, fragments = extract_input(args.clients, output / 'candidate-original', extract,
                                     True, prepared_inputs)
        normal = execute_variant(output, 'candidate', fragments, True, args)
        result['variants'].append(normal)
        if args.baseline:
            _, old = extract_input(args.baseline, output / 'baseline-original', extract,
                                   False, prepared_inputs)
            before = execute_variant(output, 'baseline', old, False, args)
            result['variants'].append(before)
            a = {row['case']: row for row in normal.get('cases', [])}
            b = {row['case']: row for row in before.get('cases', [])}
            result['normal_signature_comparison'] = [
                {'case': name, 'candidate': a.get(name, {}).get('signature'),
                 'baseline': b.get(name, {}).get('signature'),
                 'equal': name in a and name in b and a[name]['signature'] == b[name]['signature']}
                for name in NORMAL_SIGNATURES]
            result['late_normal_signature_comparison'] = [
                row for row in result['normal_signature_comparison'] if row['case'] in (
                    'ack_wait_entry', 'nack_wait_entry', 'ack_wait_during', 'nack_wait_during',
                    'ack_nexthop_wait_during', 'nack_nexthop_wait_during')]
        if args.mutations:
            for name, sensitive_case, sensitive_check, edits in mutations():
                modified, records = mutate(fragments, name, edits, extract)
                metadata = {'sensitive_case': sensitive_case, 'sensitive_check': sensitive_check,
                            'edits': records, 'requires': 'compile rc=0, run rc=1, complete JSON, designated assertion'}
                result['variants'].append(execute_variant(output, name, modified, True, args, metadata))
        signatures_ok = all(row['equal'] for row in result.get('normal_signature_comparison', []))
        if all(row['accepted'] for row in result['variants']) and signatures_ok:
            result['status'] = 'PASS_CONTROL_FLOW_ONLY'
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        result['status'] = 'FAIL'
    finally:
        try:
            result['inputs'] = [prepared.manifest() for prepared in prepared_inputs]
            for row in result['provenance'].values():
                if digest(Path(row['path']).read_bytes()) != row['sha256']:
                    raise ValueError('script/extractor changed during run: ' + row['path'])
        except Exception as error:
            result['status'] = 'FAIL'
            result['provenance_error'] = type(error).__name__ + ': ' + str(error)
        write_json(output / 'RESULT.json', result)
    print(json.dumps({'status': result['status'], 'result': str(output / 'RESULT.json'), 'open': list(OPEN)}))
    return 0 if result['status'] == 'PASS_CONTROL_FLOW_ONLY' else 1


if __name__ == '__main__':
    sys.exit(main())
