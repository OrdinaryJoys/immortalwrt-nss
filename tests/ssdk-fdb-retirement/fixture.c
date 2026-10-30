#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define A_TRUE 1
#define A_FALSE 0
#define SW_OK 0
#define SW_FAIL -1
#define SW_BUSY -2
#define SW_NOT_SUPPORTED -3
#define SW_NO_RESOURCE -4
#define HW_ENTRY 1
#define REF_FDB_MAC_NEW 1
#define REF_FDB_MAC_OLD 2
#define REF_FDB_MAC_EXPIRE 3
#define SSDK_DEBUG(...) ((void)0)
#define SSDK_ERROR(...) ((void)0)
#define SSDK_INFO(...) ((void)0)
#define SW_MACSTR ""
#define SW_MAC2STR(x) 0
#define EXPORT_SYMBOL(x)
#define GFP_KERNEL 0
#define GFP_ATOMIC 1
#define ETH_ALEN 6
#define IFNAMSIZ 16
#define SSDK_PHYSICAL_PORT1 1
#define SSDK_PHYSICAL_PORT6 6
#define FAL_SWITCH_INTR_LINK_STATUS 1
#define FAL_SWITCH_INTR_FDB_CHANGE 2
#define FAL_PHY_INTR_STATUS_UP_CHANGE 1
#define FAL_PHY_INTR_STATUS_DOWN_CHANGE 2
#define QCA_FDB_SW_SYNC_WORK_DELAY 100
#define IRQ_HANDLED 1
#define BIT(x) (1U<<(x))
#define SW_PBMP_OR(a,b) ((a)|=(b))
#define SW_PBMP_AND(a,b) ((a)&=(b))
#define SW_IS_PBMP_MEMBER(a,b) ((a)&BIT(b))
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_NO_RESOURCE; } while(0)
#define SW_RTN_ON_ERROR(r) do { if ((r)!=SW_OK) return (r); } while(0)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define msecs_to_jiffies(x) (x)
typedef unsigned int a_uint32_t;
typedef unsigned char a_uint8_t;
typedef int a_bool_t;
typedef int sw_error_t;
typedef unsigned int fal_pbmp_t;
typedef int irqreturn_t;
typedef uint32_t __be32;
typedef uint32_t u32;
static atomic_uint checks,cases;
static atomic_uint control_attempts,fdb_attempts,wait_entries,sys_remove_entries;
static atomic_uint fdb_cancel_entries,notify_wait_entries;
static void check(bool ok,const char *why) {
    atomic_fetch_add(&checks,1);
    if(!ok){fprintf(stderr,"SSDK_FDB %s\n",why);exit(86);}
}
static _Thread_local void *held[32];
static _Thread_local unsigned held_n,bh;
struct mutex { pthread_mutex_t p; bool initialized; };
#define DEFINE_MUTEX(n) struct mutex n={PTHREAD_MUTEX_INITIALIZER,true}
typedef struct mutex spinlock_t;
typedef spinlock_t aos_lock_t;
#define DEFINE_SPINLOCK(n) spinlock_t n={PTHREAD_MUTEX_INITIALIZER,true}
static bool owns(void *p) { for(unsigned i=0;i<held_n;i++)if(held[i]==p)return true;return false; }
static void mutex_init(struct mutex *p) { check(!p->initialized,"lock-construct-once");check(!pthread_mutex_init(&p->p,NULL),"pthread-init");p->initialized=true; }
static void lock_raw(struct mutex *p) { check(p->initialized&&!owns(p),"lock-valid-nonrecursive");check(!pthread_mutex_lock(&p->p),"pthread-lock");check(held_n<32,"lock-stack");held[held_n++]=p; }
static void unlock_raw(struct mutex *p) { check(held_n&&held[held_n-1]==p,"lock-pair");--held_n;check(!pthread_mutex_unlock(&p->p),"pthread-unlock"); }
static void note_mutex_attempt(void *p);
static void mutex_lock(struct mutex *p){check(!bh,"sleep-outside-bh");note_mutex_attempt(p);lock_raw(p);}
static void mutex_unlock(struct mutex *p){unlock_raw(p);}
#define spin_lock_init(p) mutex_init(p)
static void spin_lock_model(spinlock_t *p){lock_raw(p);++bh;}
static void post_unlock(void *p);
static void spin_unlock_model(spinlock_t *p){check(bh>0,"bh-balance");--bh;unlock_raw(p);post_unlock(p);}
#define spin_lock_irqsave(p,f) do{(f)=0;spin_lock_model(p);}while(0)
#define spin_unlock_irqrestore(p,f) do{(void)(f);spin_unlock_model(p);}while(0)
#define aos_lock_init(p) mutex_init(p)
#define aos_lock_bh(p) spin_lock_model(p)
#define aos_unlock_bh(p) spin_unlock_model(p)
typedef struct { pthread_mutex_t p;pthread_cond_t c; } wait_queue_head_t;
#define DECLARE_WAIT_QUEUE_HEAD(n) wait_queue_head_t n={PTHREAD_MUTEX_INITIALIZER,PTHREAD_COND_INITIALIZER}
static void init_waitqueue_head(wait_queue_head_t *p){check(!pthread_mutex_init(&p->p,NULL)&&!pthread_cond_init(&p->c,NULL),"wait-init");}
static void check_wait_live(void *p);
static void wake_up_all(wait_queue_head_t *p){check_wait_live(p);pthread_mutex_lock(&p->p);pthread_cond_broadcast(&p->c);pthread_mutex_unlock(&p->p);}
static void note_wait_queue(void *p);
#define wait_event(q,cond) do{check(!bh,"wait-outside-bh");note_wait_queue(&(q));pthread_mutex_lock(&(q).p);while(!(cond))pthread_cond_wait(&(q).c,&(q).p);pthread_mutex_unlock(&(q).p);}while(0)
struct list_head {struct list_head *next,*prev;};
#define INIT_LIST_HEAD(p) do{(p)->next=(p);(p)->prev=(p);}while(0)
static void list_add_tail(struct list_head *n,struct list_head *h){check(bh>0,"fdb-list-lock");n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *n){check(bh>0,"fdb-list-lock");n->prev->next=n->next;n->next->prev=n->prev;}
#define list_for_each_entry_safe(p,n,h,m) for(check(bh>0,"fdb-list-lock"),(p)=container_of((h)->next,__typeof__(*(p)),m),(n)=container_of((p)->m.next,__typeof__(*(p)),m);&(p)->m!=(h);(p)=(n),(n)=container_of((n)->m.next,__typeof__(*(n)),m))
typedef struct {struct {unsigned char uc[6];}addr;struct{unsigned id;}port;unsigned fid,type;} fal_fdb_entry_t;
typedef struct {int unused;} fal_fdb_op_t;
typedef struct {struct list_head list;fal_fdb_entry_t entry;unsigned state;bool notified;} ref_fdb_info_t;
struct work_struct {void(*fn)(struct work_struct *);pthread_mutex_t p;pthread_cond_t c;bool initialized,pending,running,cancelling;unsigned constructs;};
struct delayed_work {struct work_struct work;};
/* ACTUAL_ENUM */
struct qca_phy_priv {
/* ACTUAL_FIELDS */
};
struct sk_buff {int owned;};
struct nlattr {unsigned char value;char name[16];};
struct genl_info {struct nlattr *attrs[4];};
struct nla_policy {int type,len;};
struct genl_ops {int cmd;struct nla_policy *policy;int(*doit)(struct sk_buff *,struct genl_info *);};
struct genl_multicast_group {char name[32];};
struct genl_family {void *module;int hdrsize,version,maxattr;char name[32];struct nla_policy *policy;bool netnsok,parallel_ops;void *pre_doit,*post_doit;struct genl_ops *ops;unsigned n_ops;struct genl_multicast_group *mcgrps;unsigned n_mcgrps,mcgrp_offset;};
#define THIS_MODULE ((void *)0x1234)
#define NLA_NUL_STRING 1
#define NLA_BINARY 2
#define NLA_U8 3
#define SSDK_ATTR_IFNAME 1
#define SSDK_ATTR_MACADDR 2
#define SSDK_ATTR_MACPOLL 3
#define SSDK_ATTR_MAX 3
#define SSDK_COMMAND_NEW_MAC 1
#define SSDK_COMMAND_EXPIRE_MAC 2
#define SSDK_COMMAND_POLL_MAC 3
#define SSDK_GENL_MCAST_GRP_NAME "ssdk_mc"
#define SSDK_GENL_FAMILY_NAME "ssdk"
#define SSDK_GENL_VERSION 1
struct attribute {const char *name;};
struct device_attribute {struct attribute attr;};
#define __ATTR(n,m,s,t) {{#n}}
struct kobject {int owned;};
struct device_node {int unused;};
/* ACTUAL_PROTOTYPES */
/* ACTUAL_GLOBALS */
static DEFINE_MUTEX(model_core);
static atomic_uint scans,notifications,irq_frees,irq_enables,irq_disables,cancel_calls,hw_frees,priv_gets;
static atomic_bool stop_done;
static void note_wait_queue(void *p)
{
    atomic_fetch_add(&wait_entries,1);
    if(p==&ssdk_genl_notify_wait)atomic_fetch_add(&notify_wait_entries,1);
}
static void note_mutex_attempt(void *lock)
{
    if(lock==&ssdk_genl_control_lock)atomic_fetch_add(&control_attempts,1);
    if(qca_phy_priv_global)
        for(unsigned i=0;i<2;i++)
            if(qca_phy_priv_global[i] && lock==&qca_phy_priv_global[i]->fdb_ctrl_lock)
                atomic_fetch_add(&fdb_attempts,1);
}
static unsigned dev_count=2,fail_irq,fail_genl,fail_sys,sys_stage,fail_send,send_stage,fail_alloc;
static bool family_live,kobject_live,core_doit;
static const struct attribute *sys_owned[16];static unsigned sys_n;
static pthread_mutex_t sys_active_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sys_active_cond=PTHREAD_COND_INITIALIZER;
static unsigned sys_active;
static struct {pthread_mutex_t p;pthread_cond_t c;unsigned point,arrivals;bool release;} hook={PTHREAD_MUTEX_INITIALIZER,PTHREAD_COND_INITIALIZER,0,0,false};
static void point(unsigned id){pthread_mutex_lock(&hook.p);if(hook.point==id){++hook.arrivals;pthread_cond_broadcast(&hook.c);while(!hook.release)pthread_cond_wait(&hook.c,&hook.p);}pthread_mutex_unlock(&hook.p);}
static void arm(unsigned id){pthread_mutex_lock(&hook.p);hook.point=id;hook.arrivals=0;hook.release=false;pthread_mutex_unlock(&hook.p);}
static void arrived(unsigned n){
    struct timespec until;clock_gettime(CLOCK_REALTIME,&until);until.tv_sec+=4;
    pthread_mutex_lock(&hook.p);
    int result=0;
    while(hook.arrivals<n && result==0)
        result=pthread_cond_timedwait(&hook.c,&hook.p,&until);
    check(result==0 && hook.arrivals>=n,"native-hook-progress");
    pthread_mutex_unlock(&hook.p);
}
static void release_hook(void){pthread_mutex_lock(&hook.p);hook.release=true;hook.point=0;pthread_cond_broadcast(&hook.c);pthread_mutex_unlock(&hook.p);}
static void wait_flag(atomic_bool *p){for(unsigned i=0;i<8000&&!atomic_load(p);i++)usleep(500);check(atomic_load(p),"native-progress");}
static void wait_cancel(unsigned old){for(unsigned i=0;i<8000&&atomic_load(&cancel_calls)==old;i++)usleep(500);check(atomic_load(&cancel_calls)>old,"native-cancel-progress");}
static void wait_counter(atomic_uint *counter,unsigned old)
{
    for(unsigned i=0;i<8000&&atomic_load(counter)==old;i++)usleep(500);
    check(atomic_load(counter)>old,"native-counter-progress");
}
struct alloc_rec {void *p;size_t n;bool live;};
static struct alloc_rec allocs[8192];static unsigned alloc_n;
static pthread_mutex_t alloc_lock=PTHREAD_MUTEX_INITIALIZER;
static void *kzalloc(size_t n,int flags){(void)flags;if(fail_alloc&&!--fail_alloc)return NULL;void *p=calloc(1,n);check(p!=NULL,"host-allocation");pthread_mutex_lock(&alloc_lock);check(alloc_n<ARRAY_SIZE(allocs),"allocation-records");allocs[alloc_n++]=(struct alloc_rec){p,n,true};pthread_mutex_unlock(&alloc_lock);return p;}
static void assert_scoped_retired(void){check(!family_live&&!kobject_live,"free-after-controls");if(qca_phy_priv_global)for(unsigned i=0;i<dev_count;i++){struct qca_phy_priv *p=qca_phy_priv_global[i];if(!p)continue;check(!p->intr_requested&&!p->fdb_users&&!p->fdb_polling_started,"free-after-producers");check(!p->intr_workqueue.running&&!p->intr_workqueue.pending&&!p->fdb_sw_sync_dwork.work.running&&!p->fdb_sw_sync_dwork.work.pending,"free-after-work");}}
static void kfree(void *p){if(!p)return;if(p==qca_phy_priv_global)assert_scoped_retired();if(qca_phy_priv_global)for(unsigned i=0;i<dev_count;i++)if(p==qca_phy_priv_global[i])assert_scoped_retired();pthread_mutex_lock(&alloc_lock);unsigned i;for(i=0;i<alloc_n;i++)if(allocs[i].p==p&&allocs[i].live)break;check(i<alloc_n,"free-owned");allocs[i].live=false;pthread_mutex_unlock(&alloc_lock);free(p);}
static _Thread_local struct qca_phy_priv *last_leave_priv;
static _Thread_local void *last_leave_wait;
static atomic_uint last_leave_wakes;
static void post_unlock(void *p)
{
    if(last_leave_priv && p==&last_leave_priv->fdb_sw_sync_lock && !last_leave_priv->fdb_users)
        point(5);
}
static void check_wait_live(void *p)
{
    if(p==last_leave_wait) atomic_fetch_add(&last_leave_wakes,1);
    pthread_mutex_lock(&alloc_lock);
    for(unsigned i=alloc_n;i>0;i--) {
        uintptr_t start=(uintptr_t)allocs[i-1].p, address=(uintptr_t)p;
        if(address>=start && address-start<allocs[i-1].n) {
            check(allocs[i-1].live,"wake-after-private-free");
            break;
        }
    }
    pthread_mutex_unlock(&alloc_lock);
}
static void work_init(struct work_struct *w,void(*fn)(struct work_struct *)){check(!w->initialized,"work-construct-once");pthread_mutex_init(&w->p,NULL);pthread_cond_init(&w->c,NULL);w->fn=fn;w->initialized=true;++w->constructs;}
#define INIT_WORK(w,f) work_init(w,f)
#define INIT_DELAYED_WORK(w,f) work_init(&(w)->work,f)
static struct qca_phy_priv *work_priv(struct work_struct *w,bool *delayed){if(qca_phy_priv_global)for(unsigned i=0;i<dev_count;i++){struct qca_phy_priv *p=qca_phy_priv_global[i];if(!p)continue;if(w==&p->fdb_sw_sync_dwork.work){*delayed=true;return p;}if(w==&p->intr_workqueue){*delayed=false;return p;}}return NULL;}
static int schedule_work(struct work_struct *w){bool delayed=false;struct qca_phy_priv *p=work_priv(w,&delayed);check(w->initialized,"queue-initialized");if(p&&delayed)check(!p->fdb_stopping&&!p->fdb_draining,"queue-after-stop");pthread_mutex_lock(&w->p);bool queued=!w->pending&&!w->cancelling;if(queued)w->pending=true;pthread_mutex_unlock(&w->p);return queued;}
static int schedule_delayed_work(struct delayed_work *w,unsigned delay){(void)delay;return schedule_work(&w->work);}
static _Thread_local struct work_struct *current_work;
static void *run_work(void *arg){struct work_struct *w=arg;pthread_mutex_lock(&w->p);check(w->initialized&&w->pending&&!w->running,"dispatch-pending");w->pending=false;w->running=true;pthread_mutex_unlock(&w->p);current_work=w;w->fn(w);current_work=NULL;pthread_mutex_lock(&w->p);w->running=false;pthread_cond_broadcast(&w->c);pthread_mutex_unlock(&w->p);return NULL;}
static bool cancel_work_sync(struct work_struct *w){bool delayed=false;struct qca_phy_priv *p=work_priv(w,&delayed);check(!bh&&current_work!=w,"drain-unlocked-not-self");check(w->initialized,"cancel-initialized");if(p&&delayed){check(owns(&p->fdb_ctrl_lock),"controller-serialization");check(p->fdb_draining&&!p->fdb_polling_started,"close-before-cancel");atomic_fetch_add(&fdb_cancel_entries,1);}else if(p)check(!p->intr_requested,"irq-free-before-drain");atomic_fetch_add(&cancel_calls,1);pthread_mutex_lock(&w->p);bool pending=w->pending;w->pending=false;w->cancelling=true;while(w->running)pthread_cond_wait(&w->c,&w->p);w->pending=false;w->cancelling=false;pthread_mutex_unlock(&w->p);return pending;}
static bool cancel_delayed_work_sync(struct delayed_work *w){return cancel_work_sync(&w->work);}
static bool flush_work(struct work_struct *w){check(!bh&&current_work!=w,"flush-unlocked-not-self");pthread_mutex_lock(&w->p);bool pending=w->pending;if(pending&&!w->running){pthread_mutex_unlock(&w->p);run_work(w);pthread_mutex_lock(&w->p);}while(w->running)pthread_cond_wait(&w->c,&w->p);pthread_mutex_unlock(&w->p);return pending;}
static a_uint32_t ssdk_switch_device_num_get(void){return dev_count;}
static void ssdk_switch_device_num_exit(void){}
static void qca_ssdk_port_bmp_init(unsigned id){(void)id;}
static int qca_ssdk_phy_info_init(unsigned id){(void)id;return 0;}
static struct qca_phy_priv *ssdk_phy_priv_data_get(unsigned id){atomic_fetch_add(&priv_gets,1);point(2);return qca_phy_priv_global&&id<dev_count?qca_phy_priv_global[id]:NULL;}
static bool ssdk_is_emulation(unsigned id){(void)id;return false;}
static int fal_cleanup(unsigned id){(void)id;assert_scoped_retired();atomic_fetch_add(&hw_frees,1);return SW_OK;}
static int ssdk_phy_driver_cleanup(unsigned id){(void)id;assert_scoped_retired();return SW_OK;}
static int aos_mem_cmp(const void *a,const void *b,size_t n){return memcmp(a,b,n);}
static void aos_mem_copy(void *a,const void *b,size_t n){memcpy(a,b,n);}
static char *ssdk_port_to_ifname(unsigned dev,unsigned port){(void)dev;(void)port;return "eth1";}
static int fal_fdb_entry_extend_getfirst(unsigned dev,fal_fdb_op_t *op,fal_fdb_entry_t *e){(void)op;atomic_fetch_add(&scans,1);point(1);check(qca_phy_priv_global&&dev<dev_count,"scan-live-private");check(qca_phy_priv_global[dev]->fdb_users>0,"shared-fdb-admission");memset(e,0,sizeof(*e));e->port.id=1;e->fid=1;e->addr.uc[0]=2;return SW_OK;}
static int fal_fdb_entry_extend_getnext(unsigned dev,fal_fdb_op_t *op,fal_fdb_entry_t *e){(void)dev;(void)op;(void)e;return SW_FAIL;}
struct irq_rec {bool live;int depth;irqreturn_t(*fn)(int,void *);void *id;unsigned irq;};
static struct irq_rec irq_table[2];
static struct irq_rec *irq_find(unsigned irq){for(unsigned i=0;i<dev_count;i++)if(irq_table[i].irq==irq)return &irq_table[i];check(false,"irq-identity");return NULL;}
static int request_irq(unsigned irq,irqreturn_t(*fn)(int,void *),unsigned flags,const char *name,void *id){(void)flags;(void)name;struct qca_phy_priv *p=id;struct irq_rec *r=&irq_table[p->device_id];if(fail_irq)return -EIO;check(!r->live,"irq-acquire-once");*r=(struct irq_rec){true,0,fn,id,irq};return 0;}
static void disable_irq_nosync(unsigned irq){struct irq_rec *r=irq_find(irq);check(r->live,"disable-owned-irq");++r->depth;atomic_fetch_add(&irq_disables,1);}
static void synchronize_irq(unsigned irq){check(!bh&&irq_find(irq)->live,"synchronize-owned-irq");}
static void enable_irq(unsigned irq){struct irq_rec *r=irq_find(irq);check(!bh,"enable-outside-bh");check(r->live&&r->depth>0,"enable-owned-irq");--r->depth;atomic_fetch_add(&irq_enables,1);}
static void free_irq(unsigned irq,void *id){struct irq_rec *r=irq_find(irq);check(r->live&&r->id==id,"free-owned-irq");check(((struct qca_phy_priv*)id)->intr_stopping,"irq-close-before-free");check(r->depth>0,"irq-disabled-before-free");r->live=false;atomic_fetch_add(&irq_frees,1);}
static unsigned gpio_owned,gpio_frees;
static void gpio_free(unsigned id){(void)id;check(gpio_owned>0,"free-owned-gpio");--gpio_owned;++gpio_frees;}
static int fal_intr_status_get(unsigned dev,unsigned *status){(void)dev;*status=FAL_SWITCH_INTR_FDB_CHANGE;return 0;}
static int fal_intr_port_link_mask_set(unsigned d,unsigned p,unsigned mask){(void)d;(void)p;(void)mask;return 0;}
static int fal_intr_port_link_status_get(unsigned d,unsigned p,unsigned *s){(void)d;(void)p;*s=0;return 0;}
static int fal_intr_mask_get(unsigned d,unsigned *m){(void)d;*m=3;return 0;}
static int fal_intr_mask_mac_linkchg_set(unsigned d,unsigned p,int on){(void)d;(void)p;(void)on;return 0;}
static int fal_intr_mask_set(unsigned d,unsigned mask){(void)d;(void)mask;return 0;}
static int fal_intr_status_mac_linkchg_clear(unsigned d){(void)d;return 0;}
static int fal_intr_status_clear(unsigned d,unsigned mask){(void)d;(void)mask;return 0;}
static void qca_ar8327_sw_mac_polling_task(struct qca_phy_priv *p){(void)p;}
static void qca_mht_sw_mac_polling_task(struct qca_phy_priv *p){(void)p;}
static unsigned ssdk_ifname_to_port(unsigned dev,char *name){(void)dev;return !strcmp(name,"eth1")?1:0;}
static void *nla_data(struct nlattr *a){return a->name;}
static unsigned nla_get_u8(struct nlattr *a){return a->value;}
static unsigned nla_total_size(unsigned n){return n+4;}
static int genl_register_family(struct genl_family *f){check(f->module==THIS_MODULE&&!f->parallel_ops,"actual-family-contract");if(fail_genl)return -EIO;check(!family_live,"family-acquire-once");family_live=true;return 0;}
static int genl_unregister_family(struct genl_family *f){(void)f;mutex_lock(&model_core);check(family_live,"unregister-owned-family");if(qca_phy_priv_global)for(unsigned i=0;i<dev_count;i++){struct qca_phy_priv *p=qca_phy_priv_global[i];if(p)check(!p->intr_requested&&!p->fdb_polling_started&&!p->fdb_users,"family-after-producers");}check(!core_doit&&!ssdk_genl_notify_users,"family-after-callbacks");family_live=false;mutex_unlock(&model_core);return 0;}
static struct sk_buff *genlmsg_new(unsigned payload,int flags){(void)payload;(void)flags;if(fail_send&&++send_stage==fail_send)return NULL;struct sk_buff *p=malloc(sizeof(*p));check(p!=NULL,"host-allocation");p->owned=1;return p;}
static void *genlmsg_put(struct sk_buff *s,int a,int b,struct genl_family *f,int d,char cmd){(void)a;(void)b;(void)f;(void)d;(void)cmd;check(family_live&&ssdk_genl_notify_users>0,"notify-user-ledger");point(3);return fail_send&&++send_stage==fail_send?NULL:s;}
static void kfree_skb(struct sk_buff *s){check(s&&s->owned,"skb-owned");s->owned=0;free(s);}
static int nla_put_string(struct sk_buff *s,int a,char *v){(void)s;(void)a;(void)v;return fail_send&&++send_stage==fail_send?-ENOMEM:0;}
static int nla_put(struct sk_buff *s,int a,int n,void *v){(void)s;(void)a;(void)n;(void)v;return fail_send&&++send_stage==fail_send?-ENOMEM:0;}
static void genlmsg_end(struct sk_buff *s,void *h){(void)s;(void)h;}
static int genlmsg_multicast(struct genl_family *f,struct sk_buff *s,int a,int b,int flags){(void)f;(void)a;(void)b;(void)flags;check(family_live,"notify-family-live");atomic_fetch_add(&notifications,1);kfree_skb(s);return fail_send&&++send_stage==fail_send?-EIO:0;}
static struct kobject sys_obj;
static struct kobject *kobject_create_and_add(const char *name,void *parent){(void)parent;check(!strcmp(name,"ssdk"),"sysfs-name");sys_stage=0;if(fail_sys==1)return NULL;check(!kobject_live,"kobject-acquire-once");kobject_live=true;return &sys_obj;}
static int sysfs_create_file(struct kobject *k,const struct attribute *a){check(k==&sys_obj&&kobject_live,"sysfs-owned-object");if(fail_sys&&++sys_stage+1==fail_sys)return -EIO;check(sys_n<16,"sysfs-count");sys_owned[sys_n++]=a;return 0;}
static void sysfs_remove_file(struct kobject *k,const struct attribute *a){check(!bh&&k==&sys_obj&&kobject_live&&sys_n&&sys_owned[sys_n-1]==a,"sysfs-owned-reverse");atomic_fetch_add(&sys_remove_entries,1);pthread_mutex_lock(&sys_active_lock);while(sys_active)pthread_cond_wait(&sys_active_cond,&sys_active_lock);pthread_mutex_unlock(&sys_active_lock);--sys_n;}
static void kobject_put(struct kobject *k){check(k==&sys_obj&&kobject_live&&!sys_n,"kobject-put-owned");kobject_live=false;}
/* ACTUAL_FUNCTIONS */

