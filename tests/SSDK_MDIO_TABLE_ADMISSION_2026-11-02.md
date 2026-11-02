# MDIO table admission and cloud snapshot boundary

SSDK047/release25 changes three complete ssdk_plat.c functions: miibus get,
add and index_get, plus their actual private-data getter in ssdk_init.c.
The getter now bounds IDs by both SW_MAX_NR_DEV and the actual topology count
used by ssdk_alloc_priv's kcalloc. A maximum-only check is insufficient when
that allocation has fewer entries. The table functions use this getter to
reject an invalid device, missing global table or absent device metadata.
Get also rejects an invalid bus index. Add rejects NULL bus/output before
table mutation. Index lookup rejects NULL bus instead of finding an empty slot.
Ordinary insertion, first matching-or-empty slot, duplicate and full-table
behavior stay unchanged. The getter is NOT a reader lease and does not pin a
provider, prevent concurrent metadata free or make add thread-safe.

The actual three functions and actual private-data getter execute in
test-ssdk-mdio-table-admission.py. Constants/public types are extracted from
the prepared headers. Bus/private structures are explicit host projections;
no provider allocator or destructor is fabricated. 1200001 scenarios cover
all 625 four-slot layouts, all eight metadata-presence masks, five device IDs,
global presence/absence, six query bus/index combinations, topology counts0
through3 and an extreme-index probe. The real count getter is also extracted;
DT state is an explicit host projection. Physical fixture slots remain three
entries so a missing logical count guard fails semantically, not by crashing.
Whole metadata/table/canary/provider snapshots and output ownership
are checked against a separate sequential oracle. Eleven compiled source mutants
must exit86 with the exact expected semantic reason; crash or compile failure
cannot count as a successful negative. GCC16 and Clang17 ASan/UBSan pass.

The known-valid cases preserve the old API policy. Invalid inputs and absent
metadata now have explicit failures. The guard intentionally does not add
provider put/unregister/free, alter upstream pins, clear published external
metadata or claim shared-lifecycle completion. The first text hunk-count typo
and first ambiguous test mutation were rejected and retained as incomplete
local evidence; final corrected runs are separately identified.

The cloud candidate includes locally reviewed DP019 and SSDK044 through047,
not an upstream wholesale merge. Its fixed build-repository profile binds
the exact recipe/patch/test/prepared bytes. Full reviewed source files are
copied into fresh directories; reversing only known new patches, with
full-result inventory hashes, reconstructs DP18 and SSDK31/32/33 baselines.
The original runners then execute their real old witnesses as well as all
current positive/negative cases. No empty stub or skipped baseline is used.
The existing EDMA profile changes only to the reviewed19-layer identity;
its six TX/IRQ/NAPI source inputs and old18 patch prefix are identical.

This is staged argument/OF repair and compilation validation, not a complete
MDIO/I2C rollback or shared UK/SD/PHY fix. Missing contracts remain explicit:
mixed lookup-ref/borrowed/owned bus entries, adapter lifetime and the actual
QCOM allocator implementation, duplicate/full insertion cleanup, per-port
partial metadata publication, ignored bus/SFP errors, global UK ownership,
twelve SD provider callbacks and shared PHY ops reader/last-holder retirement.
Do not blindly release a bus/ops table, add a cohort counter without reader
admission/drain, or reinterpret generic Linux rules as a vendor protocol proof.

Source preparation is35 layers/692 files at the unchanged vendor pin.
No real kernel concurrency, FW/DMA, root017/018 integration, device loss,
bidirectional throughput or highest-performance qualification is supplied.
Cloud success will not authorize flashing, reboot, Release or main merge.

Fresh evidence is under:
/Volumes/FX-MD87/Review-AX6/audits/20261102/mdio-table-cloud/

Earlier9/13/17-file local receipts stay historical and are not rewritten to
qualify new test/production inputs. Read-only original bytes are retained.
