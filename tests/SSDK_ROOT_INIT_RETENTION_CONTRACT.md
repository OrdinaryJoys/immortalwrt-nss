# SSDK root-init retention and degraded-state contract

Status: **SOURCE CANDIDATE — NOT RELEASE-QUALIFIED.** This contract documents the
`054-ssdk-root-init-retention.patch` layer added to the B (r3/SSDK) source line.
It is proven only by the offline host model in
`tests/test-ssdk-root-init-retention.py` (prepared 42-patch tree, patched
`src/init/ssdk_init.c` compiled in serial stubs). No target build, module load,
hardware boot, concurrency, RCU/lockdep, workqueue-drain or module-unload
evidence is claimed here.

- Patch: `package/qca-nss/qca-ssdk/patches/054-ssdk-root-init-retention.patch`
- Patch scope: `src/init/ssdk_init.c` **only**
- Patch count: 42 (`001` … `054`), upstream pin `d9a196497ecee2530722d906e0efe1b7408b6ef6`
- `include/init/ssdk_init.h` is **not modified**: the retention context and
  helpers are module-private (`static`) and no exported ABI changes. The
  proposal text's file list mention of the header is superseded by this line.
- This patch does not change `package/qca-nss/qca-ssdk/Makefile`; the
  `PKG_RELEASE` bump and lock/manifest regeneration belong to the release/lock
  task (the shared worktree's Makefile already shows r32 from a concurrent
  task, which is not part of this change set).

## 1. Why a contract is needed

A negative result from a module's `init` makes the kernel free the module
without ever calling its `module_exit`. The pre-054 `regi_init()` tail called
`ssdk_free_priv()` and returned the error for any non-`-ENODEV` code, but
`ssdk_free_priv()` is not a generic inverse: the platform driver, the netdev
notifier, MIB/QM/MAC producers, FAL/PHY state and platform MMIO/clocks may
remain published while their code is freed. That is a UAF class (AX6-04). The
withdrawn fail-closed variants did not change this; this layer replaces the
tail with an explicit retention contract.

## 2. Staged initialization and the publication boundary

`regi_init()` records every stage it is about to run in a module-private root
context (`stage`, per-device `dev_stage[]`, `first_err`, `first_stage`,
`first_domain`, `first_dev_id`, `dev_initialized`, `published`, `no_device`):

1. `TOPOLOGY` — `ssdk_switch_device_num_init()` (helper unwinds internally)
2. `PRIV` — `ssdk_alloc_priv()` (private slots + published PHY metadata)
3. per device: `PLAT` (`ssdk_plat_init`), `DRIVER` (module-wide platform
   driver publication), `CHIP` (`chip_ver_get`)
4. **publication boundary** — from `ssdk_init()` on (FAL/PHY and later
   `SDK`/`SWITCH` stages), producers/backends are published

`first_err` latches only the first business error; later failures and cleanup
errors never overwrite the cause of the degraded state.

## 3. Error-domain mapping

`ssdk_root_errno()` maps a latched error to the module-init return:

| Domain | Mapping |
|---|---|
| Linux errno (`topology`, `priv`, `driver`, explicit `ssdk_plat_init` errnos) | verbatim |
| `SW_NOT_SUPPORTED` | `-EOPNOTSUPP` |
| `SW_OUT_OF_MEM` | `-ENOMEM` |
| `SW_ALREADY_EXIST` | `-EEXIST` |
| `SW_BUSY` | `-EBUSY` |
| `SW_BAD_*` / `SW_OUT_OF_RANGE` | `-EINVAL` |
| anything else | `-EIO` |
| final `-ENODEV` | remapped to `-EIO` |

`-ENODEV` is reserved for `chip_ver_get()`'s no-device sentinel; a module-init
failure is never reported as an absent switch. `ssdk_plat_init()` returns the
bare `SW_FAIL` (`-1`) for mapping/region failure and Linux errnos for
argument/ownership rejections; only `SW_FAIL` is classified as SSDK domain.

Only `chip_ver_get()` interprets `-ENODEV` as "no device" (`no_device` flag,
device skipped, no error latched). Every other stage treats `-ENODEV` as a
normal failure.

## 4. Pre-publication abort (fatal module init allowed)

If a failure happens before the publication boundary **and no earlier device
has published**, `regi_init()` unwinds in the same serial order `regi_exit()`
already uses for those stages and returns the mapped errno:

