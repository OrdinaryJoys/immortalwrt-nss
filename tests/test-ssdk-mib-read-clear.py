#!/usr/bin/env python3
"""Exercise exact FAL/HPPE functions with destructive register-read models.

No make, target compilation, module loading, firmware or router access.
Every failed-register position is tested. Baseline and mutations must fail.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)


def function(text, name):
    found = list(re.finditer(r'(?m)^(?:static void )?' + re.escape(name) + r'\(', text))
    if len(found) != 1:
        raise RuntimeError('ambiguous function: ' + name)
    start = found[0].start()
    if text.startswith('static void ', start):
        start += len('static void ')
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


def generate(prepared, mutation=None):
    fal = (prepared / 'src/fal/fal_mib.c').read_text()
    original = fal
    adapter = (prepared / 'src/adpt/hppe/adpt_hppe_mib.c').read_text()
    header = (prepared / 'include/fal/fal_mib.h').read_text()
    port_header = (prepared / 'include/fal/fal_type.h').read_text()
    errors = (prepared / 'include/common/sw_error.h').read_text()
    if mutation == 'no-invalidation':
        old = function(fal, '_fal_mib_counter_invalidate')
        fal = fal.replace(old, old.replace('= A_TRUE;', '= A_FALSE;'), 1)
    if mutation == 'good-read-heals':
        old = function(fal, 'fal_get_mib_info')
        new = old.replace('if (rv == SW_OK) {', 'if (rv == SW_OK) {\n        g_mibcounter_invalid[dev_id][FAL_PORT_ID_VALUE(port_id)] = A_FALSE;', 1)
        assert new != old
        fal = fal.replace(old, new, 1)
    if mutation == 'failed-flush-heals':
        old = function(fal, 'fal_mib_port_flush_counters')
        new = old.replace('_fal_mib_counter_invalidate(dev_id, port_id);',
                          'g_mibcounter_invalid[dev_id][FAL_PORT_ID_VALUE(port_id)] = A_FALSE;', 1)
        assert new != old
        fal = fal.replace(old, new, 1)
    prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t a_uint32_t;
typedef uint64_t a_uint64_t;
typedef uint64_t u64;
typedef uint32_t fal_port_t;
typedef int sw_error_t;
typedef int a_bool_t;
#define A_TRUE 1
#define A_FALSE 0
#define SW_MAX_NR_DEV 1
#define SW_MAX_NR_PORT 8
#define GFP_KERNEL 0
#define kzalloc(n,f) calloc(1,n)
#define kfree free
#define ADPT_DEV_ID_CHECK(d) do { if ((d)>=SW_MAX_NR_DEV) return SW_BAD_PARAM; } while (0)
#define ADPT_NULL_POINT_CHECK(p) do { if (!(p)) return SW_BAD_PTR; } while (0)
'''
    prefix += '\n'.join('#define ' + name + ' ' + value for name, value in
                        re.findall(r'\b(SW_\w+)\s*=\s*(-?\d+)', errors)) + '\n'
    for name in ('fal_mib_info_t', 'fal_mib_counter_t'):
        prefix += re.search(r'typedef\s+struct\s*\{[^}]+\}\s*' + name + ';', header).group() + '\n'
    prefix += re.search(r'^#define FAL_PORT_ID_VALUE\([^\n]+', port_header, re.M).group() + '\n'
    hppe_header = (prepared / 'include/hsl/hppe/hppe_init.h').read_text()
    prefix += re.search(r'^#define HPPE_TO_GMAC_PORT_ID\([^\n]+', hppe_header, re.M).group() + '\n'
    raw_names = ('adpt_hppe_get_mib_info', 'adpt_hppe_get_rx_mib_info', 'adpt_hppe_get_tx_mib_info')
    raw = '\n'.join('static sw_error_t\n' + function(adapter, name) for name in raw_names)
    macro = re.search(r'^#define HPPE_MIB_GET[^\n]*(?:\n[^\n]*)*?\n\} while \(0\)', adapter, re.M).group()
    helpers = sorted(set(re.findall(r'HPPE_MIB_GET\((hppe_\w+),', raw)))
    prefix += '#define REGISTER_COUNT ' + str(len(helpers)) + '\n'
    prefix += r'''
static uint32_t registers[SW_MAX_NR_PORT][REGISTER_COUNT];
static unsigned calls, fail_at, reads_cleared, fal_locked;
static int flush_error;
static int read_register(unsigned index, unsigned dev, unsigned port, void *value) {
    (void)dev;
    assert(fal_locked==1);
    if (port>=6) return SW_OUT_OF_RANGE;
    ++calls;
    if (calls==fail_at) return SW_READ_ERROR;
    *(uint32_t *)value=registers[port][index];
    registers[port][index]=0;
    ++reads_cleared;
    return SW_OK;
}
#define FAL_API_LOCK do { assert(fal_locked==0); fal_locked=1; } while (0)
#define FAL_API_UNLOCK do { assert(fal_locked==1); fal_locked=0; } while (0)
'''
    for index, helper in enumerate(helpers):
        prefix += f'static sw_error_t {helper}(unsigned d,unsigned p,void *v) {{ return read_register({index},d,p,v); }}\n'
    prefix += macro + '\n' + raw
    for full, lower in zip(('mib', 'rx_mib', 'tx_mib'), raw_names):
        prefix += f'static sw_error_t _fal_get_{full}_info(unsigned d,unsigned p,fal_mib_info_t *v) {{ return {lower}(d,p,v); }}\n'
    prefix += r'''
static sw_error_t _fal_mib_port_flush_counters(unsigned dev, unsigned port) {
    (void)dev;
    assert(fal_locked==1);
    if (flush_error) return flush_error;
    memset(registers[port-1],0,sizeof(registers[port-1]));
    return SW_OK;
}
'''
    prefix += re.search(r'static fal_mib_counter_t \*g_mibcounter\[[^;]+;', fal).group() + '\n'
    if 'static a_bool_t g_mibcounter_invalid[' in fal:
        prefix += re.search(r'static a_bool_t g_mibcounter_invalid\[[^;]+;', fal).group() + '\n'
        prefix += 'static void\n' + function(fal, '_fal_mib_counter_invalidate')
    for name in ('fal_mib_counter_alloc', 'fal_mib_counter_free'):
        prefix += 'sw_error_t\n' + function(fal, name)
    for name in ('_fal_rx_mib_update', '_fal_tx_mib_update'):
        prefix += 'static void\n' + function(fal, name)
    for name in ('fal_get_mib_info', 'fal_get_rx_mib_info', 'fal_get_tx_mib_info',
                 'fal_mib_counter_get', 'fal_mib_port_flush_counters'):
        prefix += 'sw_error_t\n' + function(fal, name)
    prefix += r'''
static unsigned checks, failures, injected_positions;
static void check(int condition,const char *name) {
    ++checks;
    if (!condition) { ++failures; if(failures<9) fprintf(stderr,"FAIL %s\n",name); }
}
static a_uint64_t *allocation;
static void begin(void) {
    assert(!fal_locked);
    assert(fal_mib_counter_alloc(0,&allocation)==SW_OK);
    for(unsigned p=0;p<SW_MAX_NR_PORT;++p)
        for(unsigned i=0;i<REGISTER_COUNT;++i) registers[p][i]=9;
    calls=fail_at=reads_cleared=0;
    flush_error=0;
}
static void end(void) {
    assert(!fal_locked);
    assert(fal_mib_counter_free(0,&allocation)==SW_OK && !allocation);
}
int main(void) {
    sw_error_t (*getters[])(unsigned,unsigned,fal_mib_info_t *)={fal_get_mib_info,fal_get_rx_mib_info,fal_get_tx_mib_info};
    fal_mib_info_t sample;
    fal_mib_counter_t output,sentinel,before;
    for(unsigned kind=0;kind<4;++kind) {
        unsigned count;
        begin();
        check((kind<3?getters[kind](0,1,&sample):fal_mib_counter_get(0,1,&output))==SW_OK,"successful read control");
        count=calls;
        check(count>1,"multiple real adapter fields exercised");
        end();
        for(unsigned position=1;position<=count;++position) {
            begin();
            g_mibcounter[0][1].RxFcsErr=11;
            g_mibcounter[0][1].TxUnderRun=13;
            before=g_mibcounter[0][1];
            fail_at=position;
            check((kind<3?getters[kind](0,1,&sample):fal_mib_counter_get(0,1,&output))==SW_READ_ERROR,"original failure preserved");
            ++injected_positions;
            check(reads_cleared==position-1,"prefix really cleared before injected failure");
            check(!memcmp(&before,&g_mibcounter[0][1],sizeof(before)),"failed partial sample never accumulated");
            unsigned old_calls=calls;
            fail_at=0;
            memset(&output,0xa5,sizeof(output)); sentinel=output;
            check(fal_mib_counter_get(0,1,&output)==SW_READ_ERROR,"lost read-clear epoch stays unknown");
            check(!memcmp(&output,&sentinel,sizeof(output)),"unknown does not publish zero or partial counters");
            check(calls==old_calls,"unknown snapshot does not consume more counters");
            check(fal_get_mib_info(0,1,&sample)==SW_OK,"new raw sample still works");
            check(fal_mib_counter_get(0,1,&output)==SW_READ_ERROR,"good raw sample cannot heal history");
            check(fal_mib_counter_get(0,2,&output)==SW_OK,"unrelated port remains healthy");
            before=g_mibcounter[0][1];
            flush_error=SW_WRITE_ERROR;
            check(fal_mib_port_flush_counters(0,1)==SW_WRITE_ERROR,"failed flush preserves original error");
            check(!memcmp(&before,&g_mibcounter[0][1],sizeof(before)),"failed flush preserves numbers");
            check(fal_mib_counter_get(0,1,&output)==SW_READ_ERROR,"failed flush cannot heal history");
            flush_error=0;
            check(fal_mib_port_flush_counters(0,1)==SW_OK,"explicit successful flush starts known epoch");
            memset(&before,0,sizeof(before));
            check(!memcmp(&before,&g_mibcounter[0][1],sizeof(before)),"successful flush resets cumulative state");
            check(fal_mib_counter_get(0,1,&output)==SW_OK,"successful explicit reset recovers diagnostic access");
            check(!memcmp(&before,&output,sizeof(output)),"new zero epoch is legitimate");
            end();
        }
    }
    begin();
    g_mibcounter[0][1].RxBroad=123;
    flush_error=SW_WRITE_ERROR;
    check(fal_mib_port_flush_counters(0,1)==SW_WRITE_ERROR,"flush from healthy epoch can fail");
    check(g_mibcounter[0][1].RxBroad==123,"failed healthy flush preserves data");
    check(fal_mib_counter_get(0,1,&output)==SW_READ_ERROR,"partially failed reset invalidates healthy epoch");
    end();
    begin();
    check(fal_mib_counter_get(0,1,&output)==SW_OK,"new allocation is independent epoch");
    calls=0;
    check(fal_mib_counter_get(0,0x00010001,&output)==SW_BAD_PARAM,"actual 24-bit port mask rejects high index");
    check(!calls,"invalid index never touches registers");
    check(fal_get_mib_info(0,1,NULL)==SW_BAD_PTR,"null raw output rejects before read");
    check(fal_mib_counter_get(0,1,&output)==SW_OK,"null caller error does not poison epoch");
    end();
    printf("{\"checks\":%u,\"failures\":%u,\"failed_register_positions\":%u,\"hardware_mocked\":true,\"kernel_or_firmware_built\":false}\n",checks,failures,injected_positions);
    return failures?1:0;
}
'''
    return prefix, hashlib.sha256(original.encode()).hexdigest(), len(helpers)


results = []
for label, tree, mutation, must_pass in [
    ('candidate', args.prepared, None, True), ('before-g5', args.baseline, None, False),
    ('no-invalidation', args.prepared, 'no-invalidation', False),
    ('good-read-heals', args.prepared, 'good-read-heals', False),
    ('failed-flush-heals', args.prepared, 'failed-flush-heals', False),
]:
    source, digest, helpers = generate(tree, mutation)
    c = args.output / (label + '.c')
    binary = c.with_suffix('')
    c.write_text(source)
    compile_result = subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                                     str(c),'-o',str(binary)],capture_output=True)
    (args.output / (label + '-compile.stdout')).write_bytes(compile_result.stdout)
    (args.output / (label + '-compile.stderr')).write_bytes(compile_result.stderr)
    if compile_result.returncode:
        raise SystemExit(label + ': fixture compile failed: ' + compile_result.stderr.decode())
    result = subprocess.run([str(binary)], capture_output=True)
    (args.output / (label + '.stdout')).write_bytes(result.stdout)
    (args.output / (label + '.stderr')).write_bytes(result.stderr)
    observed = json.loads(result.stdout)
    expected = result.returncode == (0 if must_pass else 1) and (observed['failures']==0) == must_pass
    results.append({'name':label,'fal_sha256':digest,'register_helpers':helpers,'returncode':result.returncode,
                    'expected_result':expected,**observed})
    print(label + ': ' + json.dumps(observed))
    if not expected:
        raise SystemExit('unexpected result: ' + label)
(args.output/'RESULT.json').write_text(json.dumps({'results':results,'target_built':False,
    'router_accessed':False,'scope':'Exact FAL/GMAC adapter functions; register read-clear and locks are models. XGMAC and concurrency are not qualified.'},indent=2)+'\n')
