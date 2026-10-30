# SSDK root partial-init ownership and error plan

Base:7ef14eec43170536e248501dee5d5552a7944a1d on local candidate
codex/ax6-ssdk-root-rollback-20261030. Build2bcafb4 remains frozen. No make,
target/module/firmware/cloud build, push, main merge, Release or device access.
Pure pinned-source preparation and native isolated function fixtures are separate
limited gates, not target or hardware execution. Do not execute old audit tools.

## Binding and ordering

Exact SSDK pin:d9a196497ecee2530722d906e0efe1b7408b6ef6 plus current18 patches.
Fresh recipe9 baseline text is ROOT-BASELINE-20261030-r1 in the previous active
ssdk-dp-retirement evidence directory:18 layers/692 files, exact declared hunk
coordinates and output bytes. New phase evidence lives in ssdk-root-rollback.
Only data are reused; no previous PASS becomes this phase's qualification.

The root acquires device topology, private slots and PHY metadata, then loops
over platform access, a global platform-driver registration, chip identification,
FAL/PHY, chip-specific initialization and per-device switch services. Sysfs,
generic netlink and cache subscription follow. Every edge needs its own owner
and partial-failure contract; array count or one success bit is insufficient.

FAL calls HSL API setup, HSL device setup, optional VLAN and adapter setup. PHY
has a separate shared driver/bitmap/metadata graph. The root currently masks a
FAL init failure with a PHY result, and its fatal path only frees private memory.
Do not expose that first error as fatal before a verified compensating path.

## Approved first independent units

A1: topology allocation before any FAL/PHY publication.

- Preserve existing valid num_devices/default/no-node behavior, including the
  existing zero-count case; do not introduce an unverified device-count policy.
- Reject reentry over an already published topology without modifying or freeing
  that existing state. This is not concurrency or provider-takeover support.
- Read a present count through the typed OF API while the found node reference
  is held, then always put that reference. Missing property keeps default1;
  malformed present data fails before any allocation/publication.
- Allocate the pointer array and each child locally, using overflow-safe array
  allocation. On failure release only this attempt's acquired children/array.
  Publish globals/count together only after all children are initialized.
- regi_init must propagate this preparation error immediately, before private,
  platform/driver/FAL/PHY and global controls. Never call generic root cleanup on
  an unacquired topology or a rejected existing owner.
- If private-array allocation failed with qca_phy_priv_global still NULL, the
  already owned topology must still be freed. No FAL/PHY cleanup is added.
- This does not qualify ssdk_dt_parse's node/clock references or partial private
  slot PHY metadata allocation; those remain in their separate ownership map.

A2: cleanup error visibility, without changing cleanup actions/order.

- ssdk_cleanup must retain the first FAL/PHY error while still invoking exactly
  the existing cleanup sequence. Preserve emulation's PHY skip.
- regi_exit must report errors per device and retain the first nonzero result
  across the full existing device loop. No added cleanup call, early break,
  changed init policy or invented per-device independence follows from this.
- Module exit is void. Better reporting cannot prevent unload, make an unsafe
  child cleanup safe or prove hardware retirement. FAL internal short-circuit
  behavior is not silently changed in this unit.

## Required ownership maps before fatal-init migration

B1: actual FAL child success/failure/self-unwind, per-device versus global
HSL/adpt pointers, VLAN allocation, API publication and cleanup gates. Read the
actual child callbacks, not only wrapper names. Never call cleanup merely
because init was attempted.

B2: actual PHY metadata allocation, driver/port bitmaps and registered callbacks,
shared driver ownership, init failures, SFP and cleanup. Distinguish initialized
metadata from registered hardware/MDIO drivers, and inspect recipe-selected PHY
features rather than assuming all chip implementations are enabled.

B3: root platform MMIO/clock/region and platform-driver ownership; switch MIB,
QM/MAC polling, IRQ/FDB and optional swconfig publication; global controller
registration and failure guarantees. Existing plat_exit and switch_unregister
are not automatically valid inverses for an arbitrary partial attempt.

C: only after those contracts identify safe operations, implement dependency-aware
owned-stage rollback. Retain services required by callbacks until they drain;
unpublish admission before releasing backing state. Preserve exact first error
separately from cleanup errors. Treat unsupported/ENODEV behavior explicitly,
not as an accidental consequence of changing an inner return value.

Unknown partial FAL writes, void callbacks, hardware reset/clock effects or
external owners remain blocked designs until evidence supports an inverse.
Do not hide the error by success, blindly call normal exit, free live state,
disable features or restore guessed defaults to obtain a green fixture.

## Verification

Compile complete current function definitions in fresh native fixtures, with
explicit OS/framework/leaf models. Bind exact baseline/candidate full-tree
derivation, patches, recipe and all owned assets; check them again at the end.
Record full independent positive traces, argument/value/owner ledgers and named
runtime mutation markers. A compile error, timeout, sanitizer output or arbitrary
nonzero return is not a successful semantic negative.

A1 tests must cover missing/present/malformed property, zero/one/multiple nodes,
each allocation failure, no premature publication, existing-state preservation,
exact reference/free balance, repeat exit and the real regi_init early barrier.
Test only the declared null-private-array failure boundary, not an invented
no-op PHY metadata model advertised as full private-slot rollback.

A2 tests must cross distinct FAL/PHY errors, emulation and multiple devices,
including nonfinal failures. New action traces must equal baseline traces while
return/log aggregation changes correctly. This proves reporting only, not the
underlying callback/module lifetime.

Use GCC and Clang ASan/UBSan with strict warnings, exact error and oracle controls,
and correct per-case shared sanitizer exit settings. LSan/kernel RCU/lockdep,
target ABI/link/modpost, real hardware, full module lifetime and performance are
not qualified by these host tests. Existing DP/SSDK results remain historical
at their exact source layers; new layers need explicit matching integration
qualification before any later separately authorized build.