1. remove the module-wide platform driver publication exactly once
   (`ssdk_driver_unregister_owned()`; it cannot depend on a device register
   mode that differs from the registering device)
2. release the PHY metadata published by `ssdk_alloc_priv()`
   (`ssdk_phy_driver_cleanup()`, all devices)
3. release platform MMIO/clock rights for the devices that entered the
   `PLAT` stage (`dev_stage[] >= SSDK_ROOT_STAGE_PLAT`); `ssdk_plat_exit()`
   is a documented no-op when acquisition did not complete (owner still NULL)
4. `ssdk_free_priv()` frees private slots and the topology

FAL/PHY/switch producers were never started, so a negative module-init result
leaves no module code referenced. Abort cleanup errors are logged but never
overwrite `first_err`.

## 5. Post-publication retention (fatal module init forbidden)

A failure after the publication boundary — or any failure once an earlier
device already published — is **retained**:

- log the stage name, device and first error code (one degraded banner that
  names the withheld netdev cache and the qca-nss-dp refusal)
- **do not** call `ssdk_free_priv()`, do not attempt rollback
- return 0 from module init; the module stays resident and the partially
  published producers remain valid
- do **not** initialize the diagnostic plane (sysfs/genl) for a retained state
- do **not** commit the netdev cache

FAL keeps its own first error (`ssdk_init()` returns it and does not attempt
PHY initialization after a FAL failure), and the HPPE return becomes a
required stage result: a HPPE failure is latched and retained before
`ssdk_switch_register()`. `dev_initialized` counts only devices whose
`ssdk_switch_register()` succeeded.

## 6. Netdev cache / qca-nss-dp contract

Cache-live is defined as **all** of:

1. `first_err == SW_OK`
2. `dev_initialized > 0`
3. the netdev notifier is registered and the cache was committed

The cache is started/committed only inside `ssdk_netdev_notifier_register()`
and only reached under that condition. A retained init, an all-DT-disabled
topology and a no-device topology therefore leave the cache uncommitted and
log the refusal explicitly; this is a hard consumer contract, not "optional":
qca-nss-dp admission fails closed when the cache is not live (no DP source
change is part of this patch). A notifier registration failure is logged as a
`netdev cache contract violation` naming the qca-nss-dp refusal; the cache is
stopped and never committed, and the final module-init status line reports the
degraded cache instead of a plain success.

