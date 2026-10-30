/* Checked host framework model around complete extracted functions, not Linux ABI. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

typedef uint8_t u8;
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
typedef unsigned long a_ulong_t;
typedef int a_bool_t;
typedef int sw_error_t;
typedef uint32_t fal_pbmp_t;
typedef uint32_t fal_port_t;
typedef int hsl_init_mode;
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define NSS_DP_IPQ807X 1
#define NSS_DP_PPE_SUPPORT 1
#define NSS_DP_NATIVE_INIT_STAGES 1
#define CONFIG_NET_DSA 0
#define HPPE 1
#define IN_MISC 1
#define IS_ENABLED(x) (x)
#define __init
#define __exit
#define A_TRUE 1
#define A_FALSE 0
#define SW_OK 0
#define SW_BAD_VALUE (-2)
#define SW_NOT_FOUND (-12)
#define SW_NOT_INITIALIZED (-21)
#define IFNAMSIZ 16
#define ETH_ALEN 6
#define ETH_MAX_MTU 65535
#define ARPHRD_ETHER 1
#define IFF_802_1Q_VLAN 1U
#define IFF_LIVE_ADDR_CHANGE 2U
#define NSS_DP_MAX_PORTS 8
#define NSS_DP_RX_BUFFER_SIZE 2048
#define NSS_DP_NETDEV_TX_QUEUE_NUM 1
#define NSS_DP_NETDEV_RX_QUEUE_NUM 1
#define NSS_DP_GSO_MAX_SEGS 16
#define NSS_DP_SWITCH_ID 0
#define NSS_DP_SW_ETHTYPE_PID 0
#define ETH_P_NONE 0
#define ETH_P_SLOW 0x8809
#define NET_NAME_PREDICTABLE 1
#define NET_NAME_ENUM 2
#define HZ 100
#define MII_BUS_ID_SIZE 20
#define PHY_ID_FMT "%s:%02x"
#define MP_GEPHY 5
#define SSDK_MII_DEFAULT_BUS_ID 0
#define NOTIFY_DONE 0
#define NETDEV_REGISTER 1
#define NETDEV_UNREGISTER 2
#define NETDEV_CHANGENAME 3
#define NETDEV_CHANGE 4
#define NETDEV_CHANGEMTU 5
#define NETDEV_CHANGEUPPER 6
#define NETDEV_UP 7
#define SWITCHDEV_PORT_ATTR_SET 1
#define SWITCHDEV_FDB_DEL_TO_DEVICE 2
#define SWITCHDEV_ATTR_ID_PORT_BRIDGE_FLAGS 1
#define SWITCHDEV_ATTR_ID_PORT_PRE_BRIDGE_FLAGS 2
#define SWITCHDEV_ATTR_ID_BRIDGE_AGEING_TIME 3
#define SWITCHDEV_ATTR_ID_PORT_STP_STATE 4
#define BR_STATE_DISABLED 0
#define BR_STATE_LISTENING 1
#define BR_STATE_LEARNING 2
#define BR_STATE_FORWARDING 3
#define BR_STATE_BLOCKING 4
#define FAL_STP_DISABLED 0
#define FAL_STP_LISTENING 1
#define FAL_STP_BLOCKING 2
#define FAL_STP_LEARNING 3
#define FAL_STP_FORWARDING 4
#define FAL_MAC_RDT_TO_CPU 1
#define NSS_DP_PRIV_FLAG(x) 1U
#define IS_ERR(p) ((uintptr_t)(p) > (uintptr_t)-4096)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define SW_IS_PBMP_MEMBER(map, port) (((map) >> (port)) & 1U)
#define BIT(n) (1UL << (n))
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_BAD_VALUE; } while (0)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define netdev_dbg(...) ((void)0)
#define netdev_err(...) ((void)0)
#define dev_err(...) ((void)0)
static void sdk_log(const char *format, ...) { (void)format; }
#define SSDK_DEBUG(...) sdk_log(__VA_ARGS__)
#define SSDK_ERROR(...) sdk_log(__VA_ARGS__)

static atomic_uint checks;
static _Noreturn void fail(const char *tag) {
    fprintf(stderr, "DP_INIT %s\n", tag); exit(86);
}
#define CHECK(c,tag) do { atomic_fetch_add(&checks, 1); if (!(c)) fail(tag); } while (0)
#define WARN_ON_ONCE(c) CHECK(!(c), "cleanup-api-failure")
static pthread_mutex_t trace_lock = PTHREAD_MUTEX_INITIALIZER;
static char events[16384];
static size_t used;
static void event(const char *s) {
    pthread_mutex_lock(&trace_lock);
    size_t n = strlen(s);
    CHECK(used+n+2 < sizeof(events), "trace-capacity");
    memcpy(events+used, s, n); used += n; events[used++]=' '; events[used]=0;
    pthread_mutex_unlock(&trace_lock);
}

struct list_head { struct list_head *next, *prev; };
struct device_node { unsigned macid, mactype; bool of_phy, fixed, poll, invalid; };
struct device { struct device_node *of_node; struct device *parent; };
struct platform_device { struct device dev; };
struct resource { unsigned long start, end; };
struct mii_bus { char id[20]; };
struct net_device;
struct phy_device { struct { struct mii_bus *bus; int addr; } mdio;
    struct net_device *attached_dev; bool live; };
struct net_device { char name[IFNAMSIZ]; struct device dev; unsigned long base_addr;
    unsigned max_mtu, watchdog_timeo, priv_flags, gso_max_segs, mtu, type;
    const void *netdev_ops; struct phy_device *phydev;
    int refs, cache_refs, lookup_refs; bool listed, registered, freed, bridge; void *priv; };
struct notifier_block { int (*notifier_call)(struct notifier_block *,unsigned long,void *); int priority; };
struct netdev_notifier_info { struct net_device *dev; };
struct netdev_notifier_changeupper_info { struct netdev_notifier_info info; bool linking; };
struct switchdev_notifier_fdb_info { struct net_device *dev; unsigned char addr[6]; };
struct switchdev_attr { unsigned id; union { unsigned ageing_time; u8 stp_state; } u; };
struct switchdev_notifier_port_attr_info { struct net_device *dev; const struct switchdev_attr *attr; bool handled; };
typedef int fal_stp_state_t;
typedef struct { int action, sg_bypass, in_stp_bypass, in_vlan_fltr_bypass, l2_filter_bypass; } fal_ctrlpkt_action_t;
typedef struct { fal_ctrlpkt_action_t action; unsigned ethtype_profile_bitmap, port_map; } fal_ctrlpkt_profile_t;
typedef struct { struct { unsigned char uc[6]; } addr; unsigned fid; } fal_fdb_entry_t;

@@TYPES@@
_Static_assert(HSL_PP_EXCL_CPU == 2 && HSL_PP_BUTT == 5, "actual property enum");
_Static_assert(sizeof(((port_info_t *)0)->property)/sizeof(fal_pbmp_t) == HSL_PP_BUTT,
               "actual property array domain");
typedef struct { ssdk_chip_type chip_type; unsigned phy_id; } ssdk_init_cfg;
struct qca_phy_priv { unsigned device_id; };
typedef struct { int (*adpt_port_netdev_notify_set)(struct qca_phy_priv *,unsigned); } adpt_api_t;
struct nss_dp_data_plane_ctx { struct net_device *dev; };
struct nss_gmac_hal_platform_data { unsigned mactype, macid; unsigned long reg_len; struct net_device *netdev; };
struct nss_gmac_hal_ops { void *(*init)(struct nss_gmac_hal_platform_data *); void (*exit)(void *); };
struct nss_dp_data_plane_ops { int (*init)(struct nss_dp_data_plane_ctx *); void (*deinit)(struct nss_dp_data_plane_ctx *); };
struct nss_dp_global_ctx { struct nss_dp_dev *nss_dp[NSS_DP_MAX_PORTS];
    bool common_init_done, enable_polling_task, tx_requeue_stop;
    int rx_buf_size, overwrite_mode, page_mode, jumbo_mru; u8 slowproto_acl_bm; };
struct nss_dp_dev { struct platform_device *pdev; struct net_device *netdev; struct phy_device *phydev;
    struct mii_bus *miibus; struct nss_dp_global_ctx *ctx; struct nss_dp_data_plane_ctx *dpc;
    struct nss_gmac_hal_ops *gmac_hal_ops; struct nss_dp_data_plane_ops *data_plane_ops;
    void *gmac_hal_ctx; unsigned macid, drv_flags, vsi, phy_mdio_addr;
    unsigned forced_speed, forced_duplex; int phy_mii_type, stats_lock;
    unsigned rx_page_mode, rx_jumbo_mru;
    bool link_poll, ppe_offload_disabled, is_switch_connected;
    bool quarantined; };
static struct nss_dp_global_ctx dp_global_ctx;
static struct nss_dp_data_plane_ctx dp_global_data_plane_ctx[NSS_DP_MAX_PORTS];
static int overwrite_mode, page_mode, jumbo_mru, tx_requeue_stop=1;
static const int nss_dp_netdev_ops;
static int nss_dp_drv, init_net;
static phy_info_t phys[SW_MAX_NR_DEV], *phy_info[SW_MAX_NR_DEV];
static port_info_t props[SW_MAX_NR_DEV], *p_port_info[SW_MAX_NR_DEV];
static struct { ssdk_netdev_switch_t netdev_switch[SSDK_NETDEV_SWITCH_NUM]; } ssdk_dt_global;
static struct notifier_block ssdk_dev_notifier;
static bool ssdk_dev_notifier_owned;
static int ssdk_dev_notifier_error;

typedef pthread_mutex_t spinlock_t;
#define DEFINE_SPINLOCK(x) spinlock_t x=PTHREAD_MUTEX_INITIALIZER
static _Thread_local unsigned cache_depth, rtnl_depth;
static pthread_mutex_t rtnl_mutex=PTHREAD_MUTEX_INITIALIZER;
#ifdef CONFIG_DEBUG_NET_SMALL_RTNL
static pthread_mutex_t net_mutex=PTHREAD_MUTEX_INITIALIZER;
#endif
static _Thread_local unsigned net_depth;
static pthread_mutex_t refs_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t refs_cond=PTHREAD_COND_INITIALIZER;
static pthread_mutex_t gate_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cond=PTHREAD_COND_INITIALIZER;
static unsigned park_kind;
static bool gate_reached, gate_release, gate_blocked;
static _Thread_local struct net_device *lookup_owner;
static void blocked(const char *tag) {
    pthread_mutex_lock(&gate_mutex);
    if(park_kind && gate_reached && !gate_release && !gate_blocked) {
        event(tag);gate_blocked=true;pthread_cond_broadcast(&gate_cond);
    }
    pthread_mutex_unlock(&gate_mutex);
}
static void park(unsigned kind) {
    if(park_kind!=kind)return;
    pthread_mutex_lock(&gate_mutex);gate_reached=true;pthread_cond_broadcast(&gate_cond);
    while(!gate_release)pthread_cond_wait(&gate_cond,&gate_mutex);
    pthread_mutex_unlock(&gate_mutex);
}
static void wait_gate(bool *flag) {
    pthread_mutex_lock(&gate_mutex);
    while(!*flag)pthread_cond_wait(&gate_cond,&gate_mutex);
    pthread_mutex_unlock(&gate_mutex);
}
static void release_gate(void) {
    pthread_mutex_lock(&gate_mutex);event("release");gate_release=true;
    pthread_cond_broadcast(&gate_cond);pthread_mutex_unlock(&gate_mutex);
}
static void spin_lock_bh(spinlock_t *p) {
    CHECK(!cache_depth, "cache-recursion"); pthread_mutex_lock(p); cache_depth++;
}
static void spin_unlock_bh(spinlock_t *p) {
    CHECK(cache_depth==1, "cache-unlock"); cache_depth--; pthread_mutex_unlock(p);
}
#define spin_lock_init(p) ((void)(p))
static void rtnl_lock(void) {
    CHECK(!rtnl_depth && !cache_depth, "rtnl-recursion");
    int rc=pthread_mutex_trylock(&rtnl_mutex);
    if(rc==EBUSY) { blocked("rtnl-wait");rc=pthread_mutex_lock(&rtnl_mutex); }
    CHECK(rc==0,"rtnl-acquire");rtnl_depth++;
}
static void rtnl_unlock(void) {
    CHECK(rtnl_depth==1, "rtnl-unlock"); rtnl_depth--; pthread_mutex_unlock(&rtnl_mutex);
}
static void net_rtnl_lock(void) {
    rtnl_lock();
#ifdef CONFIG_DEBUG_NET_SMALL_RTNL
    CHECK(net_depth==0,"net-lock-recursion");pthread_mutex_lock(&net_mutex);net_depth=1;
#endif
}
static void net_rtnl_unlock(void) {
#ifdef CONFIG_DEBUG_NET_SMALL_RTNL
    CHECK(net_depth==1,"net-unlock");net_depth=0;pthread_mutex_unlock(&net_mutex);
#endif
    rtnl_unlock();
}
#define ASSERT_RTNL() CHECK(rtnl_depth==1, "rtnl-required")
static void rcu_read_lock(void) {}
static void rcu_read_unlock(void) {}
static ssize_t strscpy(char *d,const char *s,size_t n) {
    CHECK(n>0, "copy-capacity"); size_t len=strlen(s); size_t c=len<n?len:n-1;
    memcpy(d,s,c);d[c]=0;return len<n?(ssize_t)len:-E2BIG;
}

@@PUBLIC@@
@@PROTOTYPES@@
@@GLOBALS@@
#ifdef CONFIG_NET_SWITCHDEV
static struct notifier_block nss_dp_netdev_notifier={.notifier_call=nss_dp_netdev_event};
static struct notifier_block nss_dp_switchdev_notifier={.notifier_call=nss_dp_switchdev_event};
static struct notifier_block nss_dp_switchdev_notifier_nb={.notifier_call=nss_dp_switchdev_event_nb};
static struct notifier_block *nss_dp_sw_ev_nb=&nss_dp_switchdev_notifier_nb;
#endif

/* Failure switches change framework/leaf results, never replace DP or cache logic. */
static const char *scenario;
static int fail_stage, port_count=1, chip_error, register_mode, phy_route;
static bool hal_live, platform_live, notify_live, blocking_live, atomic_live;
static bool ssdk_notify_live, foreign;
static struct notifier_block *registered_n, *registered_sb, *registered_sa, *registered_ssdk;
static bool actor_requested;
#ifdef CONFIG_NET_SWITCHDEV
static bool leaves_forbidden;
#endif
static bool mapper_zero, mapper_bitmap_miss, no_phy, embedded_reader_active;
static pthread_t embedded_reader;
static int init_result;
static void *reader_thread(void *arg);
#ifdef CONFIG_NET_SWITCHDEV
static void *callback_thread(void *arg);
#endif
static unsigned allocs, frees, attached, detached, probe_errors, mapper_calls;
static struct platform_device pdevs[2];
static struct device_node nodes[2];
static struct net_device *objects[2];
static struct phy_device phy_objects[2];
static struct mii_bus bus={.id="host"};
static struct net_device foreign_dev;
static struct nss_dp_dev foreign_private;
static unsigned probe_id;
static unsigned hold_count, put_count;
#ifdef CONFIG_NET_SWITCHDEV
static pthread_mutex_t atomic_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t atomic_cond=PTHREAD_COND_INITIALIZER;
static unsigned atomic_readers;
#endif
static unsigned hardware_filters, hardware_ethtype;
struct vsi_binding { struct device_node *node; struct net_device *netdev;
    unsigned value, gets, callback_gets, assigns, clears; bool registered; };
