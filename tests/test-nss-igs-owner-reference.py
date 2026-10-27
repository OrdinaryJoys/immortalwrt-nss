#!/usr/bin/env python3
"""Bounded, offline, real-source IGS owner-reference host regression.

Only main() compiles/runs C. This is not a scheduler, kernel ABI or callback
lifetime model. See NSS_IGS_OWNER_REFERENCE.md for the normal-unload premise.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types
import uuid


SCRIPT = Path(__file__).resolve()
HELPER = SCRIPT.parent / 'nss-dp-containment/extract_prepared_c.py'
PREFIX_NAME = 'nss_igs_module_'
KERNEL_PINS = {
    'try_module_get': '9cd753a2771f7e4769b5fc96e32d5d9bab7745022a3e0c4b2d4f7022d125ccb0',
    'module_put': 'cb6d1305e167d38aa8b20bcbe1adea7fd145b875dd651257ae0c2fdb435ced1f',
    'module_is_live': 'd3634f3b46d87208206fe4d0045e38b0145dd5c99780d451eaf80630a5355bd5',
}
# Fixture steps are shared; their expected outcomes come from Reference, not C.
PLANS = {
    'absent': [('get',), ('put',), ('put',), ('get',)],
    'irq-absent': [('irq', 1), ('get',), ('put',), ('put',)],
    'linux-null': [('linux',)],
    'coming': [('init', 1, 1, 1), ('save', 1), ('get',), ('put',)],
    'going': [('init', 1, 2, 1), ('save', 1), ('get',)],
    'refzero': [('init', 1, 0, 0), ('save', 1), ('get',)],
    'balanced-reload': [('init', 1, 0, 1), ('save', 1), ('get',), ('get',),
                        ('unload',), ('put',), ('put',), ('unload',), ('get',),
                        ('init', 2, 0, 1), ('save', 2), ('get',), ('put',), ('unload',)],
    'contend-get': [('init', 1, 0, 1), ('save', 1), ('arm', 1), ('get',),
                    ('put',), ('unload',)],
    'contend-put': [('irq', 1), ('init', 1, 0, 1), ('save', 1), ('get',),
                    ('arm', 2), ('put',), ('get',)],
}
OFF_CASES = ('absent', 'irq-absent', 'linux-null')
TARGETS = {
    'get-null': ('static.get.null_guard', 'absent', 'get.unpublished.false'),
    'put-null': ('static.put.null_guard', 'absent', 'put.null.no_kernel_call'),
    'save-lock': ('static.save.lock', 'coming', 'save.lock.balance'),
    'get-lock': ('static.get.lock', 'contend-get', 'get.entry.irq_lock'),
    'put-lock': ('static.put.lock', 'contend-put', 'put.entry.irq_lock'),
    'warn-hidden': ('static.put.warn_once_after_unlock', 'absent', 'put.null.warn_once'),
}
FIELDS = ('seq', 'case', 'event', 'owner', 'a', 'b', 'sa', 'sb', 'ha', 'hb',
          'depth', 'irq', 'locks', 'unlocks', 'pending', 'warnings', 'bugs', 'errors', 'result')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def capture(path):
    before = identity(path)
    data = path.read_bytes()
    if identity(path) != before or len(data) != before[2]:
        raise ValueError('input changed while reading: ' + str(path))
    return {'path': str(path), 'identity': before, 'sha256': digest(data), 'data': data}


def recheck(row):
    path = Path(row['path'])
    if identity(path) != row['identity'] or digest(path.read_bytes()) != row['sha256']:
        raise ValueError('input drift: ' + str(path))


def write(path, data):
    # Exclusive creation: no existing file, symlink or previous output is reused.
    with path.open('xb') as stream:
        stream.write(data.encode('utf-8') if isinstance(data, str) else data)


def write_json(path, value):
    write(path, json.dumps(value, indent=2, sort_keys=True) + '\n')


def tokens(text, helper):
    return re.findall(r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]', helper.code_mask(text))


def statement_tree(text, helper):
    """Small fail-closed reader for this contract's straight-line/if statements."""
    ts = tokens(text, helper)
    opening = ts.index('{')

    def block(pos):
        result = []
        while ts[pos] != '}':
            if ts[pos] == 'if':
                if ts[pos + 1] != '(':
                    raise ValueError('unsupported if')
                end = ts.index(')', pos + 2)
                condition = tuple(ts[pos + 2:end])
                if ts[end + 1] != '{':
                    raise ValueError('unbraced if outside bounded grammar')
                body, pos = block(end + 2)
                result.append(('if', condition, body))
            else:
                end = ts.index(';', pos)
                item = tuple(ts[pos:end])
                if any(t in item for t in ('{', '}', '#', 'else', 'goto', 'while', 'for')):
                    raise ValueError('unsupported statement')
                result.append(item)
                pos = end + 1
        return tuple(result), pos + 1

    body, end = block(opening + 1)
    if end != len(ts):
        raise ValueError('unexpected function tail')
    return tuple(ts[:opening]), body


