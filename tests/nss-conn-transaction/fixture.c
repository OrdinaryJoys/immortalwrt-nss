#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ESHUTDOWN
#define ESHUTDOWN 108 /* Linux errno, hidden by the macOS POSIX feature set. */
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t __be32;
typedef uintptr_t nss_ptr_t;
typedef uint64_t dma_addr_t;
#include "wire_abi.h"

static const char *test_case;

#define CHECK(condition, id) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%s\n", test_case, id); \
        exit(1); \
    } \
} while (0)

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define max(a, b) ((a) > (b) ? (a) : (b))
#define U32_MAX UINT32_MAX
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(target, value) __atomic_store_n(&(target), (value), __ATOMIC_RELAXED)
#define likely(value) (value)
#define unlikely(value) (value)
#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL << PAGE_SHIFT)
#define MAX_PAGE_ORDER 10
#define GFP_ATOMIC 1u
#define __GFP_NOWARN 2u
#define __GFP_ZERO 4u
/* React to lock-order misuse without pretending to test Linux IRQ semantics. */
typedef pthread_mutex_t spinlock_t;
#define DEFINE_SPINLOCK(name) spinlock_t name = PTHREAD_MUTEX_INITIALIZER
static _Thread_local unsigned lock_depth;

static void lock(spinlock_t *mutex)
{
    CHECK(!lock_depth, "lock-reentry");
    CHECK(!pthread_mutex_lock(mutex), "lock-error");
    ++lock_depth;
}

static void unlock(spinlock_t *mutex)
{
    CHECK(lock_depth == 1, "unlock-unheld");
    --lock_depth;
    CHECK(!pthread_mutex_unlock(mutex), "unlock-error");
}

#define spin_lock_bh(lockvar) lock(lockvar)
#define spin_unlock_bh(lockvar) unlock(lockvar)
#define spin_lock_irqsave(lockvar, flags) do { (flags) = 0; lock(lockvar); } while (0)
#define spin_unlock_irqrestore(lockvar, flags) do { (void)(flags); unlock(lockvar); } while (0)

struct host_wait_queue {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
};
#define DECLARE_WAIT_QUEUE_HEAD(name) \
    struct host_wait_queue name = { PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER }

static void wait_observed(void);
#define wait_event(queue, ready) do { \
    CHECK(!lock_depth, "wait-under-lock"); \
    CHECK(!pthread_mutex_lock(&(queue).mutex), "wait-lock"); \
    while (!(ready)) { \
        wait_observed(); \
        CHECK(!pthread_cond_wait(&(queue).cond, &(queue).mutex), "wait-cond"); \
    } \
    CHECK(!pthread_mutex_unlock(&(queue).mutex), "wait-unlock"); \
} while (0)

static inline void wake_up_all(struct host_wait_queue *queue)
{
    CHECK(!pthread_mutex_lock(&queue->mutex), "wake-lock");
    CHECK(!pthread_cond_broadcast(&queue->cond), "wake-cond");
    CHECK(!pthread_mutex_unlock(&queue->mutex), "wake-unlock");
}

static inline __attribute__((format(printf, 1, 2))) void host_log(const char *fmt, ...)
{
    (void)fmt;
}
#define nss_warning(...) host_log(__VA_ARGS__)
#define nss_info(...) host_log(__VA_ARGS__)
#define nss_trace(...) host_log(__VA_ARGS__)
#define pr_warn_once(...) host_log(__VA_ARGS__)

enum dma_data_direction { DMA_BIDIRECTIONAL, DMA_TO_DEVICE, DMA_FROM_DEVICE, DMA_NONE };
struct device { size_t mapping_limit; };
struct nss_ctx_instance;
typedef void (*nss_core_rx_callback_t)(struct nss_ctx_instance *, struct nss_cmn_msg *, void *);
struct host_rx_handler {
    nss_core_rx_callback_t cb;
    void *app_data;
};
struct host_top {
    void *ipv4_callback, *ipv4_ctx, *ipv6_callback, *ipv6_ctx;
    unsigned int stats_drv[3];
};
struct nss_ctx_instance {
    struct device *dev;
    unsigned int id;
#ifdef HOST_INTEGRATION
    unsigned int state;
    struct host_top *nss_top;
    struct host_rx_handler nss_rx_interface_handlers[NSS_MAX_NET_INTERFACES];
#endif
};

static struct device device4 = { 32768 }, device6 = { 32768 };
static struct nss_ctx_instance core4 = { .dev = &device4, .id = 0 };
static struct nss_ctx_instance core6 = { .dev = &device6, .id = 1 };

