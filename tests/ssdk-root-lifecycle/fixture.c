/* Native A1 boundary model, deliberately not Linux/SSDK structure ABI. */
#include <errno.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t a_uint32_t;
typedef uint32_t __be32;
typedef int sw_error_t;
struct device_node { int refs; };
struct property { int present; };
/* Extracted actual hsl_reg_mode declaration is inserted here. */
/* @ACTUAL_ENUM@ */
typedef struct {
    hsl_reg_mode switch_reg_access_mode, psgmii_reg_access_mode;
    unsigned char untouched[24];
} ssdk_dt_cfg;
typedef struct {
    a_uint32_t num_devices;
    ssdk_dt_cfg **ssdk_dt_switch_nodes;
    unsigned char foreign_fields[32];
} ssdk_dt_global_t;
struct qca_phy_priv {
    a_uint32_t device_id, ports;
    struct device_node *of_node;
    bool qca_ssdk_sw_dev_registered;
};
typedef struct { int chip_type; } ssdk_init_cfg;
static ssdk_dt_global_t ssdk_dt_global;
static struct qca_phy_priv **qca_phy_priv_global;

#define GFP_KERNEL 0
#define __init
#define KERNEL_VERSION(a,b,c) (((a) << 16) | ((b) << 8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define CONFIG_OF 1
#define HPPE 1
#define IN_NETLINK 1
#define SW_OK 0
#define SW_DISABLE 1
#define A_FALSE false
#define SSDK_STR "ssdk"
#define PPE_STR "PPE"
#define SSDK_PHYSICAL_PORT7 7
enum { CHIP_ISIS, CHIP_ISISC, CHIP_MHT, CHIP_MRPPE, CHIP_APPE,
       CHIP_HPPE, CHIP_UNSPECIFIED, CHIP_SCOMPHY };
/* @ACTUAL_ERROR_MACRO@ */

static _Noreturn void fail(const char *marker)
{
    fprintf(stderr, "SSDK_A1 %s\n", marker);
    exit(86);
}
static void require(bool ok, const char *marker)
{
    if (!ok)
        fail(marker);
}

struct allocation {
    void *ptr;
    size_t count, unit;
    unsigned kind, id;
    bool live, success;
};
static struct allocation allocations[64];
static unsigned attempts, frees[64], free_count, fail_at;
static unsigned finds, properties, reads, raw_reads, of_puts, stops, retires, logs;
static bool node_present, property_present, null_value, in_root, foreign;
static int property_length;
static uint32_t property_value;
static unsigned char property_bytes[8];
static struct device_node of_node;
static struct property of_property;
static ssdk_dt_cfg foreign_node;
static ssdk_dt_cfg foreign_node_snapshot;
static ssdk_dt_cfg *foreign_table[1] = { &foreign_node };
static ssdk_dt_global_t foreign_snapshot;
static const char *flow;