def static_contract(parts, helper):
    """Exact bounded statement grammar, checked on code_mask, not comments.

    This is a structural specification, never compiled replacement function
    bodies. Unknown control flow/extra owner accesses fail closed as shape drift.
    Every access (including the guard read) must be inside the same irqsave pair.
    """
    failures = set()
    atom = lambda s: tuple(s.split())
    lock = atom('spin_lock_irqsave ( & nss_igs_module_lock , flags )')
    unlock = atom('spin_unlock_irqrestore ( & nss_igs_module_lock , flags )')
    decl = atom('unsigned long flags')
    signatures = {
        'save': atom('void nss_igs_module_save ( struct tc_action_ops * act , struct module * module )'),
        'get': atom('bool nss_igs_module_get ( void )'),
        'put': atom('void nss_igs_module_put ( void )'),
    }
    shapes = {
        'save': (decl, atom('nss_assert ( act )'), lock,
                 atom('nss_igs_module = module'), unlock),
        'get': (decl, atom('bool acquired = false'), lock,
                ('if', ('nss_igs_module',), (atom('acquired = try_module_get ( nss_igs_module )'),)),
                unlock, atom('return acquired')),
        'put': (decl, lock, ('if', ('!', 'nss_igs_module'),
                (unlock, atom('pr_warn_once ( )'), ('return',))),
                atom('module_put ( nss_igs_module )'), unlock),
    }
    if not parts['lock']:
        failures.add('static.declaration.lock')
    for name in ('save', 'get', 'put'):
        ts = tokens(parts[name], helper)
        # Calls must have the same lock and flags, not merely matching names.
        expected_unlocks = 2 if name == 'put' else 1
        occurrences = lambda needle: sum(tuple(ts[i:i + len(needle)]) == needle
                                         for i in range(len(ts)))
        if occurrences(lock) != 1 or occurrences(unlock) != expected_unlocks:
            failures.add('static.' + name + '.lock')
        try:
            signature, body = statement_tree(parts[name], helper)
            if signature != signatures[name]:
                failures.add('static.' + name + '.signature')
            if body != shapes[name]:
                failures.add('static.' + name + '.shape')
            if name == 'get' and shapes['get'][3] not in body:
                failures.add('static.get.null_guard')
            if name == 'put' and shapes['put'][2] not in body:
                failures.add('static.put.null_guard')
            if name == 'put' and not any(node == shapes['put'][2] for node in body):
                failures.add('static.put.warn_once_after_unlock')
        except (ValueError, IndexError):
            failures.add('static.' + name + '.shape')
            if name in ('get', 'put'):
                failures.add('static.' + name + '.null_guard')
    return sorted(failures)


def cpp_stack(mask, stop):
    """Unclosed real CPP gates at a definition; comments/literals are masked."""
    stack = []
    for match in re.finditer(r'^[ \t]*#[ \t]*(if|ifdef|ifndef|elif|else|endif)\b([^\n]*)\n?',
                             mask[:stop], re.M):
        kind, condition = match.group(1), match.group(2).strip()
        if kind in ('if', 'ifdef', 'ifndef'):
            stack.append((kind, condition, match.start(), match.end(), False))
        elif not stack:
            raise ValueError('unmatched CPP branch/end')
        elif kind == 'endif':
            stack.pop()
        else:
            stack[-1] = (*stack[-1][:4], True)
    return stack


def extract_driver(root, helper, directory, registry):
    prepared = helper.Prepared(root)
    registry.append(prepared)
    source = prepared.read('nss_igs.c')
    mask = helper.code_mask(source)
    parts = {name: prepared.function('nss_igs.c', PREFIX_NAME + name)
             for name in ('save', 'get', 'put')}
    for name, pattern, required in (
            ('owner', r'^static\s+struct\s+module\s*\*\s*nss_igs_module\s*;', True),
            ('lock', r'^static\s+DEFINE_SPINLOCK\s*\(\s*nss_igs_module_lock\s*\)\s*;', False)):
        matches = list(re.finditer(pattern, mask, re.M))
        if len(matches) != (1 if required else min(1, len(matches))):
            raise ValueError('ambiguous/missing declaration: ' + name)
        parts[name] = source[matches[0].start():matches[0].end()] + '\n' if matches else ''
    # Preserve the real save CPP gate; reject different/nested enclosing context.
    start = source.index(parts['save'].rstrip())
    gates = cpp_stack(mask, start)
    if len(gates) != 1 or gates[0][:2] != ('ifdef', 'CONFIG_NET_CLS_ACT') or gates[0][4]:
        raise ValueError('save must have exactly its direct, unbranched CONFIG_NET_CLS_ACT gate')
    gate = gates[0]
    prefix = mask[gate[3]:start]
    tail = mask[start + len(parts['save'].rstrip()):]
    if '#' in prefix or prefix.strip() or not re.match(
            r'\s*EXPORT_SYMBOL\s*\(\s*nss_igs_module_save\s*\)\s*;\s*#endif\b', tail):
        raise ValueError('save CPP enclosure drift')
    parts['save_gate'] = source[gate[2]:gate[3]]
    for name in ('get', 'put'):
        if cpp_stack(mask, source.index(parts[name].rstrip())):
            raise ValueError(name + ' acquired an unsupported enclosing CPP gate')
    core = prepared.read('nss_core.h')
    cm = helper.code_mask(core)
    starts = list(re.finditer(r'^#define nss_info_always\b', cm, re.M))
    ends = list(re.finditer(r'^#if \(NSS_PKT_STATS_ENABLED == 1\)', cm, re.M))
    if len(starts) != 1:
        raise ValueError('NSS debug macro enclosure drift')
    ends = [end for end in ends if end.start() > starts[0].start()]
    if not ends:
        raise ValueError('NSS debug macro end missing')
    parts['debug'] = core[starts[0].start():ends[0].start()]
    debug_mask = helper.code_mask(parts['debug'])
    if cpp_stack(debug_mask, len(debug_mask)):
        raise ValueError('NSS debug macro block is not self-contained')
    snapshot_prepared(prepared, directory)
    extracted = directory / 'extracted'
    extracted.mkdir()
    for name, data in parts.items():
        write(extracted / (name + '.c'), data)
    return parts


