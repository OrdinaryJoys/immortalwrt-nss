/* Host substitutes around verbatim prepared-source HAL functions. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bounds.inc"
#define NSS_HAL_IPQ807x_SUPPORT 1
#define NSS_FREQ_SCALE_SUPPORT 0
#define NSS_CTX_MAGIC 0x12345
#define NSS_NBUF_PAYLOAD_SIZE 2048
#define NSS_HAL_SUPPORTED_INTERRUPTS 255
#define NSS_FEATURE_ENABLED 1
#define NSS_CTX_NAPI_NDEV(ctx) ((ctx)->napi_ndev)
#define IRQ_DISABLE_UNLAZY 1
#define NSS_AP0_IMAGE "qca-nss0.bin"
#define NSS_AP1_IMAGE "qca-nss1.bin"
#define __iomem
#define nss_info(...) ((void)0)
#define nss_info_always(...) ((void)0)
#define nss_warning(...) ((void)0)
#define pr_err(...) ((void)0)
#define dev_info(...) ((void)0)
#define nss_assert(x) REQUIRE(x, "source-assert")

static const char *scenario = "arguments";
static int core, checks;
static void require(bool ok, const char *id)
{
    checks++;
    if (!ok) {
        fprintf(stderr, "NSS_ASSERT %s case=%s core=%d dt=%d\n",
                id, scenario, core, NSS_DT_SUPPORT);
        exit(86);
    }
}
#define REQUIRE(x, id) require((x), (id))

struct device { void *of_node, *platform_data; int managed; };
struct platform_device { struct device dev; int id; };
struct net_device { int token; };
struct napi_struct { bool added, enabled, deleted; };
struct nss_ctx_instance;
struct int_ctx_instance {
    int irq, shift_factor;
    struct napi_struct napi;
    struct nss_ctx_instance *nss_ctx;
};
struct ring { void *head, *tail, *jumbo_start; };
struct meminfo { uintptr_t blocks, h2n, n2h, map, logbuffer; };
struct nss_top_instance;
struct nss_ctx_instance {
    int id, num_irq, magic, max_buf_size, decongest_cb_lock;
    struct nss_top_instance *nss_top;
    struct device *dev;
    uint32_t load, nphys, vphys;
    void *nmap, *vmap, *qgic_map;
    struct net_device *napi_ndev;
    struct int_ctx_instance int_ctx[NSS_MAX_IRQ_PER_CORE];
    uintptr_t queue_decongestion_callback[NSS_MAX_CLIENTS];
    uintptr_t queue_decongestion_ctx[NSS_MAX_CLIENTS];
    struct ring n2h_desc_ring[NSS_N2H_DESC_RING_NUM];
    struct meminfo meminfo_ctx;
};
struct nss_platform_data {
    int id, num_irq, wlanredirect_enabled;
    uint32_t load_addr, nphys, vphys;
    void *nmap, *vmap, *qgic_map;
};
struct hal_ops {
    int (*common_reset)(struct platform_device *);
    struct nss_platform_data *(*of_get_pdata)(struct platform_device *);
    int (*firmware_load)(struct nss_ctx_instance *, struct platform_device *, struct nss_platform_data *);
    int (*clock_configure)(struct nss_ctx_instance *, struct platform_device *, struct nss_platform_data *);
    int (*request_irq)(struct nss_ctx_instance *, struct nss_platform_data *, int);
    int (*core_reset)(struct platform_device *, void *, uint32_t, uint32_t);
};
struct nss_top_instance {
    struct hal_ops *hal_ops;
    struct nss_ctx_instance nss[2];
    bool nss_hal_common_init_done;
    uint32_t clk_src;
    int wlan_handler_id, frequency_handler_id;
};
static struct nss_top_instance nss_top_main;
static int nss_hal_receive_group_lock;
static bool nss_hal_receive_group_closing;
static struct platform_device device;
static struct nss_platform_data pd;
static struct net_device dummy = { 1 }, foreign_dummy = { 91 };
static struct net_device *pretransfer_owner;
static bool dummy_live, pd_live, map_n_live, map_v_live, fw_live, fw_mapped;
static bool irq_live[NSS_MAX_IRQ_PER_CORE];
static int nmap, vmap, qgic, foreign_token;
static int allocs, local_frees, owned_frees, irq_frees, irq_calls, handlers;
static int common_calls, clock_calls, mem_calls, pdata_calls, fw_calls, fw_copies;
static int fw_releases, fw_unmaps, unm_n, unm_v, pd_frees, resets, enables, boots;
static int managed_releases, global_regulator;
struct provider { bool live, enabled; int owner; };
static struct provider providers[3];
static char trace[16384];
static const struct meminfo committed = { 0x11, 0x22, 0x33, 0x44, 0x55 };
static const unsigned char fw_bytes[] = { 0x31, 0x32, 0x33, 0x34 };
static unsigned char fw_backing[sizeof(fw_bytes)];
struct firmware { const unsigned char *data; size_t size; };
static const struct firmware fw = { fw_bytes, sizeof(fw_bytes) };

enum failure { NONE, COMMON, NO_NODE, PDATA, FW, DEFER, FW_MAP, CLOCK, MEMINFO, RESET,
               IRQ0, IRQ1, IRQ2, IRQ3, IRQ4, IRQ5, IRQ6, IRQ7, IRQ8, IRQ9 };
struct test_case {
    const char *name;
    enum failure fail;
    bool cold, oom, foreign, closed;
};
static const struct test_case cases[] = {
    { "success", NONE, false, false, false, false },
    { "cold-success", NONE, true, false, false, false },
    { "dummy-oom", NONE, false, true, false, false },
    { "dummy-oom-cold", NONE, true, true, false, false },
    { "dummy-oom-commonfail", COMMON, true, true, true, false },
    { "dummy-oom-foreign", NONE, false, true, true, false },
    { "dummy-oom-foreign-cold", NONE, true, true, true, false },
    { "dummy-oom-firmware", FW, false, true, true, false },
    { "dummy-oom-clock", CLOCK, false, true, true, false },
    { "dummy-oom-meminfo", MEMINFO, false, true, true, false },
    { "firmware-error", FW, false, false, true, false },
    { "firmware-error-cold", FW, true, false, true, false },
    { "firmware-defer", DEFER, false, false, true, false },
    { "firmware-defer-cold", DEFER, true, false, true, false },
    { "firmware-map-oom", FW_MAP, false, false, true, false },
    { "firmware-map-oom-cold", FW_MAP, true, false, true, false },
    { "clock-error", CLOCK, false, false, true, false },
    { "clock-error-cold", CLOCK, true, false, true, false },
    { "meminfo-fail", MEMINFO, false, false, true, false },
    { "meminfo-fail-cold", MEMINFO, true, false, true, false },
    { "irq0-fail", IRQ0, false, false, false, false },
    { "irq1-fail", IRQ1, false, false, false, false },
    { "irq2-fail", IRQ2, false, false, false, false },
    { "irq3-fail", IRQ3, false, false, false, false },
    { "irq4-fail", IRQ4, false, false, false, false },
    { "irq5-fail", IRQ5, false, false, false, false },
    { "irq6-fail", IRQ6, false, false, false, false },
    { "irq7-fail", IRQ7, false, false, false, false },
    { "irq8-fail", IRQ8, false, false, false, false },
    { "irq9-fail", IRQ9, false, false, false, false },
    { "core-reset-fail", RESET, false, false, false, false },
    { "core-reset-fail-cold", RESET, true, false, false, false },
    { "group-closed", NONE, false, false, true, true },
    { "dummy-oom-group-closed", NONE, false, true, true, true },
    { "common-fail", COMMON, true, false, true, false },
#if NSS_DT_SUPPORT
    { "no-node", NO_NODE, false, false, true, false },
    { "no-node-cold", NO_NODE, true, false, true, false },
    { "pdata-fail", PDATA, false, false, true, false },
    { "pdata-fail-cold", PDATA, true, false, true, false },
    { "dummy-oom-no-node", NO_NODE, false, true, true, false },
    { "dummy-oom-pdata", PDATA, false, true, true, false },
#endif
};
static const struct test_case *test;

static void event(const char *name)
{
    size_t n = strlen(trace);
    REQUIRE(n + strlen(name) + 2 < sizeof(trace), "fixture-trace-capacity");
    snprintf(trace + n, sizeof(trace) - n, "%s%s", n ? "," : "", name);
}
static void pretransfer(void)
{
    if (EXPECT_EARLY) {
        REQUIRE(!test->oom, "oom-no-provider");
        REQUIRE(dummy_live && allocs == 1, "allocate-before-provider");
    }
    REQUIRE(nss_top_main.nss[core].napi_ndev == pretransfer_owner, "foreign-owner-preserved");
}
static void mutex_lock(int *lock)
{
    REQUIRE(*lock == 0, "lock-balanced"); *lock = 1; event("lock");
}
static void mutex_unlock(int *lock)
{
    REQUIRE(*lock == 1, "lock-balanced"); *lock = 0; event("unlock");
}
static void acquire_provider(struct device *d, int id)
{
    REQUIRE(!providers[id].live && d == &device.dev, "provider-single-owner");
    providers[id] = (struct provider){ true, true, core + 1 };
    d->managed++;
}
static int mock_common(struct platform_device *d)
{
    pretransfer(); event("common"); common_calls++;
    acquire_provider(&d->dev, 0);
    if (test->fail == COMMON) return -EIO;
    nss_top_main.nss_hal_common_init_done = true;
    return 0;
}
static struct nss_platform_data *mock_pdata(struct platform_device *d)
{
    REQUIRE(d == &device && d->dev.of_node, "pdata-device");
    pretransfer(); event("pdata"); pdata_calls++;
    if (test->fail == PDATA) return NULL;
    pd_live = map_n_live = map_v_live = true;
    return &pd;
}
static int firmware_request_nowarn(const struct firmware **out, const char *name, struct device *d)
{
    pretransfer(); event("firmware-request"); fw_calls++;
    REQUIRE(d == &device.dev && !fw_live, "firmware-owner");
    REQUIRE(!strcmp(name, core ? NSS_AP1_IMAGE : NSS_AP0_IMAGE), "firmware-core-name");
    if (test->fail == FW) return -ENOENT;
    if (test->fail == DEFER) return -517;
    *out = &fw; fw_live = true;
    return 0;
}
static void *nss_ioremap(uint32_t addr, size_t len)
{
    event("firmware-map");
    REQUIRE(fw_live && !fw_mapped && addr == pd.load_addr && len == sizeof(fw_bytes), "firmware-map-owner");
    if (test->fail == FW_MAP) return NULL;
    fw_mapped = true;
    return fw_backing;
}
static int nss_hal_firmware_info(struct platform_device *d, const struct firmware *f)
{
    REQUIRE(d == &device && f == &fw && fw_live, "firmware-info-owner");
    return 0;
}
static void memcpy_toio(void *to, const void *from, size_t len)
{
    REQUIRE(fw_live && fw_mapped && to == fw_backing && from == fw_bytes && len == sizeof(fw_bytes), "firmware-copy-owner");
    event("firmware-copy"); fw_copies++; memcpy(to, from, len);
}
static void release_firmware(const struct firmware *f)
{
    REQUIRE(f == &fw && fw_live, "firmware-release-owner");
    event("firmware-release"); fw_live = false; fw_releases++;
}
static int mock_clock(struct nss_ctx_instance *ctx, struct platform_device *d, struct nss_platform_data *p)
{
    REQUIRE(ctx == &nss_top_main.nss[core] && p == &pd, "clock-context");
    pretransfer(); event("clock"); clock_calls++;
    acquire_provider(&d->dev, 1);
    if (!core) { acquire_provider(&d->dev, 2); global_regulator = 3; }
    return test->fail == CLOCK ? -EIO : 0;
}
static bool nss_meminfo_init(struct nss_ctx_instance *ctx)
{
    pretransfer(); event("meminfo"); mem_calls++;
    REQUIRE(ctx == &nss_top_main.nss[core], "meminfo-context");
    if (test->fail == MEMINFO) return false;
    ctx->meminfo_ctx = committed;
    return true;
}
static struct net_device *alloc_netdev_dummy(int size)
{
    REQUIRE(size == 0 && !dummy_live && allocs == 0, "dummy-single-allocation");
    event("alloc"); allocs++;
    dummy_live = !test->oom;
    return dummy_live ? &dummy : NULL;
}
static void netif_napi_del(struct napi_struct *n)
{
    REQUIRE(dummy_live && n->added && !n->enabled && !n->deleted, "napi-delete-after-disable");
    event("napi-del"); n->added = false; n->deleted = true;
}
static int mock_request_irq(struct nss_ctx_instance *ctx, struct nss_platform_data *p, int i)
{
    REQUIRE(ctx == &nss_top_main.nss[core] && p == &pd && i >= 0 && i < NSS_MAX_IRQ_PER_CORE, "irq-context");
    REQUIRE(dummy_live && ctx->napi_ndev == &dummy, "irq-transfer-owner");
    struct int_ctx_instance *ic = &ctx->int_ctx[i];
    REQUIRE(ic->nss_ctx == ctx && !ic->irq && !irq_live[i] && !ic->napi.added, "irq-single-registration");
    event("request-irq"); irq_calls++; ic->napi.added = true;
    /* The real IPQ807x helper adds NAPI before request_irq, deleting it on failure. */
    if (test->fail == (enum failure)(IRQ0 + i)) { netif_napi_del(&ic->napi); return -EBUSY; }
    irq_live[i] = true; ic->irq = i + 10; ic->shift_factor = i;
    return 0;
}
static void napi_enable(struct napi_struct *n)
{
    REQUIRE(dummy_live && n->added && !n->enabled && !n->deleted, "napi-enable-owner");
    event("napi-enable"); n->enabled = true;
}
static void napi_disable(struct napi_struct *n)
{
    REQUIRE(dummy_live && n->added && n->enabled, "napi-disable-owner");
    event("napi-disable"); n->enabled = false;
}
static void irq_clear_status_flags(int irq, int flag)
{
    REQUIRE(irq >= 10 && irq < 10 + NSS_MAX_IRQ_PER_CORE && irq_live[irq - 10] && flag == IRQ_DISABLE_UNLAZY, "irq-flags-owner");
    event("irq-flags");
}
static void free_irq(int irq, struct int_ctx_instance *ic)
{
    REQUIRE(irq >= 10 && irq < 10 + NSS_MAX_IRQ_PER_CORE, "irq-free-range");
    REQUIRE(dummy_live && irq_live[irq - 10] && ic == &nss_top_main.nss[core].int_ctx[irq - 10] && ic->irq == irq && ic->napi.deleted, "irq-free-after-napi-delete");
    event("irq-free"); irq_live[irq - 10] = false; irq_frees++;
}
static void free_netdev(struct net_device *n)
{
    REQUIRE(n == &dummy, "free-only-owned-dummy");
    REQUIRE(dummy_live, "dummy-live-on-free");
    for (int i = 0; i < NSS_MAX_IRQ_PER_CORE; i++)
        REQUIRE(!irq_live[i] && !nss_top_main.nss[core].int_ctx[i].napi.added, "dummy-free-after-irq-cleanup");
    if (nss_top_main.nss[core].napi_ndev == n) { event("free-owned"); owned_frees++; }
    else { event("free-local"); local_frees++; }
    dummy_live = false;
}
static void iounmap(void *p)
{
    if (p == fw_backing) {
        REQUIRE(fw_mapped, "firmware-unmap-owner");
        event("firmware-unmap"); fw_mapped = false; fw_unmaps++;
    } else if (p == &nmap) {
        REQUIRE(map_n_live, "nmap-unmap-owner");
        event("unmap-n"); map_n_live = false; unm_n++;
    } else {
        REQUIRE(p == &vmap && map_v_live, "vmap-unmap-owner");
        event("unmap-v"); map_v_live = false; unm_v++;
    }
}
static void devm_kfree(struct device *d, void *p)
{
    REQUIRE(d == &device.dev && p == &pd && pd_live, "pdata-free-owner");
    event("pdata-free"); pd_live = false; pd_frees++;
}
static void handler(struct nss_ctx_instance *ctx, const char *name)
{
    REQUIRE(ctx == &nss_top_main.nss[core] && dummy_live && ctx->napi_ndev == &dummy, "handler-owner");
    event(name); handlers++;
}
static void nss_core_init_handlers(struct nss_ctx_instance *c) { handler(c, "handlers-core"); }
static void nss_dynamic_interface_register_handler(struct nss_ctx_instance *c) { handler(c, "handler-dynamic"); }
static void nss_n2h_register_handler(struct nss_ctx_instance *c) { handler(c, "handler-n2h"); }
static void nss_project_register_handler(struct nss_ctx_instance *c) { handler(c, "handler-project"); }
static void nss_unaligned_register_handler(struct nss_ctx_instance *c) { handler(c, "handler-unaligned"); }
static void spin_lock_init(int *l) { event("spin-init"); *l = 1; }
static int mock_reset(struct platform_device *d, void *m, uint32_t load, uint32_t src)
{
    REQUIRE(d == &device && dummy_live && m == &nmap && load == pd.load_addr && src == nss_top_main.clk_src, "reset-owner");
    event("core-reset"); resets++;
    return test->fail == RESET ? -EIO : 0;
}
static void nss_hal_enable_interrupt(struct nss_ctx_instance *ctx, int shift, int mask)
{
    REQUIRE(ctx == &nss_top_main.nss[core] && dummy_live && shift == enables && irq_live[shift] && mask == NSS_HAL_SUPPORTED_INTERRUPTS, "enable-irq-owner");
    event("enable-irq"); enables++;
}
static void nss_bootwait(void) { REQUIRE(dummy_live, "boot-owner"); event("bootwait"); boots++; }

