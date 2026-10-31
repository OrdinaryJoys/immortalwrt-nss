# Software VLAN constructor transaction host model

Run from the repository, using fresh output directories:

```sh
python3 -B -O tests/test-ssdk-vlan-init-rollback.py --cc gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-vlan-init-rollback/VLAN-TEST-parent-gcc-r1
python3 -B -O tests/test-ssdk-vlan-init-rollback.py --cc clang --sanitize --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-vlan-init-rollback/VLAN-TEST-parent-clang-r1
```

`--positives-only` is a development checkpoint, never final qualification.
Only new VLAN-TEST outputs are allowed. No make/target/module/firmware/device
build, cloud, push or old audit binary/script execution is performed.

## Source Binding

Exact d9a196497ecee2530722d906e0efe1b7408b6ef6 plus24->25,037 hash46702234,
plan2a8ffcc4, source identity938857c4, base receipt8714f974, current receipt
c3956ae5. Full receipt/archive/pin, upstream/prepared692 and both saved/live
patch bytes/inventories are checked. Hash-bound current repo pure
edma_patch_context.inspect_patch freshly applies25 patches at their declared
coordinates with full context/output/no fuzz/offset. Separately prove all692
bytes equal base24+037; only src/fal/fal_vlan.c changes. Current recipe15 is
strict; the sole historical exception reverses one complete15->14 replacement
to the full frozen14 hash. Extra patches are rejected, never ignored.
End gates recheck assets/inputs, both saved-patch inventories/current inventory
and all three692 trees. This is snapshot stability, not an atomic lock.

## Actual Functions And Models

Complete actual fal_vlan_init/cleanup, sid_pool_creat/destroy,
sll_creat/destroy, hsl_dev_ptr_get, VLAN compare/dump callbacks, Linux
__aos_mem_alloc/free/zero and public aos_mem_alloc/free/zero wrappers are
extracted without body cropping. Baseline24 init is name-only renamed and
freshly compiled for safe old-code frontier witnesses. Extraction records
carry paths/lines/hashes. OS kmalloc/kfree and the scoped memset leaf are
models, not a replacement of pool/list algorithms. Original memset macro is
locally push/undef/pop preserved around only actual __aos_mem_zero.

Actual types include hsl_dev_t/nr_vlans u16, fal_vlan_t, v_array_t,
sid_pool_t, sll_node_t/head_t, actual callback signatures, a_bool_t/error/
HSL/compare enums, scalar aliases, aos_size_t (actual Linux signed int),
fal_pbmp_t capacity conditional, list flags and pool-width constants.
Linux unsigned scalar bases use explicit uintN_t host primitives. Independent
ctypes layouts are derived from actual small field declarations and checked
by C static assertions, not learned from native stdout. This is a host-layout
crosscheck, not installed target headers/ABI. The only manually declared HSL
table has the actual hsl_dev_t and SW_MAX_NR_DEV; actual bounds getter is used.

Valid HSL IDs always return a table entry in this source. Missing metadata is
modeled as zero-valued table metadata, not a fabricated valid-ID NULL getter.
Invalid3/max IDs test the actual NULL return. Input nr is converted through
the actual u16 field, including65536->0,65537->1,max->65535. HSL table bytes,
other-device slots and all borrowed same-size object bytes are preserved.
Hardware-query bypass happens before capacity/borrow checks and allocates
none of these objects; it does not qualify software allocation or chip HW.

## Allocator Contracts

Linux aos_mem_pvt.h actually requests kmalloc(GFP_KERNEL|__GFP_ZERO). The
linux-zero profile retains that actual wrapper and returns zero storage.
The separately named generic-poison-stress profile deliberately violates
that Linux zero guarantee to strengthen a generic allocator-contract check;
it is NOT stock behavior or evidence of a stock missing-zero defect.037
preserves every original explicit zero. Zero-call removal controls mean
exact source-action-contract mismatch in Linux-zero; any poison-content
failure is separately labeled NON-Linux strengthening, never device failure.

Logical frees are ledger events. Storage is quarantined until final checks
then physically freed, preventing address reuse from hiding stale identities.
This is NOT a physical UAF/free/kernel allocator test; sanitizer activation
does not change that boundary. Alloc/zero/free first validate identity, live
ownership, exact size and the pre-attempt complete global tuple. During
construction allocator boundaries must not observe any early publication.
These hooks do not prove atomic triple publication or concurrent readers.