static unsigned default_vsi[SW_MAX_NR_DEV][SW_MAX_NR_PORT];
static unsigned provider_prestate[SW_MAX_NR_DEV][SW_MAX_NR_PORT];
static struct vsi_binding vsi_table[SW_MAX_NR_DEV][SW_MAX_NR_PORT];
struct vsi_call { unsigned phase, dev, port, value, before, after, node_id;
    uintptr_t node_identity; int result; };
static struct vsi_call vsi_calls[32];
static unsigned vsi_call_count;
static _Thread_local struct net_device *retiring_netdev;
#ifdef CONFIG_NET_SWITCHDEV
static unsigned control_calls;
#endif

static void *netdev_priv(struct net_device *p) { return p->priv; }
static unsigned nss_dp_get_idx_from_macid(unsigned m) { return m-1; }
static void nss_dp_plane_init(struct nss_dp_dev *p) { (void)p; }
static void ether_setup(struct net_device *p) { (void)p; }
#define SET_NETDEV_DEV(n,d) ((n)->dev.parent=(d))
static struct net_device *alloc_netdev_mqs(size_t size,const char *name,int type,
    void (*setup)(struct net_device *),int tx,int rx) {
    (void)name;(void)type;(void)tx;(void)rx;
    CHECK(probe_id<2, "probe-index");
    struct net_device *n=calloc(1,sizeof(*n)); CHECK(n!=NULL, "host-allocation");
    n->priv=calloc(1,size);CHECK(n->priv!=NULL,"host-allocation"); n->refs=1;n->type=ARPHRD_ETHER;
    snprintf(n->name,sizeof(n->name),"eth%u",probe_id);setup(n); objects[probe_id]=n;
    allocs++;event("alloc");return n;
}
static void free_netdev(struct net_device *n) {
    CHECK(!rtnl_depth && !cache_depth, "free-context");
    CHECK(!n->listed && !n->registered && n->refs==1 && !n->freed, "free-ref-ledger");
    CHECK(!n->phydev, "free-attached-phy"); n->freed=true;frees++;event("free");
    if(retiring_netdev==n)retiring_netdev=NULL;
    /* Quarantine allocations until case end so a negative is semantic, not ASan luck. */
}
static void nss_dp_set_ethtool_ops(struct net_device *n) { (void)n; }
static void nss_dp_hal_init_soc_priv_flags(struct nss_dp_dev *p) { (void)p; }
static void nss_dp_hal_deinit_soc_priv_flags(struct nss_dp_dev *p) { (void)p; }
static const char *of_get_property(struct device_node *n,const char *key,void *len) {
    (void)n;(void)key;(void)len;return "eth";
}
static int of_property_read_u32(struct device_node *n,const char *key,unsigned *v) {
    if(!strcmp(key,"qcom,id")) { *v=n->macid;return n->invalid?-1:0; }
    if(!strcmp(key,"qcom,mactype")) { *v=n->mactype;return 0; }
    if(!strcmp(key,"qcom,phy-mdio-addr")) { *v=n->macid;return 0; }
    return -1;
}
static bool of_property_read_bool(struct device_node *n,const char *key) {
    return !strcmp(key,"qcom,link-poll") && n->poll;
}
static int of_address_to_resource(struct device_node *n,int idx,struct resource *r) {
    (void)idx;r->start=NSS_MAC_CSR_BASE_ADDR+(n->macid-1)*MAC_ENABLE_INC;r->end=r->start+0xfff;return 0;
}
static unsigned long resource_size(struct resource *r) { return r->end-r->start+1; }
static int of_get_phy_mode(struct device_node *n,int *mode) { (void)n;*mode=1;return 0; }
static int of_get_mac_address(struct device_node *n,uint8_t *addr) { (void)n;memset(addr,1,6);return 0; }
static bool is_valid_ether_addr(uint8_t *a) { return a[0]!=0; }
static void eth_hw_addr_set(struct net_device *n,uint8_t *a) { (void)n;(void)a; }
static void eth_hw_addr_random(struct net_device *n) { (void)n; }
static void *of_find_property(struct device_node *n,const char *key,void *v) {
    (void)key;(void)v;return n->of_phy?n:NULL;
}
static bool of_phy_is_fixed_link(struct device_node *n) { return n->fixed; }
static void of_phy_deregister_fixed_link(struct device_node *n) { n->fixed=false;event("fixed-put"); }
static void nss_dp_adjust_link(struct net_device *n) { (void)n; }
static struct mii_bus *nss_dp_mdio_attach(struct platform_device *p) { (void)p;return &bus; }