enum { CE_LENGTH = 4224, CME_LENGTH = 16512, CE_ORDER = 1, CME_ORDER = 3 };
enum { SLOT_CAPACITY = 16 };
static _Alignas(PAGE_SIZE) unsigned char backing[SLOT_CAPACITY][PAGE_SIZE << CME_ORDER];
static struct {
    unsigned int order;
    struct device *dev;
    dma_addr_t address;
    size_t length;
    enum dma_data_direction direction;
    bool allocated, mapped;
} records[SLOT_CAPACITY];
static unsigned int alloc_calls, map_calls, error_checks;
static unsigned int fail_alloc, fail_map;
static unsigned int high_map, zero_map, crossing_map, last_byte_map;
static unsigned int pause_map_call;
static char events[128];
static size_t event_count;
#define HOST_DMA_ERROR UINT64_C(0xdeadbeef00000001)

#ifdef HOST_INTEGRATION
static inline void pause_operation(void) { CHECK(false, "unexpected-pause"); }
static inline void wait_observed(void) { CHECK(false, "unexpected-wait"); }
static unsigned char command_dma_buffer[64];
static dma_addr_t command_dma_address;
static unsigned int command_maps, command_checks, command_unmaps;
#else
static void pause_operation(void);
#endif

static void record_event(char operation, unsigned int slot)
{
    CHECK(event_count + 2 < sizeof(events) && slot < SLOT_CAPACITY, "event-capacity");
    events[event_count++] = operation;
    events[event_count++] = "0123456789abcdef"[slot];
}

static unsigned int page_slot(unsigned long address)
{
    for (unsigned int slot = 0; slot < SLOT_CAPACITY; ++slot) {
        if (address == (unsigned long)backing[slot])
            return slot;
    }
    CHECK(false, "foreign-page");
    return 0;
}

static inline unsigned int get_order(unsigned long length)
{
    unsigned int order = 0;
    for (unsigned long bytes = PAGE_SIZE; bytes < length; bytes <<= 1)
        ++order;
    return order;
}

static unsigned long __get_free_pages(unsigned int flags, unsigned int order)
{
    unsigned int slot = alloc_calls++;

    CHECK(!lock_depth, "alloc-under-lock");
    CHECK(flags == (GFP_ATOMIC | __GFP_NOWARN | __GFP_ZERO), "alloc-flags");
    CHECK(slot < SLOT_CAPACITY, "alloc-capacity");
    record_event('A', slot);
    if (alloc_calls == fail_alloc)
        return 0;
    CHECK(order <= CME_ORDER, "oversize-allocation");
    records[slot].allocated = true;
    records[slot].order = order;
    return (unsigned long)backing[slot];
}

static void free_pages(unsigned long address, unsigned int order)
{
    unsigned int slot = page_slot(address);

    CHECK(!lock_depth, "free-under-lock");
    CHECK(records[slot].allocated, "double-free");
    CHECK(!records[slot].mapped, "free-while-mapped");
    CHECK(records[slot].order == order, "free-order");
    records[slot].allocated = false;
    record_event('F', slot);
}

static inline size_t dma_max_mapping_size(struct device *dev)
{
    return dev->mapping_limit;
}

static dma_addr_t dma_map_single(struct device *dev, void *address, size_t length,
                                 enum dma_data_direction direction)
{
#ifdef HOST_INTEGRATION
    if (address == command_dma_buffer) {
        CHECK(dev == &device4 && length == sizeof(command_dma_buffer) &&
              direction == DMA_TO_DEVICE, "command-map-tuple");
        ++command_maps;
        return command_dma_address;
    }
#endif
    unsigned int slot = page_slot((unsigned long)address);
    dma_addr_t dma = UINT64_C(0x110000) + UINT64_C(0x10000) * slot;

    CHECK(!lock_depth, "map-under-lock");
    CHECK(records[slot].allocated && !records[slot].mapped, "map-ownership");
    CHECK(dev == &device4 || dev == &device6, "map-device");
    CHECK(direction == DMA_TO_DEVICE, "map-direction");
    CHECK(length == CE_LENGTH || length == CME_LENGTH, "map-length");
    CHECK(records[slot].order == (length == CE_LENGTH ? CE_ORDER : CME_ORDER), "alloc-order");
    record_event('M', slot);
    if (++map_calls == fail_map)
        return HOST_DMA_ERROR;
    if (map_calls == high_map)
        dma += UINT64_C(1) << 32;
    if (map_calls == crossing_map)
        dma = UINT32_MAX - length + 2;
    if (map_calls == last_byte_map)
        dma = UINT32_MAX - length + 1;
    if (map_calls == zero_map)
        dma = 0;
    records[slot].dev = dev;
    records[slot].address = dma;
    records[slot].length = length;
    records[slot].direction = direction;
    records[slot].mapped = true;
    if (map_calls == pause_map_call)
        pause_operation();
    return dma;
}

static int dma_mapping_error(struct device *dev, dma_addr_t dma)
{
#ifdef HOST_INTEGRATION
    if (command_maps) {
        CHECK(dev == &device4 && dma == command_dma_address, "command-native-check");
        ++command_checks;
    }
#endif
    CHECK(dev == &device4 || dev == &device6, "map-error-device");
    ++error_checks;
    if (fail_map && map_calls == fail_map)
        CHECK(dma == HOST_DMA_ERROR, "map-error-native-width");
    return dma == HOST_DMA_ERROR;
}

