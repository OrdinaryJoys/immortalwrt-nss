/* Included by fixture.c for the integration build only. */
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define IS_ALIGNED(value, alignment) (((value) & ((alignment) - 1)) == 0)
#define BUG_ON(condition) CHECK(!(condition), "production-bug-on")
#define NSS_H2N_INTR_DATA_COMMAND_QUEUE 1
#define NSS_CORE_STATE_INITIALIZED 1
#define NSS_VERIFY_CTX_MAGIC(ctx) CHECK((ctx) == &core4 || (ctx) == &core6, "tx-context")
#define NSS_PKT_STATS_INC(counter) (++*(counter))
enum { NSS_DRV_STATS_NBUF_ALLOC_FAILS, NSS_DRV_STATS_TX_CMD_QUEUE_FULL, NSS_DRV_STATS_TX_CMD_REQ };

typedef struct {
    unsigned char *page;
    unsigned int offset, size;
} skb_frag_t;

struct sk_buff {
    unsigned char *head, *data, *end;
    unsigned int len, data_len;
    struct {
        unsigned int nr_frags;
        skb_frag_t frags[1];
    } shared;
};

#define skb_shinfo(skb) (&(skb)->shared)
#define skb_frag_off(frag) ((frag)->offset)
#define skb_frag_size(frag) ((frag)->size)
#define skb_frag_address(frag) ((frag)->page + (frag)->offset)
#define skb_headlen(skb) ((skb)->len - (skb)->data_len)
#define skb_end_pointer(skb) ((skb)->end)

static unsigned char command_bytes[PAGE_SIZE], ring_bytes[PAGE_SIZE];
static struct sk_buff command_skb;
static bool skb_owned, fail_command;
static unsigned int skb_allocs, skb_frees, ring_count, ring_length, ring_flags, interrupts;

static struct sk_buff *dev_alloc_skb(unsigned int capacity)
{
    CHECK(!skb_owned && capacity <= sizeof(command_bytes), "command-allocation");
    ++skb_allocs;
    memset(command_bytes, 0xa5, sizeof(command_bytes));
    command_skb = (struct sk_buff) {
        .head = command_bytes, .data = command_bytes, .end = command_bytes + capacity,
    };
    skb_owned = true;
    return &command_skb;
}

static void *skb_put(struct sk_buff *skb, unsigned int length)
{
    unsigned int old = skb->len;

    CHECK(skb == &command_skb && skb_owned &&
          length <= (unsigned int)(skb->end - skb->data) - old, "command-write-bounds");
    skb->len += length;
    return skb->data + old;
}

static void *skb_put_zero(struct sk_buff *skb, unsigned int length)
{
    return memset(skb_put(skb, length), 0, length);
}

static void dev_kfree_skb_any(struct sk_buff *skb)
{
    CHECK(skb == &command_skb && skb_owned, "command-free-owner");
    skb_owned = false;
    ++skb_frees;
}

static int32_t nss_core_send_buffer(struct nss_ctx_instance *ctx, uint32_t iface,
                                    struct sk_buff *skb, uint16_t queue, uint8_t type,
                                    uint16_t flags)
{
    CHECK(ctx == &core4 || ctx == &core6, "ring-context");
    CHECK(!iface && queue == NSS_IF_H2N_CMD_QUEUE && type == H2N_BUFFER_CTRL,
          "ring-command-route");
    CHECK(skb == &command_skb && skb_owned, "ring-skb");
    if (fail_command)
        return NSS_TX_FAILURE_QUEUE;
    ++ring_count;
    ring_flags = flags;
    ring_length = skb->len;
    memcpy(ring_bytes, skb->data, skb->len);
    skb_owned = false;
    return NSS_CORE_STATUS_SUCCESS;
}

static void nss_hal_send_interrupt(struct nss_ctx_instance *ctx, unsigned int interrupt)
{
    CHECK((ctx == &core4 || ctx == &core6) && interrupt == NSS_H2N_INTR_DATA_COMMAND_QUEUE,
          "ring-interrupt");
    ++interrupts;
}

static unsigned int rx_logs, tx_logs, node_calls, notify_calls, wire_calls, notify_callbacks;
static int notify_cookie;
static struct host_top top;
static bool allow_wire;

