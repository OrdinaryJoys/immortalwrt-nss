#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks, cases, stages;
static char trace_buffer[16384];
static size_t trace_size;
#define CHECK(x, tag) do { checks++; if (!(x)) { \
    fprintf(stderr, "DP_PHY017 %s\n", tag); exit(86); } } while (0)
#define NSS_DP_HAL_MAX_PORTS 4
struct device_node { bool fixed; };
struct platform_device { struct { struct device_node *of_node; } dev; };
struct phy_device { bool started, irq, attached; void *adjust_link; };
struct net_device { unsigned id; bool registered, freed; };
struct nss_gmac_hal_ops { void (*exit)(void *); };
struct nss_dp_data_plane_ops { void (*deinit)(void *); };
struct nss_dp_dev {
    struct platform_device *pdev;
    struct phy_device *phydev;
    struct net_device *netdev;
    struct nss_gmac_hal_ops *gmac_hal_ops;
    struct nss_dp_data_plane_ops *data_plane_ops;
    void *gmac_hal_ctx, *dpc;
    unsigned macid;
    bool quarantined, cleared;
};
static struct { struct nss_dp_dev *nss_dp[NSS_DP_HAL_MAX_PORTS]; } dp_global_ctx;
static struct nss_dp_dev ports[2];
static struct net_device netdevs[2];
static struct phy_device phys[2];
static struct device_node nodes[2];
static struct platform_device pdevs[2];
static bool rtnl, abort_case;
static unsigned unregs[2], stops[2], irq_frees[2], detaches[2], fixed_frees[2], exits[2];

static void trace(unsigned id, char code) {
    int written = snprintf(trace_buffer + trace_size, sizeof(trace_buffer) - trace_size,
                           "%u:%c;", id, code);
    CHECK(written > 0 && (size_t)written < sizeof(trace_buffer) - trace_size, "trace-capacity");
    trace_size += (size_t)written; stages++;
}
static unsigned phy_id(struct phy_device *phy) { return (unsigned)(phy - phys); }
static void rtnl_lock(void) { CHECK(!rtnl, "rtnl-recursion"); rtnl = true; }
static void rtnl_unlock(void) { CHECK(rtnl, "rtnl-unlock"); rtnl = false; }
static void nss_dp_plane_quarantine(struct nss_dp_dev *p) {
    CHECK(rtnl, "quarantine-lock"); p->quarantined = true; trace(p->netdev->id, 'q');
}
static void nss_dp_clear_host_ctx(struct nss_dp_dev *p) {
    CHECK(rtnl && p->quarantined, "clear-lock"); p->cleared = true; trace(p->netdev->id, 'c');
}
static bool phy_is_started(struct phy_device *p) { return p->started; }
static bool phy_interrupt_is_valid(struct phy_device *p) { return p->irq; }
static void phy_stop(struct phy_device *p) {
    CHECK(p->started, "stop-once"); p->started = false; stops[phy_id(p)]++; trace(phy_id(p), 's');
}
static void phy_free_interrupt(struct phy_device *p) {
    CHECK(p->irq, "irq-once"); p->irq = false; irq_frees[phy_id(p)]++; trace(phy_id(p), 'i');
}
static void phy_detach(struct phy_device *p) {
    unsigned i = phy_id(p);
    CHECK(p->attached && !p->started && !p->irq && !p->adjust_link, "complete-disconnect");
#ifdef NSS_DP_IPQ807X
    CHECK(abort_case || !netdevs[i].registered, "registered-detach");
#endif
    p->attached = false; detaches[i]++; trace(i, 'd');
}
static bool of_phy_is_fixed_link(struct device_node *p) { return p->fixed; }
static void of_phy_deregister_fixed_link(struct device_node *p) {
    unsigned i = (unsigned)(p - nodes);
    CHECK(p->fixed, "fixed-once"); p->fixed = false; fixed_frees[i]++; trace(i, 'f');
}
static void unregister_netdev(struct net_device *n) {
    CHECK(!rtnl && n->registered && !n->freed, "unregister-once");
    rtnl_lock();
#ifdef NSS_DP_IPQ807X
    CHECK(ports[n->id].quarantined && ports[n->id].cleared, "admission-before-unregister");
    CHECK(!ports[n->id].phydev || ports[n->id].phydev->attached, "registered-phy-lifetime");
#endif
    CHECK(ports[n->id].gmac_hal_ctx != NULL, "hal-through-unregister");
    n->registered = false; unregs[n->id]++; trace(n->id, 'u'); rtnl_unlock();
}
static void model_hal_exit(void *ctx) {
    struct nss_dp_dev *p = ctx;
    CHECK(!p->netdev->registered && !p->phydev, "hal-after-retirement");
    exits[p->netdev->id]++; trace(p->netdev->id, 'h');
}
static void model_plane_exit(void *ctx) { struct nss_dp_dev *p = ctx; trace(p->netdev->id, 'p'); }
static void fal_port_vsi_set(unsigned dev, unsigned port, unsigned vsi) {
    (void)dev; (void)vsi; trace(port-1, 'v');
}
static void nss_dp_switchdev_cleanup(struct net_device *n) { trace(n->id, 'w'); }
static void nss_dp_hal_deinit_soc_priv_flags(struct nss_dp_dev *p) { trace(p->netdev->id, 'g'); }
static void free_netdev(struct net_device *n) {
    CHECK(!n->registered && !n->freed && exits[n->id] == 1, "free-after-retirement");
    n->freed = true; trace(n->id, 'x');
}