static void dma_unmap_single(struct device *dev, dma_addr_t dma, size_t length,
                             enum dma_data_direction direction)
{
#ifdef HOST_INTEGRATION
    if (command_maps) {
        CHECK(dev == &device4 && dma == command_dma_address &&
              length == sizeof(command_dma_buffer) && direction == DMA_TO_DEVICE,
              "command-unmap-tuple");
        ++command_unmaps;
        return;
    }
#endif
    CHECK(!lock_depth, "unmap-under-lock");
    for (unsigned int slot = 0; slot < SLOT_CAPACITY; ++slot) {
        if (!records[slot].mapped || records[slot].address != dma)
            continue;
        CHECK(records[slot].dev == dev, "unmap-device");
        CHECK(records[slot].length == length, "unmap-length");
        CHECK(records[slot].direction == direction, "unmap-direction");
        records[slot].mapped = false;
        record_event('U', slot);
        return;
    }
    CHECK(false, "unmap-address");
}

static inline void nss_cmn_msg_init(struct nss_cmn_msg *cm, uint32_t iface, uint32_t type,
                                   uint32_t length, void *cb, void *app_data)
{
    *cm = (struct nss_cmn_msg){
        .version = NSS_HLOS_MESSAGE_VERSION, .interface = iface, .type = type, .len = length,
        .cb = (nss_ptr_t)cb, .app_data = (nss_ptr_t)app_data,
    };
}

#ifdef HOST_INTEGRATION
#define TRANSPORT_LINKAGE
#else
#define TRANSPORT_LINKAGE static
#endif
TRANSPORT_LINKAGE int32_t nss_core_send_conn_cmd(struct nss_ctx_instance *ctx,
                                               struct nss_cmn_msg *msg, int size);
#undef TRANSPORT_LINKAGE

/* Only dependency shims precede this include; all transaction code comes from the source input. */
#include "production.inc"

enum { V4 = NSS_IPV4_RX_INTERFACE, V6 = NSS_IPV6_RX_INTERFACE };
enum { SIZE = NSS_IPV4_TX_CONN_TABLE_SIZE_MSG, CFG = NSS_IPV4_TX_CONN_CFG_RULE_MSG };
enum { REQUEST = 3072 };

#ifdef HOST_INTEGRATION
#include "integration.c"
#else

static struct nss_ctx_instance wrong_core = { .dev = &device4, .id = 1 };
#ifdef NSS_MEM_PROFILE_LOW
enum { BASELINE = 512 };
#else
enum { BASELINE = 1024 };
#endif
_Static_assert((int)SIZE == (int)NSS_IPV6_TX_CONN_TABLE_SIZE_MSG, "different SIZE IDs");
_Static_assert((int)CFG == (int)NSS_IPV6_TX_CONN_CFG_RULE_MSG, "different CFG IDs");
_Static_assert(offsetof(struct nss_ipv4_msg, msg) == sizeof(struct nss_cmn_msg),
               "unexpected IPv4 payload offset");
_Static_assert(offsetof(struct nss_ipv6_msg, msg) == sizeof(struct nss_cmn_msg),
               "unexpected IPv6 payload offset");
_Static_assert(sizeof(dma_addr_t) > sizeof(((struct nss_ipv4_rule_conn_cfg_msg *)0)->ce_mem),
               "expected native DMA address wider than wire");

union message {
    struct nss_cmn_msg cm;
    struct nss_ipv4_msg v4;
    struct nss_ipv6_msg v6;
};

struct sent {
    union message message;
    struct nss_ctx_instance *ctx;
};

static struct sent sends[16];
static unsigned int send_count;
static bool fail_size_tx, fail_cfg_tx, early_size, early_cfg;

static size_t payload_size(unsigned int iface, unsigned int type)
{
    if (iface == V4)
        return type == SIZE ? sizeof(struct nss_ipv4_rule_conn_get_table_size_msg) :
                              sizeof(struct nss_ipv4_rule_conn_cfg_msg);
    return type == SIZE ? sizeof(struct nss_ipv6_rule_conn_get_table_size_msg) :
                          sizeof(struct nss_ipv6_rule_conn_cfg_msg);
}

static unsigned int request_count(const union message *msg)
{
    if (msg->cm.interface == V4)
        return ntohl(msg->cm.type == SIZE ? msg->v4.msg.size.num_conn :
                                           msg->v4.msg.rule_conn_cfg.num_conn);
    return ntohl(msg->cm.type == SIZE ? msg->v6.msg.size.num_conn :
                                       msg->v6.msg.rule_conn_cfg.num_conn);
}

static void reply_size(union message *msg, unsigned int num, uint32_t ce, uint32_t cme)
{
    if (msg->cm.interface == V4)
        msg->v4.msg.size = (struct nss_ipv4_rule_conn_get_table_size_msg){
            htonl(num), htonl(ce), htonl(cme),
        };
    else
        msg->v6.msg.size = (struct nss_ipv6_rule_conn_get_table_size_msg){
            htonl(num), htonl(ce), htonl(cme),
        };
}

