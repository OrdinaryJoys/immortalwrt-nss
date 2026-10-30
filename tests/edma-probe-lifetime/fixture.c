#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#define NSS_DP_IPQ807X 1
#define NSS_DP_PPE_SUPPORT 1
#define __rcu
#define __iomem
#define NSS_DP_SUCCESS 0
#define NSS_DP_FAILURE -1
#define NET_NAME_PREDICTABLE 1
#define NET_NAME_ENUM 2
#define NETDEV_TX_OK 0
#define ETH_MAX_MTU 65535
#define IFF_LIVE_ADDR_CHANGE 1
#define NSS_DP_GSO_MAX_SEGS 64
#define NSS_DP_NETDEV_TX_QUEUE_NUM 4
#define NSS_DP_NETDEV_RX_QUEUE_NUM 4
#define HZ 100
#define MII_BUS_ID_SIZE 16
#define PHY_ID_FMT "%s:%02x"
#define LINUX_VERSION_CODE 0x061226
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define GFP_KERNEL 0
#define unlikely(x) (x)
#define likely(x) (x)
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define netdev_dbg(...) ((void)0)
#define netdev_err(...) ((void)0)
#define dev_err(...) ((void)0)
#define netdev_err(...) ((void)0)
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define IRQF_SHARED 1
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_ACQUIRE)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define IS_ERR(x) ((intptr_t)(x)<0 && (intptr_t)(x)>-4096)
#define IS_ERR_OR_NULL(x) (!(x)||IS_ERR(x))
typedef uint64_t dma_addr_t;
typedef int irqreturn_t;
typedef int netdev_tx_t;
typedef uint32_t fal_port_t;
typedef struct { pthread_mutex_t mutex; bool initialized; } spinlock_t;
typedef struct { pthread_mutex_t mutex; pthread_cond_t cond; } wait_queue_head_t;
struct net_device;
struct device_node { const char *name; unsigned macid; int phy_mode; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; void *drvdata; };
struct resource { unsigned long start, end; };
struct phy_device { bool live; };
struct mii_bus { char id[16]; };
struct sk_buff { int unused; };
struct napi_struct { struct net_device *dev; bool added, enabled; atomic_bool owned; };
struct nss_dp_data_plane_ctx { struct net_device *dev; };
struct nss_dp_data_plane_ops {
 int (*init)(struct nss_dp_data_plane_ctx *); int (*open)(struct nss_dp_data_plane_ctx *,uint32_t,uint32_t,uint32_t);
 int (*close)(struct nss_dp_data_plane_ctx *); int (*deinit)(struct nss_dp_data_plane_ctx *);
 int (*link_state)(struct nss_dp_data_plane_ctx *,uint32_t); int (*mac_addr)(struct nss_dp_data_plane_ctx *,uint8_t *);
 int (*change_mtu)(struct nss_dp_data_plane_ctx *,uint32_t); netdev_tx_t (*xmit)(struct nss_dp_data_plane_ctx *,struct sk_buff *);
 void (*set_features)(struct nss_dp_data_plane_ctx *); int (*pause_on_off)(struct nss_dp_data_plane_ctx *,uint32_t);
 int (*vsi_assign)(struct nss_dp_data_plane_ctx *,uint32_t); int (*vsi_unassign)(struct nss_dp_data_plane_ctx *,uint32_t);
};
struct nss_gmac_hal_dev { int unused; };
struct nss_gmac_hal_platform_data { unsigned mactype; };
struct nss_gmac_hal_ops {
 struct nss_gmac_hal_dev *(*init)(struct nss_gmac_hal_platform_data *);
 void (*exit)(struct nss_gmac_hal_dev *); int (*start)(struct nss_gmac_hal_dev *); int (*stop)(struct nss_gmac_hal_dev *);
};
struct nss_dp_global_ctx;
struct nss_dp_dev {
 unsigned macid,vsi; unsigned long flags,drv_flags; spinlock_t plane_lock,stats_lock; wait_queue_head_t plane_wait;
 unsigned plane_readers; bool plane_blocked,plane_quarantined,plane_pending,plane_was_open,phy_started;
 struct nss_dp_data_plane_ctx quarantine_ctx; struct phy_device *phydev; struct mii_bus *miibus;
 unsigned phy_mii_type,phy_mdio_addr; bool link_poll; unsigned link_state;
 struct net_device *netdev; struct platform_device *pdev; struct nss_dp_data_plane_ctx *dpc;
 struct nss_dp_data_plane_ops *data_plane_ops; struct nss_dp_global_ctx *ctx;
 struct nss_gmac_hal_dev *gmac_hal_ctx; struct nss_gmac_hal_ops *gmac_hal_ops;
};
struct net_device { struct nss_dp_dev priv; struct device *parent; bool dummy,freed,registered,stopped,carrier,running;
 atomic_uint borrowed; unsigned needed_headroom,max_mtu,watchdog_timeo,priv_flags,gso_max_segs,mtu;
 unsigned features,hw_features,vlan_features,wanted_features; const void *netdev_ops; unsigned char dev_addr[6]; unsigned long base_addr; char name[16]; };
