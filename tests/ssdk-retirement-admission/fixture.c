/* Only marked SDK definitions below are production code. Providers, quiescence,
 * heap retirement and endpoint contention are serial host observations. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
/* @SDK_TYPES@ */
static const char *scenario;
static unsigned cases;
static void check(bool yes, const char *why)
{
    if (!yes) { fprintf(stderr, "RETIRE:%s\n", why); exit(86); }
}
/* @SD_CALLBACKS@ */
typedef struct { hsl_reg_func reg_func; ssdk_chip_type chip_type; } ssdk_init_cfg;
#define SW_RTN_ON_ERROR(rv) do { if ((rv) != SW_OK) return (rv); } while (0)
/* @SD_GLOBALS@ */
/* @SD_CHECK@ */
/* @SD_INIT@ */
/* @SD_HELPERS@ */
static void sd_cases(void)
{
    ssdk_init_cfg empty = {0}, full = {0};
    install_full(&full, false);
    reset_sd();
    check(sd_init(0, &empty) == SW_OK, "empty-initial"); cases++;
    check(sd_init(0, &full) == SW_OK, "publish-initial");
    check_sd(&full); cases++;
    check(sd_init(1, &full) == SW_OK, "same-provider");
    check_sd(&full); cases++;
    check(sd_init(2, &empty) == SW_OK, "null-preserves");
    check_sd(&full); cases++;
    check(sd_init(SW_MAX_NR_DEV, &full) == SW_BAD_PARAM, "invalid-device");
    check_sd(&full); cases++;
    check(sd_init(UINT32_MAX, &empty) == SW_BAD_PARAM, "invalid-device-max");
    check_sd(&full); cases++;
    check(sd_init(0, NULL) == SW_BAD_PTR, "null-config");
    check_sd(&full); cases++;
    for (unsigned field = 0; field < 12; field++) {
        ssdk_init_cfg one = {0}, other = {0};
        reset_sd();
        install_field(&one, field, false);
        check(sd_init(0, &one) == SW_OK, "single-publish");
        check_sd(&one); cases++;
        install_full(&other, true);
        /* Other NULL slots must not be filled on a late conflict. */
        check(sd_init(1, &other) == SW_BUSY, "conflict-error");
        check_sd(&one); cases++;
        install_full(&other, false);
        check(sd_init(1, &other) == SW_OK, "compatible-fill-retry");
        check_sd(&other); cases++;
    }
}

/* Root/HSL call dependencies are stateful models, not SDK lock/ABI proofs. */
typedef struct { unsigned identity; } cfg_object;
typedef struct { sw_error_t (*dev_clean)(a_uint32_t); } hsl_api_t;
typedef struct { unsigned identity; } phy_info_t;
struct phy_driver { unsigned port_bmp[SW_MAX_NR_DEV];
    void (*exit)(a_uint32_t, a_uint32_t); const void *phy_ops; };
static struct phy_driver ssdk_phy_driver[MAX_PHY_CHIP];
static unsigned borrowed_ops[MAX_PHY_CHIP];
static a_uint32_t port_bmp[SW_MAX_NR_DEV];
static phy_info_t infos[SW_MAX_NR_DEV], *phy_info[SW_MAX_NR_DEV];
static cfg_object configs[SW_MAX_NR_DEV], *dev_ssdk_cfg[SW_MAX_NR_DEV];
static hsl_api_t apis[SW_MAX_NR_DEV];
#ifdef HPPE
static bool hsl_hppe_owned[SW_MAX_NR_DEV];
static uint64_t hsl_hppe_owner_epoch[SW_MAX_NR_DEV];
#endif
static unsigned free_info[SW_MAX_NR_DEV], free_cfg[SW_MAX_NR_DEV],
    exits[SW_MAX_NR_DEV], stops, controls, emulations, clean_calls, uk_calls;
