# 049 Shared PHY Ops Contract

Authority: the user's 2026-11-03 bounded implementation authorization. Production
scope is a new 049 patch modifying only src/hsl/phy/hsl_phy.c and
src/hsl/phy/aquantia_phy.c at exact d9a1964 plus the reviewed 36 layers. No package
release, 048, CI, old test, build repository or root-fatal policy change is owned
by this task. Parent maintains release27/profile37 and pipeline provenance.

Registration borrows, never consumes or frees an ops object. Invalid enum values
(including negative), NULL, and malformed getter metadata are rejected before
indexing. Empty/same-object registration succeeds; another object returns
SW_BUSY without replacement. Stale/empty unregister returns SW_NOT_FOUND;
matching live unregister returns SW_BUSY because raw readers have no drain API.
phy_api_ops_init is non-destructive empty-slot admission, not a reset/free API.

A static, fully initialized Aquantia table lasts for the SSDK module lifetime.
Original callback mappings and all IN_PORTCONTROL_MINI guards are retained. No
once-latch, heap allocation or runtime table rewrite remains. Registration must
succeed before hw-init, and its first error or the hardware error is returned.
Outer ssdk_phy_driver_init/root error handling is deliberately unchanged.

A static IRQ-safe lock protects short registry pointer operations only. It is
released before callbacks. Getter metadata NULL/port/type checks are sequential
admission, not protection against concurrent phy_info destruction. Per-device
cleanup validates the device, keeps existing local exit predicates/order, clears
only that device's discovered bitmaps and frees only that device's metadata.
It never clears/frees a global ops slot or retires a peer.

Native validation uses actual whole functions/types and independent field/case
oracles, full/MINI and I2C off/on profiles, explicit borrowed-owner controls,
competing publishers, exact runtime mutants and separate old counterexamples.
The two old PHY witnesses become positive repaired contracts, not mechanical
edits of their old expected status. UK remains OPEN. Exact evidence and counts
are in the fresh RESULTS.json files; no pre-run PASS is claimed here.

Blocked from this patch: live unregister/replace/free, full bare-reader leases,
metadata retirement, foreign provider module lifetime, full root-init rollback,
global sharedUK/SD cleanup and router/target acceptance. In particular no new
global final-free or last-device refcount is inferred from discovery bitmaps.

## Host activation correction after run41567115773

The cloud failure was a test-probe assumption, not evidence of a target PHY
fault: the dual-sanitized heap probe first raised GCC11 UBSan object-size,
not the required ASan heap diagnostic. Its status stays INCOMPLETE. The runner
isolates address and undefined probes while the real-source campaign retains
both sanitizers, precise semantic negative oracles, all four profiles and the
fixed 68/80/8 obligations. Probe identity and exit97/98 are checked together;
disabled and crossed-identity controls earn no SDK mutation coverage.

The separate native canary regression records actual compiles/runs and result
pollution controls. Current local validation does not replace Linux GCC11,
target-toolchain, final firmware or runtime acceptance. No production patch,
recipe, vendor pin, build lock or performance setting is changed by this test
correction. The next candidate's newer I2C/TUNIP production changes require
their own reviewed CI admission and may not silently use the old37 profile.
