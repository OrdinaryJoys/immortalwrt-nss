/* Host substitutes only: never claim kernel scheduling, lockdep or target ABI. */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

#define KERNEL_VERSION(a,b,c) (((a)<<16) | ((b)<<8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define CONFIG_RFS_ACCEL 1
#define __iomem
#define EXPORT_SYMBOL(x)
#define likely(x) (x)
#define unlikely(x) (x)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)
#define netdev_dbg(...) ((void)0)
#define netdev_info(...) ((void)0)
#define netdev_warn(...) ((void)0)
#define netdev_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define WARN_ON(x) ((x) ? (fprintf(stderr,"host WARN_ON %s:%d\n",__FILE__,__LINE__), 1) : 0)
#define WARN_ON_ONCE(x) WARN_ON(x)
#define might_sleep() ((void)0)
#define NSS_DP_MAX_PORTS 6
#define NSS_DP_HAL_MAX_PORTS 6
#define NSS_DP_START_IFNUM 1
#define MAX_ETH_TYPES 2
#define NSS_DP_PRIV_FLAG(x) (1UL << __NSS_DP_PRIV_FLAG_ ## x)
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 1
typedef int netdev_tx_t;
typedef uint32_t u32;
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint64_t u64;
typedef pthread_mutex_t spinlock_t;
typedef struct { atomic_int counter; } atomic_t;
typedef struct { pthread_mutex_t lock; pthread_cond_t cond; pthread_mutex_t *reader_lock; } wait_queue_head_t;
#define spin_lock_init(l) assert(pthread_mutex_init((l),NULL)==0)
#define spin_lock_bh(l) assert(pthread_mutex_lock(l)==0)
#define spin_unlock_bh(l) assert(pthread_mutex_unlock(l)==0)
#define spin_lock_irqsave(l,f) do { (f)=0; spin_lock_bh(l); } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(f); spin_unlock_bh(l); } while(0)
#define atomic_set(a,v) atomic_store(&(a)->counter,(v))
#define atomic_read(a) atomic_load(&(a)->counter)
#define atomic_inc(a) ((void)atomic_fetch_add(&(a)->counter,1))
#define atomic_dec_and_test(a) (atomic_fetch_sub(&(a)->counter,1)==1)
#define init_waitqueue_head(w) do { assert(pthread_mutex_init(&(w)->lock,NULL)==0); assert(pthread_cond_init(&(w)->cond,NULL)==0); (w)->reader_lock=NULL; } while(0)
static void host_writer_waiting(void);
/* Host-only stronger predicate synchronization avoids a C11 mixed-access race;
 * it does not model Linux's READ_ONCE/waitqueue memory-order implementation. */
