# External switch consumer admission

Local successor to source905f1a183c, SSDK release26, exact selected vendor
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus36 patches. The completed cloud
run41431765828 is source905f/SSDK25 and does NOT contain this repair.
No source/build push, target/firmware/cloud build, main/Release or device
action is part of this local batch. The build lock remains frozen.

## Fault and bounded change

The global external table is zero-initialized. Lookup by port or device
previously matched only the key and could return an unconnected zero-key
slot. A stale unconnected slot could also hide a later connected match.
The notifier publisher independently scanned the indexed table and could
acquire an external-slot netdev reference for an unconnected matching key.

048 requires switch_connected in both key lookup functions and skips an
unconnected slot in ssdk_netdev_switch_init. The primary PHY cache is still
registered when appropriate; absent external metadata retains SW_NOT_FOUND.
Do not turn that status into failure to retire a legitimate primary cache.

Indexed access, allocation, identity-based cache removal and all-slot
retirement sweeps remain unchanged. They must still be able to retire old
owned references, including a cell whose metadata is no longer connected.
Connected device/port zero and the first connected matching slot stay valid.

## Exact source and upstream comparison

The two old lookup functions are byte-identical to the selected CodeLinaro
Git object's functions. Current consumers are qca_mii_reg_accessible,
ssdk_switch_netdev_get, ssdk_switch_set_standby_status and MPPE athtag setup;
they already handle a missing result. The additional publisher uses indexed
access, so fixing only the lookups would miss it.

The divergent openwrt/qca-ssdk bb4f3f0b947ebfce51c78a8d39f57c7c758521c9
reference does not contain the same external helper family. It is not a
linear ownership fix to transplant wholesale. This check is not a census
of every current upstream commit or proof of external module contracts.

## Verification

- Fresh exact36-layer text preparation:692 files. Only ssdk_dts.c and
  ssdk_plat.c change; replacing the three complete functions with their
  old definitions restores every original byte. All35 prior patch hashes
  are unchanged.
- Verified native GNU patch2.7.6/2.8 both replay all36 layers with zero
  offset/fuzz and produce identical692-file trees. Reversing048 recovers
  the exact35-layer baseline. No artifact executable was used as a tool.
- Actual native lookup functions and actual external slot type: GCC16
  and Clang17-ASan/UBSan,8192 layouts/queries each,16 precise runtime source
  mutants plus the old zero-key witness. Unconnected stale entries, later
  connected entries, connected zero keys, duplicate keys, missing and wide
  keys, unchanged foreign fields and exact pointer identity are covered.
- Actual current cache C with the established allocation/value model:
  both compilers each run5 modeled profiles x35 scenarios=175 positives,
  the original32 exact mutants plus old-publisher and inverted-guard
  witnesses=34 negatives. The profiles are NOT five target chip builds.
- Previous MDIO admission:1200001 scenarios/11 precise mutants under
  Clang-ASan/UBSan. Three actual-function shared PHY/UK risk witnesses
  still report KNOWN_OPEN_NOT_REPAIRED; they are not repaired by048.

Evidence:
/Volumes/FX-MD87/Review-AX6/audits/20261102/external-lookup/
REPAIR-QUALITY.json and FINAL-REGRESSIONS.json bind the text scope and
raw process results. Earlier failed draft fixtures/preparations remain
INCOMPLETE, not counted as successful negative controls.

## Not closed

switch_connected is not a reader lease or atomic publication protocol.
The parser still sets it before every external property has been parsed.
This repair does not validate optional property defaults, device domains,
root metadata transactions, MDIO provider ownership, I2C allocator ABI,
shared PHY ops retirement, UK/SD last-holder ownership or hardware quiescence.

Before a new build, integrate a reviewed36-layer fixed CI source contract,
the new tests, recipe release26 and a new real source commit/build lock.
Do not relax the existing35-layer hashes or use the successful old image
as validation of the new local functions. Real kernel/target ABI, boot,
latency/loss/throughput and performance qualification remain open.
