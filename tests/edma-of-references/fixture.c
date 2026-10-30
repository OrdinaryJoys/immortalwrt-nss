#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define NSS_DP_IPQ807X 1
#define NSS_DP_SUCCESS 0
#define NSS_DP_FAILURE -1
#define __rcu
#define __iomem
#define IRQF_SHARED 1
#define WARN_ON(x) fixture_warn(!!(x))
#define ASSERT_RTNL() check(rtnl_held, "rtnl-held")
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define netdev_dbg(...) ((void)0)
#define rcu_access_pointer(p) (p)
#define rcu_assign_pointer(p, v) ((p) = (v))
typedef uint64_t dma_addr_t;
typedef int irqreturn_t;
typedef struct {
    unsigned unused;
} spinlock_t;
struct net_device {
    bool dummy, freed;
    unsigned needed_headroom;
    struct nss_dp_dev *priv;
};
struct napi_struct {
    struct net_device *dev;
    bool added, enabled;
};
struct device_node {
    const char *name;
    unsigned refs;
};
struct device {
    unsigned refs;
    void *data;
};
struct platform_device {
    struct device dev;
};
struct resource {
    unsigned long start, end;
};
struct sk_buff {
    int unused;
};
struct nss_dp_data_plane_ctx {
    struct net_device *dev;
};
struct nss_dp_dev {
    unsigned macid;
    struct net_device *netdev;
};
static struct nss_dp_data_plane_ctx dp_global_data_plane_ctx[6];
static unsigned checks, cases, node_gets, node_puts, device_gets, device_puts, warnings;
static unsigned fail_at, stage_calls, node_owned, device_owned, region_owned, map_owned;
static unsigned dummy_owned, ring_owned, irq_owned, region_releases, map_releases, drvdata_writes;
static unsigned dma_uses, irq_uses, port_disables, mmio_uses;
static bool dynamic_nodes = true, rtnl_held, foreign_region, trace_on;
static struct device_node node = {"edma", 5};
static struct platform_device pdev = {{7, NULL}}, foreign_pdev = {{11, NULL}};
static struct resource resource = {0x1000, 0x80fff};
static unsigned foreign_marker;
static uint32_t registers[0x80000 / 4];
static struct net_device *dummy;
static void check(bool ok, const char *why) {
    ++checks;
    if (!ok) {
        fprintf(stderr, "EDMA_OF016 %s\n", why);
        exit(86);
    }
}
static bool fixture_warn(bool v) {
    warnings += v;
    return v;
}
static bool fail(void) { return ++stage_calls == fail_at; }
static void event(const char *s) {
    if (trace_on)
        puts(s);
}
static void use_device(void) {
    check(device_owned == 1 && pdev.dev.refs == 8, "device-live-last-use");
}
static void use_node(void) {
    check(node_owned == 1 && node.refs == (dynamic_nodes ? 6U : 5U), "node-live-last-use");
}
static void rtnl_lock(void) {
    check(!rtnl_held, "no-recursive-rtnl");
    rtnl_held = true;
}
static void rtnl_unlock(void) {
    check(rtnl_held, "rtnl-balanced");
    rtnl_held = false;
}
static void synchronize_net(void) { ASSERT_RTNL(); }
static void *netdev_priv(struct net_device *d) {
    check(d && !d->freed && d->priv, "port-live");
    return d->priv;
}
static unsigned nss_dp_get_idx_from_macid(unsigned id) { return id - 1; }

/* HEADERS */

