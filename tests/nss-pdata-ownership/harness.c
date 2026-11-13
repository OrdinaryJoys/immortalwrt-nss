/* Host API substitutions; the production function is inserted by run.py. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#ifndef HOST_PAD_CONTEXT
#define HOST_PAD_CONTEXT 0
#endif
#define GFP_KERNEL 0
#define NSS_FREQ_LOW_SCALE 0
#define NSS_FREQ_MID_SCALE 1
#define NSS_FREQ_HIGH_SCALE 2
#define SENTINEL_ID 99U

struct device_node { const char *name; int refs; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct resource { uint32_t start, end; };
struct nss_platform_data {
    uint32_t id, load_addr, num_queue, num_irq;
    uint32_t nphys, vphys, qgic_phys, irq[NSS_MAX_IRQ_PER_CORE];
    void *nmap, *vmap, *qgic_map;
};
struct nss_ctx_instance { uint32_t id; void *nmap, *vmap, *qgic_map; };
/* Only invalid-id witness builds pad one cell to avoid executing C UB. */
struct nss_top_instance {
    struct nss_ctx_instance nss[NSS_MAX_CORES + HOST_PAD_CONTEXT];
    uint32_t num_nss;
};
static struct nss_top_instance nss_top_main;
static struct { struct { uint32_t frequency; } freq_scale[3]; } nss_runtime_samples;
static struct {
    const char *name;
    int alloc_fail, prop_fail, resource_fail, map_fail, irq_fail, optional_fail;
    uint32_t id, num_irq, num_nss, tcm_size;
    int success, dynamic, direct_cache;
} cfg;
static struct {
    int gets, puts, allocs, frees, required, optional, resources, map_calls;
    int irqs, features, writes, barriers;
} calls;
static struct { uint32_t bytes[8]; int acquired, released, vmalloc_live; } maps[3];
static uint32_t foreign_maps[NSS_MAX_CORES + HOST_PAD_CONTEXT][3][8];
static struct device_node node, foreign_node;
static struct platform_device device;
static struct nss_platform_data *allocation;
static int allocation_live;

static void check(int condition, const char *tag)
{
    if (!condition) {
        fprintf(stderr, "FAIL:%s:%s\n", cfg.name, tag);
        exit(86);
    }
}
#define CHECK(tag, condition) check((condition), (tag))
#define nss_assert(condition) CHECK("production_assert", (condition))

static void log_message(const char *format, ...) { (void)format; }
#define pr_err log_message
#define nss_info_always log_message

static struct device_node *of_node_get(struct device_node *np)
{
    CHECK("get_local_node", np == &node);
    calls.gets++;
    if (cfg.dynamic) np->refs++;
    return np;
}

static void of_node_put(struct device_node *np)
{
    CHECK("put_local_node", np == &node);
    calls.puts++;
    if (cfg.dynamic) np->refs--;
}

static void *devm_kzalloc(struct device *dev, size_t size, int flags)
{
    CHECK("allocation_owner", dev == &device.dev && size == sizeof(*allocation));
    (void)flags;
    calls.allocs++;
    if (cfg.alloc_fail) return NULL;
    allocation = calloc(1, size);
    CHECK("host_allocation", allocation != NULL);
    allocation_live = 1;
    return allocation;
}

static void devm_kfree(struct device *dev, void *ptr)
{
    CHECK("free_local_pdata_once", dev == &device.dev && ptr == allocation && allocation_live);
    calls.frees++;
    allocation_live = 0;
    free(ptr);
}

static int of_property_read_u32(struct device_node *np, const char *name, uint32_t *value)
{
    static const char *const required[] = {"qcom,id", "qcom,load-addr", "qcom,num-queue", "qcom,num-irq"};
    static const char *const optional[] = {"qcom,low-frequency", "qcom,mid-frequency", "qcom,max-frequency"};
    uint32_t values[] = {cfg.id, 0x4000U, 4U, cfg.num_irq};
    int i;
    CHECK("property_node", np == &node);
    for (i = 0; i < 4; i++) {
        if (!strcmp(name, required[i])) {
            CHECK("required_read_order", calls.required == i);
            calls.required++;
            if (cfg.prop_fail == i) return -1;
            *value = values[i];
            return 0;
        }
    }
    for (i = 0; i < 3; i++) {
        if (!strcmp(name, optional[i])) {
            CHECK("optional_read_order", calls.optional == i);
            calls.optional++;
            if (cfg.optional_fail == i) return -1;
            *value = 600U + (uint32_t)i;
            return 0;
        }
    }
    CHECK("known_property", 0);
    return -1;
}