struct nss_dp_global_ctx { struct nss_dp_dev *nss_dp[6]; unsigned slowproto_acl_bm; } dp_global_ctx;
static struct nss_dp_data_plane_ctx dp_global_data_plane_ctx[6];
struct nss_dp_plane_ref { struct nss_dp_data_plane_ops *ops; struct nss_dp_data_plane_ctx *dpc; };
enum {__NSS_DP_LINK_UP,__NSS_DP_LINK_DOWN};
enum {__NSS_DP_UP};
enum {__NSS_DP_PRIV_FLAG_INIT_DONE,__NSS_DP_PRIV_FLAG_IRQ_REQUESTED,__NSS_DP_PRIV_FLAG_INIT_OVERRIDE};
#define NSS_DP_PRIV_FLAG(x) (1 << __NSS_DP_PRIV_FLAG_##x)
static atomic_uint checks;
static unsigned cases,fail_stage,global_fail,lookup_fail,request_fail,lookup_calls,request_calls;
static unsigned configured_rings=1,mmio_reads,mmio_writes,port_disables,unmaps,regions_released,ring_cleanups;
static unsigned napi_adds,napi_dels,napi_enables,napi_disables,irq_frees,irq_live;
static unsigned nss_closes,override_inits,phy_disconnects,gmac_exits;
static bool mapping_live,region_live,trace_on,complete_result=true;
static _Thread_local bool rtnl_held;
static pthread_mutex_t rtnl_mutex=PTHREAD_MUTEX_INITIALIZER,rcu_mutex=PTHREAD_MUTEX_INITIALIZER,observer=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t rcu_cond=PTHREAD_COND_INITIALIZER,observed=PTHREAD_COND_INITIALIZER;
static unsigned rcu_readers;
static _Thread_local bool in_rcu;
static _Thread_local struct net_device *borrowed[6];
static unsigned pause_kind;
static bool poll_paused,poll_released,grace_started,wait_started,retire_finished;
static struct net_device *allocated[256]; static unsigned allocated_count;
static uint32_t registers[0x80000/4];
static struct platform_device dma_pdev;
static struct resource dma_resource={0x1000,0x80000};
static struct nss_gmac_hal_dev gmac;
static struct mii_bus bus={"mdio"};
static void check(bool b,const char *why) {atomic_fetch_add(&checks,1);if(!b){fprintf(stderr,"EDMA_LIFETIME %s\n",why);exit(86);}}
static void event(const char *s) {if(trace_on)puts(s);}
static void rtnl_lock(void){check(!rtnl_held,"no-recursive-rtnl");pthread_mutex_lock(&rtnl_mutex);rtnl_held=true;}
static void rtnl_unlock(void){check(rtnl_held,"rtnl-balanced");rtnl_held=false;pthread_mutex_unlock(&rtnl_mutex);}
#define ASSERT_RTNL() check(rtnl_held,"rtnl-held")
#define WARN_ON(x) ((x)?(check(false,"unexpected-warn"),true):false)
#define WARN_ON_ONCE(x) WARN_ON(x)
static void might_sleep(void){}
static void spin_lock_init(spinlock_t *l){check(!l->initialized,"spin-init-once");pthread_mutex_init(&l->mutex,NULL);l->initialized=true;}
static void spin_lock_bh(spinlock_t *l){check(l->initialized,"spin-initialized");pthread_mutex_lock(&l->mutex);}
static void spin_unlock_bh(spinlock_t *l){pthread_mutex_unlock(&l->mutex);}
static void init_waitqueue_head(wait_queue_head_t *q){pthread_mutex_init(&q->mutex,NULL);pthread_cond_init(&q->cond,NULL);}
static void wake_up_all(wait_queue_head_t *q){pthread_mutex_lock(&q->mutex);pthread_cond_broadcast(&q->cond);pthread_mutex_unlock(&q->mutex);}
#define wait_event(q,condition) do{pthread_mutex_lock(&(q).mutex);while(!(condition)){pthread_mutex_lock(&observer);wait_started=true;pthread_cond_broadcast(&observed);pthread_mutex_unlock(&observer);pthread_cond_wait(&(q).cond,&(q).mutex);}pthread_mutex_unlock(&(q).mutex);}while(0)
static void set_bit(unsigned n,unsigned long *v){*v|=1UL<<n;}static void clear_bit(unsigned n,unsigned long *v){*v&=~(1UL<<n);}static bool test_bit(unsigned n,const unsigned long *v){return (*v>>n)&1;}
static void rcu_read_lock(void){check(!in_rcu,"rcu-not-nested-fixture");pthread_mutex_lock(&rcu_mutex);++rcu_readers;in_rcu=true;memset(borrowed,0,sizeof(borrowed));pthread_mutex_unlock(&rcu_mutex);}
static void rcu_read_unlock(void){check(in_rcu,"full-poll-rcu");pthread_mutex_lock(&rcu_mutex);for(unsigned i=0;i<6;++i)if(borrowed[i])atomic_fetch_sub(&borrowed[i]->borrowed,1);--rcu_readers;in_rcu=false;pthread_cond_broadcast(&rcu_cond);pthread_mutex_unlock(&rcu_mutex);}
static void synchronize_net(void){check(!in_rcu,"no-grace-inside-reader");pthread_mutex_lock(&rcu_mutex);pthread_mutex_lock(&observer);grace_started=true;pthread_cond_broadcast(&observed);pthread_mutex_unlock(&observer);while(rcu_readers)pthread_cond_wait(&rcu_cond,&rcu_mutex);pthread_mutex_unlock(&rcu_mutex);}
#define rcu_assign_pointer(p,v) __atomic_store_n(&(p),(v),__ATOMIC_RELEASE)
#define rcu_access_pointer(p) __atomic_load_n(&(p),__ATOMIC_ACQUIRE)
static struct net_device *read_port(struct net_device *d){check(in_rcu,"port-read-rcu");if(d){check(!d->freed,"port-live-read");unsigned i=d->priv.macid-1;check(i<6,"port-index");if(!borrowed[i]){borrowed[i]=d;atomic_fetch_add(&d->borrowed,1);}}return d;}
#define rcu_dereference(p) read_port(rcu_access_pointer(p))
static void pause_poll(unsigned kind){if(pause_kind!=kind)return;pthread_mutex_lock(&observer);poll_paused=true;pthread_cond_broadcast(&observed);while(!poll_released)pthread_cond_wait(&observed,&observer);pthread_mutex_unlock(&observer);}
static void valid_dev(struct net_device *d){check(d&&!d->freed,"netdev-live-use");}
static void *netdev_priv(struct net_device *d){valid_dev(d);return &d->priv;}

