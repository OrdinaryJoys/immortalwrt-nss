/* Native allocation/value model, not kernel ABI, PHY or DSA child serialization. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
typedef unsigned long a_ulong_t;
typedef uint32_t u32;
typedef int a_bool_t;
typedef int sw_error_t;
typedef uint32_t fal_pbmp_t;
typedef uint32_t fal_port_t;
typedef int hsl_init_mode;
#define A_TRUE 1
#define A_FALSE 0
#define SW_OK 0
#define SW_BAD_VALUE (-2)
#define SW_NOT_FOUND (-12)
#define SW_NOT_INITIALIZED (-21)
#define IFNAMSIZ 16
#define PAGE_SIZE 4096
#define ARPHRD_ETHER 1
#define IFF_802_1Q_VLAN 1U
#define SSDK_MII_DEFAULT_BUS_ID 0
#define NOTIFY_DONE 0
#define NETDEV_REGISTER 1
#define NETDEV_UNREGISTER 2
#define NETDEV_CHANGENAME 3
#define NETDEV_CHANGE 4
#define NETDEV_CHANGEMTU 5
#define MP_GEPHY 5
#define IN_NETLINK 1
#define IN_MISC 1
#define IS_ENABLED(x) (x)
#define EXPORT_SYMBOL(x) static const char export_##x[] = #x
#define SW_IS_PBMP_MEMBER(map, port) (((map) >> (port)) & 1U)
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_BAD_VALUE; } while (0)
#define SSDK_DEBUG(...) do {} while (0)
#define SW_MACSTR "%02x:%02x:%02x:%02x:%02x:%02x"
#define SW_MAC2STR(x) (x)[0], (x)[1], (x)[2], (x)[3], (x)[4], (x)[5]

static unsigned checks;
static void fail(const char *tag)
{
    fprintf(stderr, "SSDK_CACHE %s\n", tag);
    exit(86);
}
#define CHECK(c, tag) do { checks++; if (!(c)) fail(tag); } while (0)

struct device_node { bool native_dp; };
struct device { struct device *parent; struct device_node *of_node; };
struct device_attribute { int unused; };
struct dsa_switch;
struct dsa_switch_ops {
    int (*suspend)(struct dsa_switch *);
    int (*resume)(struct dsa_switch *);
};
struct dsa_switch { const struct dsa_switch_ops *ops; };
struct dsa_port { struct dsa_switch *ds; };
struct phy_device;
struct net_device {
    char name[IFNAMSIZ];
    unsigned long base_addr;
    struct device dev;
    struct phy_device *phydev;
    struct dsa_port *dsa_ptr;
    unsigned type, mtu, priv_flags;
    int refs, holds, puts;
    bool dead;
};
struct phy_device { struct net_device *attached_dev; unsigned port; };
struct notifier_block {
    int (*notifier_call)(struct notifier_block *, unsigned long, void *);
    int priority;
};
struct list_head { struct list_head *next, *prev; };
typedef struct {
    struct { unsigned id; } port;
    unsigned fid;
    struct { unsigned char uc[6]; } addr;
} fal_fdb_entry_t;
struct qca_phy_priv {
    unsigned device_id;
    unsigned fdb_sw_sync_port_map;
    struct list_head sw_fdb_tbl;
};
typedef struct {
    int (*adpt_port_netdev_notify_set)(struct qca_phy_priv *, unsigned);
} adpt_api_t;

/* Actual type/constant text is inserted by the runner, not handwritten layout. */
@@ACTUAL_TYPES@@
typedef struct {
    ssdk_chip_type chip_type;
    unsigned phy_id;
    ssdk_port_cfg port_cfg;
    hsl_init_mode cpu_mode;
} ssdk_init_cfg;

typedef pthread_mutex_t spinlock_t;
#define DEFINE_SPINLOCK(x) spinlock_t x = PTHREAD_MUTEX_INITIALIZER
static _Thread_local int cache_depth;
static int fdb_bh, mdio_depth;
static void spin_lock_bh(spinlock_t *lock)
{
    CHECK(cache_depth == 0, "CACHE_RECURSION");
    CHECK(pthread_mutex_lock(lock) == 0, "CACHE_LOCK");
    cache_depth++;
}
static void spin_unlock_bh(spinlock_t *lock)
{
    CHECK(cache_depth == 1, "CACHE_UNLOCK");
    cache_depth--;
    CHECK(pthread_mutex_unlock(lock) == 0, "CACHE_UNLOCK");
}
struct mii_bus { int mdio_lock; };
static void mutex_lock(int *lock)
{
    (void)lock;
    CHECK(!cache_depth && !fdb_bh && !mdio_depth, "SLEEP_LOCK_CONTEXT");
    mdio_depth++;
}
static void mutex_unlock(int *lock)
{
    (void)lock;
    CHECK(mdio_depth == 1, "MDIO_UNLOCK");
    mdio_depth--;
}
static ssize_t strscpy(char *dst, const char *src, size_t n)
{
    size_t len = strlen(src);
    CHECK(n > 0, "COPY_BOUNDS");
    memcpy(dst, src, len < n ? len : n - 1);
    dst[len < n ? len : n - 1] = 0;
    return len < n ? (ssize_t)len : -E2BIG;
}

static phy_info_t phys[SW_MAX_NR_DEV];
static phy_info_t *phy_info[SW_MAX_NR_DEV];
static port_info_t props[SW_MAX_NR_DEV];
static port_info_t *p_port_info[SW_MAX_NR_DEV];
static struct { ssdk_netdev_switch_t netdev_switch[SSDK_NETDEV_SWITCH_NUM]; } ssdk_dt_global;
static struct notifier_block ssdk_dev_notifier;
static bool ssdk_dev_notifier_owned;
static int ssdk_dev_notifier_error;
static struct net_device a, b, c;
static struct device_node native_node = {true};
static struct device native_parent = {.of_node = &native_node};
static struct phy_device legacy_phy;
static struct net_device *lookup;
static struct qca_phy_priv priv;
static adpt_api_t adpt;
static int init_net;
static int hw_forbidden, legacy_forbidden, legacy_calls, chip_calls, mp_calls;
static int chip_error, register_error, replay_fail_index = -1;
static int register_calls, unregister_calls, notifier_present, logged_errno, error_logs;
static struct net_device *replay[3];
static unsigned replay_count;
static int suspend_calls, resume_calls, notify_calls, freed_fdb;
static bool no_bus, notify_retire;
static char notified_name[IFNAMSIZ];
static unsigned char notified_mac[6];
static struct mii_bus bus;
static bool fal_error;