static void create(unsigned version){atomic_fetch_add(&cases,1);check(!qca_phy_priv_global&&!family_live&&!kobject_live,"case-entry");memset(irq_table,0,sizeof(irq_table));fail_irq=fail_genl=fail_sys=fail_send=send_stage=fail_alloc=0;gpio_owned=0;check(!ssdk_alloc_priv(dev_count),"actual-private-allocation");for(unsigned i=0;i<dev_count;i++){struct qca_phy_priv *p=qca_phy_priv_global[i];p->device_id=i;p->version=version;p->ports=7;p->interrupt_no=40+i;p->interrupt_flag=8;p->fdb_sync=FDB_SYNC_INTR;check(!qca_fdb_sw_sync_work_init(p),"actual-fdb-init");check(p->fdb_sw_sync_dwork.work.constructs==1&&p->intr_workqueue.constructs==1,"work-construct-once");}}
static void finish(void){ssdk_free_priv();check(!qca_phy_priv_global&&!family_live&&!kobject_live&&!sys_n,"case-final");check(!ssdk_genl_notify_users,"notify-user-balance");for(unsigned i=0;i<dev_count;i++)check(!irq_table[i].live,"irq-final");check(gpio_owned==0,"gpio-balance");}
static void start_controls(void){check(!ssdk_sysfs_init(),"sysfs-init");bool mac=false;for(unsigned i=0;i<sys_n;i++)mac|=!strcmp(sys_owned[i]->name,"mac_polling");check(mac,"mac-attribute-present");check(!ssdk_genl_init(),"genl-init");}
static void *stop_all(void *arg){(void)arg;ssdk_fdb_retire_controls();atomic_store(&stop_done,true);return NULL;}
static void *stop_partial(void *arg){qca_fdb_sw_sync_work_stop(arg,BIT(1));atomic_store(&stop_done,true);return NULL;}
static void *direct_scan(void *arg){ref_fdb_sw_sync_task(arg);return NULL;}
static int poll(bool enable,bool valid){struct nlattr name={0,"eth1"},value={(unsigned char)enable,""};if(!valid)strcpy(name.name,"invalid");struct genl_info info={.attrs={[SSDK_ATTR_IFNAME]=&name,[SSDK_ATTR_MACPOLL]=&value}};mutex_lock(&model_core);core_doit=true;int r=ssdk_poll_mac(NULL,&info);core_doit=false;mutex_unlock(&model_core);return r;}
static void *poll_thread(void *arg){(void)arg;check(!poll(true,true),"poll-accepted");return NULL;}
static void *sender_thread(void *arg){(void)arg;unsigned char mac[6]={0};check(!ssdk_genl_notify_mac_info(SSDK_COMMAND_NEW_MAC,"eth1",mac),"sender-accepted");return NULL;}
static void serial_versions(void){unsigned v[]={QCA_VER_HPPE,QCA_VER_APPE,QCA_VER_MRPPE,QCA_VER_MHT,0};for(unsigned i=0;i<ARRAY_SIZE(v);i++){create(v[i]);struct qca_phy_priv *p=qca_phy_priv_global[0];start_controls();if(!v[i]){check(qca_fdb_sw_sync_work_start(p,BIT(1))==-EOPNOTSUPP,"unsupported-start");check(poll(true,true)==-EOPNOTSUPP,"poll-start-errno");}else{check(!qca_fdb_sw_sync_work_start(p,BIT(1)|BIT(2)),"supported-start");check(!qca_fdb_sw_sync_work_start(p,BIT(1)),"idempotent-start");qca_fdb_sw_sync_work_stop(p,BIT(1));check(p->fdb_polling_started&&p->fdb_sw_sync_port_map==BIT(2),"partial-port-map");qca_fdb_sw_sync_work_stop(p,BIT(2));check(!p->fdb_polling_started&&!p->fdb_sw_sync_dwork.work.pending,"last-stop");check(!qca_fdb_sw_sync_work_start(p,BIT(1)),"restart-without-reconstruct");qca_fdb_sw_sync_work_fini(p);check(qca_fdb_sw_sync_work_start(p,BIT(1))==-ESHUTDOWN,"start-after-final");check(ref_fdb_sw_sync_task(p)==SW_BUSY,"shared-after-final");}check(p->fdb_sw_sync_dwork.work.constructs==1,"work-construct-once");finish();}}
static void irq_cases(void){create(QCA_VER_MHT);struct qca_phy_priv *p=qca_phy_priv_global[0];qca_intr_work_pause(p);qca_intr_work_resume(p);check(!p->intr_paused,"pre-request-resume");fail_irq=1;check(qca_intr_init(p)==-EIO&&!p->intr_requested,"irq-failure-ledger");fail_irq=0;check(!qca_intr_init(p),"irq-retry");check(qca_intr_init(p)==-EBUSY,"irq-live-init-rejected");unsigned enables=atomic_load(&irq_enables);qca_intr_work_pause(p);qca_intr_work_pause(p);check(irq_find(p->interrupt_no)->depth==1,"pause-once");qca_intr_work_resume(p);qca_intr_work_resume(p);check(atomic_load(&irq_enables)==enables+1,"resume-once");qca_intr_deinit(p);enables=atomic_load(&irq_enables);qca_intr_work_resume(p);check(atomic_load(&irq_enables)==enables,"resume-after-retirement");finish();create(QCA_VER_HPPE);p=qca_phy_priv_global[0];fail_irq=1;check(qca_intr_init(p)==-EIO,"irq-injected-error");unsigned frees=atomic_load(&irq_frees);p->intr_gpio_requested=true;p->intr_gpio_num=21;gpio_owned=1;qca_intr_deinit(p);check(atomic_load(&irq_frees)==frees&&!gpio_owned,"irq-no-unowned-free");finish();}
static void active_drain(bool irq){create(QCA_VER_HPPE);struct qca_phy_priv *p=qca_phy_priv_global[0];start_controls();check(!qca_fdb_sw_sync_work_start(p,BIT(1)),"drain-start");struct work_struct *w=&p->fdb_sw_sync_dwork.work;if(irq){check(!qca_intr_init(p),"drain-irq-init");irq_find(p->interrupt_no)->fn(p->interrupt_no,p);w=&p->intr_workqueue;}arm(1);pthread_t worker,stopper;check(!pthread_create(&worker,NULL,run_work,w),"thread-start");arrived(1);check(p->fdb_users==1,"shared-fdb-admission");atomic_store(&stop_done,false);atomic_uint *counter=irq?&cancel_calls:&fdb_cancel_entries;unsigned old=atomic_load(counter);check(!pthread_create(&stopper,NULL,stop_all,NULL),"thread-stop");wait_counter(counter,old);check(!atomic_load(&stop_done)&&family_live,"family-live-during-drain");if(irq)check(!irq_find(p->interrupt_no)->live,"irq-free-before-drain");release_hook();pthread_join(worker,NULL);pthread_join(stopper,NULL);check(atomic_load(&stop_done)&&!family_live&&!p->fdb_users,"full-scoped-drain");check(!p->fdb_sw_sync_dwork.work.pending&&!p->intr_workqueue.pending,"no-post-stop-rearm");finish();}
static void direct_drain(void){create(QCA_VER_MHT);struct qca_phy_priv *p=qca_phy_priv_global[0];start_controls();check(!qca_fdb_sw_sync_work_start(p,BIT(1)|BIT(2)),"direct-start");arm(1);pthread_t scan,stopper;pthread_create(&scan,NULL,direct_scan,p);arrived(1);check(p->fdb_users==1,"shared-fdb-admission");atomic_store(&stop_done,false);unsigned old=atomic_load(&cancel_calls);pthread_create(&stopper,NULL,stop_partial,p);wait_cancel(old);check(!atomic_load(&stop_done),"stop-waits-shared-reader");release_hook();pthread_join(scan,NULL);pthread_join(stopper,NULL);check(p->fdb_users==0,"fdb-reference-balance");check(p->fdb_polling_started&&p->fdb_sw_sync_port_map==BIT(2),"partial-rearm");finish();}
static void entry_control(void){create(QCA_VER_HPPE);unsigned gets=atomic_load(&priv_gets);check(poll(true,true)==-ESHUTDOWN&&atomic_load(&priv_gets)==gets,"control-admission");fail_genl=1;check(ssdk_genl_init()==-EIO&&!family_live,"family-fail-ledger");check(!ssdk_genl_deinit(),"unregistered-family-noop");fail_genl=0;start_controls();check(poll(true,false)==-EINVAL,"invalid-port");arm(2);pthread_t caller,stopper;pthread_create(&caller,NULL,poll_thread,NULL);arrived(1);atomic_store(&stop_done,false);unsigned old=atomic_load(&control_attempts);pthread_create(&stopper,NULL,stop_all,NULL);wait_counter(&control_attempts,old);check(!atomic_load(&stop_done),"stop-waits-accepted-control");release_hook();pthread_join(caller,NULL);pthread_join(stopper,NULL);gets=atomic_load(&priv_gets);check(poll(true,true)==-ESHUTDOWN&&atomic_load(&priv_gets)==gets,"control-admission");finish();}
static void sysfs_failures(void){for(unsigned f=1;f<=ARRAY_SIZE(ssdk_sysfs_attrs)+1;f++){create(QCA_VER_HPPE);fail_sys=f;int r=ssdk_sysfs_init();check(r==(f==1?-ENOMEM:-EIO),f==1?"sysfs-alloc-errno":"sysfs-create-errno");check(!ssdk_sys&&!sys_n&&!kobject_live,"sysfs-failure-balance");fail_sys=0;check(!ssdk_sysfs_init(),"sysfs-retry");check(ssdk_sysfs_init()==-EBUSY,"sysfs-live-init-rejected");ssdk_sysfs_exit();ssdk_sysfs_exit();finish();}}
static void *sysfs_callback(void *arg){(void)arg;pthread_mutex_lock(&sys_active_lock);++sys_active;pthread_mutex_unlock(&sys_active_lock);point(4);check(qca_phy_priv_global!=NULL,"sysfs-callback-private-live");pthread_mutex_lock(&sys_active_lock);--sys_active;pthread_cond_broadcast(&sys_active_cond);pthread_mutex_unlock(&sys_active_lock);return NULL;}
static void sysfs_active(void){create(QCA_VER_HPPE);start_controls();arm(4);pthread_t callback,stopper;pthread_create(&callback,NULL,sysfs_callback,NULL);arrived(1);atomic_store(&stop_done,false);unsigned old=atomic_load(&sys_remove_entries);pthread_create(&stopper,NULL,stop_all,NULL);wait_counter(&sys_remove_entries,old);check(!atomic_load(&stop_done)&&family_live,"sysfs-drain-before-family");release_hook();pthread_join(callback,NULL);pthread_join(stopper,NULL);finish();}
static void sender_failures(void){create(QCA_VER_HPPE);start_controls();unsigned char mac[6]={0};for(unsigned f=1;f<=6;f++){fail_send=f;send_stage=0;ssdk_genl_notify_mac_info(SSDK_COMMAND_NEW_MAC,"eth1",mac);check(ssdk_genl_notify_users==0,"notify-user-balance");}fail_send=0;check(ssdk_genl_notify_mac_info(99,"eth1",mac)==-1&&!ssdk_genl_notify_users,"notify-error-balanced");finish();}
static void allocation_errors(void){for(unsigned f=1;f<=3;f++){atomic_fetch_add(&cases,1);fail_alloc=f;check(ssdk_alloc_priv(dev_count)==-ENOMEM,"private-allocation-fault");ssdk_free_priv();check(!qca_phy_priv_global,"partial-private-retired");fail_alloc=0;}create(QCA_VER_HPPE);start_controls();check(!qca_fdb_sw_sync_work_start(qca_phy_priv_global[0],BIT(1)),"allocation-scan-start");fail_alloc=1;check(ref_fdb_sw_sync_task(qca_phy_priv_global[0])!=SW_OK,"list-allocation-fault");check(!qca_phy_priv_global[0]->fdb_users,"fdb-reference-balance");fail_alloc=0;finish();}
static void roots(void){create(QCA_VER_HPPE);start_controls();struct qca_phy_priv *p=qca_phy_priv_global[0];check(!qca_fdb_sw_sync_work_start(p,BIT(1)),"root-fdb-start");check(!qca_intr_init(p),"root-irq-start");check(!ssdk_cleanup(0),"actual-hardware-cleanup");finish();create(QCA_VER_HPPE);start_controls();check(!qca_fdb_sw_sync_work_start(qca_phy_priv_global[0],BIT(1)),"root-private-start");finish();}
static void irq_normal(void)
{
    create(QCA_VER_HPPE);start_controls();
    struct qca_phy_priv *p=qca_phy_priv_global[0];
    check(!qca_intr_init(p),"normal-irq-init");
    unsigned enables=atomic_load(&irq_enables);
    qca_intr_handle(p->interrupt_no,p);
    qca_intr_handle(p->interrupt_no,p);
    check(irq_find(p->interrupt_no)->depth==1,"duplicate-irq-mask");
    run_work(&p->intr_workqueue);
    check(atomic_load(&irq_enables)==enables+1&&!irq_find(p->interrupt_no)->depth,
          "normal-irq-rearm");
    qca_intr_work_pause(p);
    qca_intr_handle(p->interrupt_no,p);
    check(!p->intr_workqueue.pending,"paused-irq-admission");
    qca_intr_work_resume(p);
    qca_intr_deinit(p);
    qca_intr_handle(p->interrupt_no,p);
    check(!p->intr_workqueue.pending,"retired-irq-admission");
    finish();
}
static void sender_drain(void)
{
    create(QCA_VER_HPPE);start_controls();arm(3);
    pthread_t caller,stopper;
    check(!pthread_create(&caller,NULL,sender_thread,NULL),"sender-thread");
    arrived(1);
    check(ssdk_genl_notify_users==1,"sender-user-held");
    atomic_store(&stop_done,false);
    unsigned old=atomic_load(&notify_wait_entries);
    check(!pthread_create(&stopper,NULL,stop_all,NULL),"sender-stop-thread");
    wait_counter(&notify_wait_entries,old);
    check(!atomic_load(&stop_done)&&family_live,"family-live-for-sender");
    release_hook();pthread_join(caller,NULL);pthread_join(stopper,NULL);
    check(!ssdk_genl_notify_users&&!family_live,"sender-drained");
    finish();
}
struct start_arg {struct qca_phy_priv *p;int result;atomic_bool done;};
static void *concurrent_start(void *arg)
{
    struct start_arg *a=arg;
    a->result=qca_fdb_sw_sync_work_start(a->p,BIT(3));
    atomic_store(&a->done,true);return NULL;
}
static void *final_stop(void *arg){qca_fdb_sw_sync_work_fini(arg);atomic_store(&stop_done,true);return NULL;}
static void concurrent_controls(bool final)
{
    create(QCA_VER_MHT);start_controls();
    struct qca_phy_priv *p=qca_phy_priv_global[0];
    check(!qca_fdb_sw_sync_work_start(p,BIT(1)|BIT(2)),"concurrent-start-initial");
    arm(1);pthread_t reader,stopper,starter;
    check(!pthread_create(&reader,NULL,direct_scan,p),"concurrent-reader");arrived(1);
    unsigned old=atomic_load(&cancel_calls);
    atomic_store(&stop_done,false);
    check(!pthread_create(&stopper,NULL,final?final_stop:stop_partial,p),"concurrent-stopper");
    wait_cancel(old);
    struct start_arg a={.p=p,.result=123,.done=false};
    old=atomic_load(&fdb_attempts);
    check(!pthread_create(&starter,NULL,concurrent_start,&a),"concurrent-starter");
    wait_counter(&fdb_attempts,old);
    check(!atomic_load(&a.done)&&!atomic_load(&stop_done),"start-serialized-with-stop");
    check(!qca_fdb_sw_sync_enter(p),"shared-admission-during-drain");
    release_hook();pthread_join(reader,NULL);pthread_join(stopper,NULL);pthread_join(starter,NULL);
    check(final?a.result==-ESHUTDOWN:a.result==0,"concurrent-start-result");
    check(final?!p->fdb_sw_sync_port_map:p->fdb_sw_sync_port_map==(BIT(2)|BIT(3)),
          "concurrent-map-ledger");
    finish();
}
static void *last_leave_scan(void *arg)
{
    last_leave_priv=arg;
    last_leave_wait=&last_leave_priv->fdb_wait;
#ifdef IN_FDB
    ref_fdb_sw_sync_task(arg);
#else
    /* A direct controller user, not a no-IN_FDB module scan claim. */
    check(qca_fdb_sw_sync_enter(arg),"shared-fdb-admission");
    qca_fdb_sw_sync_leave(arg);
#endif
    last_leave_priv=NULL;
    last_leave_wait=NULL;
    return NULL;
}
static void last_leave_window(void)
{
    create(QCA_VER_HPPE);
    arm(5);
    pthread_t caller;
    check(!pthread_create(&caller,NULL,last_leave_scan,qca_phy_priv_global[0]),"thread-last-leave");
    arrived(1);
    unsigned woke_before_free=atomic_load(&last_leave_wakes);
    ssdk_free_priv();
    check(!qca_phy_priv_global,"retire-observed-zero-before-wake");
    release_hook();
    pthread_join(caller,NULL);
    check(woke_before_free==1&&atomic_load(&last_leave_wakes)==1,"final-wake-before-free");
    check(!held_n&&!bh,"final-lock-balance");
    for(unsigned i=0;i<alloc_n;i++)check(!allocs[i].live,"allocation-balance");
    fputs("PASS last-leave-window wake-before-free=1\n",stdout);
}
int main(int argc,char **argv)
{
    check(argc==2,"suite-mode");
    if(!strcmp(argv[1],"direct")) {
        create(QCA_VER_HPPE);
        ref_fdb_sw_sync_task(qca_phy_priv_global[0]);
        check(!qca_phy_priv_global[0]->fdb_users,"fdb-reference-balance");
        finish();
    } else if(!strcmp(argv[1],"control")) entry_control();
    else if(!strcmp(argv[1],"last-leave-window")) {last_leave_window();return 0;}
    else if(!strcmp(argv[1],"sender")) sender_failures();
    else if(!strcmp(argv[1],"sender-direct")) {
        create(QCA_VER_HPPE);start_controls();sender_thread(NULL);finish();
    }
    else if(!strcmp(argv[1],"roots")) roots();
    else {
        check(!strcmp(argv[1],"suite"),"suite-mode");
        serial_versions();irq_cases();active_drain(false);active_drain(true);
        direct_drain();entry_control();sysfs_failures();sysfs_active();
        sender_failures();allocation_errors();roots();
        irq_normal();sender_drain();concurrent_controls(false);concurrent_controls(true);
    }
    check(!held_n&&!bh,"final-lock-balance");
    for(unsigned i=0;i<alloc_n;i++)check(!allocs[i].live,"allocation-balance");
    printf("cases=%u checks=%u scans=%u notifications=%u irq_frees=%u cancels=%u\n",
           atomic_load(&cases),atomic_load(&checks),atomic_load(&scans),
           atomic_load(&notifications),atomic_load(&irq_frees),atomic_load(&cancel_calls));
    return 0;
}
