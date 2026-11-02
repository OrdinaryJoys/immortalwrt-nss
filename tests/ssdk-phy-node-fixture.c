/* OF, providers and state below are models, not the kernel/firmware ABI. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
/* @TYPES@ */
/* @PORT_VALUES@ */
#define EPROBE_DEFER 517
#define IS_ENABLED(x) (x)
#define SSDK_ERROR(...) ((void)0)
#define SFP_I2C_BUS "SFP I2C Bus"
enum { PORTS = 4, MDIO_BUS_SLOTS = 4, I2C_OBJECTS = 16, MIDO_I2C_QCOM = 7 };
enum { SW_NODE, CONTAINER_NODE, PORT_NODE, MDIO_NODE, I2C_NODE, EXT_NODE, HANDLE_NODE };
struct device_node { unsigned kind, port, base, refs; };
struct property { int unused; };
struct device { unsigned identity, refs; };
struct i2c_adapter { struct device dev; };
struct mii_bus { unsigned identity; bool owned, allocated, registered; const char *name; };
struct qca_phy_priv { a_uint32_t sfp_rx_los_pin[SW_MAX_NR_PORT], sfp_tx_dis_pin[SW_MAX_NR_PORT],
    sfp_mod_present_pin[SW_MAX_NR_PORT], sfp_medium_pin[SW_MAX_NR_PORT]; };
typedef struct { struct { a_uint32_t wan_bmp, lan_bmp; } port_cfg; } ssdk_init_cfg;
typedef struct { a_uint8_t switch_netdev_port; a_bool_t switch_connected;
    a_uint8_t switch_dev_id, switch_cpu_port; } ssdk_netdev_switch_t;
struct metadata { unsigned address, reset, speed, duplex, access, fake, features, c45, combo; phy_dac_t dac; };
struct observation {
    unsigned trace[512][5], trace_count, bus_refs, alloc_count, register_count, free_count, ext_attempts, ext_count;
    unsigned adapter_refs[PORTS], table[MDIO_BUS_SLOTS];
    bool bus_allocated[I2C_OBJECTS], bus_registered[I2C_OBJECTS];
    struct metadata meta[SW_MAX_NR_DEV][SW_MAX_NR_PORT];
    struct qca_phy_priv private_state[SW_MAX_NR_DEV];
    ssdk_netdev_switch_t external_state[SSDK_NETDEV_SWITCH_NUM];
    ssdk_init_cfg cfg;
    sw_error_t result;
};
struct port_input {
    bool enabled, mdio, i2c_bus, i2c_mode, external, handle, force, dac, c45, combo;
    unsigned id, media, mac;
};
struct input { bool container, fallback, no_private, alias_nodes;
    unsigned ports, fault, fault_port, refs, repeats; struct port_input p[PORTS]; };
static struct input in;
static struct observation observed;
static struct device_node sw, container, port_nodes[PORTS], mdio_nodes[PORTS], fallback_node,
    i2c_nodes[PORTS], ext_nodes[PORTS], handle_nodes[PORTS];