Sysfs/genl are diagnostic-only: their failures are logged ("diagnostic plane
degraded"), never fatal and never cache-gating. They are stopped once through
the existing fdb-retirement path during module exit; the init path never
de-initializes them.

## 7. Retained-state unload semantics (residuals)

Retention is only safe if a later module unload (`rmmod`) can run the existing
`regi_exit()` without touching unstarted producers. This layer keeps
`regi_exit()` **byte-identical** to the 41-layer body (host witness:
`REFREEZE.json.regi_exit_unchanged`) and therefore keeps its proven serial
order and guards. The host model additionally compiles and runs that unchanged
actual `regi_exit()` against a modelled retained state
(`unload-retained-clean` / `unload-retained-fal-partial`): notifier
unregistration and fdb/between controls once, one module-wide driver
unregistration, per-device `switch_unregister` only for registered devices,
`ssdk_cleanup` only after all producers stopped, platform release after
cleanup, and the private/topology tail last. The partial variant models the
documented FAL-cleanup failure contract (dependent PHY release skipped, leak
accepted) and still reaches the same tail without a fatal return. The layer
adds only:

- `qm_err_check_work_stop()` / `ssdk_mac_sw_sync_work_stop()` initialized
  guards, so a device whose work item was never initialized is not passed to
  `cancel_delayed_work_sync()` (MIB/FDB/interrupt producers already carry their
  own `*_work_initialized` guards from layers 022/029/030)
- the root context reset (`ssdk_root_reset()`) clears the producer flags and
  the diagnostic latch for a fresh init context

Known **open residuals** (not hidden, not claimed closed):

- **FAL/HAL partial init leak on unload** — if FAL initialization fails after
  partially allocating `dev_ssdk_cfg`/VLAN state, the retained module's later
  `ssdk_cleanup()` may leak that partial allocation; no UAF is identified in
  source review but the leak is not quantified. Retention deliberately chooses
  a leak over freeing live producer state.
- **`of_platform_populate` children** — the platform driver probe creates
  child platform devices; unregistering the driver has no proven inverse for
  already-populated children (S2R-09 open non-inverse). Retention keeps the
  module resident, so no child references freed code, but child lifetime is
  not owned by this patch.
- **S2R-09 fatal-init rollback transaction remains BLOCKED-DESIGN** — no
  rollback, no ownership maps, no idempotent-stop proof beyond the above.
- No failure-path hardware evidence exists; a healthy boot only regresses the
  success path and can never prove the failure paths.
- Target/host **target** compile and module load are not performed here; the
  host model compiles the actual patched function bodies only.

## 8. Verification map

| Claim | Evidence |
|---|---|
| 42/42 patch queue replays context-clean into the pinned tree; only `src/init/ssdk_init.c` changes | `tests/ssdk-root-init-retention/source.py::prepare` (declared-context verify + `patch --fuzz=0`), `EXTRACTED.json`, `RESULTS.json.layers` |
| Pre-publication abort order/errno/cleanup | host model cases `abort-*`; static gates `abort_order`, `abort_scoped_by_stage`, `abort_honest_errno`, `plat_domain`, `errno_map`; mutants `abort-phy-after-plat`, `abort-plat-skip`, `abort-no-free`, `abort-unregister-unowned`, `errno-raw-minus1`, `errno-guard-removed` |
| Post-publication retention (return 0, no free, no cache, no diagnostic plane) | cases `retain-fal`, `retain-hppe`, `retain-switch`, `retain-after-publish`; static gates `retention_return_zero`, `postpub_no_free`, `cache_gate`; mutants `retain-frees-priv`, `retain-return-error`, `cache-on-degraded`, `cache-on-zero-devices` |
| FAL first error preserved, PHY not attempted | case `retain-fal`; gate `fal_first_error`; mutants `fal-continue`, `fal-overwrite-first-error` |
| HPPE return is a required stage | case `retain-hppe`; gates `hppe_capture`, `hppe_gate`; mutant `hppe-ignore` |
| `-ENODEV` only from `chip_ver_get` | cases `no-device`, `no-device-then-device`; gates `enodev_single`, `enodev_stage_errors`; mutants `chip-enodev-fatal`, `plat-enodev-swallowed` |
| All-DT-disabled / zero admitted devices have no cache | case `all-disabled`; gate `cache_degraded_log`; mutant `cache-on-zero-devices` |
| Sysfs/genl degraded but non-fatal | cases `degraded-sysfs`, `degraded-genl`; gates `sysfs_nonfatal`, `genl_nonfatal`; mutants `sysfs-fatal`, `sysfs-silent`, `genl-double-deinit` |
| Work stop is safe when unstarted / idempotent | cases `stop-idempotence`, `stop-retained-state`; gates `work_guard_mac`, `work_guard_qm`; mutants `mac-stop-guard-removed`, `qm-stop-guard-removed` |
| `regi_exit()` unchanged (re-freeze witness) | `REFREEZE.json.regi_exit_unchanged` |
| Retained-state unload composition (actual `regi_exit()`) | cases `unload-retained-clean`, `unload-retained-fal-partial`; the suite's unload barriers (controls once before producers, producers before cleanup, cleanup before platform/private) |

## 9. Existing-suite re-freeze (out of this patch's write scope)

The existing SSDK/DP suites pin historical prepared layers (31/19/20 patches).
`REFREEZE.json` records the 42-layer identities they must be re-frozen to, the
function-level impact (only `regi_init` among the models of
`test-ssdk-root-lifecycle.py` changes; `regi_exit` and every other modelled
function are unchanged) and the evidence that this patch touches only
`src/init/ssdk_init.c`. Updating those pin files and re-running them is a
separate task; until then this contract must not be represented as
"existing suites green on the 42-layer".

Feasibility was demonstrated for the exit-order suite in a scratch copy (no
repository file edited): the unchanged 312-case/6-mutant root-exit campaign
passes on the 42-layer prepared tree after updating only its three pins
(`SOURCE_SHA`, `RECEIPT_SHA`, patch count 31→42), because `regi_exit()` is
byte-identical. The other suites additionally embed layer-scoped receipt
chains and, for `test-ssdk-root-lifecycle.py`, a `regi_init()` oracle that the
retention rewrite intentionally changes; they need their own re-freeze and
oracle update task.