/* Log and stats are observations; real family handlers do callback dispatch. */
#define HOST_FAMILY(v) \
    typedef void (*nss_ipv##v##_msg_callback_t)(void *, struct nss_ipv##v##_msg *); \
    static nss_ipv##v##_msg_callback_t nss_ipv##v##_conn_sync_many_msg_cb; \
    static void nss_ipv##v##_log_rx_msg(struct nss_ipv##v##_msg *msg) \
    { (void)msg; ++rx_logs; } \
    static void nss_ipv##v##_log_tx_msg(struct nss_ipv##v##_msg *msg) \
    { (void)msg; ++tx_logs; } \
    static void nss_ipv##v##_stats_node_sync(struct nss_ctx_instance *ctx, uint32_t *value) \
    { (void)ctx; (void)value; ++node_calls; } \
    static void nss_ipv##v##_stats_notify(struct nss_ctx_instance *ctx) \
    { (void)ctx; ++notify_calls; } \
    static void nss_ipv##v##_stats_conn_sync(struct nss_ctx_instance *ctx, uint32_t *value) \
    { (void)ctx; (void)value; CHECK(false, "unexpected-conn-stats"); } \
    static void nss_ipv##v##_stats_conn_sync_many(struct nss_ctx_instance *ctx, uint32_t *value) \
    { (void)ctx; (void)value; CHECK(false, "unexpected-many-stats"); } \
    static void wire##v(void *data, struct nss_ipv##v##_msg *msg) \
    { \
        (void)data; (void)msg; \
        CHECK(allow_wire, "unexpected-wire-callback"); \
        ++wire_calls; \
    } \
    static void notify##v(void *data, struct nss_ipv##v##_msg *msg) \
    { \
        CHECK(data == &notify_cookie && msg->cm.response == NSS_CMN_RESPONSE_NOTIFY, \
              "notify-route"); \
        ++notify_callbacks; \
    }
HOST_FAMILY(4)
HOST_FAMILY(6)
#undef HOST_FAMILY

#include "entrypoints.inc"

struct packet {
    struct nss_cmn_msg cm;
    uint32_t words[3];
    unsigned char extra[16];
};

_Static_assert(offsetof(struct packet, words) == sizeof(struct nss_cmn_msg), "wire payload offset");

static struct packet reply(unsigned int family, unsigned int type)
{
    return (struct packet) {
        .cm = { .version = NSS_HLOS_MESSAGE_VERSION, .len = type == SIZE ? 12 : 4,
                .interface = family, .type = type, .response = NSS_CMN_RESPONSE_ACK,
                .cb = family == V4 ? (nss_ptr_t)wire4 : (nss_ptr_t)wire6 },
        .words = { htonl(REQUEST), htonl(CE_LENGTH), htonl(CME_LENGTH) },
    };
}

enum backing_mode {
    LINEAR, LINEAR_END, LINEAR_HEADLEN, FRAGMENT_ALIGNED, FRAGMENT, FRAGMENT_SIZE, FRAGMENT_PAGE,
};

static void receive(struct nss_ctx_instance *route, struct nss_ctx_instance *physical,
                    const struct packet *packet, enum backing_mode mode,
                    unsigned int reported, unsigned int contiguous)
{
    _Alignas(struct packet) unsigned char backing[PAGE_SIZE + sizeof(*packet)];
    unsigned int offset = 0;
    struct sk_buff skb = { .len = reported };

    if (mode == FRAGMENT_PAGE)
        offset = PAGE_SIZE - contiguous;
    else if (mode == FRAGMENT || mode == FRAGMENT_SIZE)
        offset = 1; /* Intentional unaligned table message. */
    memcpy(backing + offset, packet, sizeof(*packet));
    if (mode == FRAGMENT_ALIGNED || mode == FRAGMENT ||
        mode == FRAGMENT_SIZE || mode == FRAGMENT_PAGE) {
        skb.shared.nr_frags = 1;
        skb.shared.frags[0] = (skb_frag_t) {
            backing, offset, mode == FRAGMENT_SIZE ? contiguous : reported,
        };
    } else {
        skb.head = skb.data = backing;
        skb.end = backing + (mode == LINEAR_END ? contiguous : reported);
        if (mode == LINEAR_HEADLEN)
            skb.data_len = reported - contiguous;
    }
    nss_core_handle_nss_status_pkt(route, &skb, physical);
}

static struct nss_cmn_msg transmitted(void)
{
    struct nss_cmn_msg sent;
    memcpy(&sent, ring_bytes, sizeof(sent));
    return sent;
}

static void rx_malformed(void)
{
    bool ipv6 = !strcmp(test_case, "rx-malformed6");
    unsigned int family = ipv6 ? V6 : V4;
    struct nss_ctx_instance *ctx = ipv6 ? &core6 : &core4;
    struct nss_ctx_instance *other = ipv6 ? &core4 : &core6;
    struct packet msg = reply(family, SIZE);
    const unsigned int head = sizeof(msg.cm), full = head + 12;

    CHECK(!nss_conn_table_start(ctx, family, REQUEST) && ring_count == 1, "rx-start");
    struct nss_cmn_msg request = transmitted();
    CHECK(request.type == SIZE && request.interface == family && !request.cb &&
          request.app_data && request.len == 12, "size-wire-header");
    msg.cm.app_data = request.app_data;
    receive(ctx, ctx, &msg, LINEAR, head - 1, head - 1);
    receive(ctx, ctx, &msg, LINEAR, full - 1, full - 1);
    receive(ctx, ctx, &msg, LINEAR_END, full, full - 1);
    receive(ctx, ctx, &msg, LINEAR_HEADLEN, full, full - 1);
    receive(ctx, ctx, &msg, FRAGMENT_SIZE, full, full - 1);
    receive(ctx, ctx, &msg, FRAGMENT_PAGE, full, full - 1);
    CHECK(ring_count == 1 && alloc_calls == 0, "rx-truncated-dispatch");
    receive(ctx, other, &msg, LINEAR, full, full);
    CHECK(ring_count == 1 && alloc_calls == 0, "rx-wrong-physical-core");
    msg.cm.interface |= UINT32_C(1) << 16;
    receive(ctx, ctx, &msg, LINEAR, full, full);
    msg.cm.interface = family;
    ++msg.cm.version;
    receive(ctx, ctx, &msg, LINEAR, full, full);
    --msg.cm.version;
    msg.cm.app_data ^= 0x1234;
    receive(ctx, ctx, &msg, LINEAR, full, full);
    msg.cm.app_data ^= 0x1234;
    msg.cm.response = NSS_CMN_RESPONSE_NOTIFY;
    receive(ctx, ctx, &msg, LINEAR, full, full);
    CHECK(!rx_logs && !wire_calls && !notify_callbacks && alloc_calls == 0,
          "table-reply-legacy-route");
    msg.cm.response = NSS_CMN_RESPONSE_ACK;
    receive(ctx, ctx, &msg, FRAGMENT, full, full);
    CHECK(ring_count == 2 && alloc_calls == 2 && transmitted().type == CFG, "rx-valid-size");
    nss_ptr_t size_token = msg.cm.app_data;
    msg = reply(family, CFG);
    request = transmitted();
    CHECK(request.interface == family && !request.cb && request.app_data == size_token &&
          request.len == 12, "cfg-wire-header");
    msg.cm.app_data = request.app_data;
    receive(ctx, ctx, &msg, LINEAR, head + 3, head + 3);
    CHECK(nss_conn_table_count(family) == 1024, "rx-truncated-cfg");
    receive(ctx, ctx, &msg, FRAGMENT, head + 4, head + 4);
    CHECK(nss_conn_table_count(family) == REQUEST, "rx-valid-cfg");
    CHECK(!rx_logs && !wire_calls, "table-reply-legacy-route");
}

static void rx_non_table(void)
{
    struct packet msg = reply(V4, NSS_IPV4_RX_NODE_STATS_SYNC_MSG);
    unsigned int length = sizeof(msg.cm) + 4;

    msg.cm.response = NSS_CMN_RESPONSE_NOTIFY;
    receive(&core4, &core4, &msg, FRAGMENT, length, length);
    CHECK(!rx_logs && !node_calls && !wire_calls, "unaligned-ordinary-drop");
    receive(&core4, &core6, &msg, LINEAR, length, length);
    msg.cm.interface = V6;
    msg.cm.type = NSS_IPV6_RX_NODE_STATS_SYNC_MSG;
    receive(&core6, &core4, &msg, FRAGMENT_ALIGNED, length, length);
    CHECK(rx_logs == 2 && node_calls == 2 && notify_calls == 2 && notify_callbacks == 2,
          "ordinary-notify-route");
    allow_wire = true;
    msg = reply(V4, NSS_IPV4_TX_CREATE_RULE_MSG);
    receive(&core4, &core4, &msg, LINEAR, length, length);
    CHECK(rx_logs == 3 && wire_calls == 1 && ring_count == 0 && alloc_calls == 0,
          "ordinary-ack-route");
}

static void tx_public(void)
{
    for (unsigned int type = 0; type < 2; ++type) {
        struct packet packet = reply(V4, type ? SIZE : CFG);
        struct nss_ipv4_msg v4;
        struct nss_ipv6_msg v6;

        memcpy(&v4, &packet, sizeof(v4));
        memcpy(&v6, &packet, sizeof(v6));
        v6.cm.interface = V6;
        CHECK(nss_ipv4_tx(&core4, &v4) == NSS_TX_FAILURE_NOT_SUPPORTED, "public-v4-table");
        CHECK(nss_ipv4_tx_with_size(&core4, &v4, sizeof(v4)) == NSS_TX_FAILURE_NOT_SUPPORTED,
              "public-v4-sized-table");
        CHECK(nss_ipv6_tx(&core6, &v6) == NSS_TX_FAILURE_NOT_SUPPORTED, "public-v6-table");
        CHECK(nss_ipv6_tx_with_size(&core6, &v6, sizeof(v6)) == NSS_TX_FAILURE_NOT_SUPPORTED,
              "public-v6-sized-table");
        CHECK(nss_core_send_cmd(&core4, &v4, sizeof(v4), sizeof(v4)) ==
              NSS_TX_FAILURE_NOT_SUPPORTED, "public-core-table");
    }
    CHECK(!ring_count && !skb_allocs, "public-table-no-allocation");
    struct nss_ipv4_msg v4 = { .cm = reply(V4, NSS_IPV4_TX_CREATE_RULE_MSG).cm };
    struct nss_ipv6_msg v6 = { .cm = reply(V6, NSS_IPV6_TX_CREATE_RULE_MSG).cm };
    CHECK(nss_ipv4_tx(&core4, &v4) == NSS_TX_SUCCESS, "public-v4-ordinary");
    CHECK(nss_ipv6_tx_with_size(&core6, &v6, sizeof(v6)) == NSS_TX_SUCCESS, "public-v6-ordinary");
    CHECK(nss_core_send_cmd(&core4, &v4, sizeof(v4), sizeof(v4)) == NSS_TX_SUCCESS,
          "public-core-ordinary");
    CHECK(ring_count == 3 && interrupts == 3 && (ring_flags & H2N_BIT_FLAG_BUFFER_REUSABLE),
          "ordinary-tx-route");
}

static void tx_private(void)
{
    struct packet packet = reply(V4, CFG);
    unsigned char short_header[1] = { 0 };
    const int length = sizeof(packet.cm) + 12;

    packet.cm.len = 12;
    memset(packet.extra, 0x5a, sizeof(packet.extra));
    CHECK(nss_core_send_cmd(&core4, &packet, sizeof(packet.cm) - 1, PAGE_SIZE) ==
          NSS_TX_FAILURE_BAD_PARAM, "public-declared-short-header");
    CHECK(nss_core_send_cmd(&core4, short_header, sizeof(short_header), PAGE_SIZE) ==
          NSS_TX_FAILURE_BAD_PARAM, "public-short-header");
    CHECK(nss_core_send_cmd(&core4, &packet, length, length - 1) ==
          NSS_TX_FAILURE_BAD_PARAM, "public-short-destination");
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, sizeof(packet.cm) - 1) ==
          NSS_TX_FAILURE_BAD_PARAM, "private-short-header");
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, length - 1) ==
          NSS_TX_FAILURE_BAD_PARAM, "private-short-payload");
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, NSS_NBUF_PAYLOAD_SIZE + 1) ==
          NSS_TX_FAILURE_BAD_PARAM, "private-oversized");
    packet.cm.type = NSS_IPV4_TX_CREATE_RULE_MSG;
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, length) ==
          NSS_TX_FAILURE_BAD_PARAM, "private-non-table");
    CHECK(!ring_count && !skb_allocs, "invalid-tx-allocation");
    packet.cm.type = CFG;
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, sizeof(packet)) == NSS_TX_SUCCESS,
          "private-tx");
    CHECK(ring_count == 1 && ring_length == NSS_NBUF_PAYLOAD_SIZE && interrupts == 1,
          "private-ring-length");
    CHECK(!(ring_flags & H2N_BIT_FLAG_BUFFER_REUSABLE), "private-non-reusable");
    CHECK(!memcmp(ring_bytes, &packet, length), "private-payload");
    for (unsigned int i = length; i < ring_length; ++i)
        CHECK(ring_bytes[i] == 0, "private-zero-tail");
    fail_command = true;
    CHECK(nss_core_send_conn_cmd(&core4, &packet.cm, length) == NSS_TX_FAILURE_QUEUE,
          "private-error-propagated");
    CHECK(skb_frees == 1 && !skb_owned && ring_count == 1 && interrupts == 1, "private-tx-failure");
}