@@ACTUAL_PROTOTYPES@@
static bool (* const public_ready_consumer)(void) = ssdk_netdev_cache_ready;
_Static_assert(__builtin_types_compatible_p(__typeof__(&ssdk_netdev_cache_ready), bool (*)(void)),
               "installed ready consumer signature");
static bool (* const public_mark_consumer)(a_uint32_t, a_uint32_t) = ssdk_netdev_cache_mark_native_port;
_Static_assert(__builtin_types_compatible_p(__typeof__(&ssdk_netdev_cache_mark_native_port),
               bool (*)(a_uint32_t, a_uint32_t)), "installed mark consumer signature");
@@ACTUAL_GLOBALS@@

static int cells(struct net_device *dev)
{
    int count = 0;
    for (unsigned d = 0; d < SW_MAX_NR_DEV; d++)
        for (unsigned p = 0; p < SW_MAX_NR_PORT; p++)
            count += phy_info[d] && phy_info[d]->netdev[p] == dev;
    for (unsigned p = 0; p < SSDK_NETDEV_SWITCH_NUM; p++)
        count += ssdk_dt_global.netdev_switch[p].dev == dev;
    return count;
}
static void dev_hold(struct net_device *dev)
{
    CHECK(cache_depth == 1, "READ_PIN_AFTER_UNLOCK");
    CHECK(dev && !dev->dead && dev->refs > 0, "HOLD_AFTER_FREE");
    dev->refs++;
    dev->holds++;
}
static void dev_put(struct net_device *dev)
{
    CHECK(!cache_depth, "PUT_UNDER_CACHE_LOCK");
    CHECK(dev && !dev->dead && dev->refs > 1, "REF_UNDERFLOW");
    dev->refs--;
    dev->puts++;
    CHECK(dev->refs >= cells(dev) + 1, "PUT_BEFORE_UNPUBLISH");
}
static struct net_device *dev_get_by_name(int *net, const char *name)
{
    (void)net;
    CHECK(!cache_depth, "NAME_LOOKUP_CONTEXT");
    if (!lookup || strcmp(lookup->name, name)) return NULL;
    CHECK(!lookup->dead, "LOOKUP_AFTER_FREE");
    lookup->refs++;
    lookup->holds++;
    return lookup;
}
static unsigned qca_ssdk_phydev_to_port(unsigned dev, struct phy_device *phy)
{
    (void)dev;
    CHECK(phy && phy->attached_dev && phy->attached_dev->refs >= 2, "PHY_MAP_AFTER_PUT");
    return phy->port;
}
static void hsl_port_phydev_get(unsigned dev, unsigned port, struct phy_device **phy)
{
    CHECK(!legacy_forbidden, "LEGACY_AFTER_RETIRE");
    CHECK(!cache_depth && dev < SW_MAX_NR_DEV && port < SW_MAX_NR_PORT, "LEGACY_BOUNDS_CONTEXT");
    legacy_calls++;
    *phy = &legacy_phy;
}
static bool of_device_is_compatible(struct device_node *node, const char *name)
{
    return node && node->native_dp && !strcmp(name, "qcom,nss-dp");
}
static struct net_device *netdev_notifier_info_to_dev(void *ptr) { return ptr; }
static void ssdk_cfg_default_init(ssdk_init_cfg *cfg) { memset(cfg, 0, sizeof(*cfg)); }
static int chip_ver_get(unsigned id, ssdk_init_cfg *cfg)
{
    (void)id;
    CHECK(!hw_forbidden, "HARDWARE_ON_RETIRE");
    chip_calls++;
    cfg->chip_type = CHIP_DESS;
    return chip_error;
}
static struct qca_phy_priv *ssdk_phy_priv_data_get(unsigned id)
{
    (void)id;
    CHECK(!hw_forbidden, "HARDWARE_ON_RETIRE");
    mp_calls++;
    return &priv;
}
static adpt_api_t *adpt_api_ptr_get(unsigned id)
{
    (void)id;
    CHECK(!hw_forbidden, "HARDWARE_ON_RETIRE");
    mp_calls++;
    return &adpt;
}
static void ssdk_netdev_refresh_mac_sw_sync(struct net_device *dev) { (void)dev; }
static void ssdk_dsa_refresh_link_polling(struct net_device *dev) { (void)dev; }
static void fal_frame_max_size_set(unsigned id, unsigned size) { (void)id; (void)size; }
static void error_log(const char *fmt, ...)
{
    error_logs++;
    if (strstr(fmt, "optional netdev")) logged_errno = ssdk_dev_notifier_error;
}
#define SSDK_ERROR(...) error_log(__VA_ARGS__)
static int register_netdevice_notifier(struct notifier_block *nb)
{
    register_calls++;
    CHECK(nb->priority == 1, "NOTIFIER_ACQUISITION_LEDGER");
    if (notifier_present) return -EEXIST;
    if (register_error) return register_error;
    notifier_present = 1;
    for (unsigned i = 0; i < replay_count; i++) {
        CHECK(nb->notifier_call(nb, NETDEV_REGISTER, replay[i]) == NOTIFY_DONE, "STOCK_CALLBACK_RESULT");
        CHECK(!ssdk_netdev_cache_ready(), "REPLAY_EARLY_LIVE");
        if ((int)i == replay_fail_index) {
            /* Explicit framework fault injection; stock callback did not fail. */
            for (unsigned j = i; j > 0; j--)
                nb->notifier_call(nb, NETDEV_UNREGISTER, replay[j - 1]);
            notifier_present = 0;
            return -EIO;
        }
    }
    return 0;
}
static int unregister_netdevice_notifier(struct notifier_block *nb)
{
    CHECK(notifier_present && ssdk_dev_notifier_owned, "NOTIFIER_ACQUISITION_LEDGER");
    unregister_calls++;
    for (unsigned i = 0; i < replay_count; i++)
        nb->notifier_call(nb, NETDEV_UNREGISTER, replay[i]);
    notifier_present = 0;
    return 0;
}
static struct mii_bus *ssdk_miibus_get(unsigned id, unsigned index)
{
    (void)id; (void)index;
    CHECK(!cache_depth, "HW_UNDER_CACHE_LOCK");
    return no_bus ? NULL : &bus;
}
static int netdev_uses_dsa(struct net_device *dev)
{
    CHECK(!cache_depth && !dev->dead && dev->refs >= 2, "DSA_ALLOCATION_PIN");
    return dev->dsa_ptr != NULL;
}
static int suspend_fn(struct dsa_switch *ds)
{
    CHECK(ds && a.refs >= 2 && !cache_depth && !mdio_depth, "DSA_CALLBACK_CONTEXT");
    suspend_calls++;
    return 0;
}
static int resume_fn(struct dsa_switch *ds)
{
    CHECK(ds && a.refs >= 2 && !cache_depth && !mdio_depth, "DSA_CALLBACK_CONTEXT");
    resume_calls++;
    return 0;
}
static void fal_portvlan_member_get(unsigned id, unsigned port, fal_pbmp_t *bmp)
{
    (void)id; (void)port;
    CHECK(!cache_depth, "HW_UNDER_CACHE_LOCK");
    CHECK((uintptr_t)bmp % _Alignof(fal_pbmp_t) == 0, "FAL_OUTPUT_ALIGNMENT");
    if (!fal_error) *bmp = 0x106;
}
static void fal_port_default_cvid_get(unsigned id, unsigned port, unsigned *vid)
{
    (void)id; (void)port;
    CHECK(!cache_depth, "HW_UNDER_CACHE_LOCK");
    *vid = 42;
}
static void fal_header_type_get(unsigned id, a_bool_t *enable, unsigned *tag)
{
    (void)id;
    CHECK(!cache_depth, "HW_UNDER_CACHE_LOCK");
    *enable = 1; *tag = 0x88a8;
}
#define for_each_set_bit(bit, addr, size) for ((bit) = 0; (bit) < (size); (bit)++) if ((*(addr)) & (1UL << (bit)))
#define list_entry(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_for_each_entry_safe(pos, nextpos, head, member) \
    for ((pos) = list_entry((head)->next, __typeof__(*(pos)), member), \
         (nextpos) = list_entry((pos)->member.next, __typeof__(*(pos)), member); \
         &(pos)->member != (head); \
         (pos) = (nextpos), (nextpos) = list_entry((nextpos)->member.next, __typeof__(*(nextpos)), member))
