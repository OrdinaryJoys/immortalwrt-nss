#!/usr/bin/env python3
"""Complete actual MATCH handlers; host-only sysctl/netdev/NSS substitutes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('clients', type=Path)
parser.add_argument('--driver', type=Path, required=True)
parser.add_argument('--kernel-sysctl', type=Path, required=True)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--cc', default='cc')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
relative = 'match/nss_match_cmd.c'
names = ['nss_match_cmd_procfs_reset_nexthop', 'nss_match_cmd_procfs_set_if_nexthop']

prefix = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <limits.h>
typedef long long loff_t;
#define __user
#define IFNAMSIZ 16
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)
#define nss_match_warn(...) ((void)0)
struct ctl_table { void *data; int maxlen; };
struct nss_ctx_instance { int id; };
struct net_device { int id; };
static unsigned char nss_match_data[100];
static struct nss_ctx_instance context, wifi_context;
static struct net_device device;
static int init_net;
static int fail_match, fail_wifi, proc_error, lookup, dynamic_type, table_id, tx_error, device_exists;
static unsigned match_ifnum;
static unsigned get_count, put_count, sends, type_queries, checks, failures, cases;
static unsigned sent_if, sent_nh;
static int sent_kind;
static char looked_name[128];
static struct nss_ctx_instance *nss_match_get_context(void) { return fail_match ? NULL : &context; }
static struct nss_ctx_instance *nss_wifili_get_context(void) { return fail_wifi ? NULL : &wifi_context; }
static char *strim(char *s) {
    while (isspace((unsigned char)*s)) ++s;
    char *end = s + strlen(s);
    while (end > s && isspace((unsigned char)end[-1])) --end;
    *end = 0; return s;
}
/* Bounded unsigned base-10 contract; Linux implementation is not executed. */
static int kstrtouint(const char *s, unsigned base, unsigned *out) {
    char *end; errno = 0;
    if (!*s || *s == '-') return -EINVAL;
    unsigned long value = strtoul(s, &end, base);
    if (errno || value > UINT_MAX) return -ERANGE;
    if (*end || end == s) return -EINVAL;
    *out = (unsigned)value; return 0;
}
static struct net_device *dev_get_by_name(int *net, const char *name) {
    (void)net; snprintf(looked_name, sizeof(looked_name), "%s", name);
    if (!device_exists) return NULL;
    ++get_count; return &device;
}
static void dev_put(struct net_device *dev) { if (dev != &device) abort(); ++put_count; }
static int32_t nss_cmn_get_interface_number_by_dev(struct net_device *dev) { if (dev != &device) abort(); return lookup; }
static unsigned nss_dynamic_interface_get_type(struct nss_ctx_instance *ctx, unsigned num) {
    if (ctx != &wifi_context) abort();
    ++type_queries; sent_if = num;
    if (num < NSS_DYNAMIC_IF_START || num >= NSS_SPECIAL_IF_START) return NSS_DYNAMIC_INTERFACE_TYPE_NONE;
    return dynamic_type;
}
static int nss_match_get_table_id_by_ifnum(unsigned num) { sent_nh = num; return num == match_ifnum ? table_id : 0; }
static int send_msg(struct nss_ctx_instance *ctx, unsigned num, unsigned nh, int kind) {
    if (ctx != (kind == 1 || kind == 3 ? &wifi_context : &context)) abort();
    ++sends; sent_if = num; sent_nh = nh; sent_kind = kind; return tx_error;
}
static int nss_if_set_nexthop(struct nss_ctx_instance *c, unsigned n, unsigned h) { return send_msg(c,n,h,1); }
static int nss_phys_if_set_nexthop(struct nss_ctx_instance *c, unsigned n, unsigned h) { return send_msg(c,n,h,2); }
static int nss_if_reset_nexthop(struct nss_ctx_instance *c, unsigned n) { return send_msg(c,n,0,3); }
static int nss_phys_if_reset_nexthop(struct nss_ctx_instance *c, unsigned n) { return send_msg(c,n,0,4); }
static void check(bool ok, const char *label) { ++checks; if (!ok) { ++failures; fprintf(stderr,"FAIL %s\n",label); } }
static void reset(void) {
    fail_match = fail_wifi = proc_error = tx_error = 0;
    lookup = 2; dynamic_type = 0; table_id = 1; device_exists = 1;
    match_ifnum = 100;
    get_count = put_count = sends = type_queries = 0; sent_if = sent_nh = 0; sent_kind = 0;
    looked_name[0] = 0;
}
'''
main = r'''
static int call(bool set, const char *input, size_t length, int write) {
    struct ctl_table ctl = {nss_match_data, set ? 100 : 16};
    loff_t offset = 0;
    size_t count = length;
    return set ? nss_match_cmd_procfs_set_if_nexthop(&ctl,write,(void *)input,&count,&offset) :
        nss_match_cmd_procfs_reset_nexthop(&ctl,write,(void *)input,&count,&offset);
}
static void expect(bool set, const char *input, size_t length, int result, unsigned refs, unsigned tx, const char *name) {
    ++cases; int actual = call(set,input,length,1);
    check(actual == result,name); check(get_count == refs,name); check(put_count == refs,name); check(sends == tx,name);
}
int main(void) {
    reset(); expect(true,"lan1 100",8,0,1,1,"physical-set"); check(sent_kind==2 && sent_if==2 && sent_nh==100,"physical-payload");
    reset(); lookup=50; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP; expect(true,"wlan0 100\n",10,0,1,1,"vap-set"); check(sent_kind==1 && sent_if==50,"vap-payload");
    reset(); expect(false,"lan1\n",5,0,1,1,"physical-reset"); check(sent_kind==4,"physical-reset-kind");
    reset(); lookup=50; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP; expect(false,"wlan0",5,0,1,1,"vap-reset"); check(sent_kind==3,"vap-reset-kind");
    const char *bad[] = {"lan1", "lan1 ", "lan1 -1", "lan1 +1", "lan1 x", "lan1 1x", "lan1 1 2", "lan1 4294967296", "lan1 4294967295", "lan1 2048", " lan1 100", "abcdefghijklmnop 100"};
    for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i) { reset(); expect(true,bad[i],strlen(bad[i]),-EINVAL,0,0,"invalid-set"); }
    reset(); const char nul[]={'l','a','n','1',0,' ','1'}; expect(true,nul,sizeof(nul),-EINVAL,0,0,"embedded-nul-set");
    reset(); char longbuf[101]; memset(longbuf,'x',sizeof(longbuf)); expect(true,longbuf,100,-EINVAL,0,0,"set-full-boundary");
    reset(); longbuf[99]=0; expect(true,longbuf,101,-EINVAL,0,0,"set-over-boundary");
    reset(); char maxcmd[100]; memset(maxcmd,' ',sizeof(maxcmd)); memcpy(maxcmd,"lan1 100",8); expect(true,maxcmd,99,0,1,1,"set-99-nonterminated");
    reset(); expect(true,"lan1\t100 \n",10,0,1,1,"whitespace-token");
    reset(); expect(true,"abcdefghijklmnq 100",19,0,1,1,"ifname-max-set"); check(strlen(looked_name)==15,"set-name-not-truncated");
    reset(); expect(false,"abcdefghijklmno\n",16,0,1,1,"ifname-max-reset-newline");
    const char *badreset[]={" ", "lan1 extra", "abcdefghijklmnop", "lan1\nother"};
    for (unsigned i=0;i<sizeof(badreset)/sizeof(badreset[0]);++i) { reset(); expect(false,badreset[i],strlen(badreset[i]),-EINVAL,0,0,"invalid-reset"); }
    reset(); expect(false,nul,sizeof(nul),-EINVAL,0,0,"embedded-nul-reset");
    reset(); expect(false,longbuf,17,-EINVAL,0,0,"reset-over-boundary");
    for (int set=0;set<2;++set) {
        const char *input=set?"lan1 100":"lan1"; size_t length=strlen(input);
        reset(); proc_error=-EPERM; expect(set,input,length,-EPERM,0,0,"proc-error");
        reset(); fail_match=1; expect(set,input,length,-ENOMEM,0,0,"missing-match-context");
        reset(); fail_wifi=1; expect(set,input,length,-ENOMEM,0,0,"missing-wifi-context");
        reset(); device_exists=0; expect(set,input,length,-ENODEV,0,0,"missing-device");
        reset(); lookup=-1; expect(set,input,length,-ENODEV,1,0,"negative-interface"); check(type_queries==0,"no-type-query-on-negative");
        reset(); lookup=8; expect(set,input,length,-EFAULT,1,0,"unsupported-interface");
        reset(); tx_error=1; expect(set,input,length,-EIO,1,1,"send-error");
        reset(); fail_match=fail_wifi=1; ++cases; check(call(set,"",0,0)==0,"read-without-nss-context"); check(get_count==0 && sends==0,"read-no-effects");
        reset(); proc_error=-EFAULT; ++cases; check(call(set,"",0,0)==-EFAULT,"read-proc-error");
    }
    reset(); table_id=0; expect(true,"lan1 100",8,-EFAULT,1,0,"missing-match-table");
    reset(); table_id=5; expect(true,"lan1 100",8,-EFAULT,1,0,"table-out-of-range");
    char bound[32]; snprintf(bound,sizeof(bound),"lan1 %u",NSS_MAX_NET_INTERFACES);
    reset(); expect(true,bound,strlen(bound),-EINVAL,0,0,"actual-interface-upper-bound");
    snprintf(bound,sizeof(bound),"lan1 %u",NSS_MAX_NET_INTERFACES-1);
    reset(); expect(true,bound,strlen(bound),-EFAULT,1,0,"in-range-not-a-match-table");
    reset(); expect(true,"lan1 0",6,-EFAULT,1,0,"zero-not-a-match-table");
    reset(); table_id=NSS_MATCH_INSTANCE_MAX; expect(true,"lan1 100",8,0,1,1,"last-match-table");
    for (int set=0;set<2;++set) {
        const char *input=set?"wlan0 100":"wlan0"; size_t length=strlen(input);
        reset(); lookup=NSS_DYNAMIC_IF_START; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP;
        expect(set,input,length,0,1,1,"dynamic-first-vap"); check(sent_if==NSS_DYNAMIC_IF_START && sent_nh==(set?100:0) && sent_kind==(set?1:3),"dynamic-first-payload");
        reset(); lookup=NSS_SPECIAL_IF_START-1; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP;
        expect(set,input,length,0,1,1,"dynamic-last-vap"); check(sent_if==NSS_SPECIAL_IF_START-1 && sent_nh==(set?100:0) && sent_kind==(set?1:3),"dynamic-last-payload");
        reset(); lookup=NSS_SPECIAL_IF_START; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP;
        expect(set,input,length,-EFAULT,1,0,"beyond-dynamic-not-vap");
        reset(); lookup=50; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_MATCH;
        expect(set,input,length,-EFAULT,1,0,"dynamic-non-vap");
        reset(); lookup=50; dynamic_type=NSS_DYNAMIC_INTERFACE_TYPE_VAP; tx_error=1;
        expect(set,input,length,-EIO,1,1,"vap-send-error"); check(sent_if==50 && sent_nh==(set?100:0) && sent_kind==(set?1:3),"vap-error-payload");
        struct ctl_table ctl={nss_match_data,set?100:16}; char response[32]={0};
        int (*handler)(const struct ctl_table *,int,void *,size_t *,loff_t *)=set?nss_match_cmd_procfs_set_if_nexthop:nss_match_cmd_procfs_reset_nexthop;
        reset(); strcpy((char *)nss_match_data,"keep"); size_t count=0; loff_t pos=0; ++cases;
        check(handler(&ctl,1,(void *)input,&count,&pos)==0 && count==0 && pos==0,"zero-write-noop");
        check(!strcmp((char *)nss_match_data,"keep") && sends==0 && get_count==0,"zero-write-no-effects");
        loff_t offsets[]={1,-1,LLONG_MAX};
        for(unsigned i=0;i<3;++i) {
            reset(); strcpy((char *)nss_match_data,"keep"); count=length; pos=offsets[i]; ++cases;
            check(handler(&ctl,1,(void *)input,&count,&pos)==-EINVAL,"positional-write-reject");
            check(count==length && pos==offsets[i] && sends==0 && get_count==0 && !strcmp((char *)nss_match_data,"keep"),"positional-write-no-effects");
        }
        reset(); strcpy((char *)nss_match_data,"keep"); count=length; pos=0; ++cases;
        check(handler(&ctl,1,(void *)input,&count,&pos)==0 && count==length && pos==(loff_t)length,"write-consumption");
        check(!strcmp((char *)nss_match_data,input),"write-data");
        unsigned prior_sends=sends; count=length; ++cases;
        check(handler(&ctl,1,(void *)input,&count,&pos)==-EINVAL && sends==prior_sends && pos==(loff_t)length,"second-write-on-same-position-rejected");
        reset(); strcpy((char *)nss_match_data,"lan1"); count=3; pos=0; ++cases;
        check(handler(&ctl,0,response,&count,&pos)==0 && count==3 && pos==3 && !memcmp(response,"lan",3),"read-first-chunk");
        count=sizeof(response); memset(response,0,sizeof(response)); ++cases;
        check(handler(&ctl,0,response,&count,&pos)==0 && count==2 && pos==5 && !memcmp(response,"1\n",2),"read-tail-newline");
        count=sizeof(response); ++cases;
        check(handler(&ctl,0,response,&count,&pos)==0 && count==0 && pos==5,"read-eof");
        count=sizeof(response); pos=-1; ++cases;
        check(handler(&ctl,0,response,&count,&pos)==-EINVAL && pos==-1 && sends==0,"negative-read-rejected");
    }
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",cases,checks,failures);
    return failures ? 1 : 0;
}
'''

def run_variant(label, prepared, bodies, expected):
    directory = args.output / label
    directory.mkdir()
    generated = directory / 'actual-functions.c'
    generated.write_text(prefix + '\n'.join(bodies) + main)
    compiler = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra',
                '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-type-limits']
    if args.sanitize:
        compiler += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    compiler += [str(generated), '-o', str(directory / 'fixture')]
    built = subprocess.run(compiler, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (directory / 'compile.log').write_text(built.stdout)
    if built.returncode:
        raise RuntimeError(f'{label}: compiler failure is not a runtime negative control')
    env = os.environ.copy()
    env['ASAN_OPTIONS'] = 'detect_leaks=0'
    env['UBSAN_OPTIONS'] = 'halt_on_error=1'
    executed = subprocess.run([str(directory / 'fixture')], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    (directory / 'stdout.log').write_text(executed.stdout)
    (directory / 'stderr.log').write_text(executed.stderr)
    if (executed.returncode == 0) != expected:
        raise RuntimeError(f'{label}: unexpected result {executed.returncode}')
    if expected:
        result = json.loads(executed.stdout)
        if result['cases'] != 83 or result['checks'] < 270 or result['failures'] or executed.stderr:
            raise RuntimeError(f'{label}: incomplete or diagnostic-positive run')
    return {'variant': label, 'compile_command': compiler, 'returncode': executed.returncode,
            'expected_pass': expected, 'stdout': executed.stdout, 'input': prepared.manifest()}

candidate = extract.Prepared(args.clients)
driver = extract.Prepared(args.driver)
api = driver.read('exports/nss_api_if.h') + driver.read('exports/nss_dynamic_interface.h') + driver.read('exports/nss_match.h')
constants = ''
for name in ['NSS_MAX_DEVICE_INTERFACES', 'NSS_MAX_NET_INTERFACES',
             'NSS_MAX_PHYSICAL_INTERFACES', 'NSS_MAX_VIRTUAL_INTERFACES',
             'NSS_MAX_TUNNEL_INTERFACES', 'NSS_MAX_DYNAMIC_INTERFACES',
             'NSS_MAX_SPECIAL_INTERFACES', 'NSS_MATCH_INSTANCE_MAX',
             'NSS_PHYSICAL_IF_START', 'NSS_VIRTUAL_IF_START', 'NSS_TUNNEL_IF_START',
             'NSS_DYNAMIC_IF_START', 'NSS_SPECIAL_IF_START']:
    found = re.findall(r'^#define ' + name + r'\s+[^\n]+', api, re.M)
    if len(found) != 1:
        raise RuntimeError('Expected unique driver constant: ' + name)
    constants += found[0] + '\n'
constants += extract.structure(driver.read('exports/nss_dynamic_interface.h'), 'nss_dynamic_interface_type', 'enum')
status = re.findall(r'typedef enum\s*\{[^{}]*\}\s*nss_tx_status_t;', driver.read('exports/nss_cmn.h'))
if len(status) != 1:
    raise RuntimeError('Expected unique NSS status enum')
prefix = constants + status[0] + '\n' + prefix
kernel_text = args.kernel_sysctl.read_text()
kernel_actual = extract.structure(kernel_text, 'sysctl_writes_mode', 'enum')
kernel_actual += '\nstatic enum sysctl_writes_mode sysctl_writes_strict = SYSCTL_WRITES_STRICT;\n'
kernel_actual += extract.function(kernel_text, '_proc_do_string')
kernel_actual += 'static bool proc_first_pos_non_zero_ignore(loff_t *p, const struct ctl_table *t) { (void)t; return *p != 0; }\n'
kernel_actual += extract.function(kernel_text, 'proc_dostring', occurrence=0)
kernel_actual += r'''
static int host_proc_dostring(const struct ctl_table *ctl, int write, void *buf, size_t *len, loff_t *pos) {
    return proc_error ? proc_error : proc_dostring(ctl,write,buf,len,pos);
}
#define proc_dostring host_proc_dostring
'''
prefix += kernel_actual
bodies = [candidate.function(relative, name) for name in names]
results = [run_variant('candidate', candidate, bodies, True)]
if args.baseline:
    baseline = extract.Prepared(args.baseline)
    results.append(run_variant('old-source', baseline, [baseline.function(relative, name) for name in names], False))
if args.mutations:
    mutations = [
        ('unsigned-interface', 'int32_t if_num;', 'uint32_t if_num;'),
        ('ignore-send-error', '\t\treturn -EIO;', '\t\treturn 0;'),
        ('ignore-proc-error', 'if (ret || !write || !count)', 'if (!write || !count)'),
        ('missing-token-guard', ' || !cmd_buf', ''),
        ('missing-reference-release', '\tdev_put(dev);', '\t(void)dev;'),
        ('missing-position-guard', 'if (*ppos < 0 || (write && *ppos))', 'if (false)'),
    ]
    for label, old, new in mutations:
        if not any(old in body for body in bodies):
            raise RuntimeError('mutation anchor missing: ' + label)
        # All occurrences of the same faulty contract are changed deliberately.
        mutated = [body.replace(old, new) for body in bodies]
        results.append(run_variant(label, candidate, mutated, False))
(args.output / 'result.json').write_text(json.dumps({'qualification': 'Actual complete handlers, driver constants/enums and Linux _proc_do_string/proc_dostring; first-position warning, host API effects and numeric conversion contract substituted; no full kernel, firmware, concurrency or hardware qualification', 'kernel_sysctl': {'path':str(args.kernel_sysctl),'sha256':hashlib.sha256(args.kernel_sysctl.read_bytes()).hexdigest()}, 'sanitize': args.sanitize, 'driver': driver.manifest(), 'results': results}, indent=2) + '\n')
print(json.dumps({'variants': len(results), 'candidate': results[0]['stdout'], 'negative_variants': len(results)-1}))