static void dev_hold(struct net_device *n) {
    pthread_mutex_lock(&refs_mutex);CHECK(!n->freed && n->refs>0,"hold-live");
    n->refs++;n->cache_refs++;hold_count++;pthread_mutex_unlock(&refs_mutex);
}
static void dev_put(struct net_device *n) {
    CHECK(!cache_depth,"put-under-cache");pthread_mutex_lock(&refs_mutex);
    CHECK(!n->freed && n->refs>1,"put-ledger");
    if(lookup_owner==n) { CHECK(n->lookup_refs>0,"lookup-put");n->lookup_refs--;lookup_owner=NULL;
        if(park_kind==1)event("reader-put"); }
    else { CHECK(n->cache_refs>0,"cache-put");n->cache_refs--; }
    n->refs--;put_count++;pthread_cond_broadcast(&refs_cond);pthread_mutex_unlock(&refs_mutex);
}
static struct net_device *dev_get_by_name(int *net,const char *name) {
    (void)net;pthread_mutex_lock(&refs_mutex);struct net_device *found=NULL;
    for(unsigned i=0;i<2;i++)if(objects[i] && objects[i]->listed && !strcmp(objects[i]->name,name)) {
        found=objects[i];CHECK(!found->freed && !lookup_owner,"lookup-live");
        found->refs++;found->lookup_refs++;hold_count++;lookup_owner=found;break;
    }
    pthread_mutex_unlock(&refs_mutex);return found;
}
static unsigned ssdk_miibus_index_get(unsigned dev,struct mii_bus *p) {
    (void)dev;CHECK(p==&bus,"mapper-live-bus");
    CHECK(lookup_owner && lookup_owner->lookup_refs>0 && lookup_owner->phydev &&
          lookup_owner->phydev->live,"mapper-after-put");
    mapper_calls++;if(park_kind==1)event("reader");park(1);return 0;
}
static void hsl_port_phydev_get(unsigned dev,unsigned port,struct phy_device **p) {
    (void)dev;(void)port;*p=NULL;fail("managed-fallback");
}
static bool of_device_is_compatible(struct device_node *n,const char *compat) {
    return n && !strcmp(compat,"qcom,nss-dp");
}
static struct net_device *netdev_notifier_info_to_dev(void *p) {
    return ((struct netdev_notifier_info *)p)->dev;
}
static void ssdk_cfg_default_init(ssdk_init_cfg *p) { memset(p,0,sizeof(*p)); }
static int chip_ver_get(unsigned dev,ssdk_init_cfg *p) { (void)dev;p->chip_type=CHIP_HPPE;return chip_error; }
static struct qca_phy_priv *ssdk_phy_priv_data_get(unsigned d) { (void)d;return NULL; }
static adpt_api_t *adpt_api_ptr_get(unsigned d) { (void)d;return NULL; }
static void ssdk_netdev_refresh_mac_sw_sync(struct net_device *n) { (void)n; }
static void fal_frame_max_size_set(unsigned dev,unsigned size) { (void)dev;(void)size; }