static void foreign_unchanged(void)
{
    if (foreign)
        require(memcmp(&ssdk_dt_global, &foreign_snapshot,
                       sizeof(ssdk_dt_global)) == 0 &&
                foreign_table[0] == &foreign_node &&
                memcmp(&foreign_node, &foreign_node_snapshot,
                       sizeof(foreign_node)) == 0,
                "foreign-owner-preserved");
}
static void no_partial_publication(void)
{
    foreign_unchanged();
    if (!foreign)
        require(ssdk_dt_global.ssdk_dt_switch_nodes == NULL &&
                ssdk_dt_global.num_devices == 0, "publication-before-complete");
}
static void *allocate(unsigned kind, size_t count, size_t unit)
{
    if (foreign)
        fail("reentry-side-effect");
    if (in_root && strcmp(flow, "root-alloc") != 0 &&
        fail_at && attempts >= fail_at)
        fail("early-root-private");
    require(of_node.refs == 0, "of-put-before-allocation");
    if (!(in_root && strcmp(flow, "root-alloc") == 0 && attempts > property_value))
        no_partial_publication();
    require(attempts < 64, "allocation-model-capacity");
    struct allocation *a = &allocations[attempts++];
    a->kind = kind;
    a->count = count;
    a->unit = unit;
    a->id = attempts;
    if (attempts == fail_at)
        return NULL;
    require(!unit || count <= SIZE_MAX / unit, "allocation-overflow");
    size_t bytes = count * unit;
    require(bytes <= 8192, "allocation-model-capacity");
    a->ptr = calloc(1, bytes ? bytes : 1);
    require(a->ptr != NULL, "host-allocation");
    a->live = a->success = true;
    return a->ptr;
}
static void *kcalloc(size_t n, size_t size, int flags)
{
    require(flags == GFP_KERNEL, "allocation-flags");
    return allocate(1, n, size);
}
static void *kzalloc(size_t size, int flags)
{
    require(flags == GFP_KERNEL, "allocation-flags");
    return allocate(2, 1, size);
}
static void kfree(void *ptr)
{
    if (!ptr)
        return;
    foreign_unchanged();
    for (unsigned i = 0; i < attempts; ++i) {
        struct allocation *a = &allocations[i];
        if (a->ptr == ptr) {
            require(a->live, "double-free");
            a->live = false;
            require(free_count < 64, "free-model-capacity");
            frees[free_count++] = a->id;
            free(ptr);
            return;
        }
    }
    fail("foreign-free");
}
static struct device_node *of_find_node_by_name(struct device_node *from,
                                               const char *name)
{
    if (foreign)
        fail("reentry-side-effect");
    require(from == NULL && strcmp(name, "ess-instance") == 0, "of-arguments");
    ++finds;
    if (!node_present)
        return NULL;
    ++of_node.refs;
    return &of_node;
}
static void check_property(struct device_node *node, const char *name)
{
    require(node == &of_node && node->refs == 1 &&
            strcmp(name, "num_devices") == 0, "of-arguments");
}
static struct property *of_find_property(struct device_node *node,
                                         const char *name, int *length)
{
    check_property(node, name);
    ++properties;
    if (length)
        *length = property_length;
    return property_present ? &of_property : NULL;
}
static int of_property_read_u32(struct device_node *node, const char *name,
                                a_uint32_t *value)
{
    check_property(node, name);
    ++reads;
    require(property_present && value != NULL, "typed-property-call");
    if (null_value)
        return -ENODATA;
    if (property_length < 4)
        return -EOVERFLOW;
    *value = property_value;
    return 0;
}
static const void *of_get_property(struct device_node *node, const char *name,
                                  a_uint32_t *length)
{
    check_property(node, name);
    ++raw_reads;
    *length = (a_uint32_t)property_length;
    return property_present && !null_value ? property_bytes : NULL;
}
static a_uint32_t be32_to_cpup(const __be32 *ptr)
{
    const unsigned char *p = (const unsigned char *)ptr;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}
static void of_node_put(struct device_node *node)
{
    require(node == &of_node && node->refs == 1, "of-put-owner");
    --node->refs;
    ++of_puts;
}

