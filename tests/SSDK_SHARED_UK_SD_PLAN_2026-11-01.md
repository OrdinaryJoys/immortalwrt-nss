# Shared UK / SD bootstrap ownership and staged repair

Base: 86a7a91129549b70b92b758d57fcc69762aac9b8, exact SSDK
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus28 patches, release18.
Candidate branch codex/ax6-uk-transport-lifecycle-20261101. Build checkout
2bcafb435bb316da0f74da1f6ec0817020201ed1 and its old lock remain frozen.
No make, target/module/firmware/cloud build, push/main/Release or device
access. Only exact text preparation and fresh isolated native host tests.

## Ownership facts and unresolved boundaries

- HSL's function-static dev_init is not a per-device acquisition ledger.
  SD, UK and optional API lock are initialized once, before outer cfg
  allocation and child construction. Failed prefixes are not compensated.
- Every HSL cleanup currently calls shared UK cleanup, even for an empty
  slot. The first cleaned device can retire an endpoint used by a peer;
  dev_init remains set so later reinitialization can skip reconstruction.
- SD publishes twelve global typed function pointers. They are borrowed
  callbacks, not heap objects owned by a device. NULL fields retain prior
  values. It is unsafe to free callback targets or blindly zero/restore
  them during a peer's retirement. Root configs can contribute optional
  PSGMII/uniphy fields; a first-vector-only equality rule needs proof.
- API lock is one global mutex with no destructor. Last-device retirement
  must not destroy or reinitialize a mutex while readers can use it.
- The actual linked UK backend is ioctl, not the legacy netlink file.
  In-tree ioctl command tables do not wire SWITCH_INIT to an init/cleanup
  function merely because a numeric constant exists. Reset is a separate
  operation. External kernel callbacks remain outside this caller census.
- Linux v6.18 drivers/char/misc.c takes misc_mtx around f_op->open.
  misc_deregister unlinks the endpoint but does not close/drain old file
  descriptors. Module pinning is not explicit in-module cleanup safety.

## Phase 041a: independently bounded transport transaction

Repair the ioctl backend only before connecting a new shared coordinator:

1. Two module-lifetime static mutexes; never destroy/reinitialize the
   command mutex. Lifecycle entry uses nonblocking acquisition of both
   lifecycle and command locks and returns SW_BUSY unchanged on contention.
   This also rejects synchronous reentry from an executing command.
2. OFF -> STARTING -> READY and READY -> STOPPING -> OFF. Keep the new
   buffer private until misc_register succeeds. Failed allocation/register
   frees only private resources, does not deregister a foreign endpoint,
   consumes no successful epoch, and permits a real retry.
3. Never call misc_register/deregister while holding the command mutex:
   misc_open takes misc_mtx first, then our command mutex. Open and both
   ioctl paths reject unpublished/stopping endpoints.
4. Every successful open owns a small context containing the successful
   endpoint epoch. Both native and compat ioctls check READY, buffer and
   matching epoch under the same mutex held through real command dispatch.
   Old descriptors cannot operate on a replacement generation; release
   frees only their context. Successful epochs never reset or wrap.
5. Same effective protocol initialization remains idempotent (not an
   acquisition/refcount). A conflicting protocol is rejected. UK_MINOR_DEV
   overrides incoming nl_prot, including the AX6 minor254 profile.
6. Cleanup refuses an active command without changing any state. With the
   command mutex acquired, STOPPING rejects later commands before unlink
   and free. Old contexts remain valid allocations until their file closes,
   but cannot address retired/replaced command buffers.

This is NOT last-device ownership, child-reader retirement, SD rollback,
FAL/root error propagation, generic legacy netlink repair, general ABA,
cross-module stale-handle protection or a runtime/performance claim.
In particular HSL currently retires children BEFORE calling UK cleanup;
SW_BUSY here does not make that outer order safe. C01/C04 remain OPEN.
Do not connect a counter to the old unconditional cleanup and call it done.

## Phase 041b: coordinator required before closing C04

Before further production edits, independently verify these contracts:

