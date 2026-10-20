#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#if HOST_NSS
#define CPTCFG_ATH11K_NSS_SUPPORT 1
#endif
#if HOST_MESH
#define CPTCFG_ATH11K_NSS_MESH_SUPPORT 1
#endif
#if HOST_DEBUG
#define CPTCFG_ATH11K_DEBUGFS 1
#endif
typedef uint32_t u32;
struct list_head { struct list_head *next, *prev; };
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v, x) ((v) = (x))
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define LIST_POISON1 ((void *)0x100UL)
#define LIST_POISON2 ((void *)0x122UL)
#define __list_add_valid(a, b, c) true
#define __list_del_entry_valid(a) true
HOST_LIST_FUNCTIONS
typedef struct { unsigned initialized, depth, uses; } spinlock_t;
static unsigned checks, failures, scenarios, api_errors, alloc_call, hw_fail_at;
static unsigned live_hw;
#if HOST_MESH
static unsigned payload_count, payload_frees, freed_under_lock, tx_calls;
#endif
static unsigned long long normal_signature;
static void check(bool ok) { checks++; if (!ok) failures++; }
static void spin_lock_init(spinlock_t *l)
{
    if (l->initialized || l->depth) api_errors++;
    l->initialized++;
}
static void spin_lock_bh(spinlock_t *l)
{
    if (!l->initialized || l->depth) api_errors++;
    l->depth++; l->uses++;
}
static void spin_unlock_bh(spinlock_t *l);
#define ETH_ALEN 6
HOST_STRUCTURES
struct completion { unsigned done; };
struct arvif_nss {
    struct list_head mpath_dump, mpp_dump;
    unsigned mpath_dump_num_entries, mpp_dump_num_entries;
    struct completion dump_mpath_complete;
    bool mpp_aging, mpp_dump_req;
    void *mesh_handle;
};
struct ath11k_base;
struct ath11k;
struct ath11k_pdev {
    struct ath11k *ar;
    struct { unsigned tx_chain_mask, rx_chain_mask; } cap;
};
struct ieee80211_hw { void *priv; };
struct ath11k {
    struct ieee80211_hw *hw;
    struct ath11k_base *ab;
    struct ath11k_pdev *pdev;
    int pdev_idx, lmac_id;
    void *wmi;
    unsigned cfg_tx_chainmask, cfg_rx_chainmask, num_tx_chains, num_rx_chains;
#if HOST_NSS
    struct { spinlock_t dump_lock; } nss;
#endif
    spinlock_t data_lock;
    struct list_head arvifs, ppdu_stats_info, channel_update_queue;
    int conf_mutex, vdev_setup_done, vdev_delete_done, peer_assoc_done, peer_delete_done;
    int install_key_done, bss_survey_done, completed_11d_scan, regd_update_work;
    int channel_update_work, wmi_mgmt_tx_work, wmi_mgmt_tx_queue, fw_stats;
    struct { int started, completed, on_channel, timeout; } scan;
    struct { int wmi_sync; } thermal;
    unsigned long monitor_flags;
    int monitor_vdev_id, vdev_id_11d_scan;
};
struct ath11k_base {
    unsigned long dev_flags;
    int num_radios, hw_params;
    struct ath11k_pdev pdevs[3];
    struct { int wmi[3]; } wmi_ab;
};
struct ath11k_vif { struct ath11k *ar; struct arvif_nss nss; };
#define ATH11K_FLAG_REGISTERED 0
#define ATH11K_FLAG_MONITOR_STARTED 0
#define ATH11K_FLAG_MONITOR_VDEV_CREATED 1
#define ATH11K_11D_INVALID_VDEV_ID -1
#define ATH11K_DBG_NSS 0
#define ath11k_warn(ab, ...) ((void)(ab))
#define init_completion(p) (*(p) = 0)
#define INIT_WORK(p, fn) (*(p) = 1)
#define INIT_DELAYED_WORK(p, fn) (*(p) = 1)
#define skb_queue_head_init(p) (*(p) = 1)
static void mutex_init(int *p) { *p = 1; }
static bool test_bit(unsigned b, const unsigned long *p) { return (*p >> b) & 1; }
static void clear_bit(unsigned b, unsigned long *p) { *p &= ~(1UL << b); }
static int get_num_chains(unsigned value) { return __builtin_popcount(value); }
static int ath11k_hw_get_mac_from_pdev_id(int *params, int i) { (void)params; return i; }
static void ath11k_wmi_pdev_attach(struct ath11k_base *ab, int i) { (void)ab; (void)i; }
static void ath11k_fw_stats_init(struct ath11k *ar) { ar->fw_stats = 1; }
static void ath11k_fw_stats_free(int *p) { *p = 0; }
static const int ath11k_ops;
static struct ieee80211_hw *ieee80211_alloc_hw(size_t bytes, const int *ops)
{
    (void)ops;
    if (alloc_call++ == hw_fail_at) return NULL;
    struct ieee80211_hw *hw = calloc(1, sizeof(*hw));
    if (!hw) abort();
    hw->priv = calloc(1, bytes);
    if (!hw->priv) abort();
    live_hw++;
    return hw;
}
static void ieee80211_free_hw(struct ieee80211_hw *hw)
{
    struct ath11k *ar = hw->priv;
#if HOST_NSS
    if (ar->nss.dump_lock.depth) api_errors++;
#endif
    (void)ar;
    free(hw->priv); free(hw); live_hw--;
}
void ath11k_mac_destroy(struct ath11k_base *ab);
HOST_MAC_FUNCTIONS