static void notify_ssdk(struct net_device *n,unsigned long event_) {
    if(ssdk_notify_live) { CHECK(registered_ssdk!=NULL,"ssdk-callback-owner");
        struct netdev_notifier_info info={n};registered_ssdk->notifier_call(registered_ssdk,event_,&info); }
}
static struct phy_device *connect_phy(struct net_device *n) {
    struct nss_dp_dev *p=netdev_priv(n);
    CHECK(ssdk_netdev_managed[0][p->macid],"mark-before-attach");
    if(fail_stage==7)return NULL;
    struct phy_device *phy=&phy_objects[p->macid-1];
    *phy=(struct phy_device){.mdio={&bus,9+3*((int)p->macid-1)},.attached_dev=n,.live=true};
    n->phydev=phy;attached++;event("phy+");return phy;
}
static struct phy_device *of_phy_get_and_connect(struct net_device *n,struct device_node *node,
    void (*adjust)(struct net_device *)) { (void)node;(void)adjust;return connect_phy(n); }
static struct phy_device *model_phy_connect(struct net_device *n,const char *id,
    void (*adjust)(struct net_device *),int mode) {
    (void)id;(void)adjust;(void)mode;struct phy_device *p=connect_phy(n);return p?p:(void *)-ENODEV;
}
static void phy_attached_info(struct phy_device *p) { CHECK(p->live,"phy-live"); }
static void phy_disconnect(struct phy_device *p) {
    struct net_device *n=p->attached_dev;
    CHECK(p->live && n && !n->listed && n->refs==1,"disconnect-after-refwait");
    p->live=false;n->phydev=NULL;p->attached_dev=NULL;detached++;event("phy-");
}
static void *gmac_init(struct nss_gmac_hal_platform_data *p) {
    CHECK(hal_live,"gmac-services");event("gmac+");return fail_stage==5?NULL:p->netdev;
}
static void gmac_exit(void *p) { CHECK(p!=NULL,"gmac-owner");event("gmac-"); }
static int plane_init(struct nss_dp_data_plane_ctx *p) {
    CHECK(rtnl_depth && p->dev,"plane-lock-owner");event("plane+");return fail_stage==6?-EIO:0;
}
static void plane_deinit(struct nss_dp_data_plane_ctx *p) { (void)p;fail("unexpected-plane-deinit"); }
static struct nss_gmac_hal_ops gmac_ops={gmac_init,gmac_exit};
static struct nss_dp_data_plane_ops plane_ops={plane_init,plane_deinit};
static struct nss_gmac_hal_ops *nss_dp_hal_get_gmac_ops(unsigned t) { (void)t;return &gmac_ops; }
static struct nss_dp_data_plane_ops *nss_dp_hal_get_data_plane_ops(void) {
    CHECK(ssdk_netdev_managed[0][((struct nss_dp_dev *)objects[probe_id]->priv)->macid],"mark-before-context");
    return &plane_ops;
}
static void edma_retire_port(struct net_device *n,unsigned port) { CHECK(port==((struct nss_dp_dev *)n->priv)->macid,"retire-identity");ASSERT_RTNL();retiring_netdev=n;event("retire"); }
static void nss_dp_plane_quarantine(struct nss_dp_dev *p) { ASSERT_RTNL();p->quarantined=true;retiring_netdev=p->netdev;event("quarantine"); }
static bool nss_dp_hal_init(void) { CHECK(ssdk_netdev_cache_live,"ready-before-H");event("H+");if(fail_stage==1)return false;hal_live=true;return true; }
static void nss_dp_hal_cleanup(void) {
    pthread_mutex_lock(&gate_mutex);
    CHECK(!gate_reached || gate_release,"callback-drain");
    pthread_mutex_unlock(&gate_mutex);
    CHECK(hal_live && !platform_live && !notify_live && !blocking_live && !atomic_live,"hal-last");
    hal_live=false;event("H-");
}
sw_error_t ppe_port_vsi_get(a_uint32_t dev,fal_port_t port,a_uint32_t *vsi) {
    CHECK(hal_live && dev<SW_MAX_NR_DEV && port>0 && port<SW_MAX_NR_PORT,"vsi-services");
    struct net_device *n=retiring_netdev?retiring_netdev:(probe_id<2?objects[probe_id]:NULL);
    CHECK(n && n->dev.parent && n->dev.parent->of_node,"vsi-node-present");
    struct device_node *node=n->dev.parent->of_node;
    CHECK(dev==0 && port==node->macid,"vsi-get-identity");
    struct vsi_binding *cell=&vsi_table[dev][port];
    if(retiring_netdev) {
        CHECK(cell->registered && cell->value!=FAL_VSI_INVALID,"vsi-through-callback");
        cell->callback_gets++;
    } else cell->gets++;
    *vsi=default_vsi[dev][port];int result=fail_stage==8?-EIO:0;
    CHECK(vsi_call_count<32,"vsi-call-capacity");
    vsi_calls[vsi_call_count++]=(struct vsi_call){retiring_netdev?2U:1U,dev,port,*vsi,
        cell->value,cell->value,node->macid,(uintptr_t)node,result};
    return result;
}
sw_error_t fal_port_vsi_set(a_uint32_t dev,fal_port_t port,a_uint32_t vsi) {
    CHECK(hal_live,"vsi-services");
    struct net_device *n=retiring_netdev?retiring_netdev:(probe_id<2?objects[probe_id]:NULL);
    CHECK(n && n->dev.parent && n->dev.parent->of_node,"vsi-node-present");
    struct device_node *node=n->dev.parent->of_node;
    CHECK(dev==0 && port==node->macid && port<SW_MAX_NR_PORT,
          retiring_netdev?"vsi-clear-identity":"vsi-assign-identity");
    struct vsi_binding *binding=&vsi_table[dev][port];
    unsigned before=binding->value;
    if(retiring_netdev) {
        CHECK(vsi==0xffff,"vsi-clear-value");
        CHECK(binding->registered,"vsi-abort-prestate");
        CHECK(binding->clears==0 && binding->node==node && binding->netdev==n,"vsi-clear-once");
        binding->value=FAL_VSI_INVALID;binding->clears++;event("vsi-");
    } else {
        CHECK(binding->gets==1,"vsi-assign-phase");
        CHECK(binding->assigns==0 && vsi==default_vsi[0][node->macid],"vsi-assign-value");
        CHECK(binding->value==vsi,"vsi-default-prestate");
        /* Record a validated same-value call, not a new allocation/lease. */
        binding->node=node;binding->netdev=n;binding->value=vsi;binding->assigns++;
        event("vsi+");
    }
    CHECK(vsi_call_count<32,"vsi-call-capacity");
    vsi_calls[vsi_call_count++]=(struct vsi_call){retiring_netdev?4U:3U,dev,port,vsi,
        before,binding->value,node->macid,(uintptr_t)node,SW_OK};
    return 0;
}

