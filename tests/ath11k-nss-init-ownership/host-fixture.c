#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
typedef int nss_tx_status_t;
typedef int nss_state_t;
typedef int nss_if_num_t;
#define GFP_KERNEL 0
#define GFP_ATOMIC 0
#define ENOTSUPP EOPNOTSUPP
#define NSS_TX_SUCCESS 0
#define NSS_STATE_INITIALIZED 1
#define NSS_STATE_UNINITIALIZED 0
#define NSS_CORE_STATE_INITIALIZED 1
#define NSS_WIFILI_INTERNAL_INTERFACE 100
#define NSS_WIFILI_EXTERNAL_INTERFACE0 101
#define NSS_WIFILI_EXTERNAL_INTERFACE1 102
#define NSS_WIFILI_EXTERNAL_INTERFACE_MAX 2
#define NSS_MAX_NET_INTERFACES 256
#define ATH11K_NSS_MSG_ACK 0
#define ATH11K_NSS_MSG_TIMEOUT_MS 5000
#define HAL_SRNG_RING_ID_LMAC1_ID_START 1
#define DP_TCL_NUM_RING_MAX 3
#define DP_REO_DST_RING_MAX 4
#define DP_RXDMA_NSS_REFILL_RING_SIZE 128
#define DIV_ROUND_UP(n,d) (((n) + (d) - 1) / (d))
#define BUG_ON(v) do { if (v) abort(); } while (0)
#define WARN_ON(v) ((void)(v))
#define nss_assert(v) BUG_ON(!(v))
#define NSS_VERIFY_CTX_MAGIC(ctx) BUG_ON(!(ctx))
static void host_log(const char *format, ...) { (void)format; }
#define nss_info(...) host_log(__VA_ARGS__)
#define nss_warning(...) host_log(__VA_ARGS__)
#define ath11k_dbg(ab, mask, format, ...) host_log(format, ##__VA_ARGS__)
#define ath11k_warn(ab, format, ...) host_log(format, ##__VA_ARGS__)
#define ath11k_info(ab, format, ...) host_log(format, ##__VA_ARGS__)
HOST_CONSTANTS
HOST_TX_STRUCTURES
HOST_MESSAGE_ENUM
enum ath11k_hw_rev { ATH11K_HW_IPQ8074, ATH11K_HW_IPQ6018_HW10,
    ATH11K_HW_QCN9074_HW10, ATH11K_HW_IPQ5018_HW10, ATH11K_HW_QCN6122_HW10, HOST_UNSUPPORTED };
struct net_device { int unused; };
struct sk_buff;
struct napi_struct;
struct nss_wifili_msg;
typedef void (*nss_wifili_callback_t)(struct net_device *, struct sk_buff *, struct napi_struct *);
typedef nss_wifili_callback_t nss_phys_if_rx_callback_t;
typedef nss_wifili_callback_t nss_phys_if_rx_ext_data_callback_t;
typedef void (*nss_wifili_msg_callback_t)(void *, struct nss_wifili_msg *);
struct nss_subsystem_dataplane_register {
    nss_phys_if_rx_callback_t cb;
    nss_phys_if_rx_ext_data_callback_t ext_cb;
    void *app_data;
    struct net_device *ndev;
    u32 features, type;
};
struct nss_ctx_instance { int state; struct nss_subsystem_dataplane_register subsys_dp_register[256]; };
static struct { int lock, wifi_handler_id; struct nss_ctx_instance nss[1]; nss_wifili_msg_callback_t wifili_msg_callback; } nss_top_main;
static struct { int lock; struct { int ifnum; bool in_use; } state_tbl[2]; } nss_wifi_eif_info;
struct device { const int *of_node; };
struct nss_wifili_hal_srng_info { int unused; };
struct nss_wifili_init_msg {
    u32 target_type, flags, num_tcl_data_rings, num_reo_dest_rings;
    struct { u32 tlv_size, rx_buf_len; } wrip;
    struct { u32 dev_base_addr, shadow_rdptr_mem_addr, shadow_wrptr_mem_addr, lmac_rings_start_id; } hssm;
    struct nss_wifili_hal_srng_info tcl_ring_info[3], tx_comp_ring[3], reo_dest_ring[4];
    struct nss_wifili_hal_srng_info reo_reinject_ring, rx_rel_ring, reo_exception_ring;
    struct nss_wifili_tx_desc_init_msg wtdim;
    struct nss_wifili_tx_desc_addtnl_mem_msg wtdam;
    u32 tx_sw_internode_queue_size;
};
struct nss_wifili_msg { struct { int type; } cm; union { struct nss_wifili_init_msg init; } msg; };
struct ring { int ring_id; };
struct ath11k_dp { struct { struct ring tcl_data_ring, tcl_comp_ring; } tx_ring[3];
    struct ring reo_dst_ring[4], reo_reinject_ring, rx_rel_ring, reo_except_ring; };