/* HEADERS */

struct edma_hw edma_hw;
/* PROTOTYPES */
static void free_netdev(struct net_device *d){if(!d)return;valid_dev(d);check(!atomic_load(&d->borrowed),"free-after-reader-drain");for(unsigned i=0;i<6;++i){check(rcu_access_pointer(edma_hw.netdev_arr[i])!=d,"free-after-unpublish");check(dp_global_data_plane_ctx[i].dev!=d,"free-after-hostctx-clear");}if(d->dummy)check(!edma_hw.napi.added,"dummy-after-napi-del");else check(!d->registered,"free-after-unregister");d->freed=true;event(d->dummy?"DUMMY_FREE":"PORT_FREE");}
static struct net_device *allocate(bool dummy){if((dummy&&global_fail==4)||(!dummy&&fail_stage==1))return NULL;check(allocated_count<256,"allocation-ledger");struct net_device *d=calloc(1,sizeof(*d));check(d!=NULL,"host-allocation");d->dummy=dummy;d->mtu=1500;allocated[allocated_count++]=d;return d;}
static struct net_device *alloc_netdev_dummy(int n){(void)n;event("DUMMY_ALLOC");return allocate(true);}
static struct net_device *alloc_netdev_mqs(size_t size,const char *name,int assign,void (*setup)(struct net_device *),unsigned tx,unsigned rx){(void)size;(void)name;(void)assign;(void)setup;(void)tx;(void)rx;return allocate(false);}
static void ether_setup(struct net_device *d){(void)d;}
#define SET_NETDEV_DEV(d,p) ((d)->parent=(p))
static const int nss_dp_netdev_ops;
static void nss_dp_set_ethtool_ops(struct net_device *d){(void)d;}
static void nss_dp_hal_init_soc_priv_flags(struct nss_dp_dev *d){(void)d;}
static void nss_dp_hal_deinit_soc_priv_flags(struct nss_dp_dev *d){(void)d;}
static unsigned nss_dp_get_idx_from_macid(unsigned m){return m-1;}
static const char *of_get_property(struct device_node *n,const char *p,void *len){(void)n;(void)p;(void)len;return NULL;}
static bool of_find_property(struct device_node *n,const char *p,void *len){(void)p;(void)len;return n->phy_mode==1;}
static bool of_phy_is_fixed_link(struct device_node *n){return n->phy_mode==3;}
static void of_phy_deregister_fixed_link(struct device_node *n){(void)n;}
static void nss_dp_adjust_link(struct net_device *d){(void)d;}
static struct phy_device phy[6];
static struct phy_device *of_phy_get_and_connect(struct net_device *d,struct device_node *n,void (*f)(struct net_device *)){(void)d;(void)f;if(fail_stage==7)return NULL;phy[n->macid-1].live=true;return &phy[n->macid-1];}
static struct mii_bus *nss_dp_mdio_attach(struct platform_device *p){(void)p;return fail_stage==8?NULL:&bus;}
static struct phy_device *phy_connect(struct net_device *d,const char *id,void (*f)(struct net_device *),unsigned mode){(void)id;(void)f;(void)mode;if(fail_stage==9)return (void *)(intptr_t)-1;phy[d->priv.macid-1].live=true;return &phy[d->priv.macid-1];}
static void phy_attached_info(struct phy_device *p){check(p&&p->live,"phy-live");}
static void phy_disconnect(struct phy_device *p){check(p&&p->live,"phy-disconnect-once");p->live=false;++phy_disconnects;}
static void phy_stop(struct phy_device *p){check(p&&p->live,"phy-stop-live");}
static void phy_start(struct phy_device *p){check(p&&p->live,"phy-start-live");}
static void phy_start_aneg(struct phy_device *p){(void)p;}
static int nss_dp_of_get_pdata(struct device_node *n,struct net_device *d,struct nss_gmac_hal_platform_data *p){if(fail_stage==2)return -1;d->priv.macid=n->macid;d->priv.link_poll=n->phy_mode==2;p->mactype=0;return 0;}
static struct nss_gmac_hal_dev *gmac_init(struct nss_gmac_hal_platform_data *p){(void)p;return fail_stage==5?NULL:&gmac;}
static void gmac_exit(struct nss_gmac_hal_dev *p){check(p==&gmac,"gmac-exit-owner");++gmac_exits;}
static int gmac_start(struct nss_gmac_hal_dev *p){(void)p;return fail_stage==13?-1:0;}
static int gmac_stop(struct nss_gmac_hal_dev *p){(void)p;return fail_stage==14?-1:0;}
static struct nss_gmac_hal_ops gmac_ops={gmac_init,gmac_exit,gmac_start,gmac_stop};
static struct nss_gmac_hal_ops *nss_dp_hal_get_gmac_ops(unsigned n){(void)n;return fail_stage==4?NULL:&gmac_ops;}
static int ppe_port_vsi_get(unsigned d,unsigned p,uint32_t *v){(void)d;(void)p;*v=1;return fail_stage==10?-1:0;}
static int fal_port_vsi_set(unsigned d,unsigned p,uint32_t v){(void)d;(void)p;(void)v;return fail_stage==11?-1:0;}
static int register_netdev(struct net_device *d){check(!rtnl_held,"register-wrapper-not-locked");if(fail_stage==12)return -1;d->registered=true;return 0;}
static void unregister_netdev(struct net_device *d){check(!rtnl_held&&d->registered,"unregister-wrapper");d->registered=false;}
static struct nss_dp_data_plane_ops host_ops;
static struct nss_dp_data_plane_ops *nss_dp_hal_get_data_plane_ops(void){return fail_stage==3?NULL:&host_ops;}
static int edma_of_get_pdata(struct resource *r){if(global_fail==1)return -1;*r=dma_resource;edma_hw.pdev=&dma_pdev;static struct device_node node={"edma",0,0};edma_hw.device_node=&node;edma_hw.txdesc_rings=edma_hw.txcmpl_rings=edma_hw.rxfill_rings=edma_hw.rxdesc_rings=configured_rings;edma_hw.txdesc_ring_start=23;edma_hw.txdesc_ring_end=23+configured_rings;edma_hw.txcmpl_ring_start=7;edma_hw.txcmpl_ring_end=7+configured_rings;edma_hw.rxdesc_ring_start=15;edma_hw.rxdesc_ring_end=15+configured_rings;edma_hw.rxfill_ring_start=7;edma_hw.rxfill_ring_end=7+configured_rings;return 0;}
static unsigned long resource_size(struct resource *r){return r->end-r->start+1;}
static struct resource *request_mem_region(unsigned long p,unsigned long n,const char *s){(void)p;(void)n;(void)s;if(global_fail==2)return NULL;check(!region_live,"region-acquire-once");region_live=true;return &dma_resource;}
static void release_mem_region(unsigned long p,unsigned long n){(void)p;(void)n;check(region_live&&!mapping_live,"region-after-unmap");region_live=false;++regions_released;}
static void *ioremap(unsigned long p,unsigned long n){(void)p;(void)n;if(global_fail==3)return NULL;mapping_live=true;return registers;}
static void iounmap(void *p){check(mapping_live&&p==registers,"mmio-unmap-owned");mapping_live=false;++unmaps;event("MMIO_RELEASE");}
static void platform_set_drvdata(struct platform_device *p,void *v){p->drvdata=v;}
static void *platform_get_drvdata(struct platform_device *p){return p->drvdata;}
int edma_hw_init(struct edma_hw *h){if(global_fail==5)return -1;h->edma_initialized=true;h->active=0;unsigned n=configured_rings;h->txcmpl_ring=calloc(n,sizeof(*h->txcmpl_ring));h->rxdesc_ring=calloc(n,sizeof(*h->rxdesc_ring));h->rxfill_ring=calloc(n,sizeof(*h->rxfill_ring));check(h->txcmpl_ring&&h->rxdesc_ring&&h->rxfill_ring,"mock-rings");for(unsigned i=0;i<n;++i){h->txcmpl_ring[i].id=7+i;h->rxdesc_ring[i].id=15+i;h->rxfill_ring[i].id=7+i;}h->txcmpl_intr_mask=h->rxdesc_intr_mask=h->rxfill_intr_mask=h->misc_intr_mask=3;return 0;}
void edma_cleanup_rings(struct edma_hw *h){check(!in_rcu&&!rcu_readers&&!irq_live&&!h->napi.added,"rings-after-cpu-drain");++ring_cleanups;free(h->txcmpl_ring);free(h->rxdesc_ring);free(h->rxfill_ring);h->txcmpl_ring=NULL;h->rxdesc_ring=NULL;h->rxfill_ring=NULL;event("HOST_RINGS_FREE");}
uint32_t edma_reg_read(uint32_t off){check(mapping_live,"mmio-read-live");++mmio_reads;return registers[(off/4)%(sizeof(registers)/4)];}
void edma_reg_write(uint32_t off,uint32_t v){check(mapping_live,"mmio-write-live");++mmio_writes;if(off==EDMA_REG_PORT_CTRL&&v==EDMA_DISABLE){++port_disables;event("PORT_DISABLE");}registers[(off/4)%(sizeof(registers)/4)]=v;}
struct irq_entry {int irq;void *id;bool live;} irqs[64];static unsigned irq_count;
static int platform_get_irq(struct platform_device *p,unsigned n){check(p==&dma_pdev,"irq-device");++lookup_calls;return lookup_calls==lookup_fail?-1:100+(int)n;}
static int request_irq(int irq,irqreturn_t (*handler)(int,void *),unsigned flags,const char *name,void *id){(void)handler;(void)flags;(void)name;ASSERT_RTNL();++request_calls;if(request_calls==request_fail)return -1;check(irq_count<64&&id==&dma_pdev,"irq-acquire-owner");irqs[irq_count++]=(struct irq_entry){irq,id,true};++irq_live;return 0;}
static void free_irq(int irq,void *id){ASSERT_RTNL();int i=(int)irq_count-1;while(i>=0&&!irqs[i].live)--i;check(i>=0&&irqs[i].irq==irq&&irqs[i].id==id,"reverse-acquired-irq-owner");irqs[i].live=false;--irq_live;++irq_frees;}
static void netif_napi_add(struct net_device *d,struct napi_struct *n,int (*poll)(struct napi_struct *,int)){(void)poll;valid_dev(d);check(d->dummy&&!n->added,"dummy-napi-owner");n->dev=d;n->added=true;n->enabled=false;++napi_adds;}
static void netif_napi_del(struct napi_struct *n){check(n->added&&!n->enabled&&!rcu_readers&&!irq_live,"napi-del-disabled-drained");valid_dev(n->dev);n->added=false;++napi_dels;}
static void napi_enable(struct napi_struct *n){check(n->added&&!n->enabled&&!n->dev->freed,"napi-enable-once");n->enabled=true;++napi_enables;}
static void napi_disable(struct napi_struct *n){check(n->enabled&&!n->dev->freed,"napi-disable-once");n->enabled=false;check(!atomic_load(&n->owned),"ownership-released-before-disable");++napi_disables;}
static bool napi_complete(struct napi_struct *n){check(in_rcu,"complete-inside-fullpoll");atomic_store(&n->owned,false);return complete_result;}
static bool napi_schedule_prep(struct napi_struct *n){return n->enabled;}
static void __napi_schedule(struct napi_struct *n){atomic_store(&n->owned,true);}
static uint32_t edma_clean_rx(struct edma_hw *h,int b,struct edma_rxdesc_ring *r){(void)h;(void)b;(void)r;return 0;}
uint32_t edma_clean_tx(struct edma_hw *h,struct edma_txcmpl_ring *r){(void)h;(void)r;return 0;}
int edma_alloc_rx_buffer(struct edma_hw *h,struct edma_rxfill_ring *r){(void)h;(void)r;return 0;}
static bool netif_queue_stopped(struct net_device *d){valid_dev(d);check(in_rcu&&borrowed[d->priv.macid-1]==d,"port-dereference-protocol");pause_poll(1);return d->stopped;}
static bool netif_carrier_ok(struct net_device *d){valid_dev(d);return d->carrier;}
static void netif_start_queue(struct net_device *d){valid_dev(d);d->stopped=false;}
static void netif_stop_queue(struct net_device *d){valid_dev(d);d->stopped=true;}
static void netif_carrier_on(struct net_device *d){valid_dev(d);d->carrier=true;}
static void netif_carrier_off(struct net_device *d){valid_dev(d);d->carrier=false;}
static void netif_device_detach(struct net_device *d){valid_dev(d);}
static void netif_device_attach(struct net_device *d){valid_dev(d);}
static void netif_tx_disable(struct net_device *d){valid_dev(d);d->stopped=true;}
static void dev_core_stats_tx_dropped_inc(struct net_device *d){valid_dev(d);}
static void dev_kfree_skb_any(struct sk_buff *s){(void)s;}
static int fake_init(struct nss_dp_data_plane_ctx *c){valid_dev(c->dev);++override_inits;return 0;}
static int fake_open(struct nss_dp_data_plane_ctx *c,uint32_t a,uint32_t b,uint32_t d){(void)c;(void)a;(void)b;(void)d;return 0;}
static int fake_close(struct nss_dp_data_plane_ctx *c){(void)c;++nss_closes;return 0;}
static int fake_value(struct nss_dp_data_plane_ctx *c,uint32_t v){(void)c;(void)v;return 0;}
static int fake_mac(struct nss_dp_data_plane_ctx *c,uint8_t *v){(void)c;(void)v;return 0;}
static netdev_tx_t fake_xmit(struct nss_dp_data_plane_ctx *c,struct sk_buff *s){(void)c;(void)s;return 0;}
static void fake_features(struct nss_dp_data_plane_ctx *c){(void)c;}
static struct nss_dp_data_plane_ops fake_ops={.init=fake_init,.open=fake_open,.close=fake_close,.deinit=fake_close,.link_state=fake_value,.mac_addr=fake_mac,.change_mtu=fake_value,.xmit=fake_xmit,.set_features=fake_features,.pause_on_off=fake_value};
static struct nss_dp_data_plane_ops nss_dp_quarantine_ops;
/* FUNCTIONS */