#ifdef CONFIG_NET_SWITCHDEV
static struct net_device *switchdev_notifier_info_to_dev(void *p) { return *(struct net_device **)p; }
static int notifier_from_errno(int err) { return err; }
static struct net_device *netdev_master_upper_dev_get_rcu(struct net_device *n) { return n->bridge?n:NULL; }
static bool netif_is_bridge_master(struct net_device *n) { return n->bridge; }
#define netdev_for_each_lower_dev(dev,lower,iter) for((void)(dev),(iter)=NULL,(lower)=NULL; (iter)!=NULL; (iter)=NULL)
static int fal_mgmtctrl_ctrlpkt_profile_add(unsigned d,fal_ctrlpkt_profile_t *p) { (void)d;CHECK(hal_live&&!leaves_forbidden,"callback-services");control_calls++;hardware_filters|=p->port_map;event("filter+");return 0; }
static int fal_mgmtctrl_ctrlpkt_profile_del(unsigned d,fal_ctrlpkt_profile_t *p) { (void)d;CHECK(hal_live&&!leaves_forbidden,"callback-services");control_calls++;hardware_filters&=~p->port_map;event("filter-");return 0; }
static int fal_mgmtctrl_ethtype_profile_set(unsigned d,unsigned p,unsigned e) { (void)d;(void)p;CHECK(hal_live&&!leaves_forbidden,"callback-services");control_calls++;CHECK(e!=ETH_P_NONE || !hardware_filters,"ethtype-premature-clear");hardware_ethtype=e;event(e==ETH_P_NONE?"etype-":"etype+");return 0; }
static int fal_stp_port_state_set(unsigned d,unsigned s,unsigned p,int state) { (void)d;(void)s;(void)p;(void)state;CHECK(hal_live&&!leaves_forbidden,"callback-services");control_calls++;event("stp");return 0; }
static int fal_fdb_entry_del_bymac(unsigned d,fal_fdb_entry_t *e) { (void)d;(void)e;CHECK(hal_live&&!leaves_forbidden,"callback-services");event("fdb");return 0; }
static int register_switchdev_blocking_notifier(struct notifier_block *n) {
    (void)n;CHECK(!rtnl_depth,"blocking-public-lock");event("Sb+");if(fail_stage==2)return -ENOMEM;
    rtnl_lock();CHECK(!blocking_live,"blocking-once");blocking_live=true;registered_sb=n;rtnl_unlock();return 0;
}
static int unregister_switchdev_blocking_notifier(struct notifier_block *n) {
    CHECK(!rtnl_depth && blocking_live && registered_sb==n,"blocking-owner");rtnl_lock();blocking_live=false;registered_sb=NULL;rtnl_unlock();event("Sb-");return 0;
}
static int register_switchdev_notifier(struct notifier_block *n) {
    CHECK(n!=NULL && !atomic_live,"atomic-owner");event("Sa+");if(fail_stage==3)return -ENOSPC;atomic_live=true;registered_sa=n;return 0;
}
static int unregister_switchdev_notifier(struct notifier_block *n) {
    CHECK(atomic_live && registered_sa==n && !cache_depth && !rtnl_depth,"atomic-owner");
    pthread_mutex_lock(&atomic_mutex);
    while(atomic_readers) { blocked("Sa-wait");pthread_cond_wait(&atomic_cond,&atomic_mutex); }
    atomic_live=false;registered_sa=NULL;pthread_mutex_unlock(&atomic_mutex);event("Sa-");return 0;
}
#endif
static int register_netdevice_notifier(struct notifier_block *n) {
    CHECK(!rtnl_depth,"notifier-public-lock");
    if(n==&ssdk_dev_notifier) { if(fail_stage==10)return -EIO;ssdk_notify_live=true;registered_ssdk=n;return 0; }
    event("N+");if(fail_stage==9) {
#ifdef CONFIG_NET_SWITCHDEV
        if(park_kind==3) {
            CHECK(pthread_create(&embedded_reader,NULL,callback_thread,NULL)==0,"thread-create");
            embedded_reader_active=true;wait_gate(&gate_reached);
        }
#endif
        return -EAGAIN;
    }
#ifdef CONFIG_NET_SWITCHDEV
    rtnl_lock();leaves_forbidden=true;
    struct netdev_notifier_info info={&foreign_dev};
    n->notifier_call(n,NETDEV_REGISTER,&info);
    n->notifier_call(n,NETDEV_UP,&info);
    struct netdev_notifier_changeupper_info upper={{&foreign_dev},false};
    n->notifier_call(n,NETDEV_CHANGEUPPER,&upper);
    upper.linking=true;n->notifier_call(n,NETDEV_CHANGEUPPER,&upper);
    leaves_forbidden=false;rtnl_unlock();
#endif
    notify_live=true;registered_n=n;return 0;
}
static int unregister_netdevice_notifier(struct notifier_block *n) {
    CHECK(!rtnl_depth,"notifier-public-lock");rtnl_lock();
    if(n==&ssdk_dev_notifier) { CHECK(ssdk_notify_live && registered_ssdk==n,"ssdk-notifier-owner");ssdk_notify_live=false;registered_ssdk=NULL; }
    else { CHECK(notify_live && registered_n==n,"netdev-notifier-owner");notify_live=false;registered_n=NULL;event("N-"); }
    rtnl_unlock();return 0;
}

