/* Host fixture for the ath11k wifili peer stats payload bound.
 *
 * The two extracted functions below are the complete post-patch definitions
 * from the prepared backports tree. The wifili wire structures come from the
 * prepared qca-nss-drv exports, so the compiled record sizes are the real 12.5
 * and legacy layouts selected by NSS_FIRMWARE_VERSION_12_5. ath11k peers, the
 * base lock, RCU, timers and the NSS receive path are host mocks; no target
 * header, module, firmware or device is exercised.
 *
 * Compile twice: HOST_WIDE=1 with -DNSS_FIRMWARE_VERSION_12_5 (12.5 build) and
 * HOST_WIDE=0 without it (legacy/reverted build).
 */
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef HOST_WIDE
#error "HOST_WIDE must be defined to 0 (legacy layout) or 1 (12.5 layout)"
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

#define __KERNEL__ 1
#define ETH_ALEN 6
/* HOST_CONSTANTS */
struct net_device;
struct sk_buff;
struct napi_struct;
struct notifier_block;
struct module;

#include "nss_def.h"
#include "nss_cmn.h"
#include "nss_wifili_if.h"

/* Wire ABI: 12.5 firmware scales the peer record to 212 bytes (retry block at
 * offset 188), the legacy layout is 196 bytes (retry block at offset 180).
 * Both keep the peer count prefix, the 2096-byte message and the 1632-byte
 * SOC statistics notification. */
#if HOST_WIDE
_Static_assert(sizeof(struct nss_wifili_rx_ctrl_stats) == 96, "12.5 rx ctrl size");
_Static_assert(sizeof(struct nss_wifili_retry_ctrl_stats) == 24, "12.5 retry ctrl size");
_Static_assert(sizeof(struct nss_wifili_peer_ctrl_stats) == 212, "12.5 peer ctrl size");
_Static_assert(sizeof(struct nss_wifili_peer_stats) == 216, "12.5 peer stats size");
_Static_assert(offsetof(struct nss_wifili_peer_ctrl_stats, retry) == 188,
               "12.5 retry block offset");
#else
_Static_assert(sizeof(struct nss_wifili_rx_ctrl_stats) == 88, "legacy rx ctrl size");
_Static_assert(sizeof(struct nss_wifili_retry_ctrl_stats) == 16, "legacy retry ctrl size");
_Static_assert(sizeof(struct nss_wifili_peer_ctrl_stats) == 196, "legacy peer ctrl size");
_Static_assert(sizeof(struct nss_wifili_peer_stats) == 200, "legacy peer stats size");
_Static_assert(offsetof(struct nss_wifili_peer_ctrl_stats, retry) == 180,
               "legacy retry block offset");
#endif
_Static_assert(offsetof(struct nss_wifili_peer_stats, wpcs) == 4, "peer count prefix size");
_Static_assert(offsetof(struct nss_wifili_msg, msg.peer_stats.stats) ==
               offsetof(struct nss_wifili_msg, msg), "peer stats payload follows the common header");
_Static_assert(sizeof(struct nss_wifili_msg) == 2096, "wire message size");
_Static_assert(sizeof(struct nss_wifili_stats_notification) == 1632, "stats notification size");

struct rate_info {
    u8 flags;
};

/* HOST_PEER_STATS */

#define HOST_PEER_COUNT_OFFSET 4u
#define HOST_STRIDE ((unsigned)sizeof(struct nss_wifili_peer_ctrl_stats))
#define HOST_OTHER_STRIDE ((unsigned)(HOST_WIDE ? 196u : 212u))
#define HOST_MAX_PEERS 4u

static unsigned checks;
static unsigned failures;
static unsigned warn_calls;
static unsigned info_calls;
static unsigned dbg_calls;
static char last_warn[512];
static char last_info[512];
static char last_dbg[512];
static unsigned peer_lookups;
static unsigned long jiffies = 0x4050;

static void check(bool value, const char *what)
{
    checks++;
    if (!value) {
        failures++;
        fprintf(stderr, "FAIL: %s\n", what);
    }
}

static void host_log_call(unsigned *counter, char *target, const char *format, ...)
{
    va_list arguments;

    va_start(arguments, format);
    (*counter)++;
    vsnprintf(target, 512, format, arguments);
    va_end(arguments);
}

