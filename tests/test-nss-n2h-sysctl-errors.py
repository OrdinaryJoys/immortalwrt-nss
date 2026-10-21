#!/usr/bin/env python3
"""Complete actual extra-pbuf handlers; parser, logging and NSS outcome are models."""
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
source = (args.prepared / 'nss_n2h.c').read_text()
header = (args.prepared / 'exports/nss_cmn.h').read_text()
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
models = r'''
struct ctl_table {void *data;};
struct nss_ctx_instance {void *dev; int buf_sz_allocated;};
struct nss_top_instance {struct nss_ctx_instance nss[NSS_CORE_MAX];};
static struct nss_top_instance nss_top_main;
static int nss_n2h_core0_add_buf_pool_size, nss_n2h_core1_add_buf_pool_size;
static int parse_result, backend_status, backend_allocated, expected_core, requested;
static unsigned checks, failures, calls, success_logs, failure_logs, cases;
static uint64_t signature = UINT64_C(1469598103934665603);
static void check(bool condition) {checks++;if (!condition) failures++;}
static void mix(unsigned value) {signature ^= value;signature *= UINT64_C(1099511628211);}
static int proc_dointvec(const struct ctl_table *ctl, int write, void *buffer, size_t *len, loff_t *pos) {
    (void)len;(void)pos;
    if (parse_result) return parse_result;
    if (write) *(int *)ctl->data = *(int *)buffer;
    return 0;
}
static void log_message(void *dev, const char *fmt, ...) {
    (void)dev;
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
    nss_n2h_core0_add_buf_pool_size = nss_n2h_core1_add_buf_pool_size = 77;
    parse_result = 0;calls = success_logs = failure_logs = 0;expected_core = core;cases++;
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
            check(calls == 1 && nss_top_main.nss[core].buf_sz_allocated == backend_allocated);
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
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%016llx\"}\n",
        cases,checks,failures,(unsigned long long)signature);
    return failures ? 1 : 0;
}
'''
variants = [('candidate', body, True)]
if args.baseline:
    variants.append(('baseline', functions((args.baseline / 'nss_n2h.c').read_text()), False))
if args.mutations:
    for label, before, after in [
        ('positive-status', 'return -EIO;', 'return ret;'),
        ('false-success', 'return -EIO;', 'return 0;'),
        ('inverted-guard', 'if (ret != NSS_TX_SUCCESS)', 'if (ret == NSS_TX_SUCCESS)'),
        ('false-success-log', 'return -EIO;', 'dev_info(nss_ctx->dev, "got added to NSS"); return -EIO;'),
    ]:
        if body.count(before) != 2:
            raise ValueError('mutation context: ' + label)
        variants.append((label, body.replace(before, after), False))
records = []
normal = None
for label, code, must_pass in variants:
    c = args.output / (label + '.c')
    c.write_text(prefix + enums + maximum[0] + '\n' + models + code + main)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(c.with_suffix(''))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True)
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
    if label == 'baseline' and result['normal_signature'] != normal:
        raise SystemExit('normal path changed')
    records.append(dict(label=label, command=command, result=result,
                        generated_sha256=hashlib.sha256(c.read_bytes()).hexdigest()))
summary = dict(records=records, handlers_sha256=hashlib.sha256(body.encode()).hexdigest(),
    input_sha256=hashlib.sha256((args.prepared/'nss_n2h.c').read_bytes()).hexdigest(),
    asset_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='complete handlers and actual enums; modeled parser, NSS outcomes and logging; not allocation/DMA/FW or kernel VFS')
(args.output/'RESULT.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps([dict(label=r['label'], **r['result']) for r in records], indent=2))
