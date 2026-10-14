/* Kernel/API substitutes only, not a DRV registration/removal state machine. */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

#define NSS_MAX_CORES 2
#define NSS_MAX_IRQ_PER_CORE 2
#define NSS_MAX_NET_INTERFACES 4
#define NSS_DP_MAX_INTERFACES 4
#define NSS_DP_START_IFNUM 1
#define NSS_CORE_0 0
#define NSS_MAX_NUM_PRI 4
#define NSS_TX_SUCCESS 0
#define NSS_DP_SUCCESS 0
#define NSS_HAL_SUPPORTED_INTERRUPTS 0xffff
/* GENERIC and exact SoC guards are selected explicitly by compiler args. */
/* Select the exact source guard NSS_HAL_IPQ807x_SUPPORT via compiler args.
 * Uppercase-X NSS_HAL_IPQ807X_SUPPORT is deliberately not an alias. */
#define NSS_FABRIC_SCALING_SUPPORT 0
#define IRQ_DISABLE_UNLAZY 1
#define EXPORT_SYMBOL(x)
#define NSS_VERIFY_CTX_MAGIC(x) ((void)(x))
#define BUG_ON(x) assert(!(x))
#define WARN_ON(x) ((x) ? (fprintf(stderr,"host WARN_ON %s:%d\n",__FILE__,__LINE__),1) : 0)
#define WARN_ON_ONCE(x) WARN_ON(x)
#define nss_info(...) ((void)0)
#define nss_info_always(...) ((void)0)
#define nss_warning(...) ((void)0)
#define nss_trace(...) ((void)0)
#define nss_assert(x) assert(x)
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_SEQ_CST)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_SEQ_CST)
#define likely(x) (x)
#define unlikely(x) (x)
#define might_sleep() ((void)0)
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
typedef pthread_mutex_t spinlock_t;
struct mutex { pthread_mutex_t lock; };
#define DEFINE_SPINLOCK(name) spinlock_t name=PTHREAD_MUTEX_INITIALIZER
#define DEFINE_MUTEX(name) struct mutex name={PTHREAD_MUTEX_INITIALIZER}
#define spin_lock_init(lock) assert(pthread_mutex_init((lock),NULL)==0)
#define spin_lock_bh(lock) assert(pthread_mutex_lock(lock)==0)
#define spin_unlock_bh(lock) assert(pthread_mutex_unlock(lock)==0)
#define spin_lock_irqsave(lock,flags) do { (flags)=0; spin_lock_bh(lock); } while(0)
#define spin_unlock_irqrestore(lock,flags) do { (void)(flags); spin_unlock_bh(lock); } while(0)
#define mutex_init(value) assert(pthread_mutex_init(&(value)->lock,NULL)==0)
#define mutex_lock(value) assert(pthread_mutex_lock(&(value)->lock)==0)
#define mutex_unlock(value) assert(pthread_mutex_unlock(&(value)->lock)==0)
static pthread_mutex_t host_rtnl=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local bool host_holds_rtnl;
static void rtnl_lock(void) { assert(pthread_mutex_lock(&host_rtnl)==0); host_holds_rtnl=true; }
static void rtnl_unlock(void) { host_holds_rtnl=false; assert(pthread_mutex_unlock(&host_rtnl)==0); }
static bool rtnl_is_locked(void) { return host_holds_rtnl; }
#define ASSERT_RTNL() assert(rtnl_is_locked())

enum host_api_event { HOST_CANCEL_WAIT, HOST_DESTROY_WAIT, HOST_NAPI_WAIT, HOST_NAPI_GRACE, HOST_IRQ_FREE, HOST_NAPI_DELETE, HOST_NDEV_FREE, HOST_NOTIFY_RETURN, HOST_NAPI_COMPLETE };
static void host_observe(enum host_api_event event,int core);