def snapshot_prepared(prepared, directory):
    directory.mkdir()
    for row in prepared.files.values():
        target = directory / 'input' / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        write(target, row['text'])
    write_json(directory / 'prepared-manifest.json', prepared.manifest())


def extract_kernel(root, helper, directory, registry):
    prepared = helper.Prepared(root)
    registry.append(prepared)
    parts = {}
    for name, relative in (('module_is_live', 'include/linux/module.h'),
                           ('try_module_get', 'kernel/module/main.c'),
                           ('module_put', 'kernel/module/main.c')):
        definition = prepared.function(relative, name)
        parts[name] = definition
    snapshot_prepared(prepared, directory)
    extracted = directory / 'extracted'
    extracted.mkdir()
    for name, definition in parts.items():
        write(extracted / (name + '.c'), definition)
        if digest(definition.encode()) != KERNEL_PINS[name]:
            raise ValueError('Linux 6.18.38 definition pin drift: ' + name)
    return parts


def edit_masked(text, pattern, replacement, helper, count=1):
    matches = list(re.finditer(pattern, helper.code_mask(text), re.M))
    if len(matches) != count:
        raise ValueError('mutation context drift: ' + pattern)
    for match in reversed(matches):
        text = text[:match.start()] + replacement + text[match.end():]
    return text


def mutation(original, name, helper):
    parts = dict(original)
    if name.endswith('-lock'):
        fn = name.split('-')[0]
        parts[fn] = edit_masked(parts[fn],
            r'spin_(?:lock_irqsave|unlock_irqrestore)\s*\([^;]+\)\s*;', '', helper,
            3 if fn == 'put' else 2)
        # The declaration becomes unused when the lock pair is removed.
        parts[fn] = edit_masked(parts[fn], r'unsigned long flags\s*;', '', helper)
    elif name in ('get-null', 'put-null'):
        fn = name.split('-')[0]
        text = parts[fn]
        matches = list(re.finditer(r'\bif\s*\(\s*' + ('!' if fn == 'put' else '') +
                                  r'\s*nss_igs_module\s*\)\s*\{', helper.code_mask(text)))
        if len(matches) != 1:
            raise ValueError('mutation NULL guard context drift')
        match = matches[0]
        end = helper.block_end(text, match.end() - 1)
        inner = text[match.end():end - 1] if fn == 'get' else ''
        parts[fn] = text[:match.start()] + inner + text[end:]
    elif name == 'warn-hidden':
        parts['put'] = edit_masked(parts['put'], r'\bpr_warn_once\b', 'nss_warning', helper)
    else:
        raise ValueError('unknown mutation')
    return parts


C_PREFIX = r'''
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Explicit host substitutes, NOT Linux ABI, atomicity or real IRQs. */
enum { MODULE_STATE_LIVE, MODULE_STATE_COMING, MODULE_STATE_GOING };
struct module { int state; int refcnt; int id; };
struct tc_action_ops { int opaque; };
typedef struct { int opaque; } spinlock_t;
#define DEFINE_SPINLOCK(n) spinlock_t n
#define likely(x) (x)
#define _RET_IP_ 0UL
static void emit(const char *, int);
static int atomic_inc_not_zero(int *);
static int atomic_dec_if_positive(int *);
static void trace_event(const char *, struct module *);
void record_bug(bool);
static void record_warn(bool);
void warn_once(void);
void lock_enter(void *, unsigned long *);
void lock_exit(void *, unsigned long);
static void hook(int);
#define trace_module_get(m, ip) trace_event("trace.get", (m))
#define trace_module_put(m, ip) trace_event("trace.put", (m))
#define WARN_ON(c) record_warn(!!(c))
/* BUG is recorded and continued ONLY as a model probe; not real BUG execution. */
#define BUG_ON(c) record_bug(!!(c))
#define pr_warn_once(...) warn_once()
#define spin_lock_irqsave(l, f) lock_enter((l), &(f))
#define spin_unlock_irqrestore(l, f) lock_exit((l), (f))
'''

