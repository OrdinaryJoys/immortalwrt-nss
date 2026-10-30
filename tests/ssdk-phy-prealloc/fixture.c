/* Explicit Linux private/work/topology models; real SDK metadata declarations below. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
#include "@LINUX_ENUM_PATH@"
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
struct net_device;
/* @TYPES@ */
/* @APIS@ */
struct device_node { unsigned unused; };
struct model_init { unsigned initialized; };
struct work_struct { void (*fn)(struct work_struct *); unsigned initialized; };
struct delayed_work { struct work_struct work; };
struct qca_phy_priv {
    a_uint32_t device_id, ports;
    struct device_node *of_node;
    a_bool_t qca_ssdk_sw_dev_registered;
    struct model_init fdb_ctrl_lock, fdb_sw_sync_lock, fdb_wait, sw_fdb_tbl;
    struct delayed_work fdb_sw_sync_dwork;
    bool fdb_work_initialized;
    struct model_init qm_lock, intr_ctrl_lock, intr_rearm_lock, intr_state_lock;
    struct work_struct intr_workqueue;
    bool intr_work_initialized;
    unsigned char untouched[23];
};
typedef struct { ssdk_chip_type chip_type; } ssdk_init_cfg;
static phy_info_t *phy_info[SW_MAX_NR_DEV], *reference_phy_info[SW_MAX_NR_DEV];
static a_uint32_t port_bmp[SW_MAX_NR_DEV], reference_port_bmp[SW_MAX_NR_DEV];
static struct qca_phy_priv **qca_phy_priv_global;
static phy_info_t foreign[SW_MAX_NR_DEV], foreign_copy[SW_MAX_NR_DEV];
static struct qca_phy_priv foreign_private, foreign_private_copy;
static struct qca_phy_priv *foreign_vector[1] = { &foreign_private };
/* Shared-ops sentinel is a model, not a real driver's teardown protocol. */
static unsigned char shared_ops[67], shared_ops_copy[67];
static phy_info_t *expected_phy[SW_MAX_NR_DEV];
static a_uint32_t expected_bmp[SW_MAX_NR_DEV];
static struct qca_phy_priv **expected_private;
static char events[256][160];
static unsigned event_count, attempts, fault_at, count, scenario, irq_setups;
static const char *flow;
struct allocation { void *ptr; bool live; char kind; size_t count, bytes; };
static struct allocation allocations[32];
static jmp_buf root_stop;
static unsigned root_boundary, topology_exits;

