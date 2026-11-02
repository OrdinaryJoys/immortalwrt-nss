/* Reduced OF/provider models; complete production functions are inserted below. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
/* @TYPES@ */
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#ifndef TEST_KERNEL
#define TEST_KERNEL KERNEL_VERSION(6,18,38)
#endif
#define LINUX_VERSION_CODE TEST_KERNEL
#define SSDK_ERROR(...) ((void)0)
#define SSDK_INFO(...) ((void)0)
typedef a_uint32_t __be32;
struct device_node { unsigned base, refs, kind, index; };
struct mii_bus { unsigned identity; };
struct qca_mdio_data { struct mii_bus *mii_bus; };
struct device { unsigned base, refs; };
struct platform_device { struct device dev; };
typedef struct { struct { a_uint32_t wan_bmp, lan_bmp; } port_cfg; } ssdk_init_cfg;
static struct device_node sw, default_node, legacy_node, children[24];
static struct platform_device platform;
static struct mii_bus bus = {17}, foreign_bus = {29};
static struct qca_mdio_data mdio_data;
struct input {
    bool switch_arg, explicit_node, fallback_node, platform_found, data_found, bus_found;
    bool emulation, legacy_found, alternating;
    unsigned child_count, refs, initial_wan;
    sw_error_t add_error, phy_error;
};
struct metadata { unsigned address, c45, features; };
struct observation {
    unsigned operations[256][4], count, platform_refs, bus_refs, table_id;
    struct metadata meta[SW_MAX_NR_PORT];
    ssdk_init_cfg cfg;
    sw_error_t result;
};
static struct input in;
static struct observation observed;
static unsigned bus_refs;
static struct mii_bus *table;
static const char *case_name;
static unsigned scenarios;
static void demand(bool condition, const char *reason)
{
    if (!condition) { fprintf(stderr, "MDIO_NODE:%s:%s\n", case_name, reason); exit(86); }
}
static void op(unsigned kind, unsigned a, unsigned b, unsigned c)
{
    demand(observed.count < 256, "trace-capacity");
    unsigned *row = observed.operations[observed.count++];
    row[0] = kind; row[1] = a; row[2] = b; row[3] = c;
}
static struct device_node *get(struct device_node *n) { n->refs++; return n; }
static void live(struct device_node *n) { demand(n && n->refs > n->base, "node-use-after-local-put"); }
static void of_node_put(struct device_node *n)
{
    if (!n) return;
    demand(n->refs > n->base, "foreign-or-double-node-put");
    n->refs--;
}
static struct device_node *of_parse_phandle(struct device_node *n, const char *name, int index)
{
    demand(n == &sw && n->refs == n->base && !strcmp(name, "mdio-bus") && !index, "phandle-input");
    return in.explicit_node ? get(&default_node) : NULL;
}
static hsl_reg_mode ssdk_switch_reg_access_mode_get(a_uint32_t id)
{
    demand(id == 1, "device-identity");
    return in.refs == 2 ? HSL_REG_MDIO : HSL_REG_LOCAL_BUS;
}
static struct device_node *of_find_compatible_node(struct device_node *from,
    const char *type, const char *compatible)
{
    demand(!from && !type, "compatible-lookup-input");
    unsigned selected;
    if (!strcmp(compatible, "qcom,ipq40xx-mdio")) selected = 0;
    else if (!strcmp(compatible, "qcom,qca-mdio")) selected = 1;
    else { demand(!strcmp(compatible, "virtual,mdio-gpio"), "compatible-lookup-name"); selected = 2; }
    op(10, selected, 0, 0);
    bool match = in.refs == 2 ? selected == 2 : selected == (in.refs == 1 ? 1u : 0u);
    return in.fallback_node && match ? get(&default_node) : NULL;
}
static struct mii_bus *of_mdio_find_bus(struct device_node *n)
{
    live(n); demand(n == &default_node, "bus-lookup-identity");
    op(1, 0, 0, 0);
    if (!in.bus_found) return NULL;
    bus_refs++;
    return &bus;
}
static struct platform_device *of_find_device_by_node(struct device_node *n)
{
    live(n); demand(n == &default_node, "platform-lookup-identity");
    op(2, 0, 0, 0);
    if (!in.platform_found) return NULL;
    platform.dev.refs++;
    return &platform;
}
static void *dev_get_drvdata(struct device *dev)
{
    demand(dev == &platform.dev && dev->refs == dev->base + 1, "provider-not-held");
    op(3, 0, 0, 0);
    if (!in.data_found) return NULL;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6,1,0)
    return in.bus_found ? &bus : NULL;
#else
    return &mdio_data;
