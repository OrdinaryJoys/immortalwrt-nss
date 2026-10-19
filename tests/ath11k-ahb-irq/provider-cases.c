/* Real driver functions are inserted by the runner; providers are substitutes. */
static void failed_probe(unsigned hybrid, enum stage stage,
                         enum fault fault, unsigned at)
{
    reset(true, 0xaaa);
    selected_hybrid = hybrid;
    selected_rev = hybrid == 2 ? ATH11K_HW_QCN6122_HW10 :
                   hybrid ? ATH11K_HW_WCN6750_HW10 : ATH11K_HW_IPQ8074;
    fail_stage = stage;
    fault_kind = fault;
    fault_at = at;
    struct platform_device device = {0};
    CHECK(ath11k_ahb_probe(&device) < 0);
    CHECK(!live_resources && !core_live && !free_live_core && !device.data);
    CHECK(no_irq_resources());
    CHECK(!rproc_refs && !map_live && !bad_api);
    CHECK(put_calls == rproc_get_calls && unmap_calls == map_calls);
}

static void provider_matrix(void)
{
    for (unsigned hybrid = 0; hybrid < 3; hybrid++) {
        for (unsigned stage = DMA; stage <= CORE_INIT; stage++) {
            if (hybrid && stage == RESOURCES) continue;
            failed_probe(hybrid, stage, NONE, 0);
        }
        if (hybrid) {
            for (unsigned stage = MSI_CONFIG; stage <= MSI_PROPERTY; stage++)
                failed_probe(hybrid, stage, NONE, 0);
            reset(true, 0);
            selected_hybrid = true;
            selected_rev = hybrid == 2 ? ATH11K_HW_QCN6122_HW10 : ATH11K_HW_WCN6750_HW10;
            struct platform_device device = {0};
            CHECK(ath11k_ahb_probe(&device) == 0);
            unsigned vectors = base.pci.msi.config->total_vectors;
            core_live = false; /* Upper-level teardown is outside this fixture. */
            ath11k_ahb_free_resources(&base);
            CHECK(!rproc_refs && !map_live && !bad_api);
            for (unsigned at = 1; at <= vectors; at++) {
                reset(true, 0);
                selected_hybrid = true;
                selected_rev = hybrid == 2 ? ATH11K_HW_QCN6122_HW10 : ATH11K_HW_WCN6750_HW10;
                msi_irq_fail_at = at;
                struct platform_device failed = {0};
                CHECK(ath11k_ahb_probe(&failed) == -EPROBE_DEFER);
                CHECK(!failed.data && !map_live && !rproc_refs && !bad_api);
                CHECK(unmap_calls == 1 && !put_calls);
            }
        }
    }
    reset(true, 0xaaa);
    struct platform_device device = {0};
    CHECK(ath11k_ahb_probe(&device) == 0);
    unsigned lookups = lookup_calls, requests = request_calls, allocs = allocation_calls;
    core_live = false;
    ath11k_ahb_free_resources(&base);
    CHECK(!rproc_refs && !bad_api);
    for (unsigned kind = LOOKUP; kind <= ALLOCATION; kind++) {
        unsigned count = kind == LOOKUP ? lookups : kind == REQUEST ? requests : allocs;
        for (unsigned at = 1; at <= count; at++)
            failed_probe(0, 0, kind, at);
    }
    for (unsigned hybrid = 0; hybrid < 3; hybrid++) {
        reset(true, 0);
        selected_hybrid = hybrid != 0;
        selected_rev = hybrid == 2 ? ATH11K_HW_QCN6122_HW10 :
                       hybrid ? ATH11K_HW_WCN6750_HW10 : ATH11K_HW_IPQ8074;
        host_rproc_present = false;
        struct platform_device absent = {0};
        CHECK(ath11k_ahb_probe(&absent) == -EPROBE_DEFER);
        CHECK(!rproc_refs && !map_live && !put_calls && !bad_api);
    }
}

static void successful_lifetimes(void)
{
    const dma_addr_t addresses[] = {0, 0xf0000000ULL, 0x123456789ULL};
    for (unsigned round = 0; round < 4; round++)
    for (unsigned hybrid = 0; hybrid < 3; hybrid++)
    for (unsigned address = 0; address < sizeof(addresses) / sizeof(addresses[0]); address++) {
        reset(round & 1, 0xaaa);
        selected_hybrid = hybrid != 0;
        selected_rev = hybrid == 2 ? ATH11K_HW_QCN6122_HW10 :
                       hybrid ? ATH11K_HW_WCN6750_HW10 : ATH11K_HW_IPQ8074;
        next_dma = addresses[address];
        struct platform_device device = {0};
        CHECK(ath11k_ahb_probe(&device) == 0);
        CHECK(rproc_refs == 1 && !put_calls && core_live);
        CHECK(map_live == (hybrid != 0) && !unmap_calls);
        if (hybrid) {
            CHECK(base.pci.msi.addr_lo == lower_32_bits(next_dma));
            CHECK(base.pci.msi.addr_hi == upper_32_bits(next_dma));
            CHECK(base.pci.msi.ep_base_data == 49);
            /* Cleanup must use the original mapped address, not a consumer copy. */
            base.pci.msi.addr_lo = base.pci.msi.addr_hi = 0xdeadbeef;
        }
        expected_at_drain = true;
        core_live = false;
        ath11k_ahb_free_resources(&base);
        CHECK(!device.data && !rproc_refs && !map_live && !live_resources);
        CHECK(no_irq_resources());
        CHECK(put_calls == 1 && unmap_calls == (hybrid != 0));
        CHECK(drain_checks == 1 && !bad_api);
    }
}

int main(void)
{
    provider_matrix();
    successful_lifetimes();
    printf("{\"checks\":%u,\"failures\":%u,\"scope\":\"actual AHB getter/MSI/probe/finalizer functions; provider/IRQ/workqueue APIs modeled\"}\n",
           checks, failures);
    return failures ? 1 : 0;
}