#include "actual-functions.inc"

/* Model only the devres boundary: this is NOT Linux driver-core execution. */
static void host_failed_probe_cleanup(void)
{
    event("host-devres-release");
    for (int i = 2; i >= 0; i--) {
        if (!providers[i].live) continue;
        REQUIRE(providers[i].owner == core + 1, "devres-owned-by-probing-device");
        providers[i].live = false; managed_releases++; device.dev.managed--;
    }
    REQUIRE(device.dev.managed == 0, "devres-ledger-balanced");
    /* Enabled state/global borrow intentionally remain: no provider safety claim. */
}

static void setup(void)
{
    static struct hal_ops ops = { mock_common, mock_pdata, nss_hal_firmware_load,
                                 mock_clock, mock_request_irq, mock_reset };
    memset(&nss_top_main, 0, sizeof(nss_top_main));
    memset(&pd, 0, sizeof(pd)); memset(&device, 0, sizeof(device));
    memset(providers, 0, sizeof(providers)); memset(irq_live, 0, sizeof(irq_live));
    memset(fw_backing, 0, sizeof(fw_backing));
    allocs = local_frees = owned_frees = irq_frees = irq_calls = handlers = 0;
    common_calls = clock_calls = mem_calls = pdata_calls = fw_calls = fw_copies = 0;
    fw_releases = fw_unmaps = unm_n = unm_v = pd_frees = resets = enables = boots = 0;
    managed_releases = 0; global_regulator = test->foreign ? 91 : 0;
    dummy_live = fw_live = fw_mapped = false;
    pd_live = map_n_live = map_v_live = !NSS_DT_SUPPORT;
    trace[0] = 0; checks = 0;
    nss_hal_receive_group_lock = 0; nss_hal_receive_group_closing = test->closed;
    nss_top_main.hal_ops = &ops;
    nss_top_main.nss_hal_common_init_done = !test->cold;
    nss_top_main.clk_src = 19;
    pd.id = core; pd.num_irq = NSS_MAX_IRQ_PER_CORE;
    pd.nmap = &nmap; pd.vmap = &vmap; pd.qgic_map = &qgic;
    pd.nphys = 0x1000; pd.vphys = 0x2000; pd.load_addr = 0x3000;
    device.dev.of_node = NSS_DT_SUPPORT && test->fail != NO_NODE ? &pd : NULL;
    device.dev.platform_data = &pd; device.id = NSS_DT_SUPPORT ? 77 : core;
    pretransfer_owner = test->foreign ? &foreign_dummy : NULL;
    for (int c = 0; c < 2; c++) {
        struct nss_ctx_instance *ctx = &nss_top_main.nss[c];
        ctx->napi_ndev = c == core ? pretransfer_owner : &foreign_dummy;
        ctx->meminfo_ctx = (struct meminfo){ 91, 92, 93, 94, 95 };
        ctx->magic = 71; ctx->max_buf_size = 72;
        for (int i = 0; i < NSS_MAX_CLIENTS; i++) {
            ctx->queue_decongestion_callback[i] = 101 + i;
            ctx->queue_decongestion_ctx[i] = 201 + i;
        }
        for (int i = 0; i < NSS_N2H_DESC_RING_NUM; i++)
            ctx->n2h_desc_ring[i] = (struct ring){ &foreign_token, &foreign_token, &foreign_token };
    }
}
static int expected_errno(void)
{
    if (test->closed) return -ESHUTDOWN;
    if (EXPECT_EARLY && test->oom) return -ENOMEM;
    switch (test->fail) {
    case COMMON: case PDATA: case MEMINFO: return -EFAULT;
    case NO_NODE: return -ENODEV;
    case FW: return -ENOENT;
    case DEFER: return -517;
    case FW_MAP: return -ENOMEM;
    case CLOCK: case RESET: return -EIO;
    default: return test->fail >= IRQ0 ? -EBUSY : 0;
    }
}

