typedef u32 phandle;
#define EPROBE_DEFER 517
#define IORESOURCE_MEM 0
#define PAGE_SIZE 4096
#define DMA_FROM_DEVICE 2
#define ATH11K_FLAG_MULTI_MSI_VECTORS 0
#define lower_32_bits(value) ((u32)(value))
#define upper_32_bits(value) ((u32)((uint64_t)(value) >> 32))
#define ath11k_dbg(...) ((void)0)
static struct ath11k_ahb *ath11k_ahb_priv(struct ath11k_base *ab);
struct rproc { unsigned unused; };
static struct rproc provider_rproc;
struct resource { uint64_t start, end; };
static struct resource provider_memory = { .start = 0xdead0000, .end = 0xdead0fff };
static bool host_rproc_present, map_live, expected_at_drain;
static unsigned rproc_refs, rproc_get_calls, put_calls, map_calls, unmap_calls;
static unsigned drain_checks, msi_irq_fail_at, msi_irq_calls;
static dma_addr_t next_dma, original_dma;
static struct device *original_dma_device;
static void provider_reset(void)
{
    host_rproc_present = true;
    map_live = expected_at_drain = false;
    rproc_refs = rproc_get_calls = put_calls = map_calls = unmap_calls = 0;
    drain_checks = msi_irq_fail_at = msi_irq_calls = 0;
    next_dma = original_dma = 0;
    original_dma_device = NULL;
}
static int of_property_read_u32(struct device_node *node, const char *name, phandle *value)
{
    (void)node; (void)name; *value = 1;
    return failed(RPROC);
}
static struct rproc *rproc_get_by_phandle(phandle value)
{
    (void)value;
    if (!host_rproc_present) return NULL;
    rproc_refs++; rproc_get_calls++;
    return &provider_rproc;
}
static void rproc_put(struct rproc *rproc)
{
    if (rproc != &provider_rproc || rproc_refs != 1 || core_live || live_irqs || pcic_live)
        bad_api++;
    if (rproc_refs) rproc_refs--;
    put_calls++;
}
static int ath11k_pcic_init_msi_config(struct ath11k_base *ab)
{
    if (failed(MSI_CONFIG)) return -EIO;
    return host_real_msi_config(ab);
}
static struct resource *platform_get_resource(struct platform_device *pdev, unsigned type, unsigned number)
{
    (void)pdev; (void)type; (void)number;
    return failed(MSI_RESOURCE) ? NULL : &provider_memory;
}
static dma_addr_t dma_map_resource(struct device *device, uint64_t pa, size_t size, int direction, unsigned attrs)
{
    if (map_live || pa != provider_memory.start || size != PAGE_SIZE || direction != DMA_FROM_DEVICE || attrs)
        bad_api++;
    if (failed(MSI_MAP)) return UINT64_MAX;
    map_live = true;
    map_calls++;
    original_dma = next_dma;
    original_dma_device = device;
    return next_dma;
}
static bool dma_mapping_error(struct device *device, dma_addr_t address)
{
    (void)device;
    return address == UINT64_MAX;
}
static void dma_unmap_resource(struct device *device, dma_addr_t address, size_t size, int direction, unsigned attrs)
{
    if (!map_live || device != original_dma_device || address != original_dma ||
        size != PAGE_SIZE || direction != DMA_FROM_DEVICE || attrs || core_live || live_irqs || pcic_live)
        bad_api++;
    map_live = false;
    unmap_calls++;
}
static int of_property_read_u32_index(struct device_node *node, const char *name, unsigned index, int *value)
{
    (void)node; (void)name;
    if (index != 1) bad_api++;
    *value = 17;
    return failed(MSI_PROPERTY);
}
static int platform_get_irq(struct platform_device *device, unsigned number)
{
    (void)device; msi_irq_calls++;
    if (msi_irq_fail_at == msi_irq_calls) return -EPROBE_DEFER;
    return number + 32;
}
static void set_bit(unsigned number, unsigned long *flags) { *flags |= 1UL << number; }
static void *devm_platform_get_and_ioremap_resource(struct platform_device *pdev, unsigned number, struct resource **resource)
{
    (void)pdev; (void)number; *resource = &provider_memory;
    return failed(RESOURCES) ? ERR_PTR(-EIO) : &provider_memory;
}
static size_t resource_size(const struct resource *resource) { return resource->end - resource->start + 1; }
static void provider_core_free(struct ath11k_base *ab)
{
    if (core_live) free_live_core++;
    if (expected_at_drain) {
        drain_checks++;
        if (rproc_refs != 1 || map_live != selected_hybrid) bad_api++;
    }
    release(BASE_ALLOC);
    /* Catch any post-core_free access through ab or its private data. */
    memset(ab, 0xa5, sizeof(*ab));
}
