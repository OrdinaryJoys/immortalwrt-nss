# SSDK root-init retention: actual 42-layer host model

The 42-layer prepared tree (`d9a19649` + the live 42-patch inventory, last
`054-ssdk-root-init-retention.patch`) is replayed context-clean from a local
pinned clone. From the prepared `src/init/ssdk_init.c` the model extracts,
without body modification:

- the complete actual `regi_init()` (all stages, latches, retain/abort tails),
- the actual `ssdk_init()` (FAL first error, PHY suppression),
- the root context helpers (reset/stage/latch/domain/errno/abort),
- the module-wide `ssdk_driver_register()` / `ssdk_driver_unregister_owned()` /
  per-device wrapper,
- `qm_err_check_work_init/start/stop`, `qca_mac_sw_sync_work_init`,
  `ssdk_mac_sw_sync_work_stop` and their chip checks,
- `ssdk_netdev_notifier_register()` (qca-nss-dp cache contract wording).

Stubs are explicit models, not target ABI: SDK leaf calls
(`sd_init_check`, `fal_init`, `ssdk_phy_driver_init`, `chip_ver_get`,
`qca_hppe_hw_init`, `ssdk_switch_register`, topology/priv/platform/driver
publication, sysfs/genl, netdev cache/notifier, cleanup/platform/free
inverses), serial work/mutex primitives, and the kernel errno constants. The
model never runs real kernel workqueues, threads, RCU or module unload; it is
a serial contract model.

## Cases

29 fixed scenarios across the case table in `source.py`:

- healthy 1/2-device, MDIO-only and mixed no-device/device topologies,
- pre-publication abort at topology/priv/plat/driver/chip with honest errnos,
  exact unwind order and stage-scoped platform cleanup,
- post-publication retention at FAL/PHY(artificial)/HPPE/switch and
  retention after an earlier device already published,
- all-DT-disabled, no-device, sysfs/genl degraded, notifier-failure degraded,
  module-wide driver publication with two devices,
- work-stop idempotence, retained-state unload composition through the
  actual unchanged `regi_exit()` (clean and FAL-partial-cleanup variants),
- first-error latch and errno-map units.

Every positive asserts the outcome class, exact module-init return, call
counters (driver register/unregister, PHY metadata cleanup, platform exit,
cache start/commit/stop, notifier, frees), cleanup-order barriers and required
log markers. Free-form log text is not the oracle; the listed markers are.

## Mutants

23 named source mutants in `test-ssdk-root-init-retention.py` are applied to
the extracted actual code, newly compiled clean, and must exit 86 with no
stdout and exactly one fixed `ROOT_ASSERT:<marker>` line: FAL continue/overwrite,
first-error overwrite, HPPE ignore, cache on zero devices / degraded, sysfs
fatal/silent, genl double deinit, abort order/skip/no-free/unowned-unregister,
retain frees/returns error, errno `-ENODEV`, errno raw `-1`, chip `-ENODEV`
fatal, platform `-ENODEV` swallowed, MAC/QM stop-guard removal, driver double
register.

## Static gates and controls

Static gates inspect the actual prepared source: patch touches only
`src/init/ssdk_init.c`; `regi_exit()` body is byte-identical to the 41-layer;
only `chip_ver_get()` interprets `-ENODEV`; no old `SW_CNTU...` macro in the
root loop; no free/negative return on the post-publication path; retention
returns 0 with the banner; cache requires first error clear and >0 initialized
devices; exact errno map with `-ENODEV` remapped; `ssdk_plat_init` bare
`SW_FAIL` gets an honest errno; abort order and `dev_stage[]` scoping;
`stage` is read back in the banners; module-wide driver publication;
FAL/HPPE stage handling; sysfs/genl non-fatal; qca-nss-dp notifier contract
wording; work initialized guards; producer unload guards present. Seventeen
text mutations prove each gate can fail (gate controls).

## Re-freeze witness

`REFREEZE.json` records the 42-layer identities and function impact for the
existing SSDK/DP suites plus the fact that `regi_exit()` is unchanged. The
existing pin files are outside this patch's write scope; the witness is what
the re-freeze needs.

## Run

```sh
python3 -B -O tests/test-ssdk-root-init-retention.py \
  --upstream-cache /tmp/qsdk-ssdk \
  --output /tmp/ssdk-root-init-retention-$(date +%s) \
  --cc gcc-16 --sanitize
```

The output directory must be fresh. The driver prints a JSON summary and writes
`RESULTS.json`, `EXTRACTED.json`, `REFREEZE.json` and `ASSET-FREEZE.json`.
Status `HOST_MODEL_ONLY` means the offline contract model passed; it is not a
target compile, build, flash or hardware qualification.
