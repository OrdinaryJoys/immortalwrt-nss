/* Host API substitutes, not a scheduler, DMA engine, or target ABI. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error This fixture requires enabled checks
#endif
#define KERNEL_VERSION(a,b,c) (((a)<<16) | ((b)<<8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define NSS_DP_IPQ807X 1
#define NSS_DP_PPE_SUPPORT 1
#define NSS_DP_MAC_POLL_SUPPORT 1
#define NSS_DP_EDMA_SWITCH_DEV_ID 0
#define NSS_DP_MAX_PORTS 6
#define MAX_ETH_TYPES 2
#define NSS_DP_PRIV_FLAG(x) (1UL << __NSS_DP_PRIV_FLAG_ ## x)
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 1
#define EXPORT_SYMBOL(x)
#define __iomem
#define __rcu
#define READ_ONCE(x) (x)
#define netdev_dbg(...) ((void)0)
#define netdev_err(...) ((void)0)
#define might_sleep() ((void)0)
#define WARN_ON_ONCE(x) host_internal(!(x), "unexpected-warning")
#define BIT(n) (1UL << (n))
typedef int netdev_tx_t;
typedef uint64_t u64;
typedef uint8_t u8;
typedef unsigned spinlock_t;
typedef unsigned wait_queue_head_t;
struct nss_dp_dev;
struct nss_dp_gmac_stats;
struct nss_gmac_hal_platform_data;
struct resource;
struct napi_struct { unsigned unused; };
struct nss_dp_hal_info { unsigned unused; };
struct nss_dp_hal_gmac_stats { unsigned unused; };
struct rtnl_link_stats64 {
    uint64_t tx_dropped, rx_dropped, tx_packets, rx_packets, tx_bytes, rx_bytes;
};
struct phy_device { unsigned starts, stops, anegs; };
enum { __QUEUE_STATE_DRV_XOFF, __QUEUE_STATE_STACK_XOFF, __QUEUE_STATE_FROZEN };
struct netdev_queue {
    unsigned long state;
    unsigned starts, stops, wakes, schedules;
};
struct net_device {
    void *priv;
    unsigned mtu, num_tx_queues, real_num_tx_queues, id;
    unsigned char dev_addr[6];
    uint64_t features, hw_features, vlan_features, wanted_features;
    struct rtnl_link_stats64 stats;
    struct netdev_queue txq[4];
    bool running, device_present, carrier;
    unsigned attaches, detaches, disables, activations;
};
struct sk_buff { unsigned freed; };
static const char *case_name;
static bool rtnl_held;
static void check(bool condition, const char *marker)
{
    if (!condition) {
        fprintf(stderr, "MQ_FAIL %s %s\n", case_name, marker);
        exit(86);
    }
}
static int host_internal(bool condition, const char *marker)
{
    if (!condition) {
        fprintf(stderr, "MQ_HARNESS %s\n", marker);
        exit(87);
    }
    return 0;
}
#define ASSERT_RTNL() ((void)host_internal(rtnl_held, "rtnl"))
#define spin_lock_init(p) (*(p)=0)
#define spin_lock_bh(p) ((void)host_internal((*(p))++ == 0, "nested-lock"))
#define spin_unlock_bh(p) ((void)host_internal((*(p))-- == 1, "unbalanced-lock"))
#define init_waitqueue_head(p) (*(p)=0)
/* Sequential tests require an already-drained reader set; no fake blocking. */
#define wait_event(w,condition) do { (void)(w); host_internal(!!(condition), "undrained-reader"); } while (0)
#define wake_up_all(p) ((void)(p))
static inline int test_bit(unsigned n, const unsigned long *v) { return !!(*v & BIT(n)); }
static inline void set_bit(unsigned n, unsigned long *v) { *v |= BIT(n); }
static inline void clear_bit(unsigned n, unsigned long *v) { *v &= ~BIT(n); }
#define netdev_priv(dev) ((dev)->priv)
#define netif_running(dev) ((dev)->running)
static struct netdev_queue *netdev_get_tx_queue(struct net_device *dev, unsigned i)
{
    host_internal(i < dev->num_tx_queues && i < 4, "txq-bounds");
    return &dev->txq[i];
}
static void netif_tx_start_queue(struct netdev_queue *q)
{
    clear_bit(__QUEUE_STATE_DRV_XOFF, &q->state);
    q->starts++;
}
static void netif_tx_stop_queue(struct netdev_queue *q)
{
    set_bit(__QUEUE_STATE_DRV_XOFF, &q->state);
    q->stops++;
}
static void netif_tx_wake_queue(struct netdev_queue *q)
{
    q->wakes++;
    if (test_bit(__QUEUE_STATE_DRV_XOFF, &q->state)) {
        clear_bit(__QUEUE_STATE_DRV_XOFF, &q->state);
        q->schedules++;
    }
}
static void netif_start_queue(struct net_device *dev)
{
    netif_tx_start_queue(netdev_get_tx_queue(dev, 0));
}
static void netif_tx_start_all_queues(struct net_device *dev)
{
    for (unsigned i=0; i<dev->num_tx_queues; i++)
        netif_tx_start_queue(netdev_get_tx_queue(dev, i));
}
static void netif_stop_queue(struct net_device *dev)
{
    netif_tx_stop_queue(netdev_get_tx_queue(dev, 0));
}
static void netif_tx_wake_all_queues(struct net_device *dev)
{
    for (unsigned i=0; i<dev->num_tx_queues; i++)
        netif_tx_wake_queue(netdev_get_tx_queue(dev, i));
}
static void netif_tx_stop_all_queues(struct net_device *dev)
{
    for (unsigned i=0; i<dev->num_tx_queues; i++)
        netif_tx_stop_queue(netdev_get_tx_queue(dev, i));
}
static void netif_tx_disable(struct net_device *dev)
{
    dev->disables++;
    netif_tx_stop_all_queues(dev);
}
/* Linux 6.18.38 dev.c:3467-3489: attach wakes only on PRESENT 0->1 + running. */
static void netif_device_detach(struct net_device *dev)
{
    bool was_present=dev->device_present;
    dev->device_present=false;
    dev->detaches++;
    if (was_present && netif_running(dev))
        netif_tx_stop_all_queues(dev);
}
static void netif_device_attach(struct net_device *dev)
{
    bool was_present=dev->device_present;
    dev->device_present=true;
    dev->attaches++;
    if (!was_present && netif_running(dev))
        netif_tx_wake_all_queues(dev);
}
/* Carrier/linkwatch/dev_activate do not clear driver XOFF; no scheduler here. */
#define netif_carrier_off(dev) ((dev)->carrier=false)
#define netif_carrier_on(dev) ((dev)->carrier=true)
#define phy_start(p) ((p)->starts++)
#define phy_stop(p) ((p)->stops++)
#define phy_start_aneg(p) ((p)->anegs++)
static void dev_core_stats_tx_dropped_inc(struct net_device *dev) { dev->stats.tx_dropped++; }
static void dev_kfree_skb_any(struct sk_buff *skb)
{
    host_internal(skb && !skb->freed, "skb-double-free");
    skb->freed++;
}
static struct { bool enable_polling_task; } dp_global_ctx;
static unsigned polling_starts;
static void ssdk_mac_sw_sync_work_start(unsigned id)
{
    host_internal(id == NSS_DP_EDMA_SWITCH_DEV_ID, "polling-device");
    polling_starts++;
}
static bool edma_retire_port(struct net_device *dev, uint32_t macid);
static struct net_device *host_other_device(struct net_device *dev);