static _Noreturn void fail(const char *name)
{ fprintf(stderr, "SSDK_PHY %s\n", name); exit(86); }
static void check(bool ok, const char *name) { if (!ok) fail(name); }
static void event(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void event(const char *fmt, ...)
{
    check(event_count < 256, "EVENT_CAPACITY");
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(events[event_count], sizeof(events[0]), fmt, ap);
    va_end(ap);
    check(n > 0 && (size_t)n < sizeof(events[0]), "EVENT_LENGTH");
    ++event_count;
}
static void globals_unchanged(const char *name)
{
    check(memcmp(phy_info, expected_phy, sizeof(phy_info)) == 0 &&
          memcmp(port_bmp, expected_bmp, sizeof(port_bmp)) == 0 &&
          qca_phy_priv_global == expected_private, name);
    check(memcmp(foreign, foreign_copy, sizeof(foreign)) == 0 &&
          memcmp(&foreign_private, &foreign_private_copy, sizeof(foreign_private)) == 0 &&
          foreign_vector[0] == &foreign_private &&
          memcmp(shared_ops, shared_ops_copy, sizeof(shared_ops)) == 0, "FOREIGN_PAYLOAD");
}
static void *allocate(size_t n, size_t bytes, char kind)
{
    globals_unchanged("STAGING_GLOBAL");
    check(attempts < 32 && (!bytes || n <= SIZE_MAX / bytes), "ALLOC_DOMAIN");
    if (kind == 'V') check(bytes == sizeof(void *) && n == count, "VECTOR_SHAPE");
    bool root = !strcmp(flow, "alloc") || !strcmp(flow, "root");
    if (kind != 'V') {
        char expected = root && attempts % 2 ? 'P' : 'M';
        check(bytes == (expected == 'P' ? sizeof(struct qca_phy_priv) : sizeof(phy_info_t)), "ALLOC_SHAPE");
        kind = expected;
    }
    ++attempts;
    bool ok = attempts != fault_at;
    event("ALLOC %u %c %u\n", attempts, kind, (unsigned)ok);
    allocations[attempts - 1].kind = kind;
    allocations[attempts - 1].count = n;
    allocations[attempts - 1].bytes = bytes;
    if (!ok) return NULL;
    size_t total = n * bytes;
    void *p = calloc(1, total ? total : 1);
    check(p != NULL, "HOST_ALLOC");
    allocations[attempts - 1].ptr = p;
    allocations[attempts - 1].live = true;
    return p;
}
#define GFP_KERNEL 0
static void *kcalloc(size_t n, size_t bytes, int flags)
{ check(flags == GFP_KERNEL, "ALLOC_FLAGS"); return allocate(n, bytes, 'V'); }
static void *kzalloc(size_t bytes, int flags)
{
    check(flags == GFP_KERNEL, "ALLOC_FLAGS");
    bool root = !strcmp(flow, "alloc") || !strcmp(flow, "root");
    /* The old complete allocator used kzalloc, the new one kcalloc. */
    if (root && !attempts && bytes == count * sizeof(void *))
        return allocate(count, sizeof(void *), 'V');
    return allocate(1, bytes, '?');
}
static void kfree(void *p)
{
    if (!p) return;
    globals_unchanged("FREE_GLOBAL");
    for (unsigned i = attempts; i; --i) {
        struct allocation *a = &allocations[i - 1];
        if (a->ptr == p) {
            check(a->live, "DOUBLE_FREE");
            for (unsigned j = i; j < attempts; ++j)
                check(!allocations[j].live, "FREE_ORDER");
            event("FREE %u\n", i);
            a->live = false;
            free(p);
            return;
        }
    }
    fail("FOREIGN_FREE");
}
static void *reference_alloc(size_t bytes, int flags)
{ check(flags == GFP_KERNEL, "REFERENCE_FLAGS"); void *p = calloc(1, bytes); check(p != NULL, "REFERENCE_ALLOC"); return p; }
static void model_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void model_log(const char *fmt, ...)
{
    /* Logs are consumed, formatted and checked separately from semantic markers. */
    char message[160]; va_list ap; va_start(ap, fmt);
    int n = vsnprintf(message, sizeof(message), fmt, ap); va_end(ap);
    check(n > 0 && (size_t)n < sizeof(message), "LOG_FORMAT");
    if (strstr(message, "kzalloc failed")) event("LOG META_ENOMEM\n");
    else if (strstr(message, "module init failed!")) fail("ROOT_GENERIC_OUT");
    else fail("UNEXPECTED_LOG");
}
#define SSDK_ERROR(...) model_log(__VA_ARGS__)
#define SSDK_INFO(...) model_log(__VA_ARGS__)
#define __init
#define HPPE 1
#define IN_NETLINK 1
#define CONFIG_OF 1
#define KERNEL_VERSION(a,b,c) (((a) << 16) | ((b) << 8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define SSDK_STR "ssdk"
#define PPE_STR "PPE"
/* @MACRO@ */
static void model_init(struct model_init *p) { check(!p->initialized, "SETUP_DUPLICATE"); p->initialized = 1; }
#define mutex_init(p) model_init(p)
#define aos_lock_init(p) model_init(p)
#define spin_lock_init(p) model_init(p)
#define init_waitqueue_head(p) model_init(p)
#define INIT_LIST_HEAD(p) model_init(p)
static void qca_fdb_sw_sync_work_task(struct work_struct *w) { (void)w; fail("WORK_STARTED"); }
static void qca_intr_workqueue_task(struct work_struct *w) { (void)w; fail("WORK_STARTED"); }
static void model_work(struct work_struct *p, void (*fn)(struct work_struct *), bool irq)
{
    globals_unchanged("SETUP_GLOBAL");
    check(!p->initialized, "SETUP_DUPLICATE");
    p->initialized = 1; p->fn = fn;
    event("SETUP %s\n", irq ? "IRQ" : "FDB");
    if (irq && ++irq_setups == count && scenario == 61) {
        qca_phy_priv_global = foreign_vector; expected_private = foreign_vector;
        event("INJECT PRIVATE\n");
    }
    if (irq && irq_setups == count && scenario == 62) {
        phy_info[SW_MAX_NR_DEV - 1] = &foreign[SW_MAX_NR_DEV - 1];
        expected_phy[SW_MAX_NR_DEV - 1] = phy_info[SW_MAX_NR_DEV - 1];
        event("INJECT META\n");
    }
}
#define INIT_DELAYED_WORK(p, fn) model_work(&(p)->work, fn, false)
#define INIT_WORK(p, fn) model_work(p, fn, true)
static _Noreturn void late(void) { fail("LATE_RESOURCE"); }
static int ssdk_switch_device_num_init(void) { event("TOPO INIT %u\n", count); return 0; }
static a_uint32_t ssdk_switch_device_num_get(void) { return count; }
static void ssdk_switch_device_num_exit(void) { ++topology_exits; event("TOPO EXIT\n"); }
static void ssdk_netdev_cache_stop(void) { fail("GLOBAL_CLEANUP"); }
static void ssdk_fdb_retire_controls(void) { fail("GLOBAL_CLEANUP"); }
static void ssdk_cfg_default_init(ssdk_init_cfg *p) { p->chip_type = CHIP_UNSPECIFIED; event("CFG LEAF\n"); }
static sw_error_t ssdk_dt_parse(ssdk_init_cfg *p, a_uint32_t n, a_uint32_t *id)
{ (void)p; check(n == 0 && id != NULL, "DT_BOUNDARY_ARGS"); root_boundary = 1; event("STOP DT\n"); longjmp(root_stop, 1); }
static a_uint32_t ssdk_device_id_get(a_uint32_t id) { (void)id; late(); }
static struct device_node *ssdk_dts_node_get(a_uint32_t id) { (void)id; late(); }
static int ssdk_plat_init(ssdk_init_cfg *p, a_uint32_t id) { (void)p; (void)id; late(); }
static void ssdk_driver_register(a_uint32_t id) { (void)id; late(); }
static int chip_ver_get(a_uint32_t id, ssdk_init_cfg *p) { (void)p; (void)id; late(); }
static int ssdk_init(a_uint32_t id, ssdk_init_cfg *p) { (void)p; (void)id; late(); }
static void qca_hppe_hw_init(a_uint32_t id) { (void)id; late(); }
static int ssdk_switch_register(a_uint32_t id, ssdk_chip_type chip) { (void)id; (void)chip; late(); }
static void ssdk_sysfs_init(void) { check(count == 0, "ZERO_BOUNDARY"); root_boundary = 2; event("STOP ZERO_SYSFS\n"); longjmp(root_stop, 1); }
static void ssdk_genl_init(void) { late(); }
static void ssdk_netdev_notifier_register(void) { late(); }
/* Reference calls are complete baseline bodies, with named globals/functions renamed only. */
void reference_qca_ssdk_port_bmp_set(a_uint32_t, a_uint32_t);
sw_error_t reference_hsl_port_feature_set(a_uint32_t, a_uint32_t, phy_features_t);
sw_error_t reference_hsl_port_feature_clear(a_uint32_t, a_uint32_t, phy_features_t);
/* @QCA@ */
/* @REFERENCE@ */
/* @FUNCTIONS@ */

static void metadata_equal(phy_info_t *p, unsigned d, a_uint32_t initial, a_uint32_t bitmap)
{
    check(p != NULL && d < SW_MAX_NR_DEV, "META_OWNER");
    phy_info_t expected;
    memset(&expected, 0, sizeof(expected));
    for (unsigned j = 0; j < SW_MAX_NR_PORT; ++j) {
        expected.phy_type[j] = MAX_PHY_CHIP;
        expected.port_link_status[j] = PORT_LINK_DOWN;
        expected.port_mode[j] = PORT_INTERFACE_MODE_MAX;
        expected.phy_address[j] = j == SSDK_PHYSICAL_PORT0 ? INVALID_PHY_ADDR : j - 1;
    }
    a_uint32_t desired = initial;
#ifdef QCA808X_PORTS_INFO
    desired = 0;
    for (size_t i = 0; i < sizeof(reference_qca808x_phy_info) / sizeof(reference_qca808x_phy_info[0]); ++i) {
        unsigned port = reference_qca808x_phy_info[i].port_id;
        check(port < SW_MAX_NR_PORT, "REFERENCE_TABLE_DOMAIN");
        desired |= (a_uint32_t)1 << port;
        expected.phy_address[port] = reference_qca808x_phy_info[i].phy_address;
        if (reference_qca808x_phy_info[i].phy_access_type == PHY_I2C_ACCESS)
            expected.phy_features[port] |= PHY_F_I2C;
    }
#endif
    check(memcmp(p, &expected, sizeof(expected)) == 0 && bitmap == desired, "META_COMPLETE_VALUE");
    reference_port_bmp[d] = initial;
    check(reference_phy_info[d] == NULL && reference_qca_ssdk_phy_info_init(d) == 0, "REFERENCE_INIT");
    check(memcmp(p, reference_phy_info[d], sizeof(*p)) == 0 && bitmap == reference_port_bmp[d], "BASELINE_COMPLETE_EQUIVALENCE");
    free(reference_phy_info[d]); reference_phy_info[d] = NULL;
    event("META %u FULL_BASELINE_MATCH\n", d);
}
static void private_equal(struct qca_phy_priv *p)
{
    struct qca_phy_priv expected;
    memset(&expected, 0, sizeof(expected));
    expected.qca_ssdk_sw_dev_registered = A_FALSE;
    expected.fdb_ctrl_lock.initialized = expected.fdb_sw_sync_lock.initialized = 1;
    expected.fdb_wait.initialized = expected.sw_fdb_tbl.initialized = 1;
    expected.fdb_sw_sync_dwork.work.fn = qca_fdb_sw_sync_work_task;
    expected.fdb_sw_sync_dwork.work.initialized = 1;
    expected.fdb_work_initialized = true;
    expected.qm_lock.initialized = expected.intr_ctrl_lock.initialized = 1;
    expected.intr_rearm_lock.initialized = expected.intr_state_lock.initialized = 1;
    expected.intr_workqueue.fn = qca_intr_workqueue_task;
    expected.intr_workqueue.initialized = 1;
    expected.intr_work_initialized = true;
    check(memcmp(p, &expected, sizeof(expected)) == 0, "PRIVATE_COMPLETE_VALUE");
}
static unsigned live_count(void)
{ unsigned n = 0; for (unsigned i = 0; i < attempts; ++i) n += allocations[i].live; return n; }
static void root_transfer_owners(void)
{
    check(count <= SW_MAX_NR_DEV && attempts == 1 + 2 * count, "ROOT_OWNER_COUNT");
    const struct allocation *v = &allocations[0];
    check(v->live && v->kind == 'V' && v->count == count &&
          v->bytes == sizeof(*qca_phy_priv_global) &&
          qca_phy_priv_global == v->ptr, "ROOT_VECTOR_OWNER");
    bool seen[32] = {true};
    for (unsigned d = 0; d < count; ++d) {
        struct qca_phy_priv *p = qca_phy_priv_global[d];
        phy_info_t *m = phy_info[d];
        check(p != NULL, "ROOT_PRIVATE_MISSING");
        check(m != NULL, "ROOT_METADATA_MISSING");
        for (unsigned j = 0; j < d; ++j) {
            check(p != qca_phy_priv_global[j], "ROOT_PRIVATE_ALIAS");
            check(m != phy_info[j], "ROOT_METADATA_ALIAS");
        }
        unsigned pi = 1 + 2 * d, mi = 2 + 2 * d;
        const struct allocation *pa = &allocations[pi], *ma = &allocations[mi];
        check(pa->live && pa->kind == 'P' && pa->ptr == p &&
              pa->count == 1 && pa->bytes == sizeof(*p), "ROOT_PRIVATE_SLOT");
        check(ma->live && ma->kind == 'M' && ma->ptr == m &&
              ma->count == 1 && ma->bytes == sizeof(*m), "ROOT_METADATA_SLOT");
        check(!seen[pi] && !seen[mi], "ROOT_OWNER_DUPLICATE_ID");
        seen[pi] = seen[mi] = true;
    }
    for (unsigned i = 0; i < attempts; ++i)
        check(seen[i] && allocations[i].live, "ROOT_TRANSFER_CLOSURE");
}
static void cleanup_model(void)
{
    event("MODEL_CLEANUP\n");
    /* Harness owner disposal, never represented as actual normal driver cleanup. */
    for (unsigned i = attempts; i; --i) if (allocations[i - 1].live) {
        void *p = allocations[i - 1].ptr;
        for (unsigned d = 0; d < SW_MAX_NR_DEV; ++d) if (phy_info[d] == p) {
            phy_info[d] = NULL; expected_phy[d] = NULL;
        }
        if ((void *)qca_phy_priv_global == p) { qca_phy_priv_global = NULL; expected_private = NULL; }
        kfree(p);
    }
    check(live_count() == 0, "MODEL_FINAL_OWNER_LEDGER");
}
int main(int argc, char **argv)
{
    check(argc == 6, "ARGS"); flow = argv[1]; count = (unsigned)strtoul(argv[2], NULL, 10);
    fault_at = (unsigned)strtoul(argv[3], NULL, 10); scenario = (unsigned)strtoul(argv[4], NULL, 10);
    int expected_ret = (int)strtol(argv[5], NULL, 10), ret = 0;
    memset(foreign, 0xa6, sizeof(foreign)); memcpy(foreign_copy, foreign, sizeof(foreign));
    memset(&foreign_private, 0x93, sizeof(foreign_private)); foreign_private_copy = foreign_private;
    memset(shared_ops, 0xd5, sizeof(shared_ops)); memcpy(shared_ops_copy, shared_ops, sizeof(shared_ops));
    for (unsigned d = 0; d < SW_MAX_NR_DEV; ++d) port_bmp[d] = expected_bmp[d] = 0x9100u + d * 0x101u;
    if (scenario == 5) phy_info[0] = expected_phy[0] = &foreign[0];
    if (scenario == 6) phy_info[SW_MAX_NR_DEV - 1] = expected_phy[SW_MAX_NR_DEV - 1] = &foreign[SW_MAX_NR_DEV - 1];
    if (scenario == 60) qca_phy_priv_global = expected_private = foreign_vector;
    if (!strcmp(flow, "alloc") || !strcmp(flow, "root")) {
        if (!strcmp(flow, "root")) {
            if (setjmp(root_stop) == 0) ret = regi_init();
            else ret = 0;
        } else ret = ssdk_alloc_priv(count);
        check(ret == expected_ret, "ALLOC_RETURN");
        if (!ret) {
            check(count <= SW_MAX_NR_DEV && qca_phy_priv_global != NULL &&
                  live_count() == 1 + 2 * count, "OWNER_LEDGER");
            root_transfer_owners();
            expected_private = qca_phy_priv_global;
            for (unsigned d = 0; d < count; ++d) {
                metadata_equal(phy_info[d], d, 0x3e, port_bmp[d]);
                private_equal(qca_phy_priv_global[d]); expected_phy[d] = phy_info[d]; expected_bmp[d] = port_bmp[d];
            }
            event("TRANSFER %u\n", count);
            if (!strcmp(flow, "root")) check(topology_exits == 0 && root_boundary == (count ? 1u : 2u), "ROOT_SUCCESS_BOUNDARY");
        } else {
            globals_unchanged("ABORT_GLOBAL"); check(live_count() == 0, "OWNER_LEDGER");
            if (!strcmp(flow, "root")) check(topology_exits == 1 && root_boundary == 0, "ROOT_ERROR_GATE");
        }
    } else if (!strcmp(flow, "prepare")) {
        phy_info_t *p = scenario == 3 ? &foreign[1] : NULL, *old = p;
        a_uint32_t bitmap = 0x7531;
        ret = qca_ssdk_phy_info_prepare(scenario == 1 ? NULL : &p, scenario == 2 ? NULL : &bitmap);
        check(ret == expected_ret, "PREPARE_RETURN"); globals_unchanged("PREPARE_GLOBAL");
        if (!ret) metadata_equal(p, 1, 0x7531, bitmap);
        else check(p == old && bitmap == 0x7531 && live_count() == 0, "PREPARE_FAILURE_OWNER");
    } else if (!strcmp(flow, "legacy")) {
        if (scenario == 3 && count < SW_MAX_NR_DEV) phy_info[count] = expected_phy[count] = &foreign[count];
        ret = qca_ssdk_phy_info_init(count); check(ret == expected_ret, "LEGACY_RETURN");
        if (!ret) { metadata_equal(phy_info[count], count, expected_bmp[count], port_bmp[count]); expected_phy[count] = phy_info[count]; expected_bmp[count] = port_bmp[count]; }
        else check(live_count() == 0, "LEGACY_FAILURE_OWNER");
    } else if (!strcmp(flow, "publish")) {
        check(count <= SW_MAX_NR_DEV + 1, "PUBLISH_MODEL_DOMAIN");
        phy_info_t *p[SW_MAX_NR_DEV + 1] = {0}, *old[SW_MAX_NR_DEV + 1] = {0};
        a_uint32_t maps[SW_MAX_NR_DEV + 1] = {0}, saved[SW_MAX_NR_DEV + 1];
        for (unsigned d = 0; d < count; ++d) {
            maps[d] = 0x6600 + d;
            check(qca_ssdk_phy_info_prepare(&p[d], &maps[d]) == 0, "PUBLISH_PREPARATION");
        }
        if (scenario == 3 && count) p[count - 1] = NULL;
        if (scenario == 4 && count > 1) p[1] = p[0];
        memcpy(old, p, sizeof(p)); memcpy(saved, maps, sizeof(maps));
        ret = qca_ssdk_phy_info_publish(scenario == 1 ? NULL : p, scenario == 2 ? NULL : maps, count);
        check(ret == expected_ret, "PUBLISH_RETURN");
        if (!ret) {
            for (unsigned d = 0; d < count; ++d) {
                check(p[d] == NULL && phy_info[d] == old[d], "PUBLISH_CONSUME");
                metadata_equal(phy_info[d], d, 0x6600 + d, port_bmp[d]); expected_phy[d] = phy_info[d]; expected_bmp[d] = maps[d];
            }
            event("PUBLISH %u\n", count);
        } else check(memcmp(p, old, sizeof(p)) == 0 && memcmp(maps, saved, sizeof(maps)) == 0, "PUBLISH_FAILURE_OWNER");
    } else fail("FLOW");
    globals_unchanged("FINAL_GLOBAL"); event("RETURN %d\n", ret);
    cleanup_model(); event("END CLEAN\n");
    for (unsigned i = 0; i < event_count; ++i) fputs(events[i], stdout);
    return 0;
}
