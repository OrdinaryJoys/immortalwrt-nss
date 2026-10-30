#!/usr/bin/env python3
"""Actual denied-port snapshot functions with explicit host RCU/bitmap effects."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('ecm', type=Path)
p.add_argument('--cc', default='cc')
p.add_argument('--sanitize', action='store_true')
p.add_argument('--mutations', action='store_true')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
prepared = extract.Prepared(a.ecm)
relative = 'frontends/ecm_front_end_common.c'
source = prepared.read(relative)
begin = source.index('#define ECM_FRONT_END_DENIED_PORTS_COUNT ')
end = source.index('/*\n * Predefined frontend and feature support map.', begin)
globals_actual = source[begin:end]
names = ['ecm_front_end_denied_ports_read', 'ecm_front_end_ports_denied',
         'ecm_front_end_denied_port_token', 'ecm_front_end_denied_ports_handler',
         'ecm_front_end_udp_denied_ports_handler', 'ecm_front_end_tcp_denied_ports_handler',
         'ecm_front_end_common_sysctl_unregister', 'ecm_front_end_check_udp_denied_ports',
         'ecm_front_end_check_tcp_denied_ports']
body = globals_actual + '\n'.join(prepared.function(relative, n) for n in names)
prefix = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <limits.h>
#include <ctype.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
typedef long long loff_t;
typedef uint64_t u64;
#define __rcu
#define GFP_KERNEL 0
#define DEFINE_MUTEX(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define check_add_overflow(a,b,c) __builtin_add_overflow(a,b,c)
struct ctl_table { void *data; int maxlen; };
struct ctl_table_header { int value; };
static struct ctl_table_header *ecm_front_end_ctl_tbl_hdr;
static _Thread_local int admin_depth, read_depth;
static pthread_rwlock_t grace_lock=PTHREAD_RWLOCK_INITIALIZER;
static pthread_mutex_t ledger_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned checks, failures, cases, unregisters;
static atomic_uint live_maps, publications;
static int fail_input, fail_bitmap, fail_output;
struct allocation { unsigned long *p; bool live, published, retired, safe; };
static struct allocation ledger[5000];
static unsigned ledger_count;
static pthread_mutex_t pause_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t pause_cv=PTHREAD_COND_INITIALIZER;
static bool pause_lookup, lookup_paused, release_lookup, grace_entered;
static atomic_bool writer_done;
static void require(bool ok) { if (!ok) { fprintf(stderr,"HOST_CONTRACT_FAILURE\n"); abort(); } }
static void check(bool ok, const char *label) { ++checks; if (!ok) { ++failures; fprintf(stderr,"FAIL %s\n",label); } }
static void mutex_lock(pthread_mutex_t *m) { require(!read_depth); require(pthread_mutex_lock(m)==0); ++admin_depth; }
static void mutex_unlock(pthread_mutex_t *m) { require(admin_depth>0); --admin_depth; require(pthread_mutex_unlock(m)==0); }
#define lockdep_is_held(p) (admin_depth>0)
static void rcu_read_lock(void) { require(!admin_depth); require(pthread_rwlock_rdlock(&grace_lock)==0); ++read_depth; }
static void rcu_read_unlock(void) { require(read_depth>0); --read_depth; require(pthread_rwlock_unlock(&grace_lock)==0); }
static struct allocation *find_map(unsigned long *p) {
    for (unsigned i=ledger_count;i>0;--i) if(ledger[i-1].p==p && ledger[i-1].live) return &ledger[i-1];
    return NULL;
}
static unsigned long *bitmap_zalloc(unsigned n, int flags) {
    (void)flags; require(admin_depth && n==65536);
    if (fail_bitmap) { --fail_bitmap; return NULL; }
    unsigned long *p=calloc((n+63)/64,sizeof(unsigned long)); require(p!=NULL);
    pthread_mutex_lock(&ledger_lock); require(ledger_count<5000);
    ledger[ledger_count++]=(struct allocation){.p=p,.live=true};
    pthread_mutex_unlock(&ledger_lock); atomic_fetch_add(&live_maps,1); return p;
}
static void bitmap_free(unsigned long *p) {
    if (!p) return;
    require(admin_depth);
    pthread_mutex_lock(&ledger_lock); struct allocation *m=find_map(p);
    require(m && (!m->retired || m->safe) && !m->published); m->live=false;
    pthread_mutex_unlock(&ledger_lock); atomic_fetch_sub(&live_maps,1); free(p);
}
static void publish(unsigned long **location, unsigned long *p) {
    require(admin_depth && !read_depth);
    pthread_mutex_lock(&ledger_lock);
    unsigned long *old=__atomic_load_n(location,__ATOMIC_ACQUIRE);
    if(old) { struct allocation *m=find_map(old); require(m && m->published); m->published=false; m->retired=true; m->safe=false; }
    if(p) { struct allocation *m=find_map(p); require(m && !m->published); m->published=true; }
    __atomic_store_n(location,p,__ATOMIC_RELEASE);
    pthread_mutex_unlock(&ledger_lock); atomic_fetch_add(&publications,1);
}
#define rcu_assign_pointer(p,v) publish(&(p),(v))
static unsigned long *read_map(unsigned long **location, bool protected) {
    require(protected ? admin_depth>0 : read_depth>0);
    return __atomic_load_n(location,__ATOMIC_ACQUIRE);
}
#define rcu_dereference(p) read_map(&(p),false)
#define rcu_dereference_protected(p,c) ((void)(c),read_map(&(p),true))
static void synchronize_rcu(void) {
    require(admin_depth && !read_depth);
    pthread_mutex_lock(&pause_lock); grace_entered=true; pthread_cond_broadcast(&pause_cv); pthread_mutex_unlock(&pause_lock);
    require(pthread_rwlock_wrlock(&grace_lock)==0);
    pthread_mutex_lock(&ledger_lock);
    for(unsigned i=0;i<ledger_count;++i) if(ledger[i].retired) ledger[i].safe=true;
    pthread_mutex_unlock(&ledger_lock); require(pthread_rwlock_unlock(&grace_lock)==0);
}
static bool raw_bit(unsigned long p,const unsigned long *map) { require(p<65536); return !!(map[p/64] & (1UL<<(p%64))); }
static bool test_bit(unsigned long p,const unsigned long *map) {
    require(read_depth>0);
    pthread_mutex_lock(&pause_lock);
    if(pause_lookup) { lookup_paused=true; pthread_cond_broadcast(&pause_cv); while(!release_lookup) pthread_cond_wait(&pause_cv,&pause_lock); }
    pthread_mutex_unlock(&pause_lock);
    return raw_bit(p,map);
}
static void __set_bit(unsigned p,unsigned long *map) { require(admin_depth && p<65536); map[p/64]|=1UL<<(p%64); }
static void __clear_bit(unsigned p,unsigned long *map) { require(admin_depth && p<65536); map[p/64]&=~(1UL<<(p%64)); }
static void bitmap_copy(unsigned long *d,const unsigned long *s,unsigned n) { require(admin_depth && n==65536); memcpy(d,s,n/8); }
static void bitmap_zero(unsigned long *d,unsigned n) { require(admin_depth && n==65536); memset(d,0,n/8); }
static bool bitmap_empty(const unsigned long *d,unsigned n) { require(admin_depth && n==65536); for(unsigned i=0;i<n/64;++i) if(d[i]) return false; return true; }
static bool bitmap_equal(const unsigned long *d,const unsigned long *s,unsigned n) { require(admin_depth && n==65536); return !memcmp(d,s,n/8); }
static unsigned bitmap_weight(const unsigned long *d,unsigned n) { require(admin_depth && n==65536); unsigned count=0;for(unsigned i=0;i<n/64;++i)count+=(unsigned)__builtin_popcountl(d[i]);return count; }
#define for_each_set_bit(p,map,n) for((p)=0;(p)<(n);++(p)) if(raw_bit((p),(map)))
static void *kvzalloc(size_t n,int flags) { (void)flags; require(admin_depth); if(fail_output){--fail_output;return NULL;} return calloc(1,n); }
#define kvfree free
#define kfree free
static char *kmemdup_nul(const void *p,size_t n,int flags) { (void)flags; if(fail_input){--fail_input;return NULL;} char *d=malloc(n+1); require(d!=NULL);memcpy(d,p,n);d[n]=0;return d; }
static int scnprintf(char *p,size_t n,const char *fmt,...) {
    va_list ap;va_start(ap,fmt);int r=vsnprintf(p,n,fmt,ap);va_end(ap);return n?(r<(int)n?r:(int)n-1):0;
}
static ssize_t memory_read_from_buffer(void *to,size_t count,loff_t *pos,const void *from,size_t available) {
    if(*pos<0)return -EINVAL;
    if((unsigned long long)*pos>=available)return 0;
    size_t n=available-(size_t)*pos;if(n>count)n=count;memcpy(to,(const char *)from+*pos,n);*pos+=(loff_t)n;return (ssize_t)n;
}
static int kstrtouint(const char *s,unsigned base,unsigned *out) {
    char *end;errno=0;if(!*s || *s=='-')return -EINVAL;unsigned long v=strtoul(s,&end,base);
    if(errno || v>UINT_MAX)return -ERANGE;
    if(*end || end==s)return -EINVAL;
    *out=(unsigned)v;return 0;
}
static void unregister_sysctl_table(struct ctl_table_header *h) { require(h!=NULL);++unregisters; }
'''
main = r'''
static int command(bool udp,const void *input,size_t length,loff_t *pos) {
    size_t count=length;struct ctl_table ctl={0};
    int ret=udp?ecm_front_end_udp_denied_ports_handler(&ctl,1,(void *)input,&count,pos):ecm_front_end_tcp_denied_ports_handler(&ctl,1,(void *)input,&count,pos);
    check(count==length,"write-count-unchanged");return ret;
}
static void write_ok(bool udp,const char *input) { ++cases;loff_t pos=0;size_t n=strlen(input);check(command(udp,input,n,&pos)==0 && pos==(loff_t)n,"write-success"); }
static size_t read_all(bool udp,char *out,size_t size,loff_t *pos,int expected) {
    struct ctl_table ctl={0};size_t n=size;int ret=udp?ecm_front_end_udp_denied_ports_handler(&ctl,0,out,&n,pos):ecm_front_end_tcp_denied_ports_handler(&ctl,0,out,&n,pos);
    check(ret==expected,"read-status");return n;
}
static void *paused_reader(void *unused) { (void)unused;bool result=ecm_front_end_check_udp_denied_ports(80,1);return (void *)(uintptr_t)result; }
static void *remove_writer(void *unused) { (void)unused;loff_t pos=0;size_t n=6;struct ctl_table ctl={0};int r=ecm_front_end_udp_denied_ports_handler(&ctl,1,"del 80",&n,&pos);require(r==0);atomic_store(&writer_done,true);return NULL; }
static void *add_writer(void *id) { char cmd[32];snprintf(cmd,sizeof(cmd),"add %u",300+(unsigned)(uintptr_t)id);loff_t pos=0;size_t n=strlen(cmd);struct ctl_table ctl={0};require(ecm_front_end_tcp_denied_ports_handler(&ctl,1,cmd,&n,&pos)==0);return NULL; }
int main(void) {
    ++cases;check(!ecm_front_end_check_udp_denied_ports(0,65535) && !ecm_front_end_check_tcp_denied_ports(53,80),"empty-fast-path");
    char empty[4]={0};loff_t empty_pos=0;fail_output=1;++cases;check(read_all(true,empty,sizeof(empty),&empty_pos,0)==0 && fail_output==1,"empty-read-no-allocation");fail_output=0;
    write_ok(true,"add 0 53 80 65535\n");
    empty_pos=0;fail_output=1;++cases;check(read_all(true,empty,0,&empty_pos,0)==0 && fail_output==1,"zero-read-no-allocation");fail_output=0;
    ++cases;check(ecm_front_end_check_udp_denied_ports(53,1) && ecm_front_end_check_udp_denied_ports(1,80),"both-directions");check(ecm_front_end_check_udp_denied_ports(0,1) && ecm_front_end_check_udp_denied_ports(1,65535),"port-boundaries");check(!ecm_front_end_check_tcp_denied_ports(53,80),"protocol-isolation");
    unsigned pubs=atomic_load(&publications);write_ok(true,"add 80 80");check(atomic_load(&publications)==pubs,"idempotent-no-publication");
    const char *invalid[]={"add","del","bad 1","add -1","add +1","add 65536","add 4294967295","add 4294967296","add 1x","add 81 bad","del 53 bad","add *","del * bad","del 53 *","del *suffix"," \t\n"};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i){++cases;loff_t pos=0;pubs=atomic_load(&publications);check(command(true,invalid[i],strlen(invalid[i]),&pos)==-EINVAL && pos==0,"invalid-command");check(atomic_load(&publications)==pubs && ecm_front_end_check_udp_denied_ports(53,80) && !ecm_front_end_check_udp_denied_ports(81,81),"invalid-batch-no-effects");}
    ++cases;const char nul[]={'a','d','d',' ',0,'8','1'};loff_t pos=0;check(command(true,nul,sizeof(nul),&pos)==-EINVAL && pos==0,"embedded-nul");
    char raw[513];memset(raw,' ',sizeof(raw));memcpy(raw,"add 6",5);pos=0;++cases;check(command(true,raw,512,&pos)==0 && pos==512 && ecm_front_end_check_udp_denied_ports(6,6),"full-nonterminated-input");
    pos=0;++cases;check(command(true,raw,513,&pos)==-EINVAL && pos==0,"oversized-input");
    pos=1;++cases;check(command(true,"add 81",6,&pos)==-EINVAL && pos==1,"nonzero-write");pos=-1;++cases;check(command(true,"add 81",6,&pos)==-EINVAL && pos==-1,"negative-write");pos=LLONG_MAX;++cases;check(command(true,"add 81",6,&pos)==-EINVAL && pos==LLONG_MAX,"large-position");
    pos=0;++cases;check(command(true,"",0,&pos)==0 && pos==0,"zero-write-noop");
    fail_input=1;pos=0;++cases;check(command(true,"add 81",6,&pos)==-ENOMEM && pos==0,"input-allocation-failure");
    fail_bitmap=1;pos=0;++cases;check(command(true,"add 81",6,&pos)==-ENOMEM && pos==0 && !ecm_front_end_check_udp_denied_ports(81,81),"map-allocation-failure");
    char output[64]={0};pos=0;++cases;size_t n=read_all(true,output,3,&pos,0);check(n==3 && pos==3 && !memcmp(output,"0 6",3),"read-first");n=read_all(true,output,sizeof(output),&pos,0);const char *tail=" 53 80 65535 \n";check(n==strlen(tail) && pos==(loff_t)(3+strlen(tail)) && !memcmp(output,tail,strlen(tail)),"read-continuation");n=read_all(true,output,sizeof(output),&pos,0);check(n==0,"read-eof");
    pos=-1;++cases;read_all(true,output,sizeof(output),&pos,-EINVAL);check(pos==-1,"negative-read");fail_output=1;pos=0;++cases;read_all(true,output,sizeof(output),&pos,-ENOMEM);check(pos==0,"read-allocation-failure");
    write_ok(true,"del 0 65535 6");write_ok(false,"add 443");check(!ecm_front_end_check_udp_denied_ports(0,65535) && ecm_front_end_check_tcp_denied_ports(443,1),"delete-protocol-separation");
    pthread_t reader,writer;pause_lookup=true;require(pthread_create(&reader,NULL,paused_reader,NULL)==0);
    pthread_mutex_lock(&pause_lock);while(!lookup_paused)pthread_cond_wait(&pause_cv,&pause_lock);grace_entered=false;pthread_mutex_unlock(&pause_lock);
    require(pthread_create(&writer,NULL,remove_writer,NULL)==0);pthread_mutex_lock(&pause_lock);while(!grace_entered)pthread_cond_wait(&pause_cv,&pause_lock);++cases;check(!atomic_load(&writer_done),"writer-waits-for-old-reader");release_lookup=true;pthread_cond_broadcast(&pause_cv);pthread_mutex_unlock(&pause_lock);
    void *reader_result;require(pthread_join(reader,&reader_result)==0);require(pthread_join(writer,NULL)==0);pause_lookup=false;check((uintptr_t)reader_result==1 && !ecm_front_end_check_udp_denied_ports(80,1),"old-snapshot-completes-before-free");
    pthread_t writers[16];for(unsigned i=0;i<16;++i)require(pthread_create(&writers[i],NULL,add_writer,(void *)(uintptr_t)i)==0);for(unsigned i=0;i<16;++i)require(pthread_join(writers[i],NULL)==0);++cases;for(unsigned i=0;i<16;++i)check(ecm_front_end_check_tcp_denied_ports(300+i,1),"concurrent-writers-no-lost-update");
    write_ok(true,"del *");pos=0;check(read_all(true,output,sizeof(output),&pos,0)==0 && !ecm_front_end_check_udp_denied_ports(53,80),"clear-empty");
    char batch[512];size_t used=4;memcpy(batch,"add ",4);
    for(unsigned port=0;port<65536;++port){char token[8];int length=snprintf(token,sizeof(token),"%u ",port);if(used+(size_t)length>sizeof(batch)){++cases;pos=0;check(command(true,batch,used,&pos)==0,"full-table-batch");used=4;}memcpy(batch+used,token,(size_t)length);used+=(size_t)length;}
    ++cases;pos=0;check(command(true,batch,used,&pos)==0,"full-table-last-batch");
    for(unsigned port=0;port<65536;++port)check(ecm_front_end_check_udp_denied_ports((uint16_t)port,(uint16_t)port),"all-ports-present");
    char *large=calloc(1,ECM_FRONT_END_DENIED_PORTS_TEXT_SIZE+1);require(large!=NULL);pos=0;++cases;n=read_all(true,large,ECM_FRONT_END_DENIED_PORTS_TEXT_SIZE,&pos,0);size_t expected=1;for(unsigned port=0;port<65536;++port){char token[8];expected+=(size_t)snprintf(token,sizeof(token),"%u ",port);}check(n==expected && n>512 && large[n-1]=='\n',"complete-bounded-output");free(large);
    static struct ctl_table_header header;ecm_front_end_ctl_tbl_hdr=&header;++cases;ecm_front_end_common_sysctl_unregister();check(unregisters==1 && !ecm_front_end_ctl_tbl_hdr && !atomic_load(&live_maps),"exit-retires-both-maps");ecm_front_end_common_sysctl_unregister();check(unregisters==1 && !atomic_load(&live_maps),"idempotent-exit");
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u,\"live_maps\":%u}\n",cases,checks,failures,atomic_load(&live_maps));return failures?1:0;
}
'''

def run(name, code, expected):
    out = a.output / name
    out.mkdir()
    generated = out / 'actual-functions.c'
    generated.write_text(prefix + code + main)
    command = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-pthread']
    if not expected:
        command += ['-Wno-unused-function']
    if a.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    command += [str(generated), '-o', str(out / 'fixture')]
    built = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (out / 'compile.log').write_text(built.stdout)
    if built.returncode:
        raise RuntimeError(name + ': compile failure is not a negative runtime control')
    env = os.environ.copy()
    env['ASAN_OPTIONS'] = 'detect_leaks=0'
    env['UBSAN_OPTIONS'] = 'halt_on_error=1'
    executed = subprocess.run([str(out / 'fixture')], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=60)
    (out / 'stdout.log').write_text(executed.stdout)
    (out / 'stderr.log').write_text(executed.stderr)
    if (executed.returncode == 0) != expected:
        raise RuntimeError(name + ': unexpected status ' + str(executed.returncode))
    if expected:
        data = json.loads(executed.stdout)
        if data['cases'] != 799 or data['checks'] < 65000 or data['failures'] or data['live_maps'] or executed.stderr:
            raise RuntimeError(name + ': incomplete/diagnostic-positive run')
    return {'name': name, 'compiler': command, 'expected_pass': expected, 'returncode': executed.returncode, 'stdout': executed.stdout}

results = [run('candidate', body, True)]
if a.mutations:
    mutations = [
        ('no-grace-before-free', '\t\tsynchronize_rcu();', '\t\t(void)0;'),
        ('no-port-bound', ' || port >= ECM_FRONT_END_DENIED_PORTS_COUNT', ''),
        ('invalid-batch-success', '\tint ret = -EINVAL;', '\tint ret = 0;'),
        ('small-read-buffer', 'capacity = (size_t)bitmap_weight(ports, ECM_FRONT_END_DENIED_PORTS_COUNT) * 6 + 2;', 'capacity = 512;'),
        ('protocol-alias', '&ecm_front_end_tcp_denied_ports);', '&ecm_front_end_udp_denied_ports);'),
    ]
    for name, old, new in mutations:
        if old not in body:
            raise RuntimeError('missing mutation anchor ' + name)
        results.append(run(name, body.replace(old, new), False))
(a.output / 'result.json').write_text(json.dumps({'qualification': 'Actual complete snapshot/admin/packet wrappers/exit functions; bitmap, memory, mutex and RCU semantics substituted with checked host APIs and pthread grace model. No Linux RCU scheduler, full module, target, firmware or performance qualification.', 'input':prepared.manifest(), 'sanitize':a.sanitize, 'results':results}, indent=2) + '\n')
print(json.dumps({'variants':len(results),'candidate':results[0]['stdout']}))