static struct i2c_adapter adapters[PORTS];
static struct mii_bus borrowed_bus, i2c_buses[I2C_OBJECTS];
static unsigned active_port, scenarios;
static struct property property;
static const char *case_name;
static void demand(bool ok, const char *reason)
{
    if (!ok) { fprintf(stderr, "PHY_NODE:%s:%s\n", case_name, reason); exit(86); }
}
static void action(unsigned kind, unsigned a, unsigned b, unsigned c, unsigned d)
{
    demand(observed.trace_count < 512, "trace-capacity");
    unsigned *row = observed.trace[observed.trace_count++];
    row[0] = kind; row[1] = a; row[2] = b; row[3] = c; row[4] = d;
}
static void live(struct device_node *n) { demand(n && n->refs > n->base, "node-use-after-local-put"); }
static struct device_node *get(struct device_node *n) { n->refs++; return n; }
static void of_node_put(struct device_node *n)
{
    if (!n) return;
    demand(n->refs > n->base, "foreign-or-double-put"); n->refs--;
}
static const struct port_input *port_input(struct device_node *n)
{
    live(n); demand(n->kind == PORT_NODE && n->port < in.ports, "port-node-identity");
    return &in.p[n->port];
}
static bool fault(unsigned kind) { return in.fault == kind && in.fault_port == active_port; }
static struct device_node *of_get_child_by_name(struct device_node *parent, const char *name)
{
    if (parent == &sw) {
        demand(!strcmp(name, "qcom,port_phyinfo") && sw.refs == sw.base, "borrowed-switch");
        return in.container ? get(&container) : NULL;
    }
    const struct port_input *p = port_input(parent);
    demand(!strcmp(name, "switch_external"), "child-name");
    return p->external ? get(&ext_nodes[parent->port]) : NULL;
}
static struct device_node *of_get_next_available_child(struct device_node *parent, struct device_node *prev)
{
    live(parent); demand(parent == &container, "iterator-parent");
    unsigned start = prev ? prev->port + 1 : 0;
    if (prev) live(prev);
    struct device_node *next = NULL;
    for (unsigned i = start; i < in.ports; i++) if (in.p[i].enabled) {
        active_port = i; next = get(&port_nodes[i]); break;
    }
    of_node_put(prev); return next;
}
#define for_each_available_child_of_node(parent, child) \
    for ((child) = of_get_next_available_child((parent), NULL); (child); \
         (child) = of_get_next_available_child((parent), (child)))
