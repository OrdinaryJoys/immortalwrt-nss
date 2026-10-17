#!/usr/bin/env python3
"""Compile actual prepared MIB structs/functions. Hardware and locks are models."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--expect-failure', action='store_true')
args = parser.parse_args()
fal = (args.prepared / 'src/fal/fal_mib.c').read_text()
ref = (args.prepared / 'src/ref/ref_mib.c').read_text()
header = (args.prepared / 'include/fal/fal_mib.h').read_text()
platform = (args.prepared / 'include/init/ssdk_plat.h').read_text()
buffer_sizes = re.findall(r'a_uint8_t\s+buf\[(\d+)\]', platform)
if len(buffer_sizes) != 1:
    raise RuntimeError('ambiguous target diagnostic buffer size')


def function(text, name):
    matches = list(re.finditer(r'(?m)^' + re.escape(name) + r'\(', text))
    if len(matches) != 1:
        raise RuntimeError('ambiguous function: ' + name)
    start = matches[0].start()
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


types = ''
for name in ('fal_mib_info_t', 'fal_mib_counter_t'):
    body = re.findall(r'typedef\s+struct\s*\{([^}]+)\}\s*' + name + ';', header)
    if len(body) != 1:
        raise RuntimeError('ambiguous struct: ' + name)
    types += 'typedef struct {' + body[0] + '} ' + name + ';\n'
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t a_uint32_t;
typedef uint64_t a_uint64_t;
typedef uint64_t u64;
typedef uint32_t fal_port_t;
typedef int sw_error_t;
#define SW_OK 0
#define SW_BAD_PTR -1
#define SW_BAD_PARAM -2
#define SW_MAX_NR_PORT 8
#define SW_MAX_NR_DEV 1
#define FAL_PORT_ID_VALUE(v) ((v) & 0xffff)
'''
prefix += types
prefix += r'''
static fal_mib_counter_t counters[8];
static fal_mib_counter_t *g_mibcounter[1] = {counters};
static fal_mib_info_t sample;
static int io_status, flush_status, fal_locks, mutexes, warnings, mutate_on_unlock;
static void unlock_fal(void) {
    assert(fal_locks-- == 1);
    if (mutate_on_unlock) counters[1].RxFcsErr += 100;
}
#define FAL_API_LOCK assert(fal_locks++ == 0)
#define FAL_API_UNLOCK unlock_fal()
static int _fal_get_mib_info(unsigned dev, unsigned port, fal_mib_info_t *out) {
    (void)dev; (void)port; assert(fal_locks == 1);
    *out = sample; return io_status;
}
static int _fal_get_rx_mib_info(unsigned dev, unsigned port, fal_mib_info_t *out) {
    return _fal_get_mib_info(dev,port,out);
}
static int _fal_get_tx_mib_info(unsigned dev, unsigned port, fal_mib_info_t *out) {
    return _fal_get_mib_info(dev,port,out);
}
static int _fal_mib_port_flush_counters(unsigned dev, unsigned port) {
    (void)dev; (void)port; assert(fal_locks == 1); return flush_status;
}
'''
for name in ('_fal_rx_mib_update', '_fal_tx_mib_update'):
    # The updater definitions have a same-line static return type.
    anchor = 'static void ' + name + '('
    start = fal.index(anchor)
    opening = fal.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (fal[end] == '{') - (fal[end] == '}')
        end += 1
    prefix += fal[start:end] + '\n'
for name in ('fal_get_mib_info', 'fal_get_rx_mib_info', 'fal_get_tx_mib_info',
             'fal_mib_counter_get', 'fal_mib_port_flush_counters'):
    prefix += 'sw_error_t\n' + function(fal, name)
prefix += r'''
struct switch_attr { int unused; };
struct switch_val {int port_vlan; union {char *s;} value; int len;};
struct qca_phy_priv {unsigned device_id, mib_loop_cnt, ports; int mib_lock, reg_mutex, version;
    a_uint64_t *mib_counters; char buf[TARGET_MIB_BUFFER_SIZE]; uint64_t canary;};
struct switch_dev {int ports; struct qca_phy_priv *priv;};
static struct qca_phy_priv *qca_phy_priv_get(struct switch_dev *d) {return d->priv;}
static void mutex_lock(int *m) {(void)m; assert(mutexes++ == 0);}
static void mutex_unlock(int *m) {(void)m; assert(mutexes-- == 1);}
#define pr_warn_ratelimited(...) ((void)warnings++)
#define QCA_MIB_ITEM_NUMBER (sizeof(fal_mib_counter_t)/sizeof(a_uint64_t))
#ifdef HPPE
#define QCA_VER_HPPE 1
#define QCA_VER_APPE 2
#define QCA_VER_MRPPE 3
#define PORT_XGMAC_TYPE 1
static int qca_hppe_port_mac_type_get(unsigned dev, int port) {(void)dev; (void)port; return 0;}
static int qca_ar8327_sw_print_xgport_mib(struct switch_dev *d, const struct switch_attr *a, struct switch_val *v) {
    (void)d; (void)a; (void)v; assert(!"XGMAC is not modeled by this GMAC regression"); return -EIO;
}
#endif
'''
for name in ('_qca_ar8327_sw_capture_port_counter', '_qca_ar8327_sw_capture_port_rx_counter',
             '_qca_ar8327_sw_capture_port_tx_counter', 'qca_ar8327_sw_get_port_mib',
             'qca_ar8327_sw_set_reset_mibs', 'qca_ar8327_sw_set_port_reset_mib'):
    prefix += 'int\n' + function(ref, name)
prefix += 'void\n' + function(ref, 'qca_ar8327_sw_mib_task')
tests = r'''
static unsigned checks, failures;
static void check(int ok, const char *name) {checks++; if(!ok) {failures++;printf("FAIL %s\n",name);}}
static void reset(void) {
    memset(counters,0,sizeof(counters)); memset(&sample,0,sizeof(sample));
    io_status=flush_status=warnings=mutate_on_unlock=0; assert(!fal_locks && !mutexes);
}
int main(void) {
    fal_mib_info_t input={0}; fal_mib_counter_t out;
    reset(); sample.RxJumboFcsErr=3; sample.RxJumboAligenErr=7;
    memset(&out,0xa5,sizeof(out));
    check(fal_mib_counter_get(0,1,&out)==0,"success");
    check(counters[1].RxJumboFcsErr==3,"accumulate jumbo fcs");
    check(counters[1].RxJumboAligenErr==7,"accumulate jumbo alignment");
    check(out.RxJumboFcsErr==3,"output jumbo fcs");
    check(out.RxJumboAligenErr==7,"output jumbo alignment");
    check(!memcmp(&out,&counters[1],sizeof(out)),"all output fields initialized, including unsupported counters");
    reset(); sample.RxFcsErr=0xffffffffU; fal_mib_counter_get(0,1,&out);
    sample.RxFcsErr=7; fal_mib_counter_get(0,1,&out);
    check(out.RxFcsErr==0x100000006ULL,"64 bit accumulation");
    sw_error_t (*getters[])(unsigned,unsigned,fal_mib_info_t*)={fal_get_mib_info,fal_get_rx_mib_info,fal_get_tx_mib_info};
    for(unsigned i=0;i<3;i++) {
        reset(); sample.RxFcsErr=11; sample.TxUnderRun=13; io_status=-5;
        check(getters[i](0,1,&input)==-5,"getter preserves error");
        check(!counters[1].RxFcsErr && !counters[1].TxUnderRun,"partial failed read not accumulated");
    }
    reset(); sample.RxFcsErr=2; mutate_on_unlock=1;
    fal_mib_counter_get(0,1,&out);
    check(out.RxFcsErr==2,"output belongs to locked snapshot");
    reset(); counters[1].RxFcsErr=15; flush_status=-9;
    check(fal_mib_port_flush_counters(0,1)==-9,"flush returns error");
    check(counters[1].RxFcsErr==15,"failed flush preserves cumulative state");
    flush_status=0; check(fal_mib_port_flush_counters(0,1)==0 && !counters[1].RxFcsErr,"successful flush resets");
    struct qca_phy_priv priv={.ports=2,.mib_counters=(a_uint64_t*)counters,.version=1};
    struct switch_dev dev={.ports=2,.priv=&priv};
    struct switch_val val={.port_vlan=1,.len=123};
    reset(); io_status=-5;
    check(qca_ar8327_sw_get_port_mib(&dev,NULL,&val)==-EIO,"swconfig read fails");
    check(val.len==123 && !val.value.s,"failed swconfig has no successful output");
    qca_ar8327_sw_mib_task(&priv);
    check(warnings==1,"periodic failure reported");
    check(priv.mib_loop_cnt==1,"periodic failure does not stall remaining ports");
    reset(); sample.RxFcsErr=4;
    check(qca_ar8327_sw_get_port_mib(&dev,NULL,&val)==0 && val.value.s==priv.buf,"normal swconfig preserved");
    check(strstr(val.value.s,"RxJumboFcsErr") && strstr(val.value.s,"RxJumboAligenErr"),"swconfig exposes jumbo errors");
    reset(); counters[1].RxFcsErr=15; flush_status=-9;
    check(qca_ar8327_sw_set_port_reset_mib(&dev,NULL,&val)==-EIO,"port reset error propagated");
    check(counters[1].RxFcsErr==15,"port reset failure preserves data");
    check(qca_ar8327_sw_set_reset_mibs(&dev,NULL,&val)==-EIO,"all port reset error propagated");
    check(counters[1].RxFcsErr==15,"all port reset failure preserves data");
    check(!fal_locks && !mutexes,"locks balanced including error paths");
    reset(); memset(counters,0xff,sizeof(counters)); priv.canary=0x123456789abcdef0ULL;
    check(qca_ar8327_sw_get_port_mib(&dev,NULL,&val)==0,"maximum counters formatted");
    check(val.len>0 && (unsigned)val.len<sizeof(priv.buf),"maximum output fits actual target buffer");
    check(priv.buf[val.len]=='\0' && (unsigned)val.len==strlen(priv.buf),"maximum output not truncated");
    check(priv.canary==0x123456789abcdef0ULL,"diagnostic buffer canary preserved");
    printf("checks=%u failures=%u\n",checks,failures);
    return failures ? 1 : 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ssdk-mib-') as directory:
    c = Path(directory) / 'test.c'
    binary = c.with_suffix('')
    c.write_text('#define TARGET_MIB_BUFFER_SIZE '+buffer_sizes[0]+'\n'+prefix + tests)
    for hppe in (False, True):
        options = ['-DHPPE=1'] if hppe else []
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        *options, str(c), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        print(result.stdout, end='')
        print(json.dumps({'hardware_mocked': True, 'target_built': False, 'hppe_gmac_dispatch': hppe,
                          'fal_sha256': hashlib.sha256(fal.encode()).hexdigest(),
                          'ref_sha256': hashlib.sha256(ref.encode()).hexdigest(),
                          'returncode': result.returncode}))
        if result.returncode != (1 if args.expect_failure else 0):
            raise SystemExit('unexpected result: ' + result.stderr)