static void begin(void){++cases;check(!mapping_live&&!region_live&&!irq_live&&!rcu_readers&&!rtnl_held,"case-start-balanced");memset(&edma_hw,0,sizeof(edma_hw));memset(&dp_global_ctx,0,sizeof(dp_global_ctx));memset(dp_global_data_plane_ctx,0,sizeof(dp_global_data_plane_ctx));memset(registers,0,sizeof(registers));fail_stage=global_fail=lookup_fail=request_fail=lookup_calls=request_calls=0;irq_count=0;allocated_count=0;configured_rings=1;pause_kind=0;poll_paused=poll_released=grace_started=wait_started=retire_finished=false;host_ops=(struct nss_dp_data_plane_ops){.init=edma_if_init,.open=edma_if_open,.close=edma_if_close,.deinit=edma_if_deinit,.link_state=fake_value,.mac_addr=fake_mac,.change_mtu=fake_value,.set_features=fake_features,.pause_on_off=fake_value,.xmit=fake_xmit};nss_dp_quarantine_ops=fake_ops;}
static void end(void){check(!irq_live&&!mapping_live&&!region_live&&!rtnl_held&&!rcu_readers,"case-end-balanced");for(unsigned i=0;i<allocated_count;++i){struct net_device *d=allocated[i];check(d->freed,"all-netdevs-retired");if(d->priv.plane_lock.initialized){pthread_mutex_destroy(&d->priv.plane_lock.mutex);pthread_mutex_destroy(&d->priv.stats_lock.mutex);pthread_mutex_destroy(&d->priv.plane_wait.mutex);pthread_cond_destroy(&d->priv.plane_wait.cond);}free(d);}}
static struct platform_device ports[6];static struct device_node nodes[6];
static struct net_device *probe(unsigned i,int mode){nodes[i]=(struct device_node){"port",i+1,mode};ports[i].dev.of_node=&nodes[i];int ret=nss_dp_probe(&ports[i]);if(ret)return NULL;return dp_global_ctx.nss_dp[i]->netdev;}
static void remove_all(void){fail_stage=0;nss_dp_remove(&ports[0]);edma_cleanup(false);edma_cleanup(false);}
static void init_failures(void){for(unsigned f=1;f<=5;++f){begin();global_fail=f;check(edma_init()!=0,"init-injected-failure");check(!edma_hw.reg_base&&!edma_hw.reg_resource&&!edma_hw.napi_dev&&!mapping_live&&!region_live,"init-failure-clears-owners");global_fail=0;check(!edma_init(),"init-failure-retry");edma_cleanup(false);end();}}
static void probe_failures(void){for(unsigned stage=1;stage<=12;++stage){begin();check(!edma_init(),"init");fail_stage=stage==6?7:stage;int mode=stage==6?3:(stage==7||stage>=10)?1:(stage==8||stage==9)?2:0;check(!probe(0,mode),"probe-injected-failure");check(!dp_global_ctx.nss_dp[0]&&!dp_global_data_plane_ctx[0].dev&&!rcu_access_pointer(edma_hw.netdev_arr[0])&&!edma_hw.active&&!edma_hw.dp_override_cnt,"probe-failure-no-publication-or-override");fail_stage=0;check(probe(0,0)!=NULL,"probe-retry");remove_all();end();}}
static void irq_failures(void){for(unsigned rings=1;rings<=3;rings+=2)for(unsigned kind=0;kind<2;++kind)for(unsigned k=1;k<=rings*3+1;++k){begin();configured_rings=rings;check(!edma_init(),"irq-init");if(kind)request_fail=k;else lookup_fail=k;check(!probe(0,0),"irq-injected-failure");check(!irq_live&&!edma_hw.napi_added&&!edma_hw.napi_enabled&&!edma_hw.dp_override_cnt,"irq-full-reverse-unwind");lookup_fail=request_fail=lookup_calls=request_calls=0;check(probe(0,0)!=NULL,"irq-retry");remove_all();end();}}
static void memberships(void){for(unsigned mode=0;mode<4;++mode){begin();check(!edma_init(),"member-init");struct net_device *a=probe(0,0),*b=probe(1,0);check(a&&b,"two-probes");rtnl_lock();check(!nss_dp_open(b),"peer-open");check(!edma_if_open(&dp_global_data_plane_ctx[1],0,0,0)&&edma_hw.active==1,"duplicate-open-idempotent");if(mode==0){fail_stage=13;check(nss_dp_open(a)!=0,"late-open-failure");}else{check(!nss_dp_open(a),"first-open");if(mode==1){fail_stage=14;check(nss_dp_close(a)!=0,"early-close-failure");}else if(mode==2){a->priv.data_plane_ops=&fake_ops;struct nss_dp_data_plane_ctx fake={a};a->priv.dpc=&fake;nss_dp_plane_quarantine(&a->priv);}else nss_dp_plane_quarantine(&a->priv);}check(edma_hw.active==1&&edma_hw.napi_enabled&&edma_hw.host_open[1]&&!edma_hw.host_open[0],"peer-membership-survives");check(dp_global_data_plane_ctx[0].dev==a,"quarantine-keeps-static-hostctx");check(!nss_closes,"quarantine-never-guesses-nss-close");nss_dp_plane_quarantine(&a->priv);check(edma_hw.active==1,"repeat-quarantine-no-double-close");fail_stage=0;check(!nss_dp_close(b)&&!nss_dp_close(b)&&!edma_hw.active&&!edma_hw.napi_enabled,"duplicate-close-idempotent");rtnl_unlock();remove_all();end();}}
static void takeover_exit(void){begin();check(!edma_init(),"takeover-init");struct nss_dp_data_plane_ctx next[6];for(unsigned i=0;i<6;++i){struct net_device *d=probe(i,0);check(d!=NULL,"takeover-probe");rtnl_lock();check(!nss_dp_open(d),"takeover-open");next[i].dev=d;check(!nss_dp_override_data_plane(d,&fake_ops,&next[i]),"normal-takeover");check(!edma_if_deinit(&dp_global_data_plane_ctx[i]),"repeat-host-deinit");check(edma_hw.dp_override_cnt==i+1,"unique-override-accounting");check(dp_global_data_plane_ctx[i].dev==d,"takeover-keeps-static-context");rtnl_unlock();}check(!edma_hw.edma_initialized&&!edma_hw.napi_dev&&mapping_live&&region_live&&!irq_live,"override-retains-mmio-only");unsigned disables=port_disables,oldunmaps=unmaps;remove_all();check(port_disables==disables+1&&unmaps==oldunmaps+1&&!dma_pdev.drvdata,"exit-final-disable-before-release");unsigned writes=mmio_writes;edma_cleanup(false);check(mmio_writes==writes,"repeat-exit-no-mmio");end();}
static void foreign_context(void){begin();check(!edma_init(),"foreign-init");struct net_device *d=probe(0,0),*other=allocate(false);check(d&&other,"foreign-allocation");other->priv.macid=1;other->priv.netdev=other;rtnl_lock();nss_dp_clear_host_ctx(&other->priv);check(dp_global_data_plane_ctx[0].dev==d,"foreign-static-context-kept");rtnl_unlock();free_netdev(other);remove_all();end();}
static void complete_and_reprobe(void){begin();check(!edma_init(),"rearm-init");struct net_device *d=probe(0,0);check(d!=NULL,"rearm-probe");rtnl_lock();check(!nss_dp_open(d),"rearm-open");rtnl_unlock();registers[EDMA_REG_RXDESC_INT_MASK(15)/4]=registers[EDMA_REG_TX_INT_MASK(7)/4]=0;complete_result=false;edma_napi(&edma_hw.napi,64);check(!registers[EDMA_REG_RXDESC_INT_MASK(15)/4]&&!registers[EDMA_REG_TX_INT_MASK(7)/4],"complete-false-no-rearm");complete_result=true;edma_napi(&edma_hw.napi,64);check(registers[EDMA_REG_RXDESC_INT_MASK(15)/4]&&registers[EDMA_REG_TX_INT_MASK(7)/4],"complete-true-rearms");check(!probe(0,0)&&dp_global_data_plane_ctx[0].dev==d,"foreign-claim-not-overwritten");struct nss_dp_data_plane_ctx nss={d};rtnl_lock();check(!nss_dp_override_data_plane(d,&fake_ops,&nss),"reprobe-takeover");rtnl_unlock();nss_dp_remove(&ports[0]);check(!probe(0,0)&&!dp_global_data_plane_ctx[0].dev&&!edma_hw.active&&edma_hw.dp_override_cnt==1,"overridden-id-reprobe-rejected");for(unsigned i=1;i<6;++i){struct net_device *p=probe(i,0);check(p!=NULL,"other-id-probe");nss.dev=p;rtnl_lock();check(!nss_dp_override_data_plane(p,&fake_ops,&nss),"other-id-takeover");rtnl_unlock();}check(edma_hw.dp_override_cnt==6&&!edma_hw.edma_initialized,"all-ids-threshold");remove_all();end();}
static void *poll_worker(void *p){(void)p;atomic_store(&edma_hw.napi.owned,true);edma_napi(&edma_hw.napi,64);return NULL;}
static struct net_device *retiring;
static void finish_retire_worker(void){pthread_mutex_lock(&observer);retire_finished=true;pthread_cond_broadcast(&observed);pthread_mutex_unlock(&observer);}
static void *retire_worker(void *p){(void)p;rtnl_lock();nss_dp_plane_quarantine(&retiring->priv);rtnl_unlock();finish_retire_worker();return NULL;}
static void *abort_worker(void *p){(void)p;nss_dp_abort_host_probe(&retiring->priv);finish_retire_worker();return NULL;}
static void admitted_reader(void){begin();check(!edma_init(),"admitted-init");retiring=probe(0,0);rtnl_lock();check(!nss_dp_open(retiring),"admitted-open");rtnl_unlock();struct nss_dp_plane_ref ref;check(nss_dp_plane_get(&retiring->priv,&ref),"old-reference-admitted");pthread_t writer;pthread_create(&writer,NULL,retire_worker,NULL);pthread_mutex_lock(&observer);while(!wait_started&&!retire_finished)pthread_cond_wait(&observed,&observer);check(wait_started&&!retire_finished,"quarantine-waits-admitted-reference");check(edma_hw.host_open[0]&&edma_hw.active==1&&rcu_access_pointer(edma_hw.netdev_arr[0])==retiring,"membership-not-retired-before-admitted-drain");pthread_mutex_unlock(&observer);struct nss_dp_plane_ref denied;check(!nss_dp_plane_get(&retiring->priv,&denied),"new-admission-closed");check(ref.ops==&host_ops&&ref.dpc==&dp_global_data_plane_ctx[0],"old-pair-snapshot-preserved");nss_dp_plane_put(&retiring->priv);pthread_join(writer,NULL);check(!edma_hw.active&&!edma_hw.host_open[0]&&!edma_hw.napi_enabled,"membership-retired-after-admitted-drain");remove_all();end();}
static void reader_schedules(void){for(unsigned mode=1;mode<=2;++mode){begin();check(!edma_init(),"reader-init");struct net_device *peer=probe(1,0);retiring=probe(0,0);rtnl_lock();check(!nss_dp_open(peer),"reader-peer-open");if(mode==2)check(!nss_dp_open(retiring),"tail-port-open");rtnl_unlock();pause_kind=mode;pthread_t poll,retire;pthread_create(&poll,NULL,poll_worker,NULL);pthread_mutex_lock(&observer);while(!poll_paused)pthread_cond_wait(&observed,&observer);pthread_mutex_unlock(&observer);if(mode==1)pthread_create(&retire,NULL,abort_worker,NULL);else{rtnl_lock();edma_if_close(&dp_global_data_plane_ctx[1]);rtnl_unlock();pthread_create(&retire,NULL,retire_worker,(void *)1);}pthread_mutex_lock(&observer);while(!grace_started&&!retire_finished)pthread_cond_wait(&observed,&observer);check(grace_started&&!retire_finished,"retirement-grace-wait");check(!retiring->freed&&mapping_live,"paused-reader-owner-live");poll_released=true;pthread_cond_broadcast(&observed);pthread_mutex_unlock(&observer);pthread_join(poll,NULL);pthread_join(retire,NULL);pause_kind=0;check(!rcu_access_pointer(edma_hw.netdev_arr[0]),"reader-retired-port");if(mode==1)check(edma_hw.active==1&&edma_hw.napi_enabled,"reader-peer-still-active");else{check(!edma_hw.napi_enabled&&!edma_hw.active,"tail-member-retired");check(!registers[EDMA_REG_RXDESC_INT_MASK(15)/4]&&!registers[EDMA_REG_TX_INT_MASK(7)/4],"tail-final-mask");}remove_all();end();}}
int main(int argc,char **argv){check(argc==2,"fixture-mode");if(!strcmp(argv[1],"trace"))trace_on=true;else check(!strcmp(argv[1],"suite"),"known-mode");init_failures();probe_failures();irq_failures();memberships();foreign_context();takeover_exit();complete_and_reprobe();admitted_reader();reader_schedules();printf("cases=%u checks=%u irq_frees=%u adds=%u dels=%u enables=%u disables=%u\n",cases,atomic_load(&checks),irq_frees,napi_adds,napi_dels,napi_enables,napi_disables);return 0;}
