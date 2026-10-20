# NSS init ownership host test

This test extracts seven complete functions from the prepared ath11k tree and
eight registry/state functions from the exact prepared NSS driver. It does not
compile or execute a Linux module or firmware.

```sh
python3 tests/test-ath11k-nss-init-ownership.py PREPARED_BACKPORTS \
  --driver-prepared PREPARED_NSS_DRIVER --baseline PRE_R19_BACKPORTS \
  --mutations --sanitize --output NEW_OUTPUT_DIRECTORY
```

Covered contracts:

- If the existing initialization-state check rejects the published interface,
  unregister exactly that interface and release its external reservation.
- Preserve the original admission point: readiness may arrive during sleeping
  descriptor allocation, and a later retry on the same object must still work.
- Preserve a foreign external interface when using/releasing the second slot.
- Descriptor CPU ownership, a successful DMA address zero, failed handles left
  untouched/zero/error-valued, metadata clearing and repeated host cleanup.
- Real descriptor limits and both message arrays, 1/2/3 radio parameter shapes,
  missing/valid/invalid DT properties and five symbolic hardware switch cases.
- Preserve the normal initialization resource/message signature.

The baseline must fail independently in N01 and N02 assertions. Five mutations
isolate premature readiness rejection, unregister, zero-address ownership,
metadata and DMA release.
Compiler/sanitizer errors are not accepted as assertion-based negative controls.

Limits:

- DMA allocations are ownership tokens, not real DMA memory. API-boundary
  mismatch assertions are not proof of backend double-free: Linux guards NULL.
- Locking, scheduling, allocation and firmware replies are modeled. Unsupported
  synthetic hardware/radio combinations are not actual device qualifications.
- Only the descriptor message structures are copied from driver headers; other
  layouts, ring/interface IDs and firmware behavior are host contracts, not ABI.
- Post-send failures preserve the existing init unwind behavior. The test does
  not establish firmware quiescence, callback draining or the full N03/N04 path.
- The existing signed loop and int/u32 page-index warnings remain recorded as
  warnings. Other warnings stay fatal, and ASan/UBSan stays enabled when chosen.
- The provider must already be loaded through the existing module dependency;
  this is not a new API for accessing NSS before its own initialization.

The production change requires a new mac80211 package release and a later
separately approved target build. Host success is not runtime acceptance.
