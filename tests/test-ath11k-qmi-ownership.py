#!/usr/bin/env python3
"""Actual prepared functions; modeled Linux work/lock primitives, not a kernel test."""
import argparse
import hashlib
import importlib.util
import json
import re
import shlex
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('extract_c',ROOT/'nss-dp-containment/extract_prepared_c.py')
extract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared',type=Path)
parser.add_argument('--baseline',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cc',default='cc',help='host compiler command, for GCC/Clang qualification')
parser.add_argument('--sanitize',action='store_true')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)

def definition(text,name):
    matches=list(re.finditer(r'^(?:static\s+)?(?:int|void|bool)\s+'+re.escape(name)+r'\([^;{}]*\)\s*\{',extract.code_mask(text),re.M))
    if len(matches)!=1:raise ValueError('ambiguous function '+name)
    match=matches[0]
    return text[match.start():extract.block_end(text,match.end()-1)]+'\n'

PREFIX=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define READ_ONCE(v) (v)
#define ATH11K_FLAG_REGISTERED 0
#define ATH11K_FLAG_QMI_FAIL 1
#define ATH11K_FLAG_UNREGISTERING 2
#define ATH11K_FLAG_CRASH_FLUSH 3
#define ATH11K_FLAG_RECOVERY 4
#define ATH11K_QMI_RESP_LEN_MAX 1024
#define ATH11K_QMI_WLFW_SERVICE_ID_V01 1
#define ATH11K_QMI_WLFW_SERVICE_VERS_V01 1
#define ATH11K_QMI_EVENT_FW_READY 1
#define ATH11K_DBG_QMI 0
#define GFP_ATOMIC 0
#define test_bit(n,p) (!!(*(p)&(1UL<<(n))))
#define set_bit(n,p) (*(p)|=1UL<<(n))
#define clear_bit(n,p) (*(p)&=~(1UL<<(n)))
#define mutex_init(p) (*(p)=0)
#define mutex_lock(p) assert(!(*(p))++)
#define mutex_unlock(p) assert((*(p))--==1)
#define spin_lock_init(p) (*(p)=0)
#define spin_lock(p) mutex_lock(p)
#define spin_unlock(p) mutex_unlock(p)
#define init_waitqueue_head(p) (*(p)=0)
#define atomic_set(p,v) (*(p)=(v))
#define atomic_read(p) (*(p))
#define wait_event(q,c) do {(void)(q);assert(c);} while(0)
#define ath11k_warn(...) ((void)0)
#define ath11k_err(...) ((void)0)
#define ath11k_dbg(...) ((void)0)
struct list_head {struct list_head *next,*prev;};
#define INIT_LIST_HEAD(p) do {(p)->next=(p);(p)->prev=(p);} while(0)
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
static void list_add_tail(struct list_head *n,struct list_head *h) {n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *n) {n->prev->next=n->next;n->next->prev=n->prev;}
static void list_splice_init(struct list_head *h,struct list_head *d) {
    if(h->next!=h) {d->next=h->next;d->prev=h->prev;d->next->prev=d;d->prev->next=d;INIT_LIST_HEAD(h);}
}
#define list_for_each_entry_safe(p,n,h,m) \
 for(p=container_of((h)->next,__typeof__(*p),m),n=container_of(p->m.next,__typeof__(*p),m); \
 &p->m!=(h);p=n,n=container_of(n->m.next,__typeof__(*n),m))
enum ath11k_qmi_event_type {TEST_EVENT};
struct ath11k_qmi_driver_event {enum ath11k_qmi_event_type type;void *data;struct list_head list;};
struct target_info {int unused;};
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
#define __iomem
HOST_TARGET_MEMORY_LAYOUT
struct qmi_handle {int live;};
struct work_struct {int queued;};
struct ath11k_base;
struct ath11k_qmi {struct ath11k_base *ab;struct qmi_handle handle;struct target_info target;
    struct target_mem_chunk target_mem[ATH11K_QMI_WLANFW_MAX_NUM_MEM_SEG_V01];void *event_wq;struct work_struct event_work;
    struct list_head event_list;int target_mem_mode,service_ins_id,event_lock,cb_lock,cb_waitq,cb_active;
    bool cb_closing,cb_initialized,event_closing;};