static void command_dma(void)
{
    const u32 len = sizeof(command_dma_buffer), unchanged = 17;
    u32 wire = unchanged;
    bool valid = false;

    if (!strcmp(test_case, "cmd-map-empty")) {
        CHECK(!nss_core_map_linear_cmd(&device4, command_dma_buffer, 0, &wire),
              "command-empty-result");
        CHECK(!command_maps && !command_checks && !command_unmaps && wire == unchanged,
              "command-empty-effects");
        return;
    }
    if (!strcmp(test_case, "cmd-map-zero")) {
        valid = true;
    } else if (!strcmp(test_case, "cmd-map-boundary")) {
        command_dma_address = UINT32_MAX - len + 1;
        valid = true;
    } else if (!strcmp(test_case, "cmd-map-error")) {
        command_dma_address = HOST_DMA_ERROR;
    } else if (!strcmp(test_case, "cmd-map-high")) {
        command_dma_address = (UINT64_C(1) << 32) + 32;
    } else {
        CHECK(!strcmp(test_case, "cmd-map-crossing"), "unknown-command-dma-case");
        command_dma_address = UINT32_MAX - len + 2;
    }
    CHECK(nss_core_map_linear_cmd(&device4, command_dma_buffer, len, &wire) == valid,
          "command-map-result");
    CHECK(command_maps == 1 && command_checks == 1, "command-map-checks");
    CHECK(command_unmaps == (!valid && command_dma_address != HOST_DMA_ERROR), "command-map-unmaps");
    CHECK(wire == (valid ? command_dma_address : unchanged), "command-wire-address");
}

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;
    test_case = argv[1];
    core4.state = core6.state = NSS_CORE_STATE_INITIALIZED;
    core4.nss_top = core6.nss_top = &top;
    top.ipv4_callback = notify4;
    top.ipv6_callback = notify6;
    top.ipv4_ctx = top.ipv6_ctx = &notify_cookie;
    core4.nss_rx_interface_handlers[V4].cb = nss_ipv4_rx_msg_handler;
    core6.nss_rx_interface_handlers[V6].cb = nss_ipv6_rx_msg_handler;

    if (!strcmp(test_case, "rx-malformed4") || !strcmp(test_case, "rx-malformed6"))
        rx_malformed();
    else if (!strcmp(test_case, "rx-non-table"))
        rx_non_table();
    else if (!strcmp(test_case, "tx-public"))
        tx_public();
    else if (!strcmp(test_case, "tx-private"))
        tx_private();
    else if (!strncmp(test_case, "cmd-map-", 8))
        command_dma();
    else
        return 2;
    printf("PASS %s\n", test_case);
    return 0;
}