#define ath11k_warn(ab, format, ...) \
    host_log_call(&warn_calls, last_warn, format, ##__VA_ARGS__)
#define ath11k_info(ab, format, ...) \
    host_log_call(&info_calls, last_info, format, ##__VA_ARGS__)
#define ath11k_dbg(ab, mask, format, ...) \
    host_log_call(&dbg_calls, last_dbg, format, ##__VA_ARGS__)
#define ATH11K_DBG_NSS 0
#define ATH11K_NSS_TXRX_NETDEV_STATS(direction, vif, bytes, packets) \
    do { (void)(vif); (void)(bytes); (void)(packets); } while (0)

struct ieee80211_sta {
    int unused;
};

struct ieee80211_vif {
    int unused;
};

struct ath11k_peer {
    u32 peer_id;
    struct ieee80211_sta *sta;
    struct ieee80211_vif *vif;
    struct {
        struct peer_stats *nss_stats;
        bool ext_vdev_up;
        struct ieee80211_vif *ext_vif;
    } nss;
};

struct ath11k_base {
    int base_lock;
    struct {
        bool stats_enabled;
        bool peer_stats_len_warned;
        bool peer_stats_layout_logged;
    } nss;
};

static struct ath11k_base ab;
static struct ath11k_peer peers[HOST_MAX_PEERS];
static struct peer_stats peer_counters[HOST_MAX_PEERS];
static struct ieee80211_sta fake_sta;
static struct ieee80211_vif fake_vif;

static void rcu_read_lock(void) { }
static void rcu_read_unlock(void) { }

static void spin_lock_bh(int *lock)
{
    if ((*lock)++)
        abort();
}

static void spin_unlock_bh(int *lock)
{
    if (--(*lock))
        abort();
}

static struct ath11k_peer *ath11k_peer_find_by_id(struct ath11k_base *base, u32 peer_id)
{
    unsigned i;

    (void)base;
    peer_lookups++;
    for (i = 0; i < HOST_MAX_PEERS; i++) {
        if (peers[i].sta && peers[i].peer_id == peer_id)
            return &peers[i];
    }
    return NULL;
}

/* HOST_FUNCTIONS */

#define HOST_PAYLOAD_OFFSET ((unsigned)offsetof(struct nss_wifili_msg, msg.peer_stats.stats))

/* Model the message buffer the NSS driver hands to the callback: the common
 * header followed by exactly cm.len bytes of peer stats. ASan therefore flags
 * any read past the firmware-declared payload. */
struct host_message {
    unsigned char *memory;
    size_t len;
    struct nss_wifili_msg *msg;
    struct nss_wifili_peer_stats *stats;
};

static struct host_message message_new(size_t len)
{
    struct host_message message;

    message.len = len;
    message.memory = malloc(HOST_PAYLOAD_OFFSET + (len ? len : 1));
    if (!message.memory) {
        fprintf(stderr, "allocation failed\n");
        abort();
    }
    memset(message.memory, 0, HOST_PAYLOAD_OFFSET);
    memset(message.memory + HOST_PAYLOAD_OFFSET, 0xA5, len ? len : 1);
    message.msg = (struct nss_wifili_msg *)(void *)message.memory;
    message.msg->cm.len = (uint16_t)len;
    message.stats = &message.msg->msg.peer_stats.stats;
    return message;
}

static void message_drop(struct host_message *message)
{
    free(message->memory);
    message->memory = NULL;
    message->msg = NULL;
    message->stats = NULL;
}

static struct nss_wifili_peer_ctrl_stats *record_at(struct host_message *message, unsigned index)
{
    return (struct nss_wifili_peer_ctrl_stats *)(void *)
        (message->memory + HOST_PAYLOAD_OFFSET + HOST_PEER_COUNT_OFFSET + index * HOST_STRIDE);
}

static void reset_world(bool stats_enabled)
{
    unsigned i;

    memset(&ab, 0, sizeof(ab));
    ab.nss.stats_enabled = stats_enabled;
    memset(peers, 0, sizeof(peers));
    memset(peer_counters, 0, sizeof(peer_counters));
    peer_lookups = 0;
    warn_calls = 0;
    info_calls = 0;
    dbg_calls = 0;
    last_warn[0] = '\0';
    last_info[0] = '\0';
    last_dbg[0] = '\0';
    for (i = 0; i < HOST_MAX_PEERS; i++)
        peers[i].vif = &fake_vif;
}

static void add_peer(unsigned slot, u32 peer_id)
{
    peers[slot].peer_id = peer_id;
    peers[slot].sta = &fake_sta;
    peers[slot].nss.nss_stats = &peer_counters[slot];
}

static void fill_record(struct nss_wifili_peer_ctrl_stats *record, u32 peer_id, u32 base)
{
    memset(record, 0, sizeof(*record));
    record->peer_id = peer_id;
    record->tx.tx_mcast_cnt = base + 1;
    record->tx.tx_ucast_cnt = base + 2;
    record->tx.tx_bcast_cnt = base + 3;
    record->tx.tx_mcast_bytes = base + 10;
    record->tx.tx_ucast_bytes = base + 20;
    record->tx.tx_bcast_bytes = base + 30;
    record->tx.retries = base + 40;
    record->tx.dropped.drop_stats[0] = base + 50;
    record->tx.dropped.drop_stats[NSS_WIFILI_TQM_RR_MAX - 1] = base + 60;
    record->tx.amsdu_cnt = base + 500;
    record->tx.non_amsdu_cnt = base + 600;
    record->tx.ofdma = base + 700;
    record->retry.tx_failed_retry_count = base + 70;
    record->retry.tx_multiple_retry_count = base + 80;
    record->retry.rx_retry_count = base + 90;
#if HOST_WIDE
    record->retry.tx_mpdu_retry_count = base + 1300;
    record->retry.tx_mpdu_total_retry_count = base + 1400;
#endif
    record->rx.rx_recvd = base + 100;
    record->rx.rx_recvd_bytes = base + 200;
    record->rx.err.mic_err = base + 300;
    record->rx.err.decrypt_err = base + 400;
    record->rx.amsdu_cnt = base + 800;
    record->rx.non_amsdu_cnt = base + 900;
    record->rx.rx_intra_bss_pkts_num = base + 1100;
    record->rx.rx_intra_bss_fail_num = base + 1200;
}

static void check_peer_counters(unsigned slot, u32 base, const char *what)
{
    const struct peer_stats *stats = &peer_counters[slot];
    char name[160];

#define EXPECT(field, expected)                                        \
    do {                                                               \
        if (snprintf(name, sizeof(name), "%s %s", what, #field) >=     \
            (int)sizeof(name))                                         \
            name[sizeof(name) - 1] = '\0';                             \
        check(stats->field == (u32)(expected), name);                  \
    } while (0)

    EXPECT(tx_packets, base * 3 + 6);
    EXPECT(tx_bytes, base * 3 + 60);
    EXPECT(tx_retries, base + 40);
    EXPECT(tx_dropped, base * 2 + 110);
    EXPECT(tx_failed, base + 70);
    EXPECT(rx_packets, base + 100);
    EXPECT(rx_bytes, base + 200);
    EXPECT(rx_dropped, base * 2 + 700);
    EXPECT(tx_amsdu, base + 500);
    EXPECT(tx_non_amsdu, base + 600);
    EXPECT(tx_ofdma, base + 700);
    EXPECT(tx_multiple_retries, base + 80);
#if HOST_WIDE
    EXPECT(tx_mpdu_retries, base + 1300);
    EXPECT(tx_mpdu_total_retries, base + 1400);
#else
    EXPECT(tx_mpdu_retries, 0);
    EXPECT(tx_mpdu_total_retries, 0);
#endif
    EXPECT(rx_amsdu, base + 800);
    EXPECT(rx_non_amsdu, base + 900);
    EXPECT(rx_retries, base + 90);
    EXPECT(rx_intra_bss, base + 1100);
    EXPECT(rx_intra_bss_fail, base + 1200);
    EXPECT(rx_mic_err, base + 300);
    EXPECT(rx_decrypt_err, base + 400);
#undef EXPECT
}

static void scenario_rejected(void)
{
    struct host_message message;

    /* A peer count of zero is not a parseable peer stats message. */
    reset_world(true);
    message = message_new(HOST_PEER_COUNT_OFFSET);
    message.stats->npeers = 0;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0 && peer_lookups == 0,
          "zero peer count rejected before peer data");
    check(strstr(last_warn, "invalid npeers=0") != NULL,
          "zero peer count warning reports the invalid count");
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1, "rejection warning is one-shot");
    message_drop(&message);

    /* A count beyond the defensive cap cannot be a firmware payload. */
    reset_world(true);
    message = message_new(65535);
    message.stats->npeers = 1025;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0 && peer_lookups == 0,
          "peer count beyond the 1024 cap rejected");
    check(strstr(last_warn, "invalid npeers=1025") != NULL,
          "peer count cap warning reports the invalid count");
    message_drop(&message);

    /* Less than the peer count field itself: it must not be read. */
    reset_world(true);
    message = message_new(HOST_PEER_COUNT_OFFSET - 1);
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0 && peer_lookups == 0,
          "message shorter than the peer count rejected");
    check(strstr(last_warn, "message too short") != NULL,
          "short message warning names the missing peer count");
    message_drop(&message);

    /* One peer record less than the compiled layout requires. */
    reset_world(true);
    add_peer(0, 7);
    message = message_new(sizeof(struct nss_wifili_peer_stats) - 1);
    message.stats->npeers = 1;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0 && peer_lookups == 0,
          "truncated single-peer payload rejected");
    check(strstr(last_warn, "no complete record") != NULL,
          "truncated payload warning reports the missing complete record");
    message_drop(&message);
}