static struct device_node *of_parse_phandle(struct device_node *n, const char *name, int index)
{
    live(n); demand(!index, "phandle-index");
    if (n->kind == EXT_NODE) {
        demand(!strcmp(name, "switch_handle"), "handle-property");
        unsigned p = in.alias_nodes ? 0 : n->port;
        return in.p[n->port].handle ? get(&handle_nodes[p]) : NULL;
    }
    const struct port_input *p = port_input(n);
    if (!strcmp(name, "mdiobus")) return p->mdio ? get(&mdio_nodes[in.alias_nodes ? 0 : n->port]) : NULL;
    demand(!strcmp(name, "i2c-bus"), "bus-property");
    return p->i2c_bus ? get(&i2c_nodes[in.alias_nodes ? 0 : n->port]) : NULL;
}
static hsl_reg_mode ssdk_switch_reg_access_mode_get(a_uint32_t id)
{ demand(id == 1, "provider-device"); return in.refs == 2 ? HSL_REG_MDIO : HSL_REG_LOCAL_BUS; }
static struct device_node *of_find_compatible_node(struct device_node *from, const char *type, const char *name)
{
    demand(!from && !type, "compatible-input");
    unsigned selector;
    if (!strcmp(name, "qcom,ipq40xx-mdio")) selector = 0;
    else if (!strcmp(name, "qcom,qca-mdio")) selector = 1;
    else { demand(!strcmp(name, "virtual,mdio-gpio"), "compatible-name"); selector = 2; }
    return in.fallback && selector == in.refs ? get(&fallback_node) : NULL;
}
static struct mii_bus *of_mdio_find_bus(struct device_node *n)
{
    live(n); demand(n->kind == MDIO_NODE, "mdio-identity");
    observed.bus_refs++; action(1, active_port, 0, 0, 0); return &borrowed_bus;
}
static sw_error_t ssdk_miibus_add(a_uint32_t id, struct mii_bus *b, a_uint32_t *index)
{
    demand(id == 1 && index && (!b || b == &borrowed_bus || b->owned), "bus-add-identity");
    action(2, active_port, b ? b->identity : 0, 0, 0);
    if (!b) return SW_BAD_PTR;
    if (fault(8)) return SW_OUT_OF_RANGE;
    for (unsigned i = 0; i < MDIO_BUS_SLOTS; i++) if (observed.table[i] == b->identity) { *index = i; return SW_OK; }
    for (unsigned i = 0; i < MDIO_BUS_SLOTS; i++) if (!observed.table[i]) {
        observed.table[i] = b->identity; *index = i; return SW_OK;
    }
    return SW_OUT_OF_RANGE;
}
static struct i2c_adapter *of_find_i2c_adapter_by_node(struct device_node *n)
{
    live(n); demand(n->kind == I2C_NODE, "i2c-node-identity");
    action(3, active_port, n->port, 0, 0);
    if (fault(5)) return NULL;
    adapters[n->port].dev.refs++; return &adapters[n->port];
}
static struct mii_bus *mdio_i2c_alloc(struct device *dev, struct i2c_adapter *adpt, int protocol)
{
    demand(dev == &adpt->dev && protocol == MIDO_I2C_QCOM && dev->refs > 10, "allocator-input");
    action(4, active_port, dev->identity, 0, 0);
    if (fault(6)) return NULL;
    demand(observed.alloc_count < I2C_OBJECTS, "bus-object-capacity");
    struct mii_bus *b = &i2c_buses[observed.alloc_count++]; b->allocated = true; return b;
}
static int of_mdiobus_register(struct mii_bus *b, struct device_node *n)
{
    live(n); demand(n->kind == I2C_NODE && b->owned && b->allocated && !b->registered &&
        b->name && !strcmp(b->name, SFP_I2C_BUS), "register-input");
    observed.register_count++; action(5, active_port, b->identity, 0, 0);
    if (fault(7)) return -5;
    b->registered = true; return 0;
}
static void mdiobus_free(struct mii_bus *b)
{
    demand(b && b->owned && b->allocated && !b->registered, "free-owned-unpublished-bus");
    b->allocated = false; observed.free_count++; action(6, active_port, b->identity, 0, 0);
}
static int of_get_named_gpio(struct device_node *n, const char *name, int index)
{
    live(n); demand(!index, "gpio-index");
    if (n->kind == MDIO_NODE) { demand(!strcmp(name, "phy-reset-gpio"), "reset-name"); return in.refs == 0 ? 17 : in.refs == 1 ? 0 : -EPROBE_DEFER; }
    port_input(n);
    demand(!strcmp(name, "sfp_rx_los_pin") || !strcmp(name, "sfp_tx_dis_pin") ||
        !strcmp(name, "sfp_mod_present_pin") || !strcmp(name, "sfp_medium_pin"), "sfp-gpio-name");
    return in.refs == 0 ? 23 : in.refs == 1 ? -EPROBE_DEFER : 0;
}
static struct qca_phy_priv *ssdk_phy_priv_data_get(a_uint32_t id)
{ demand(id == 1, "private-device"); return in.no_private ? NULL : &observed.private_state[id]; }
static struct property *of_find_property(struct device_node *n, const char *name, int *length)
{
    const struct port_input *p = port_input(n); demand(!strcmp(name, "phy_dac"), "find-property-name");
    if (length) *length = 8;
    return p->dac ? &property : NULL;
}
static int of_property_read_u32_array(struct device_node *n, const char *name, a_uint32_t *values, size_t count)
{
    port_input(n); demand(!strcmp(name, "phy_dac") && count == 2, "dac-array-input");
    if (fault(2)) return -EINVAL;
    values[0] = 0x101 + n->port; values[1] = 0x202 + n->port; return 0;
}
static int of_property_read_u32(struct device_node *n, const char *name, a_uint32_t *value)
{
    live(n); demand(value != NULL, "property-output");
    if (n->kind == HANDLE_NODE) {
        demand(!strcmp(name, "device_id"), "handle-read");
        if (fault(9)) return -EINVAL;
        *value = 2; return 0;
    }
    if (n->kind == EXT_NODE) { demand(!strcmp(name, "switch_cpu_port"), "external-read"); *value = 5; return 0; }
    const struct port_input *p = port_input(n);
    if (!strcmp(name, "port_id")) { if (fault(1)) return -EINVAL; *value = p->id; return 0; }
    if (!strcmp(name, "phy_address")) { *value = 3 + n->port; return 0; }
    if (!strcmp(name, "phy_i2c_address")) { if (fault(3)) return -EINVAL; *value = 0x56 + n->port; return 0; }
    if (!strcmp(name, "forced-speed")) { if (!p->force) return -EINVAL; *value = 1000; return 0; }
    demand(!strcmp(name, "forced-duplex"), "port-u32-name");
    if (!p->force) return -EINVAL;
    *value = 1; return 0;
}
static bool of_property_read_bool(struct device_node *n, const char *name)
{
    const struct port_input *p = port_input(n);
    if (!strcmp(name, "phy-i2c-mode")) return p->i2c_mode;
    if (!strcmp(name, "ethernet-phy-ieee802.3-c45")) return p->c45;
    demand(!strcmp(name, "ethernet-phy-combo"), "port-bool-name"); return p->combo;
}
static int of_property_read_string(struct device_node *n, const char *name, const char **value)
{
    const struct port_input *p = port_input(n);
    if (!strcmp(name, "port_mac_sel")) { if (!p->mac) return -EINVAL; *value = p->mac == 1 ? "QGMAC_PORT" : "XGMAC_PORT"; return 0; }
    demand(!strcmp(name, "media-type"), "port-string-name");
    if (!p->media) return -EINVAL;
    *value = p->media == 1 ? "sfp" : "sfp_sgmii"; return 0;
}
static struct metadata *cell(a_uint32_t dev, a_uint32_t port)
{ demand(dev == 1 && port < SW_MAX_NR_PORT, "metadata-owner"); return &observed.meta[dev][port]; }
#define SETTER(name, field, type, code) \
static void name(a_uint32_t dev, a_uint32_t port, type value) \
{ cell(dev, port)->field = value; action(code, dev, port, value, 0); }
SETTER(hsl_phy_address_init, address, a_uint32_t, 10)
SETTER(hsl_port_phy_reset_gpio_set, reset, a_uint32_t, 11)
SETTER(hsl_port_force_speed_set, speed, a_uint32_t, 12)
SETTER(hsl_port_force_duplex_set, duplex, a_uint8_t, 13)
SETTER(hsl_port_phy_access_type_set, access, a_uint8_t, 14)
SETTER(qca_ssdk_phy_mdio_fake_address_set, fake, a_uint32_t, 15)
SETTER(hsl_port_phy_c45_capability_set, c45, a_bool_t, 16)
SETTER(hsl_port_phy_combo_capability_set, combo, a_bool_t, 17)
static void hsl_port_phy_dac_set(a_uint32_t dev, a_uint32_t port, phy_dac_t value)
{ cell(dev, port)->dac = value; action(18, dev, port, value.mdac, value.edac); }
static sw_error_t hsl_port_feature_set(a_uint32_t dev, a_uint32_t port, phy_features_t value)
{ cell(dev, port)->features |= value; action(19, dev, port, value, 0); return SW_OK; }
static sw_error_t sfp_phy_init(a_uint32_t dev, a_uint32_t port, a_uint32_t index)
{ cell(dev, port); action(20, dev, port, index, 0); return fault(10) ? SW_FAIL : SW_OK; }
static a_uint32_t ssdk_dts_netdev_switch_alloc(ssdk_netdev_switch_t **out)
{
    demand(out != NULL && port_nodes[active_port].refs > port_nodes[active_port].base, "external-active-port");
    observed.ext_attempts++; action(21, active_port, 0, 0, 0);
    if (fault(4) || observed.ext_count == SSDK_NETDEV_SWITCH_NUM) return SSDK_NETDEV_SWITCH_NUM;
    *out = &observed.external_state[observed.ext_count++]; return 0;
}
static unsigned safe_bit(unsigned n) { demand(n < 32, "bit-boundary"); return 1u << n; }
#define BIT(n) safe_bit(n)
/* @FUNCTIONS@ */
static void reset(void)
{
    memset(&observed, 0, sizeof(observed));
    memset(observed.meta, 0xa5, sizeof(observed.meta));
    memset(observed.private_state, 0x3c, sizeof(observed.private_state));
    observed.cfg.port_cfg.wan_bmp = in.refs == 2 ? 1u << 14 : 0;
    sw = (struct device_node){SW_NODE, 0, 7, 7};
    container = (struct device_node){CONTAINER_NODE, 0, 3, 3};
    fallback_node = (struct device_node){MDIO_NODE, 0, in.refs, in.refs};
    for (unsigned p = 0; p < PORTS; p++) {
        port_nodes[p] = (struct device_node){PORT_NODE, p, in.refs + 1, in.refs + 1};
        mdio_nodes[p] = (struct device_node){MDIO_NODE, p, in.refs + 2, in.refs + 2};
        i2c_nodes[p] = (struct device_node){I2C_NODE, p, in.refs + 3, in.refs + 3};
        ext_nodes[p] = (struct device_node){EXT_NODE, p, in.refs + 4, in.refs + 4};
        handle_nodes[p] = (struct device_node){HANDLE_NODE, p, in.refs + 5, in.refs + 5};
        adapters[p].dev = (struct device){100 + p, 10};
    }
    borrowed_bus = (struct mii_bus){.identity = 1};
    for (unsigned i = 0; i < I2C_OBJECTS; i++) i2c_buses[i] = (struct mii_bus){.identity = 10 + i, .owned = true};
    active_port = 0;
}
static void snapshot(struct observation *out)
{
    for (unsigned p = 0; p < PORTS; p++) observed.adapter_refs[p] = adapters[p].dev.refs;
    for (unsigned i = 0; i < I2C_OBJECTS; i++) {
        observed.bus_allocated[i] = i2c_buses[i].allocated;
        observed.bus_registered[i] = i2c_buses[i].registered;
    }
    memcpy(out, &observed, sizeof(*out));
}
static void node_balance(void)
{
    demand(sw.refs == sw.base && container.refs == container.base, "container-lease-balance");
    demand(fallback_node.refs == fallback_node.base, "mdio-lease-balance");
    for (unsigned p = 0; p < PORTS; p++) {
        demand(port_nodes[p].refs == port_nodes[p].base, "iterator-lease-balance");
        demand(mdio_nodes[p].refs == mdio_nodes[p].base, "mdio-lease-balance");
        demand(i2c_nodes[p].refs == i2c_nodes[p].base, "i2c-lease-balance");
        demand(ext_nodes[p].refs == ext_nodes[p].base, "external-lease-balance");
        demand(handle_nodes[p].refs == handle_nodes[p].base, "handle-lease-balance");
    }
}
static sw_error_t expected_return(void)
{
    if (!in.container) return SW_NOT_FOUND;
    unsigned external = 0;
    for (unsigned p = 0; p < in.ports; p++) if (in.p[p].enabled) {
        if (in.fault_port == p && (in.fault == 1 || (in.fault == 2 && in.p[p].dac))) return SW_BAD_VALUE;
#ifdef IN_PHY_I2C_MODE
        if (in.fault_port == p && in.fault == 3 && in.p[p].i2c_mode) return SW_BAD_VALUE;
#endif
        if (in.p[p].external && ((in.fault_port == p && in.fault == 4) || external++ == SSDK_NETDEV_SWITCH_NUM)) return SW_NO_RESOURCE;
    }
    return SW_OK;
}
static void scenario(const char *name, bool old)
{
    case_name = name;
    reset();
    for (unsigned n = 0; n < in.repeats; n++) observed.result = baseline_ssdk_dt_parse_phy_info(&sw, 1, &observed.cfg);
    struct observation expected;
    snapshot(&expected);
    reset();
    for (unsigned n = 0; n < in.repeats; n++) {
        observed.result = old ? baseline_ssdk_dt_parse_phy_info(&sw, 1, &observed.cfg) : ssdk_dt_parse_phy_info(&sw, 1, &observed.cfg);
        /* Only the first execution has a fresh external table for the independent return oracle. */
        if (!n) demand(observed.result == expected_return(), "return-value");
        node_balance();
    }
    struct observation actual;
    snapshot(&actual);
    demand(!memcmp(&expected, &actual, sizeof(actual)), "non-of-state-changed");
    scenarios++;
}
static void layout(unsigned which)
{
    const unsigned masks[] = {0, 1, 0x42, 0x8c, 0x38, 0xff, 0x3f, 0xba};
    unsigned m = masks[which];
    in.fallback = m & 2;
    for (unsigned p = 0; p < PORTS; p++) {
        unsigned ids[] = {1, SW_MAX_NR_PORT - 1, 0, 3};
        in.p[p] = (struct port_input){ .enabled = in.refs != 1 || p % 2 == 0,
            .mdio = m & 1, .i2c_bus = m & 4, .i2c_mode = m & 8, .external = m & 16,
            .handle = m & 32, .force = m & 64, .dac = m & 128, .c45 = p % 2,
            .combo = (which + p) % 3 == 0, .id = ids[p], .media = (which + p) % 3,
            .mac = (which + p) % 3 };
    }
}
static void probe(const char *name, bool old)
{
    in = (struct input){.container = true, .ports = 1, .repeats = 1};
    in.p[0] = (struct port_input){.enabled = true, .id = 1};
    if (!strcmp(name, "mdio")) in.p[0].mdio = true;
    else if (!strcmp(name, "i2c")) in.p[0].i2c_bus = true;
    else if (!strcmp(name, "external")) in.p[0].external = true;
    else if (!strcmp(name, "handle")) { in.p[0].external = true; in.p[0].handle = true; }
    else if (!strcmp(name, "external-failure")) { in.p[0].external = true; in.fault = 4; }
    else if (!strcmp(name, "i2c-address-failure")) {
        in.p[0].mdio = in.p[0].i2c_bus = in.p[0].i2c_mode = true; in.fault = 3;
    } else if (!strcmp(name, "second-bad-port")) {
        in.ports = 2; in.p[0].mdio = true;
        in.p[1] = (struct port_input){.enabled = true, .id = 15}; in.fault = 1; in.fault_port = 1;
    } else demand(false, "unknown-probe");
    scenario(name, old);
}
int main(int argc, char **argv)
{
    if (argc == 3) probe(argv[2], !strcmp(argv[1], "old"));
    else if (argc == 1) {
        for (unsigned l = 0; l < 8; l++)
        for (unsigned count = 0; count <= PORTS; count++)
        for (unsigned f = 0; f <= 10; f++)
        for (unsigned p = 0; p < PORTS; p++)
        for (unsigned refs = 0; refs < 3; refs++) {
            in = (struct input){.container = true, .ports = count, .fault = f, .fault_port = p,
                .refs = refs, .repeats = 1 + refs % 2, .alias_nodes = refs == 1, .no_private = refs == 2};
            layout(l); scenario("matrix", false);
        }
        in = (struct input){.repeats = 1}; scenario("missing-container", false);
        const char *names[] = {"mdio", "i2c", "external", "handle", "external-failure", "i2c-address-failure", "second-bad-port"};
        for (unsigned i = 0; i < 7; i++) probe(names[i], false);
    } else return 2;
    printf("{\"scenarios\":%u,\"failures\":0,\"feature_profile\":%u,\"provider_retirement_unverified\":true}\n", scenarios, (unsigned)TEST_FEATURES);
    return 0;
}