struct workqueue_struct;
struct work_struct { void (*function)(struct work_struct *); struct workqueue_struct *owner; };
struct delayed_work { struct work_struct work; };
struct workqueue_struct {
    pthread_mutex_t lock;
    pthread_cond_t cond;
    struct work_struct *work;
    bool pending,running,destroyed;
    unsigned enqueue_calls,cancel_calls,destroy_calls;
};
static struct workqueue_struct host_queue;
static bool host_queue_initialized,host_create_fail;
static struct workqueue_struct *create_singlethread_workqueue(const char *name) {
    assert(name);
    if(host_create_fail) return NULL;
    if(host_queue_initialized) {
        assert(!host_queue.running && !host_queue.pending);
        assert(pthread_mutex_destroy(&host_queue.lock)==0); assert(pthread_cond_destroy(&host_queue.cond)==0);
    }
    memset(&host_queue,0,sizeof(host_queue));
    assert(pthread_mutex_init(&host_queue.lock,NULL)==0); assert(pthread_cond_init(&host_queue.cond,NULL)==0);
    host_queue_initialized=true; return &host_queue;
}
#define INIT_DELAYED_WORK(dwork,fn) do { (dwork)->work.function=(fn); (dwork)->work.owner=NULL; } while(0)
static bool queue_work_on(int cpu,struct workqueue_struct *queue,struct work_struct *work) {
    assert(cpu==1 && queue && work && work->function);
    assert(pthread_mutex_lock(&queue->lock)==0); queue->enqueue_calls++;
    bool accepted=!queue->destroyed && !queue->pending;
    if(accepted) { queue->pending=true; queue->work=work; work->owner=queue; }
    assert(pthread_mutex_unlock(&queue->lock)==0); return accepted;
}
static void *host_execute_queued_work(void *argument) {
    struct workqueue_struct *queue=argument;
    assert(pthread_mutex_lock(&queue->lock)==0);
    assert(queue->pending && !queue->running && !queue->destroyed);
    struct work_struct *work=queue->work; queue->pending=false; queue->running=true;
    assert(pthread_mutex_unlock(&queue->lock)==0);
    work->function(work);
    assert(pthread_mutex_lock(&queue->lock)==0); queue->running=false;
    assert(pthread_cond_broadcast(&queue->cond)==0); assert(pthread_mutex_unlock(&queue->lock)==0); return NULL;
}
static bool cancel_delayed_work_sync(struct delayed_work *work) {
    struct workqueue_struct *queue=work->work.owner;
    if(!queue) return false;
    /* This host substitute checks that the caller does not wait under RTNL. */
    assert(!host_holds_rtnl);
    assert(pthread_mutex_lock(&queue->lock)==0); queue->cancel_calls++;
    bool pending=queue->pending; queue->pending=false; host_observe(HOST_CANCEL_WAIT,-1);
    while(queue->running) assert(pthread_cond_wait(&queue->cond,&queue->lock)==0);
    assert(pthread_mutex_unlock(&queue->lock)==0); return pending;
}
static void destroy_workqueue(struct workqueue_struct *queue) {
    assert(queue && !host_holds_rtnl);
    assert(pthread_mutex_lock(&queue->lock)==0); queue->destroy_calls++;
    host_observe(HOST_DESTROY_WAIT,-1);
    while(queue->running) assert(pthread_cond_wait(&queue->cond,&queue->lock)==0);
    bool pending=queue->pending;
    assert(pthread_mutex_unlock(&queue->lock)==0);
    if(pending) host_execute_queued_work(queue);
    assert(pthread_mutex_lock(&queue->lock)==0); assert(!queue->pending && !queue->running);
    queue->destroyed=true; assert(pthread_mutex_unlock(&queue->lock)==0);
}
static void flush_workqueue(struct workqueue_struct *queue) {
    assert(queue && !host_holds_rtnl);
    assert(pthread_mutex_lock(&queue->lock)==0);
    while(queue->running) assert(pthread_cond_wait(&queue->cond,&queue->lock)==0);
    bool pending=queue->pending; assert(pthread_mutex_unlock(&queue->lock)==0);
    if(pending) host_execute_queued_work(queue);
}

struct net_device { int host_core,host_frees; bool host_admin_up; };
struct sk_buff { int host_placeholder; };
struct napi_struct { pthread_mutex_t lock; pthread_cond_t cond; int host_core; bool enabled,active,tail_active,deleted; };
struct platform_device { int id; struct { void *of_node; } dev; };
struct nss_ctx_instance;
struct nss_top_instance;
struct nss_phys_if_stats { int host_placeholder; };
struct nss_dp_data_plane_ctx { struct net_device *dev; };
struct nss_dp_gmac_stats { int host_placeholder; };
struct nss_dp_data_plane_ops { int host_placeholder; };
static unsigned host_napi_complete_calls,host_irq_rearm_calls;
static void napi_complete(struct napi_struct *napi) {
    assert(pthread_mutex_lock(&napi->lock)==0);
    /* Fixture ownership bit, not Linux NAPI state/RCU or a poll scheduler. */
    assert(napi->active); napi->active=false; host_napi_complete_calls++;
    host_observe(HOST_NAPI_COMPLETE,napi->host_core);
    assert(pthread_cond_broadcast(&napi->cond)==0); assert(pthread_mutex_unlock(&napi->lock)==0);
}
static void enable_irq(unsigned irq) { assert(irq); host_irq_rearm_calls++; }
typedef void (*nss_phys_if_rx_callback_t)(struct net_device *,struct sk_buff *,struct napi_struct *);
typedef void (*nss_phys_if_rx_ext_data_callback_t)(struct net_device *,struct sk_buff *,void *);
typedef void (*nss_phys_if_xmit_callback_t)(void *,struct sk_buff *);
static void napi_disable(struct napi_struct *napi) {
    assert(pthread_mutex_lock(&napi->lock)==0); napi->enabled=false;
    host_observe(HOST_NAPI_WAIT,napi->host_core);
    while(napi->active) assert(pthread_cond_wait(&napi->cond,&napi->lock)==0);
    assert(pthread_mutex_unlock(&napi->lock)==0);
}
static void netif_napi_del(struct napi_struct *napi) {
    assert(pthread_mutex_lock(&napi->lock)==0);
    assert(!napi->active && !napi->enabled && !napi->deleted);
    /* Mock grace may hold a post-complete poll tail; this is not Linux RCU. */
    host_observe(HOST_NAPI_GRACE,napi->host_core);
    while(napi->tail_active) assert(pthread_cond_wait(&napi->cond,&napi->lock)==0);
    napi->deleted=true; assert(pthread_mutex_unlock(&napi->lock)==0);
    host_observe(HOST_NAPI_DELETE,napi->host_core);
}
static void irq_clear_status_flags(unsigned irq,unsigned flags) { assert(irq && flags==IRQ_DISABLE_UNLAZY); }
static void free_irq(unsigned irq,void *cookie);
static void free_netdev(struct net_device *dev) {
    assert(dev && ++dev->host_frees==1); host_observe(HOST_NDEV_FREE,dev->host_core);
}
static void iounmap(void *address) { assert(address); }
/* NSS scaffolding and exact actual definitions are supplied separately. */
