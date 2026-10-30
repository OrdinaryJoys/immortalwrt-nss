/* COUNT native OS/struct boundary model, not target ABI or cleanup safety. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t a_uint32_t;
struct device_node { int refs; };
struct property { int present; };
/* @ACTUAL_SW_ERRORS@ */
/* @ACTUAL_CAPACITY@ */
/* @ACTUAL_ENUM@ */
typedef struct {
    hsl_reg_mode switch_reg_access_mode, psgmii_reg_access_mode;
    unsigned char payload[24];
} ssdk_dt_cfg;
typedef struct {
    a_uint32_t num_devices;
    ssdk_dt_cfg **ssdk_dt_switch_nodes;
    unsigned char unrelated[32];
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
#define A_FALSE false
#define SSDK_STR "ssdk"
#define PPE_STR "PPE"
#define SSDK_PHYSICAL_PORT7 7
enum { CHIP_ISIS, CHIP_ISISC, CHIP_MHT, CHIP_MRPPE, CHIP_APPE,
       CHIP_HPPE, CHIP_UNSPECIFIED, CHIP_SCOMPHY };
/* @ACTUAL_ERROR_MACRO@ */
_Static_assert(SW_MAX_NR_DEV == 3, "this campaign is the actual capacity3 profile");

static _Noreturn void fail(const char *marker)
{
    fprintf(stderr, "SSDK_COUNT %s\n", marker);
    exit(86);
}
static void require(bool ok, const char *marker) { if (!ok) fail(marker); }
static char events[96][256];
static unsigned event_count;
static void event(const char *format, ...) __attribute__((format(printf, 1, 2)));
static void event(const char *format, ...)
{
    require(event_count < 96, "event-capacity");
    va_list args;
    va_start(args, format);
    int n = vsnprintf(events[event_count], sizeof(events[0]), format, args);
    va_end(args);
    require(n > 0 && (size_t)n < sizeof(events[0]), "event-length");
    ++event_count;
}
static struct device_node node;
static struct property property;
static bool has_node, has_property, in_root, foreign;
static int property_length, prep_error;
static uint32_t property_value, effective;
static unsigned fail_at, attempts;
static const char *flow;
static ssdk_dt_cfg foreign_child, foreign_child_copy;
static ssdk_dt_cfg *foreign_table[1] = { &foreign_child };
static ssdk_dt_global_t foreign_copy;
struct block { void *ptr; unsigned id; bool live; };
static struct block blocks[16];

static void unchanged(void)
{
    if (foreign)
        require(memcmp(&ssdk_dt_global, &foreign_copy, sizeof(foreign_copy)) == 0 &&
                foreign_table[0] == &foreign_child &&
                memcmp(&foreign_child, &foreign_child_copy, sizeof(foreign_child)) == 0,
                "foreign-owner-preserved");
}
static void *allocate(unsigned kind, size_t n, size_t size)
{
    require(!foreign, "foreign-side-effect");
    require(node.refs == 0, "of-put-before-allocation");
    if (in_root && strcmp(flow, "root-alloc") != 0 &&
        (((prep_error || effective > SW_MAX_NR_DEV) && kind == 2) ||
         (fail_at && attempts >= fail_at)))
        fail("root-entered-private");
    require(effective <= SW_MAX_NR_DEV, "count-admitted-to-allocator");
    require(prep_error == 0, "malformed-allocated");
    bool private_array = in_root && strcmp(flow, "root-alloc") == 0 && attempts == effective + 1;
    if (!private_array)
        require(ssdk_dt_global.ssdk_dt_switch_nodes == NULL && ssdk_dt_global.num_devices == 0,
                "premature-publication");
    require(attempts < 16 && (!size || n <= SIZE_MAX / size), "allocation-model-domain");
    struct block *b = &blocks[attempts++];
    b->id = attempts;
    bool ok = attempts != fail_at;
    event("ALLOC %u %zu %zu %u %u\n", kind, n, size, attempts, (unsigned)ok);
    if (!ok)
        return NULL;
    size_t bytes = n * size;
    require(bytes <= 4096, "allocation-model-domain");
    b->ptr = calloc(1, bytes ? bytes : 1);
    require(b->ptr != NULL, "host-allocation");
    b->live = true;
    return b->ptr;
}
static void *kcalloc(size_t n, size_t size, int flags)
{ require(flags == GFP_KERNEL, "allocation-flags"); return allocate(1, n, size); }
static void *kzalloc(size_t size, int flags)
{ require(flags == GFP_KERNEL, "allocation-flags"); return allocate(2, 1, size); }
static void kfree(void *ptr)
{
    if (!ptr) return;
    unchanged();
    for (unsigned i = 0; i < attempts; ++i) {
        if (blocks[i].ptr == ptr) {
            require(blocks[i].live, "double-free");
            event("FREE %u\n", blocks[i].id);
            blocks[i].live = false;
            free(ptr);
            return;
        }
    }
    fail("foreign-free");
}
static struct device_node *of_find_node_by_name(struct device_node *from, const char *name)
{
    require(!foreign, "foreign-side-effect");
    require(from == NULL && strcmp(name, "ess-instance") == 0, "of-arguments");
    event("OF_FIND %u\n", (unsigned)has_node);
    if (!has_node) return NULL;
    ++node.refs;
    return &node;
}
static void of_arguments(struct device_node *np, const char *name)
{ require(np == &node && node.refs == 1 && strcmp(name, "num_devices") == 0, "of-arguments"); }
static struct property *of_find_property(struct device_node *np, const char *name, int *len)
{
    of_arguments(np, name);
    event("OF_PROPERTY %d\n", property_length);
    if (len) *len = property_length;
    return has_property ? &property : NULL;
}
static int of_property_read_u32(struct device_node *np, const char *name, a_uint32_t *value)
{
    of_arguments(np, name);
    require(has_property && value != NULL, "typed-property-call");
    int ret = property_length == 0 ? -ENODATA : property_length < 4 ? -EOVERFLOW : 0;
    if (!ret) *value = property_value;
    event("OF_READ %d %u\n", ret, ret ? 0u : property_value);
    return ret;
}
static void of_node_put(struct device_node *np)
{
    require(np == &node && node.refs == 1, "of-put-owner");
    --node.refs;
    event("OF_PUT %d\n", node.refs);
}
static _Noreturn void late(void) { fail("root-later-stage"); }
static void ssdk_netdev_cache_stop(void)
{ require(strcmp(flow, "root") != 0, "root-controls"); event("CONTROL cache\n"); }
static void ssdk_fdb_retire_controls(void)
{ require(strcmp(flow, "root") != 0, "root-controls"); event("CONTROL retire\n"); }
static void qca_fdb_sw_sync_work_setup(struct qca_phy_priv *p) { (void)p; late(); }
static void qca_intr_work_init(struct qca_phy_priv *p) { (void)p; late(); }
static void qca_ssdk_port_bmp_init(a_uint32_t id) { (void)id; late(); }
static void qca_ssdk_phy_info_init(a_uint32_t id) { (void)id; late(); }
static void ssdk_cfg_default_init(ssdk_init_cfg *cfg) { (void)cfg; late(); }
static int ssdk_dt_parse(ssdk_init_cfg *cfg, a_uint32_t n, a_uint32_t *id)
{ (void)cfg; (void)n; (void)id; late(); }
static a_uint32_t ssdk_device_id_get(a_uint32_t id) { (void)id; late(); }
static struct device_node *ssdk_dts_node_get(a_uint32_t id) { (void)id; late(); }
static int ssdk_plat_init(ssdk_init_cfg *cfg, a_uint32_t id) { (void)cfg; (void)id; late(); }
static void ssdk_driver_register(a_uint32_t id) { (void)id; late(); }
static int chip_ver_get(a_uint32_t id, ssdk_init_cfg *cfg) { (void)id; (void)cfg; late(); }
static int ssdk_init(a_uint32_t id, ssdk_init_cfg *cfg) { (void)id; (void)cfg; late(); }
static void qca_hppe_hw_init(a_uint32_t id) { (void)id; late(); }
static int ssdk_switch_register(a_uint32_t id, int chip) { (void)id; (void)chip; late(); }
static void ssdk_sysfs_init(void) { late(); }
static void ssdk_genl_init(void) { late(); }
static void ssdk_netdev_notifier_register(void) { late(); }
static void model_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void model_log(const char *fmt, ...)
{
    char text[200];
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(text, sizeof(text), fmt, args);
    va_end(args);
    require(n > 0 && (size_t)n < sizeof(text), "log-length");
    event("LOG %s", text);
}
#define SSDK_INFO(...) model_log(__VA_ARGS__)
/* @ACTUAL_FUNCTIONS@ */

static void state(const char *label)
{
    require(ssdk_switch_device_num_get() == ssdk_dt_global.num_devices, "actual-get-count");
    event("STATE %s %u %u\n", label, ssdk_dt_global.num_devices,
          (unsigned)(ssdk_dt_global.ssdk_dt_switch_nodes != NULL));
}
int main(int argc, char **argv)
{
    require(argc == 10, "arguments");
    flow = argv[1];
    has_node = strtoul(argv[2], NULL, 10) != 0;
    property_length = (int)strtol(argv[3], NULL, 10);
    has_property = property_length >= 0;
    property_value = (uint32_t)strtoull(argv[4], NULL, 10);
    fail_at = (unsigned)strtoul(argv[5], NULL, 10);
    unsigned existing = (unsigned)strtoul(argv[6], NULL, 10);
    bool repeat = strtoul(argv[7], NULL, 10) != 0;
    int expected_ret = (int)strtol(argv[8], NULL, 10);
    effective = has_node && has_property ? property_value : 1;
    prep_error = has_node && has_property && property_length < 4 ?
                 (property_length == 0 ? -ENODATA : -EOVERFLOW) : 0;
    memset(ssdk_dt_global.unrelated, 0xa5, sizeof(ssdk_dt_global.unrelated));
    unsigned char unrelated[32];
    memcpy(unrelated, ssdk_dt_global.unrelated, sizeof(unrelated));
    if (existing) {
        foreign = true;
        memset(&foreign_child, 0x39, sizeof(foreign_child));
        foreign_child_copy = foreign_child;
        ssdk_dt_global.ssdk_dt_switch_nodes = existing & 1 ? foreign_table : NULL;
        ssdk_dt_global.num_devices = existing & 2 ? 1 : 0;
        foreign_copy = ssdk_dt_global;
    }
    in_root = strcmp(flow, "root") == 0 || strcmp(flow, "root-alloc") == 0;
    int ret = in_root ? regi_init() : ssdk_switch_device_num_init();
    require(ret == expected_ret, "return-value");
    require(node.refs == 0, "of-reference-balance");
    unchanged();
    state("return");
    if (!foreign && !ret) {
        require(!in_root && ssdk_dt_global.num_devices == effective &&
                ssdk_dt_global.ssdk_dt_switch_nodes != NULL, "topology-values");
        for (unsigned i = 0; i < effective; ++i) {
            ssdk_dt_cfg zero = {0}, *child = ssdk_dt_global.ssdk_dt_switch_nodes[i];
            require(child != NULL && memcmp(child, &zero, sizeof(zero)) == 0, "node-data");
            for (unsigned j = 0; j < i; ++j)
                require(child != ssdk_dt_global.ssdk_dt_switch_nodes[j], "node-identity");
            event("NODE %u %d %d 1\n", i, child->switch_reg_access_mode, child->psgmii_reg_access_mode);
        }
        if (repeat) {
            unsigned old_attempts = attempts, old_events = event_count;
            ssdk_dt_global_t old = ssdk_dt_global;
            require(ssdk_switch_device_num_init() == -EBUSY && attempts == old_attempts &&
                    event_count == old_events && memcmp(&old, &ssdk_dt_global, sizeof(old)) == 0,
                    "repeat-init");
            event("REENTRY -%d\n", EBUSY);
        }
        if (strcmp(flow, "null-private") == 0) {
            ssdk_free_priv();
            require(ssdk_dt_global.num_devices == 0 && ssdk_dt_global.ssdk_dt_switch_nodes == NULL,
                    "null-private-topology");
        }
    }
    if (!foreign) {
        ssdk_switch_device_num_exit();
        require(ssdk_dt_global.num_devices == 0 && ssdk_dt_global.ssdk_dt_switch_nodes == NULL,
                "exit-state");
        state("exit");
        ssdk_switch_device_num_exit();
        state("repeat-exit");
    }
    for (unsigned i = 0; i < attempts; ++i) require(!blocks[i].live, "allocation-leak");
    require(qca_phy_priv_global == NULL, "private-null");
    require(memcmp(unrelated, ssdk_dt_global.unrelated, sizeof(unrelated)) == 0, "unrelated-state");
    FILE *oracle = fopen(argv[9], "r");
    require(oracle != NULL, "oracle-open");
    char line[256];
    for (unsigned i = 0; i < event_count; ++i)
        require(fgets(line, sizeof(line), oracle) != NULL && strcmp(line, events[i]) == 0,
                "ordered-trace");
    require(fgets(line, sizeof(line), oracle) == NULL && !ferror(oracle), "ordered-trace");
    require(fclose(oracle) == 0, "oracle-close");
    printf("RESULT %d\n", ret);
    for (unsigned i = 0; i < event_count; ++i) fputs(events[i], stdout);
    return 0;
}