static void respond(unsigned int index, enum nss_cmn_response response)
{
    union message msg = sends[index].message;

    msg.cm.response = response;
    if (msg.cm.type == SIZE)
        reply_size(&msg, request_count(&msg), CE_LENGTH, CME_LENGTH);
    nss_conn_table_rx(sends[index].ctx, &msg.cm);
}

static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cond = PTHREAD_COND_INITIALIZER;
static bool pause_size_tx, pause_after_reply, operation_paused, release_operation;
static bool close_waiting, close_returned;

static void gate_lock(void)
{
    CHECK(!pthread_mutex_lock(&gate), "gate-lock");
}

static void gate_unlock(void)
{
    CHECK(!pthread_mutex_unlock(&gate), "gate-unlock");
}

static void gate_signal(void)
{
    CHECK(!pthread_cond_broadcast(&gate_cond), "gate-signal");
}

static void gate_wait(void)
{
    CHECK(!pthread_cond_wait(&gate_cond, &gate), "gate-wait");
}

static void wait_observed(void)
{
    gate_lock();
    close_waiting = true;
    gate_signal();
    gate_unlock();
}

static void pause_operation(void)
{
    gate_lock();
    operation_paused = true;
    gate_signal();
    while (!release_operation)
        gate_wait();
    gate_unlock();
}

static int32_t nss_core_send_conn_cmd(struct nss_ctx_instance *ctx,
                                      struct nss_cmn_msg *msg, int size)
{
    unsigned int index = send_count++;
    struct sent *command = &sends[index];
    unsigned int iface = msg->interface, type = msg->type;

    CHECK(!lock_depth, "tx-under-lock");
    CHECK(index < ARRAY_SIZE(sends), "tx-capacity");
    CHECK(iface == V4 || iface == V6, "tx-interface");
    CHECK(ctx == (iface == V4 ? &core4 : &core6), "tx-context");
    CHECK(type == SIZE || type == CFG, "tx-type");
    CHECK(msg->len == payload_size(iface, type), "tx-payload-length");
    CHECK(size == (int)(sizeof(*msg) + msg->len), "tx-buffer-size");
    CHECK(!msg->cb, "tx-callback-pointer");
    CHECK(msg->app_data, "tx-token");
    command->ctx = ctx;
    memcpy(&command->message, msg, sizeof(*msg) + msg->len);
    if (type == SIZE && pause_size_tx && !pause_after_reply)
        pause_operation();
    if (type == SIZE && early_size)
        respond(index, NSS_CMN_RESPONSE_ACK);
    if (type == CFG && early_cfg) {
        int before = nss_conn_table_count(iface);

        respond(index, NSS_CMN_RESPONSE_ACK);
        CHECK(nss_conn_table_count(iface) == before, "early-cfg-before-tx-success");
    }
    if (type == SIZE && pause_size_tx && pause_after_reply)
        pause_operation();
    return (type == SIZE ? fail_size_tx : fail_cfg_tx) ? NSS_TX_FAILURE_QUEUE : NSS_TX_SUCCESS;
}

static void check_events(const char *expected)
{
    CHECK(!strcmp(events, expected), "dma-prefix");
}

static void check_live(unsigned int allocated, unsigned int mapped)
{
    unsigned int actual_allocated = 0, actual_mapped = 0;

    for (unsigned int i = 0; i < SLOT_CAPACITY; ++i) {
        actual_allocated += records[i].allocated;
        actual_mapped += records[i].mapped;
    }
    CHECK(actual_allocated == allocated && actual_mapped == mapped, "dma-retention");
}

static void check_cfg(unsigned int index, unsigned int count,
                      unsigned int ce, unsigned int cme)
{
    const struct sent *command = &sends[index];
    const union message *msg = &command->message;
    unsigned int iface = msg->cm.interface;
    const struct device *dev = iface == V4 ? &device4 : &device6;

    CHECK(index < send_count && msg->cm.type == CFG, "cfg-send");
    CHECK(request_count(msg) == count, "cfg-count");
    CHECK(records[ce].dev == dev && records[cme].dev == dev, "cfg-dma-device");
    CHECK(records[ce].length == CE_LENGTH && records[cme].length == CME_LENGTH, "cfg-dma-length");
    CHECK((iface == V4 ? msg->v4.msg.rule_conn_cfg.ce_mem :
                         msg->v6.msg.rule_conn_cfg.ce_mem) == records[ce].address, "cfg-ce-address");
    CHECK((iface == V4 ? msg->v4.msg.rule_conn_cfg.cme_mem :
                         msg->v6.msg.rule_conn_cfg.cme_mem) == records[cme].address, "cfg-cme-address");
}

