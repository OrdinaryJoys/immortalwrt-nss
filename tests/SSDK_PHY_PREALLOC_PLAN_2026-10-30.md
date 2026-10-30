# PHY metadata pre-DT ownership transaction

Base3a73e535d6c3120c17b7ca501a7cae95d4e4c91a, SSDK pin
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus21 patches. No make, target,
module/firmware/cloud build, push, main, Release or device access. Current
repo pure preparation and freshly generated native function fixtures only.
Do not execute historical/sealed generated programs or upgrade their PASS.

## Admission is a separate prerequisite

Selected recipe is MODULE_TYPE=KSLIB; upstream mk/Makefile builds obj-m.
The actual root path before private preparation only acquired topology. Driver,
DT/MDIO/SFP, sysfs, genl and notifier/cache registration occur later. Embedded
FDB/IRQ setup only initializes fields and queues no work. PHY metadata helpers
are not exported kernel symbols; the old init has one root caller, replaced by
this unit. No constructor is permission to overwrite a pre-existing owner.

Read exact Linux6.18.38/e46dc0adfe39724bcf52cea47b8f9c9aed86a394:
resolve_symbol/ref_module and __symbol_get use strong_try_module_get, which
rejects COMING; init completes before LIVE. Plain try_module_get/module_is_live
does not exclude COMING. This is not a universal isolation shortcut. The actual
selected SSDK exports and registered callback paths require separate bounded
source review before accepting pre-DT publication. Other embedding/builtin,
nonstandard early callbacks, live reentry and concurrent teardown remain outside
this fresh-root contract, not silently supported by a local pointer check.

## Staged ownership

prepare receives an empty owned output cell and an initial candidate bitmap.
It allocates/fills a private real phy_info_t. Optional QCA808X_PORTS_INFO fills
the same port/address/feature bits and candidate bitmap without global calls.
Any preparation error leaves caller output/bitmap and globals unchanged.

Root constructs its pointer vector, all private records, all metadata and
candidate bitmaps locally. Counts are bounded by real SW_MAX_NR_DEV. Work setup
may initialize only these local records; no service/work/IRQ is started.

Before transfer, root checks its private destination is still empty. Metadata
publication validates all fixed global slots are empty, count/arguments valid,
every candidate present and no duplicate candidate identity. It performs no
fallible work after its first store, consumes each owned input pointer and
updates only the admitted slots. Root publishes its complete private vector
last. These ordinary stores are not an atomic multi-cell protocol for live
raw readers: admission above is required, not a new lifetime lock.

On failure root releases only its local metadata/private objects in reverse
allocation order and its vector. It never clears or restores a global cell,
frees foreign objects, or invokes global PHY/FAL/cache/control/IRQ cleanup.
regi_init's pre-DT allocation error retires only the topology it just acquired
and returns the exact errno. It does not enter generic free_priv/module exit.

The DT-only exit call and its ownership comment are outside the qca808x
retained slice, matching the existing DT include/init/exit marker boundaries.
The allocation error arm and exact return remain retained. A pure marker
projection is only a dependency-regression check, not an actual exporter or
QCA808x target-build qualification.

Normal post-DT cleanup remains unchanged. The temporary ledger is consumed at
success and is not retained for a later second free. Shared phy_ops/global UK,
live reader retirement, FAL fatal migration, parser error/ID domains and full
root abort remain OPEN. Do not add late metadata frees to hide those gaps.

The compatibility qca_ssdk_phy_info_init signature stays. Its valid fresh-slot
values match upstream in QCA on/off profiles; absent QCA leaves a pre-existing
bitmap unchanged as before. Existing slots/invalid IDs are rejected without
allocation or mutation, not reused or freed. This serialized-init compatibility
entry is not a general live reinitialization API.

## Required verification

- Exact pinned21 baseline ->034 outputs, whole692 files, no fuzz/offset and
  only admitted source/header changes. SSDK release11->12 only; DP9/pins/build
  lock/performance knobs unchanged. Old recipe exception must match its entire
  historical hash after the unique release-line delta; current22 is strict.
- Extract complete real prepare/publish/compatibility/root allocator and early
  error functions, actual phy_info_t, enums, constants and QCA table. Model
  Linux structs/allocator/OF/work explicitly; do not claim target ABI.
- Every vector/private/metadata allocation fault for counts0..3; original errno,
  only successful owned allocations retired once, globals and arbitrary prior
  bitmaps unchanged, no shared-ops or control/driver/FAL/PHY cleanup.
- QCA on/off and PHY-I2C layout profiles; all valid fields/zero payload/candidate
  bitmap match complete old source behavior. Pure staging has no global writes.
- Busy/invalid/NULL/duplicate candidates reject before transfer; foreign slots
  inside/outside count survive. Success transfers all objects once and disarms
  local free eligibility. No claimed concurrent-writer solution via equality.
- Actual root pre-DT error gate reaches topology exit, never generic free_priv
  or later resources. Success after preparation stops at the first DT consumer
  in the native model; no whole-root successful-init qualification follows.
- Independent complete stdout/action/owner oracles; precise clean-compiling
  source mutations and old-code witnesses must exit86 with empty stdout and
  one exact named diagnostic. Compiler/timeout/signal/sanitizer is not semantic
  negative credit. Strict GCC and Clang ASan/UBSan with activation controls;
  LSan unqualified. All input/asset/generated/tree identities rechecked at end.
- Independent source/admission and test-quality review. Target, kernel RCU,
  real work/IRQ/hardware/module runtime and performance remain unverified.