static sw_error_t child_result, endpoint_result;
static bool endpoint_live, emulated;
#define UK_IF 1
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_BAD_PTR; } while (0)
#define SSDK_ERROR(...) ((void)0)
static hsl_api_t *hsl_api_ptr_get(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "api-index"); return &apis[dev]; }
static void aos_mem_free(void *p)
{
    unsigned dev;
    for (dev = 0; dev < SW_MAX_NR_DEV; dev++) if (p == &configs[dev]) break;
    check(dev < SW_MAX_NR_DEV && !free_cfg[dev], "foreign-or-double-cfg-free");
    free_cfg[dev]++;
}
static void kfree(void *p)
{
    unsigned dev;
    for (dev = 0; dev < SW_MAX_NR_DEV; dev++) if (p == &infos[dev]) break;
    check(dev < SW_MAX_NR_DEV && !free_info[dev], "foreign-or-double-phy-free");
    free_info[dev]++;
}
static void phy_exit(unsigned dev, unsigned bitmap)
{ check(bitmap == 3 && dev < SW_MAX_NR_DEV, "phy-exit-identity"); exits[dev]++; }
static sw_error_t child_clean(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "child-device"); clean_calls++; return child_result; }
#ifdef HPPE
static sw_error_t hppe_cleanup(unsigned dev) { return child_clean(dev); }
static sw_error_t hppe_cleanup_owned(unsigned dev, uint64_t epoch)
{
    check(dev < SW_MAX_NR_DEV && epoch == dev + 1 && hsl_hppe_owned[dev], "hppe-owner-identity");
    return child_clean(dev);
}
static sw_error_t hppe_init_state_check(unsigned dev)
{
    check(dev < SW_MAX_NR_DEV, "hppe-admission-device");
    return hsl_hppe_owned[dev] ? SW_ALREADY_EXIST : SW_OK;
}
#endif
static sw_error_t sw_uk_cleanup(void)
{
    uk_calls++;
    if (endpoint_result != SW_OK) return endpoint_result;
    endpoint_live = false;
    return SW_OK;
}
static void ssdk_netdev_cache_stop(void) { stops++; }
static void ssdk_fdb_retire_controls(void) { controls++; }
static bool ssdk_is_emulation(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "emulation-device"); emulations++; return emulated; }
/* @HSL_CLEANUP@ */
static sw_error_t fal_cleanup(unsigned dev)
{
    /* Serial dependency bridge to the complete real HSL function below FAL.
     * No claim about the outer FAL guard, VLAN or adapter implementation. */
    if (dev >= SW_MAX_NR_DEV) return SW_BAD_PARAM;
    return hsl_dev_cleanup_core(dev);
}
/* @PHY_CLEANUP@ */
/* @ROOT_CLEANUP@ */
static void reset_root(void)
{
    memset(free_info, 0, sizeof(free_info)); memset(free_cfg, 0, sizeof(free_cfg));
    memset(exits, 0, sizeof(exits)); memset(ssdk_phy_driver, 0, sizeof(ssdk_phy_driver));
    stops = controls = emulations = clean_calls = uk_calls = 0;
    child_result = endpoint_result = SW_OK;
    endpoint_live = true; emulated = false;
    for (unsigned dev = 0; dev < SW_MAX_NR_DEV; dev++) {
        phy_info[dev] = &infos[dev]; dev_ssdk_cfg[dev] = &configs[dev];
        apis[dev].dev_clean = child_clean; port_bmp[dev] = 3;
#ifdef HPPE
        apis[dev].dev_clean = hppe_cleanup;
        hsl_hppe_owned[dev] = true; hsl_hppe_owner_epoch[dev] = dev + 1;
#endif
        for (unsigned type = 0; type < MAX_PHY_CHIP; type++) {
            ssdk_phy_driver[type].port_bmp[dev] = 3;
            ssdk_phy_driver[type].exit = phy_exit;
            ssdk_phy_driver[type].phy_ops = &borrowed_ops[type];
        }
    }
}
static void root_cases(void)
{
    reset_root();
    check(ssdk_cleanup(SW_MAX_NR_DEV) == SW_BAD_PARAM && !stops && !controls && !uk_calls,
        "invalid-cleanup-no-global-retirement"); cases++;
    check(ssdk_cleanup(UINT32_MAX) == SW_BAD_PARAM && !stops && !controls && !uk_calls,
        "invalid-cleanup-no-global-retirement"); cases++;
    for (unsigned dev = 0; dev < SW_MAX_NR_DEV; dev++)
        for (unsigned emu = 0; emu < 2; emu++)
            for (int error = -29; error <= 0; error++) {
                reset_root(); emulated = emu; child_result = error;
                check(ssdk_cleanup(dev) == error, "child-first-error");
                check(stops == 1 && controls == 1 && clean_calls == 1, "controls-before-child");
                if (error) {
                    check(!uk_calls && endpoint_live && !free_cfg[dev], "child-rejection-retained");
                    check(!free_info[dev] && !exits[dev] && phy_info[dev] == &infos[dev] &&
                        port_bmp[dev] == 3 && ssdk_phy_driver[0].port_bmp[dev] == 3 &&
                        !emulations, "fal-failure-retains-phy");
                    child_result = SW_OK;
                    check(ssdk_cleanup(dev) == SW_OK, "child-retry");
                }
                check(free_cfg[dev] == 1 && !endpoint_live, "successful-hsl-retirement");
                check(free_info[dev] == !emu && exits[dev] == (!emu ? MAX_PHY_CHIP : 0),
                    "phy-success-predicate");
                for (unsigned peer = 0; peer < SW_MAX_NR_DEV; peer++) if (peer != dev)
                    check(!free_cfg[peer] && !free_info[peer] && !exits[peer] &&
                        phy_info[peer] == &infos[peer] && port_bmp[peer] == 3,
                        "peer-metadata-preserved");
                for (unsigned type = 0; type < MAX_PHY_CHIP; type++) {
                    check(ssdk_phy_driver[type].phy_ops == &borrowed_ops[type], "borrowed-ops-preserved");
                    for (unsigned peer = 0; peer < SW_MAX_NR_DEV; peer++)
                        check(ssdk_phy_driver[type].port_bmp[peer] == ((peer == dev && !emu) ? 0 : 3),
                            "all-type-peer-bitmaps");
                }
                cases++;
            }
    for (unsigned dev = 0; dev < SW_MAX_NR_DEV; dev++) {
        reset_root(); endpoint_result = SW_BUSY;
        check(ssdk_cleanup(dev) == SW_BUSY, "uk-busy-error");
        check(free_cfg[dev] == 1 && !dev_ssdk_cfg[dev] && endpoint_live,
            "known-hsl-before-uk-order-not-repaired");
        check(!free_info[dev] && !exits[dev] && phy_info[dev] == &infos[dev],
            "uk-refusal-retains-phy");
        endpoint_result = SW_OK;
        check(ssdk_cleanup(dev) == SW_OK && free_info[dev] == 1 && exits[dev] == MAX_PHY_CHIP &&
            clean_calls == 1 && uk_calls == 2, "uk-retry-no-double-retirement"); cases++;
    }
}