static void start4(unsigned int count)
{
    unsigned int index = send_count;

    CHECK(nss_conn_table_start(&core4, V4, count) == 0, "start4");
    CHECK(send_count > index && sends[index].message.cm.type == SIZE, "size-send");
    CHECK(request_count(&sends[index].message) == count, "size-count");
}

static void rollback_case(void)
{
    const char *expected;
    unsigned int expected_sends = 1, checks;

    if (!strcmp(test_case, "alloc-ce")) {
        fail_alloc = 1;
        expected = "A0";
        checks = 0;
    } else if (!strcmp(test_case, "alloc-cme")) {
        fail_alloc = 2;
        expected = "A0A1F0";
        checks = 0;
    } else if (!strcmp(test_case, "map-ce")) {
        fail_map = 1;
        expected = "A0A1M0F1F0";
        checks = 1;
    } else if (!strcmp(test_case, "map-cme")) {
        fail_map = 2;
        expected = "A0A1M0M1U0F1F0";
        checks = 2;
    } else if (!strcmp(test_case, "high-ce")) {
        high_map = 1;
        expected = "A0A1M0U0F1F0";
        checks = 1;
    } else if (!strcmp(test_case, "high-cme") || !strcmp(test_case, "dma-crossing")) {
        if (!strcmp(test_case, "high-cme"))
            high_map = 2;
        else
            crossing_map = 2;
        expected = "A0A1M0M1U1U0F1F0";
        checks = 2;
    } else if (!strcmp(test_case, "zero-dma-rollback")) {
        zero_map = 1;
        fail_map = 2;
        expected = "A0A1M0M1U0F1F0";
        checks = 2;
    } else {
        early_cfg = !strcmp(test_case, "early-cfg-tx-failure");
        CHECK(early_cfg || !strcmp(test_case, "cfg-tx-failure"), "unknown-rollback-case");
        fail_cfg_tx = true;
        expected = "A0A1M0M1U1U0F1F0";
        expected_sends = 2;
        checks = 2;
    }
    start4(REQUEST);
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == expected_sends, "prefix-tx-count");
    CHECK(error_checks == checks, "prefix-map-error-checks");
    check_events(expected);
    check_live(0, 0);
    CHECK(nss_conn_table_count(V4) == BASELINE, "rollback-count");
    respond(0, NSS_CMN_RESPONSE_ACK);
    if (early_cfg)
        respond(1, NSS_CMN_RESPONSE_ACK);
    check_events(expected);
    start4(REQUEST);
    CHECK(sends[0].message.cm.app_data != sends[expected_sends].message.cm.app_data,
          "retry-new-token");
    if (early_cfg) {
        early_cfg = fail_cfg_tx = false;
        respond(expected_sends, NSS_CMN_RESPONSE_ACK);
        CHECK(nss_conn_table_count(V4) == BASELINE, "retry-unconfirmed-count");
        check_cfg(expected_sends + 1, REQUEST, 2, 3);
        respond(expected_sends + 1, NSS_CMN_RESPONSE_ACK);
        CHECK(nss_conn_table_count(V4) == REQUEST, "retry-confirmed-count");
        check_events("A0A1M0M1U1U0F1F0A2A3M2M3");
        check_live(2, 2);
    }
}

static void test_nested(void)
{
    early_size = true;
    early_cfg = true;
    zero_map = 1;
    last_byte_map = 2;
    start4(REQUEST);
    CHECK(send_count == 2, "nested-cfg-tx");
    check_cfg(1, REQUEST, 0, 1);
    CHECK(nss_conn_table_count(V4) == REQUEST, "nested-ack-count");
    respond(0, NSS_CMN_RESPONSE_ACK);
    respond(1, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 2, "nested-duplicate");
    CHECK(nss_conn_table_count(V4) == REQUEST, "nested-state-after-return");
    CHECK(nss_conn_table_start(&core4, V4, REQUEST + 1024) != 0, "nested-second-admission");
    nss_conn_table_close();
    check_events("A0A1M0M1");
    check_live(2, 2);
}

static void test_size_failure(void)
{
    fail_size_tx = true;
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) < 0, "failed-size-tx-errno");
    CHECK(send_count == 1, "failed-size-only");
    respond(0, NSS_CMN_RESPONSE_ACK);
    check_events("");
    fail_size_tx = false;
    start4(REQUEST);
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 2, "stale-size-tx");
    check_events("");
    respond(1, NSS_CMN_RESPONSE_EVERSION);
    CHECK(nss_conn_table_count(V4) == BASELINE, "size-nack-count");
    respond(1, NSS_CMN_RESPONSE_ACK);
    check_events("");
    start4(REQUEST);
    CHECK(sends[0].message.cm.app_data != sends[1].message.cm.app_data &&
          sends[1].message.cm.app_data != sends[2].message.cm.app_data, "stale-token-reuse");
}

