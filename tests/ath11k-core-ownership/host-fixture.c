#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ATH11K_FLAG_REGISTERED 0
#define ATH11K_FLAG_CRASH_FLUSH 1
#define ATH11K_FLAG_HW_CRYPTO_DISABLED 2
#define ATH11K_FLAG_RAW_MODE 3
#define ATH11K_CRYPT_MODE_SW 0
#define ATH11K_CRYPT_MODE_HW 1
#define ATH11K_HW_TXRX_RAW 1
#define WMI_HOST_HW_MODE_DBS 1
#define ath11k_err(...) ((void)0)
#define ath11k_info(...) ((void)0)
enum stage { NONE, FIRMWARE, CE, DP, WMI, HTC_INIT, HIF, HTC_WAIT, HTT,
    WMI_CONNECT, HTC_START, SERVICE, MAC_ALLOC, REO, WMI_INIT, UNIFIED, DBS,
    VERSION, DEBUGFS, DP_PDEV, NSS, MAC_REGISTER, THERMAL, SPECTRAL, END };
enum resource { R_DP, R_WMI, R_HIF, R_MAC, R_REO, R_PDEV, R_NSS, R_REG,
    R_THERMAL, R_SPECTRAL, RESOURCES };
struct ath11k_base {
    unsigned long dev_flags;
    int core_lock, htc, dp, fw_mode;
    struct { bool single_pdev_only; int num_rxdma_per_pdev; } hw_params;
    bool nss_enabled;
};
static unsigned checks, failures, scenarios, api_errors;
static unsigned held, borrowed, triggered;
static unsigned long long trace, normal_signature;
static enum stage failure_stage;
static int ath11k_crypto_mode, ath11k_frame_mode;
static bool firmware;
static bool test_bit(unsigned bit, const unsigned long *flags) { return (*flags >> bit) & 1; }
static void set_bit(unsigned bit, unsigned long *flags) { *flags |= 1UL << bit; }
static void clear_bit(unsigned bit, unsigned long *flags) { *flags &= ~(1UL << bit); }
static void event(unsigned value) { trace = trace * 131 + value; }
static void check(bool condition) { checks++; if (!condition) failures++; }
static int step(enum stage stage)
{
    event(100 + stage);
    if (stage != failure_stage) return 0;
    triggered++;
    return -EIO;
}
static void acquire(enum resource resource)
{
    unsigned bit = 1U << resource;
    if (held & bit) api_errors++;
    held |= bit;
    event(200 + resource);
}
static void release(enum resource resource)
{
    unsigned bit = 1U << resource;
    if (!(held & bit) || (borrowed & bit)) api_errors++;
    held &= ~bit;
    event(300 + resource);
}
static int acquire_at(enum stage stage, enum resource resource)
{
    int ret = step(stage);
    if (!ret) acquire(resource);
    return ret;
}
static void mutex_lock(int *lock) { if ((*lock)++) api_errors++; }
static void mutex_unlock(int *lock) { if (--(*lock)) api_errors++; }
static int ath11k_core_start_firmware(struct ath11k_base *ab, int mode)
{
    (void)ab; (void)mode;
    int ret = step(FIRMWARE);
    if (!ret) firmware = true;
    return ret;
}
static void ath11k_qmi_firmware_stop(struct ath11k_base *ab) { (void)ab; firmware = false; event(400); }
static int ath11k_ce_init_pipes(struct ath11k_base *ab) { (void)ab; return step(CE); }
static int ath11k_dp_alloc(struct ath11k_base *ab) { (void)ab; return acquire_at(DP, R_DP); }
static void ath11k_dp_free(struct ath11k_base *ab) { (void)ab; release(R_DP); }
static int ath11k_wmi_attach(struct ath11k_base *ab) { (void)ab; return acquire_at(WMI, R_WMI); }
static void ath11k_wmi_detach(struct ath11k_base *ab) { (void)ab; release(R_WMI); }
static int ath11k_htc_init(struct ath11k_base *ab) { (void)ab; return step(HTC_INIT); }
static int ath11k_hif_start(struct ath11k_base *ab) { (void)ab; return acquire_at(HIF, R_HIF); }
static void ath11k_hif_stop(struct ath11k_base *ab) { (void)ab; release(R_HIF); }
static void ath11k_hif_irq_enable(struct ath11k_base *ab) { (void)ab; event(401); }
static int ath11k_htc_wait_target(int *htc) { (void)htc; return step(HTC_WAIT); }
static int ath11k_dp_htt_connect(int *dp) { (void)dp; return step(HTT); }
static int ath11k_wmi_connect(struct ath11k_base *ab) { (void)ab; return step(WMI_CONNECT); }
static int ath11k_htc_start(int *htc) { (void)htc; return step(HTC_START); }
static int ath11k_wmi_wait_for_service_ready(struct ath11k_base *ab) { (void)ab; return step(SERVICE); }
static int ath11k_mac_allocate(struct ath11k_base *ab)
{
    if (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags)) return 0;
    return acquire_at(MAC_ALLOC, R_MAC);
}
static void ath11k_mac_destroy(struct ath11k_base *ab) { (void)ab; release(R_MAC); }
static void ath11k_dp_pdev_pre_alloc(struct ath11k_base *ab) { (void)ab; event(402); }
static int ath11k_dp_pdev_reo_setup(struct ath11k_base *ab) { (void)ab; return acquire_at(REO, R_REO); }
static void ath11k_dp_pdev_reo_cleanup(struct ath11k_base *ab) { (void)ab; release(R_REO); }
static int ath11k_wmi_cmd_init(struct ath11k_base *ab) { (void)ab; return step(WMI_INIT); }
static int ath11k_wmi_wait_for_unified_ready(struct ath11k_base *ab) { (void)ab; return step(UNIFIED); }
static int ath11k_wmi_set_hw_mode(struct ath11k_base *ab, int mode) { (void)ab; (void)mode; return step(DBS); }
static int ath11k_dp_tx_htt_h2t_ver_req_msg(struct ath11k_base *ab) { (void)ab; return step(VERSION); }
static int ath11k_debugfs_pdev_create(struct ath11k_base *ab)
{
    if (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags)) return 0;
    return step(DEBUGFS);
}
static void ath11k_debugfs_pdev_destroy(struct ath11k_base *ab) { (void)ab; }
static int ath11k_dp_pdev_alloc(struct ath11k_base *ab) { (void)ab; return acquire_at(DP_PDEV, R_PDEV); }
static void ath11k_dp_pdev_free(struct ath11k_base *ab) { (void)ab; release(R_PDEV); }
static int ath11k_nss_setup(struct ath11k_base *ab)
{
    return ab->nss_enabled ? acquire_at(NSS, R_NSS) : 0;
}
static void ath11k_nss_teardown(struct ath11k_base *ab) { if (ab->nss_enabled) release(R_NSS); }
static int ath11k_mac_register(struct ath11k_base *ab)
{
    if (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags)) return 0;
    return acquire_at(MAC_REGISTER, R_REG);
}
static void ath11k_mac_unregister(struct ath11k_base *ab) { (void)ab; release(R_REG); }
static int ath11k_thermal_register(struct ath11k_base *ab)
{
    if (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags)) return 0;
    return acquire_at(THERMAL, R_THERMAL);
}
static void ath11k_thermal_unregister(struct ath11k_base *ab) { (void)ab; release(R_THERMAL); }
static int ath11k_spectral_init(struct ath11k_base *ab) { (void)ab; return acquire_at(SPECTRAL, R_SPECTRAL); }
HOST_FUNCTIONS
static void dispose_success(struct ath11k_base *ab)
{
    release(R_SPECTRAL);
    if (!borrowed) { release(R_THERMAL); release(R_REG); }
    ath11k_nss_teardown(ab);
    ath11k_dp_pdev_free(ab);
    ath11k_core_stop(ab);
    if (!borrowed) ath11k_mac_destroy(ab);
    ath11k_dp_free(ab);
}
static void run_case(bool registered, bool dbs, bool nss, int crypto, bool raw, enum stage stage)
{
    struct ath11k_base ab = { .dev_flags = registered ? 1UL : 0UL,
        .hw_params = {dbs, dbs ? 2 : 1}, .nss_enabled = nss };
    held = borrowed = registered ? (1U << R_MAC) | (1U << R_REG) : 0;
    api_errors = triggered = 0;
    trace = 0;
    firmware = false;
    ath11k_crypto_mode = crypto;
    ath11k_frame_mode = raw ? ATH11K_HW_TXRX_RAW : 0;
    failure_stage = stage;
    int ret = ath11k_core_qmi_firmware_ready(&ab);
    scenarios++;
    check(ret == (triggered ? -EIO : 0));
    check(ab.core_lock == 0);
    check(test_bit(ATH11K_FLAG_REGISTERED, &ab.dev_flags) == registered);
    if (ret) {
        check(held == borrowed);
        check(!firmware);
    } else {
        unsigned expected = ((1U << RESOURCES) - 1) & ~(nss ? 0 : 1U << R_NSS);
        if (registered) expected &= ~(1U << R_THERMAL);
        check(held == expected);
        check(firmware);
        if (stage == NONE) normal_signature = normal_signature * 131 + trace;
        dispose_success(&ab);
        check(held == borrowed);
    }
    check(api_errors == 0);
    /* Retry only after a clean rollback. Do not conceal a failure by resetting the ledger. */
    if (ret && held == borrowed && !api_errors) {
        failure_stage = NONE;
        triggered = 0;
        ret = ath11k_core_qmi_firmware_ready(&ab);
        check(ret == 0);
        dispose_success(&ab);
        check(held == borrowed && api_errors == 0 && ab.core_lock == 0);
    }
}
int main(void)
{
    for (int registered = 0; registered < 2; registered++)
        for (int dbs = 0; dbs < 2; dbs++)
            for (int nss = 0; nss < 2; nss++)
                for (int crypto = 0; crypto < 2; crypto++)
                    for (int raw = 0; raw < 2; raw++)
                        for (int stage = NONE; stage < END; stage++)
                            run_case(registered, dbs, nss, crypto, raw, stage);
    printf("{\"scenarios\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%llu\"}\n",
           scenarios, checks, failures, normal_signature);
    return failures ? 1 : 0;
}