#endif
}
static void put_device(struct device *dev)
{
    demand(dev == &platform.dev && dev->refs > dev->base, "foreign-provider-put");
    dev->refs--;
}
static sw_error_t ssdk_miibus_add(a_uint32_t id, struct mii_bus *b, a_uint32_t *index)
{
    demand(id == 1 && index && (!b || b == &bus), "bus-add-identity");
    op(4, b ? b->identity : 0, (unsigned)in.add_error, 0);
    if (!b) return SW_BAD_PTR;
    if (in.add_error) return in.add_error;
    table = b; *index = 2;
    return SW_OK;
}
static bool ssdk_is_emulation(a_uint32_t id) { demand(id == 1, "emulation-id"); return in.emulation; }
static sw_error_t ssdk_dt_parse_phy_info(struct device_node *n, a_uint32_t id, ssdk_init_cfg *cfg)
{
    demand(n == &sw && id == 1 && cfg == &observed.cfg, "phy-boundary-input");
    op(5, (unsigned)in.phy_error, 0, 0);
    return in.phy_error; /* Explicit dependency boundary, not a tested PHY implementation. */
}
static struct device_node *of_find_node_by_name(struct device_node *from, const char *name)
{
    demand(!from && !strcmp(name, "mdio"), "legacy-node-input");
    op(6, 0, 0, 0);
    return in.legacy_found ? get(&legacy_node) : NULL;
}
static struct device_node *of_get_next_available_child(struct device_node *parent, struct device_node *prev)
{
    live(parent); demand(parent == &legacy_node, "iterator-parent");
    unsigned start = prev ? prev->index + 1 : 0;
    if (prev) { live(prev); demand(prev->kind == 3, "iterator-child"); }
    struct device_node *next = NULL;
    for (unsigned i = start; i < in.child_count; i++)
        if (!in.alternating || i % 3 != 1) { next = get(&children[i]); break; }
    of_node_put(prev);
    return next;
}
#define for_each_available_child_of_node(parent, child) \
    for ((child) = of_get_next_available_child((parent), NULL); (child); \
         (child) = of_get_next_available_child((parent), (child)))