## Oracles And Cases

Independent Python constructs the entire expected MODEL action/ID/size/
return/owner trace. Native buffers actions, checks semantic ledgers, compares
the complete expected bytes before stdout; runner checks stdout again.
Expected hashes derive from memory, not read-back-as-truth. Valid pool header
and inner IDs are checked before dereference by allocation identity/kind/
size/live status. Validate all ID entries and rounded zero tails, min/count/
width/ptr fields. List header/callback identity, every in-allocation node
identity before read, reverse free-chain order, zero data and NULL terminal
are checked. DB full byte extent is zero and belongs to the expected allocation.
Borrowed same-size objects and two peer tuples never become this attempt's
owners. Seven nonempty borrowed tuple combinations retain all pointers/bytes.

Every dev0..2, invalid IDs, capacities0/1/255/256/257/4096/4097 and u16
boundaries, all four allocation faults, retry/repeated init/cleanup, hardware
bypass with borrowed/invalid-count prestate and invalid-count-before-borrow
ordering are covered. Direct actual pool tests additionally cover65536/65537
width transitions and min37; direct list tests cover all four flag combinations
and zero/fixed/nonfixed nodes. Cleanup runs only for successful fresh owned
objects with valid dev, never invalid IDs or borrowed slots. No claim that
cleanup is universally safe for arbitrary partially owned global tuples.

Failure action oracle is exact: pool-inner fail frees header internally;
DB fail frees inner then header; list fail frees DB then inner then header.
Normal successful cleanup retains its existing order DB/inner/header/list,
then repeated cleanup does nothing. No foreign/borrowed writes/frees or normal
global cleanup/reset are used as failed-construction compensation; local
owned objects are freed in the failure order above. This is serialized/quiescent, not a
global UK/no-reader or root rollback contract.

## Quality Gates

Clean compile exit0 and empty stdout/stderr are required (-Wall/-Wextra/
-Werror/-Wformat=2, only explicit -Wno-unused-function). Native positives
require exit0/exact stdout/empty stderr. Directed semantic negatives require
exit86, empty stdout and exactly one named SSDK_VLAN marker. Timeout, crash,
compiler failure, signal and sanitizer diagnostic never earn negative credit.
Source mutants are separate from complete old-init safe publication/borrow
frontier witnesses (not target failure reproduction). The existing explicit
zero contract controls are separately classified. There are no assert side
effects; Python -O is recorded.

A separate harness control corrupts only the DB allocation-record kind.
The strong owner gate rejects before payload read. Weakening only that kind
gate accepts the same valid payload/trace. This tests ledger-shape quality,
NOT production mutation, a real wrong allocation or a claim that source
swaps would evade the whole trace. These model controls do not inflate source
mutant or positive case counts.

Output pollution controls exercise exit/stdout/stderr/marker/sanitizer gates.
Tail controls reject changed/truncated/deleted/renamed/extra expected files,
extra generated files and nested rogue/RESULTS.json. Only this run's root
RESULTS.json is excluded. Generated file inventory is exact; fresh692 is
separately verified. Optional currentbinary.dSYM requires Info.plist and its
DWARF/binary, permits only optional host Relocations/arch/binary.yml. Opaque
compiler bytes are hash-bound after shape checks; unknown members rejected.
Clang ASan/UBSan require separate97/98 activation canaries; normal runtimes
both use97 and actual env is recorded. LSan disabled/unqualified. Author
development runs GCC only; parent independent sanitizer results are separate.

## Open / Test P2

No real kernel memory/target ABI, HSL/provider/chip lifecycle, full root,
concurrent readers/reset/UK, atomic publication, HW/FW/DMA/performance or
stock-device fault attribution. No populated VLAN-list runtime forwarding,
sid allocation/free API or list insertion/search/deletion algorithm proof.
The ledger/shape oracle is a selected constructor contract, not whole-struct
kernel padding/ABI or every possible utility capacity/overflow proof.
Other FAL/HSL/PHY/adapter/shared-bootstrap owners and root error domains remain
outside this patch. Previous036 tests/qualifications are not inherited by25.