/* No A1 early-failure test may acquire any of these later resources. */
static _Noreturn void late(void) { fail("early-root-later-stage"); }
static void ssdk_netdev_cache_stop(void)
{
    require(strcmp(flow, "root") != 0, "early-root-controls");
    ++stops;
}
static void ssdk_fdb_retire_controls(void)
{
    require(strcmp(flow, "root") != 0, "early-root-controls");
    ++retires;
}
static void qca_fdb_sw_sync_work_setup(struct qca_phy_priv *p) { (void)p; late(); }
static void qca_intr_work_init(struct qca_phy_priv *p) { (void)p; late(); }
static void qca_ssdk_port_bmp_init(a_uint32_t id) { (void)id; late(); }
static void qca_ssdk_phy_info_init(a_uint32_t id) { (void)id; late(); }
static void ssdk_cfg_default_init(ssdk_init_cfg *cfg) { (void)cfg; late(); }
static int ssdk_dt_parse(ssdk_init_cfg *cfg, a_uint32_t n, a_uint32_t *id)
{ (void)cfg; (void)n; (void)id; late(); }
static a_uint32_t ssdk_device_id_get(a_uint32_t id) { (void)id; late(); }
static struct device_node *ssdk_dts_node_get(a_uint32_t id) { (void)id; late(); }
static int ssdk_plat_init(ssdk_init_cfg *cfg, a_uint32_t id)
{ (void)cfg; (void)id; late(); }
static void ssdk_driver_register(a_uint32_t id) { (void)id; late(); }
static int chip_ver_get(a_uint32_t id, ssdk_init_cfg *cfg)
{ (void)id; (void)cfg; late(); }
static int ssdk_init(a_uint32_t id, ssdk_init_cfg *cfg)
{ (void)id; (void)cfg; late(); }
static void qca_hppe_hw_init(a_uint32_t id) { (void)id; late(); }
static int ssdk_switch_register(a_uint32_t id, int chip)
{ (void)id; (void)chip; late(); }
static void ssdk_sysfs_init(void) { late(); }
static void ssdk_genl_init(void) { late(); }
static void ssdk_netdev_notifier_register(void) { late(); }
static void model_log(const char *format, ...)
{
    require(strstr(format, "module init failed!") != NULL, "unexpected-root-log");
    ++logs;
}
#define SSDK_INFO(...) model_log(__VA_ARGS__)
/* @ACTUAL_FUNCTIONS@ */