static __be32 values[24];
static const void *of_get_property(struct device_node *n, const char *name, a_uint32_t *len)
{
    live(n); demand(n->kind == 3 && n->index < in.child_count, "property-input");
    if (!strcmp(name, "reg")) {
        *len = 4; return n->index % 4 == 2 ? NULL : &values[n->index];
    }
    demand(!strcmp(name, "compatible"), "property-name");
    *len = 4; return n->index % 2 ? &values[n->index] : NULL;
}
static a_uint32_t be32_to_cpup(const __be32 *value)
{
    demand(value >= values && value < values + 24, "property-value");
    return *value; /* Host stores modeled values in CPU order. */
}
static void hsl_phy_address_init(a_uint32_t id, a_uint32_t port, a_uint32_t value)
{
    demand(id == 1 && port < SW_MAX_NR_PORT, "metadata-address");
    observed.meta[port].address = value; op(7, id, port, value);
}
static void hsl_port_phy_c45_capability_set(a_uint32_t id, a_uint32_t port, a_bool_t value)
{
    demand(id == 1 && port < SW_MAX_NR_PORT, "metadata-c45");
    observed.meta[port].c45 = value; op(8, id, port, value);
}
static sw_error_t hsl_port_feature_set(a_uint32_t id, a_uint32_t port, phy_features_t value)
{
    demand(id == 1 && port < SW_MAX_NR_PORT, "metadata-feature");
    observed.meta[port].features |= value; op(9, id, port, value); return SW_OK;
}
static unsigned safe_bit(unsigned value) { demand(value < 32, "bitmap-shift"); return 1u << value; }
#define BIT(value) safe_bit(value)
/* @FUNCTIONS@ */
static void reset(void)
{
    memset(&observed, 0, sizeof(observed));
    for (unsigned i = 0; i < SW_MAX_NR_PORT; i++)
        observed.meta[i] = (struct metadata){0xabc0 + i, 0, 0x80};
    observed.cfg.port_cfg.wan_bmp = in.initial_wan;
    sw = (struct device_node){7, 7, 0, 0};
    default_node = (struct device_node){in.refs, in.refs, 1, 0};
    legacy_node = (struct device_node){in.refs + 1, in.refs + 1, 2, 0};
    for (unsigned i = 0; i < 24; i++) {
        children[i] = (struct device_node){in.refs + 2, in.refs + 2, 3, i};
        values[i] = 100 + i;
    }
    platform.dev = (struct device){11, 11};
    mdio_data.mii_bus = in.bus_found ? &bus : NULL;
    table = &foreign_bus; bus_refs = 0;
}
static struct observation snapshot(void)
{
    observed.platform_refs = platform.dev.refs;
    observed.bus_refs = bus_refs;
    observed.table_id = table->identity;
    return observed;
}
static void node_balance(void)
{
    demand(default_node.refs == default_node.base && legacy_node.refs == legacy_node.base &&
        sw.refs == sw.base, "node-lease-balance");
    for (unsigned i = 0; i < 24; i++) demand(children[i].refs == children[i].base, "child-lease-balance");
}
static void scenario(const char *name, bool legacy, bool check_old)
{
    case_name = name;
    reset();
    if (legacy) baseline_ssdk_dt_parse_mdio(1, &sw, &observed.cfg);
    else observed.result = baseline_ssdk_dt_parse_default_mdio_bus(in.switch_arg ? &sw : NULL, 1);
    struct observation expected = snapshot();
    reset();
    if (legacy) {
        if (check_old) baseline_ssdk_dt_parse_mdio(1, &sw, &observed.cfg);
        else ssdk_dt_parse_mdio(1, &sw, &observed.cfg);
    } else {
        observed.result = check_old ? baseline_ssdk_dt_parse_default_mdio_bus(in.switch_arg ? &sw : NULL, 1) :
            ssdk_dt_parse_default_mdio_bus(in.switch_arg ? &sw : NULL, 1);
        sw_error_t result;
        if (in.switch_arg && in.explicit_node) result = in.bus_found ? in.add_error : SW_BAD_PTR;
        else if (!in.fallback_node || !in.platform_found) result = SW_NOT_FOUND;
#if LINUX_VERSION_CODE < KERNEL_VERSION(6,1,0)
        else if (!in.data_found) result = SW_NOT_FOUND;
#endif
        else result = in.data_found && in.bus_found ? in.add_error : SW_BAD_PTR;
        demand(observed.result == result, "return-value");
    }
    struct observation actual = snapshot();
    demand(!memcmp(&expected, &actual, sizeof(actual)), "non-of-state-changed");
    node_balance();
    scenarios++;
}
static void probe(const char *name, bool old)
{
    memset(&in, 0, sizeof(in));
    in = (struct input){ .switch_arg = true, .explicit_node = true, .fallback_node = true,
        .platform_found = true, .data_found = true, .bus_found = true, .phy_error = SW_NOT_FOUND };
    bool legacy = false;
    if (!strcmp(name, "explicit")) { }
    else if (!strcmp(name, "fallback")) in.explicit_node = false;
    else if (!strcmp(name, "fallback-missing")) { in.explicit_node = false; in.platform_found = false; }
    else if (!strcmp(name, "legacy-empty")) { legacy = true; in.legacy_found = true; }
    else if (!strcmp(name, "legacy-break")) { legacy = true; in.legacy_found = true; in.child_count = 20; }
    else if (!strcmp(name, "add-failure")) in.add_error = SW_OUT_OF_RANGE;
    else demand(false, "unknown-probe");
    scenario(name, legacy, old);
}
int main(int argc, char **argv)
{
    if (argc == 3) probe(argv[2], !strcmp(argv[1], "old"));
    else if (argc == 1) {
        sw_error_t errors[] = {SW_OK, SW_OUT_OF_RANGE, SW_FAIL};
        for (unsigned bits = 0; bits < 64; bits++)
        for (unsigned error = 0; error < 3; error++)
        for (unsigned refs = 0; refs < 3; refs++) {
            in = (struct input){ .switch_arg = bits & 1, .explicit_node = bits & 2,
                .fallback_node = bits & 4, .platform_found = bits & 8, .data_found = bits & 16,
                .bus_found = bits & 32, .refs = refs, .add_error = errors[error] };
            scenario("default-matrix", false, false);
        }
        unsigned counts[] = {0, 1, 2, 14, 15, 16, 20};
        sw_error_t phy_errors[] = {SW_OK, SW_NOT_FOUND, SW_BAD_VALUE};
        for (unsigned emulate = 0; emulate < 2; emulate++)
        for (unsigned default_ok = 0; default_ok < 2; default_ok++)
        for (unsigned phy = 0; phy < 3; phy++)
        for (unsigned found = 0; found < 2; found++)
        for (unsigned count = 0; count < 7; count++)
        for (unsigned wan = 0; wan < 2; wan++)
        for (unsigned alternating = 0; alternating < 2; alternating++) {
            in = (struct input){ .switch_arg = true, .explicit_node = true, .bus_found = true,
                .emulation = emulate, .add_error = default_ok ? SW_OK : SW_FAIL,
                .phy_error = phy_errors[phy], .legacy_found = found, .child_count = counts[count],
                .initial_wan = wan ? 0x4000 : 0, .alternating = alternating, .refs = count % 3 };
            scenario("legacy-matrix", true, false);
        }
        const char *names[] = {"explicit", "fallback", "fallback-missing", "legacy-empty", "legacy-break", "add-failure"};
        for (unsigned i = 0; i < 6; i++) probe(names[i], false);
    } else return 2;
    printf("{\"scenarios\":%u,\"failures\":0,\"provider_retirement_unverified\":true}\n", scenarios);
    return 0;
}