struct edma_hw edma_hw;
/* PROTOTYPES */
static struct device_node *of_find_node_by_name(struct device_node *from, const char *name) {
    check(!from && !strcmp(name, "edma"), "node-get-arguments");
    if (fail())
        return NULL;
    check(!node_owned, "node-get-not-overwritten");
    node_owned = 1;
    ++node_gets;
    if (dynamic_nodes)
        ++node.refs;
    event("NODE_GET");
    return &node;
}
static struct platform_device *of_find_device_by_node(struct device_node *n) {
    check(n == &node, "device-get-node");
    use_node();
    if (fail())
        return NULL;
    check(!device_owned, "device-get-not-overwritten");
    device_owned = 1;
    ++device_gets;
    ++pdev.dev.refs;
    event("DEVICE_GET");
    return &pdev;
}
static void put_device(struct device *d) {
    check(d == &pdev.dev && device_owned == 1 && pdev.dev.refs == 8, "put-device-owned");
    check(!irq_owned && !ring_owned && !map_owned && !region_owned && !dummy_owned,
          "device-put-after-last-use");
    check(!edma_hw.pdev && !edma_hw.device_node, "detach-before-put");
    --device_owned;
    --pdev.dev.refs;
    ++device_puts;
    event("DEVICE_PUT");
}
static void of_node_put(struct device_node *n) {
    check(n == &node && node_owned == 1, "put-node-owned");
    check(!irq_owned && !ring_owned && !map_owned && !region_owned && !dummy_owned,
          "node-put-after-last-use");
    check(!edma_hw.pdev && !edma_hw.device_node, "detach-before-put");
    --node_owned;
    if (dynamic_nodes)
        --node.refs;
    ++node_puts;
    event("NODE_PUT");
}
static int of_address_to_resource(struct device_node *n, unsigned index, struct resource *r) {
    check(n == &node && !index, "address-arguments");
    use_node();
    if (fail())
        return -1;
    *r = resource;
    return 0;
}
static int of_property_read_u32(struct device_node *n, const char *name, uint32_t *v) {
    check(n == &node, "property-node");
    use_node();
    if (fail())
        return -1;
    const char *names[] = {"qcom,txdesc-ring-start", "qcom,txdesc-rings",
                           "qcom,txcmpl-ring-start", "qcom,txcmpl-rings",
                           "qcom,rxfill-ring-start", "qcom,rxfill-rings",
                           "qcom,rxdesc-ring-start", "qcom,rxdesc-rings"};
    unsigned values[] = {23, 1, 7, 1, 7, 1, 15, 1};
    unsigned i;
    for (i = 0; i < 8; ++i)
        if (!strcmp(name, names[i]))
            break;
    check(i < 8, "known-property");
    *v = values[i];
    return 0;
}
static unsigned long resource_size(struct resource *r) { return r->end - r->start + 1; }
static struct resource *request_mem_region(unsigned long start, unsigned long size,
                                           const char *name) {
    check(start == resource.start && size == resource_size(&resource) && !strcmp(name, "edma"),
          "region-arguments");
    if (fail() || foreign_region)
        return NULL;
    check(!region_owned, "region-acquire-once");
    region_owned = 1;
    event("REGION_GET");
    return &resource;
}
static void release_mem_region(unsigned long start, unsigned long size) {
    check(!foreign_region, "foreign-region-not-released");
    check(region_owned == 1 && !map_owned && start == resource.start &&
              size == resource_size(&resource),
          "release-acquired-region-only");
    region_owned = 0;
    ++region_releases;
    event("REGION_RELEASE");
}
static void *ioremap(unsigned long start, unsigned long size) {
    check(region_owned && start == resource.start && size == resource_size(&resource),
          "map-owned-region");
    if (fail())
        return NULL;
    map_owned = 1;
    event("MAP_GET");
    return registers;
}
static void iounmap(void *p) {
    check(p == registers && map_owned == 1, "unmap-owned");
    map_owned = 0;
    ++map_releases;
    event("MAP_RELEASE");
}
static void *platform_get_drvdata(struct platform_device *p) {
    check(p == &pdev, "drvdata-device");
    use_device();
    return p->dev.data;
}
static void platform_set_drvdata(struct platform_device *p, void *data) {
    check(p == &pdev, "drvdata-device");
    use_device();
    if (!data)
        check(p->dev.data == &edma_hw, "foreign-drvdata-preserved");
    p->dev.data = data;
    ++drvdata_writes;
    event(data ? "DRVDATA_SET" : "DRVDATA_CLEAR");
}
static struct net_device *alloc_netdev_dummy(unsigned n) {
    check(!n, "dummy-size");
    if (fail())
        return NULL;
    check(!dummy_owned, "dummy-acquire-once");
    dummy = calloc(1, sizeof(*dummy));
    check(dummy != NULL, "host-allocation");
    dummy->dummy = true;
    dummy_owned = 1;
    event("DUMMY_GET");
    return dummy;
}
static void free_netdev(struct net_device *d) {
    if (!d)
        return;
    check(d == dummy && dummy_owned == 1 && !edma_hw.napi_added && !edma_hw.napi_enabled,
          "dummy-free-owned");
    dummy_owned = 0;
    free(d);
    dummy = NULL;
    event("DUMMY_FREE");
}
static void dma_use(void) {
    use_device();
    ++dma_uses;
    event("DMA_API_USE");
}
int edma_hw_init(struct edma_hw *h) {
    dma_use();
    if (fail())
        return -1;
    h->txcmpl_ring = calloc(h->txcmpl_rings, sizeof(*h->txcmpl_ring));
    h->rxdesc_ring = calloc(h->rxdesc_rings, sizeof(*h->rxdesc_ring));
    h->rxfill_ring = calloc(h->rxfill_rings, sizeof(*h->rxfill_ring));
    check(h->txcmpl_ring && h->rxdesc_ring && h->rxfill_ring, "ring-allocate");
    for (unsigned i = 0; i < h->txcmpl_rings; ++i)
        h->txcmpl_ring[i].id = h->txcmpl_ring_start + i;
    for (unsigned i = 0; i < h->rxdesc_rings; ++i)
        h->rxdesc_ring[i].id = h->rxdesc_ring_start + i;
    for (unsigned i = 0; i < h->rxfill_rings; ++i)
        h->rxfill_ring[i].id = h->rxfill_ring_start + i;
    ring_owned = 1;
    h->edma_initialized = true;
    h->active = 0;
    h->txcmpl_intr_mask = h->rxdesc_intr_mask = h->rxfill_intr_mask = h->misc_intr_mask = 3;
    return 0;
}
void edma_cleanup_rings(struct edma_hw *h) {
    check(ring_owned && !irq_owned && !h->napi_added && !h->napi_enabled,
          "rings-after-cpu-retirement");
    dma_use();
    free(h->txcmpl_ring);
    free(h->rxdesc_ring);
    free(h->rxfill_ring);
    h->txcmpl_ring = NULL;
    h->rxdesc_ring = NULL;
    h->rxfill_ring = NULL;
    ring_owned = 0;
    event("RINGS_RELEASE");
}
uint32_t edma_reg_read(uint32_t off) {
    check(map_owned, "mmio-live");
    ++mmio_uses;
    return registers[(off / 4) % (sizeof(registers) / 4)];
}
void edma_reg_write(uint32_t off, uint32_t value) {
    check(map_owned, "mmio-live");
    ++mmio_uses;
    registers[(off / 4) % (sizeof(registers) / 4)] = value;
    if (off == EDMA_REG_PORT_CTRL && value == EDMA_DISABLE) {
        ++port_disables;
        event("PORT_DISABLE");
    }
}
static unsigned irq_count;
static int irq_ids[32];
static int platform_get_irq(struct platform_device *p, unsigned i) {
    check(p == &pdev, "irq-get-device");
    use_device();
    use_node();
    return 100 + (int)i;
}
static int request_irq(int irq, irqreturn_t (*handler)(int, void *), unsigned flags,
                       const char *name, void *id) {
    (void)handler;
    (void)flags;
    (void)name;
    ASSERT_RTNL();
    check(id == &pdev && irq_count < 32, "irq-request-owner");
    use_device();
    irq_ids[irq_count++] = irq;
    ++irq_owned;
    ++irq_uses;
    return 0;
}
static void free_irq(int irq, void *id) {
    ASSERT_RTNL();
    use_device();
    check(irq_owned && irq_count && irq_ids[irq_count - 1] == irq && id == &pdev, "irq-free-owner");
    --irq_owned;
    --irq_count;
    ++irq_uses;
    event("IRQ_FREE");
}
irqreturn_t edma_handle_irq(int n, void *p) {
    (void)n;
    (void)p;
    return 0;
}
irqreturn_t edma_handle_misc_irq(int n, void *p) {
    (void)n;
    (void)p;
    return 0;
}
int edma_napi(struct napi_struct *p, int b) {
    (void)p;
    (void)b;
    return 0;
}
static void netif_napi_add(struct net_device *d, struct napi_struct *n,
                           int (*f)(struct napi_struct *, int)) {
    (void)f;
    check(d == dummy && dummy_owned && !n->added, "napi-dummy-owner");
    n->dev = d;
    n->added = true;
}
static void netif_napi_del(struct napi_struct *n) {
    check(n->added && !n->enabled && !irq_owned, "napi-del-drained");
    n->added = false;
}
static void napi_enable(struct napi_struct *n) {
    check(n->added && !n->enabled, "napi-enable-once");
    n->enabled = true;
}
static void napi_disable(struct napi_struct *n) {
    check(n->enabled, "napi-disable-once");
    n->enabled = false;
}

