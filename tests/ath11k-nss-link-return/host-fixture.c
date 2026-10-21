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
static unsigned held_locks, bh_order_failures, publication_failures;
static unsigned transaction_state_failures, unlock_window_failures;
static spinlock_t *transaction_lock;
static int bh_depth;
static u64 signature = UINT64_C(1469598103934665603);
static void check(bool ok) { checks++; failures += !ok; }
static void check_transaction(bool ok)
{
    check(ok);
    transaction_state_failures += !ok;
}
static void digest(const void *ptr, size_t size)
{
    const unsigned char *bytes = ptr;
    for (size_t i = 0; i < size; i++) {
        signature ^= bytes[i];
        signature *= UINT64_C(1099511628211);
    }
}
static void spin_lock(spinlock_t *lock)
{
    check(!lock->held);
    if (!lock->held) {
        lock->held = true;
        held_locks++;
    }
}
static void spin_unlock(spinlock_t *lock)
{
    check(lock->held && held_locks > 0);
    check(transaction_lock != lock);
    unlock_window_failures += transaction_lock == lock;
    if (lock->held) {
        lock->held = false;
        if (held_locks)
            held_locks--;
    }
}
static void local_bh_enable(void)
{
    check(bh_depth > 0);
    if (bh_depth == 1) {
        check(held_locks == 0);
        bh_order_failures += held_locks != 0;
    }
    bh_depth--;
}
static void spin_lock_bh(spinlock_t *lock) { bh_depth++; spin_lock(lock); }
static void spin_unlock_bh(spinlock_t *lock) { spin_unlock(lock); local_bh_enable(); }
#define lockdep_assert_held(lock) check((lock)->held)

HOST_STRUCTURES

struct ath11k_dp { struct { int ring_id; } wbm_desc_rel_ring; };
struct ath11k_base { struct ath11k_dp dp; struct { struct hal_srng srng_list[3]; } hal; };
static struct {
    struct hal_srng *ring;
    u32 *slot;
    unsigned slot_word, hp, reap_hp;
    struct hal_wbm_release_ring descriptor;
} publication;
static void check_publication(bool ok)
{
    check(ok);
    publication_failures += !ok;
}
static void ath11k_hal_srng_access_begin(struct ath11k_base *ab, struct hal_srng *ring)
{
    (void)ab;
    check(ring->lock.held && bh_depth > 0);
    check(ring == publication.ring && begins == ends);
    check_transaction(transaction_lock == NULL);
    if (!transaction_lock)
        transaction_lock = &ring->lock;
    begins++;
}
static void ath11k_hal_srng_access_end(struct ath11k_base *ab, struct hal_srng *ring)
{
    (void)ab;
    check(ring->lock.held && bh_depth > 0);
    check(begins == ends + 1);
    check_transaction(transaction_lock == &ring->lock);
    check_publication(ring == publication.ring);
    check_publication(ring->u.src_ring.hp == publication.hp);
    check_publication(ring->u.src_ring.reap_hp == publication.reap_hp);
    check_publication(ring->ring_base_vaddr + publication.slot_word == publication.slot);
    check_publication(!memcmp(publication.slot, &publication.descriptor, sizeof(publication.descriptor)));
    ends++;
    if (transaction_lock == &ring->lock)
        transaction_lock = NULL;
}

HOST_FUNCTIONS

int main(void)
{
    const unsigned sizes[] = { 2, 3, 8 };
    const int nesting[] = { 0, 1, 4 };
    u32 seeds[68] = { 0, UINT32_MAX, UINT32_C(0xa5a5a5a5), UINT32_C(0x5a5a5a5a) };
    const unsigned seed_count = sizeof(seeds) / sizeof(seeds[0]);
    const unsigned entry_words = sizeof(struct hal_wbm_release_ring) / sizeof(u32);
    _Static_assert(sizeof(struct hal_wbm_release_ring) == 32, "descriptor ABI");
    for (unsigned bit = 0; bit < 32; bit++) {
        seeds[4 + bit * 2] = UINT32_C(1) << bit;
        seeds[5 + bit * 2] = ~(UINT32_C(1) << bit);
    }
    for (unsigned seed = 0; seed < seed_count; seed++)
    for (unsigned selected = 0; selected < 3; selected++)
    for (unsigned depth = 0; depth < 3; depth++)
    for (unsigned size = 0; size < 3; size++)
    for (unsigned slot = 0; slot < sizes[size]; slot++)
    for (unsigned full = 0; full < 2; full++) {
        struct ath11k_base ab = { 0 };
        u32 storage[3][8 * 8], before[3][8 * 8];
        struct ath11k_buffer_addr address = { .info0 = 0x12345678, .info1 = 0xabcdef00 };
        for (unsigned i = 0; i < 3; i++)
            for (unsigned word = 0; word < 8 * 8; word++)
                storage[i][word] = seeds[seed];
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
        held_locks = 0;
        transaction_lock = NULL;
        begins = ends = 0;
        scenarios++;
        for (unsigned repeat = 0; repeat < 4; repeat++) {
            unsigned hp = ring->u.src_ring.hp;
            unsigned next = (hp + entry_words) % ring->ring_size;
            unsigned previous_reap = ring->u.src_ring.reap_hp;
            address.info0 = UINT32_C(0x12345678) + repeat;
            address.info1 = UINT32_C(0xabcdef00) ^ (repeat << 11);
            ring->u.src_ring.cached_tp = full ? next : (next + entry_words) % ring->ring_size;
            memcpy(before, storage, sizeof(before));
            struct hal_wbm_release_ring expected;
            memcpy(&expected, &storage[selected][hp], sizeof(expected));
            expected.buf_addr_info = address;
            /* Independent SW/MSDU-link/PUT_IN_IDLE oracle, not the extracted setter. */
            expected.info0 |= UINT32_C(0x44);
            publication.ring = ring;
            publication.slot = &storage[selected][hp];
            publication.slot_word = hp;
            publication.hp = full ? hp : next;
            publication.reap_hp = full ? previous_reap : next;
            memcpy(&publication.descriptor, publication.slot, sizeof(publication.descriptor));
            if (!full)
                publication.descriptor = expected;
            ath11k_nss_wifili_link_desc_return(&ab, &address);
            calls++;
            check(!ring->lock.held);
            check(held_locks == 0);
            check(bh_depth == nesting[depth]);
            check(begins == repeat + 1 && ends == repeat + 1);
            check_transaction(transaction_lock == NULL);
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
    printf("{\"seeds\":%u,\"scenarios\":%u,\"calls\":%u,\"checks\":%u,\"failures\":%u,"
           "\"bh_order_failures\":%u,\"publication_failures\":%u,"
           "\"transaction_state_failures\":%u,\"unlock_window_failures\":%u,\"normal_signature\":\"%016llx\"}\n",
           seed_count, scenarios, calls, checks, failures, bh_order_failures,
           publication_failures, transaction_state_failures, unlock_window_failures,
           (unsigned long long)signature);
    return failures ? 1 : 0;
}