static int of_address_to_resource(struct device_node *np, int index, struct resource *res)
{
#if HOST_PAD_CONTEXT
    CHECK("invalid_id_no_context_write", nss_top_main.nss[NSS_MAX_CORES].id == SENTINEL_ID);
#endif
    CHECK("resource_node_and_order", np == &node && calls.resources == index);
    calls.resources++;
    if (cfg.resource_fail == index) return -1;
    res->start = (uint32_t)(index + 1) * 0x1000U;
    res->end = res->start + (index == 1 ? cfg.tcm_size : 16U) - 1U;
    return 0;
}

static size_t resource_size(const struct resource *res) { return res->end - res->start + 1U; }

static void *map_resource(uint32_t physical, size_t size, int cached)
{
    int index = calls.map_calls++;
    CHECK("map_arguments", index < 3 && physical == (uint32_t)(index + 1) * 0x1000U);
    CHECK("map_type_and_size", cached == (index == 1) && size == (index == 1 ? cfg.tcm_size : 16U));
    if (cfg.map_fail == index + 1) return NULL;
    maps[index].acquired++;
    maps[index].vmalloc_live = !(cached && cfg.direct_cache);
    return maps[index].bytes;
}

static void *nss_ioremap(uint32_t physical, size_t size) { return map_resource(physical, size, 0); }
static void *ioremap_cache(uint32_t physical, size_t size) { return map_resource(physical, size, 1); }

static void iounmap(void *pointer)
{
    int i;
    for (i = 0; i < 3; i++) {
        if (pointer == maps[i].bytes) {
            CHECK("unmap_acquired_once", maps[i].acquired == 1 && maps[i].released == 0);
            maps[i].released++;
            maps[i].vmalloc_live = 0;
            return;
        }
    }
    CHECK("unmap_local_not_foreign", 0);
}

/* An accidental disposal must fail at runtime, not merely fail compilation. */
void irq_dispose_mapping(unsigned int irq)
{
    (void)irq;
    CHECK("no_irq_disposal_without_ownership", 0);
}

static unsigned int irq_of_parse_and_map(struct device_node *np, int index)
{
    CHECK("irq_node_and_order", np == &node && calls.irqs == index);
    calls.irqs++;
    if (cfg.irq_fail == index) return 0;
    return 100U + (unsigned int)index; /* Deliberately borrowed, pre-existing virqs. */
}

static void nss_write_32(void *map, int32_t offset, uint32_t value)
{
    CHECK("tcm_mapping_live", map == maps[1].bytes && maps[1].acquired && !maps[1].released);
    CHECK("tcm_write_offset_value", offset == calls.writes * 4 && value == 0 && (uint32_t)offset < cfg.tcm_size);
    maps[1].bytes[offset / 4] = value;
    calls.writes++;
    CHECK("tcm_after_all_irqs", calls.irqs == (int)cfg.num_irq && cfg.irq_fail < 0);
}

void barrier(void)
{
    CHECK("barrier_after_tcm", calls.writes == (int)cfg.tcm_size / 4);
    calls.barriers++;
}
#define NSS_CORE_DSB() barrier()

static void nss_hal_dt_parse_features(struct device_node *np, struct nss_platform_data *npd)
{
    CHECK("features_after_barrier", calls.barriers == 1 && np == &node && npd == allocation);
    calls.features++;
}

/* @FUNCTION@ */

