#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
#define GFP_KERNEL 0
#define DMA_FROM_DEVICE 1
#define ath11k_warn(...) ((void)0)
#define fallthrough __attribute__((fallthrough))
#define PTR_ALIGN(p, a) ((__typeof__(p))(((uintptr_t)(p) + (a) - 1) & ~((uintptr_t)(a) - 1)))
HOST_CONSTANTS
HOST_TYPES
struct ath11k_base { void *dev; struct { bool alloc_cacheable_memory; } hw_params; };
static int stage;
static bool allocation_cached, live;
static void *allocated;
static size_t allocation_size;
static unsigned checks, failures, scenarios, api_errors, hal_calls;
static struct hal_srng_params received;
static uint64_t normal_signature;
static void check(bool ok) { checks++; if (!ok) failures++; }
static void *host_allocate(size_t size, dma_addr_t *address, bool cached)
{
    if (live) api_errors++;
    if (stage == 3) return NULL;
    allocated = malloc(size);
    if (!allocated) exit(90);
    *address = 0x1000;
    allocation_size = size; allocation_cached = cached; live = true;
    return allocated;
}
static void host_free(size_t size, void *pointer, bool cached)
{
    if (!live || pointer != allocated) { api_errors++; return; }
    if (size != allocation_size || cached != allocation_cached) api_errors++;
    free(allocated); live = false;
}
static void *dma_alloc_coherent(void *dev, size_t size, dma_addr_t *address, int flags)
{
    (void)dev; (void)flags; return host_allocate(size, address, false);
}
static void *dma_alloc_noncoherent(void *dev, size_t size, dma_addr_t *address, int direction, int flags)
{
    if (direction != DMA_FROM_DEVICE) api_errors++;
    (void)dev; (void)flags; return host_allocate(size, address, true);
}
static void dma_free_coherent(void *dev, size_t size, void *pointer, dma_addr_t address)
{
    (void)dev; (void)address; host_free(size, pointer, false);
}
static void dma_free_noncoherent(void *dev, size_t size, void *pointer, dma_addr_t address, int direction)
{
    (void)dev; (void)address;
    if (direction != DMA_FROM_DEVICE) api_errors++;
    host_free(size, pointer, true);
}
static int ath11k_hal_srng_get_entrysize(struct ath11k_base *ab, enum hal_ring_type type)
{
    (void)ab; (void)type; return stage == 1 ? -EINVAL : 32;
}
static int ath11k_hal_srng_get_max_entries(struct ath11k_base *ab, enum hal_ring_type type)
{
    (void)ab; (void)type; return stage == 2 ? -EINVAL : 64;
}
static void ath11k_dp_srng_msi_setup(struct ath11k_base *ab, struct hal_srng_params *params, enum hal_ring_type type, int ring)
{
    (void)ab; (void)params; (void)type; (void)ring;
}
static int ath11k_hal_srng_setup(struct ath11k_base *ab, enum hal_ring_type type, int ring, int mac, struct hal_srng_params *params)
{
    (void)ab; (void)type; (void)ring; (void)mac; hal_calls++; received = *params;
    return stage == 4 ? -EIO : 7;
}
HOST_FUNCTIONS
static bool valid_type(enum hal_ring_type type)
{
    return type != HAL_CE_SRC && type != HAL_CE_DST && type != HAL_CE_DST_STATUS;
}
int main(void)
{
    for (int cacheable = 0; cacheable < 2; cacheable++)
    for (int old_cached = 0; old_cached < 2; old_cached++)
    for (int type = 0; type < HAL_MAX_RING_TYPES; type++)
    for (int index = 0; index < 2; index++)
    for (stage = 0; stage < 5; stage++) {
        struct ath11k_base ab = { .hw_params.alloc_cacheable_memory = cacheable };
        struct dp_srng ring = { .cached = old_cached };
        int requested = index ? 80 : 16, entries = index ? 64 : 16;
        bool expected_cached = cacheable && (type == HAL_REO_DST || type == HAL_WBM2SW_RELEASE);
        scenarios++; api_errors = hal_calls = 0; live = false; allocated = NULL;
        int ret = ath11k_dp_srng_setup(&ab, &ring, type, index ? 3 : 0, 0, requested);
        int expected = stage == 1 || stage == 2 ? -EINVAL : stage == 3 ? -ENOMEM :
            !valid_type(type) ? -EINVAL : stage == 4 ? -EIO : 0;
        check(ret == expected);
        if (!expected) {
            check(live && ring.vaddr_unaligned == allocated);
            check(ring.cached == expected_cached);
            check(ring.ring_id == 7 && hal_calls == 1);
            check(received.num_entries == entries);
            check(received.ring_base_vaddr == ring.vaddr && received.ring_base_paddr == ring.paddr);
            check(!!(received.flags & HAL_SRNG_FLAGS_CACHED) == expected_cached);
            if (type == HAL_WBM2SW_RELEASE)
                check(received.intr_timer_thres_us == (index ? HAL_SRNG_INT_TIMER_THRESHOLD_OTHER : HAL_SRNG_INT_TIMER_THRESHOLD_TX));
            if (old_cached == 0)
                normal_signature = normal_signature * 131 + received.flags + received.num_entries +
                    received.intr_timer_thres_us + received.intr_batch_cntr_thres_entries + ring.cached;
            ath11k_dp_srng_cleanup(&ab, &ring);
        }
        check(!live);
        check(ring.vaddr_unaligned == NULL);
        check(!api_errors);
        ath11k_dp_srng_cleanup(&ab, &ring);
        check(!live && !api_errors);
        if (live) { free(allocated); live = false; }
    }
    printf("{\"checks\":%u,\"failures\":%u,\"scenarios\":%u,\"normal_signature\":\"%llu\",\"api_models\":true}\n",
        checks, failures, scenarios, (unsigned long long)normal_signature);
    return failures ? 1 : 0;
}