enum { HSL_DEV_IDLE = 0 };
static struct { unsigned phase; } hsl_dev_guards[SW_MAX_NR_DEV];
#define HSL_DEV_ID_CHECK(dev) do { if ((dev) >= SW_MAX_NR_DEV) return SW_BAD_PARAM; } while (0)
static unsigned fal_init_calls, fal_mutations, phy_init_calls;
static sw_error_t hsl_port_prop_slot_available(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "port-table-device"); return SW_OK; }
static void *adpt_api_ptr_get(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "adapter-device"); return NULL; }
/* @HSL_HPPE_REQUEST@ */
/* @HSL_INIT_AVAILABLE@ */
static sw_error_t fal_init(unsigned dev, ssdk_init_cfg *cfg)
{
    sw_error_t rv;
    fal_init_calls++;
    rv = hsl_dev_init_available(dev, cfg);
    if (rv != SW_OK) return rv;
    fal_mutations++;
    return sd_init(dev, cfg);
}
static int ssdk_phy_driver_init(unsigned dev)
{ check(dev < SW_MAX_NR_DEV, "phy-init-device"); phy_init_calls++; return SW_OK; }
/* @ROOT_INIT@ */
static void init_cases(void)
{
    for (unsigned field = 0; field < 12; field++) {
        ssdk_init_cfg one = {0}, other = {0};
        reset_root(); reset_sd();
        for (unsigned dev = 0; dev < SW_MAX_NR_DEV; dev++) {
            dev_ssdk_cfg[dev] = NULL; apis[dev].dev_clean = NULL;
#ifdef HPPE
            hsl_hppe_owned[dev] = false; hsl_hppe_owner_epoch[dev] = 0;
#endif
        }
        fal_init_calls = fal_mutations = phy_init_calls = 0;
        install_field(&one, field, false); install_full(&other, true);
        check(sd_init(0, &one) == SW_OK, "init-baseline-publish");
        check(ssdk_init(0, &other) == SW_BUSY && !fal_init_calls && !fal_mutations && !phy_init_calls,
            "root-conflict-before-fal-and-phy");
        check_sd(&one); cases++;
        check(hsl_dev_init_available(1, &other) == SW_BUSY, "hsl-conflict-before-api-reset");
        check_sd(&one); cases++;
        install_full(&other, false);
        check(ssdk_init(0, &other) == SW_OK && fal_init_calls == 1 && fal_mutations == 1 && phy_init_calls == 1,
            "compatible-init-retry");
        check_sd(&other); cases++;
    }
    fal_init_calls = fal_mutations = phy_init_calls = 0;
    check(ssdk_init(0, NULL) == SW_BAD_PTR && !fal_init_calls && !phy_init_calls, "root-null-admission"); cases++;
    check(ssdk_init(SW_MAX_NR_DEV, NULL) == SW_BAD_PARAM && !fal_init_calls && !phy_init_calls,
        "root-device-admission"); cases++;
}
int main(int argc, char **argv)
{
    scenario = "retirement"; (void)scenario;
    if (argc == 2 && !strcmp(argv[1], "conflict")) {
        ssdk_init_cfg one = {0}, other = {0};
        reset_sd(); install_field(&one, 11, false); install_full(&other, true);
        check(sd_init(0, &one) == SW_OK, "single-publish");
        check(sd_init(1, &other) == SW_BUSY, "conflict-error");
        check_sd(&one);
        puts("conflict-rejected-without-publication");
        return 0;
    }
    check(argc == 1, "arguments");
    sd_cases(); root_cases(); init_cases();
    printf("{\"status\":\"PASS\",\"cases\":%u,\"shared_uk_order\":\"OPEN\"}\n", cases);
    return 0;
}