static void list_del(struct list_head *node)
{
    node->prev->next = node->next; node->next->prev = node->prev;
}
static void kfree(void *ptr) { freed_fdb++; free(ptr); }
static int ssdk_genl_notify_mac_info(char cmd, char *name, unsigned char *addr)
{
    CHECK(fdb_bh && !cache_depth, "FDB_NOTIFY_CONTEXT");
    CHECK(cmd == SSDK_COMMAND_NEW_MAC || cmd == SSDK_COMMAND_EXPIRE_MAC, "FDB_COMMAND");
    if (notify_retire) {
        CHECK(name != a.name, "BORROWED_NAME");
        ssdk_netdev_cache_unregister(&a);
        memset(a.name, 'z', IFNAMSIZ - 1); a.name[IFNAMSIZ - 1] = 0;
    }
    strscpy(notified_name, name, sizeof(notified_name));
    memcpy(notified_mac, addr, 6);
    notify_calls++;
    return 0;
}

@@ACTUAL_FUNCTIONS@@

static unsigned long port_base(unsigned p)
{
#ifdef MP
    return MP_GMAC_BASE_ADDR + (p - 1) * MAC_CONFIGURATION_INC;
#elif defined(APPE)
    return NSS_XGMAC_CSR_BASE_ADDR + (p - 1) * MAC_TX_CONFIGURATION_INC;
#else
    return p < 5 ? NSS_MAC_CSR_BASE_ADDR + (p - 1) * MAC_ENABLE_INC :
        NSS_XGMAC_CSR_BASE_ADDR + (p - 5) * MAC_TX_CONFIGURATION_INC;
#endif
}
static void initdev(struct net_device *dev, const char *name, unsigned port)
{
    memset(dev, 0, sizeof(*dev));
    strscpy(dev->name, name, sizeof(dev->name));
    dev->refs = 1; dev->type = ARPHRD_ETHER; dev->mtu = 1500;
    dev->base_addr = port_base(port); dev->dev.parent = &native_parent;
}
static void setup(void)
{
    for (unsigned d = 0; d < SW_MAX_NR_DEV; d++) {
        phy_info[d] = &phys[d]; p_port_info[d] = &props[d];
        props[d].property[HSL_PP_EXCL_CPU] = 0xfffe;
    }
    for (unsigned i = 0; i < SSDK_NETDEV_SWITCH_NUM; i++) {
        ssdk_dt_global.netdev_switch[i].switch_netdev_port = (a_uint8_t)(i + 1);
        ssdk_dt_global.netdev_switch[i].switch_dev_id = (a_uint8_t)(i + 1);
        ssdk_dt_global.netdev_switch[i].switch_cpu_port = 0;
        ssdk_dt_global.netdev_switch[i].switch_connected = true;
    }
    initdev(&a, "ethA", 1); initdev(&b, "ethB", 1); initdev(&c, "ethC", 3);
    legacy_phy.attached_dev = &a; legacy_phy.port = 7;
    priv.sw_fdb_tbl.next = priv.sw_fdb_tbl.prev = &priv.sw_fdb_tbl;
    priv.fdb_sw_sync_port_map = 1U << 1;
}
static void live(void)
{
    CHECK(!ssdk_netdev_cache_ready() && !public_ready_consumer(), "COLD_READY");
    ssdk_netdev_cache_start();
    CHECK(!ssdk_netdev_cache_ready(), "STARTING_READY");
    ssdk_netdev_cache_commit();
    CHECK(ssdk_netdev_cache_ready(), "LIVE_READY");
}
static void event(unsigned long kind, struct net_device *dev)
{
    CHECK(ssdk_dev_event(&ssdk_dev_notifier, kind, dev) == NOTIFY_DONE, "STOCK_CALLBACK_RESULT");
}
static void name_is(unsigned port, const char *expected)
{
    char name[IFNAMSIZ];
    CHECK(ssdk_port_to_ifname_copy(0, port, name, sizeof(name)), "NAME_AVAILABLE");
    CHECK(!strcmp(name, expected), "NAME_VALUE");
}
static void final_empty(void)
{
    ssdk_netdev_cache_stop();
    CHECK(!ssdk_netdev_cache_ready(), "STOPPED_READY");
    CHECK(cells(&a) == 0 && cells(&b) == 0 && cells(&c) == 0, "SWEEP_ALL");
    CHECK(a.refs == 1 && b.refs == 1 && c.refs == 1, "FINAL_REF_BALANCE");
    CHECK(a.holds == a.puts && b.holds == b.puts && c.holds == c.puts, "FINAL_TOKEN_BALANCE");
}
static void metadata_init(unsigned dev, unsigned cpu)
{
#ifdef HPPE
    ssdk_init_cfg cfg = {0};
    cfg.port_cfg.cpu_bmp = 1U << cpu;
    cfg.port_cfg.lan_bmp = 1U << 1;
    SSDK_CURRENT_CHIP_TYPE[dev] = CHIP_HPPE;
    g_chip_ver[dev].chip_type = CHIP_HPPE;
    g_chip_ver[dev].chip_revision = 0;
    CHECK(hppe_dev_init(dev, &cfg) == SW_OK, "ACTUAL_CPU_METADATA_INIT");
#else
    (void)dev; (void)cpu;
#endif
}
static void mark_case(const char *which)
{
    char name[IFNAMSIZ];
#ifndef HPPE
    live();
    SSDK_CURRENT_CHIP_TYPE[0] = CHIP_HPPE;
    g_chip_ver[0].chip_type = CHIP_HPPE;
    dev_table[0].nr_ports = 2; dev_table[0].cpu_port_nr = 3;
    CHECK(!public_mark_consumer(0, 1), "MARK_NON_HPPE_BUILD");
    CHECK(!ssdk_netdev_managed[0][1] && !a.holds, "MARK_REJECT_NO_SIDE_EFFECT");
#else
    if (!strcmp(which, "mark-states")) {
        legacy_phy.attached_dev = NULL;
        metadata_init(0, 3);
        CHECK(!public_mark_consumer(0, 1), "MARK_COLD");
        ssdk_netdev_cache_start();
        CHECK(!public_mark_consumer(0, 1), "MARK_STARTING");
        ssdk_netdev_cache_commit();
        hw_forbidden = 1; p_port_info[0] = NULL;
        CHECK(public_mark_consumer(0, 1) && public_mark_consumer(0, 1), "MARK_LIVE");
        CHECK(!a.phydev && !legacy_phy.attached_dev, "MARK_BEFORE_ATTACHMENT");
        a.phydev = &legacy_phy; legacy_phy.attached_dev = &a;
        hw_forbidden = 0; p_port_info[0] = &props[0];
        CHECK(!a.holds && !cells(&a) && a.refs == 1, "MARK_NO_BINDING_REF");
        legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "MARK_TOMBSTONE");
        ssdk_netdev_cache_stop();
        CHECK(!public_mark_consumer(0, 2) && !ssdk_netdev_managed[0][2], "MARK_STOPPED");
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "MARK_STOP_TOMBSTONE");
        a.phydev = NULL; legacy_phy.attached_dev = &c;
        legacy_forbidden = 0; name_is(2, "ethC");
    } else if (!strcmp(which, "mark-reject")) {
        live();
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_UNINITIALIZED");
        SSDK_CURRENT_CHIP_TYPE[0] = CHIP_HPPE; g_chip_ver[0].chip_type = CHIP_HPPE;
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_UNINITIALIZED");
        ssdk_init_cfg cfg = {0};
        CHECK(hppe_dev_init(0, &cfg) == SW_BAD_VALUE && !dev_table[0].nr_ports,
              "CPU_INIT_WITHOUT_CPU_FAILS");
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_UNINITIALIZED");
        metadata_init(0, 3); metadata_init(1, 3);
        ssdk_chip_type wrong[] = {CHIP_UNSPECIFIED, CHIP_ISIS, CHIP_ISISC, CHIP_APPE, CHIP_MRPPE, CHIP_SCOMPHY, CHIP_MHT};
        for (unsigned i = 0; i < sizeof(wrong) / sizeof(wrong[0]); i++) {
            SSDK_CURRENT_CHIP_TYPE[0] = wrong[i];
            CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_CHIP");
        }
        SSDK_CURRENT_CHIP_TYPE[0] = CHIP_HPPE;
        g_chip_ver[0].chip_revision = CPPE_REVISION;
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_VARIANT");
        g_chip_ver[0].chip_revision = 0; g_chip_ver[0].chip_type = CHIP_APPE;
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_VARIANT");
        g_chip_ver[0].chip_type = CHIP_HPPE;
        CHECK(!public_mark_consumer(1, 1) && !public_mark_consumer(SW_MAX_NR_DEV, 1) &&
              !public_mark_consumer(UINT_MAX, 1), "MARK_REJECT_DEVICE");
        unsigned bad[] = {7, 0, SW_MAX_NR_PORT, UINT_MAX};
        for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++)
            CHECK(!public_mark_consumer(0, bad[i]), "MARK_REJECT_PORT");
        CHECK(!public_mark_consumer(0, 3), "MARK_REJECT_CPU");
        dev_table[0].cpu_port_nr = SW_MAX_NR_PORT;
        CHECK(!public_mark_consumer(0, 1), "MARK_REJECT_CPU_METADATA");
        dev_table[0].cpu_port_nr = 3;
        for (unsigned d = 0; d < SW_MAX_NR_DEV; d++)
            for (unsigned p = 0; p < SW_MAX_NR_PORT; p++)
                CHECK(!ssdk_netdev_managed[d][p], "MARK_REJECT_NO_SIDE_EFFECT");
        CHECK(dev_table[0].nr_ports == 2 && public_mark_consumer(0, 6), "MARK_COUNT_NOT_MAX_ID");
    } else if (!strcmp(which, "mark-failed-register")) {
        legacy_phy.attached_dev = NULL;
        live(); metadata_init(0, 3);
        CHECK(public_mark_consumer(0, 1), "MARK_LIVE");
        CHECK(!a.phydev && !legacy_phy.attached_dev, "MARK_BEFORE_ATTACHMENT");
        a.phydev = &legacy_phy; legacy_phy.attached_dev = &a;
        chip_error = -EIO; event(NETDEV_REGISTER, &a); event(NETDEV_UNREGISTER, &a);
        CHECK(!a.holds && !cells(&a) && a.refs == 1, "FAILED_NATIVE_NO_PUBLICATION");
        legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "FAILED_NATIVE_NO_FALLBACK");
        chip_error = 0; props[0].property[HSL_PP_EXCL_CPU] = 0;
        event(NETDEV_REGISTER, &a); event(NETDEV_UNREGISTER, &a);
        CHECK(!a.holds && !cells(&a) && !ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "FAILED_MAPPING_NO_FALLBACK");
        ssdk_netdev_cache_stop();
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "FAILED_NATIVE_STOP_PERSISTENT");
    } else if (!strcmp(which, "mark-reregister")) {
        legacy_phy.attached_dev = NULL;
        live(); metadata_init(0, 3);
        CHECK(public_mark_consumer(0, 1), "MARK_LIVE");
        CHECK(!a.phydev && !legacy_phy.attached_dev, "MARK_BEFORE_ATTACHMENT");
        a.phydev = &legacy_phy; legacy_phy.attached_dev = &a;
        event(NETDEV_REGISTER, &a); event(NETDEV_REGISTER, &b);
        CHECK(public_mark_consumer(0, 1) && a.refs == 1 && b.refs == 3, "MARK_KEEP_BINDING");
        strcpy(a.name, "stale"); event(NETDEV_CHANGENAME, &a); event(NETDEV_UNREGISTER, &a);
        name_is(1, "ethB"); CHECK(b.refs == 3, "MARK_LATE_EVENT");
        event(NETDEV_UNREGISTER, &b); legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "MARK_RETIRED_PERSISTENT");
        event(NETDEV_REGISTER, &a); name_is(1, "stale");
        a.phydev = NULL; legacy_phy.attached_dev = &c;
        legacy_forbidden = 0; name_is(4, "ethC");
    } else fail("UNKNOWN_CASE");