C_WRAPPERS = r'''
#undef try_module_get
#undef module_put
bool try_module_get(struct module *module)
{
    bool ret;
    emit("try.enter", module ? module->id : 0);
    hook(1);
    ret = linux_try_module_get(module);
    emit("try.exit", ret);
    return ret;
}
void module_put(struct module *module)
{
    emit("put.enter", module ? module->id : 0);
    hook(2);
    linux_module_put(module);
    emit("put.exit", -1);
}
'''

C_MODEL = r'''
static struct module modules[2] = {{0, 0, 1}, {0, 0, 2}};
static int held[2], depth, locks, unlocks, pending, warnings, bugs, errors, armed, seq;
static unsigned long irq;
static void *active_lock;
static const char *case_name;
#ifdef CONFIG_NET_CLS_ACT
static struct tc_action_ops action;
#endif
static void request_unload(void);
static void emit(const char *event, int result)
{
    printf("{\"seq\":%d,\"case\":\"%s\",\"event\":\"%s\",\"owner\":%d,"
           "\"a\":%d,\"b\":%d,\"sa\":%d,\"sb\":%d,\"ha\":%d,\"hb\":%d,"
           "\"depth\":%d,\"irq\":%lu,\"locks\":%d,\"unlocks\":%d,\"pending\":%d,"
           "\"warnings\":%d,\"bugs\":%d,\"errors\":%d,\"result\":%d}\n",
           seq++, case_name, event, nss_igs_module ? nss_igs_module->id : 0,
           modules[0].refcnt, modules[1].refcnt, modules[0].state, modules[1].state,
           held[0], held[1], depth, irq, locks, unlocks, pending, warnings, bugs, errors, result);
}
void lock_enter(void *lock, unsigned long *flags)
{
    if (depth || lock != EXPECTED_LOCK) ++errors;
    *flags = irq; irq = 1; depth++; locks++; active_lock = lock;
    emit("lock", -1);
}
void lock_exit(void *lock, unsigned long flags)
{
    if (depth != 1 || lock != active_lock || !irq) ++errors;
    depth--; irq = flags; unlocks++;
    emit("unlock", -1);
    if (pending && !depth) {
        pending = 0;
        emit("contender.resume", -1);
        request_unload();
    }
}
static int atomic_inc_not_zero(int *ref)
{
    int ret = *ref != 0;
    if (ret) ++*ref;
    emit("atomic.inc", ret);
    return ret;
}
static int atomic_dec_if_positive(int *ref)
{
    int ret = *ref - 1;
    if (*ref > 0) --*ref;
    emit("atomic.dec", ret);
    return ret;
}
static void trace_event(const char *event, struct module *module)
{
    emit(event, module->id);
}
void record_bug(bool condition)
{
    if (condition) { ++bugs; emit("bug.recorded", -1); }
}
static void record_warn(bool condition)
{
    if (condition) { ++errors; emit("kernel.warn", -1); }
}
void warn_once(void)
{
    if (!warnings) { ++warnings; emit("warning.once", -1); }
}
static void publish(int id)
{
    emit("save.begin", id);
#ifdef CONFIG_NET_CLS_ACT
    nss_igs_module_save(&action, id ? &modules[id - 1] : NULL);
#else
    ++errors; /* No off-config publication bypass. This branch must not run. */
#endif
    emit("save.end", id);
}
static void request_unload(void)
{
    struct module *owner;
    if (depth) { pending = 1; emit("contender.defer", -1); return; }
    emit("contender.attempt", -1);
    owner = nss_igs_module;
    if (!owner) { emit("unload.absent", -1); return; }
    /* Premise: base ref=1; normal refs exclude normal unload, never force. */
    if (owner->refcnt != 1 || owner->state != MODULE_STATE_LIVE) {
        emit("unload.blocked", -1); return;
    }
    owner->state = MODULE_STATE_GOING;
    emit("unload.admit", -1);
    publish(0);
    owner->refcnt = 0;
    emit("unload.cleared", -1);
}
static void hook(int api)
{
    if (armed == api) { armed = 0; request_unload(); }
}
static void do_get(void)
{
    struct module *owner = nss_igs_module;
    bool ret;
    emit("get.begin", -1);
    ret = nss_igs_module_get();
    if (ret && owner) ++held[owner->id - 1];
    emit("get.end", ret);
}
static void do_put(void)
{
    struct module *owner = nss_igs_module;
    emit("release.begin", -1);
    nss_igs_module_put();
    if (owner && held[owner->id - 1] > 0) --held[owner->id - 1];
    emit("release.end", -1);
}
'''