struct ath11k_base {struct ath11k_qmi qmi;unsigned long dev_flags;struct {int fw_mem_mode;bool cbcal_restart_fw;} hw_params;};
struct platform_device {struct ath11k_base *ab;};
static int ath11k_qmi_ops,ath11k_qmi_msg_handlers[1];
static int failure,queues,handles,event_allocs,releases,release_post_result,ready_error,ready_calls,checks;
static struct ath11k_base *current;
static int ath11k_qmi_driver_event_post(struct ath11k_qmi *,enum ath11k_qmi_event_type,void *);
static void ath11k_qmi_deinit_service(struct ath11k_base *);
static void *allocate(size_t n) {void *p=calloc(1,n);assert(p);event_allocs++;return p;}
static void release(void *p) {if(p){event_allocs--;free(p);}}
#define kzalloc(n,f) allocate(n)
#define kfree release
#define INIT_WORK(w,f) ((w)->queued=0)
static void *alloc_ordered_workqueue(const char *n,int f) {(void)n;(void)f;if(failure==1)return NULL;queues++;return (void*)1;}
static void destroy_workqueue(void *p) {assert(p&&queues==1);queues--;}
static void queue_work(void *q,struct work_struct *w) {assert(q&&queues==1);w->queued=1;}
static void cancel_work_sync(struct work_struct *w) {assert(handles==1);w->queued=0;}
static int qmi_handle_init(struct qmi_handle *h,int n,int *o,int *m) {
    (void)n;(void)o;(void)m;if(failure==2)return -EIO;h->live=1;handles++;return 0;
}
static int qmi_add_lookup(struct qmi_handle *h,int a,int b,int c) {
    (void)h;(void)a;(void)b;(void)c;
    if(failure==3){ath11k_qmi_driver_event_post(&current->qmi,TEST_EVENT,NULL);return -EIO;}return 0;
}
static void qmi_handle_release(struct qmi_handle *h) {
    assert(h->live&&handles==1);releases++;
    release_post_result=ath11k_qmi_driver_event_post(&current->qmi,TEST_EVENT,NULL);
    h->live=0;handles--;
}
static void ath11k_qmi_m3_free(struct ath11k_base *a) {(void)a;}
static void ath11k_qmi_free_target_mem_chunk(struct ath11k_base *a) {(void)a;}
static void *platform_get_drvdata(struct platform_device *p) {return p->ab;}
static void ath11k_ahb_remove_prepare(struct ath11k_base *a) {set_bit(ATH11K_FLAG_UNREGISTERING,&a->dev_flags);}
static void ath11k_ahb_power_down(struct ath11k_base *a,bool s) {(void)a;(void)s;}
static void ath11k_debugfs_soc_destroy(struct ath11k_base *a) {(void)a;}
static void ath11k_core_pm_notifier_unregister(struct ath11k_base *a) {(void)a;}
static void ath11k_fw_destroy(struct ath11k_base *a) {(void)a;}
static void ath11k_ahb_free_resources(struct ath11k_base *a) {(void)a;assert(!handles&&!queues&&!event_allocs);}
static void ath11k_core_deinit(struct ath11k_base *a) {ath11k_qmi_deinit_service(a);}
static int ath11k_core_qmi_firmware_ready(struct ath11k_base *a) {(void)a;ready_calls++;return ready_error;}
static void check(bool ok) {checks++;if(!ok){fprintf(stderr,"ownership invariant failed at check %d\n",checks);exit(1);}}
'''

MAIN=r'''
int main(void) {
    struct ath11k_base ab={0};struct platform_device p={&ab};current=&ab;
    for(failure=1;failure<=3;failure++) {
        memset(&ab,0,sizeof(ab));
        int ret=ath11k_qmi_init_service(&ab);
        check(ret<0);check(!handles&&!queues&&!event_allocs);
    }
    failure=0;memset(&ab,0,sizeof(ab));check(!ath11k_qmi_init_service(&ab));
    check(!ath11k_qmi_driver_event_post(&ab.qmi,TEST_EVENT,NULL));
    ath11k_qmi_deinit_service(&ab);
    check(release_post_result==-ESHUTDOWN);check(!handles&&!queues&&!event_allocs);
    int previous=releases;ath11k_qmi_deinit_service(&ab);check(releases==previous);
    for(int remove=0;remove<2;remove++) for(int registered=0;registered<2;registered++) {
        memset(&ab,0,sizeof(ab));check(!ath11k_qmi_init_service(&ab));
        if(registered)set_bit(ATH11K_FLAG_REGISTERED,&ab.dev_flags);
        if(remove)ath11k_ahb_remove(&p);else ath11k_ahb_shutdown(&p);
        check(!handles&&!queues&&!event_allocs);
    }
    memset(&ab,0,sizeof(ab));ready_calls=0;ready_error=-EIO;
    ready_event(&ab);check(!test_bit(ATH11K_FLAG_REGISTERED,&ab.dev_flags));
    check(test_bit(ATH11K_FLAG_QMI_FAIL,&ab.dev_flags));check(ready_calls==1);
    memset(&ab,0,sizeof(ab));ready_calls=0;ready_error=0;
    ready_event(&ab);check(test_bit(ATH11K_FLAG_REGISTERED,&ab.dev_flags));check(ready_calls==1);
    ready_event(&ab);check(ready_calls==1);
    ab.hw_params.cbcal_restart_fw=true;clear_bit(ATH11K_FLAG_REGISTERED,&ab.dev_flags);
    ready_event(&ab);check(!test_bit(ATH11K_FLAG_REGISTERED,&ab.dev_flags)&&ready_calls==1);
    struct test_dp tx={0};
    for(int i=0;i<DP_TCL_NUM_RING_MAX;i++)tx.tx_ring[i].tx_status=allocate(16);
    tx_status_free(&tx);check(!event_allocs);
    tx_status_free(&tx);check(!event_allocs);
    puts("QMI ownership/failure/late-del_server/shutdown/FW_READY checks passed");
    printf("{\"checks\":%d,\"kernel_primitives_modeled\":true,\"real_concurrency\":false}\n",checks);
    return 0;
}
'''
records=[]
for label,tree,must_pass in [('candidate',args.prepared,True)]+([('baseline',args.baseline,False)] if args.baseline else []):
    wifi=tree/'drivers/net/wireless/ath/ath11k'
    qmi=(wifi/'qmi.c').read_text();ahb=(wifi/'ahb.c').read_text()
    header=(wifi/'qmi.h').read_text()
    limit=re.search(r'^#define ATH11K_QMI_WLANFW_MAX_NUM_MEM_SEG_V01\s+\d+\s*$',header,re.M)
    if limit is None:raise ValueError('missing target memory array limit')
    # Keep the actual array element layout: shrinking it to int[4] creates a
    # GCC memset-elt-size diagnostic absent from the real prepared structure.
    layout=limit.group()+'\n'+extract.structure(header,'target_mem_chunk')
    pieces=[PREFIX.replace('HOST_TARGET_MEMORY_LAYOUT',layout)]
    for name in ('ath11k_qmi_driver_event_post','ath11k_qmi_cb_close','ath11k_qmi_driver_event_purge','ath11k_qmi_deinit_service','ath11k_qmi_init_service'):
        pieces.append(definition(qmi,name))
    for name in ('ath11k_ahb_remove','ath11k_ahb_shutdown'):
        pieces.append(definition(ahb,name))
    case=qmi.split('case ATH11K_QMI_EVENT_FW_READY:',1)[1].split('case ATH11K_QMI_EVENT_COLD_BOOT_CAL_DONE:',1)[0]
    pieces.append('static void ready_event(struct ath11k_base *ab) {int ret __attribute__((unused));switch(1){case 1:'+case+'}}\n')
    dp=(wifi/'dp.c').read_text()
    free=definition(dp,'ath11k_dp_free')
    needle='for (i = 0; i < DP_TCL_NUM_RING_MAX; i++) {'
    start=free.rindex(needle)
    opening=free.index('{',start)
    block=free[start:extract.block_end(free,opening)]
    limit=re.search(r'^#define DP_TCL_NUM_RING_MAX\s+\d+', (wifi/'dp.h').read_text(),re.M).group()
    pieces.append(limit+'\nstruct test_dp {struct {void *tx_status;} tx_ring[DP_TCL_NUM_RING_MAX];};\n')
    pieces.append('static void tx_status_free(struct test_dp *dp) {int i;'+block+'}\n')
    pieces.append(MAIN)
    c=args.output/(label+'.c');c.write_text('\n'.join(pieces))
    command=shlex.split(args.cc)+['-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(c),'-o',str(c.with_suffix(''))]
    if args.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
    result=subprocess.run(command,capture_output=True,timeout=60)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(c.with_suffix(''))],capture_output=True,timeout=30)
    (args.output/(label+'.stdout')).write_bytes(result.stdout);(args.output/(label+'.stderr')).write_bytes(result.stderr)
    if (result.returncode==0)!=must_pass:raise SystemExit('unexpected '+label+' result: '+result.stderr.decode())
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:',result.stderr):
        raise SystemExit('sanitizer failure is not a valid assertion negative control: '+label)
    records.append(dict(label=label,returncode=result.returncode,expected_pass=must_pass,command=command,
        qmi_sha256=hashlib.sha256(qmi.encode()).hexdigest(),ahb_sha256=hashlib.sha256(ahb.encode()).hexdigest(),
        qmi_header_sha256=hashlib.sha256(header.encode()).hexdigest(),layout_sha256=hashlib.sha256(layout.encode()).hexdigest()))
(args.output/'RESULT.json').write_text(json.dumps(dict(results=records,scope='actual functions and resource effects; work/locks modeled, not kernel concurrency or full recovery qualification'),indent=2)+'\n')
print(json.dumps(records,indent=2))
