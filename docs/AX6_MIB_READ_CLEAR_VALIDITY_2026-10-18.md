# G5 MIB Read-Clear Validity Contract

This follows the current 020/021/022/023 SSDK chain, at source HEAD
5c740975bd86599f6c44c408f136d2d8a5dcfec0. Patch 024 and SSDK release 5
are local changes only; the build lock and accepted S6 image remain frozen.

## Failure Semantics

A register read can consume a counter before a later field fails. Discarding
the failed structure prevents partial accumulation but cannot recover that
consumed prefix. Returning a successful cumulative snapshot after a subsequent
good read would therefore hide an incomplete history.

024 adds one private invalid flag per device/port. A failed full/RX/TX sample,
or a failed counter flush, makes that cumulative epoch unknown. Failed samples
are not accumulated. A later successful raw sample may still be collected,
but does not silently repair the historical gap. Cumulative snapshot requests
return SW_READ_ERROR without writing output or consuming more registers.
Only an explicitly requested, successful hardware flush clears the software
counters and invalid flag. The patch never initiates a flush automatically.
Allocation/free start/end a distinct software epoch, not continuity across
module reload. Null-output rejection does not taint an existing epoch.

The flag covers the complete cumulative structure rather than promising
per-field accuracy. Public structs, signatures, exports and hardware modes
are unchanged. It uses the existing FAL lock for sample/snapshot/flush state.
022 allocation/free concurrency and complete module lifetime remain separate
gates; this patch does not claim to solve them.

## Scope

This is a diagnostic repair, not a packet-forwarding, reset or performance
change. There is no new register access, IRQ/RPS/PBUF/offload change, automatic
reload or recovery. Raw MIB calls retain their per-call status; cumulative
callers must honor SW_READ_ERROR rather than display a healthy zero value.
AX6 physical GMAC register failures are modeled, not observed hardware faults.
MMIO bus faults that do not return an SSDK status are not detected by this
contract. G9 XGMAC composition and global non-MIB HPPE propagation are excluded.

## Offline Tests

`tests/test-ssdk-mib-read-clear.py` compiles exact prepared FAL and HPPE GMAC
function bodies using the actual MIB structs, error constants and port macro.
Register reads destructively clear modeled state; kernel locks are modeled.
Every failing position across full/RX/TX/cumulative reads is exercised.

```sh
python3 tests/test-ssdk-mib-read-clear.py PREPARED_WITH_024 \
  --baseline PREPARED_THROUGH_023 --output NEW_EVIDENCE_DIRECTORY
python3 tests/test-ssdk-mib-errors.py PREPARED_WITH_024
```

Observed: 129 failing-register positions, 2080 checks, zero candidate failures.
The pre-024 baseline fails 646 checks. Three intentional mutations (no latch,
good-read healing, failed-flush healing) fail 646/129/130 checks respectively.
The existing ordinary/HPPE-GMAC suites each pass 32 checks. These are native
function tests, not firmware, target modules, XGMAC, concurrent kernel execution
or hardware throughput tests. Final CI integration and target/S6 validation
remain deferred; no build is authorized by this document.
