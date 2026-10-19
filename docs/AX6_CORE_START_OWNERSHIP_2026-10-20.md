# AX6 core startup ownership, r18 local candidate

Patch 999-952 follows the complete mac80211 package patch order after 949-951.
It changes core.c only in the prepared tree. No firmware, API ABI, NSS offload,
ring sizing, IRQ affinity, RPS/PBUF, country or channel settings are changed.

## Defects and repair

1. DBS setup failure occurs after MAC allocation and REO setup. The old jump
   bypasses both cleanup stages. Route this error through REO cleanup.
2. During registered recovery, mac_allocate and mac_register return success
   without acquiring new MAC ownership. core_start, pdev_create and the outer
   firmware-ready error chain used to destroy/unregister those retained objects.
   Capture REGISTERED under the existing caller's core_lock and unwind only
   ownership acquired by this call.
3. thermal_register also returns early when REGISTERED. Do not unregister a
   skipped thermal registration after spectral failure. This prevents a duplicate
   cleanup; it does NOT restore thermal devices removed earlier by crash recovery.

The only REGISTERED writes in the prepared ath11k tree are in the QMI event
worker, after successful firmware_ready. Registered recovery uses restart_work;
core_start and pdev_create are called only by firmware_ready under core_lock.
These observations bound this local fix; they do not establish a general
QMI event/remove concurrency contract.

IPQ8074 has single_pdev_only=false. The DBS correction is a shared-driver
compatibility repair, not evidence that this branch caused AX6 throughput loss.

## Verification

- Four actual prepared core functions, with child/Linux resource APIs modeled.
- 768 scenarios, 6016 assertions, zero failures: GCC16 and Clang ASan/UBSan.
- Old source: 224 assertion failures. Five compiled negative controls fail
  16/144/32/16/80 assertions. No compiler/sanitizer failure counts as a negative.
- Identical normal-success event signature; clean modeled rollback permits retry.
- Full package patch replay, zero fuzz and no added orig/rej files.
- Existing 14 regression groups pass on that same prepared tree.
- Earlier DP/SRNG tests are reused only where their recorded source/asset bytes
  are unchanged. This is not a new target build or DMA qualification.

Final evidence: Review-AX6/audits/20261019/core-start-ownership, especially
gcc-qualified/RESULT.json, asan-qualified/RESULT.json, REVIEW.json and PREFLIGHT.json.
Initial malformed diff / offset refresh, missing local GCC15, and the first
mutant's unused-variable compile error are retained as failed attempts; only
the exact refreshed patch and final test assets are qualification evidence.

## Cross-check and limits

Official Linux c03c1a14507dfaf8b856c2608f9ac216021fc222 core.c and thermal.c
are saved with Git blob and SHA256 binding. The DBS error jump also exists in
that primary source. Its different MAC lifecycle is not copied wholesale into
the NSS fork. This patch is Pending, not an official upstream accepted fix.

Still OPEN: thermal restoration after registered recovery; child NSS partial
startup/teardown; CE partial init; registered plus QMI_FAIL/remove; coldboot
calibration timeout/restart policy; real scheduling and hardware DMA; SSDK/DP
reset epoch and IRQ-off performance; rpcd durable recovery and LuCI integration.

The successful cloud run39237618912 contains r15, source60a65bf159/buildd605724.
Its independent final artifact acceptance does not cover local949-952/r18.
No push, new build, hardware access, merge, release or flash is authorized here.