/* @functions@ */

static struct nss_gmac_hal_ops hal = { model_hal_exit };
static struct nss_dp_data_plane_ops plane = { model_plane_exit };
static void reset(bool attached, bool started, bool irq, bool fixed) {
    memset(&dp_global_ctx, 0, sizeof(dp_global_ctx));
    memset(ports, 0, sizeof(ports)); memset(netdevs, 0, sizeof(netdevs));
    memset(phys, 0, sizeof(phys)); memset(nodes, 0, sizeof(nodes));
    memset(unregs, 0, sizeof(unregs)); memset(stops, 0, sizeof(stops));
    memset(irq_frees, 0, sizeof(irq_frees)); memset(detaches, 0, sizeof(detaches));
    memset(fixed_frees, 0, sizeof(fixed_frees)); memset(exits, 0, sizeof(exits));
    rtnl = abort_case = false;
    for (unsigned i=0; i<2; i++) {
        netdevs[i] = (struct net_device){i, true, false};
        phys[i] = (struct phy_device){started, irq, attached, (void *)1};
        nodes[i].fixed = fixed; pdevs[i].dev.of_node = &nodes[i];
        ports[i] = (struct nss_dp_dev){.pdev=&pdevs[i], .phydev=attached?&phys[i]:NULL,
            .netdev=&netdevs[i], .gmac_hal_ops=&hal, .data_plane_ops=&plane,
            .gmac_hal_ctx=&ports[i], .dpc=&ports[i], .macid=i+1};
        dp_global_ctx.nss_dp[i+1] = &ports[i];
    }
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "semantic-canary")) CHECK(false, "semantic-canary");
    if (argc == 2 && !strcmp(argv[1], "nonsemantic-canary")) return 97;
    for (unsigned bits=0; bits<16; bits++) {
        bool started=bits&1, irq=bits&2, fixed=bits&4, attached=bits&8;
        reset(attached, started, irq, fixed);
        nss_dp_remove(&pdevs[0]);
        for (unsigned i=0; i<2; i++) {
            CHECK(unregs[i]==1 && exits[i]==1 && netdevs[i].freed, "port-ledger");
            CHECK(stops[i]==(unsigned)(attached&&started), "stop-ledger");
            CHECK(irq_frees[i]==(unsigned)(attached&&irq), "irq-ledger");
            CHECK(detaches[i]==(unsigned)attached, "detach-ledger");
            CHECK(fixed_frees[i]==(unsigned)(attached&&fixed), "fixed-ledger");
            CHECK(!dp_global_ctx.nss_dp[i+1], "published-port-clear");
        }
        unsigned before = stages;
        nss_dp_remove(&pdevs[0]); CHECK(stages==before, "repeat-remove"); cases++;
    }
    for (unsigned bits=0; bits<8; bits++) {
        bool started=bits&1, irq=bits&2, fixed=bits&4;
        reset(true, started, irq, fixed); abort_case = true;
        for (unsigned i=0; i<2; i++) {
            netdevs[i].registered = false;
            nss_dp_phy_disconnect(&ports[i]);
            CHECK(!ports[i].phydev && detaches[i]==1 && unregs[i]==0, "probe-abort");
            CHECK(stops[i]==(unsigned)started && irq_frees[i]==(unsigned)irq,
                  "probe-disconnect-ledger");
            unsigned before=stages; nss_dp_phy_disconnect(&ports[i]);
            CHECK(stages==before, "repeat-disconnect");
        }
        cases++;
    }
    fputs(trace_buffer, stdout);
    printf("\nPASS DP_PHY017 cases=%u checks=%u stages=%u\n", cases, checks, stages);
    return 0;
}