struct ath11k_base {
    struct device *dev; struct ath11k_dp dp;
    struct { int hal_desc_sz; } hw_params;
    u32 mem_pa; int userpd_id, num_radios; enum ath11k_hw_rev hw_rev;
    struct { struct { u32 paddr; } rdp, wrp; } hal;
    struct { int if_num, response, complete; struct nss_ctx_instance *ctx; u32 tx_desc_limit;
        dma_addr_t tx_desc_paddr[ATH11K_NSS_MAX_NUMBER_OF_PAGE];
        u32 *tx_desc_vaddr[ATH11K_NSS_MAX_NUMBER_OF_PAGE];
        u32 tx_desc_size[ATH11K_NSS_MAX_NUMBER_OF_PAGE]; } nss;
};
enum fault { HEALTHY, NOT_READY, LOST_AFTER_PUBLICATION, MSG_NOMEM, SEND_REJECT, REPLY_TIMEOUT, REPLY_NACK };
static enum fault fault;
static struct ath11k_base *active;
static unsigned messages, message_live, dma_attempts, fail_at, handle_mode, invalid_dma, free_calls, count;
static unsigned checks, failures, n01_failures, n02_failures, scenarios;
static unsigned long long normal_signature;
static int property;
static bool foreign_live;
static struct net_device foreign_device;
static dma_addr_t next_dma;
static struct { void *cpu; dma_addr_t dma; size_t size; bool live; } allocations[256];
static void check_n01(bool value) { checks++; if (!value) { failures++; n01_failures++; } }
static void check_n02(bool value) { checks++; if (!value) { failures++; n02_failures++; } }
static void spin_lock_bh(int *lock)
{
    BUG_ON((*lock)++);
    if (lock == &nss_top_main.lock && fault == LOST_AFTER_PUBLICATION &&
        nss_top_main.nss[0].subsys_dp_register[active->nss.if_num].ndev)
        nss_top_main.nss[0].state = 0;
}
static void spin_unlock_bh(int *lock) { BUG_ON(--(*lock)); }
static void *kzalloc(size_t bytes, int flags)
{ (void)flags; if (fault == MSG_NOMEM) return NULL; void *p = calloc(1, bytes); if (!p) abort(); message_live++; return p; }
static void kfree(void *p) { if (p) { BUG_ON(!message_live); message_live--; free(p); } }
static void *dma_alloc_coherent(struct device *dev, size_t size, dma_addr_t *dma, int flags)
{
    (void)dev; (void)flags;
    if (++dma_attempts == fail_at) {
        if (handle_mode == 1) *dma = 0;
        if (handle_mode == 2) *dma = UINT64_MAX;
        return NULL;
    }
    BUG_ON(count >= 256);
    void *cpu = malloc(1); if (!cpu) abort();
    *dma = next_dma; next_dma += 0x40000;
    allocations[count].cpu = cpu; allocations[count].dma = *dma;
    allocations[count].size = size; allocations[count++].live = true;
    return cpu;
}
static void dma_free_coherent(struct device *dev, size_t size, void *cpu, dma_addr_t dma)
{
    (void)dev; free_calls++;
    for (unsigned i = 0; i < count; i++) {
        if (allocations[i].live && cpu && allocations[i].cpu == cpu && allocations[i].dma == dma && allocations[i].size == size) {
            allocations[i].live = false; free(cpu); return;
        }
    }
    invalid_dma++;
}
static bool of_property_read_bool(const int *node, const char *name) { (void)node; (void)name; return false; }
static int of_property_read_u32(const int *node, const char *name, u32 *value)
{ (void)node; (void)name; if (property < 0) return -EINVAL; *value = property; return 0; }
static void ath11k_nss_fill_srng_info(struct ath11k_base *ab, int ring, struct nss_wifili_hal_srng_info *info)
{ (void)ab; (void)ring; (void)info; }
static void ath11k_nss_wifili_event_receive(void *ab, struct nss_wifili_msg *msg) { (void)ab; (void)msg; }
static void ath11k_nss_wifili_ext_callback_wrapper(struct net_device *dev, struct sk_buff *skb, struct napi_struct *napi)
{ (void)dev; (void)skb; (void)napi; }
static void nss_cmn_msg_init(void *cm, int num, int type, size_t size, nss_wifili_msg_callback_t cb, void *data)
{ (void)num; (void)size; (void)cb; (void)data; ((struct nss_wifili_msg *)cm)->cm.type = type; }
static void reinit_completion(int *value) { *value = 0; }
static int msecs_to_jiffies(int value) { return value; }
static int nss_wifili_tx_msg(struct nss_ctx_instance *ctx, struct nss_wifili_msg *msg)
{
    (void)msg; messages++;
    if (ctx->state != NSS_CORE_STATE_INITIALIZED || fault == SEND_REJECT) return 1;
    if (fault == REPLY_NACK) active->nss.response = 1;
    return NSS_TX_SUCCESS;
}
static int wait_for_completion_timeout(int *value, int timeout) { (void)value; (void)timeout; return fault == REPLY_TIMEOUT ? 0 : 1; }
DRIVER_FUNCTIONS
HOST_FUNCTIONS
static unsigned live_dma(void) { unsigned n = 0; for (unsigned i = 0; i < count; i++) n += allocations[i].live; return n; }
static unsigned registrations(void) { unsigned n = 0; for (int i = 0; i < 256; i++) n += nss_top_main.nss[0].subsys_dp_register[i].ndev != NULL; return n; }
static void check_clean(struct ath11k_base *ab)
{
    check_n01(live_dma() == 0 && invalid_dma == 0);
    for (unsigned i = 0; i < ATH11K_NSS_MAX_NUMBER_OF_PAGE; i++)
        check_n01(!ab->nss.tx_desc_vaddr[i] && !ab->nss.tx_desc_paddr[i] && !ab->nss.tx_desc_size[i]);
    check_n02(registrations() == (foreign_live ? 1U : 0U) && message_live == 0);
    check_n02(nss_wifi_eif_info.state_tbl[0].in_use == foreign_live && !nss_wifi_eif_info.state_tbl[1].in_use);
    if (foreign_live)
        check_n02(nss_top_main.nss[0].subsys_dp_register[NSS_WIFILI_EXTERNAL_INTERFACE0].ndev == &foreign_device);
}
static void reset_case(struct ath11k_base *ab, int radios, enum ath11k_hw_rev hw)
{
    for (unsigned i = 0; i < count; i++) if (allocations[i].live) free(allocations[i].cpu);
    memset(allocations, 0, sizeof(allocations)); memset(ab, 0, sizeof(*ab));
    memset(&nss_top_main, 0, sizeof(nss_top_main)); memset(&nss_wifi_eif_info, 0, sizeof(nss_wifi_eif_info));
    nss_top_main.nss[0].state = NSS_CORE_STATE_INITIALIZED;
    nss_wifi_eif_info.state_tbl[0].ifnum = NSS_WIFILI_EXTERNAL_INTERFACE0;
    nss_wifi_eif_info.state_tbl[1].ifnum = NSS_WIFILI_EXTERNAL_INTERFACE1;
    static struct device dev;
    ab->dev = &dev; ab->num_radios = radios; ab->hw_rev = hw; active = ab;
    fault = HEALTHY; foreign_live = false; property = -1; messages = message_live = dma_attempts = fail_at = handle_mode = invalid_dma = free_calls = count = 0;
    next_dma = 0x10000000;
}
static void dispose_success(struct ath11k_base *ab)
{
    /* Host resource test boundary after a modeled successful firmware reset.
     * This does not test or change the production N03 teardown sequence. */
    nss_unregister_wifili_if(ab->nss.if_num);
    ath11k_nss_tx_desc_mem_free(ab);
}
static void init_cases(int radios, enum ath11k_hw_rev hw, int desc)
{
    struct ath11k_base ab;
    for (int f = HEALTHY; f <= REPLY_NACK; f++) {
        reset_case(&ab, radios, hw); property = desc; fault = f;
        if (fault == NOT_READY) nss_top_main.nss[0].state = 0;
        int ret = ath11k_nss_init(&ab);
        scenarios++;
        check_n02(ret == (fault == HEALTHY ? 0 : fault == MSG_NOMEM ? -ENOMEM : -EINVAL));
        if (fault == HEALTHY) {
            check_n02(registrations() == 1 && messages == 1 && ab.nss.ctx == &nss_top_main.nss[0]);
            normal_signature = normal_signature * 131 + ab.nss.if_num * 17 + ab.nss.tx_desc_limit * 3 + live_dma();
            dispose_success(&ab);
        }
        if (fault == NOT_READY) check_n02(count == 0 && messages == 0);
        if (fault == LOST_AFTER_PUBLICATION) check_n02(messages == 0);
        check_clean(&ab);
        /* Repeat cleanup without concealing any failed assertion in the ledger. */
        unsigned before = free_calls;
        ath11k_nss_tx_desc_mem_free(&ab);
        check_n01(before == free_calls);
    }
    /* A valid DMA handle of zero must not suppress an owned CPU allocation. */
    reset_case(&ab, radios, hw); property = desc; next_dma = 0;
    check_n02(ath11k_nss_init(&ab) == 0); dispose_success(&ab); check_clean(&ab); scenarios++;
    /* A not-ready rejection is retriable on the same object. */
    reset_case(&ab, radios, hw); property = desc; fault = NOT_READY; nss_top_main.nss[0].state = 0;
    check_n02(ath11k_nss_init(&ab) == -EINVAL);
    fault = HEALTHY; nss_top_main.nss[0].state = NSS_CORE_STATE_INITIALIZED;
    check_n02(ath11k_nss_init(&ab) == 0); dispose_success(&ab); check_clean(&ab); scenarios++;
}
static void allocation_cases(int radios, int desc)
{
    struct ath11k_base ab;
    reset_case(&ab, radios, ATH11K_HW_IPQ8074); property = desc;
    check_n02(ath11k_nss_init(&ab) == 0);
    unsigned total_pages = count;
    dispose_success(&ab);
    for (unsigned cold = 0; cold < 2; cold++) for (unsigned mode = 0; mode < 3; mode++) {
        for (unsigned index = 1; index <= total_pages; index++) {
            reset_case(&ab, radios, ATH11K_HW_IPQ8074); property = desc;
            if (!cold) { check_n02(ath11k_nss_init(&ab) == 0); dispose_success(&ab); }
            handle_mode = mode; fail_at = index; dma_attempts = 0;
            check_n02(ath11k_nss_init(&ab) == -EINVAL);
            check_clean(&ab); scenarios++;
        }
    }
    reset_case(&ab, radios, ATH11K_HW_IPQ8074);
}
static void busy_external_cases(void)
{
    for (int hw = ATH11K_HW_QCN9074_HW10; hw <= ATH11K_HW_QCN6122_HW10; hw++) {
        if (hw == ATH11K_HW_IPQ5018_HW10) continue;
        for (int f = HEALTHY; f <= LOST_AFTER_PUBLICATION; f++) {
            struct ath11k_base ab;
            reset_case(&ab, 1, hw); property = 16384; fault = f;
            foreign_live = true;
            nss_wifi_eif_info.state_tbl[0].in_use = true;
            nss_top_main.nss[0].subsys_dp_register[NSS_WIFILI_EXTERNAL_INTERFACE0].ndev = &foreign_device;
            if (fault == NOT_READY) nss_top_main.nss[0].state = 0;
            int ret = ath11k_nss_init(&ab);
            check_n02(ret == (fault == HEALTHY ? 0 : -EINVAL));
            if (!ret) {
                check_n02(ab.nss.if_num == NSS_WIFILI_EXTERNAL_INTERFACE1 && registrations() == 2);
                dispose_success(&ab);
            }
            if (fault == NOT_READY) check_n02(count == 0 && messages == 0);
            check_clean(&ab); scenarios++;
        }
    }
}
int main(void)
{
    const int desc[] = {-1, 1024, 16384, 65536, 1234};
    for (int n = 1; n <= 3; n++) for (unsigned p = 0; p < sizeof(desc)/sizeof(desc[0]); p++) {
        for (int hw = ATH11K_HW_IPQ8074; hw <= ATH11K_HW_QCN6122_HW10; hw++) init_cases(n, hw, desc[p]);
        allocation_cases(n, desc[p]);
    }
    busy_external_cases();
    struct ath11k_base ab;
    reset_case(&ab, 2, HOST_UNSUPPORTED);
    check_n02(ath11k_nss_init(&ab) == -ENOTSUPP); check_clean(&ab); scenarios++;
    printf("{\"scenarios\":%u,\"checks\":%u,\"failures\":%u,\"n01_failures\":%u,\"n02_failures\":%u,\"normal_signature\":\"%llu\"}\n",
        scenarios, checks, failures, n01_failures, n02_failures, normal_signature);
    return failures ? 1 : 0;
}