def program(parts, kernel):
    chunks = [C_PREFIX, parts['debug'], parts['owner'], parts['lock']]
    chunks += ['#define EXPECTED_LOCK ' + ('(&nss_igs_module_lock)' if parts['lock'] else 'NULL') + '\n',
               '#define try_module_get linux_try_module_get\n#define module_put linux_module_put\n',
               kernel['module_is_live'], kernel['try_module_get'], kernel['module_put'], C_WRAPPERS,
               parts['save_gate'], parts['save'], '#endif\n', parts['get'], parts['put'], C_MODEL,
               'int main(int argc, char **argv) {\nif (argc != 2) return 64;\ncase_name = argv[1];\n']
    for case, steps in PLANS.items():
        if case not in OFF_CASES:
            chunks.append('#ifdef CONFIG_NET_CLS_ACT\n')
        chunks.append('if (!strcmp(case_name, "' + case + '")) {\n')
        for step in steps:
            op = step[0]
            if op == 'irq':
                chunks.append(f'irq = {step[1]}; emit("fixture.irq", -1);\n')
            elif op == 'init':
                index, state, refs = step[1] - 1, step[2], step[3]
                chunks.append(f'modules[{index}].state = {state}; modules[{index}].refcnt = {refs}; '
                              f'emit("fixture.module", {step[1]});\n')
            elif op == 'save':
                chunks.append(f'publish({step[1]});\n')
            elif op == 'arm':
                chunks.append(f'armed = {step[1]}; emit("fixture.arm", armed);\n')
            elif op == 'get':
                chunks.append('do_get();\n')
            elif op == 'put':
                chunks.append('do_put();\n')
            elif op == 'unload':
                chunks.append('request_unload();\n')
            elif op == 'linux':
                chunks.append('emit("linux.null.get", linux_try_module_get(NULL));\n'
                              'linux_module_put(NULL); emit("linux.null.put", -1);\n')
            else:
                raise ValueError('unknown fixture step')
        chunks.append('emit("done", -1); return errors ? 65 : 0; }\n')
        if case not in OFF_CASES:
            chunks.append('#endif\n')
    chunks.append('return 64; }\n')
    return '\n'.join(chunks)


class Reference:
    """Independent contract ledger: no extracted C is evaluated here."""
    def __init__(self, case, variant='candidate', debug=0):
        self.case = case
        self.variant, self.debug = variant, debug
        self.rows = []
        self.s = {key: 0 for key in FIELDS if key not in ('seq', 'case', 'event', 'result')}
        self.armed = 0

    def event(self, event, result=-1):
        self.rows.append(dict(self.s, seq=len(self.rows), case=self.case, event=event, result=result))

    def lock(self):
        old = self.s['irq']
        self.s.update(depth=1, irq=1, locks=self.s['locks'] + 1)
        self.event('lock')
        return old

    def unlock(self, old):
        self.s.update(depth=0, irq=old, unlocks=self.s['unlocks'] + 1)
        self.event('unlock')
        if self.s['pending']:
            self.s['pending'] = 0
            self.event('contender.resume')
            self.unload()

    def save(self, owner):
        self.event('save.begin', owner)
        locked = self.variant not in ('baseline', 'save-lock')
        old = self.lock() if locked else None
        self.s['owner'] = owner
        if locked:
            self.unlock(old)
        self.event('save.end', owner)

    def unload(self):
        if self.s['depth']:
            self.s['pending'] = 1
            self.event('contender.defer')
            return
        self.event('contender.attempt')
        owner = self.s['owner']
        if not owner:
            self.event('unload.absent')
        elif (self.s['a' if owner == 1 else 'b'] != 1 or
              self.s['sa' if owner == 1 else 'sb'] != 0):
            self.event('unload.blocked')
        else:
            ref, state = ('a', 'sa') if owner == 1 else ('b', 'sb')
            self.s[state] = 2
            self.event('unload.admit')
            self.save(0)
            self.s[ref] = 0
            self.event('unload.cleared')

    def api(self, put=False):
        self.event('release.begin' if put else 'get.begin')
        owner = self.s['owner']
        ref, state, hold = ('a', 'sa', 'ha') if owner == 1 else ('b', 'sb', 'hb')
        if self.variant == 'baseline' and self.debug and not owner:
            self.s['bugs'] += 1
            self.event('bug.recorded')
        locked = self.variant not in ('baseline', 'put-lock' if put else 'get-lock')
        old = self.lock() if locked else None
        success = False
        call_kernel = bool(owner) or self.variant in (
            'baseline', 'put-null' if put else 'get-null')
        if call_kernel:
            self.event('put.enter' if put else 'try.enter', owner)
            if self.armed == (2 if put else 1):
                self.armed = 0
                self.unload()
            if put:
                if owner:
                    self.s[ref] -= 1
                    self.event('atomic.dec', self.s[ref])
                    self.event('trace.put', owner)
                self.event('put.exit')
            else:
                if not owner:
                    success = True  # Real Linux NULL-module semantics.
                elif self.s[state] != 2:
                    success = self.s[ref] > 0
                    self.s[ref] += int(success)
                    self.event('atomic.inc', int(success))
                    if success:
                        self.event('trace.get', owner)
                self.event('try.exit', int(success))
        if locked:
            self.unlock(old)
        if put:
            if (not owner and not self.s['warnings'] and
                    self.variant not in ('baseline', 'put-null', 'warn-hidden')):
                self.s['warnings'] = 1
                self.event('warning.once')
            if owner:
                self.s[hold] -= 1
            self.event('release.end')
        else:
            if success and owner:
                self.s[hold] += 1
            self.event('get.end', int(success))

    def run(self):
        for step in PLANS[self.case]:
            op = step[0]
            if op == 'irq':
                self.s['irq'] = step[1]
                self.event('fixture.irq')
            elif op == 'init':
                ref, state = ('a', 'sa') if step[1] == 1 else ('b', 'sb')
                self.s[state], self.s[ref] = step[2:]
                self.event('fixture.module', step[1])
            elif op == 'save':
                self.save(step[1])
            elif op == 'arm':
                self.armed = step[1]
                self.event('fixture.arm', step[1])
            elif op in ('get', 'put'):
                self.api(op == 'put')
            elif op == 'unload':
                self.unload()
            elif op == 'linux':
                # The pinned real Linux functions, not the IGS NULL contract.
                self.event('linux.null.get', 1)
                self.event('linux.null.put')
        self.event('done')
        return self.rows