/* Pointer identities, not process addresses, make cross-executable state comparable. */
static int ptr_id(const void *p)
{
    if (!p) return 0;
    if (p == &dummy) return 1;
    if (p == &foreign_dummy) return 2;
    if (p == &nmap) return 3;
    if (p == &vmap) return 4;
    if (p == &qgic) return 5;
    if (p == &nss_top_main) return 6;
    if (p == &device.dev) return 7;
    if (p == &nss_top_main.nss[0]) return 8;
    if (p == &nss_top_main.nss[1]) return 9;
    if (p == &foreign_token) return 10;
    REQUIRE(false, "snapshot-known-pointer"); return -1;
}
static void emit_state(const char *phase, int ret)
{
    printf("{\"case\":\"%s\",\"dt\":%d,\"core\":%d,\"phase\":\"%s\",\"oom\":%d,\"closed\":%d,\"ret\":%d,\"trace\":\"%s\",\"allocs\":%d,\"local_frees\":%d,\"checks\":%d,\"state\":[",
           scenario, NSS_DT_SUPPORT, core, phase, test->oom, test->closed, ret,
           trace, allocs, local_frees, checks);
    printf("%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
           device.id, device.dev.managed, nss_top_main.nss_hal_common_init_done,
           global_regulator, pd_live, map_n_live, map_v_live, fw_live, fw_mapped,
           dummy_live, owned_frees, common_calls, clock_calls, mem_calls, pdata_calls,
           fw_calls, fw_copies, fw_releases, fw_unmaps, unm_n, unm_v, pd_frees,
           irq_calls, irq_frees, handlers, resets, enables, boots, managed_releases,
           nss_top_main.frequency_handler_id);
    for (int i = 0; i < 3; i++)
        printf(",%d,%d,%d", providers[i].live, providers[i].enabled, providers[i].owner);
    for (size_t i = 0; i < sizeof(fw_backing); i++) printf(",%u", fw_backing[i]);
    for (int c = 0; c < 2; c++) {
        struct nss_ctx_instance *ctx = &nss_top_main.nss[c];
        printf(",%d,%d,%d,%d,%d,%d,%d,%u,%u,%u,%d,%d,%d,%d,%lu,%lu,%lu,%lu,%lu",
               ctx->id, ctx->num_irq, ctx->magic, ctx->max_buf_size, ctx->decongest_cb_lock,
               ptr_id(ctx->nss_top), ptr_id(ctx->dev), ctx->load, ctx->nphys, ctx->vphys,
               ptr_id(ctx->nmap), ptr_id(ctx->vmap), ptr_id(ctx->qgic_map), ptr_id(ctx->napi_ndev),
               (unsigned long)ctx->meminfo_ctx.blocks, (unsigned long)ctx->meminfo_ctx.h2n,
               (unsigned long)ctx->meminfo_ctx.n2h, (unsigned long)ctx->meminfo_ctx.map,
               (unsigned long)ctx->meminfo_ctx.logbuffer);
        for (int i = 0; i < NSS_MAX_IRQ_PER_CORE; i++) {
            struct int_ctx_instance *ic = &ctx->int_ctx[i];
            printf(",%d,%d,%d,%d,%d,%d", ic->irq, ic->shift_factor, ic->napi.added,
                   ic->napi.enabled, ic->napi.deleted, ptr_id(ic->nss_ctx));
        }
        for (int i = 0; i < NSS_MAX_CLIENTS; i++)
            printf(",%lu,%lu", (unsigned long)ctx->queue_decongestion_callback[i],
                   (unsigned long)ctx->queue_decongestion_ctx[i]);
        for (int i = 0; i < NSS_N2H_DESC_RING_NUM; i++)
            printf(",%d,%d,%d", ptr_id(ctx->n2h_desc_ring[i].head),
                   ptr_id(ctx->n2h_desc_ring[i].tail), ptr_id(ctx->n2h_desc_ring[i].jumbo_start));
    }
    puts("]}");
}
static void run_case(void)
{
    setup();
    struct nss_top_instance before = nss_top_main;
    struct platform_device before_device = device;
    int before_regulator = global_regulator;
    int ret = nss_hal_probe(&device);
    struct nss_ctx_instance *ctx = &nss_top_main.nss[core];
    REQUIRE(ret == expected_errno(), "return-errno");
    REQUIRE(nss_hal_receive_group_lock == 0, "lock-balanced");
    REQUIRE(!memcmp(&before.nss[1 - core], &nss_top_main.nss[1 - core], sizeof(*ctx)), "sibling-context-preserved");
    REQUIRE(foreign_dummy.token == 91, "foreign-object-preserved");
    REQUIRE(!fw_live && !fw_mapped, "firmware-temporary-released");
    if (fw_copies) REQUIRE(!memcmp(fw_backing, fw_bytes, sizeof(fw_bytes)), "firmware-copy-content");
    if ((EXPECT_EARLY && test->oom) || test->closed) {
        REQUIRE(!memcmp(&before, &nss_top_main, sizeof(before)), "oom-context-unpublished");
        REQUIRE(!memcmp(&before_device, &device, sizeof(device)), "oom-device-unchanged");
        REQUIRE(global_regulator == before_regulator, "oom-global-unchanged");
        REQUIRE(!common_calls && !pdata_calls && !fw_calls && !clock_calls && !mem_calls && !irq_calls && !resets, "oom-zero-acquisitions");
        REQUIRE(!dummy_live && !local_frees && !owned_frees && allocs == !test->closed, "oom-no-dummy-owner");
        REQUIRE(!strcmp(trace, test->closed ? "lock,unlock" : "lock,alloc,unlock"), "oom-exact-trace");
    } else if (test->fail >= COMMON && test->fail <= MEMINFO) {
        REQUIRE(ctx->napi_ndev == pretransfer_owner, "foreign-owner-preserved");
        REQUIRE(!dummy_live && local_frees == EXPECT_EARLY && allocs == EXPECT_EARLY && !owned_frees, "local-owner-released");
    } else if (test->fail >= IRQ0 || test->fail == RESET) {
        int registered = test->fail == RESET ? NSS_MAX_IRQ_PER_CORE : test->fail - IRQ0;
        REQUIRE(irq_frees == registered, "irq-prefix-cleaned");
        REQUIRE(owned_frees == 1 && !dummy_live && !ctx->napi_ndev && !local_frees, "irq-owner-released");
        for (int i = 0; i < NSS_MAX_IRQ_PER_CORE; i++)
            REQUIRE(!irq_live[i] && !ctx->int_ctx[i].irq && !ctx->int_ctx[i].napi.added && !ctx->int_ctx[i].napi.enabled, "irq-prefix-empty");
    } else if (!test->oom) {
        REQUIRE(dummy_live && ctx->napi_ndev == &dummy && allocs == 1 && !owned_frees && !local_frees, "success-owner-retained");
        REQUIRE(irq_calls == NSS_MAX_IRQ_PER_CORE && enables == NSS_MAX_IRQ_PER_CORE && handlers == 5 && resets == 1 && boots == 1, "success-full-probe");
        REQUIRE(!unm_n && !unm_v && pd_frees == NSS_DT_SUPPORT, "success-mapping-retained");
        for (int i = 0; i < NSS_MAX_CLIENTS; i++)
            REQUIRE(!ctx->queue_decongestion_callback[i] && !ctx->queue_decongestion_ctx[i], "success-callback-init");
        for (int i = 0; i < NSS_N2H_DESC_RING_NUM; i++)
            REQUIRE(!ctx->n2h_desc_ring[i].head && !ctx->n2h_desc_ring[i].tail && !ctx->n2h_desc_ring[i].jumbo_start, "success-ring-init");
    } else {
        /* Baseline's late allocator NULL currently returns zero after meminfo commit. */
        REQUIRE(!EXPECT_EARLY && allocs == 1 && !dummy_live && !ctx->napi_ndev && mem_calls == 1 && !irq_calls, "baseline-late-oom");
    }
    if (mem_calls && test->fail != MEMINFO)
        REQUIRE(!memcmp(&ctx->meminfo_ctx, &committed, sizeof(committed)), "meminfo-commit-retained");
    else REQUIRE(!memcmp(&ctx->meminfo_ctx, &before.nss[core].meminfo_ctx, sizeof(committed)), "meminfo-unmodified");
    REQUIRE(local_frees + owned_frees <= 1, "dummy-freed-once");
    emit_state("probe", ret);
    trace[0] = 0;
    if (ret) host_failed_probe_cleanup();
    if (EXPECT_EARLY && test->oom && !test->closed)
        REQUIRE(managed_releases == 0 && global_regulator == before_regulator, "oom-zero-managed-releases");
    emit_state("host-failure-boundary", ret);
}
int main(int argc, char **argv)
{
    REQUIRE(argc == 1 || argc == 3, "fixture-arguments");
    int runs = 0;
    for (core = 0; core < 2; core++) {
        for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
            test = &cases[i]; scenario = test->name;
            if (argc == 3 && (strcmp(argv[1], scenario) || strcmp(argv[2], core ? "1" : "0"))) continue;
            run_case(); runs++;
        }
    }
    REQUIRE(runs > 0, "fixture-case-exists");
    return 0;
}