#endif
}
static void run_case(const char *which)
{
    char name[IFNAMSIZ], out[PAGE_SIZE];
    if (!strcmp(which, "property-domain")) {
        CHECK(HSL_PP_PHY == 0 && HSL_PP_INCL_CPU == 1 && HSL_PP_EXCL_CPU == 2 &&
              HSL_PP_INNER == 3 && HSL_PP_CPU == 4 && HSL_PP_BUTT == 5,
              "PROPERTY_ENUM_DOMAIN");
        CHECK(sizeof(props[0].property) / sizeof(props[0].property[0]) == 5,
              "PROPERTY_TABLE_EXTENT");
        memset(props[0].property, 0, sizeof(props[0].property));
        props[0].property[HSL_PP_INCL_CPU] = 1U << 1;
        props[0].property[HSL_PP_EXCL_CPU] = 1U << 2;
        CHECK(!hsl_port_prop_check(0, 1, HSL_PP_EXCL_CPU) &&
              hsl_port_prop_check(0, 2, HSL_PP_EXCL_CPU), "PROPERTY_ROW_ISOLATION");
        CHECK(hsl_port_prop_check(0, 1, HSL_PP_INCL_CPU) &&
              !hsl_port_prop_check(0, 2, HSL_PP_INCL_CPU), "PROPERTY_ROW_ISOLATION");
        for (unsigned row = 0; row < HSL_PP_BUTT; row++)
            props[0].property[row] = 1U << (row + 3);
        for (unsigned row = 0; row < HSL_PP_BUTT; row++)
            for (unsigned bit = 3; bit < HSL_PP_BUTT + 3; bit++)
                CHECK(hsl_port_prop_check(0, bit, (hsl_port_prop_t)row) ==
                      (a_bool_t)(bit == row + 3), "PROPERTY_ROW_MATRIX");
        CHECK(!hsl_port_prop_check(0, 1, HSL_PP_BUTT) &&
              !hsl_port_prop_check(SW_MAX_NR_DEV, 1, HSL_PP_EXCL_CPU),
              "PROPERTY_BOUNDS_REJECT");
    } else if (!strncmp(which, "mark-", 5)) {
        mark_case(which);
    } else if (!strcmp(which, "readiness")) {
        CHECK(!ssdk_netdev_cache_ready(), "COLD_READY");
        ssdk_netdev_cache_start(); event(NETDEV_REGISTER, &a);
        CHECK(!ssdk_netdev_cache_ready(), "STARTING_READY"); legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "STARTING_NO_FALLBACK");
        ssdk_netdev_cache_commit(); CHECK(ssdk_netdev_cache_ready(), "LIVE_READY"); name_is(1, "ethA");
        ssdk_netdev_cache_stop();
        CHECK(!ssdk_netdev_cache_ready() && !ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "STOPPED_READY");
    } else if (!strcmp(which, "normal")) {
        live(); event(NETDEV_REGISTER, &a);
        CHECK(a.refs == 3 && cells(&a) == 2, "CELL_REFS"); name_is(1, "ethA");
        event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 1 && cells(&a) == 0, "UNREGISTER_REFS");
        event(NETDEV_UNREGISTER, &a); legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "TOMBSTONE_DENY");
    } else if (!strcmp(which, "primary-only")) {
        live(); CHECK(ssdk_netdev_switch_init(&c) == SW_NOT_FOUND, "PRIMARY_ONLY_STATUS");
        CHECK(c.refs == 2 && cells(&c) == 1, "PRIMARY_ONLY_REF"); name_is(3, "ethC");
        event(NETDEV_UNREGISTER, &c); legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 3, name, sizeof(name)), "PRIMARY_TOMBSTONE");
        legacy_forbidden = 0; name_is(4, "ethA"); CHECK(legacy_calls == 1, "UNKNOWN_LEGACY_MISS");
    } else if (!strcmp(which, "duplicate")) {
        live(); event(NETDEV_REGISTER, &a); event(NETDEV_REGISTER, &a);
        CHECK(a.refs == 3 && a.holds == 2 && !a.puts, "DUP_REGISTER_REF");
    } else if (!strcmp(which, "replacement")) {
        live(); event(NETDEV_REGISTER, &a); event(NETDEV_REGISTER, &b);
        CHECK(a.refs == 1 && b.refs == 3, "REPLACE_BALANCE");
        strcpy(a.name, "staleA"); event(NETDEV_CHANGENAME, &a); event(NETDEV_UNREGISTER, &a);
        CHECK(b.refs == 3 && cells(&b) == 2, "STALE_EVENT_REPLACEMENT"); name_is(1, "ethB");
        event(NETDEV_UNREGISTER, &b); legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "TOMBSTONE_DENY");
        event(NETDEV_REGISTER, &a); name_is(1, "staleA");
        event(NETDEV_UNREGISTER, &b); name_is(1, "staleA");
    } else if (!strcmp(which, "rename")) {
        live(); event(NETDEV_REGISTER, &a); strcpy(a.name, "renamed");
        hw_forbidden = 1; event(NETDEV_CHANGENAME, &a); hw_forbidden = 0; name_is(1, "renamed");
        ssdk_switch_name_copy(0, name); CHECK(!strcmp(name, "renamed"), "SWITCH_RENAME");
        strcpy(a.name, "ethA"); event(NETDEV_CHANGENAME, &a); name_is(1, "ethA");
    } else if (!strcmp(which, "all-slots")) {
        live(); event(NETDEV_REGISTER, &a);
        /* Model another writer cell only to exercise all-device retirement bounds. */
        for (unsigned d = 0; d < SW_MAX_NR_DEV; d++)
            for (unsigned p = 0; p < SW_MAX_NR_PORT; p++) {
                if (d == 0 && p == 1) continue;
                spin_lock_bh(&ssdk_netdev_cache_lock); dev_hold(&a);
                phys[d].netdev[p] = &a; ssdk_netdev_managed[d][p] = true;
                spin_unlock_bh(&ssdk_netdev_cache_lock);
            }
        spin_lock_bh(&ssdk_netdev_cache_lock); dev_hold(&a);
        ssdk_dt_global.netdev_switch[1].dev = &a;
        spin_unlock_bh(&ssdk_netdev_cache_lock);
        event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 1 && cells(&a) == 0, "MATCH_ALL_CELLS");
    } else if (!strcmp(which, "identity-hw")) {
        live(); event(NETDEV_REGISTER, &a); a.base_addr = ULONG_MAX; a.type = 0; a.priv_flags = IFF_802_1Q_VLAN;
        strcpy(a.name, "not-native"); a.dev.parent = NULL;
        hw_forbidden = legacy_forbidden = 1; event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 1 && !ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "IDENTITY_RETIRE");
    } else if (!strcmp(which, "reader")) {
        live(); event(NETDEV_REGISTER, &a);
#if CONFIG_NET_DSA
        struct net_device *reader = ssdk_switch_netdev_get(1);
        CHECK(reader == &a && a.refs == 4, "READER_REF");
        event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 2 && !ssdk_switch_netdev_get(1), "READER_AFTER_RETIRE");
        CHECK(!strcmp(reader->name, "ethA"), "OLD_READER_VALID"); dev_put(reader);