def oracle(rows, case, variant='candidate', debug=0):
    if not rows or len(rows) > 512:
        raise ValueError('empty/oversized JSON event ledger')
    failures = set()
    beginnings = {}
    allowed_events = {'bug.recorded', 'kernel.warn', 'unload.absent'} | {
        row['event'] for plan in PLANS for row in Reference(plan).run()}
    for index, row in enumerate(rows):
        if set(row) != set(FIELDS) or row['case'] != case or row['seq'] != index:
            raise ValueError('JSON schema/case/sequence mismatch')
        if not isinstance(row['event'], str) or any(type(row[k]) is not int for k in FIELDS
                                                   if k not in ('case', 'event')):
            raise ValueError('JSON event types mismatch')
        if row['event'] not in allowed_events:
            raise ValueError('unknown JSON event')
        if row['errors']:
            raise ValueError('host substitute invariant failure; never negative success')
        event = row['event']
        if event in ('get.begin', 'release.begin', 'save.begin'):
            beginnings[event.split('.')[0]] = row
        if event in ('try.enter', 'put.enter'):
            name = 'get' if event == 'try.enter' else 'put'
            if row['depth'] != 1 or row['irq'] != 1:
                failures.add(name + '.entry.irq_lock')
            if row['result'] == 0:
                failures.add(name + '.null.no_kernel_call')
        if event == 'warning.once' and row['depth']:
            failures.add('put.warning.after_unlock')
        if event in ('get.end', 'release.end', 'save.end'):
            stem = event.split('.')[0]
            start = beginnings[stem]
            name = 'put' if stem == 'release' else stem
            if (row['locks'] - start['locks'], row['unlocks'] - start['unlocks'], row['irq']) != (
                    1, 1, start['irq']):
                # A deferred unload may itself execute one save(NULL) pair.
                nested = event == 'release.end' and start['owner'] and not row['owner']
                if not (nested and (row['locks'] - start['locks'], row['unlocks'] - start['unlocks'],
                                    row['irq']) == (2, 2, start['irq'])):
                    failures.add(name + '.lock.balance')
            if event == 'get.end' and not start['owner'] and row['result'] != 0:
                failures.add('get.unpublished.false')
            if event == 'release.end' and not start['owner'] and row['warnings'] != 1:
                failures.add('put.null.warn_once')
    if rows[-1]['event'] != 'done':
        raise ValueError('missing final JSON event')
    expected = Reference(case).run()
    if rows != expected:
        failures.add('ledger.exact_contract')
    variant_expected = Reference(case, variant, debug).run()
    if rows != variant_expected:
        raise ValueError('variant event ledger mismatch: ' + variant + ':' + case)
    return {'assertions_failed': sorted(failures), 'events': len(rows),
            'expected_events': len(expected), 'expected_sha256': digest(json.dumps(expected, sort_keys=True).encode()),
            'variant_expected_sha256': digest(json.dumps(variant_expected, sort_keys=True).encode()),
            'variant_ledger_exact': True}