/* FUNCTIONS */

static void balanced(void) {
    check(!node_owned && node.refs == 5, "node-get-put-balance");
    check(!device_owned && pdev.dev.refs == 7, "device-get-put-balance");
    check(!edma_hw.device_node && !edma_hw.pdev, "global-reference-pointers-cleared");
    check(!edma_hw.reg_base && !edma_hw.reg_resource && !edma_hw.napi_dev,
          "resource-pointers-cleared");
    check(!region_owned && !map_owned && !dummy_owned && !ring_owned && !irq_owned,
          "other-resources-balanced");
}
static void begin(void) {
    ++cases;
    check(!node_owned && !device_owned && !region_owned && !map_owned && !dummy_owned &&
              !ring_owned && !irq_owned && !rtnl_held,
          "case-entry-balanced");
    memset(&edma_hw, 0, sizeof(edma_hw));
    memset(dp_global_data_plane_ctx, 0, sizeof(dp_global_data_plane_ctx));
    memset(registers, 0, sizeof(registers));
    fail_at = stage_calls = irq_count = 0;
    foreign_region = false;
    pdev.dev.data = &foreign_marker;
    node.refs = 5;
    pdev.dev.refs = 7;
}
static void end(void) {
    balanced();
    check(!rtnl_held, "rtnl-end-balanced");
}
static void failures(void) {
    for (unsigned cfg = 0; cfg < 2; ++cfg) {
        dynamic_nodes = !!cfg;
        for (unsigned f = 1; f <= 15; ++f) {
            begin();
            unsigned rg = region_releases, mp = map_releases, ds = drvdata_writes;
            fail_at = f;
            int ret = edma_init();
            check(ret == (f <= 11 ? -EINVAL : f == 14 ? -ENOMEM : -EFAULT), "failure-errno");
            balanced();
            check(region_releases - rg == (f >= 13 ? 1U : 0U), "failure-region-ownership");
            check(map_releases - mp == (f >= 14 ? 1U : 0U), "failure-map-ownership");
            check(drvdata_writes == ds && pdev.dev.data == &foreign_marker,
                  "unpublished-failure-keeps-drvdata");
            fail_at = stage_calls = 0;
            check(!edma_init(), "failed-init-retry");
            check(pdev.dev.data == &edma_hw, "success-still-unconditional-publish");
            edma_cleanup(false);
            balanced();
            unsigned nr = node_puts, dr = device_puts, m = mmio_uses;
            edma_cleanup(false);
            check(nr == node_puts && dr == device_puts && m == mmio_uses, "repeat-final-noop");
            end();
        }
    }
}
static void busy_region_case(void) {
    begin();
    foreign_region = true;
    unsigned rr = region_releases;
    check(edma_init() == -EFAULT, "busy-region-error");
    check(foreign_region && region_releases == rr, "foreign-region-retained");
    balanced();
    check(pdev.dev.data == &foreign_marker, "foreign-drvdata-on-busy-region");
    foreign_region = false;
    fail_at = stage_calls = 0;
    check(!edma_init(), "busy-retry");
    edma_cleanup(false);
    end();
}
static void partial_cases(void) {
    for (unsigned n = 1; n <= 2; ++n) {
        begin();
        stage_calls = 0;
        edma_hw.device_node = of_find_node_by_name(NULL, "edma");
        if (n == 2)
            edma_hw.pdev = of_find_device_by_node(edma_hw.device_node);
        unsigned ng = node_gets, np = node_puts, dg = device_gets, dp = device_puts, w = warnings;
        check(edma_init() == -EBUSY, "partial-owned-init-refused");
        check(node_gets == ng && node_puts == np && device_gets == dg && device_puts == dp &&
                  warnings == w + 1,
              "live-init-no-gets-or-puts");
        edma_cleanup(true);
        check(node_owned == 1 && device_owned == (n == 2), "override-keeps-partial-refs");
        edma_cleanup(false);
        check(pdev.dev.data == &foreign_marker, "partial-no-foreign-drvdata-clear");
        end();
    }
}
static void live_and_foreign(void) {
    begin();
    check(!edma_init(), "live-init");
    unsigned ng = node_gets, np = node_puts, dg = device_gets, dp = device_puts,
             rg = region_releases, mp = map_releases, ds = drvdata_writes, w = warnings;
    check(edma_init() == -EBUSY, "live-init-refused");
    check(node_gets == ng && node_puts == np && device_gets == dg && device_puts == dp &&
              region_releases == rg && map_releases == mp && drvdata_writes == ds &&
              warnings == w + 1,
          "live-owner-untouched");
    pdev.dev.data = &foreign_marker;
    edma_cleanup(false);
    check(pdev.dev.data == &foreign_marker, "foreign-final-drvdata-retained");
    end();
}
static void override_case(void) {
    begin();
    check(!edma_init(), "override-init");
    unsigned np = node_puts, dp = device_puts, m = map_releases, r = region_releases,
             d = port_disables;
    edma_cleanup(true);
    check(node_owned == 1 && device_owned == 1 && map_owned == 1 && region_owned == 1 &&
              !dummy_owned && !ring_owned,
          "override-retains-global-owners");
    check(node_puts == np && device_puts == dp && map_releases == m && region_releases == r &&
              port_disables == d,
          "override-no-global-release");
    edma_cleanup(true);
    check(node_puts == np && device_puts == dp, "repeat-override-retains");
    edma_cleanup(false);
    check(port_disables == d + 1 && !pdev.dev.data, "final-disable-and-own-drvdata-clear");
    balanced();
    m = mmio_uses;
    edma_cleanup(false);
    check(mmio_uses == m, "repeat-override-exit-no-mmio");
    end();
}
static void peer_abort(void) {
    begin();
    check(!edma_init(), "peer-init");
    struct net_device a = {0}, b = {0};
    struct nss_dp_dev pa = {1, &a}, pb = {2, &b};
    a.priv = &pa;
    b.priv = &pb;
    dp_global_data_plane_ctx[0].dev = &a;
    dp_global_data_plane_ctx[1].dev = &b;
    rtnl_lock();
    check(!edma_if_init(&dp_global_data_plane_ctx[0]) &&
              !edma_if_init(&dp_global_data_plane_ctx[1]),
          "ports-published");
    check(!edma_if_open(&dp_global_data_plane_ctx[1], 0, 0, 0), "peer-open");
    rtnl_unlock();
    unsigned np = node_puts, dp = device_puts;
    nss_dp_abort_host_probe(&pa);
    check(node_puts == np && device_puts == dp && node_owned && device_owned &&
              edma_hw.active == 1 && edma_hw.napi_enabled,
          "probe-abort-no-global-put");
    rtnl_lock();
    check(edma_retire_port(&b, 2), "peer-retire");
    nss_dp_clear_host_ctx(&pb);
    rtnl_unlock();
    edma_cleanup(false);
    end();
}
static void old_case(const char *mode) {
    begin();
    if (!strcmp(mode, "old-missing-pdev")) {
        fail_at = 2;
        check(edma_init() == -EINVAL, "old-injected-failure");
    } else if (!strcmp(mode, "old-region")) {
        foreign_region = true;
        check(edma_init() == -EFAULT, "old-region-failure");
    } else {
        check(!edma_init(), "old-init");
        edma_cleanup(false);
    }
    balanced();
}
int main(int argc, char **argv) {
    check(argc == 2, "mode");
    const char *m = argv[1];
    if (!strncmp(m, "poison-", 7)) {
        fputs("EDMA_OF016 node-get-put-balance\n", stderr);
        if (!strcmp(m, "poison-exit"))
            return 87;
        if (!strcmp(m, "poison-stdout"))
            fputs("unexpected\n", stdout);
        else if (!strcmp(m, "poison-stderr"))
            fputs("unexpected\n", stderr);
        else if (!strcmp(m, "poison-sanitizer")) {
            fputs("AddressSanitizer: synthetic unrelated failure\n", stderr);
            return 1;
        }
        return 86;
    }
    if (!strncmp(m, "old-", 4)) {
        old_case(m);
        return 0;
    }
    if (!strcmp(m, "target-region"))
        busy_region_case();
    else if (!strcmp(m, "target-partial"))
        partial_cases();
    else if (!strcmp(m, "target-foreign"))
        live_and_foreign();
    else if (!strcmp(m, "target-override"))
        override_case();
    else if (!strcmp(m, "target-peer"))
        peer_abort();
    else {
        if (!strcmp(m, "trace"))
            trace_on = true;
        else
            check(!strcmp(m, "suite"), "known-mode");
        failures();
        busy_region_case();
        partial_cases();
        live_and_foreign();
        override_case();
        peer_abort();
    }
    check(node_gets == node_puts && device_gets == device_puts, "total-get-put-balance");
    printf("cases=%u checks=%u node=%u/%u device=%u/%u dma_uses=%u irq_uses=%u\n", cases, checks,
           node_gets, node_puts, device_gets, device_puts, dma_uses, irq_uses);
    return 0;
}
