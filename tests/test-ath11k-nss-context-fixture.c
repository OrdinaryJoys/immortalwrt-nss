/* Fresh source fragments are inserted at the SOURCE markers by the runner.
 * Kernel/FW/allocator boundaries below are mocks, not a Linux skb or DMA test.
 */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#define ETH_ALEN 6
#define __KERNEL__ 1
#define NSS_FIRMWARE_VERSION_12_5 1
struct net_device;
struct sk_buff;
struct napi_struct { int unused; };
struct notifier_block;
struct module;
/* SOURCE_CONSTANTS */
#include "exports/nss_def.h"
#include "exports/nss_cmn.h"
#include "exports/nss_wifili_if.h"
/* SOURCE_LEGACY_TYPES */
/* SOURCE_REGISTRY */
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define smp_store_release(p, v) __atomic_store_n((p), (v), __ATOMIC_RELEASE)
#define likely(x) (x)
#define unlikely(x) (x)
#define NSS_PKT_STATS_INC(x) ((void)0)
#define NSS_PKT_STATS_DEC(x) ((void)0)
#define NSS_VERIFY_CTX_MAGIC(x) ((void)(x))
#define NSS_CORE_STATE_INITIALIZED 1
#define nss_warning(...) ((void)0)
#define nss_info(...) ((void)0)
#define NSS_IF_N2H_DATA_QUEUE_0 0
#define N2H_BIT_FLAG_IP_TRANSPORT_CHECKSUM_VALID 1
#define CHECKSUM_NONE 0
#define CHECKSUM_UNNECESSARY 1
#define NETIF_F_SG 1
#define NETIF_F_FRAGLIST 2
#define LINUX_VERSION_CODE 0x061200
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define NETDEV_TX_BUSY 1
static int failures, checks, callbacks, freed, linearized, messages, bug_armed;
static int linearize_failure, expected_nonlinear, stack_deliveries;
static jmp_buf bug_jump;
static void *expected_context;
static void check(bool ok, const char *why) {
    checks++;
    if (!ok) { failures++; fprintf(stderr, "FAIL: %s\n", why); }
}
static void bug(void) {
    if (bug_armed) longjmp(bug_jump, 1);
    fprintf(stderr, "unexpected BUG_ON\n"); abort();
}
#define BUG_ON(x) do { if (x) bug(); } while (0)
#define nss_assert(x) BUG_ON(!(x))
struct net_device_ops {
    uint16_t (*ndo_select_queue)(struct net_device *, struct sk_buff *, void *);
    int (*ndo_start_xmit)(struct sk_buff *, struct net_device *);
};
struct net_device {
    unsigned char guard[192];
    uint32_t features;
    unsigned real_num_rx_queues;
    struct net_device_ops *netdev_ops;
};
static void *netdev_priv(struct net_device *d) { return (char *)d + sizeof(*d); }
struct sk_buff {
    unsigned char *head;
    bool frags, frag_list, consumed;
    int ip_summed, protocol;
    struct net_device *dev;
};
static int skb_is_nonlinear(struct sk_buff *b) { return b->frags || b->frag_list; }
static int skb_has_frag_list(struct sk_buff *b) { return b->frag_list; }
static struct sk_buff *skb_shinfo(struct sk_buff *b) { return b; }
#define nr_frags frags
static int __skb_linearize(struct sk_buff *b) {
    linearized++;
    if (linearize_failure) return -1;
    b->frags = b->frag_list = false;
    return 0;
}
static void dev_kfree_skb_any(struct sk_buff *b) {
    check(!b->consumed, "skb consumed once");
    b->consumed = true; freed++;
}
static void dev_hold(struct net_device *d) { check(d != NULL, "real netdev hold"); }
static void dev_put(struct net_device *d) { check(d != NULL, "real netdev put"); }
static unsigned netif_skb_features(struct sk_buff *b) { return b->dev->features; }
static void skb_set_queue_mapping(struct sk_buff *b, unsigned q) { (void)b;(void)q; }
static void skb_record_rx_queue(struct sk_buff *b, unsigned q) { (void)b;(void)q; }
static int eth_type_trans(struct sk_buff *b, struct net_device *d) {
    (void)b; check(d != NULL, "real netdev protocol"); return 0;
}
static void netif_receive_skb(struct sk_buff *b) {
    stack_deliveries++; dev_kfree_skb_any(b);
}
struct nss_top_instance;
struct nss_ctx_instance {
    int state;
    struct nss_subsystem_dataplane_register subsys_dp_register[NSS_MAX_NET_INTERFACES];
    struct nss_top_instance *nss_top;
    nss_cmn_service_code_callback_t service_code_callback[256];
    void *service_code_ctx[256];
};
struct nss_top_instance {
    struct nss_ctx_instance nss[2];
    int wifi_handler_id;
    nss_wifili_msg_callback_t wifili_msg_callback;
};
static struct nss_top_instance nss_top_main;
static bool nss_is_dynamic_interface(uint32_t n) {
    return n >= NSS_DYNAMIC_IF_START && n < NSS_SPECIAL_IF_START;
}
void nss_wifili_release_external_if(nss_if_num_t n) { (void)n; }
static void nss_wifili_log_rx_msg(struct nss_wifili_msg *m) { (void)m; }
static void nss_core_log_msg_failures(struct nss_ctx_instance *c, struct nss_cmn_msg *m) {
    (void)c; (void)m;
}
static void nss_wifili_stats_sync(struct nss_ctx_instance *c,
                                struct nss_wifili_stats_sync_msg *m, unsigned i) {
    (void)c; (void)m; (void)i;
}
static void nss_wifili_stats_notify(struct nss_ctx_instance *c, unsigned i) {
    (void)c; (void)i;
}
/* SOURCE_CORE */
/* SOURCE_LOOKUP */
/* SOURCE_WIFILI */
typedef uint32_t u32;
struct ath11k_base {
    uint64_t canary;
    struct { u32 response; int complete; bool mesh_nss_offload_enabled; int if_num; } nss;
};
struct ath11k { struct { struct nss_ctx_instance *ctx; } nss; };
#define ATH11K_DBG_NSS 0
#define ATH11K_DBG_NSS_WDS 0
static void check_ab(struct ath11k_base *ab) {
    check(ab == expected_context, "ath11k receives original ab");
}
#define ath11k_dbg(ab, ...) check_ab(ab)
#define ath11k_warn(ab, ...) check_ab(ab)
#define ath11k_info(ab, ...) check_ab(ab)
static void complete(int *c) { (*c)++; }
static void ath11k_nss_peer_mem_free(struct ath11k_base *a, u32 p) { (void)a;(void)p; }
static void ath11k_nss_wifili_stats_sync(struct ath11k_base *a, void *m) { (void)a;(void)m; }
static void ath11k_nss_get_peer_stats(struct ath11k_base *a, void *m) { (void)a;(void)m; }
static void ath11k_nss_wifili_link_desc_return(struct ath11k_base *a, void *m) { (void)a;(void)m; }
static void ath11k_nss_process_mic_error(struct ath11k_base *ab, struct sk_buff *b) {
    check_ab(ab); callbacks++;
    check(skb_is_nonlinear(b) == expected_nonlinear, "callback skb linearity");
    dev_kfree_skb_any(b);
}
/* SOURCE_ATH */
static struct nss_ctx_instance *client_soc(struct ath11k_base *ab) {
    struct nss_ctx_instance *nss_contex;
    uint32_t features = 0;
    /* SOURCE_SOC_CALL */
    return nss_contex;
}
static struct nss_ctx_instance *client_radio(struct ath11k *ar, int radio_if_num) {
    uint32_t features = 0;
    /* SOURCE_RADIO_CALL */
    return ar->nss.ctx;
}
static void opaque_ext(void *ctx, struct sk_buff *b, struct napi_struct *n) {
    (void)n;
    check(ctx == expected_context, "opaque ext context identity");
    check(skb_is_nonlinear(b) == expected_nonlinear, "opaque feature contract");
    callbacks++; dev_kfree_skb_any(b);
}
static void legacy_ext(struct net_device *d, struct sk_buff *b, struct napi_struct *n) {
    (void)n;
    check(d == expected_context, "legacy gets actual ndev");
    check(skb_is_nonlinear(b) == expected_nonlinear, "legacy dynamic features");
    callbacks++; dev_kfree_skb_any(b);
}
static void opaque_msg(void *ctx, struct nss_wifili_msg *m) {
    (void)m; check(ctx == expected_context, "opaque notify identity"); messages++;
}
static void legacy_msg(void *ctx, struct nss_wifili_msg *m) {
    (void)m; check(ctx == expected_context, "legacy notify identity"); messages++;
}
static void reset(void) {
    memset(&nss_top_main, 0, sizeof(nss_top_main));
    nss_top_main.nss[0].nss_top = &nss_top_main;
    nss_top_main.nss[0].state = NSS_CORE_STATE_INITIALIZED;
    freed = callbacks = linearized = messages = stack_deliveries = 0;
    linearize_failure = expected_nonlinear = 0;
}
static struct sk_buff packet(unsigned char *head, int shape) {
    struct nss_wifili_soc_per_packet_metadata *m =
        (void *)(head + NSS_WIFILI_SOC_PER_PACKET_METADATA_OFFSET);
    memset(head, 0, 64);
    m->pkt_type = NSS_WIFILI_SOC_EXT_DATA_PKT_MIC_ERROR;
    return (struct sk_buff){.head=head,.frags=(shape & 1),.frag_list=(shape & 2)};
}
static void notify(struct nss_ctx_instance *c, unsigned id, bool ack) {
    struct nss_wifili_msg m = {0};
    m.cm.interface = id; m.cm.type = NSS_WIFILI_INIT_MSG;
    m.cm.response = ack ? NSS_CMN_RESPONSE_ACK : NSS_CMN_RESPONSE_NOTIFY;
    m.cm.cb = (nss_ptr_t)opaque_msg;
    m.cm.app_data = (nss_ptr_t)(uintptr_t)0xdead;
    nss_wifili_handler(c, &m.cm, NULL);
}
static void check_slot_rejection(struct nss_ctx_instance *c, unsigned id) {
#if HAS_OPAQUE
    struct net_device d = {0};
    struct nss_subsystem_dataplane_register old = c->subsys_dp_register[id];
    nss_wifili_msg_callback_t old_msg = nss_top_main.wifili_msg_callback;
    check(nss_register_wifili_if(id, NULL, legacy_ext, legacy_msg, &d, 3) == NULL,
          "legacy wrapper rejects opaque slot");
    check(memcmp(&old, &c->subsys_dp_register[id], sizeof(old)) == 0,
          "wrapper cannot create dual-type slot");
    check(nss_top_main.wifili_msg_callback == old_msg,
          "rejected legacy registration cannot overwrite global callback");
    bug_armed = 1;
    if (setjmp(bug_jump) == 0) {
        nss_core_register_subsys_dp(c, id, NULL, legacy_ext, NULL, &d, 3);
        check(false, "core register must reject opaque slot");
    } else {
        check(true, "core register BUG rejects opaque slot");
    }
    bug_armed = 0;
    check(memcmp(&old, &c->subsys_dp_register[id], sizeof(old)) == 0,
          "core rejection preserves opaque fields/features");
#else
    (void)c;(void)id;
#endif
}
int main(void) {
    union { max_align_t align; unsigned char bytes[1024]; } owner = {0}, storage;
    struct ath11k_base *ab = (void *)owner.bytes;
    struct ath11k ar = {0};
    struct net_device d = {0};
    struct nss_ctx_instance *c;
    unsigned id = NSS_WIFILI_INTERNAL_INTERFACE;
    reset(); ab->nss.if_num = id; expected_context = ab;
    /* Deliberately poison the fake ndev view; opaque code must never read it. */
    ((struct net_device *)(void *)owner.bytes)->features = NETIF_F_SG | NETIF_F_FRAGLIST;
    c = client_soc(ab);
    check(c != NULL, "actual ath11k SoC registration");
#if HAS_OPAQUE
    check(c->subsys_dp_register[id].ndev == NULL, "SoC is not a fake netdev");
    check(c->subsys_dp_register[id].wifili_ctx == ab, "SoC typed context");
    check(nss_cmn_get_interface_dev(c,id)==NULL, "public getter never exposes opaque SoC");
    check_slot_rejection(c, id);
#endif
    struct nss_wifili_msg msg = {0};
    msg.cm.interface=id;msg.cm.type=NSS_WIFILI_INIT_MSG;
    msg.cm.response=NSS_CMN_RESPONSE_ACK;msg.cm.cb=(nss_ptr_t)ath11k_nss_wifili_event_receive;
    nss_wifili_handler(c,&msg.cm,NULL);
    check(ab->nss.complete == 1, "actual ath11k ACK callback body");
    for (int shape=0; shape<4; shape++) {
        struct sk_buff b=packet(storage.bytes,shape);
        expected_nonlinear=0; linearize_failure=0;
        int before=callbacks, frees=freed;
        nss_core_handle_ext_buffer_pkt(c,id,&b,NULL,1);
        check(callbacks==before+1 && freed==frees+1, "actual client ext delivery");
    }
#if HAS_OPAQUE
    /* Per-owner notify must not be hijacked by a legacy/global registration. */
    check(nss_register_wifili_if(NSS_WIFILI_EXTERNAL_INTERFACE1,NULL,legacy_ext,
          legacy_msg,&d,0)!=NULL, "legacy independent slot");
    check(nss_cmn_get_interface_dev(c,NSS_WIFILI_EXTERNAL_INTERFACE1)==&d,
          "public getter preserves real legacy netdev");
    check(nss_cmn_get_interface_number(c,&d)==NSS_WIFILI_EXTERNAL_INTERFACE1,
          "reverse netdev lookup skips opaque slots");
    check(nss_register_wifili_if_ctx(NSS_WIFILI_EXTERNAL_INTERFACE0,opaque_ext,
          opaque_msg,NULL,0)==NULL, "empty slot rejects NULL opaque owner");
    msg.cm.response=NSS_CMN_RESPONSE_NOTIFY;
    nss_wifili_handler(c,&msg.cm,NULL);
    check(ab->nss.complete==2, "opaque notify uses actual per-owner callback");
    check(nss_register_wifili_if_ctx(NSS_WIFILI_EXTERNAL_INTERFACE0,opaque_ext,
          opaque_msg,&ar,0)!=NULL, "second opaque SoC owner");
    expected_context=&ar;
    notify(c,NSS_WIFILI_EXTERNAL_INTERFACE0,false);
    check(messages==1, "second opaque slot has its own notify callback");
    expected_context=ab;
    notify(c,id,false);
    check(ab->nss.complete==3, "first opaque notify was not globally replaced");
    check(nss_register_wifili_if_ctx(id,opaque_ext,opaque_msg,ab,0)==NULL,
          "duplicate opaque registration rejected");
    check(nss_register_wifili_if_ctx(NSS_WIFILI_EXTERNAL_INTERFACE1,opaque_ext,
          opaque_msg,ab,0)==NULL, "opaque rejects legacy occupied slot");
    check(client_radio(&ar,NSS_DYNAMIC_IF_START)!=NULL, "actual radio registration");
    check(c->subsys_dp_register[NSS_DYNAMIC_IF_START].wifili_ctx==&ar &&
          !c->subsys_dp_register[NSS_DYNAMIC_IF_START].ndev, "radio is opaque ar");
    check(nss_cmn_get_interface_dev(c,NSS_DYNAMIC_IF_START)==NULL,
          "public getter never exposes opaque radio");
    struct sk_buff b=packet(storage.bytes,3);
    int frees=freed, calls=callbacks;
    nss_core_handle_ext_buffer_pkt(c,NSS_DYNAMIC_IF_START,&b,NULL,0);
    check(freed==frees+1 && callbacks==calls, "radio has no ext callback");
    check(nss_register_wifili_radio_if(NSS_DYNAMIC_IF_START,NULL,NULL,NULL,&d,0)==NULL,
          "legacy radio wrapper rejects opaque radio");
    nss_unregister_wifili_radio_if(NSS_DYNAMIC_IF_START);
    check(!c->subsys_dp_register[NSS_DYNAMIC_IF_START].wifili_ctx,
          "quiesced radio unregister clears opaque owner");
    check(nss_register_wifili_radio_if(NSS_DYNAMIC_IF_START,NULL,NULL,NULL,&d,0)!=NULL,
          "cleared radio slot can be reused by legacy real netdev");
    check(nss_register_wifili_if_ctx(NSS_DYNAMIC_IF_START,opaque_ext,opaque_msg,ab,0)==NULL,
          "SoC API rejects radio id");
    check(nss_register_wifili_radio_if_ctx(id,&ar,0)==NULL, "radio API rejects SoC id");
    check(nss_register_wifili_if_ctx(NSS_MAX_NET_INTERFACES,opaque_ext,opaque_msg,ab,0)==NULL,
          "out-of-range rejected");
    check(nss_register_wifili_if_ctx(NSS_WIFILI_EXTERNAL_INTERFACE0,opaque_ext,
          opaque_msg,NULL,0)==NULL, "NULL opaque owner rejected");
    for (unsigned features=0; features<4; features++)
    for (int shape=0; shape<4; shape++)
    for (int fail=0; fail<2; fail++) {
        for (int legacy=0; legacy<2; legacy++) {
            reset(); c=&nss_top_main.nss[0];
            bool needs=((shape&1)&&!(features&NETIF_F_SG))||
                       ((shape&2)&&!(features&NETIF_F_FRAGLIST));
            if (legacy) {
                d.features=features;
                expected_context=&d;
                check(nss_register_wifili_if(id,NULL,legacy_ext,legacy_msg,&d,
                      features^3)!=NULL, "legacy setup");
            } else {
                expected_context=ab;
                check(nss_register_wifili_if_ctx(id,opaque_ext,opaque_msg,ab,
                      features)!=NULL, "opaque setup");
            }
            struct sk_buff p=packet(storage.bytes,shape);
            expected_nonlinear=needs ? 0 : !!shape; linearize_failure=fail;
            nss_core_handle_ext_buffer_pkt(c,id,&p,NULL,0);
            check(freed==1, "matrix free exactly once");
            check(callbacks==(needs&&fail ? 0 : 1), "matrix failfree/callback");
            check(linearized==(needs ? 1 : 0), "matrix features source");
            check(p.ip_summed==CHECKSUM_NONE, "checksum state preserved");
            notify(c,id,false);notify(c,id,true);
            check(messages==2, "notify/ACK exact registered context");
            nss_unregister_wifili_if(id);
            check(!c->subsys_dp_register[id].wifili_ctx &&
                  !c->subsys_dp_register[id].wifili_ext_cb &&
                  !c->subsys_dp_register[id].wifili_msg_cb &&
                  !c->subsys_dp_register[id].ndev,
                  "unregister clears both registration kinds after quiescence");
            notify(c,id,true);
            check(messages==2, "late message after unregister has no context");
            struct sk_buff after=packet(storage.bytes,shape);
            nss_core_handle_ext_buffer_pkt(c,id,&after,NULL,1);
            check(freed==2 && callbacks==(needs&&fail ? 0 : 1),
                  "unregistered owner drops without callback");
        }
    }
    reset(); c=&nss_top_main.nss[0]; d.features=0; expected_context=&d;
    check(nss_register_wifili_if(id,NULL,legacy_ext,legacy_msg,&d,0)!=NULL,
          "legacy before dynamic features change");
    d.features=NETIF_F_SG|NETIF_F_FRAGLIST;
    struct sk_buff dynamic=packet(storage.bytes,3);
    expected_nonlinear=1;
    nss_core_handle_ext_buffer_pkt(c,id,&dynamic,NULL,1);
    check(linearized==0 && callbacks==1, "legacy observes post-registration features");
    check(nss_register_wifili_if(id,NULL,legacy_ext,legacy_msg,&d,3)!=NULL,
          "legacy same-netdev registration update remains supported");
    d.features=0; expected_nonlinear=0;
    struct sk_buff dynamic_again=packet(storage.bytes,3);
    nss_core_handle_ext_buffer_pkt(c,id,&dynamic_again,NULL,1);
    check(linearized==1 && callbacks==2, "legacy dynamic features can change back");
    reset();expected_context=ab;c=client_soc(ab);
    struct sk_buff unknown=packet(storage.bytes,0);
    ((struct nss_wifili_soc_per_packet_metadata *)(void *)(storage.bytes+4))->pkt_type=0xffff;
    nss_core_handle_ext_buffer_pkt(c,id,&unknown,NULL,0);
    check(freed==1 && callbacks==0, "unknown ath11k ext metadata drops");
    struct sk_buff normal=packet(storage.bytes,0);
    nss_core_handle_buffer_pkt(c,id,&normal,NULL,0,0,0);
    struct sk_buff virt=packet(storage.bytes,0);
    nss_core_handle_virt_if_pkt(c,id,&virt);
    check(freed==3 && stack_deliveries==0, "opaque normal/virtual never use netdev ops");
#endif
    printf("checks=%d failures=%d wire_msg_size=%zu cmn_size=%zu\n",
           checks,failures,sizeof(struct nss_wifili_msg),sizeof(struct nss_cmn_msg));
    return failures ? 1 : 0;
}
