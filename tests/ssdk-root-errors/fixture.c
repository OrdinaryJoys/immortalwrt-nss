/* A2 native leaf/structure model, not Linux/SSDK target ABI or safe cleanup proof. */
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t a_uint32_t;
/* @ACTUAL_ERROR_ENUM@ */
struct qca_phy_priv { bool qca_ssdk_sw_dev_registered; };
static struct qca_phy_priv slots[4];
static struct qca_phy_priv *slot_ptrs[4];
static struct qca_phy_priv **qca_phy_priv_global = slot_ptrs;
#define A_TRUE true
#define __exit
#define SSDK_STR "ssdk"

static unsigned device_count, emulation_mask;
static sw_error_t fal_results[4], phy_results[4];
static char events[128][256];
static unsigned event_count;

static _Noreturn void fail(const char *marker)
{
    fprintf(stderr, "SSDK_A2 %s\n", marker);
    exit(86);
}
static void require(bool ok, const char *marker)
{
    if (!ok)
        fail(marker);
}
static void event(const char *format, ...) __attribute__((format(printf, 1, 2)));
static void event(const char *format, ...)
{
    require(event_count < 128, "event-capacity");
    va_list args;
    va_start(args, format);
    int length = vsnprintf(events[event_count], sizeof(events[0]), format, args);
    va_end(args);
    require(length > 0 && (size_t)length < sizeof(events[0]), "event-length");
    ++event_count;
}
static void action(const char *name, int device)
{
    event("A %s %d\n", name, device);
}
static void device_action(const char *name, a_uint32_t device)
{
    require(device < device_count, "leaf-device-argument");
    action(name, (int)device);
}
static void model_log(char severity, const char *format, ...) __attribute__((format(printf, 2, 3)));
static void model_log(char severity, const char *format, ...)
{
    char text[220];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    require(length > 0 && (size_t)length < sizeof(text) && text[length - 1] == '\n',
            "log-format");
    event("L %c %s", severity, text);
}
#define SSDK_ERROR(...) model_log('E', __VA_ARGS__)
#define SSDK_INFO(...) model_log('I', __VA_ARGS__)
static void ssdk_netdev_cache_stop(void) { action("cache-stop", -1); }
static void ssdk_fdb_retire_controls(void) { action("retire-controls", -1); }
static sw_error_t fal_cleanup(a_uint32_t device)
{
    device_action("fal", device);
    return fal_results[device];
}
static bool ssdk_is_emulation(a_uint32_t device)
{
    device_action("emulation", device);
    return (emulation_mask & (1u << device)) != 0;
}
static sw_error_t ssdk_phy_driver_cleanup(a_uint32_t device)
{
    device_action("phy", device);
    return phy_results[device];
}
static void ssdk_netdev_notifier_unregister(void) { action("notifier-unregister", -1); }
static a_uint32_t ssdk_switch_device_num_get(void)
{
    action("device-count", -1);
    return device_count;
}
static void ssdk_driver_unregister(a_uint32_t device) { device_action("driver-unregister", device); }
static void ssdk_switch_unregister(a_uint32_t device) { device_action("switch-unregister", device); }
static void sfp_phy_exit(a_uint32_t device) { device_action("sfp-exit", device); }
static void ssdk_plat_exit(a_uint32_t device) { device_action("platform-exit", device); }
static void ssdk_free_priv(void) { action("free-priv", -1); }

/* @ACTUAL_FUNCTIONS@ */

static const char *mismatch(const char *expected, const char *actual)
{
    if (strncmp(expected, "L E ssdk FAL ", 13) == 0)
        return "fal-error-log";
    if (strncmp(expected, "L E ssdk PHY ", 13) == 0)
        return "phy-error-log";
    if (strncmp(expected, "L E qca-ssdk device ", 20) == 0)
        return "device-error-log";
    if (strstr(expected, "module exit") != NULL || strstr(actual, "module exit") != NULL)
        return "module-first-error-log";
    if (expected[0] == 'L' || actual[0] == 'L')
        return "unexpected-log";
    return "action-order-or-gate";
}
static void results_arg(const char *input, sw_error_t *values)
{
    const char *cursor = input;
    for (unsigned i = 0; i < device_count; ++i) {
        char *end;
        long value = strtol(cursor, &end, 10);
        require(end != cursor && value <= SW_OK && value >= SW_ABORTED, "error-domain");
        values[i] = (sw_error_t)value;
        if (i + 1 < device_count) {
            require(*end == ',', "error-input");
            cursor = end + 1;
        } else {
            require(*end == '\0', "error-input");
        }
    }
    if (!device_count)
        require(strcmp(input, "-") == 0, "zero-device-input");
}
int main(int argc, char **argv)
{
    require(argc == 8, "arguments");
    bool module = strcmp(argv[1], "exit") == 0;
    require(module || strcmp(argv[1], "cleanup") == 0, "flow");
    device_count = (unsigned)strtoul(argv[2], NULL, 10);
    unsigned registered = (unsigned)strtoul(argv[3], NULL, 10);
    emulation_mask = (unsigned)strtoul(argv[4], NULL, 10);
    require(device_count <= 4 && (module || device_count == 1), "native-model-domain");
    for (unsigned i = 0; i < device_count; ++i) {
        slots[i].qca_ssdk_sw_dev_registered = (registered & (1u << i)) != 0;
        qca_phy_priv_global[i] = &slots[i];
    }
    results_arg(argv[5], fal_results);
    results_arg(argv[6], phy_results);
    sw_error_t result = SW_OK;
    if (module)
        regi_exit();
    else
        result = ssdk_cleanup(0);
    FILE *oracle = fopen(argv[7], "r");
    require(oracle != NULL, "oracle-open");
    char wanted[256], actual[256];
    if (module)
        strcpy(actual, "RESULT void\n");
    else
        snprintf(actual, sizeof(actual), "RESULT %d\n", (int)result);
    require(fgets(wanted, sizeof(wanted), oracle) != NULL && strcmp(wanted, actual) == 0,
            "cleanup-first-error");
    for (unsigned i = 0; i < event_count; ++i) {
        require(fgets(wanted, sizeof(wanted), oracle) != NULL, "extra-action-or-log");
        if (strcmp(wanted, events[i]) != 0)
            fail(mismatch(wanted, events[i]));
    }
    if (fgets(wanted, sizeof(wanted), oracle) != NULL) {
        if (wanted[0] == 'L')
            fail(mismatch(wanted, ""));
        fail("missing-action-or-log");
    }
    require(!ferror(oracle), "oracle-read");
    require(fclose(oracle) == 0, "oracle-close");
    fputs(actual, stdout);
    for (unsigned i = 0; i < event_count; ++i)
        fputs(events[i], stdout);
    return 0;
}