static void unlist_and_wait(struct net_device *n) {
    CHECK(!rtnl_depth,"unregister-public-lock");net_rtnl_lock();
    pthread_mutex_lock(&refs_mutex);
    CHECK(n->listed,"unregister-once");n->listed=false;n->registered=false;
    pthread_mutex_unlock(&refs_mutex);
#ifdef CONFIG_NET_SWITCHDEV
    if(n->bridge) {
        CHECK(notify_live && blocking_live && atomic_live,"callbacks-through-P");
        struct netdev_notifier_changeupper_info info={{n},false};
        CHECK(registered_n && registered_sa,"callbacks-through-P");
        registered_n->notifier_call(registered_n,NETDEV_CHANGEUPPER,&info);
        struct switchdev_notifier_fdb_info fdb={.dev=n};
        registered_sa->notifier_call(registered_sa,SWITCHDEV_FDB_DEL_TO_DEVICE,&fdb);
    }
#endif
    notify_ssdk(n,NETDEV_UNREGISTER);event("unlist");net_rtnl_unlock();
    CHECK(!net_depth && !rtnl_depth,"refwait-outside-net-rtnl");
    pthread_mutex_lock(&refs_mutex);
    while(n->refs!=1) { blocked("wait");pthread_cond_wait(&refs_cond,&refs_mutex); }
    pthread_mutex_unlock(&refs_mutex);event("refwait");
}
static int register_netdev(struct net_device *n) {
    CHECK(!rtnl_depth,"register-public-lock");event("register");
    struct nss_dp_dev *attempt_priv=netdev_priv(n);
    CHECK(vsi_table[0][attempt_priv->macid].gets==1 &&
          vsi_table[0][attempt_priv->macid].assigns==1,"vsi-required-assign-phase");
    if(register_mode==1) { CHECK(ssdk_ifname_to_port(0,n->name)==0,"prelist-invisible");return -EIO; }
    net_rtnl_lock();pthread_mutex_lock(&refs_mutex);n->listed=true;pthread_mutex_unlock(&refs_mutex);
    notify_ssdk(n,NETDEV_REGISTER);net_rtnl_unlock();
    if(register_mode==2) {
        if(park_kind==1) {
            CHECK(pthread_create(&embedded_reader,NULL,reader_thread,NULL)==0,"thread-create");
            embedded_reader_active=true;wait_gate(&gate_reached);
        }
        unlist_and_wait(n);return -EACCES;
    }
    n->registered=true;
    struct nss_dp_dev *registered_priv=netdev_priv(n);
    CHECK(vsi_table[0][registered_priv->macid].assigns==1,"vsi-register-assignment");
    vsi_table[0][registered_priv->macid].registered=true;
#ifdef CONFIG_NET_SWITCHDEV
    if(actor_requested) {
        CHECK(notify_live && registered_n,"published-without-N");
        struct nss_dp_dev *priv=netdev_priv(n);
        CHECK(!dp_global_ctx.common_init_done && !dp_global_ctx.nss_dp[priv->macid-1],"publication-before-commit");
        rtnl_lock();n->bridge=true;event("actor");
        struct netdev_notifier_changeupper_info upper={{n},true};
        unsigned before=control_calls;
        registered_n->notifier_call(registered_n,NETDEV_CHANGEUPPER,&upper);
        CHECK(control_calls==before,"linking-no-sideeffect");
        struct switchdev_attr attr={.id=SWITCHDEV_ATTR_ID_PORT_STP_STATE,.u.stp_state=BR_STATE_DISABLED};
        struct switchdev_notifier_port_attr_info info={n,&attr,false};
        CHECK(registered_sb!=NULL,"published-without-S");
        registered_sb->notifier_call(registered_sb,SWITCHDEV_PORT_ATTR_SET,&info);
        CHECK(info.handled && (dp_global_ctx.slowproto_acl_bm&(1U<<priv->macid)),"actual-actor-stp");
        rtnl_unlock();
    }
#endif
    return 0;
}
static void unregister_netdev(struct net_device *n) { unlist_and_wait(n); }
static int platform_driver_register(int *driver) {
    (void)driver;CHECK(hal_live && !platform_live,"platform-owner");event("P+");
    if(fail_stage==4)return -EBUSY;
    for(probe_id=0;probe_id<(unsigned)port_count;probe_id++) {
        int rc=nss_dp_probe(&pdevs[probe_id]);if(rc)probe_errors++;
        if(actor_requested && !rc) {
            CHECK((dp_global_ctx.slowproto_acl_bm&(1U<<nodes[probe_id].macid))!=0,
                  "probe-clobbered-accepted-bit");
            CHECK(dp_global_ctx.slowproto_acl_bm==hardware_filters,"accepted-filter-ledger");
        }
    }
    if(fail_stage==11) {
        event("core-comp");for(int i=0;i<port_count;i++)
            if(objects[i] && objects[i]->registered)nss_dp_remove(&pdevs[i]);
        return -ERANGE;
    }
    platform_live=true;return 0;
}
static void platform_driver_unregister(int *driver) {
    (void)driver;CHECK(platform_live && hal_live,"platform-owner");event("P-");
    for(int i=0;i<port_count;i++) if(objects[i] && objects[i]->registered)nss_dp_remove(&pdevs[i]);
    platform_live=false;
}

/* Existing probe uses uint8_t phy_id with char APIs. Keep real leaf signatures. */
#define phy_connect(n,id,cb,mode) model_phy_connect(n,(const char *)(id),cb,mode)
#undef snprintf
#define snprintf(buf,n,...) snprintf((char *)(buf),n,__VA_ARGS__)
@@FUNCTIONS@@

