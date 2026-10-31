# PHY port admission and local OF retirement

Base470b10dfeb8bdab1a76dd6deb48a3ad3948f1918; exact SSDK
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus23 patches/recipe13.
No make/target/module/firmware/cloud build, push/main/Release or device.
Only fresh native host fixtures and current-repo pure source preparation.

## Contract and change

Same fresh serialized selected obj-m/static-DT contract as035. Before any
topology/private allocation or MDIO/SFP/platform/FAL registration, validate
the enabled switches' available qcom,port_phyinfo children. Missing container
retains optional legacy MDIO fallback, empty container remains valid; retain
the original child filtering even if the container itself is disabled.

One private typed read helper serves pure admission and actual PHY parsing.
port_id retains the original single-u32 first-cell/long-property tolerance;
reject missing/short or id>=actual SW_MAX_NR_PORT16 before BIT/metadata/GPIO
arrays. Preserve port0/15 and duplicate iteration order; do not invent ID==
ordinal or dedup policy or confuse physical-port7/virtual-port capacities.
Optional phy_dac needs the original two-cell prefix when present; preserve
long prefixes and actual phy_dac_t's u32-to-u8 conversion, not a new255 clamp.
Publish the small output record only after all reads succeed. Actual parsing
reads the same helper before per-port effects, then applies DAC at its original
setter position. Not an atomic property snapshot or dynamic-writer rollback.

Pure traversal owns only its container and iterator references. Next iterator
consumes prev; explicit error puts current child, then container. Actual parser
routes normal/existing/new early errors through one local container/iterator
exit, without freeing bus/provider/adapter/global PHY/FAL resources. These
local puts do not prove every other node/bus reader or owner retired safely.

## Required verification

- Exact23->24 derivation,692 files, declared coordinates/context/no fuzz or
  offset; intended DTS only; unique recipe13->14, pin/build lock unchanged.
- Complete actual new helper/traversal/prepare caller and selected PHY parser
  bodies; actual SW_MAX_NR_PORT/phy_dac_t/error constants. Reduced OS/large
  structs and service leaves explicit, never target ABI or full subtree proof.
- IDs0/15/16/max and missing/empty/short/long; DAC absent/empty/short/exact/long,
  >255 conversion; typed errors preserve output. Disabled children, absent/
  empty/disabled-parent containers, duplicate IDs, later child/switch failure,
  repeated calls. Errors precede root allocations and resource registrations.
- Exact temporary-node ownership/from-consumption/retirement on each success
  and early exit; foreign/provider refs unchanged. Actual caller order and
  original valid setter values/order have independent complete model oracles.
- Clean compile then exact86/empty stdout/unique named semantic-negative
  stderr. Crashes/compiler/sanitizer/timeout never count; old unsafe boundary
  witnesses and weak-harness controls separate from production mutations.
- Memory-oracle expected/source/JSON hashes, precise inventories and complete
  tree/input/generated tail gates; source receipts only data, never execute
  old sealed programs. Fresh GCC/Clang ASan/UBSan activation, LSan unqualified.
- Independent source/compatibility/test quality review before local commit;
  old035/PHY/root qualifications do not automatically cover current24 layers.

## Still open

Legacy MDIO fallback raw-reg/compatible extents, optional I2C-address failure,
MDIO add/default errors, SFP/adapter/bus/provider ownership and unknown QCOM
allocator API, external-switch/other OF refs, LED/QoS bounds, shared driver/
UK/PHY ops, platform/clock/FAL rollback, SDK/Linux error-domain handling,
whole-root/private combination, real kernel/OF/IRQ/RCU/FW/DMA and performance.
Ordinary static port/DAC errors stop at pure admission; not every parser error
is thereby made fatal/reversible. No performance knob or hot-path change.
