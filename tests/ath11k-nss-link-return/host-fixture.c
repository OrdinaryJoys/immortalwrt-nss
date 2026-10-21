#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint64_t dma_addr_t;
typedef struct { bool held; } spinlock_t;
#define __packed __attribute__((packed))
#define GENMASK(h, l) ((UINT32_MAX >> (31 - (h))) & (UINT32_MAX << (l)))
#define FIELD_PREP(mask, value) (((u32)(value) << __builtin_ctz(mask)) & (mask))

static unsigned checks, failures, scenarios, calls, begins, ends;
static int bh_depth;
static u64 signature = UINT64_C(1469598103934665603);
static void check(bool ok) { checks++; failures += !ok; }
static void digest(const void *ptr, size_t size)
{
    const unsigned char *bytes = ptr;
    for (size_t i = 0; i < size; i++) {
        signature ^= bytes[i];
        signature *= UINT64_C(1099511628211);
    }
}
static void spin_lock(spinlock_t *lock) { check(!lock->held); lock->held = true; }
static void spin_unlock(spinlock_t *lock) { check(lock->held); lock->held = false; }
static void local_bh_enable(void) { check(bh_depth > 0); bh_depth--; }
static void spin_lock_bh(spinlock_t *lock) { bh_depth++; spin_lock(lock); }
static void spin_unlock_bh(spinlock_t *lock) { spin_unlock(lock); local_bh_enable(); }
#define lockdep_assert_held(lock) check((lock)->held)

HOST_STRUCTURES

struct ath11k_dp { struct { int ring_id; } wbm_desc_rel_ring; };
struct ath11k_base { struct ath11k_dp dp; struct { struct hal_srng srng_list[3]; } hal; };
static void ath11k_hal_srng_access_begin(struct ath11k_base *ab, struct hal_srng *ring)
{
    (void)ab;
    check(ring->lock.held && bh_depth > 0);
    begins++;
}
static void ath11k_hal_srng_access_end(struct ath11k_base *ab, struct hal_srng *ring)
{
    (void)ab;
    check(ring->lock.held && bh_depth > 0);
    ends++;
}

HOST_FUNCTIONS

int main(void)
{
    const unsigned sizes[] = { 2, 3, 8 };
    const int nesting[] = { 0, 1, 4 };
    const unsigned entry_words = sizeof(struct hal_wbm_release_ring) / sizeof(u32);
    _Static_assert(sizeof(struct hal_wbm_release_ring) == 32, "descriptor ABI");
    for (unsigned selected = 0; selected < 3; selected++)
    for (unsigned depth = 0; depth < 3; depth++)
    for (unsigned size = 0; size < 3; size++)
    for (unsigned slot = 0; slot < sizes[size]; slot++)
    for (unsigned full = 0; full < 2; full++) {
        struct ath11k_base ab = { 0 };
        u32 storage[3][8 * 8], before[3][8 * 8];
        struct ath11k_buffer_addr address = { .info0 = 0x12345678, .info1 = 0xabcdef00 };
        memset(storage, 0xa5, sizeof(storage));
        for (unsigned i = 0; i < 3; i++) {
            ab.hal.srng_list[i].ring_id = i;
            ab.hal.srng_list[i].initialized = 1;
            ab.hal.srng_list[i].ring_dir = HAL_SRNG_DIR_SRC;
            ab.hal.srng_list[i].num_entries = sizes[size];
            ab.hal.srng_list[i].ring_base_vaddr = storage[i];
            ab.hal.srng_list[i].ring_size = sizes[size] * entry_words;
            ab.hal.srng_list[i].entry_size = entry_words;
            ab.hal.srng_list[i].u.src_ring.hp = slot * entry_words;
        }
        ab.dp.wbm_desc_rel_ring.ring_id = selected;
        struct hal_srng *ring = &ab.hal.srng_list[selected];
        bh_depth = nesting[depth];
        begins = ends = 0;
        scenarios++;
        for (unsigned repeat = 0; repeat < 4; repeat++) {
            unsigned hp = ring->u.src_ring.hp;
            unsigned next = (hp + entry_words) % ring->ring_size;
            unsigned previous_reap = ring->u.src_ring.reap_hp;
            ring->u.src_ring.cached_tp = full ? next : (next + entry_words) % ring->ring_size;
            memcpy(before, storage, sizeof(before));
            struct hal_wbm_release_ring expected;
            memcpy(&expected, &storage[selected][hp], sizeof(expected));
            expected.buf_addr_info = address;
            expected.info0 |= UINT32_C(0x44);
            ath11k_nss_wifili_link_desc_return(&ab, &address);
            calls++;
            check(!ring->lock.held);
            check(bh_depth == nesting[depth]);
            check(begins == repeat + 1 && ends == repeat + 1);
            check(ring->u.src_ring.hp == (full ? hp : next));
            check(ring->u.src_ring.reap_hp == (full ? previous_reap : next));
            if (!full)
                memcpy(&before[selected][hp], &expected, sizeof(expected));
            check(!memcmp(before, storage, sizeof(storage)));
            for (unsigned i = 0; i < 3; i++)
                check(!ab.hal.srng_list[i].lock.held);
            digest(storage, sizeof(storage));
            digest(&ring->u.src_ring.hp, sizeof(ring->u.src_ring.hp));
            digest(&ring->u.src_ring.reap_hp, sizeof(ring->u.src_ring.reap_hp));
        }
    }
    printf("{\"scenarios\":%u,\"calls\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%016llx\"}\n",
           scenarios, calls, checks, failures, (unsigned long long)signature);
    return failures ? 1 : 0;
}