static void assert_live_empty(const char *marker)
{
    for (unsigned i = 0; i < attempts; ++i)
        require(!allocations[i].live, marker);
}
static void exit_and_check(void)
{
    ssdk_switch_device_num_exit();
    require(ssdk_dt_global.ssdk_dt_switch_nodes == NULL &&
            ssdk_dt_global.num_devices == 0, "exit-state");
    assert_live_empty("allocation-leak");
    unsigned before = free_count;
    ssdk_switch_device_num_exit();
    require(free_count == before && ssdk_dt_global.num_devices == 0 &&
            ssdk_dt_global.ssdk_dt_switch_nodes == NULL, "repeat-exit");
}
int main(int argc, char **argv)
{
    require(argc == 9, "arguments");
    flow = argv[1];
    node_present = strtoul(argv[2], NULL, 10) != 0;
    property_length = (int)strtol(argv[3], NULL, 10);
    property_present = property_length >= 0;
    null_value = property_length == 0;
    property_value = (uint32_t)strtoull(argv[4], NULL, 10);
    fail_at = (unsigned)strtoul(argv[5], NULL, 10);
    unsigned existing = (unsigned)strtoul(argv[6], NULL, 10);
    unsigned repeat = (unsigned)strtoul(argv[7], NULL, 10);
    require(strcmp(argv[8], "A1") == 0, "arguments");
    for (unsigned i = 0; i < 4; ++i)
        property_bytes[i] = (unsigned char)(property_value >> (24 - 8 * i));
    memset(ssdk_dt_global.foreign_fields, 0xa5, sizeof(ssdk_dt_global.foreign_fields));
    unsigned char preserved[sizeof(ssdk_dt_global.foreign_fields)];
    memcpy(preserved, ssdk_dt_global.foreign_fields, sizeof(preserved));
    if (existing) {
        foreign = true;
        memset(&foreign_node, 0x39, sizeof(foreign_node));
        foreign_node_snapshot = foreign_node;
        ssdk_dt_global.ssdk_dt_switch_nodes = existing & 1 ? foreign_table : NULL;
        ssdk_dt_global.num_devices = existing & 2 ? 1 : 0;
        foreign_snapshot = ssdk_dt_global;
    }
    int expected_ret = existing ? -EBUSY :
        node_present && property_present && property_length < 4 ?
        (null_value ? -ENODATA : -EOVERFLOW) : fail_at ? -ENOMEM : 0;
    in_root = strcmp(flow, "root") == 0 || strcmp(flow, "root-alloc") == 0;
    int ret = in_root ? regi_init() : ssdk_switch_device_num_init();
    require(ret == expected_ret, "return-value");
    require(raw_reads == 0, "typed-property-only");
    require(of_node.refs == 0, "of-ref-balance");
    unsigned successful_nodes = node_present && property_present ? property_value : 1;
    if (foreign) {
        foreign_unchanged();
        require(attempts == 0 && finds == 0, "reentry-side-effect");
    } else if (ret) {
        require(ssdk_dt_global.ssdk_dt_switch_nodes == NULL &&
                ssdk_dt_global.num_devices == 0, "failure-unpublished");
        assert_live_empty(strcmp(flow, "root-alloc") == 0 ?
                          "null-private-topology" : "allocation-leak");
        exit_and_check();
    } else {
        require(!in_root, "scope-root-success-not-modeled");
        require(ssdk_dt_global.num_devices == successful_nodes &&
                ssdk_dt_global.ssdk_dt_switch_nodes != NULL, "topology-values");
        for (unsigned i = 0; i < successful_nodes; ++i) {
            ssdk_dt_cfg zero = {0};
            ssdk_dt_cfg *node = ssdk_dt_global.ssdk_dt_switch_nodes[i];
            require(node != NULL && node->switch_reg_access_mode == HSL_REG_MDIO &&
                    node->psgmii_reg_access_mode == HSL_REG_MDIO &&
                    memcmp(node, &zero, sizeof(zero)) == 0, "node-values");
            for (unsigned j = 0; j < i; ++j)
                require(node != ssdk_dt_global.ssdk_dt_switch_nodes[j], "node-identity");
        }
        if (repeat) {
            ssdk_dt_global_t snapshot = ssdk_dt_global;
            unsigned old_attempts = attempts, old_finds = finds;
            require(ssdk_switch_device_num_init() == -EBUSY, "reentry-return");
            require(memcmp(&snapshot, &ssdk_dt_global, sizeof(snapshot)) == 0 &&
                    old_attempts == attempts && old_finds == finds, "reentry-side-effect");
        }
        if (strcmp(flow, "null-private") == 0) {
            ssdk_free_priv();
            require(ssdk_dt_global.ssdk_dt_switch_nodes == NULL &&
                    ssdk_dt_global.num_devices == 0, "null-private-topology");
        }
        exit_and_check();
    }
    require(qca_phy_priv_global == NULL, "private-null-boundary");
    require(memcmp(preserved, ssdk_dt_global.foreign_fields, sizeof(preserved)) == 0,
            "unrelated-global-preserved");
    printf("{\"ret\":%d,\"find\":%u,\"property\":%u,\"read\":%u,"
           "\"raw\":%u,\"put\":%u,\"refs\":%d,\"stop\":%u,\"retire\":%u,"
           "\"logs\":%u,\"count\":%u,\"table\":%s,\"alloc\":[", ret, finds, properties,
           reads, raw_reads, of_puts, of_node.refs, stops, retires,
           logs,
           ssdk_dt_global.num_devices,
           ssdk_dt_global.ssdk_dt_switch_nodes ? "true" : "false");
    for (unsigned i = 0; i < attempts; ++i) {
        struct allocation *a = &allocations[i];
        printf("%s[%u,%zu,%zu,%s]", i ? "," : "", a->kind, a->count, a->unit,
               a->success ? "true" : "false");
    }
    printf("],\"free\":[");
    for (unsigned i = 0; i < free_count; ++i)
        printf("%s%u", i ? "," : "", frees[i]);
    printf("],\"node_size\":%zu,\"pointer_size\":%zu}\n",
           sizeof(ssdk_dt_cfg), sizeof(void *));
    return 0;
}