#else
        CHECK(ssdk_netdev_cache_name(0, 1, name, sizeof(name)) == 1, "COPY_SNAPSHOT");
        event(NETDEV_UNREGISTER, &a); strcpy(a.name, "gone");
        CHECK(!strcmp(name, "ethA"), "OWNED_COPY");
#endif
    } else if (!strcmp(which, "stop")) {
        live(); event(NETDEV_REGISTER, &a); ssdk_netdev_cache_stop();
        CHECK(a.refs == 1 && !ssdk_netdev_cache_ready(), "STOP_BALANCE");
        event(NETDEV_REGISTER, &b); CHECK(b.refs == 1 && !cells(&b), "STOP_NO_PUBLISH");
        legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "STOP_NO_FALLBACK");
        hw_forbidden = 1; event(NETDEV_UNREGISTER, &a); ssdk_netdev_cache_stop();
    } else if (!strcmp(which, "replay-success")) {
        replay[0] = &a; replay[1] = &c; replay_count = 2;
        ssdk_netdev_notifier_register();
        CHECK(ssdk_netdev_cache_ready() && ssdk_dev_notifier_owned && !ssdk_dev_notifier_error, "REPLAY_LIVE_LEDGER");
        CHECK(a.refs == 3 && c.refs == 2, "REPLAY_REFS");
        ssdk_netdev_notifier_register();
        CHECK(register_calls == 1 && ssdk_dev_notifier_owned && ssdk_netdev_cache_ready() &&
              a.refs == 3 && c.refs == 2, "NOTIFIER_DUPLICATE_OWNER");
        ssdk_netdev_notifier_unregister(); ssdk_netdev_notifier_unregister();
        CHECK(unregister_calls == 1 && a.refs == 1 && c.refs == 1, "REPLAY_REMOVAL_LEDGER");
    } else if (!strcmp(which, "replay-api-error")) {
        register_error = -ENODEV; ssdk_netdev_notifier_register();
        CHECK(!ssdk_netdev_cache_ready() && !ssdk_dev_notifier_owned && ssdk_dev_notifier_error == -ENODEV, "OPTIONAL_ERROR_LEDGER");
        CHECK(logged_errno == -ENODEV && error_logs == 1, "OPTIONAL_EXACT_LOG");
        ssdk_netdev_notifier_unregister(); CHECK(!unregister_calls, "UNOWNED_UNREGISTER");
        name_is(1, "ethA"); CHECK(legacy_calls == 1, "OPTIONAL_UNKNOWN_LEGACY");
    } else if (!strncmp(which, "replay-fail-", 12)) {
        replay[0] = &a; replay[1] = &b; replay[2] = &c; replay_count = 3;
        b.base_addr = port_base(2); replay_fail_index = atoi(which + 12);
        CHECK(replay_fail_index >= 0 && replay_fail_index < 3, "CASE_ARGUMENT");
        ssdk_netdev_notifier_register();
        CHECK(!ssdk_dev_notifier_owned && !ssdk_netdev_cache_ready() && ssdk_dev_notifier_error == -EIO, "REPLAY_FAILED_LEDGER");
        CHECK(a.refs == 1 && b.refs == 1 && c.refs == 1, "FAILED_REPLAY_CURRENT_LEAK");
        CHECK(logged_errno == -EIO && error_logs == 1, "REPLAY_EXACT_LOG");
        legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, (unsigned)replay_fail_index + 1, name, sizeof(name)), "REPLAY_TOMBSTONE");
        ssdk_netdev_notifier_unregister(); CHECK(!unregister_calls, "UNOWNED_UNREGISTER");
    } else if (!strcmp(which, "admission")) {
        live(); a.type = 0; event(NETDEV_REGISTER, &a); CHECK(a.refs == 1, "ADMISSION_TYPE");
        a.type = ARPHRD_ETHER; a.priv_flags = IFF_802_1Q_VLAN; event(NETDEV_REGISTER, &a); CHECK(a.refs == 1, "ADMISSION_VLAN");
        a.priv_flags = 0; strcpy(a.name, "lan"); a.dev.parent = NULL;
        event(NETDEV_REGISTER, &a); CHECK(a.refs == 1, "ADMISSION_NAME");
        a.dev.parent = &native_parent; event(NETDEV_REGISTER, &a); CHECK(a.refs == 3, "NATIVE_RENAMED_ADMISSION");
    } else if (!strcmp(which, "bounds")) {
        live(); CHECK(ssdk_netdev_switch_init(NULL) == SW_BAD_VALUE, "NULL_PUBLISH");
        a.base_addr = 0; CHECK(ssdk_netdev_switch_init(&a) == SW_BAD_VALUE, "BAD_BASE");
        a.base_addr = port_base(SW_MAX_NR_PORT); CHECK(ssdk_netdev_switch_init(&a) == SW_BAD_VALUE, "PORT_LIMIT");
        a.base_addr = port_base(1); props[0].property[HSL_PP_EXCL_CPU] = 0;
        CHECK(ssdk_netdev_switch_init(&a) == SW_BAD_VALUE, "CPU_EXCLUSION");
        props[0].property[HSL_PP_EXCL_CPU] = 0xfffe; phy_info[0] = NULL;
        CHECK(ssdk_netdev_switch_init(&a) == SW_BAD_VALUE, "NULL_PHYINFO"); phy_info[0] = &phys[0];
        for (unsigned d = SW_MAX_NR_DEV; d < SW_MAX_NR_DEV + 2; d++)
            CHECK(!ssdk_port_to_ifname_copy(d, 0, name, sizeof(name)), "DEV_BOUND");
        CHECK(!ssdk_port_to_ifname_copy(UINT_MAX, UINT_MAX, name, sizeof(name)), "UINT_BOUND");
        CHECK(!ssdk_port_to_ifname_copy(0, SW_MAX_NR_PORT, name, sizeof(name)), "PORT_BOUND");
        CHECK(!ssdk_port_to_ifname_copy(0, 1, NULL, IFNAMSIZ), "NULL_COPY");
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, IFNAMSIZ - 1), "SHORT_COPY");
        CHECK(!legacy_calls, "INVALID_NO_LEGACY");
