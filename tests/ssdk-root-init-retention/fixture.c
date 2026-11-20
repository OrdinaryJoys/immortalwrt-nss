/* 42-layer actual root init (patched) in a bounded serial host model.
 *
 * The complete actual regi_init() and every function 054 adds or edits are
 * extracted without body modification from the prepared 42-patch d9a19649
 * tree (tests/ssdk-root-init-retention/source.py). This file supplies only
 * explicit stubs/models: SDK leaf calls, work/mutex primitives, producer stop
 * contracts and the Linux target errno constants. It is not target ABI,
 * thread/concurrency, RCU/lockdep, real kernel workqueue or module-unload
 * proof.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdbool.h>

#include "sdk.h"

/* Linux target errno constants. The host shim must not borrow host libc
 * values: the mapping under test is the kernel ABI the module returns. */
#define EPERM 1
#define EIO 5
#define ENOMEM 12
#define EBUSY 16
#define EEXIST 17
#define ENODEV 19
#define EINVAL 22
#define EOPNOTSUPP 95

#define __init
#define __exit

#define CONFIG_OF 1
#define LINUX_VERSION_CODE 397862 /* 6.18.38 */
#define KERNEL_VERSION(a, b, c) (((a) << 16) + ((b) << 8) + (c))

#define SSDK_PHYSICAL_PORT1 1
#define SSDK_PHYSICAL_PORT3 3
#define SSDK_PHYSICAL_PORT4 4
#define SSDK_PHYSICAL_PORT6 6
#define SSDK_PHYSICAL_PORT7 7
#define SW_MAX_NR_PORT 8
#define SSDK_MIB_CHANGE_WQ
#define SSDK_QM_CHANGE_WQ
#define PPE_STR "HPPE"

struct device_node { unsigned sentinel; };
struct mutex { unsigned sentinel; };
struct work_struct { int initialized; };
struct delayed_work { struct work_struct work; int initialized; };
struct workqueue_struct { unsigned sentinel; };
struct platform_driver { unsigned sentinel; };
struct notifier_block {
	int (*notifier_call)(struct notifier_block *, unsigned long, void *);
	int priority;
};
struct qca_phy_priv {
	a_uint32_t device_id;
	a_uint32_t version;
	a_bool_t polling_once;
	a_uint32_t ports;
	struct device_node *of_node;
	struct delayed_work qm_dwork_polling;
	struct delayed_work mac_sw_sync_dwork;
	struct mutex mac_sw_sync_lock;
	struct mutex qm_lock;
	a_bool_t qca_ssdk_sw_dev_registered;
};
typedef struct {
	int chip_type;
	int chip_revision;
	int phy_id;
} ssdk_init_cfg;

/* qca_phy_priv_global is the prepared module-level pointer table. */
struct qca_phy_priv **qca_phy_priv_global;

struct notifier_block ssdk_dev_notifier;
static bool ssdk_dev_notifier_owned;
static int ssdk_dev_notifier_error;

struct platform_driver ssdk_driver;
static struct workqueue_struct wq_singleton;
#define system_long_wq (&wq_singleton)
#define msecs_to_jiffies(value) (value)
#define mutex_init(mutex) do { (void)(mutex); } while (0)
#define INIT_DELAYED_WORK(dwork, func) \
	do { \
		(void)(func); \
		(dwork)->initialized = 1; \
		(dwork)->work.initialized = 1; \
	} while (0)
#define INIT_WORK(dwork, func) INIT_DELAYED_WORK(dwork, func)

static void qm_err_check_work_task_polling(struct work_struct *work);
static void qca_mac_sw_sync_work_task(struct work_struct *work);

/* ----------------------------------------------------------------------- */
#include "cases.h"

static const struct input *cur;
static unsigned ndev;
static struct qca_phy_priv priv_slots[SW_MAX_NR_DEV];
static struct qca_phy_priv *priv_ptrs[SW_MAX_NR_DEV];
static struct device_node node_singleton;
static char trace[131072];
static size_t used;

static unsigned entered_plat[SW_MAX_NR_DEV];
static unsigned plat_exited[SW_MAX_NR_DEV];
static unsigned phy_cleaned[SW_MAX_NR_DEV];
static unsigned local_bus_mode[SW_MAX_NR_DEV];
static unsigned driver_registered;
static unsigned driver_register_ok;
static unsigned driver_register_calls;
static unsigned driver_unregister_calls;
static unsigned notifier_calls;
static unsigned notifier_registered;
static unsigned cache_start_calls;
static unsigned cache_commit_calls;
static unsigned cache_stop_calls;
static unsigned sysfs_calls;
static unsigned genl_calls;
static unsigned genl_deinit_calls;
static unsigned free_calls;
static unsigned freed;
static unsigned topology_init_calls;
static unsigned topology_exit_calls;
static unsigned alloc_calls;
static unsigned phy_cleanup_calls;
static unsigned plat_exit_calls;
static unsigned cancel_mac;
static unsigned cancel_qm;
static unsigned sd_calls;
static unsigned fal_failed;
static unsigned phy_calls;
static unsigned hppe_called;
static unsigned hppe_failed;
static unsigned switch_calls;
static unsigned switch_ok;

