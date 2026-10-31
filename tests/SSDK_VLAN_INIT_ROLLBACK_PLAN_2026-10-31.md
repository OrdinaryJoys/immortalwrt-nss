# SSDK software VLAN-cache construction transaction

Base e6f95934b573d911a49a00e1a364d1f8afaa1fed, exact SSDK pin
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus24 patches, release14.
No make/target/module/firmware/cloud build, push/main/Release or device.
Only exact source preparation and fresh isolated native host fixtures.

## Scope and ordering

SSDK-ROOT-ERR01 cannot safely be repaired by an early return alone: partial
FAL/HSL/PHY/platform owners and SDK/Linux error domains remain open. HPPE
constructor and shared-bootstrap ownership are being reviewed separately.
This increment fixes the independently bounded FAL-C02 constructor only.

fal_vlan_init obtains a pool (two allocations), DB and fixed-node list.
DB/list failure currently retains earlier published allocations. Construct
all three objects privately; free only this attempt's successful allocations
in reverse acquisition order on failure; publish the three pointers only
after all allocations and zeroing succeed. Preserve original pool/list
SW_FAIL and DB SW_OUT_OF_MEM results and helper-internal pool abort.

Keep the original hsl_dev_ptr_get/NULL, hardware-query bypass and 1..4096
capacity admission order. A software-cache slot with any pre-existing pool,
DB or list is not owned by this attempt: return SW_ALREADY_EXIST without
allocating, writing, freeing or resetting it. Do not call fal_vlan_cleanup
or fal_vlan_reset as failed-construction compensation. Preserve peers and
legitimate fresh success values, list ordering, callback identities and ID
capacity. Do not change fal_vlan_reset or any forwarding/runtime hot path.

This is a serialized, quiescent constructor contract, not atomic triple
publication, UK/readers admission, concurrent reset/reentry or root-wide
rollback. HPPE normally reports hw_vlan_query and allocates none of these
software-cache objects: passing that branch does not qualify software paths
and this change is not attribution of a current stock throughput fault.

## Required validation

- Exact24->25 patch derivation and complete692-file manifests, no fuzz or
  offset; only fal_vlan.c changes; unique recipe14->15, pin/build unchanged.
- Actual complete init/cleanup and pool/list constructors/destructors,
  relevant types/macros/error values, HSL bounds getter, actual comparison
  callback where practical. Model allocator/OS only, explicit exclusions.
- Fail every underlying allocation: pool header, pool inner, DB, list.
  Exact error, action order, identity, sizes, success publication and zeroing;
  no global partial publication observable from allocator boundaries.
- Every valid dev, invalid IDs, missing model metadata, hardware bypass,
  entry counts0/1/255/256/257/4096/4097/max, nonempty slot combinations,
  peer sentinel state, repeated failure/retry/success/cleanup and same-size
  foreign objects. Do not free borrowed objects just to make a model clean.
- Mutations must compile cleanly then fail with exact named semantic marker,
  not timeout/compiler error/crash/sanitizer credit; retain safe old-code
  boundary witnesses separately from current source mutants.
- Strict stdout/stderr/exit and independent expected-oracle checks, input,
  generated and source-tail hashes/exact inventories; Python -O and fresh
  GCC plus Clang ASan/UBSan activation. LSan remains unqualified.
- Independent source/compatibility and test quality review before local
  acceptance. Existing036 fixtures remain historical; do not relax their
  recipe/source gates to transfer qualification to25 layers.

## Open after this increment

HPPE/HSL config and port-info partial construction, borrowed/live same-dev
state, adapter/UK/PHY/global owners, FAL/root first-error and errno mapping,
concurrent VLAN readers/reset, complete root integration, other chips/DTB,
target ABI and actual kernel/FW/DMA/network/performance remain open.