static void test_size_identity(void)
{
    union message msg;

    start4(REQUEST);
    msg = sends[0].message;
    reply_size(&msg, REQUEST, CE_LENGTH, CME_LENGTH);
    CHECK(nss_conn_table_message(&msg.cm), "size-classifier");
    msg.cm.interface = UINT32_MAX;
    CHECK(!nss_conn_table_message(&msg.cm), "wrong-interface-classifier");
    nss_conn_table_rx(&core4, &msg.cm);
    msg.cm.interface = V6;
    nss_conn_table_rx(&core4, &msg.cm);
    msg.cm.interface = V4;
    msg.cm.type = NSS_IPV4_RX_NODE_STATS_SYNC_MSG;
    CHECK(!nss_conn_table_message(&msg.cm), "stats-classifier");
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(send_count == 1 && alloc_calls == 0, "size-wrong-interface-type");
    msg.cm.type = CFG;
    CHECK(nss_conn_table_message(&msg.cm), "cfg-classifier");
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE && alloc_calls == 0, "cfg-before-size");
    msg.cm.type = SIZE;
    nss_conn_table_rx(&wrong_core, &msg.cm);
    CHECK(alloc_calls == 0, "size-wrong-core");
    msg.cm.app_data ^= 0x40000000u;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(alloc_calls == 0, "size-wrong-token");
    msg.cm.app_data = sends[0].message.cm.app_data;
    msg.cm.response = NSS_CMN_RESPONSE_NOTIFY;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(alloc_calls == 0, "size-notify");
    msg.cm.response = NSS_CMN_RESPONSE_ACK;
    msg.cm.len = sizeof(msg.v4.msg.size) - 1;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(alloc_calls == 0, "size-short");
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 2, "size-valid-after-invalid");
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 2 && alloc_calls == 2, "size-duplicate");
}

static void test_bad_size(void)
{
    union message msg;
    uint32_t ce = CE_LENGTH, cme = CME_LENGTH;
    unsigned int count = REQUEST;

    if (!strcmp(test_case, "wrong-size-count"))
        count += 1024;
    else if (!strcmp(test_case, "empty-ce"))
        ce = 0;
    else if (!strcmp(test_case, "empty-cme"))
        cme = 0;
    else if (!strcmp(test_case, "oversize-map"))
        cme = UINT32_MAX;
    else {
        CHECK(!strcmp(test_case, "oversize-page-order"), "unknown-size-case");
        device4.mapping_limit = UINT32_MAX;
        ce = (PAGE_SIZE << MAX_PAGE_ORDER) + 1;
    }
    start4(REQUEST);
    msg = sends[0].message;
    reply_size(&msg, count, ce, cme);
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(send_count == 1 && alloc_calls == 0 && map_calls == 0,
          "reject-size-before-allocation");
    check_events("");
    check_live(0, 0);
    CHECK(nss_conn_table_count(V4) == BASELINE, "bad-size-count");
}

static void test_cfg_identity(void)
{
    union message msg;

    start4(REQUEST);
    respond(0, NSS_CMN_RESPONSE_ACK);
    check_cfg(1, REQUEST, 0, 1);
    CHECK(nss_conn_table_count(V4) == BASELINE, "unconfirmed-count");
    msg = sends[1].message;
    msg.cm.len = sizeof(msg.v4.msg.rule_conn_cfg.num_conn) - 1;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-short");
    msg = sends[1].message;
    nss_conn_table_rx(&wrong_core, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-wrong-core");
    msg.cm.app_data ^= 0x40000000u;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-wrong-token");
    msg = sends[1].message;
    msg.cm.interface = V6;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-wrong-family");
    msg = sends[1].message;
    msg.cm.response = NSS_CMN_RESPONSE_NOTIFY;
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-notify");
    msg = sends[1].message;
    msg.cm.len = sizeof(msg.v4.msg.rule_conn_cfg.num_conn);
    nss_conn_table_rx(&core4, &msg.cm);
    CHECK(nss_conn_table_count(V4) == REQUEST, "cfg-confirmed-count");
    respond(1, NSS_CMN_RESPONSE_EVERSION);
    CHECK(nss_conn_table_count(V4) == REQUEST, "cfg-late-nack");
    check_events("A0A1M0M1");
    check_live(2, 2);
}

static void test_retention(void)
{
    bool nack = !strcmp(test_case, "cfg-nack-retained");
    bool bad_count = !strcmp(test_case, "cfg-wrong-count");

    start4(REQUEST);
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 2, "retained-cfg-send");
    if (nack || bad_count) {
        if (nack) {
            respond(1, NSS_CMN_RESPONSE_EVERSION);
        } else {
            union message msg = sends[1].message;

            msg.v4.msg.rule_conn_cfg.num_conn = htonl(REQUEST + 1024);
            nss_conn_table_rx(&core4, &msg.cm);
        }
        CHECK(nss_conn_table_count(V4) == BASELINE, "cfg-failed-count");
        respond(1, NSS_CMN_RESPONSE_ACK);
        CHECK(nss_conn_table_count(V4) == BASELINE, "uncertain-late-ack-count");
        CHECK(nss_conn_table_start(&core4, V4, REQUEST) != 0, "uncertain-retry");
        check_live(2, 2);
    }
    nss_conn_table_close();
    check_live(2, 2);
    nss_conn_table_close();
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) != 0, "closed-start");
    CHECK(nss_conn_table_start(&core4, V4, NSS_FW_DEFAULT_NUM_CONN) != 0, "closed-default");
    respond(0, NSS_CMN_RESPONSE_ACK);
    respond(1, NSS_CMN_RESPONSE_ACK);
    CHECK(nss_conn_table_count(V4) == BASELINE, "closed-late-ack-count");
    CHECK(send_count == 2, "closed-extra-send");
    check_events("A0A1M0M1");
    check_live(2, 2);
}