static void configure(const char *name, int dynamic, int direct_cache)
{
    int n = -1, i, j, k;
    memset(&cfg, 0, sizeof(cfg));
    memset(&calls, 0, sizeof(calls));
    memset(&maps, 0, sizeof(maps));
    cfg.name = name;
    cfg.dynamic = dynamic;
    cfg.direct_cache = direct_cache;
    cfg.prop_fail = cfg.resource_fail = cfg.irq_fail = cfg.optional_fail = -1;
    cfg.num_irq = NSS_MAX_IRQ_PER_CORE;
    cfg.num_nss = NSS_MAX_CORES;
    cfg.tcm_size = 16;
    if (!strcmp(name, "alloc")) cfg.alloc_fail = 1;
    else if (sscanf(name, "property%d", &n) == 1 && n >= 0 && n < 4) cfg.prop_fail = n;
    else if (!strcmp(name, "irq-count")) cfg.num_irq = NSS_MAX_IRQ_PER_CORE + 1;
    else if (!strcmp(name, "id-bound")) cfg.id = NSS_MAX_CORES;
    else if (!strcmp(name, "id-max")) cfg.id = UINT32_MAX;
    else if (sscanf(name, "resource%d", &n) == 1 && n >= 0 && n < 3) cfg.resource_fail = n;
    else if (sscanf(name, "map%d", &n) == 1 && n >= 1 && n <= 3) cfg.map_fail = n;
    else if (sscanf(name, "irq%d", &n) == 1 && n >= 0 && n < NSS_MAX_IRQ_PER_CORE) cfg.irq_fail = n;
    else if (!strcmp(name, "success0")) { cfg.success = 1; cfg.num_irq = 0; }
    else if (!strcmp(name, "success1")) { cfg.success = 1; cfg.num_irq = 1; }
    else if (!strcmp(name, "success10")) cfg.success = 1;
    else if (!strcmp(name, "last-id-root-one")) { cfg.success = 1; cfg.id = NSS_MAX_CORES - 1; cfg.num_nss = 1; }
    else if (!strcmp(name, "last-id-nine-irqs")) { cfg.success = 1; cfg.id = NSS_MAX_CORES - 1; cfg.num_irq = 9; }
    else if (!strcmp(name, "tcm20")) { cfg.success = 1; cfg.tcm_size = 20; }
    else if (sscanf(name, "optional%d", &n) == 1 && n >= 0 && n < 3) { cfg.success = 1; cfg.optional_fail = n; }
    else CHECK("known_case", 0);
    node = (struct device_node){"nss-local", 5};
    foreign_node = (struct device_node){"foreign-owner", 11};
    device.dev.of_node = &node;
    nss_top_main.num_nss = cfg.num_nss;
    for (i = 0; i < NSS_MAX_CORES + HOST_PAD_CONTEXT; i++) {
        nss_top_main.nss[i] = (struct nss_ctx_instance){SENTINEL_ID, foreign_maps[i][0], foreign_maps[i][1], foreign_maps[i][2]};
        for (j = 0; j < 3; j++) for (k = 0; k < 8; k++) foreign_maps[i][j][k] = 0xabc000U + (uint32_t)i;
    }
    for (i = 0; i < 3; i++) {
        nss_runtime_samples.freq_scale[i].frequency = 400U + (uint32_t)i;
        for (k = 0; k < 8; k++) maps[i].bytes[k] = 0xdeadbeefU;
    }
}

