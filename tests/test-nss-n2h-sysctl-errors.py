#!/usr/bin/env python3
"""Actual extra-pbuf handlers/readiness helper; parser, logging and NSS are models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared', type=Path)
p.add_argument('--baseline', type=Path)
p.add_argument('--cc', default='cc')
p.add_argument('--sanitize', action='store_true')
p.add_argument('--mutations', action='store_true')
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
prepared = extract.Prepared(args.prepared)
source = prepared.read('nss_n2h.c')
header = prepared.read('exports/nss_cmn.h')
core_header = prepared.read('nss_core.h')
core_state = prepared.structure('nss_core.h', 'nss_core_state', kind='enum')
ctx_definition = prepared.structure('nss_core.h', 'nss_ctx_instance')
ctx_fields = ''
for name in ('dev', 'state', 'buf_sz_allocated', 'magic'):
    matches = list(re.finditer(r'^[ \t]*[A-Za-z_][A-Za-z_0-9 \t*]*\b' + name + r'\s*;',
                               extract.code_mask(ctx_definition), re.M))
    if len(matches) != 1:
        raise ValueError('context field: ' + name)
    ctx_fields += ctx_definition[matches[0].start():matches[0].end()] + '\n'
ctx_model = 'struct nss_ctx_instance {\n' + ctx_fields + '};\n'
magic = re.findall(r'^#define NSS_CTX_MAGIC[^\n]+', core_header, re.M)
if len(magic) != 1:
    raise ValueError('NSS_CTX_MAGIC')
ready_helper = prepared.function('nss_stats.c', 'nss_sysctl_ctx_ready')
enums = ''
for name in ('nss_tx_status_t', 'nss_core_id_t'):
    matches = re.findall(r'typedef enum\s*\{[^{}]*\}\s*' + name + ';', header)
    if len(matches) != 1:
        raise ValueError(name)
    enums += matches[0] + '\n'
maximum = re.findall(r'^#define NSS_N2H_MAX_BUF_POOL_SIZE[^\n]+', source, re.M)
assert len(maximum) == 1

def functions(text):
    return ''.join(extract.function(text, 'nss_n2h_buf_cfg_core%d_handler' % core) for core in (0, 1))

body = functions(source)
prefix = r'''
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <limits.h>
typedef long long loff_t;
#define __user
'''
models = ctx_model + r'''
struct ctl_table {void *data;};
struct nss_top_instance {struct nss_ctx_instance nss[NSS_CORE_MAX];};
static struct nss_top_instance nss_top_main;
static int nss_n2h_core0_add_buf_pool_size, nss_n2h_core1_add_buf_pool_size;
static int parse_result, backend_status, backend_allocated, expected_core, requested;
static unsigned checks, failures, calls, success_logs, failure_logs, cases;
static unsigned parser_calls, log_calls, ctx_reads, helper_cases, helper_failures;
static unsigned cold_cases[NSS_CORE_MAX], cold_failures[NSS_CORE_MAX];
static char first_cold_failure[128];
static uint64_t signature = UINT64_C(1469598103934665603);
static void check(bool condition) {checks++;if (!condition) failures++;}
static void check_helper(bool condition) {check(condition);if (!condition) helper_failures++;}
static void check_cold(bool condition, const char *name, int core) {
    check(condition);
    if (!condition) {
        cold_failures[core]++;
        if (!first_cold_failure[0])
            snprintf(first_cold_failure, sizeof(first_cold_failure), "core%d-case%u-%s", core, cases, name);
    }
}
/* Single-thread host model: real volatile loads, with observable short circuiting. */
#define READ_ONCE(value) (ctx_reads++, *(volatile __typeof__(value) *)&(value))
static void mix(unsigned value) {signature ^= value;signature *= UINT64_C(1099511628211);}
static int proc_dointvec(const struct ctl_table *ctl, int write, void *buffer, size_t *len, loff_t *pos) {
    (void)len;(void)pos;
    parser_calls++;
    if (parse_result) return parse_result;
    if (write) *(int *)ctl->data = *(int *)buffer;
    return 0;
}
static void log_message(void *dev, const char *fmt, ...) {
    (void)dev;
    log_calls++;
    if (strstr(fmt, "got added to NSS")) success_logs++;
    if (strstr(fmt, "configuration failed")) failure_logs++;
}
#define dev_info log_message
#define dev_warn log_message
static nss_tx_status_t nss_n2h_buf_pool_cfg(struct nss_ctx_instance *ctx, int value, nss_core_id_t core) {
    calls++;
    check((int)core == expected_core && ctx == &nss_top_main.nss[expected_core]);
    check(value == requested);
    ctx->buf_sz_allocated = backend_allocated;
    return backend_status;
}
'''
main = r'''
static void reset(int core) {
    memset(&nss_top_main, 0, sizeof(nss_top_main));
    nss_top_main.nss[core].state = NSS_CORE_STATE_INITIALIZED;
    nss_top_main.nss[core].magic = NSS_CTX_MAGIC;
    nss_n2h_core0_add_buf_pool_size = nss_n2h_core1_add_buf_pool_size = 77;
    parse_result = 0;calls = success_logs = failure_logs = 0;expected_core = core;cases++;
    parser_calls = log_calls = ctx_reads = 0;
    backend_status = NSS_TX_SUCCESS;backend_allocated = 0;
}
static int invoke(int core, int write, int value) {
    struct ctl_table ctl = {.data = core ? &nss_n2h_core1_add_buf_pool_size : &nss_n2h_core0_add_buf_pool_size};
    size_t length = sizeof(value);loff_t pos = 0;requested = value;
    return core ? nss_n2h_buf_cfg_core1_handler(&ctl,write,&value,&length,&pos) :
                  nss_n2h_buf_cfg_core0_handler(&ctl,write,&value,&length,&pos);
}
int main(void) {
    const int sizes[] = {1, 4096, NSS_N2H_MAX_BUF_POOL_SIZE};
    for (int core = 0; core < NSS_CORE_MAX; core++) {
        for (int status = NSS_TX_SUCCESS; status < NSS_TX_FAILURE_MAX; status++)
        for (unsigned size = 0; size < sizeof(sizes)/sizeof(sizes[0]); size++)
        for (int partial = 0; partial < 2; partial++) {
            reset(core);backend_status = status;backend_allocated = partial ? 8192 : 0;
            int ret = invoke(core,1,sizes[size]);
            check(ret == (status == NSS_TX_SUCCESS ? 0 : -EIO));
            check(calls == 1 && nss_top_main.nss[core].buf_sz_allocated == (uint32_t)backend_allocated);
            check((core ? nss_n2h_core1_add_buf_pool_size : nss_n2h_core0_add_buf_pool_size) == backend_allocated);
            check((core ? nss_n2h_core0_add_buf_pool_size : nss_n2h_core1_add_buf_pool_size) == 77);
            check(success_logs == (status == NSS_TX_SUCCESS ? 1u : 0u));
            check(failure_logs == (status == NSS_TX_SUCCESS ? 0u : 1u));
            if (status == NSS_TX_SUCCESS) {mix(ret);mix(calls);mix(backend_allocated);mix(success_logs);}
        }
        const int bad[] = {-1, 0, NSS_N2H_MAX_BUF_POOL_SIZE+1, INT_MAX};
        for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
            reset(core);int ret=invoke(core,1,bad[i]);
            check(ret == -EINVAL && !calls && !success_logs && !failure_logs);mix(ret);mix(calls);
        }
        for (int write=0;write<2;write++) {
            reset(core);parse_result=-EFAULT;int ret=invoke(core,write,4096);
            check(ret == -EFAULT && !calls && !success_logs && !failure_logs);mix(ret);
        }
        reset(core);int ret=invoke(core,0,4096);
        check(!ret && !calls && !success_logs && !failure_logs);mix(ret);
        for (int input=0;input<2;input++) {
            reset(core);nss_top_main.nss[core].buf_sz_allocated=4096;
            int ret=invoke(core,1,input ? 4096 : 0);
            check(ret == -EPERM && !calls && !success_logs && !failure_logs);
            check((core ? nss_n2h_core1_add_buf_pool_size : nss_n2h_core0_add_buf_pool_size)==4096);mix(ret);
        }
    }
    unsigned normal_failures = failures;
    const enum nss_core_state states[] = {NSS_CORE_STATE_UNINITIALIZED, NSS_CORE_STATE_INITIALIZED,
        NSS_CORE_STATE_FW_DEAD, NSS_CORE_STATE_FW_DUMP, NSS_CORE_STATE_PANIC};
    const uint32_t magics[] = {0, NSS_CTX_MAGIC, NSS_CTX_MAGIC ^ 1u};
    reset(0);helper_cases++;
    check_helper(!nss_sysctl_ctx_ready(NULL));
    check_helper(!ctx_reads);
    for (int core = 0; core < NSS_CORE_MAX; core++)
    for (unsigned s = 0; s < sizeof(states)/sizeof(states[0]); s++)
    for (unsigned m = 0; m < sizeof(magics)/sizeof(magics[0]); m++) {
        reset(core);helper_cases++;
        nss_top_main.nss[core].state = states[s];
        nss_top_main.nss[core].magic = magics[m];
        bool ready = states[s] == NSS_CORE_STATE_INITIALIZED && magics[m] == NSS_CTX_MAGIC;
        check_helper(nss_sysctl_ctx_ready(&nss_top_main.nss[core]) == ready);
        check_helper(ctx_reads == (states[s] == NSS_CORE_STATE_INITIALIZED ? 2u : 1u));
        if (!TEST_COLD_ADMISSION || ready) continue;
        for (int write = 0; write < 2; write++)
        for (int parse_error = 0; parse_error < 2; parse_error++)
        for (int allocated = 0; allocated <= 4096; allocated += 4096) {
            reset(core);cold_cases[core]++;
            nss_top_main.nss[core].state = states[s];
            nss_top_main.nss[core].magic = magics[m];
            nss_top_main.nss[core].buf_sz_allocated = allocated;
            /* Keep the peer ready: admission must use the selected core. */
            nss_top_main.nss[!core].state = NSS_CORE_STATE_INITIALIZED;
            nss_top_main.nss[!core].magic = NSS_CTX_MAGIC;
            struct nss_top_instance before = nss_top_main;
            parse_result = parse_error ? -EFAULT : 0;
            int ret = invoke(core, write, 4096);
            check_cold(ret == (write ? -ENODEV : parse_result), "return", core);
            check_cold(parser_calls == (write ? 0u : 1u), "parser-admission", core);
            check_cold(ctx_reads == (write ? (states[s] == NSS_CORE_STATE_INITIALIZED ? 2u : 1u) : 0u),
                "readiness-loads", core);
            check_cold(!calls && !log_calls && !success_logs && !failure_logs, "side-effects", core);
            check_cold(nss_n2h_core0_add_buf_pool_size == 77 && nss_n2h_core1_add_buf_pool_size == 77 &&
                !memcmp(&before, &nss_top_main, sizeof(before)), "state-preserved", core);
        }
    }
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%016llx\","
        "\"normal_failures\":%u,\"helper_cases\":%u,\"helper_failures\":%u,"
        "\"cold_cases_core0\":%u,\"cold_cases_core1\":%u,"
        "\"cold_failures_core0\":%u,\"cold_failures_core1\":%u,\"first_cold_failure\":\"%s\"}\n",
        cases,checks,failures,(unsigned long long)signature,normal_failures,helper_cases,helper_failures,
        cold_cases[0],cold_cases[1],cold_failures[0],cold_failures[1],first_cold_failure);
    return failures ? 1 : 0;
}
'''
variants = [('candidate', body, ready_helper, True, None)]
if args.baseline:
    variants.append(('baseline', functions((args.baseline / 'nss_n2h.c').read_text()), ready_helper, False, None))
if args.mutations:
    for label, before, after in [
        ('positive-status', 'return -EIO;', 'return ret;'),
        ('false-success', 'return -EIO;', 'return 0;'),
        ('inverted-guard', 'if (ret != NSS_TX_SUCCESS)', 'if (ret == NSS_TX_SUCCESS)'),
        ('false-success-log', 'return -EIO;', 'dev_info(nss_ctx->dev, "got added to NSS"); return -EIO;'),
    ]:
        if body.count(before) != 2:
            raise ValueError('mutation context: ' + label)
        variants.append((label, body.replace(before, after), ready_helper, False, None))
    guard = '\tif (write && !nss_sysctl_ctx_ready(nss_ctx))\n\t\treturn -ENODEV;\n'
    for core in (0, 1):
        handler = extract.function(source, 'nss_n2h_buf_cfg_core%d_handler' % core)
        if handler.count(guard) != 1 or body.count(handler) != 1:
            raise ValueError('mutation context: cold-core%d-admission-bypass' % core)
        variants.append(('cold-core%d-admission-bypass' % core,
                         body.replace(handler, handler.replace(guard, '')), ready_helper, False, core))
    for field, expected in (('state', 'NSS_CORE_STATE_INITIALIZED'), ('magic', 'NSS_CTX_MAGIC')):
        before = '(READ_ONCE(nss_ctx->%s) == %s)' % (field, expected)
        if ready_helper.count(before) != 1:
            raise ValueError('mutation context: ready-helper-ignore-' + field)
        mutated_helper = ready_helper.replace(before, '((void)READ_ONCE(nss_ctx->%s), true)' % field)
        variants.append(('ready-helper-ignore-' + field, body, mutated_helper, False, 'helper'))
records = []
normal = None
for label, code, helper, must_pass, cold_control in variants:
    c = args.output / (label + '.c')
    c.write_text(prefix + enums + core_state + magic[0] + '\n' + maximum[0] + '\n' + models +
                 helper + code + '#define TEST_COLD_ADMISSION %d\n' % (label != 'baseline') + main)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(c.with_suffix(''))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True)
    (args.output / (label + '-compile.stdout')).write_bytes(compiled.stdout)
    (args.output / (label + '-compile.stderr')).write_bytes(compiled.stderr)
    if compiled.returncode:
        raise SystemExit(compiled.stderr.decode())
    ran = subprocess.run([str(c.with_suffix(''))], capture_output=True)
    (args.output / (label + '.stdout')).write_bytes(ran.stdout)
    (args.output / (label + '.stderr')).write_bytes(ran.stderr)
    result = json.loads(ran.stdout)
    if ran.stderr or ran.returncode != (0 if must_pass else 1) or (result['failures']==0) != must_pass:
        raise SystemExit('unexpected ' + label)
    if label == 'candidate':
        normal = result['normal_signature']
    cold_failures = [result['cold_failures_core%d' % core] for core in (0, 1)]
    if cold_control is not None:
        if result['normal_failures'] or result['normal_signature'] != normal:
            raise SystemExit('cold control changed normal path: ' + label)
        if cold_control == 'helper':
            localized = all(cold_failures) and result['helper_failures'] > 0
        else:
            localized = cold_failures[cold_control] > 0 and not cold_failures[1 - cold_control] and not result['helper_failures']
        if not localized or not result['first_cold_failure']:
            raise SystemExit('cold control did not fail its runtime oracle: ' + label)
    elif any(cold_failures) or result['helper_failures']:
        raise SystemExit('unrelated readiness failure: ' + label)
    if label == 'baseline' and result['normal_signature'] != normal:
        raise SystemExit('normal path changed')
    records.append(dict(label=label, command=command, compile_returncode=compiled.returncode,
                        run_command=[str(c.with_suffix(''))], run_returncode=ran.returncode, result=result,
                        generated_sha256=hashlib.sha256(c.read_bytes()).hexdigest()))
summary = dict(records=records, handlers_sha256=hashlib.sha256(body.encode()).hexdigest(),
    input_sha256=hashlib.sha256((args.prepared/'nss_n2h.c').read_bytes()).hexdigest(),
    ready_helper_sha256=hashlib.sha256(ready_helper.encode()).hexdigest(),
    prepared=prepared.manifest(),
    asset_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='complete handlers/readiness helper, actual enums/constants and four actual context fields; '
          'modeled container layouts, single-thread READ_ONCE loads, parser, NSS outcomes and logging; '
          'baseline runs only legacy handler oracles plus candidate helper checks; '
          'not allocation/DMA/FW, concurrency or kernel VFS')
(args.output/'RESULT.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps([dict(label=r['label'], **r['result']) for r in records], indent=2))