static void test_close_pending(void)
{
    start4(REQUEST);
    nss_conn_table_close();
    respond(0, NSS_CMN_RESPONSE_ACK);
    CHECK(send_count == 1, "closed-size-ack");
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) != 0, "closed-start");
    check_events("");
    check_live(0, 0);
}

static void *open_thread(void *unused)
{
    (void)unused;
    start4(REQUEST);
    return NULL;
}

static void *receive_thread(void *unused)
{
    (void)unused;
    respond(0, NSS_CMN_RESPONSE_ACK);
    return NULL;
}

static void *close_thread(void *unused)
{
    (void)unused;
    nss_conn_table_close();
    gate_lock();
    close_returned = true;
    gate_signal();
    gate_unlock();
    return NULL;
}

static void test_close_inflight(void)
{
    pthread_t operation, closer;
    bool preparing = !strcmp(test_case, "close-preparing");
    bool nested = !strcmp(test_case, "close-nested");

    if (preparing) {
        start4(REQUEST);
        pause_map_call = 2;
    } else {
        pause_size_tx = early_size = true;
        pause_after_reply = early_cfg = nested;
    }
    CHECK(!pthread_create(&operation, NULL, preparing ? receive_thread : open_thread, NULL),
          "start-thread");
    gate_lock();
    while (!operation_paused)
        gate_wait();
    CHECK(!pthread_create(&closer, NULL, close_thread, NULL), "close-thread");
    while (!close_waiting && !close_returned)
        gate_wait();
    CHECK(close_waiting && !close_returned, preparing ? "close-joins-rx" : "close-joins-sender");
    release_operation = true;
    gate_signal();
    gate_unlock();
    CHECK(!pthread_join(operation, NULL) && !pthread_join(closer, NULL), "join-threads");
    if (nested) {
        CHECK(send_count == 2 && nss_conn_table_count(V4) == REQUEST, "close-nested-active");
        check_events("A0A1M0M1");
        check_live(2, 2);
    } else {
        CHECK(send_count == 1, "inflight-late-size");
        check_events(preparing ? "A0A1M0M1U1U0F1F0" : "");
        check_live(0, 0);
    }
}

static void test_budget(void)
{
    unsigned int count4 = 5120, count6 = 3072;
    union message wrong;

    start4(count4);
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) != 0, "duplicate-pending-admission");
    CHECK(nss_conn_table_start(&core6, V6, count6 + 1024) != 0, "pending-reservation");
    CHECK(send_count == 1, "budget-rejected-before-tx");
    CHECK(nss_conn_table_start(&core6, V6, count6) == 0, "budget-exact-limit");
    CHECK(send_count == 2 && request_count(&sends[1].message) == count6, "size6");
    CHECK(nss_conn_table_count(V4) == BASELINE && nss_conn_table_count(V6) == BASELINE,
          "reserved-not-accepted");
    wrong = sends[0].message;
    wrong.cm.interface = V6;
    reply_size(&wrong, count6, CE_LENGTH, CME_LENGTH);
    nss_conn_table_rx(&core6, &wrong.cm);
    CHECK(send_count == 2 && alloc_calls == 0, "other-family-token");
    respond(1, NSS_CMN_RESPONSE_ACK);
    check_cfg(2, count6, 0, 1);
    respond(2, NSS_CMN_RESPONSE_ACK);
    CHECK(nss_conn_table_count(V6) == (int)count6, "accepted6");
    fail_map = 4;
    respond(0, NSS_CMN_RESPONSE_ACK);
    check_events("A0A1M0M1A2A3M2M3U2F3F2");
    check_live(2, 2);
    CHECK(nss_conn_table_count(V4) == BASELINE && nss_conn_table_count(V6) == (int)count6,
          "rollback-other-family");
    CHECK(nss_conn_table_start(&core4, V4, count4 + 1024) != 0, "accepted-peer-budget");
    start4(count4);
    CHECK(send_count == 4, "released-budget-usable");
}