static void scenario_disabled(void)
{
    struct host_message message;

    reset_world(false);
    add_peer(0, 7);
    message = message_new(sizeof(struct nss_wifili_peer_stats));
    message.stats->npeers = 1;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 0 && info_calls == 0 && peer_lookups == 0,
          "disabled peer stats stay a silent no-op");
    message_drop(&message);
}

static void scenario_same_layout(void)
{
    const u32 ids[2] = { 100, 101 };
    const u32 bases[2] = { 1000, 2000 };
    struct host_message message;
    char expected[160];
    unsigned i;

    reset_world(true);
    for (i = 0; i < 2; i++)
        add_peer(i, ids[i]);
    message = message_new(HOST_PEER_COUNT_OFFSET + 2 * HOST_STRIDE);
    message.stats->npeers = 2;
    for (i = 0; i < 2; i++)
        fill_record(record_at(&message, i), ids[i], bases[i]);

    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 0 && info_calls == 1,
          "compiled-layout payload accepted and logged once");
    check(peer_lookups == 2, "both peers of the compiled layout are parsed");
    if (snprintf(expected, sizeof(expected),
                 "nss wifili peer stats: len=%u npeers=%u stride=%zu\n",
                 (unsigned)message.len, 2u, (size_t)HOST_STRIDE) >=
        (int)sizeof(expected))
        expected[sizeof(expected) - 1] = '\0';
    check(strcmp(last_info, expected) == 0, "layout log line has the probe format");
    check_peer_counters(0, bases[0], "first peer");
    check_peer_counters(1, bases[1], "second peer");

    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(info_calls == 1, "layout log line is one-shot");
    check(peer_counters[0].tx_packets == 2 * (bases[0] * 3 + 6),
          "repeated message accumulates peer counters");

    /* Exactly the declared length of a single peer record. */
    reset_world(true);
    add_peer(0, ids[0]);
    message_drop(&message);
    message = message_new(sizeof(struct nss_wifili_peer_stats));
    message.stats->npeers = 1;
    fill_record(record_at(&message, 0), ids[0], bases[0]);
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 0 && info_calls == 1 && peer_lookups == 1,
          "single-peer payload at the exact declared length is accepted");
    check_peer_counters(0, bases[0], "exact-length peer");
    message_drop(&message);

    /* A payload longer than the compiled layout needs is still parseable. */
    reset_world(true);
    add_peer(0, ids[0]);
    message = message_new(HOST_PEER_COUNT_OFFSET + HOST_STRIDE + 8);
    message.stats->npeers = 1;
    fill_record(record_at(&message, 0), ids[0], bases[0]);
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 0 && info_calls == 1 && peer_lookups == 1,
          "payload with an extra tail is accepted");
    check_peer_counters(0, bases[0], "extra-tail peer");
    message_drop(&message);
}