static void *reader_thread(void *arg) {
    (void)arg;unsigned port=ssdk_ifname_to_port(0,"eth0");
    CHECK(port==(mapper_zero?0U:1U),"g3-result");
    CHECK(lookup_owner==NULL,"g3-put-ledger");return NULL;
}
static void *exit_thread(void *arg) { (void)arg;nss_dp_exit();return NULL; }
static void *init_thread(void *arg) { (void)arg;init_result=nss_dp_init();return NULL; }
#ifdef CONFIG_NET_SWITCHDEV
static void *callback_thread(void *arg) {
    (void)arg;
    if(park_kind==2) {
        pthread_mutex_lock(&atomic_mutex);CHECK(atomic_live,"atomic-callback-live");atomic_readers++;pthread_mutex_unlock(&atomic_mutex);
        struct switchdev_notifier_fdb_info fdb={.dev=&foreign_dev};
        registered_sa->notifier_call(registered_sa,SWITCHDEV_FDB_DEL_TO_DEVICE,&fdb);
        event("callback");park(2);event("callback-exit");
        pthread_mutex_lock(&atomic_mutex);atomic_readers--;pthread_cond_broadcast(&atomic_cond);pthread_mutex_unlock(&atomic_mutex);
    } else {
        rtnl_lock();
        struct switchdev_attr attr={.id=SWITCHDEV_ATTR_ID_PORT_BRIDGE_FLAGS};
        struct switchdev_notifier_port_attr_info info={&foreign_dev,&attr,false};
        registered_sb->notifier_call(registered_sb,SWITCHDEV_PORT_ATTR_SET,&info);
        event("callback");park(3);event("callback-exit");rtnl_unlock();
    }
    return NULL;
}
#endif

