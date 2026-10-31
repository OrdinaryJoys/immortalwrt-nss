# HPPE fresh ownership and local constructor rollback

Base ea1f786c279c0fc273ece6b30f0c8d8ca8951e63; exact SSDK pin
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus26 patches/release16.
No make/target/module/firmware/cloud build, push/main/Release or device.
Only exact text preparation and fresh isolated host C fixtures are allowed.

## Admission And Ownership Contract

This is serialized, quiescent per-device construction/retirement, not a
concurrent init or general reader-lifetime protocol. A per-device busy flag
rejects synchronous nested init/cleanup with SW_BUSY; it is not a lock.
An existing HPPE cfg or recorded port token rejects reinit before writes,
using actual SW_ALREADY_EXIST=-16, not SW_NOT_SUPPORTED=-19/Linux ENODEV.
No borrowed cfg copy, fake success or implicit replace/restart is permitted.

Property-enabled modes independently reject an occupied port slot and
foreign dev_clean before allocation/metadata writes. An already retired
HPPE cleanup hook may be reused. Both KERNEL_MODULE && USER_MODE skips
port/API ownership: a preexisting port slot is preserved, not adopted.
The original API-installation guard remains; normal combined-mode outer
callback absence remains OPEN, not repaired by direct-child cleanup tests.

Additive opaque port build helpers keep the actual port_info fields/size
and all legacy reset/allocation/cleanup/setter bodies unchanged. Private
build allocation does not publish. Private map/property setters validate
their own domains and preserve valid bitmap policy. Publish rechecks the
destination slot, then consumes the local handle to NULL. Abort consumes
only still-private storage; abort after successful publish is a NULL no-op.
Paired owned cleanup checks admitted ID and exact slot identity before
free; mismatch preserves foreign state and the HPPE cfg/token for diagnosis.
Identity checks are not an ABA or general post-displacement lifetime proof.

## Transaction And Rollback

New cfg and port storage remain attempt-owned until all fallible work
completes. Save only the immediate HPPE-entry hsl_dev_t metadata; restore it
on failed dev/property/alloc/publish work, abort private P, free new C, clear
the busy flag, and return the original first SW error. API callbacks remain
untouched on failure. After P publication, only nonfallible ownership/API
stores follow. Successful bitmap/count/CPU and callback identities must
match the26-layer baseline for fresh admitted inputs.

Normal cleanup retires only the recorded P token, then C; dependency error
must not free C or clear its token. Combined C-only cleanup never touches
an unowned P. Out-of-range cleanup IDs must be rejected before array access.
Foreign/current/peer owners, NULL and idempotent exits are separate cases.

## Required Qualification

- Exact26->27 full692-file derivation, declared coordinates/context/zero
  offset/fuzz; only header/port helper/HPPE files change, recipe16->17 only.
  Pin, DP release and frozen build lock remain unchanged.
- Complete actual candidate functions/macros/types, all seven new helper
  bodies, legacy helper bodies and declaration/definition type agreement.
  Reduced cfg/API/OS leaves must remain explicit, not target ABI proof.
- Four compile-time mode profiles; independent C/P empty/old matrix, old
  cfg bytes/token/API/metadata preservation, all devs and invalid IDs.
- Natural cfg/P OOM, CPU validation failure, first error, exact allocation
  and reverse free order, explicit retry, published success/paired cleanup,
  foreign API, stale same-device callback and unchanged peers.
- Synthetic private map/set/publish failures marked artificial separately
  from natural allocator/CPU failure; publish conflict must leave foreign P
  intact and still-private owned storage eligible for exact abort.
- Same-device synchronous nested init/cleanup and cross-device behavior,
  no lost busy flag on any exit; no concurrent/RCU/reader safety inference.
- Exact independent state/action/owner/oracle inventory; frozen assets and
  all raw/expected/generated/source tails. Independent negative obligation
  inventory before execution and final completion; empty/truncated/duplicate
  controls cannot pass. Clean compile then exact86 marker only, never
  compiler/crash/sanitizer/timeout negative credit. Safe old witnesses and
  model/gate controls counted separately. Python -O, fresh parent GCC and
  Clang ASan/UBSan97/98 canaries; LSan remains unqualified.

Outer HSL cfg/API zeroing, shared UK/SD/bootstrap, adapter, PHY/provider,
root error masking/SDK errno domain and general reader/cleanup lifetime
remain separate OPEN contracts. FAL-C01 is not wholly closed by this child
group, nor do27-layer selected tests certify the full root combination or
highest performance. No old sealed test/program execution or inherited PASS.