1. A global reservation must cover admission BEFORE FAL/API metadata or
   child mutation and stay held through the outer FAL continuation. Reject
   conflicting peer/reentrant entry without granting an ambient bypass.
   Define all reader gates, including direct API clear and SD consumers.
   Audit sleeping/atomic execution context before selecting reader locks;
   do not wrap every exported FAL/SD read in a sleeping mutex by default.
2. Record per-device actual acquired stages, separately from fully ready
   state. Child failure after prefix acquisition must either compensate
   exactly its prefix or retain a retryable owner, preserving first error.
   Root discovered-device counts are not successful-holder counts.
3. An explicit owned endpoint identity must distinguish HSL-cohort
   retirement from direct/foreign sw_uk_init/cleanup callers. A nonNULL
   buffer, chip name or matching minor does not transfer retirement rights.
4. SD requires typed compatibility checks and a borrowed-provider lifetime
   contract. Preserve baseline owners, allow or reject NULL-fill according
   to actual multi-device configs, and never overwrite a conflicting live
   callback. State whether contributions last until cohort retirement.
5. On cleanup, stop/drain controls BEFORE child/API/SD retirement. Failure
   retains ownership and retry state. Only the actual last successful
   holder may retire the shared endpoint and owned publication; do not
   release peer state when an empty/unowned slot is visited.
   HSL cleanup returns before FAL's optional VLAN cleanup, and ssdk_cleanup
   calls PHY retirement afterwards. A child-only success counter cannot
   represent these remaining stages: retain an explicit pending lease
   through the real dependency boundary rather than withdraw SD/UK merely
   because the HPPE child or outer cfg has just been freed. Determine actual
   remaining users before assigning the final coordinator commit point.
6. Initialize the optional API lock at most once for its actual lifetime.
   Generic external providers, direct SD readers, whole-root acquired-abort
   and root errno domains need their own proof, not inferred quiescence.

## Verification requirements

Replay all existing28 plus the one new patch at exact declared context,
zero offset/fuzz/rejects; compare every output and all old patch identities.
The only intended prepared change in041a is sw_api_ks_ioctl.c.
Use fresh native host fixtures with kernel/allocator/misc/usercopy models
explicitly labeled, actual production parser/dispatcher/native+compat
paths, constant and dynamic minor profiles, allocation/register failures,
publication hooks, synchronous reentry, successful retry, active-command
cleanup rejection, both old-FD paths across reinit, epoch exhaustion,
and context ownership. Include true source semantic negative controls
that compile successfully and fail a precise assertion, not compile errors.
Host mutex models are not real kernel lockdep, scheduling, modpost or ABI.
Review source, tests and evidence independently before accepting this scope.

## Primary references

- Exact recipe CodeLinaro pin, read from local primary Git object cache:
  https://git.codelinaro.org/clo/qsdk/oss/lklm/qca-ssdk.git
- https://raw.githubusercontent.com/torvalds/linux/v6.18/drivers/char/misc.c

The CodeLinaro web fetch was restricted and the GitHub blob page returned
404 in this session. Exact local Git objects remain the source comparison;
do not claim a successful remote CodeLinaro fetch or all-upstream approval.
The read-only openwrt/qca-ssdk HEAD observation bb4f3f0b947ebfce51c78a8d39f57c7c758521c9
is not permission to change the selected release train or merge it.
The exact pin is NOT an ancestor of that HEAD. The selected SD, ioctl and
API-lock file bytes are identical across those two objects; HSL differs in
chip/legacy dispatch composition (including MRPPE stripping), not a shared
bootstrap ownership fix. This is a divergent reference comparison, not an
available safe linear update or evidence of no faults elsewhere upstream.

## Additional conditional risk found during review

API_LOCK combinations need their own target review: hsl_lock.c defines
sw_hsl_api_lock as aos_mutex_lock_t, while hsl.h declares aos_lock_t in
its API_LOCK plus combined/standalone condition. The Linux backend maps
these to mutex versus spinlock. This predates041a, is not enabled in the
selected AX6 default profile, and was not corrected or target-compiled
here. Do not classify it as a proven active router fault or cover it with
a reduced host stub. Whole-coordinator design must resolve that contract.