static unsigned notifier_unregister_calls;
static unsigned fdb_controls_calls;
static unsigned switch_unregister_calls;
static unsigned switch_unregistered[SW_MAX_NR_DEV];
static unsigned cleanup_calls;
static unsigned cleanup_failed;
static unsigned unload_partial;

static unsigned log_sysfs_degraded;
static unsigned log_genl_degraded;
static unsigned log_notifier_contract;
static unsigned log_zero_dev;
static unsigned log_no_device;
static unsigned log_retained;
static unsigned log_aborted;
static unsigned log_succeeded;
static unsigned log_cache_degraded;

int root_first_err_snapshot(void);

static _Noreturn void fail(const char *marker)
{
	fprintf(stderr, "ROOT_ASSERT:%s\n", marker);
	exit(86);
}

#define CHECK(condition, marker) \
	do { if (!(condition)) fail(marker); } while (0)

static void emit(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void emit(const char *fmt, ...)
{
	va_list ap;
	int length;

	va_start(ap, fmt);
	length = vsnprintf(trace + used, sizeof(trace) - used, fmt, ap);
	va_end(ap);
	CHECK(length >= 0 && (size_t)length < sizeof(trace) - used, "TRACE_CAPACITY");
	used += (size_t)length;
}

static void model_log(const char *level, const char *fmt, ...)
	__attribute__((format(printf, 2, 3)));
static void model_log(const char *level, const char *fmt, ...)
{
	char line[512];
	va_list ap;
	int length;

	va_start(ap, fmt);
	length = vsnprintf(line, sizeof(line), fmt, ap);
	va_end(ap);
	CHECK(length >= 0 && (size_t)length < sizeof(line), "LOG_CAPACITY");
	if (strstr(line, "sysfs diagnostic plane degraded"))
		log_sysfs_degraded = 1;
	if (strstr(line, "genl diagnostic plane degraded"))
		log_genl_degraded = 1;
	if (strstr(line, "netdev cache contract violation"))
		log_notifier_contract = 1;
	if (strstr(line, "no admitted switch device"))
		log_zero_dev = 1;
	if (strstr(line, "no device found!"))
		log_no_device = 1;
	if (strstr(line, "module init retained in stage"))
		log_retained = 1;
	if (strstr(line, "module init aborted in stage"))
		log_aborted = 1;
	if (strstr(line, "module init succeeded!"))
		log_succeeded = 1;
	if (strstr(line, "netdev cache not live"))
		log_cache_degraded = 1;
	emit("%s %s", level, line);
}

#define SSDK_INFO(...) model_log("INFO", __VA_ARGS__)
#define SSDK_ERROR(...) model_log("ERROR", __VA_ARGS__)
#define SSDK_DEBUG(...) model_log("DEBUG", __VA_ARGS__)

static unsigned any_phy_cleanup(void)
{
	unsigned dev_id;

	for (dev_id = 0; dev_id < SW_MAX_NR_DEV; dev_id++)
		if (phy_cleaned[dev_id])
			return 1;
	return 0;
}

static unsigned any_plat_exit(void)
{
	unsigned dev_id;

	for (dev_id = 0; dev_id < SW_MAX_NR_DEV; dev_id++)
		if (plat_exited[dev_id])
			return 1;
	return 0;
}

static unsigned all_phy_cleaned(void)
{
	unsigned dev_id;

	for (dev_id = 0; dev_id < ndev; dev_id++)
		if (!phy_cleaned[dev_id])
			return 0;
	return 1;
}

static unsigned entered_plat_count(void)
{
	unsigned dev_id, count = 0;

	for (dev_id = 0; dev_id < SW_MAX_NR_DEV; dev_id++)
		if (entered_plat[dev_id])
			++count;
	return count;
}

/* ---------------------------------------------------------------- stubs -- */

/* Work/mutex primitives are no-ops except for the initialized witnesses the
 * stop functions must consult. */
static void cancel_delayed_work_sync(struct delayed_work *dwork)
{
	unsigned dev_id;

	for (dev_id = 0; dev_id < SW_MAX_NR_DEV; dev_id++) {
		if (dwork == &priv_slots[dev_id].qm_dwork_polling) {
			if (!dwork->initialized)
				fail("QM_STOP_UNSTARTED");
			++cancel_qm;
			return;
		}
		if (dwork == &priv_slots[dev_id].mac_sw_sync_dwork) {
			if (!dwork->initialized)
				fail("MAC_STOP_UNSTARTED");
			++cancel_mac;
			return;
		}
	}
	fail("CANCEL_UNKNOWN");
}

static int queue_delayed_work_on(int cpu, struct workqueue_struct *queue,
				 struct delayed_work *dwork, unsigned long delay)
{
	(void)cpu;
	(void)queue;
	(void)dwork;
	(void)delay;
	return 1;
}

static void qm_err_check_work_task_polling(struct work_struct *work)
{
	(void)work;
	fail("WORK_RAN_IN_HOST_MODEL");
}

static void qca_mac_sw_sync_work_task(struct work_struct *work)
{
	(void)work;
	fail("WORK_RAN_IN_HOST_MODEL");
}

static struct qca_phy_priv *ssdk_phy_priv_data_get(a_uint32_t dev_id)
{
	if (dev_id >= SW_MAX_NR_DEV)
		return NULL;
	return qca_phy_priv_global[dev_id];
}

static a_bool_t ssdk_is_emulation(a_uint32_t dev_id)
{
	(void)dev_id;
	return A_FALSE;
}

/* Topology. */
static int ssdk_switch_device_num_init(void)
{
	CHECK(!topology_init_calls, "TOPO_ONCE");
	++topology_init_calls;
	emit("TOPO_INIT %d\n", cur->topology_rv);
	return cur->topology_rv;
}

static void ssdk_switch_device_num_exit(void)
{
	++topology_exit_calls;
	emit("TOPO_EXIT\n");
}

static a_uint32_t ssdk_switch_device_num_get(void)
{
	return ndev;
}

static int ssdk_alloc_priv(a_uint32_t dev_num)
{
	++alloc_calls;
	emit("ALLOC_PRIV %u %d\n", dev_num, cur->alloc_rv);
	return cur->alloc_rv;
}

static void ssdk_cfg_default_init(ssdk_init_cfg *cfg)
{
	cfg->chip_type = CHIP_UNSPECIFIED;
	cfg->chip_revision = 0;
	cfg->phy_id = 0;
}

static sw_error_t ssdk_dt_parse(ssdk_init_cfg *cfg, a_uint32_t num,
				a_uint32_t *dev_id)
{
	(void)cfg;
	if (cur->dt_disabled & (1u << num)) {
		emit("DT_PARSE %u disabled\n", num);
		return SW_DISABLE;
	}
	*dev_id = num;
	emit("DT_PARSE %u enabled\n", num);
	return SW_OK;
}

static a_uint32_t ssdk_device_id_get(a_uint32_t dev_id)
{
	return dev_id;
}

static struct device_node *ssdk_dts_node_get(a_uint32_t dev_id)
{
	(void)dev_id;
	return &node_singleton;
}

static hsl_reg_mode ssdk_switch_reg_access_mode_get(a_uint32_t dev_id)
{
	if (dev_id >= SW_MAX_NR_DEV)
		return HSL_REG_MDIO;
	return local_bus_mode[dev_id] ? HSL_REG_LOCAL_BUS : HSL_REG_MDIO;
}

/* Platform stage. */
static int ssdk_plat_init(ssdk_init_cfg *cfg, a_uint32_t dev_id)
{
	int rv;

	(void)cfg;
	CHECK(dev_id < ndev, "PLAT_DEVICE");
	CHECK(!entered_plat[dev_id], "PLAT_TWICE");
	entered_plat[dev_id] = 1;
	local_bus_mode[dev_id] = (cur->local_bus >> dev_id) & 1u;
	rv = cur->plat_rv[dev_id];
	emit("PLAT_INIT %u %d\n", dev_id, rv);
	return rv;
}

static void ssdk_plat_exit(a_uint32_t dev_id)
{
	CHECK(!freed, "PLAT_EXIT_AFTER_FREE");
	if (unload_partial)
		CHECK(cleanup_calls > dev_id, "PLAT_BEFORE_CLEANUP");
	else
		CHECK(all_phy_cleaned(), "ABORT_ORDER_PHY_AFTER_PLAT");
	CHECK(dev_id < ndev && entered_plat[dev_id], "PLAT_EXIT_UNENTERED");
	CHECK(!plat_exited[dev_id], "PLAT_EXIT_TWICE");
	plat_exited[dev_id] = 1;
	++plat_exit_calls;
	emit("PLAT_EXIT %u\n", dev_id);
}

static sw_error_t ssdk_phy_driver_cleanup(a_uint32_t dev_id)
{
	CHECK(!freed, "PHY_CLEANUP_AFTER_FREE");
	CHECK(!any_plat_exit(), "ABORT_ORDER_PHY_AFTER_PLAT");
	CHECK(dev_id < ndev, "PHY_CLEANUP_DEVICE");
	CHECK(!phy_cleaned[dev_id], "PHY_CLEANUP_TWICE");
	phy_cleaned[dev_id] = 1;
	++phy_cleanup_calls;
	emit("PHY_CLEANUP %u\n", dev_id);
	return SW_OK;
}

static void ssdk_free_priv(void)
{
	unsigned dev_id;

	if (cur->expect_outcome == OUT_RETAIN)
		fail("RETAIN_FREED");
	/* A free in any other non-abort scenario is judged by the outcome checks,
	 * not here, so the first violated expectation is reported. */
	if (cur->expect_outcome != OUT_ABORT && cur->expect_outcome != OUT_UNLOAD)
		return;
	CHECK(!freed, "FREE_TWICE");
	CHECK(!driver_registered, "NULL_DRIVER_AFTER_FREE");
	CHECK(unload_partial || all_phy_cleaned(), "ABORT_PHY_LEAKED");
	for (dev_id = 0; dev_id < ndev; dev_id++)
		CHECK(!entered_plat[dev_id] || plat_exited[dev_id],
		      "ABORT_PLAT_LEAKED");
	freed = 1;
	++free_calls;
	emit("FREE_PRIV\n");
}

/* Module-exit producer/cleanup leaves used by the unchanged actual regi_exit. */
static void ssdk_netdev_notifier_unregister(void)
{
	CHECK(!notifier_unregister_calls, "NOTIFIER_UNREG_ONCE");
	notifier_unregister_calls = 1;
	emit("NOTIFIER_UNREG\n");
}

static void ssdk_fdb_retire_controls(void)
{
	CHECK(notifier_unregister_calls, "FDB_BEFORE_NOTIFIER");
	++fdb_controls_calls;
	emit("FDB_CONTROLS\n");
}

static unsigned driver_stopped_all(void)
{
	unsigned dev_id;

	if (driver_registered)
		return 0;
	for (dev_id = 0; dev_id < ndev; dev_id++)
		if (priv_slots[dev_id].qca_ssdk_sw_dev_registered == A_TRUE &&
		    !switch_unregistered[dev_id])
			return 0;
	return 1;
}

static int ssdk_switch_unregister(a_uint32_t dev_id)
{
	CHECK(dev_id < ndev, "SWITCH_UNREG_DEVICE");
	CHECK(priv_slots[dev_id].qca_ssdk_sw_dev_registered == A_TRUE,
	      "SWITCH_UNREG_GUARD");
	CHECK(!switch_unregistered[dev_id], "SWITCH_UNREG_ONCE");
	switch_unregistered[dev_id] = 1;
	++switch_unregister_calls;
	emit("SWITCH_UNREG %u\n", dev_id);
	return 0;
}

static sw_error_t ssdk_cleanup(a_uint32_t dev_id)
{
	CHECK(dev_id < ndev, "CLEANUP_DEVICE");
	CHECK(fdb_controls_calls, "CLEANUP_BEFORE_CONTROLS");
	CHECK(driver_stopped_all(), "CLEANUP_BEFORE_PRODUCERS");
	++cleanup_calls;
	if (unload_partial && dev_id == 1) {
		cleanup_failed = 1;
		emit("CLEANUP %u failed\n", dev_id);
		return SW_FAIL;
	}
	(void)ssdk_phy_driver_cleanup(dev_id);
	emit("CLEANUP %u ok\n", dev_id);
	return SW_OK;
}

/* Chip probe stage. */
static int chip_ver_get(a_uint32_t dev_id, ssdk_init_cfg *cfg)
{
	int rv;

	CHECK(dev_id < ndev, "CHIP_DEVICE");
	if (cur->chip_none & (1u << dev_id)) {
		emit("CHIP_GET %u no-device\n", dev_id);
		return -ENODEV;
	}
	rv = cur->chip_rv[dev_id];
	emit("CHIP_GET %u %d\n", dev_id, rv);
	if (rv)
		return rv;
	cfg->chip_type = CHIP_HPPE;
	return 0;
}

/* Driver publication. */
static int platform_driver_register(struct platform_driver *driver)
{
	(void)driver;
	CHECK(!driver_registered, "DRIVER_DOUBLE_REG");
	++driver_register_calls;
	emit("DRIVER_REGISTER\n");
	if (cur->driver_rv)
		return cur->driver_rv;
	driver_registered = 1;
	driver_register_ok = 1;
	return 0;
}

static void platform_driver_unregister(struct platform_driver *driver)
{
	(void)driver;
	CHECK(driver_registered, "DRIVER_UNREG_UNOWNED");
	CHECK(!any_phy_cleanup(), "ABORT_ORDER_DRIVER");
	CHECK(!any_plat_exit(), "ABORT_ORDER_DRIVER");
	CHECK(!freed, "ABORT_ORDER_DRIVER");
	++driver_unregister_calls;
	driver_registered = 0;
	emit("DRIVER_UNREGISTER\n");
}

/* SDK stages inside ssdk_init(). */
static sw_error_t sd_init_check(a_uint32_t dev_id, ssdk_init_cfg *cfg)
{
	(void)dev_id;
	(void)cfg;
	++sd_calls;
	emit("SD %d\n", cur->sd_rv);
	return cur->sd_rv;
}

static sw_error_t fal_init(a_uint32_t dev_id, ssdk_init_cfg *cfg)
{
	(void)dev_id;
	(void)cfg;
	if (cur->fal_rv != SW_OK)
		fal_failed = 1;
	emit("FAL %d\n", cur->fal_rv);
	return cur->fal_rv;
}

static int ssdk_phy_driver_init(a_uint32_t dev_id)
{
	CHECK(!fal_failed, "FAL_PHY_AFTER_FAILURE");
	(void)dev_id;
	++phy_calls;
	emit("PHY %d\n", cur->phy_rv);
	return cur->phy_rv;
}

static sw_error_t qca_hppe_hw_init(a_uint32_t dev_id)
{
	CHECK(!fal_failed, "FAL_SILENT_ACCEPT");
	(void)dev_id;
	++hppe_called;
	if (cur->hppe_rv != SW_OK)
		hppe_failed = 1;
	emit("HPPE %d\n", cur->hppe_rv);
	return cur->hppe_rv;
}

static sw_error_t ssdk_switch_register(a_uint32_t dev_id, int chip_type)
{
	(void)chip_type;
	CHECK(!hppe_failed, "HPPE_SWITCH_AFTER_FAILURE");
	CHECK(dev_id < ndev, "SWITCH_DEVICE");
	++switch_calls;
	switch_ok = (cur->switch_rv == SW_OK) ? 1 : 0;
	emit("SWITCH %d\n", cur->switch_rv);
	return cur->switch_rv;
}

/* Diagnostic plane. */
static int ssdk_sysfs_init(void)
{
	++sysfs_calls;
	emit("SYSFS %d\n", cur->sysfs_rv);
	return cur->sysfs_rv;
}

static int ssdk_genl_init(void)
{
	++genl_calls;
	emit("GENL %d\n", cur->genl_rv);
	return cur->genl_rv;
}

int ssdk_genl_deinit(void)
{
	++genl_deinit_calls;
	fail("GENL_DOUBLE_DEINIT");
	return 0;
}

/* Netdev cache contract. */
void ssdk_netdev_cache_start(void)
{
	++cache_start_calls;
	emit("CACHE_START\n");
}

void ssdk_netdev_cache_commit(void)
{
	++cache_commit_calls;
	emit("CACHE_COMMIT\n");
}

void ssdk_netdev_cache_stop(void)
{
	++cache_stop_calls;
	emit("CACHE_STOP\n");
}

static int register_netdevice_notifier(struct notifier_block *notifier)
{
	(void)notifier;
	CHECK(cur->expect_outcome != OUT_ZERODEV, "CACHE_ZERO_DEVICES");
	if (root_first_err_snapshot())
		fail("CACHE_DEGRADED");
	++notifier_calls;
	emit("NOTIFIER_REGISTER %d\n", cur->notifier_rv);
	if (cur->notifier_rv)
		return cur->notifier_rv;
	notifier_registered = 1;
	return 0;
}

static int ssdk_dev_event(struct notifier_block *notifier, unsigned long event,
			  void *ptr)
{
	(void)notifier;
	(void)event;
	(void)ptr;
	return 0;
}

/* ------------------------------------------------------- actual code ---- */
#include "actual.c"

int root_first_err_snapshot(void)
{
	return ssdk_root.first_err;
}

/* ------------------------------------------------------------ scenarios - */

static void reset_model(void)
{
	unsigned dev_id;

	memset(entered_plat, 0, sizeof(entered_plat));
	memset(plat_exited, 0, sizeof(plat_exited));
	memset(phy_cleaned, 0, sizeof(phy_cleaned));
	memset(local_bus_mode, 0, sizeof(local_bus_mode));
	memset(priv_slots, 0, sizeof(priv_slots));
	driver_registered = driver_register_ok = driver_register_calls = 0;
	driver_unregister_calls = 0;
	notifier_calls = notifier_registered = 0;
	cache_start_calls = cache_commit_calls = cache_stop_calls = 0;
	sysfs_calls = genl_calls = genl_deinit_calls = 0;
	free_calls = freed = 0;
	notifier_unregister_calls = fdb_controls_calls = 0;
	switch_unregister_calls = cleanup_calls = cleanup_failed = 0;
	unload_partial = 0;
	memset(switch_unregistered, 0, sizeof(switch_unregistered));
	topology_init_calls = topology_exit_calls = alloc_calls = 0;
	phy_cleanup_calls = plat_exit_calls = cancel_mac = cancel_qm = 0;
	sd_calls = fal_failed = phy_calls = hppe_called = hppe_failed = 0;
	switch_calls = switch_ok = 0;
	log_sysfs_degraded = log_genl_degraded = log_notifier_contract = 0;
	log_zero_dev = log_no_device = log_retained = log_aborted = 0;
	log_succeeded = log_cache_degraded = 0;
	ssdk_dev_notifier_owned = false;
	ssdk_dev_notifier_error = 0;
	ssdk_driver_owned = false;
	for (dev_id = 0; dev_id < SW_MAX_NR_DEV; dev_id++) {
		priv_slots[dev_id].device_id = dev_id;
		priv_slots[dev_id].version = QCA_VER_HPPE;
		priv_slots[dev_id].of_node = &node_singleton;
		priv_slots[dev_id].ports = SSDK_PHYSICAL_PORT7;
		priv_ptrs[dev_id] = &priv_slots[dev_id];
	}
	qca_phy_priv_global = priv_ptrs;
}

static void check_init_outcome(const struct input *in, int ret)
{
	unsigned expected_unregister;

	switch (in->expect_outcome) {
	case OUT_OK: {
		unsigned expected_registers =
			((cur->local_bus & ((1u << ndev) - 1)) != 0) ? 1u : 0u;

		CHECK(ret == 0, "RETURN_CODE");
		CHECK(driver_register_calls == expected_registers,
		      "DRIVER_REGISTER_COUNT");
		if (cur->chip_none)
			CHECK(hppe_called == 1 && switch_calls == 1,
			      "NO_DEVICE_SKIPPED_DEVICE");
		CHECK(notifier_registered && cache_commit_calls == 1,
		      "HEALTHY_CACHE");
		CHECK(sysfs_calls == 1 && genl_calls == 1, "DIAG_PLANE");
		CHECK(log_succeeded, "SUCCESS_LOG");
		break;
	}
	case OUT_ABORT:
		if (ret == 0)
			fail("ABORT_SWALLOWED");
		if (ret == -1)
			fail("ERRNO_RAW_MINUS1");
		if (ret == -ENODEV)
			fail("ERRNO_ENODEV");
		CHECK(ret == in->expect_ret, "ABORT_RETURN");
		CHECK(free_calls == 1, "ABORT_NO_FREE");
		CHECK(notifier_calls == 0 && cache_start_calls == 0 &&
		      cache_commit_calls == 0, "ABORT_CACHE");
		CHECK(sysfs_calls == 0 && genl_calls == 0, "ABORT_DIAG");
		CHECK(log_aborted, "ABORT_LOG");
		CHECK(phy_cleanup_calls == in->ndev, "ABORT_PHY_CLEANUP");
		CHECK(plat_exit_calls == entered_plat_count(),
		      "ABORT_PLAT_CLEANUP");
		expected_unregister = driver_register_ok;
		CHECK(driver_unregister_calls == expected_unregister,
		      "ABORT_DRIVER_CLEANUP");
		break;
	case OUT_RETAIN:
		CHECK(ret == 0, "RETAIN_RETURN_ERROR");
		CHECK(free_calls == 0, "RETAIN_FREED");
		CHECK(notifier_calls == 0 && cache_start_calls == 0 &&
		      cache_commit_calls == 0, "CACHE_ON_RETAIN");
		CHECK(sysfs_calls == 0 && genl_calls == 0, "DIAG_ON_RETAIN");
		CHECK(log_retained, "RETAIN_LOG");
		break;
	case OUT_NODEVICE:
		CHECK(ret == 0, "CHIP_ENODEV_FATAL");
		CHECK(notifier_calls == 0 && cache_commit_calls == 0,
		      "CACHE_NO_DEVICE");
		CHECK(log_no_device, "NO_DEVICE_LOG");
		CHECK(hppe_called == 0 && switch_calls == 0, "NODEVICE_HPPE");
		break;
	case OUT_ZERODEV:
		CHECK(ret == 0, "ZERODEV_RETURN");
		CHECK(notifier_calls == 0 && cache_commit_calls == 0,
		      "CACHE_ZERO_DEVICES");
		CHECK(log_zero_dev, "ZERODEV_LOG");
		break;
	case OUT_DEG_SYSFS:
		CHECK(ret == 0, "SYSFS_FATAL");
		CHECK(cache_commit_calls == 1, "DEG_CACHE");
		CHECK(log_sysfs_degraded, "SYSFS_SILENT");
		CHECK(genl_calls == 1, "DEG_GENL");
		break;
	case OUT_DEG_GENL:
		CHECK(ret == 0, "GENL_FATAL");
		CHECK(cache_commit_calls == 1, "DEG_CACHE");
		CHECK(log_genl_degraded, "GENL_SILENT");
		CHECK(sysfs_calls == 1, "DEG_SYSFS");
		break;
	case OUT_DEG_NOTIFIER:
		CHECK(ret == 0, "NOTIFIER_FATAL");
		CHECK(cache_start_calls == 1 && cache_stop_calls == 1 &&
		      cache_commit_calls == 0, "NOTIFIER_CACHE");
		CHECK(log_notifier_contract, "NOTIFIER_CONTRACT_LOG");
		CHECK(log_cache_degraded, "NOTIFIER_FINAL_STATUS");
		break;
	case OUT_EARLY_TOPO:
		CHECK(ret == in->expect_ret, "EARLY_TOPO_RETURN");
		CHECK(alloc_calls == 0 && topology_exit_calls == 0 &&
		      free_calls == 0, "EARLY_TOPO_CLEANUP");
		break;
	case OUT_EARLY_PRIV:
		CHECK(ret == in->expect_ret, "EARLY_PRIV_RETURN");
		CHECK(alloc_calls == 1 && topology_exit_calls == 1 &&
		      free_calls == 0, "EARLY_PRIV_CLEANUP");
		break;
	default:
		fail("OUTCOME_UNKNOWN");
	}
	if (in->expect_outcome != OUT_ABORT && in->expect_outcome != OUT_UNLOAD) {
		CHECK(phy_cleanup_calls == 0 && plat_exit_calls == 0 &&
		      driver_unregister_calls == 0, "UNEXPECTED_CLEANUP");
		if (in->expect_outcome != OUT_RETAIN)
			CHECK(free_calls == 0, "FREE_UNEXPECTED");
	}
	if (strcmp(in->name, "retain-after-publish") == 0)
		CHECK(hppe_called == 1 && switch_calls == 1,
		      "DEGRADED_DEV_MISSING");
}

static void run_stop_model(const struct input *in)
{
	struct qca_phy_priv *priv = &priv_slots[0];

	ssdk_root_reset();

	/* The MAC work is gated by the HPPE/SCOMPHY chip family and the QM work
	 * by the DESS/MHT family; test each with a version its chip check admits. */
	if (in->variant == 0) {
		priv->version = QCA_VER_HPPE;
		CHECK(ssdk_mac_sw_sync_work_stop(0) == SW_NOT_SUPPORTED,
		      "MAC_STOP_UNSTARTED_RETURN");
		CHECK(cancel_mac == 0, "MAC_STOP_UNSTARTED_CANCEL");
		CHECK(qca_mac_sw_sync_work_init(priv) == 0, "MAC_INIT");
		CHECK(ssdk_mac_sw_sync_work_stop(0) == SW_OK, "MAC_STOP_STARTED");
		CHECK(cancel_mac == 1, "MAC_CANCEL");
		ssdk_mac_sw_sync_work_stop(0);
		CHECK(cancel_mac == 2, "MAC_CANCEL_REPEAT");
		priv->version = QCA_VER_DESS;
		qm_err_check_work_stop(priv);
		CHECK(cancel_qm == 0, "QM_STOP_UNSTARTED_CANCEL");
		qm_err_check_work_init(priv);
		qm_err_check_work_stop(priv);
		CHECK(cancel_qm == 1, "QM_CANCEL");
		qm_err_check_work_stop(priv);
		CHECK(cancel_qm == 2, "QM_CANCEL_REPEAT");
	} else {
		/* Retained-state unload: chip/plat were reached but no producer
		 * work was ever initialized. */
		entered_plat[0] = 1;
		priv->version = QCA_VER_HPPE;
		CHECK(ssdk_mac_sw_sync_work_stop(0) == SW_NOT_SUPPORTED,
		      "MAC_STOP_UNSTARTED_RETURN");
		CHECK(cancel_mac == 0, "MAC_STOP_UNSTARTED_CANCEL");
		priv->version = QCA_VER_DESS;
		qm_err_check_work_stop(priv);
		CHECK(cancel_qm == 0, "QM_STOP_UNSTARTED_CANCEL");
		ssdk_driver_unregister_owned();
		CHECK(phy_cleanup_calls == 0, "UNLOAD_CLEANUP_ORDER");
		ssdk_phy_driver_cleanup(0);
		ssdk_plat_exit(0);
		ssdk_free_priv();
		CHECK(free_calls == 1 && plat_exited[0] && phy_cleaned[0],
		      "UNLOAD_TAIL");
	}
}

static void run_latch_unit(void)
{
	ssdk_root_reset();
	ssdk_root_stage_set(SSDK_ROOT_STAGE_TOPOLOGY, 0);
	ssdk_root_latch(SSDK_ROOT_STAGE_TOPOLOGY, 0, -12,
			SSDK_ROOT_DOMAIN_LINUX);
	ssdk_root_latch(SSDK_ROOT_STAGE_PRIV, 0, -22, SSDK_ROOT_DOMAIN_SW);
	CHECK(ssdk_root.first_err == -12, "FIRST_ERROR_OVERWRITE");
	CHECK(ssdk_root.first_stage == SSDK_ROOT_STAGE_TOPOLOGY,
	      "FIRST_STAGE_OVERWRITE");
	CHECK(ssdk_root.first_dev_id == 0, "FIRST_DEVICE");
	CHECK(ssdk_root_errno(SW_NOT_SUPPORTED, SSDK_ROOT_DOMAIN_SW) ==
	      -EOPNOTSUPP, "ERRNO_MAP");
	CHECK(ssdk_root_errno(-5, SSDK_ROOT_DOMAIN_LINUX) == -5,
	      "ERRNO_VERBATIM");
	CHECK(ssdk_root_errno(SW_BUSY, SSDK_ROOT_DOMAIN_SW) == -EBUSY,
	      "ERRNO_BUSY");
	CHECK(strcmp(ssdk_root_stage_name(SSDK_ROOT_STAGE_SWITCH), "switch") == 0,
	      "STAGE_NAME");
	CHECK(strcmp(ssdk_root_stage_name(SSDK_ROOT_STAGE_PLAT), "plat") == 0,
	      "STAGE_NAME_PLAT");
}

static void run_errno_unit(void)
{
	CHECK(ssdk_root_errno(SW_OK, SSDK_ROOT_DOMAIN_SW) == 0, "ERRNO_OK");
	CHECK(ssdk_root_errno(SW_NOT_SUPPORTED, SSDK_ROOT_DOMAIN_SW) ==
	      -EOPNOTSUPP, "ERRNO_SW_ENODEV");
	CHECK(ssdk_root_errno(SW_OUT_OF_MEM, SSDK_ROOT_DOMAIN_SW) == -ENOMEM,
	      "ERRNO_MAP");
	CHECK(ssdk_root_errno(SW_ALREADY_EXIST, SSDK_ROOT_DOMAIN_SW) == -EEXIST,
	      "ERRNO_MAP");
	CHECK(ssdk_root_errno(SW_BUSY, SSDK_ROOT_DOMAIN_SW) == -EBUSY,
	      "ERRNO_MAP");
	CHECK(ssdk_root_errno(SW_BAD_PTR, SSDK_ROOT_DOMAIN_SW) == -EINVAL,
	      "ERRNO_MAP");
	CHECK(ssdk_root_errno(SW_FAIL, SSDK_ROOT_DOMAIN_SW) == -EIO, "ERRNO_MAP");
	CHECK(ssdk_root_errno(-ENODEV, SSDK_ROOT_DOMAIN_LINUX) == -EIO,
	      "ERRNO_GUARD");
	CHECK(ssdk_root_errno(-EINVAL, SSDK_ROOT_DOMAIN_LINUX) == -EINVAL,
	      "ERRNO_VERBATIM");
}

static void run_unload_model(const struct input *in)
{
	unsigned dev_id;

	/* Model a retained module: device 0 published and registered, device 1
	 * retained at its post-publication failure, platform rights held. */
	ndev = in->ndev;
	unload_partial = in->variant == 1;
	driver_registered = 1;
	driver_register_ok = 1;
	ssdk_driver_owned = true;
	local_bus_mode[0] = 1;
	for (dev_id = 0; dev_id < ndev; dev_id++)
		entered_plat[dev_id] = 1;
	priv_slots[0].qca_ssdk_sw_dev_registered = A_TRUE;
	priv_slots[1].qca_ssdk_sw_dev_registered = A_FALSE;
	regi_exit();
	CHECK(notifier_unregister_calls == 1 && fdb_controls_calls == 1,
	      "UNLOAD_CONTROLS");
	CHECK(driver_unregister_calls == 1, "UNLOAD_DRIVER");
	CHECK(switch_unregister_calls == 1 && switch_unregistered[0],
	      "UNLOAD_SWITCH");
	CHECK(cleanup_calls == ndev, "UNLOAD_CLEANUP");
	CHECK(unload_partial ? cleanup_failed : !cleanup_failed,
	      "UNLOAD_CLEANUP_RESULT");
	CHECK(plat_exit_calls == ndev, "UNLOAD_PLATFORM");
	CHECK(free_calls == 1 && freed, "UNLOAD_FREE");
}

static void run_case(unsigned index)
{
	const struct input *in = &inputs[index];
	int ret = 0;

	reset_model();
	cur = in;
	ndev = in->ndev;
	CHECK(ndev <= SW_MAX_NR_DEV, "MODEL_CAPACITY");
	emit("CASE %s\n", in->name);
	switch (in->kind) {
	case 0:
		ret = regi_init();
		check_init_outcome(in, ret);
		break;
	case 1:
		run_stop_model(in);
		break;
	case 2:
		run_latch_unit();
		break;
	case 3:
		run_errno_unit();
		break;
	case 4:
		run_unload_model(in);
		break;
	default:
		fail("CASE_KIND");
	}
	emit("END\n");
}

int main(int argc, char **argv)
{
	unsigned index = 0;

	if (argc == 1) {
		for (index = 0; index < CASE_COUNT; index++)
			run_case(index);
	} else if (argc == 2) {
		index = (unsigned)strtoul(argv[1], NULL, 10);
		CHECK(index < CASE_COUNT, "CASE_RANGE");
		run_case(index);
	} else {
		fail("ARGUMENTS");
	}
	CHECK(fwrite(trace, 1, used, stdout) == used, "STDOUT");
	return 0;
}
