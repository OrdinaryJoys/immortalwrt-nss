#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint8_t u8;
typedef uint64_t dma_addr_t;
#define __packed __attribute__((packed))
#define GFP_KERNEL 0
#define DMA_FROM_DEVICE 0
#define HAL_WBM_IDLE_LINK 1
#define HAL_RXDMA_MONITOR_DESC 2
#define ath11k_warn(...) ((void)0)
HOST_CONSTANTS
HOST_TYPES
struct list_head { int initialized; };
#define INIT_LIST_HEAD(p) ((p)->initialized = 1)
#define spin_lock_init(p) (*(p) = 1)
#define idr_init(p) (*(p) = 1)
struct hal_srng { int unused; };
struct ath11k_base;
struct ath11k_dp {
    struct ath11k_base *ab;
    struct list_head reo_cmd_list, reo_cmd_cache_flush_list, reo_cmd_update_rx_queue_list, dp_full_mon_mpdu_list;
    int reo_cmd_lock, reo_cmd_update_queue_lock, reo_cmd_cache_flush_count;
    struct dp_srng wbm_idle_ring;
    struct dp_link_desc_bank link_desc_banks[DP_LINK_DESC_BANKS_MAX];
    struct hal_wbm_idle_scatter_list scatter_list[DP_IDLE_SCATTER_BUFS_MAX];
    struct { int txbuf_idr, tx_idr_lock, tcl_data_ring_id, tx_status_head, tx_status_tail; void *tx_status; } tx_ring[DP_TCL_NUM_RING_MAX];
};
struct ath11k_base { void *dev; struct ath11k_dp dp; struct { struct hal_srng srng_list[1]; } hal; };
enum kind { IDLE, BANK, SCATTER, COMMON, TX };
struct allocation { void *pointer; size_t size; enum kind kind; bool live; };
static struct allocation ledger[256];
static unsigned allocations, api_errors, checks, failures, scenarios, tx_calls, dscp_calls;
static unsigned event_count;
static uint64_t trace, normal_signature;
static int fail_stage, link_variant, cached_ring;
static void *common;
static void event(unsigned value) { trace = trace * 131 + value; event_count++; }
static void check(bool ok) { checks++; if (!ok) failures++; }
static unsigned live_count(void)
{
    unsigned count = 0;
    for (unsigned i = 0; i < allocations; i++) count += ledger[i].live;
    return count;
}
static void *allocate(enum kind kind, size_t size)
{
    if (allocations == 256) exit(90);
    void *pointer = malloc(size);
    if (!pointer) exit(91);
    ledger[allocations++] = (struct allocation){pointer, size, kind, true};
    event(10 + kind);
    return pointer;
}
static void release(void *pointer, size_t size, bool dma)
{
    if (!pointer) return;
    for (unsigned i = 0; i < allocations; i++) {
        if (!ledger[i].live || ledger[i].pointer != pointer) continue;
        if (dma && ledger[i].size != size) api_errors++;
        ledger[i].live = false;
        event(20 + ledger[i].kind);
        free(pointer);
        return;
    }
    api_errors++;
}
static void kfree(void *pointer) { release(pointer, 0, false); }
static void dma_free_coherent(void *dev, size_t size, void *pointer, dma_addr_t address)
{
    (void)dev; (void)address; release(pointer, size, true);
}
static void dma_free_noncoherent(void *dev, size_t size, void *pointer, dma_addr_t address, int direction)
{
    if (direction != DMA_FROM_DEVICE) api_errors++;
    dma_free_coherent(dev, size, pointer, address);
}
static void *kmalloc(size_t size, int flags)
{
    (void)flags;
    unsigned slot = tx_calls++;
    if (fail_stage == (int)(4 + slot)) return NULL;
    return allocate(TX, size);
}
static void ath11k_dp_link_desc_bank_free(struct ath11k_base *, struct dp_link_desc_bank *);
static void ath11k_dp_scatter_idle_link_desc_cleanup(struct ath11k_base *);
static void ath11k_dp_srng_cleanup(struct ath11k_base *, struct dp_srng *);
static void ath11k_dp_link_desc_cleanup(struct ath11k_base *, struct dp_link_desc_bank *, u32, struct dp_srng *);
static int ath11k_wbm_idle_ring_setup(struct ath11k_base *ab, u32 *count)
{
    if (fail_stage == 1) return -EIO;
    *count = 64;
    ab->dp.wbm_idle_ring = (struct dp_srng){ .vaddr_unaligned = allocate(IDLE, 64),
        .size = 64, .cached = cached_ring, .ring_id = 0 };
    return 0;
}
static int ath11k_dp_link_desc_setup(struct ath11k_base *ab, struct dp_link_desc_bank *banks,
                                    u32 type, struct hal_srng *srng, u32 count)
{
    (void)type; (void)srng; (void)count;
    if (fail_stage == 2 && link_variant == 0) return -EINVAL;
    for (int i = 0; i < 2; i++) {
        banks[i].size = 64;
        banks[i].vaddr_unaligned = allocate(BANK, banks[i].size);
    }
    if (fail_stage == 2 && link_variant == 1) {
        ath11k_dp_link_desc_bank_free(ab, banks);
        return -ENOMEM;
    }
    for (int i = 0; i < 2; i++) ab->dp.scatter_list[i].vaddr = allocate(SCATTER, HAL_WBM_IDLE_SCATTER_BUF_SIZE_MAX);
    if (fail_stage == 2) {
        ath11k_dp_scatter_idle_link_desc_cleanup(ab);
        ath11k_dp_link_desc_bank_free(ab, banks);
        return -ENOMEM;
    }
    return 0;
}
static void ath11k_dp_srng_common_cleanup(struct ath11k_base *ab)
{
    (void)ab; kfree(common); common = NULL;
}
static int ath11k_dp_srng_common_setup(struct ath11k_base *ab)
{
    common = allocate(COMMON, 64);
    if (fail_stage == 3) {
        ath11k_dp_srng_common_cleanup(ab);
        return -EIO;
    }
    return 0;
}
static void ath11k_hal_tx_set_dscp_tid_map(struct ath11k_base *ab, int index)
{
    (void)ab;
    if (index != (int)dscp_calls) api_errors++;
    dscp_calls++;
}
HOST_FUNCTIONS
static bool slots_empty(struct ath11k_base *ab)
{
    for (int i = 0; i < DP_TCL_NUM_RING_MAX; i++)
        if (ab->dp.tx_ring[i].tx_status) return false;
    return true;
}
static void success_cleanup(struct ath11k_base *ab)
{
    ath11k_dp_link_desc_cleanup(ab, ab->dp.link_desc_banks, HAL_WBM_IDLE_LINK, &ab->dp.wbm_idle_ring);
    ath11k_dp_srng_common_cleanup(ab);
    for (int i = 0; i < DP_TCL_NUM_RING_MAX; i++) {
        kfree(ab->dp.tx_ring[i].tx_status);
        ab->dp.tx_ring[i].tx_status = NULL;
    }
}
static void check_success(struct ath11k_base *ab, int result)
{
    check(result == 0);
    check(dscp_calls == HAL_DSCP_TID_MAP_TBL_NUM_ENTRIES_MAX);
    check(tx_calls == DP_TCL_NUM_RING_MAX);
    check(ab->dp.ab == ab);
    check(ab->dp.reo_cmd_list.initialized && ab->dp.reo_cmd_cache_flush_list.initialized &&
          ab->dp.reo_cmd_update_rx_queue_list.initialized && ab->dp.dp_full_mon_mpdu_list.initialized);
    check(ab->dp.reo_cmd_lock == 1 && ab->dp.reo_cmd_update_queue_lock == 1);
    for (int i = 0; i < DP_TCL_NUM_RING_MAX; i++) {
        check(ab->dp.tx_ring[i].tx_status != NULL);
        check(ab->dp.tx_ring[i].tcl_data_ring_id == i);
        check(ab->dp.tx_ring[i].tx_status_head == 0);
        check(ab->dp.tx_ring[i].tx_status_tail == DP_TX_COMP_RING_SIZE - 1);
        check(ab->dp.tx_ring[i].txbuf_idr == 1 && ab->dp.tx_ring[i].tx_idr_lock == 1);
    }
}
int main(void)
{
    for (cached_ring = 0; cached_ring < 2; cached_ring++)
    for (link_variant = 0; link_variant < 3; link_variant++)
    for (int stage = 0; stage < 4 + DP_TCL_NUM_RING_MAX; stage++) {
        struct ath11k_base ab = {0};
        scenarios++; allocations = api_errors = tx_calls = dscp_calls = event_count = 0;
        trace = 0; common = NULL; fail_stage = stage;
        int result = ath11k_dp_alloc(&ab);
        if (stage == 0) {
            check_success(&ab, result);
            normal_signature = normal_signature * 131 + trace + event_count + DP_TX_COMP_RING_SIZE;
            success_cleanup(&ab);
        } else {
            int expected = stage == 1 || stage == 3 ? -EIO :
                stage == 2 && link_variant == 0 ? -EINVAL : -ENOMEM;
            check(result == expected);
            check(!dscp_calls);
            check(!live_count());
            check(slots_empty(&ab));
            check(!ab.dp.wbm_idle_ring.vaddr_unaligned && !common);
            check(!api_errors);
            /* Retry the same object without emergency cleanup between calls. */
            fail_stage = 0; tx_calls = dscp_calls = 0;
            check_success(&ab, ath11k_dp_alloc(&ab));
            success_cleanup(&ab);
        }
        check(!live_count()); check(slots_empty(&ab)); check(!api_errors);
        /* Keep assertion-negative runs sanitizer-clean after recording leaks. */
        for (unsigned i = 0; i < allocations; i++)
            if (ledger[i].live) { free(ledger[i].pointer); ledger[i].live = false; }
    }
    printf("{\"checks\":%u,\"failures\":%u,\"scenarios\":%u,\"normal_signature\":\"%llu\","
           "\"tx_comp_ring_size\":%u,\"api_models\":true}\n", checks, failures, scenarios,
           (unsigned long long)normal_signature, DP_TX_COMP_RING_SIZE);
    return failures ? 1 : 0;
}