def oracle_negative_controls():
    """Reject unrelated deviations even after a negative's target is satisfied."""
    results = []
    for label in ('extra-bug', 'missing-trace', 'wrong-unrelated-ref'):
        rows = Reference('coming', 'get-null').run()
        if label == 'extra-bug':
            row = dict(rows[-1], event='bug.recorded')
            rows.insert(len(rows) - 1, row)
            for item in rows[-2:]:
                item['bugs'] += 1
        elif label == 'missing-trace':
            index = next(i for i, row in enumerate(rows) if row['event'] == 'trace.get')
            del rows[index]
        else:
            rows[-1]['b'] += 1
        for index, row in enumerate(rows):
            row['seq'] = index
        try:
            oracle(rows, 'coming', 'get-null')
        except ValueError as error:
            if 'variant event ledger mismatch' not in str(error):
                raise
            results.append({'name': label, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('unrelated negative deviation was accepted: ' + label)
    return results


class Runner:
    def __init__(self, output, registry, self_rows):
        self.output, self.registry, self.self_rows = output, registry, self_rows
        self.output_identity = identity(output)[:2]
        self.command_count = 0
        self.build_rows = []

    def check(self):
        if self.output.is_symlink() or identity(self.output)[:2] != self.output_identity:
            raise ValueError('output directory changed')
        for row in self.self_rows:
            recheck(row)
        for row in self.build_rows:
            recheck(row)
        return [prepared.manifest() for prepared in self.registry]

    def command(self, argv, kind, cwd):
        self.check()
        self.command_count += 1
        stem = self.output / ('command-%04d' % self.command_count)
        record = {'kind': kind, 'argv': [str(a) for a in argv], 'cwd': str(cwd),
                  'shell': False, 'timeout_seconds': 90 if kind == 'compile' else 20,
                  'status': 'started'}
        write_json(stem.with_suffix('.request.json'), record)
        env = dict(os.environ, LC_ALL='C')
        # Do not force detect_leaks: unsupported on some macOS ASan runtimes.
        try:
            result = subprocess.run(record['argv'], cwd=cwd, env=env, capture_output=True,
                                    timeout=record['timeout_seconds'], check=False)
            write(stem.with_suffix('.stdout'), result.stdout)
            write(stem.with_suffix('.stderr'), result.stderr)
            record.update(status='finished', returncode=result.returncode,
                          stdout_sha256=digest(result.stdout), stderr_sha256=digest(result.stderr))
            write_json(stem.with_suffix('.result.json'), record)
        except BaseException as error:
            if isinstance(error, subprocess.TimeoutExpired):
                write(stem.with_suffix('.stdout'), error.stdout or b'')
                write(stem.with_suffix('.stderr'), error.stderr or b'')
            write_json(stem.with_suffix('.exception.json'),
                       dict(record, status='exception', exception=type(error).__name__, message=str(error)))
            raise
        self.check()
        if result.returncode != 0:
            raise ValueError(kind + ' nonzero exit (not a negative pass): ' + str(stem))
        if kind == 'run' and result.stderr:
            raise ValueError('run stderr/sanitizer diagnostic (not a negative pass): ' + str(stem))
        return result.stdout


def output_directory(requested, roots):
    path = Path(requested).absolute() if requested else Path(tempfile.gettempdir()).resolve() / (
        'nss-igs-owner-' + uuid.uuid4().hex)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('output path may not contain symlinks: ' + str(parent))
    # Resolve .. only after the symlink check, then reject every input/source tree.
    path = path.resolve()
    if any(path == root or root in path.parents for root in roots):
        raise ValueError('output must be outside source/input trees')
    if not path.parent.is_dir():
        raise ValueError('output parent must already exist')
    path.mkdir(mode=0o700)  # No exist_ok: a previously used directory is forbidden.
    return path


def strict_json_lines(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return [json.loads(line, object_pairs_hook=pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            for line in data.decode('utf-8').splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('driver', type=Path)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--cc', default='cc', help='one executable, no shell or compiler arguments')
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = None
    try:
        compiler = shutil.which(args.cc)
        if not compiler or args.cc.startswith('-'):
            raise ValueError('--cc must name one executable (not a shell command)')
        roots = [args.driver.resolve(strict=True), args.kernel.resolve(strict=True),
                 SCRIPT.parent.parent.resolve()]
        if args.baseline:
            roots.append(args.baseline.resolve(strict=True))
        output = output_directory(args.output, roots)
        self_rows = [capture(SCRIPT), capture(HELPER)]
        provenance = output / 'runner-inputs'
        provenance.mkdir()
        for row in self_rows:
            write(provenance / Path(row['path']).name, row['data'])
        write_json(provenance / 'manifest.json',
                   [{k: row[k] for k in ('path', 'identity', 'sha256')} for row in self_rows])
        helper = types.ModuleType('owner_prepared_extractor')
        ast.parse(self_rows[1]['data'], filename=str(HELPER))
        # Load the exact snapshotted shared helper without writing __pycache__.
        exec(compile(self_rows[1]['data'], str(HELPER), 'exec'), helper.__dict__)
        registry = []
        runner = Runner(output, registry, self_rows)
        parts = extract_driver(roots[0], helper, output / 'candidate-inputs', registry)
        kernel = extract_kernel(roots[1], helper, output / 'kernel-inputs', registry)
        candidate_static = static_contract(parts, helper)
        write_json(output / 'candidate-static.json', candidate_static)
        if candidate_static:
            raise ValueError('candidate static contract rejected: ' + repr(candidate_static))
        variants = {'candidate': parts}
        if args.baseline:
            variants['baseline'] = extract_driver(roots[-1], helper, output / 'baseline-inputs', registry)
        if args.mutations:
            variants.update({name: mutation(parts, name, helper) for name in TARGETS})
        write_json(output / 'INPUTS.json', {'prepared': runner.check(),
                   'runner_inputs': [{k: row[k] for k in ('path', 'identity', 'sha256')} for row in self_rows]})
        report = {'status': 'running', 'compiler': str(Path(compiler).resolve()),
                  'sanitize': args.sanitize, 'matrix': [], 'static_decoys': [],
                  'oracle_negative_controls': oracle_negative_controls(),
                  'kernel_definition_pins': KERNEL_PINS,
                  'scope': 'CONFIG_MODULE_UNLOAD; current obj-m; normal balanced refs only'}
        if args.mutations:
            for fn in ('save', 'get', 'put'):
                broken = mutation(parts, fn + '-lock', helper)
                decoy = dict(broken)
                decoy[fn] += ('/* spin_lock_irqsave(&nss_igs_module_lock, flags); '
                              'spin_unlock_irqrestore(&nss_igs_module_lock, flags); '
                              'if (nss_igs_module) {} pr_warn_once("decoy"); */\n')
                failures = static_contract(decoy, helper)
                label = 'static.' + fn + '.lock'
                if label not in failures:
                    raise ValueError('comment decoy escaped code_mask static oracle')
                report['static_decoys'].append({'function': fn, 'required': label, 'failed': failures})
        write_json(output / 'static-decoys.json', report['static_decoys'])
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        for variant, fragments in variants.items():
            static = static_contract(fragments, helper)
            write_json(output / (variant + '-static-contract.json'), static)
            if variant in TARGETS and TARGETS[variant][0] not in static:
                raise ValueError('mutation missed designated static assert: ' + variant)
            if variant == 'baseline' and not {'static.get.lock', 'static.put.lock',
                                               'static.save.lock'}.issubset(static):
                raise ValueError('baseline is not the expected unlocked negative source')
            for enabled in (False, True):
                for debug in (0, 1):
                    directory = output / (variant + '-act%d-debug%d' % (enabled, debug))
                    directory.mkdir()
                    source, binary = directory / 'host.c', directory / 'host'
                    write(source, program(fragments, kernel))
                    config = ['-DNSS_DEBUG_LEVEL=' + str(debug)]
                    if enabled:
                        config.append('-DCONFIG_NET_CLS_ACT=1')
                    # Real CPP: the save gate and unmodified debug macros select branches.
                    runner.command([compiler, *flags, *config, source, '-o', binary], 'compile', directory)
                    runner.build_rows = [capture(source), capture(binary)]
                    write_json(directory / 'build-manifest.json',
                               [{k: row[k] for k in ('path', 'identity', 'sha256')} for row in runner.build_rows])
                    results = {}
                    for case in (PLANS if enabled else OFF_CASES):
                        raw = runner.command([binary, case], 'run', directory)
                        try:
                            rows = strict_json_lines(raw)
                            result = oracle(rows, case, variant, debug)
                            write_json(directory / (case + '.events.json'), rows)
                            write_json(directory / (case + '.oracle.json'), result)
                        except BaseException as error:
                            write_json(directory / (case + '.json-exception.json'),
                                       {'exception': type(error).__name__, 'message': str(error)})
                            raise
                        results[case] = result
                    if variant == 'candidate':
                        if any(row['assertions_failed'] for row in results.values()):
                            raise ValueError('candidate runtime contract failed: ' + str(directory))
                    elif variant == 'baseline':
                        required = [('absent', 'get.unpublished.false'), ('absent', 'put.null.no_kernel_call')]
                        if enabled:
                            required += [('contend-get', 'get.entry.irq_lock'), ('contend-put', 'put.entry.irq_lock')]
                        for case, label in required:
                            if label not in results[case]['assertions_failed']:
                                raise ValueError('baseline missed designated assert: ' + label)
                    else:
                        _, case, label = TARGETS[variant]
                        if case in results and label not in results[case]['assertions_failed']:
                            raise ValueError('mutation missed designated runtime assert: ' + variant + ':' + label)
                        # A save/get/put lock negative needs an on-config contender.
                        # Off cases are still compiled/run, not counted as detections.
                    report['matrix'].append({'variant': variant, 'net_cls_act': enabled,
                                             'debug': debug, 'static_failed': static, 'cases': results})
                    runner.check()
        report.update(status='pass', commands=runner.command_count, prepared=runner.check(),
                      runner_inputs=[{k: row[k] for k in ('path', 'identity', 'sha256')} for row in self_rows])
        write_json(output / 'RESULT.json', report)
        runner.check()
        print(str(output / 'RESULT.json'))
        return 0
    except BaseException as error:
        if output is not None:
            try:
                write_json(output / 'FAILURE.json', {'status': 'fail', 'exception': type(error).__name__,
                                                    'message': str(error)})
            except BaseException as logging_error:
                print('failure logging also failed: ' + repr(logging_error), file=sys.stderr)
        print('FAIL CLOSED: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