static void scenario_probe_after_rejection(void)
{
    struct host_message message;

    /* A first short message must not suppress the later layout probe. */
    reset_world(true);
    message = message_new(HOST_PEER_COUNT_OFFSET);
    message.stats->npeers = 0;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0, "probe: first message rejected");
    message_drop(&message);

    add_peer(0, 7);
    message = message_new(sizeof(struct nss_wifili_peer_stats));
    message.stats->npeers = 1;
    fill_record(record_at(&message, 0), 7, 1000);
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 1 && peer_lookups == 1,
          "probe: accepted message still logs the layout after a rejection");
    message_drop(&message);
}

#if HOST_WIDE
static void scenario_foreign_layout(void)
{
    struct host_message message;
    unsigned char *memory;

    /* Firmware still reports the legacy 196-byte record: the 12.5 build must
     * refuse the payload and never walk into it with the wide stride. */
    reset_world(true);
    add_peer(0, 100);
    message = message_new(HOST_PEER_COUNT_OFFSET + 2 * HOST_OTHER_STRIDE);
    message.stats->npeers = 2;
    memory = message.memory;
    *(u32 *)(void *)(memory + HOST_PEER_COUNT_OFFSET) = 100;
    *(u32 *)(void *)(memory + HOST_PEER_COUNT_OFFSET + HOST_OTHER_STRIDE) = 101;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1 && info_calls == 0 && peer_lookups == 0,
          "legacy payload rejected before peer data in the 12.5 build");
    check(strstr(last_warn, "payload too short") != NULL,
          "legacy payload warning names the layout mismatch");
    check(peer_counters[0].tx_packets == 0,
          "rejected foreign payload leaves peer counters untouched");
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 1, "foreign layout warning is one-shot");
    message_drop(&message);
}
#else
static void scenario_foreign_layout(void)
{
    struct host_message message;
    unsigned char *memory;

    /* With the define reverted, a 12.5 firmware payload is longer than the
     * legacy layout requires. It is accepted, and the probe line exposes the
     * mismatch: len = 4 + n*212 while the host stride stays 196. The parse
     * stays inside the declared payload, so this direction is not unsafe. */
    reset_world(true);
    add_peer(0, 100);
    message = message_new(HOST_PEER_COUNT_OFFSET + 2 * HOST_OTHER_STRIDE);
    message.stats->npeers = 2;
    memory = message.memory;
    *(u32 *)(void *)(memory + HOST_PEER_COUNT_OFFSET) = 100;
    *(u32 *)(void *)(memory + HOST_PEER_COUNT_OFFSET + HOST_OTHER_STRIDE) = 101;
    ath11k_nss_get_peer_stats(&ab, message.msg);
    check(warn_calls == 0 && info_calls == 1 && peer_lookups == 2,
          "legacy build accepts the longer 12.5 payload without a warning");
    check(strstr(last_info, "len=428 npeers=2 stride=196") != NULL,
          "legacy build probe exposes the 12.5/legacy length mismatch");
    message_drop(&message);
}
#endif

static void report(void)
{
    printf("{\"wide\":%d,\"checks\":%u,\"failures\":%u,"
           "\"rx_ctrl\":%zu,\"retry_ctrl\":%zu,\"peer_ctrl\":%zu,"
           "\"peer_stats\":%zu,\"retry_off\":%zu,"
           "\"message\":%zu,\"stats_notification\":%zu}\n",
           HOST_WIDE, checks, failures,
           sizeof(struct nss_wifili_rx_ctrl_stats),
           sizeof(struct nss_wifili_retry_ctrl_stats),
           sizeof(struct nss_wifili_peer_ctrl_stats),
           sizeof(struct nss_wifili_peer_stats),
           offsetof(struct nss_wifili_peer_ctrl_stats, retry),
           sizeof(struct nss_wifili_msg),
           sizeof(struct nss_wifili_stats_notification));
}

int main(void)
{
    scenario_rejected();
    scenario_disabled();
    scenario_same_layout();
    scenario_probe_after_rejection();
    scenario_foreign_layout();
    report();
    return failures ? 1 : 0;
}