#ifndef MP
        a.base_addr = port_base(SW_MAX_NR_PORT - 1);
        CHECK(ssdk_netdev_switch_init(&a) == SW_NOT_FOUND, "LAST_PORT");
        name_is(SW_MAX_NR_PORT - 1, "ethA");
#endif
    } else if (!strcmp(which, "copy-bounds")) {
        struct { unsigned pre; char value[IFNAMSIZ]; unsigned post; } guarded;
        live(); strcpy(a.name, "123456789abcdef"); event(NETDEV_REGISTER, &a);
        guarded.pre = 0xa1b2c3d4; guarded.post = 0x10203040;
        for (size_t n = 0; n < IFNAMSIZ; n++) {
            memset(guarded.value, 'x', IFNAMSIZ);
            CHECK(!ssdk_port_to_ifname_copy(0, 1, guarded.value, n), "COPY_SHORT_DENY");
            CHECK(guarded.value[0] == 'x' && guarded.pre == 0xa1b2c3d4 && guarded.post == 0x10203040, "COPY_SHORT_GUARD");
        }
        CHECK(ssdk_port_to_ifname_copy(0, 1, guarded.value, sizeof(guarded.value)), "COPY_FULL_ACCEPT");
        CHECK(!memcmp(guarded.value, a.name, IFNAMSIZ) && guarded.pre == 0xa1b2c3d4 && guarded.post == 0x10203040, "COPY_FULL_GUARD");
    } else if (!strcmp(which, "legacy")) {
        name_is(1, "ethA"); CHECK(legacy_calls == 1, "COLD_LEGACY");
        CHECK(ssdk_port_to_ifname_copy(0, 2, name, sizeof(name)), "LEGACY_AVAILABLE");
        strcpy(a.name, "changed"); CHECK(!strcmp(name, "ethA"), "LEGACY_OUTPUT_OWNED");
        legacy_phy.attached_dev = NULL;
        CHECK(!ssdk_port_to_ifname_copy(0, 2, name, sizeof(name)), "LEGACY_NO_ATTACH");
    } else if (!strcmp(which, "tombstone")) {
        live(); event(NETDEV_REGISTER, &a); event(NETDEV_UNREGISTER, &a);
        hw_forbidden = legacy_forbidden = 1;
        CHECK(!ssdk_port_to_ifname_copy(0, 1, name, sizeof(name)), "TOMBSTONE_DENY");
        CHECK(!legacy_calls, "TOMBSTONE_NO_LOOKUP");
        hw_forbidden = legacy_forbidden = 0; event(NETDEV_REGISTER, &b); name_is(1, "ethB");
        event(NETDEV_UNREGISTER, &a); name_is(1, "ethB");
    } else if (!strcmp(which, "g3-missing")) {
        CHECK(ssdk_ifname_to_port(0, "absent") == 0, "G3_MISSING");
    } else if (!strcmp(which, "g3-no-phy")) {
        lookup = &a; CHECK(ssdk_ifname_to_port(0, "ethA") == 0, "G3_NO_PHY_VALUE");
        CHECK(a.refs == 1 && a.holds == a.puts, "G3_NO_PHY_PUT");
    } else if (!strcmp(which, "g3-success")) {
        lookup = &a; a.phydev = &legacy_phy;
        CHECK(ssdk_ifname_to_port(0, "ethA") == 7, "G3_VALUE");
        CHECK(a.refs == 1 && a.holds == a.puts, "G3_PUT");
    } else if (!strcmp(which, "dsa")) {
        struct dsa_switch_ops ops = {.suspend = suspend_fn, .resume = resume_fn};
        struct dsa_switch ds = {.ops = &ops}; struct dsa_port port = {.ds = &ds};
        live(); event(NETDEV_REGISTER, &a); a.dsa_ptr = &port;
        ssdk_switch_set_standby_status(1, true); ssdk_switch_set_standby_status(1, false);
#if CONFIG_NET_DSA
        CHECK(ssdk_switch_enable_dsa(1) == A_TRUE && a.refs == 3, "DSA_READER_BALANCE");
        CHECK(suspend_calls == 1 && resume_calls == 1, "DSA_SYNC_CALLBACKS");
        ds.ops = NULL; ssdk_switch_set_standby_status(1, true);
        port.ds = NULL; ssdk_switch_set_standby_status(1, true);
        a.dsa_ptr = NULL; ssdk_switch_set_standby_status(1, true);
        CHECK(ssdk_switch_enable_dsa(1) == A_FALSE && a.refs == 3, "DSA_ALL_EXIT_PUT");
#else
        CHECK(!suspend_calls && !resume_calls, "DSA_DISABLED_PROFILE");
#endif
        no_bus = true; ssdk_switch_set_standby_status(1, true);
        ssdk_switch_set_standby_status(99, true); CHECK(a.refs == 3, "DSA_READER_BALANCE");
        event(NETDEV_UNREGISTER, &a);
        CHECK(!ssdk_dts_netdev_switch_find_by_netdev(&a), "IDENTITY_LOOKUP_RETIRED");
    } else if (!strcmp(which, "sysfs")) {
        ssdk_netdev_switch_t before[SSDK_NETDEV_SWITCH_NUM];
        live();
        for (unsigned i = 0; i < SSDK_NETDEV_SWITCH_NUM; i++) {
            ssdk_netdev_switch_t *sw = &ssdk_dt_global.netdev_switch[i];
            sw->switch_cpu_port = (a_uint8_t)(i * 3);
            sw->switch_erp_standby = (i == 0);
            for (unsigned p = 0; p < SSDK_MAX_PORT_NUM; p++)
                sw->switch_port_vid[p] = 0xa5a50000U + (i << 8) + p;
            before[i] = *sw;
        }
        CHECK(ssdk_eth_switch_get(NULL, NULL, out) > 0, "SYSFS_EMPTY");
        for (unsigned i = 0; i < SSDK_NETDEV_SWITCH_NUM; i++) {
            ssdk_netdev_switch_t *sw = &ssdk_dt_global.netdev_switch[i];
            CHECK(sw->dev == before[i].dev && sw->switch_connected == before[i].switch_connected &&
                  sw->switch_netdev_port == before[i].switch_netdev_port &&
                  sw->switch_dev_id == before[i].switch_dev_id && sw->switch_cpu_port == before[i].switch_cpu_port &&
                  sw->switch_erp_standby == before[i].switch_erp_standby, "SYSFS_NEIGHBOR_FIELDS");
            for (unsigned p = 0; p < SSDK_MAX_PORT_NUM; p++)
                CHECK(sw->switch_port_vid[p] == ((p == 1 || p == 2) ? 42 : before[i].switch_port_vid[p]),
                      "SYSFS_VID_SENTINELS");
            CHECK(sw->switch_port_bmp == 6 && sw->switch_athtag == 0x88a8, "SYSFS_BITMAP_STORAGE");
        }
        CHECK(strstr(out, "\"name\":\"\"") != NULL, "SYSFS_UNBOUND_NAME");
        event(NETDEV_REGISTER, &a); strcpy(a.name, "renamed"); event(NETDEV_CHANGENAME, &a);
        CHECK(ssdk_eth_switch_get(NULL, NULL, out) > 0 && strstr(out, "\"name\":\"renamed\""), "SYSFS_SNAPSHOT");
        CHECK(ssdk_dts_netdev_switch_find_by_netdev(&a) == &ssdk_dt_global.netdev_switch[0], "IDENTITY_LOOKUP");
        event(NETDEV_UNREGISTER, &a);
        CHECK(ssdk_eth_switch_get(NULL, NULL, out) > 0 && !strstr(out, "renamed"), "SYSFS_RETIRED");
        fal_error = true; ssdk_dt_global.netdev_switch[0].switch_port_bmp = 4;
        CHECK(ssdk_eth_switch_get(NULL, NULL, out) > 0 &&
              ssdk_dt_global.netdev_switch[0].switch_port_bmp == 4, "SYSFS_ERROR_PRIOR_VALUE");
    } else if (!strncmp(which, "fdb-", 4)) {
        ref_fdb_info_t *entry = calloc(1, sizeof(*entry)); CHECK(entry != NULL, "ALLOC");
        live(); event(NETDEV_REGISTER, &a);
        entry->entry.port.id = 1; entry->entry.addr.uc[0] = 0xa5;
        entry->state = !strcmp(which, "fdb-expire") ? REF_FDB_MAC_EXPIRE : REF_FDB_MAC_NEW;
        entry->notified = entry->state == REF_FDB_MAC_EXPIRE;
        entry->list.next = entry->list.prev = &priv.sw_fdb_tbl;
        priv.sw_fdb_tbl.next = priv.sw_fdb_tbl.prev = &entry->list;
        if (!strcmp(which, "fdb-missing")) { event(NETDEV_UNREGISTER, &a); legacy_forbidden = 1; }
        else notify_retire = true;
        fdb_bh = 1; CHECK(_ref_fdb_notify_mac(&priv) == SW_OK, "FDB_RESULT"); fdb_bh = 0;
        if (!strcmp(which, "fdb-missing")) CHECK(!notify_calls && !entry->notified, "FDB_NO_FALSE_NOTIFY");
        else CHECK(notify_calls == 1 && !strcmp(notified_name, "ethA") && notified_mac[0] == 0xa5, "FDB_OWNED_SNAPSHOT");
        if (strcmp(which, "fdb-expire"))
            CHECK(entry->state == REF_FDB_MAC_EXPIRE && entry->notified == !!notify_calls, "FDB_NEW_SIDE_EFFECTS");
        if (strcmp(which, "fdb-expire")) { list_del(&entry->list); free(entry); }
        else CHECK(freed_fdb == 1 && priv.sw_fdb_tbl.next == &priv.sw_fdb_tbl, "FDB_EXPIRE_FREE");
    } else fail("UNKNOWN_CASE");
    final_empty();
    CHECK(checks >= 10, "CASE_MINIMUM");
}
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    setup(); run_case(argv[1]);
    printf("PASS %s\n", argv[1]);
    return 0;
}