static void test_token_exhaustion(void)
{
    /* Seed the real allocator immediately before its boundary, not a token model. */
    nss_conn_token = UINT32_MAX - 1;
    start4(REQUEST);
    CHECK(sends[0].message.cm.app_data == UINT32_MAX, "last-wire-token");
    respond(0, NSS_CMN_RESPONSE_EVERSION);
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) == -EOVERFLOW, "exhausted-token");
    CHECK(nss_conn_table_start(&core6, V6, REQUEST) == -EOVERFLOW, "exhausted-token-peer");
    CHECK(send_count == 1, "exhaustion-no-send");
    respond(0, NSS_CMN_RESPONSE_ACK);
    check_events("");
}

static void test_profile(void)
{
#if defined(NSS_DRV_IPV4_ENABLE)
    CHECK(nss_conn_table_count(V4) == BASELINE, "profile-baseline");
    CHECK(nss_conn_table_start(&core4, V4, -1024) < 0, "negative-count");
    CHECK(nss_conn_table_start(&core4, V4, INT_MAX) < 0, "extreme-count");
    CHECK(nss_conn_table_start(&core4, V4, 1025) < 0, "quanta");
    CHECK(nss_conn_table_start(&core4, V4, 0) < 0, "zero-count");
    CHECK(nss_conn_table_start(&core4, V4, NSS_FW_DEFAULT_NUM_CONN) == 0, "fw-default");
    CHECK(send_count == 0, "invalid-and-default-no-tx");
#if defined(NSS_MEM_PROFILE_LOW)
    CHECK(nss_conn_table_start(&core4, V4, NSS_DEFAULT_NUM_CONN) < 0, "low-invalid-granularity");
    CHECK(send_count == 0, "low-no-tx");
#else
    start4(NSS_DEFAULT_NUM_CONN);
#if defined(NSS_DRV_IPV6_ENABLE)
    CHECK(nss_conn_table_start(&core6, V6, NSS_DEFAULT_NUM_CONN) == 0, "profile-v6");
    CHECK(send_count == 2, "profile-dual-send");
#endif
#endif
#else
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) < 0, "disabled-v4");
    CHECK(nss_conn_table_start(&core6, V6, NSS_DEFAULT_NUM_CONN) == 0, "profile-v6");
    CHECK(send_count == 1, "v6-only-send");
#endif
    CHECK(nss_conn_table_start(&core4, UINT32_MAX, REQUEST) < 0, "invalid-interface");
    check_events("");
}

static void test_single_family(void)
{
    const int limit = NSS_MAX_TOTAL_NUM_CONN_IPV4_IPV6;

#if defined(NSS_DRV_IPV6_ENABLE)
    CHECK(nss_conn_table_start(&core4, V4, REQUEST) < 0, "disabled-v4");
    CHECK(nss_conn_table_start(&core6, V6, limit) == 0, "single-v6-budget");
    CHECK(sends[0].message.cm.interface == V6, "single-v6-interface");
#else
    CHECK(nss_conn_table_start(&core6, V6, REQUEST) < 0, "disabled-v6");
    start4(limit);
#endif
    respond(0, NSS_CMN_RESPONSE_ACK);
    check_cfg(1, limit, 0, 1);
    respond(1, NSS_CMN_RESPONSE_ACK);
    CHECK(nss_conn_table_count(sends[0].message.cm.interface) == limit, "single-family-accepted");
    nss_conn_table_close();
    check_live(2, 2);
}

int main(int argc, char **argv)
{
    static const struct {
        const char *name;
        void (*run)(void);
    } cases[] = {
        { "alloc-ce", rollback_case }, { "alloc-cme", rollback_case },
        { "map-ce", rollback_case }, { "map-cme", rollback_case },
        { "high-ce", rollback_case }, { "high-cme", rollback_case },
        { "dma-crossing", rollback_case },
        { "zero-dma-rollback", rollback_case }, { "cfg-tx-failure", rollback_case },
        { "early-cfg-tx-failure", rollback_case },
        { "nested-ack", test_nested }, { "size-failure", test_size_failure },
        { "size-identity", test_size_identity }, { "wrong-size-count", test_bad_size },
        { "empty-ce", test_bad_size }, { "empty-cme", test_bad_size },
        { "oversize-map", test_bad_size }, { "cfg-identity", test_cfg_identity },
        { "oversize-page-order", test_bad_size }, { "token-exhaustion", test_token_exhaustion },
        { "cfg-nack-retained", test_retention }, { "close-published", test_retention },
        { "cfg-wrong-count", test_retention },
        { "close-pending", test_close_pending }, { "close-inflight", test_close_inflight },
        { "close-preparing", test_close_inflight },
        { "close-nested", test_close_inflight },
        { "dual-budget", test_budget }, { "profile", test_profile },
        { "single-family", test_single_family },
    };

    if (argc != 2)
        return 2;
    test_case = argv[1];
    for (size_t i = 0; i < ARRAY_SIZE(cases); ++i) {
        if (!strcmp(test_case, cases[i].name)) {
            cases[i].run();
            printf("PASS %s\n", test_case);
            return 0;
        }
    }
    return 2;
}

#endif