#define host_condition(w,condition) ({ assert((w).reader_lock); assert(pthread_mutex_lock((w).reader_lock)==0); bool value=!!(condition); assert(pthread_mutex_unlock((w).reader_lock)==0); value; })
#define wait_event(w,condition) do { assert(pthread_mutex_lock(&(w).lock)==0); host_writer_waiting(); while(!host_condition(w,condition)) assert(pthread_cond_wait(&(w).cond,&(w).lock)==0); assert(pthread_mutex_unlock(&(w).lock)==0); } while(0)
#define wake_up_all(w) do { assert(pthread_mutex_lock(&(w)->lock)==0); assert(pthread_cond_broadcast(&(w)->cond)==0); assert(pthread_mutex_unlock(&(w)->lock)==0); } while(0)
#define wake_up(w) wake_up_all(w)
static pthread_mutex_t host_rtnl = PTHREAD_MUTEX_INITIALIZER;
static _Thread_local int host_rtnl_held;
static void rtnl_lock(void) { assert(pthread_mutex_lock(&host_rtnl)==0); host_rtnl_held=1; }
static void rtnl_unlock(void) { host_rtnl_held=0; assert(pthread_mutex_unlock(&host_rtnl)==0); }
static int rtnl_is_locked(void) { return host_rtnl_held; }
#define ASSERT_RTNL() assert(rtnl_is_locked())
#define lockdep_assert_held(x) ((void)(x))
struct nss_dp_dev;
struct nss_gmac_hal_platform_data;
struct sk_buff;
struct net_device;
struct rtnl_link_stats64 { uint64_t tx_dropped, rx_dropped, tx_packets, rx_packets, tx_bytes, rx_bytes; };
enum { ETH_SS_STATS = 1 };
struct ethtool_stats { unsigned host_placeholder; };
struct net_device_ops { int (*ndo_open)(struct net_device *); int (*ndo_stop)(struct net_device *); };
struct rps_dev_flow { unsigned cpu; };
struct rps_dev_flow_table { unsigned log; struct rps_dev_flow flows[4]; };
struct rps_sock_flow_table { unsigned mask; uint32_t ents[4]; };
struct netdev_rx_queue { struct rps_dev_flow_table *rps_flow_table; };
static struct { struct rps_sock_flow_table *rps_sock_flow_table; unsigned rps_cpu_mask; } net_hotdata;
struct net_device {
    uint64_t features, hw_features, vlan_features, wanted_features;
    void *priv;
    const struct net_device_ops *netdev_ops;
    unsigned mtu;
    unsigned char dev_addr[6];
    struct rtnl_link_stats64 stats;
    struct netdev_rx_queue *_rx;
    bool queue_started, carrier, device_present;
};
struct sk_buff { unsigned len, hash, rx_queue, protocol, ip_summed; bool queue_recorded; int freed; struct net_device *dev; };
struct phy_device { bool link; unsigned speed; };
struct napi_struct { unsigned host_placeholder; };
struct nss_dp_hal_info { unsigned host_placeholder; };
struct nss_dp_hal_gmac_stats { unsigned host_placeholder; };
#define netdev_priv(dev) ((dev)->priv)
#define netif_running(dev) ((dev)->queue_started)
#define netif_device_detach(dev) ((dev)->device_present=false)
#define netif_device_attach(dev) ((dev)->device_present=true)
#define netif_carrier_on(dev) ((dev)->carrier=true)
#define netif_carrier_off(dev) ((dev)->carrier=false)
#define netif_stop_queue(dev) ((dev)->queue_started=false)
#define netif_start_queue(dev) ((dev)->queue_started=true)
#define netif_wake_queue(dev) ((dev)->queue_started=true)
#define netif_tx_disable(dev) ((dev)->queue_started=false)
#define netif_tx_stop_all_queues(dev) ((dev)->queue_started=false)
#define netif_tx_wake_all_queues(dev) ((dev)->queue_started=true)
#define phy_stop(dev) ((void)(dev))
#define phy_start(dev) ((void)(dev))
#define phy_start_aneg(dev) ((void)(dev))
#define rcu_dereference(x) (x)
#define skb_rx_queue_recorded(skb) ((skb)->queue_recorded)
#define skb_get_rx_queue(skb) ((skb)->rx_queue)
#define skb_get_hash(skb) ((skb)->hash)
#define hash_32(hash,bits) ((hash) & ((1U<<(bits))-1))
static void dev_kfree_skb_any(struct sk_buff *skb) { assert(skb); assert(++skb->freed==1); }
#define dev_kfree_skb(skb) dev_kfree_skb_any(skb)
#define consume_skb(skb) dev_kfree_skb_any(skb)
#define dev_core_stats_tx_dropped_inc(dev) ((dev)->stats.tx_dropped++)
#define dev_core_stats_rx_dropped_inc(dev) ((dev)->stats.rx_dropped++)
static unsigned eth_type_trans(struct sk_buff *skb, struct net_device *dev) { assert(skb->dev==dev); return 0x0800; }
static void host_napi_receive(struct napi_struct *, struct sk_buff *);
#define napi_gro_receive(napi,skb) host_napi_receive((napi),(skb))
/* Structs and state-machine functions below this point are extracted from C. */