#if HOST_MESH
#define GFP_ATOMIC 0
#define NSS_TX_SUCCESS 0
#define NSS_WIFI_MESHMGR_SUCCESS 0
#define NSS_WIFI_MESHMGR_FAILURE_ONESHOT_ALREADY_ATTACHED 2
typedef int nss_tx_status_t;
typedef int nss_wifi_meshmgr_status_t;
struct nss_wifi_mesh_msg { struct { struct nss_wifi_mesh_path_table_dump mpath_table_dump; } msg; };
static struct { void *ptr; bool freed; } payloads[128];
static struct ath11k_vif *active_vif;
static bool inject_reply, fail_payload;
static int tx_status;
static void deliver(unsigned count, bool more);
static void *kzalloc(size_t bytes, int flag)
{
    (void)flag;
    if (fail_payload) return NULL;
    if (payload_count == 128) abort();
    void *p = calloc(1, bytes);
    if (!p) abort();
    payloads[payload_count++] = (typeof(payloads[0])){p, false};
    return p;
}
static void kfree(void *p)
{
    if (active_vif->ar->nss.dump_lock.depth) freed_under_lock++;
    for (unsigned i = 0; i < payload_count; i++) {
        if (payloads[i].ptr != p) continue;
        if (payloads[i].freed) api_errors++;
        payloads[i].freed = true; payload_frees++;
        return;
    }
    api_errors++;
}
/* Quarantine host storage until case end so negative controls fail by assertions,
 * not by executing undefined accesses through the intentionally broken list. */
