# PHY port admission host model

Run from the repository with a fresh output directory:

```sh
python3 -B tests/test-ssdk-phy-port-admission.py --cc gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-phy-port-admission/PORT-TEST-parent-gcc-r1
python3 -B tests/test-ssdk-phy-port-admission.py --cc clang --sanitize --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-phy-port-admission/PORT-TEST-parent-clang-r1
```

`--positives-only` is a development checkpoint, never full qualification.
Only PORT-TEST outputs are allowed. No make/target/module/firmware/device
build is performed. Historical audit programs/binaries are never executed.

## Source identity

Fixed SSDK d9a196497ecee2530722d906e0efe1b7408b6ef6, receipt23 d681a1b6,
receipt24 8714f974, frozen036 e6c4df5b and plan b85e9582. Both full receipts,
archive/pin/all692 upstream and prepared files, saved/current patch bytes and
inventories are checked. The current repo pure `edma_patch_context.py` is
hash-bound and applies all24 patches with exact coordinates/context/output,
no fuzz/offset. A second full-tree derivation proves24=23+036 and only
`src/init/ssdk_dts.c` changes. All other692-tree bytes remain bound.
The sole historical recipe exception reverses one complete release14->13
and must recover the full frozen13 recipe hash; current24 stays strict.
Extra patches are rejected, never ignored. End gates recheck all assets,
inputs, both saved-patch inventories, live inventory and all three692 trees.
This is snapshot stability, not an atomic filesystem lock.

## Actual Bodies And Models

Complete actual reader, validator, access/ID readers, switch lookup,
prepare-node caller, topology init/exit and PHY parser are extracted. Body
lines are not cropped or rewritten. Complete baseline23 parser is separately
name-renamed and freshly compiled for two instrumented boundary witnesses.
Extraction records carry paths/lines/hashes. Public a_bool_t/sw_error_t,
hsl_reg_mode, actual two-u8 phy_dac_t, feature enum/macros, address macros,
GPIO constants and SW_MAX_NR_PORT16 are actual text, not fake enums.
Linux unsigned scalar bases are modeled with uintN_t; public aliases are
actual declarations. This is not the installed kernel header graph/ABI.

Large cfg/private/global structures, allocation, OF, MDIO, I2C, SFP and hsl
setters are explicit reduced models. Setters guard device/port bounds before
array access; BIT guards before shifts. Access/force/c45/combo/feature leaves
record parameters and model the selected metadata writes, not hardware.
The GPIO/private model is always non-NULL. MDIO add succeeds with index2;
fallback MDIO lookup returnsNULL, switch_handle isNULL and external allocation
is a single explicit leaf record. Those are not full provider contracts.
CONFIG_MDIO_I2C is always off: unknown QCOM bus-creation API unqualified.
Four profiles toggle IN_PHY_I2C_MODE and IN_SFP_PHY independently.

Typed-array model returns0 on success; first-cell/long-prefix tolerance,
missing/no-value/short and injected typed errors are explicit. Typed leaf
errors use host errno constants (not a Linux errno-number ABI test), while
the actual negative SDK sw_error_t domain is extracted unchanged.

OF identities are checked before dereference. Child-next gets next before
putting previous; normal terminal child isNULL. Local early paths put current
child once and container once. `of_find_node_by_name` consumes from, including
the instance lookup. Disabled children are skipped, but disabled-container
status does not suppress its children. MDIO phandle is a real modeled get:
the preexisting parser's missing put is counted exactly as OPEN_MDIO_HELD.
External gets are likewise counted as OPEN_EXTERNAL_HELD. These providers'
retained references are NOT described as fully retired or repaired by036.
Only locally acquired container/iterator and topology-owned nodes are closed.

## Oracle And Negatives

Independent Python oracle emits the complete selected MODEL action/argument/
owner/field trace, not the driver's raw formatted logs. C buffers actions,
checks return/output atomicity/local references and topology owner shape,
then compares the whole expected file before emitting stdout. Runner requires
byte-exact stdout and empty stderr. Expected hashes come from oracle memory,
not file read-back. Metadata/all private GPIO cells, bitmaps, externally held
references and external leaf record are compared; repeated parse state is
preserved. DAC conversion uses u8 truncation, not clamp; its setter remains
at the original position after address/force setters.

Topology uses the actual complete pre-allocation gate and prepare-node caller.
Before vector indexing, exact live allocation identity/kind/count/size is
checked; before cfg payload reads, each slot's identity/kind/count/size,
uniqueness/closure is checked. Identical disabled cfg payloads cannot make a
slot swap/alias pass. All count0..3 allocation fault positions are exercised.
This is NOT regi_init, private allocation or full24 root+PHY integration.

Coverage includes ID missing/empty/1..3/4/5/8/12 bytes,0/15/16/max, typed
errors, DAC absent/0..8/12 bytes and >255 truncation, missing/empty/disabled
containers, disabled children/switch, duplicate ordered IDs, mixed later-child
errors, multiple/permuted switches, repeats, optional I2C success/failure,
SFP/force/GPIO/MDIO values and external allocation success/failure. Missing
container and three old/new early errors are checked for local retirement.

Candidate-source negatives compile cleanly, then require exit86, empty stdout
and exactly one specific SSDK_PORT marker. No timeout/signal/compile failure/
sanitizer report earns negative credit. Two complete-old-parser tests stop
before original out-of-bounds shift/index or raw-DAC prefix dereference:
instrumented safe boundary witnesses ONLY, not actual OOB/failure reproduction.
Separate iterator-order/MDIO-borrow/global-lookup-order harness pollution controls
do not count as production mutants. Global name lookup obtains the next node
before releasing from, matching the bound Linux6.18.38 reference
e46dc0adfe39724bcf52cea47b8f9c9aed86a394 drivers/of/base.c. This ordering model
does not implement the real global tree search, devtree lock or RCU semantics.
No unsafe/uninitialized mutation is run for credit.

Output-gate controls reject exit/stdout/stderr/marker/sanitizer pollution.
Tail controls reject modified/truncated/deleted/renamed/extra expected files,
extra generated files and nested rogue/RESULTS.json. Only this run's root
RESULTS.json is excluded. Exact generated inventory and expected inventory
are checked; fresh692 is separately revalidated. Debug output is opaque but
fixed-shape: optional currentbinary.dSYM must contain Info.plist and its
DWARF/binary, optionally only host Relocations/arch/binary.yml; other members
are rejected. No broad scan is used to silently bless unrelated output.

Flags are -Wall/-Wextra/-Werror/-Wformat=2; only -Wno-unused-function is allowed.
Clang ASan+UBSan activation requires separate97/98 diagnostic canaries;
normal ASan and UBSan both exit97 on diagnostics, environments are recorded.
Leak sanitizer is disabled/unqualified. No assert side effects are used.

## Open Boundaries

No real Linux OF/refcount/RCU/concurrent writer/target ABI or firmware/hardware
execution. No complete root/private/PHY combination, SFP/MDIO/bus/provider/
adapter/external-node rollback, unknown QCOM I2C API, dynamic property atomicity,
legacy fallback raw reg/compatible extents, shared ops or chip HW proof.
Setter values and model ownership are not performance/real-device diagnosis.