static void setup(void) {
    foreign_private.netdev=&foreign_dev;foreign_private.ctx=&dp_global_ctx;
    foreign_dev.priv=&foreign_private;
    for(unsigned i=0;i<SW_MAX_NR_DEV;i++) {
        phy_info[i]=&phys[i];p_port_info[i]=&props[i];
        props[i].property[HSL_PP_EXCL_CPU]=0x7e;
    }
    port_bmp[0]=0x7e;
    for(unsigned p=1;p<=SSDK_PHYSICAL_PORT6;p++)phys[0].phy_address[p]=TO_PHY_ADDR_E((9+3*(p-1)),0);
    if(mapper_zero)phys[0].phy_address[1]=TO_PHY_ADDR_E(31,0);
    if(mapper_bitmap_miss)port_bmp[0]&=~BIT(1);
    for(unsigned dev=0;dev<SW_MAX_NR_DEV;dev++)for(unsigned port=0;port<SW_MAX_NR_PORT;port++) {
        default_vsi[dev][port]=(dev==0 && port>0 && port<=SSDK_PHYSICAL_PORT6)?
            default_pport_vsi[port-1]:(24+((dev+port)%8));
        vsi_table[dev][port].value=default_vsi[dev][port];
        provider_prestate[dev][port]=default_vsi[dev][port];
    }
    SSDK_CURRENT_CHIP_TYPE[0]=CHIP_HPPE;g_chip_ver[0].chip_type=CHIP_HPPE;
    dev_table[0].nr_ports=7;dev_table[0].cpu_port_nr=0;
    for(unsigned i=0;i<2;i++) {
        nodes[i]=(struct device_node){.macid=i+1,.of_phy=!phy_route&&!no_phy,.poll=phy_route};
        pdevs[i].dev.of_node=&nodes[i];
    }
    for(unsigned i=0;i<SSDK_NETDEV_SWITCH_NUM;i++)ssdk_dt_global.netdev_switch[i].switch_netdev_port=255;
    ssdk_netdev_notifier_register();
}
static void finish(void) {
    CHECK(!nss_dp_hal_owned,"implementation-hal-owner");
    CHECK(!nss_dp_platform_owned,"implementation-platform-owner");
#ifdef CONFIG_NET_SWITCHDEV
    CHECK(!nss_dp_netdev_owned,"implementation-netdev-owner");
    CHECK(!switchdev_atomic_owned,"implementation-atomic-owner");
    CHECK(!switchdev_blocking_owned,"implementation-blocking-owner");
#endif
    CHECK(!dp_global_ctx.common_init_done,"implementation-common-init");
    for(unsigned i=0;i<NSS_DP_MAX_PORTS;i++)CHECK(!dp_global_ctx.nss_dp[i],"implementation-port-slot");
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)for(unsigned p=0;p<SW_MAX_NR_PORT;p++) {
        struct vsi_binding *cell=&vsi_table[d][p];
        CHECK(default_vsi[d][p]==provider_prestate[d][p],"vsi-software-map");
        if(cell->registered) {
            CHECK(cell->assigns==1 && cell->clears==1 && cell->value==FAL_VSI_INVALID,
                  "vsi-success-remove");
        } else CHECK(cell->clears==0 && cell->value==provider_prestate[d][p],"vsi-provider-baseline");
        bool attempted=d==0 && p>0 && p<=2 && objects[p-1]!=NULL;
        unsigned expected_get=attempted && !foreign && fail_stage!=5 && fail_stage!=6 && fail_stage!=7;
        unsigned expected_set=expected_get && fail_stage!=8;
        CHECK(cell->gets==expected_get && cell->assigns==expected_set,"vsi-exact-call-count");
        CHECK(cell->callback_gets==(unsigned)(actor_requested && cell->registered),"vsi-callback-get-count");
        if(cell->assigns) {
            CHECK(d==0 && p>0 && p<=2 && cell->assigns==1 &&
                cell->node==&nodes[p-1] && cell->netdev==objects[p-1],"vsi-node-call-ledger");
        }
    }
    for(unsigned i=0;i<vsi_call_count;i++) {
        struct vsi_call *call=&vsi_calls[i];
        CHECK(call->dev==0 && call->port>0 && call->port<=2 &&
              call->node_id==nodes[call->port-1].macid &&
              call->node_identity==(uintptr_t)&nodes[call->port-1],"vsi-call-identity");
        CHECK(call->phase>=1 && call->phase<=4,"vsi-call-phase");
        if(call->phase==3)CHECK(call->result==0 && call->before==call->after &&
            call->after==provider_prestate[call->dev][call->port],"vsi-same-value-write");
        if(call->phase==4)CHECK(call->result==0 && call->value==FAL_VSI_INVALID &&
            call->after==FAL_VSI_INVALID,"vsi-success-remove");
    }
    CHECK(!hal_live && !platform_live && !notify_live && !blocking_live && !atomic_live,"global-ledger");
    CHECK(allocs==frees && attached==detached,"local-ledger");
    CHECK(!hardware_filters && !hardware_ethtype,"filter-retirement-ledger");
    for(unsigned i=0;i<NSS_DP_MAX_PORTS;i++)CHECK(dp_global_data_plane_ctx[i].dev==(foreign?&foreign_dev:NULL),"foreign-context-preserved");
    for(unsigned i=0;i<2;i++)if(objects[i]) { CHECK(objects[i]->freed && objects[i]->refs==1,"object-ledger");free(objects[i]->priv);free(objects[i]); }
    ssdk_netdev_notifier_unregister();
    CHECK(!registered_n && !registered_sb && !registered_sa && !registered_ssdk,"callback-ledger");
    CHECK(hold_count==put_count,"final-ref-ledger");
    fputs(events,stdout);printf("\nPASS DP_INIT alloc=%u free=%u attach=%u detach=%u errors=%u holds=%u puts=%u maps=%u\n",
        allocs,frees,attached,detached,probe_errors,hold_count,put_count,mapper_calls);
}
int main(int argc,char **argv) {
    CHECK(argc==2,"case-argument");scenario=argv[1];
    if(!strcmp(scenario,"zero"))port_count=0;
    else if(!strcmp(scenario,"two"))port_count=2;
    else if(!strcmp(scenario,"mdio"))phy_route=1;
    else if(!strcmp(scenario,"mark-false"))foreign=true;
    else if(!strcmp(scenario,"ready-false"))fail_stage=10;
    else if(!strcmp(scenario,"actor"))actor_requested=true;
    else if(!strcmp(scenario,"two-actor")) { port_count=2;actor_requested=true; }
    else if(!strcmp(scenario,"late-P")) { actor_requested=true;fail_stage=11; }
    else if(!strcmp(scenario,"prelist"))register_mode=1;
    else if(!strcmp(scenario,"veto"))register_mode=2;
    else if(!strcmp(scenario,"veto-reader")) { register_mode=2;park_kind=1; }
    else if(!strcmp(scenario,"g3-reader"))park_kind=1;
    else if(!strcmp(scenario,"g3-zero"))mapper_zero=true;
    else if(!strcmp(scenario,"g3-unmapped"))mapper_bitmap_miss=true;
    else if(!strcmp(scenario,"g3-no-phy"))no_phy=true;
    else if(!strcmp(scenario,"g3-missing"))port_count=0;
    else if(!strcmp(scenario,"atomic-drain")) { port_count=0;park_kind=2; }
    else if(!strcmp(scenario,"blocking-drain")) { port_count=0;park_kind=3; }
    else if(!strcmp(scenario,"blocking-fail-N")) { port_count=0;park_kind=3;fail_stage=9; }
    else if(!strcmp(scenario,"property-domain"))port_count=0;
    else if(!strncmp(scenario,"fail-",5))fail_stage=atoi(scenario+5);
    else CHECK(!strcmp(scenario,"normal"),"known-case");
    setup();
    if(!strcmp(scenario,"property-domain")) {
        for(unsigned p=0;p<HSL_PP_BUTT;p++)props[0].property[p]=1U<<(p+1);
        for(unsigned p=0;p<HSL_PP_BUTT;p++)for(unsigned port=0;port<8;port++)
            CHECK(hsl_port_prop_check(0,port,(hsl_port_prop_t)p)==(port==p+1),"property-domain");
        CHECK(!hsl_port_prop_check(0,1,HSL_PP_BUTT),"property-domain-upper");
        CHECK(!hsl_port_prop_check(SW_MAX_NR_DEV,1,HSL_PP_EXCL_CPU),"property-device-upper");
    }
    if(foreign) {
        dev_table[0].cpu_port_nr=1;
        for(unsigned i=0;i<NSS_DP_MAX_PORTS;i++)dp_global_data_plane_ctx[i].dev=&foreign_dev;
    }
    int rc;
    if((register_mode==2 && park_kind==1) || !strcmp(scenario,"blocking-fail-N")) {
        pthread_t worker;CHECK(pthread_create(&worker,NULL,init_thread,NULL)==0,"thread-create");
        wait_gate(&gate_blocked);
        if(park_kind==1)CHECK(objects[0]->phydev && objects[0]->phydev->live && !objects[0]->freed,"refwait-keeps-phy");
        else CHECK(hal_live,"wait-keeps-H");
        release_gate();CHECK(pthread_join(worker,NULL)==0,"thread-join");
        CHECK(embedded_reader_active && pthread_join(embedded_reader,NULL)==0,"thread-join");rc=init_result;
    } else rc=nss_dp_init();
    if(fail_stage==10)CHECK(rc==-ENODEV,"ready-before-acquire");
    else if(fail_stage==1)CHECK(rc==-EFAULT,"hal-error");
    else if(fail_stage==2)CHECK(rc==-ENOMEM,"first-error");
    else if(fail_stage==3)CHECK(rc==-ENOSPC,"first-error");
    else if(fail_stage==4)CHECK(rc==-EBUSY,"first-error");
    else if(fail_stage==9)CHECK(rc==-EAGAIN,"first-error");
    else if(fail_stage==11)CHECK(rc==-ERANGE,"first-error");
    else {
        CHECK(rc==0 && dp_global_ctx.common_init_done,"platform-not-probe-result");
        if(park_kind && !embedded_reader_active) {
            pthread_t reader,remover;
            if(park_kind==1)CHECK(pthread_create(&reader,NULL,reader_thread,NULL)==0,"thread-create");
#ifdef CONFIG_NET_SWITCHDEV
            else CHECK(pthread_create(&reader,NULL,callback_thread,NULL)==0,"thread-create");
#else
            else fail("switchdev-profile");
#endif
            wait_gate(&gate_reached);CHECK(pthread_create(&remover,NULL,exit_thread,NULL)==0,"thread-create");
            wait_gate(&gate_blocked);CHECK(hal_live,"wait-keeps-H");
            if(park_kind==1)CHECK(objects[0]->phydev && objects[0]->phydev->live,"refwait-keeps-phy");
            release_gate();CHECK(pthread_join(reader,NULL)==0 && pthread_join(remover,NULL)==0,"thread-join");
        } else {
            if(!strcmp(scenario,"g3-zero"))CHECK(ssdk_ifname_to_port(0,"eth0")==0,"g3-result");
            if(!strcmp(scenario,"g3-unmapped"))CHECK(ssdk_ifname_to_port(0,"eth0")==0,"g3-result");
            if(!strcmp(scenario,"g3-no-phy"))CHECK(ssdk_ifname_to_port(0,"eth0")==0,"g3-result");
            if(!strcmp(scenario,"g3-missing"))CHECK(ssdk_ifname_to_port(0,"eth0")==0,"g3-result");
            nss_dp_exit();
        }
    }
    if(foreign)CHECK(probe_errors==1 && allocs==1 && attached==0,"mark-failure-local-only");
    finish();return 0;
}