static void host_forget_free(void *p) __attribute__((unused));
static void host_forget_free(void *p) { (void)p; }
static void complete(struct completion *p) { p->done++; }
static int nss_wifi_meshmgr_dump_mesh_path_sync(void *handle) { (void)handle; tx_calls++; return tx_status; }
static int nss_wifi_meshmgr_dump_mesh_proxy_path_sync(void *handle) { (void)handle; tx_calls++; return tx_status; }
HOST_NSS_FUNCTIONS
static void deliver(unsigned count, bool more)
{
    size_t bytes = sizeof(struct nss_wifi_mesh_msg) + count * sizeof(struct nss_wifi_mesh_path_dump_entry);
    struct nss_wifi_mesh_msg *msg = calloc(1, bytes);
    if (!msg) abort();
    msg->msg.mpath_table_dump.num_entries = count;
    msg->msg.mpath_table_dump.more_events = more;
    for (unsigned i = 0; i < count; i++) msg->msg.mpath_table_dump.path_entry[i].metric = 100 + i;
    int ret = ath11k_nss_mesh_process_path_table_dump_msg(active_vif, msg);
    check(ret == (fail_payload ? -ENOMEM : 0));
    free(msg);
}
#endif
static void spin_unlock_bh(spinlock_t *l)
{
    if (l->depth != 1) api_errors++;
    l->depth = 0;
#if HOST_MESH
    if (inject_reply && l == &active_vif->ar->nss.dump_lock) {
        inject_reply = false;
        if (!list_empty(&active_vif->nss.mpath_dump)) { api_errors++; return; }
        deliver(2, false);
    }
#endif
}
static void allocation_case(int radios, int failure)
{
    struct ath11k_base ab = {.num_radios=radios};
    unsigned errors_before = api_errors;
    alloc_call = 0; hw_fail_at = failure < 0 ? ~0U : (unsigned)failure;
    int ret = ath11k_mac_allocate(&ab);
    check(ret == (failure < 0 ? 0 : -ENOMEM));
    if (!ret) {
        check(live_hw == (unsigned)radios);
        for (int i = 0; i < radios; i++) {
            struct ath11k *ar = ab.pdevs[i].ar;
            check(ar && ar->pdev_idx == i && ar->hw->priv == ar);
#if HOST_NSS
            check(ar->nss.dump_lock.initialized == 1);
            spin_lock_bh(&ar->nss.dump_lock);
#endif
        }
        ab.dev_flags |= 1UL << ATH11K_FLAG_REGISTERED;
        unsigned calls = alloc_call;
        for (unsigned retry = 0; retry < 3; retry++) check(ath11k_mac_allocate(&ab) == 0);
        check(alloc_call == calls);
        for (int i = 0; i < radios; i++) {
#if HOST_NSS
            check(ab.pdevs[i].ar->nss.dump_lock.initialized == 1);
            spin_unlock_bh(&ab.pdevs[i].ar->nss.dump_lock);
#endif
        }
        normal_signature = normal_signature * 131 + radios;
        ath11k_mac_destroy(&ab);
    }
    check(live_hw == 0);
    for (int i = 0; i < radios; i++) check(ab.pdevs[i].ar == NULL);
    check(api_errors == errors_before);
    scenarios++;
}
#if HOST_MESH
static void dump_case(unsigned stale, int status, bool interleave, bool allocation_failure)
{
    struct ath11k_base ab = {.num_radios=1};
    alloc_call = 0; hw_fail_at = ~0U;
    unsigned errors_before = api_errors;
    check(ath11k_mac_allocate(&ab) == 0);
    struct ath11k_vif vif = {.ar=ab.pdevs[0].ar};
    active_vif = &vif;
    INIT_LIST_HEAD(&vif.nss.mpath_dump); INIT_LIST_HEAD(&vif.nss.mpp_dump);
    payload_count = payload_frees = freed_under_lock = tx_calls = 0;
    memset(payloads, 0, sizeof(payloads));
    fail_payload = false; inject_reply = false;
    if (stale) deliver(stale, false);
    tx_status = status; inject_reply = interleave;
    fail_payload = allocation_failure;
    unsigned frees_before = payload_frees;
    int ret = ath11k_nss_dump_mpath_request(&vif);
    check(ret == (status == NSS_TX_SUCCESS ? 0 : -EINVAL));
    unsigned fresh = interleave && !allocation_failure ? 2 : 0;
    check(vif.nss.mpath_dump_num_entries == fresh);
    check(payload_frees == frees_before + (stale ? 1 : 0));
    check(freed_under_lock == 0 && tx_calls == 1);
    bool valid = fresh ? !list_empty(&vif.nss.mpath_dump) : list_empty(&vif.nss.mpath_dump);
    check(valid);
    /* Refuse to traverse a failed source-head invariant in the broken variant. */
    if (valid && api_errors == errors_before) {
        fail_payload = false;
        if (fresh) {
            struct ath11k_nss_mpath_entry *entry = list_first_entry(&vif.nss.mpath_dump, struct ath11k_nss_mpath_entry, list);
            check(entry->num_entries == 2 && entry->mpath[1].metric == 101);
        }
        tx_status = NSS_TX_SUCCESS;
        check(ath11k_nss_dump_mpath_request(&vif) == 0);
        check(list_empty(&vif.nss.mpath_dump));
        check(vif.nss.mpath_dump_num_entries == 0);
        deliver(3, true); deliver(1, false);
        check(vif.nss.mpath_dump_num_entries == 4);
        check(ath11k_nss_dump_mpath_request(&vif) == 0);
        check(list_empty(&vif.nss.mpath_dump));
        for (unsigned i = 0; i < payload_count; i++) check(payloads[i].freed);
    }
    inject_reply = fail_payload = false;
    for (unsigned i = 0; i < payload_count; i++) free(payloads[i].ptr);
    check(api_errors == errors_before);
    ath11k_mac_destroy(&ab); active_vif = NULL;
    scenarios++;
}
static void mpp_control(void)
{
    struct ath11k_base ab = {.num_radios=1};
    alloc_call = 0; hw_fail_at = ~0U; check(ath11k_mac_allocate(&ab) == 0);
    struct ath11k_vif vif = {.ar=ab.pdevs[0].ar};
    active_vif=&vif; INIT_LIST_HEAD(&vif.nss.mpp_dump);
    payload_count=payload_frees=0; fail_payload=false; inject_reply=false;
    struct ath11k_nss_mpp_entry *p = kzalloc(sizeof(*p), GFP_ATOMIC);
    list_add_tail(&p->list, &vif.nss.mpp_dump); vif.nss.mpp_dump_num_entries=1;
    tx_status=NSS_TX_SUCCESS;
    check(ath11k_nss_dump_mpp_request(&vif) == 0);
    check(list_empty(&vif.nss.mpp_dump) && payload_frees == 1 && vif.nss.mpp_dump_num_entries == 0);
    free(p); active_vif=NULL; ath11k_mac_destroy(&ab); scenarios++;
}
#endif
int main(void)
{
    (void)list_add_tail; (void)list_del; (void)list_is_head;
    (void)list_splice_tail; (void)list_splice_tail_init;
    /* Exercise the common lock boundary even when mesh functions are absent. */
    spinlock_t local = {0}; spin_lock_init(&local); spin_lock_bh(&local); spin_unlock_bh(&local);
    for (int radios = 1; radios <= 3; radios++)
        for (int fail = -1; fail < radios; fail++) allocation_case(radios, fail);
#if HOST_MESH
    for (unsigned stale = 0; stale <= 3; stale++)
        for (int status = 0; status <= 1; status++)
            for (int interleave = 0; interleave <= 1; interleave++)
                for (int alloc_fail = 0; alloc_fail <= 1; alloc_fail++) dump_case(stale, status, interleave, alloc_fail);
    mpp_control();
#endif
    check(live_hw == 0);
    printf("{\"scenarios\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%llu\"}\n",
        scenarios, checks, failures, normal_signature);
    return failures ? 1 : 0;
}