static void verify(struct nss_platform_data *result)
{
    int i, j, k, reached, expected;
    CHECK("return_contract", (result != NULL) == cfg.success);
    CHECK("node_ref_balanced", node.refs == 5 && foreign_node.refs == 11);
    CHECK("node_get_put_balanced", calls.gets == 1 && calls.puts == 1);
    CHECK("pdata_lifetime", calls.allocs == 1 && calls.frees == (!cfg.alloc_fail && !cfg.success) && allocation_live == cfg.success);
    expected = cfg.alloc_fail ? 0 : (cfg.prop_fail < 0 ? 4 : cfg.prop_fail + 1);
    CHECK("required_prefix", calls.required == expected);
    reached = !cfg.alloc_fail && cfg.prop_fail < 0;
    if (cfg.id >= NSS_MAX_CORES) CHECK("invalid_id_frequency_untouched", calls.optional == 0);
    CHECK("optional_prefix", calls.optional == (reached && cfg.id < NSS_MAX_CORES ? 3 : 0));
    for (i = 0; i < 3; i++) {
        expected = reached && cfg.id < NSS_MAX_CORES && cfg.optional_fail != i ? 600 + i : 400 + i;
        CHECK("valid_id_frequency_policy", nss_runtime_samples.freq_scale[i].frequency == (uint32_t)expected);
    }
    reached = reached && cfg.id < NSS_MAX_CORES && cfg.num_irq <= NSS_MAX_IRQ_PER_CORE;
    CHECK("resource_prefix", calls.resources == (reached ? (cfg.resource_fail < 0 ? 3 : cfg.resource_fail + 1) : 0));
    for (i = 0; i < NSS_MAX_CORES + HOST_PAD_CONTEXT; i++) {
        uint32_t expected_id = reached && (uint32_t)i == cfg.id ? cfg.id : SENTINEL_ID;
        CHECK("context_id_scope", nss_top_main.nss[i].id == expected_id);
        CHECK("foreign_context_maps", nss_top_main.nss[i].nmap == foreign_maps[i][0] && nss_top_main.nss[i].vmap == foreign_maps[i][1] && nss_top_main.nss[i].qgic_map == foreign_maps[i][2]);
        for (j = 0; j < 3; j++) for (k = 0; k < 8; k++) CHECK("foreign_map_contents", foreign_maps[i][j][k] == 0xabc000U + (uint32_t)i);
    }
    reached = reached && cfg.resource_fail < 0;
    CHECK("map_prefix", calls.map_calls == (reached ? (cfg.map_fail ? cfg.map_fail : 3) : 0));
    for (i = 0; i < 3; i++) {
        static const char *const tags[] = {"nmap_rollback", "vmap_rollback", "qgic_rollback"};
        expected = reached && (!cfg.map_fail || i + 1 < cfg.map_fail);
        CHECK("map_acquisition_prefix", maps[i].acquired == expected);
        if (cfg.success) CHECK("success_retains_maps", maps[i].released == 0 && maps[i].vmalloc_live == !(i == 1 && cfg.direct_cache));
        else CHECK(tags[i], maps[i].released == expected && maps[i].vmalloc_live == 0);
    }
    reached = reached && !cfg.map_fail;
    CHECK("irq_prefix", calls.irqs == (reached ? (cfg.irq_fail < 0 ? (int)cfg.num_irq : cfg.irq_fail + 1) : 0));
    CHECK("tcm_count", calls.writes == (cfg.success ? (int)cfg.tcm_size / 4 : 0));
    CHECK("barrier_count", calls.barriers == cfg.success);
    CHECK("feature_count", calls.features == cfg.success);
    for (i = 0; i < 8; i++) CHECK("tcm_contents", maps[1].bytes[i] == (cfg.success && (uint32_t)i < cfg.tcm_size / 4 ? 0 : 0xdeadbeefU));
    if (result) {
        CHECK("returned_local_maps", result->nmap == maps[0].bytes && result->vmap == maps[1].bytes && result->qgic_map == maps[2].bytes);
        CHECK("returned_properties", result->id == cfg.id && result->num_irq == cfg.num_irq && result->load_addr == 0x4000U && result->num_queue == 4);
        for (i = 0; i < (int)cfg.num_irq; i++) CHECK("borrowed_irq_retained", result->irq[i] == 100U + (uint32_t)i);
        /* Test-owner cleanup occurs strictly after all retention assertions. */
        for (i = 0; i < 3; i++) iounmap(maps[i].bytes);
        devm_kfree(&device.dev, result);
    }
}

int main(int argc, char **argv)
{
    CHECK("arguments", argc == 4);
    configure(argv[1], atoi(argv[2]), atoi(argv[3]));
    verify(__nss_hal_of_get_pdata(&device));
    printf("PASS:%s:dynamic=%d:direct-cache=%d\n", cfg.name, cfg.dynamic, cfg.direct_cache);
    return 0;
}
