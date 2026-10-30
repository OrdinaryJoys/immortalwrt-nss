# SSDK count admission before fixed-capacity writers

This phase starts at81cefc88bf4bf91a64892b985282b14543a7a68a. The earlier
A1/A2 phase is accepted only in its separately recorded bounded scope. This
phase may not reuse old native PASS as current qualification. No make, target,
module/firmware/cloud build, push/main/Release or device access is permitted.
New native complete-function fixtures and pure source preparation are allowed.

## Source contract and fix boundary

The actual pinned SSDK sw_config.h sets SW_MAX_NR_DEV=3. phy_info, port_bmp
and each PHY driver's port bitmap have that fixed capacity. regi_init calls
ssdk_alloc_priv(count) before parsing any switch node. That function calls
qca_ssdk_port_bmp_init and qca_ssdk_phy_info_init for each slot, without a
count-capacity guard. A parser-only device-ID check would therefore be too late.
This inherited conditional source defect is not an observed AX6 runtime fault.
Selected AX6/stock text uses count1 and compatibility ID0; no live DTB was read.

033 will reject dev_num > SW_MAX_NR_DEV before the first topology allocation
or publication, after typed OF read and its reference release. Use the actual
capacity macro, not a board-specific literal or an assumed performance limit.
The existing regi_init earliest error barrier then returns the Linux -EINVAL
before private/PHY/platform/FAL resources or global controls. No cleanup is
necessary or newly invoked on that pre-owner error.

Preserve zero, missing-node/property defaults, counts through the capacity,
existing-owner -EBUSY priority and malformed-property error priority. This
does not certify all those counts for every board, zero-device root behavior,
multi-device shared UK/PHY ownership, duplicates/sparse IDs or dynamic DT.
Do not normalize invalid count, invent a new device ID, alter disabled policy,
route any new error to normal exit, or add parser/fatal/FAL cleanup changes.

The earlier A1 isolated topology tests used count7 only as an allocator-boundary
model, not a promise of whole-SDK support. This new evidence-backed capacity
policy intentionally supersedes that old isolated acceptance for count>3.
Keep its old source and FAIL/PASS records unchanged, not silently relabeled.

SSDK release10->11 invalidates future package caches; DP stays9 and all driver
pins, build locks and performance switches remain unchanged. Bind new21-layer
source exactly to old20 plus033, with strict whole-tree output. Historical
recipe exception must prove the unique10->11 line through the full old hash;
the current21 receipt matches all live inputs without an exception.

## Required verification

Read exact upstream constructor/caller/array declarations and sw.h includes;
independently review the actual increment. Fresh native fixtures extract the
complete actual DT init/exit/get and root early barrier, preserving explicit
native allocator/OF/structure models. Compile the real capacity macro value,
not a separately guessed one. Test0/default/1/2/3, every admitted allocation
failure, >capacity/7/UINT32_MAX rejection before any allocation/publication,
OF balance, foreign owner preservation, malformed-property priority and root
exclusion from private/controls. Late private/FAL/PHY leaves remain fail-fast.

Use independent full positive ledgers and clean-compiling old-source/runtime
mutations with exact named86/empty-stdout/unique-stderr rejection. Compiler
errors, signals, timeout and sanitizer findings do not earn semantic-negative
credit. Run GCC and Clang ASan/UBSan with activation controls, strict warnings,
input/tree/asset end hashes and a separate independent source/test review.
No LSan, Linux concurrency/RCU, target ABI/link, real module/hardware, throughput
or whole-root rollback qualification follows. Other old20/cache/FDB/DP
qualifications remain at their exact original source inputs.
