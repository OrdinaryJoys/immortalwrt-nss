# SSDK DT admission before resource registration

Base093f38f0ec1213786b555cd652eacc30430835ab; exact SSDK
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus22 patches. No make,
target/module/firmware/cloud build, push/main/Release or device access.
Fresh host function fixtures and current repo pure source preparation only;
historical audit files are data, never executable qualification shortcuts.

## Contract and ownership

Selected fresh serialized obj-m root: topology/private destinations empty,
no earlier admitted consumer or concurrent module teardown. This is not a
builtin/live-reentry or atomic whole-device-tree snapshot protocol. The
selected source disables OF overlays, but arbitrary external OF writers are
not thereby proven absent. Cache validated per-node inputs rather than
re-reading an ID/reg after partial driver initialization.

Under the same CONFIG_OF and >=3.14 guard as the original parser, prepare up
to actual SW_MAX_NR_DEV nodes on a small stack ledger before any topology or
private allocation, MDIO/SFP, clock/platform/FAL/driver registration. Keep the
existing global name lookup and from-reference consumption; do not add an
extra put of the consumed ess-instance reference.

Missing device_id keeps the original0 default. A present property must contain
one u32 cell and pass typed reading; IDs must be in both dynamic count and
fixed capacity. Reject duplicate enabled IDs while allowing valid permutations.
Disabled nodes remain skipped, with no reference escaping the failed lookup;
malformed properties on disabled nodes are not newly consumed. A missing
declared node is an admission error, not permission to reuse a previous ID.
Count0, missing instance/default count1, non-OF and old parser guards retain
their bounded prior behavior; no arbitrary topology is declared board-supported.

Read switch_access_mode and its original required reg prefix into a small
private access record. Local bus requires2 cells, PCIe1; typed reads reject
short/empty data. Larger reg properties retain the old consumed prefix.
Unknown access strings still select MDIO; do not silently re-interpret address
cells, add request_mem_region, or change the normal register map.

The temporary ledger owns every successful node lookup until all validation
and topology allocations succeed. Errors release only its references and
allocated local topology cells/vector, preserving errno and foreign globals.
No generic PHY/FAL/MDIO/clock cleanup is eligible during this pure stage.

After all fallible work, transfer each reference and validated access record
to the existing topology cell indexed by validated ID, consume the local
pointer, and publish a private static name-index->ID/enabled map before the
complete global topology. Do not change public header/struct layout. Existing
cfg.of_node owns the reference; private.of_node and getters only borrow it.
The parser uses the admitted node/ID/access without a second lookup/raw decode.
Final topology exit releases its owned references once and clears admission
metadata at its existing root retirement position. A node reference does not
make all downstream services, raw readers or normal cleanup lifetime-safe.

## Verification required before local commit

- Exact22->035 source derivation, all692 files, declared coordinates/no fuzz or
  offsets; only the intended DTS source changes. Recipe12->13 only, pins and
  build lock frozen. Old22 recipe exception requires the full historical hash
  after exactly the unique release-line reversal; current23 is strict.
- Complete actual helper, lookup, prepare, init/exit/parser bodies and actual
  enums/constants. Explicit reduced Linux/topology/consumer models are not
  target ABI or full parser-subtree execution. No synthetic enum numbers.
- Missing/present device_id lengths, every dynamic/fixed bound, duplicate and
  permutation IDs, enabled/disabled/missing node combinations, default/zero
  counts, local/PCIe/MDIO modes and short/long reg prefixes. Validate every
  allocation-failure position for counts0..3 and both fallback branches.
- Track OF from-consumption, every local/adopted reference and every memory
  identity; no failed lookup owner escape, double put, foreign cleanup,
  forgotten adopted reference or partial-global publication. Borrowers do not
  acquire or retire a second ownership claim.
- Parser observes admitted ID/access after modeled property mutation, performs
  no second ID/access lookup/read, and reaches only explicit modeled leaves.
  Root early failures do not reach private/driver stages; a modeled private
  failure reaches its actual dedicated topology exit. If the actual private
  allocator is a leaf, no complete23-layer PHY qualification is inferred.
- Independent complete action/owner/argument/value oracles, exact full stdout,
  clean-compiling runtime source mutations and safe old-code witnesses. Each
  negative needs exact86/empty stdout/one expected marker; crashes, compiler
  errors, sanitizer diagnostics or timeouts get no semantic credit. Include
  controls that reject polluted output and prove a removed admission/owner
  assertion would otherwise accept the wrong state.
- GCC and Clang ASan/UBSan with activation controls; LSan unqualified. Bind all
  test assets, helpers, receipts, profile expectations and generated files;
  recheck all inventories/tree/input bytes at end. No mutation of a sealed
  evidence program. Independent source/compatibility and test-quality reviews.

## Explicitly still open

Full MDIO/I2C/SFP/property sub-parser bounds and ignored errors, dynamic OF
reconfiguration, clock/platform/FAL partial-init compensations, shared UK/PHY
ops, SDK versus Linux error-domain handling and normal/post-DT reader retirement
remain separate work. Admission removes ordinary ID/access DT validation errors
from the partial-driver phase; it is not a new universal root abort mechanism.
Target link/modpost/ABI, real OF/work/IRQ/RCU/FW/DMA, device and performance are
not tested or changed by this phase.
