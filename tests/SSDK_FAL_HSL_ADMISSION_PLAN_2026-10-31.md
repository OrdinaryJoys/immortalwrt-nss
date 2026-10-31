# FAL/HSL pre-mutation admission and paired retirement

Base 8ebbf67db78091e7b767789ae545616523b70666, SSDK release17,
exact CodeLinaro recipe pin d9a196497ecee2530722d906e0efe1b7408b6ef6
plus27 local patches. Candidate040 raises only SSDK release18; DP9 and
the frozen build checkout/lock are unchanged. No make/target/module/
firmware/cloud build, push/main/Release or device operation is allowed.
Fresh exact text preparation and isolated native host fixtures only.

## Established Defects And Scope

The actual fal_init called hsl_api_init (clearing API), then hsl_dev_init
(clearing dev_table and copying outer cfg) before039 could reject an
occupied HPPE child. Direct hsl_api_init and hsl_dev_init were bypasses.
The normal combined KERNEL_MODULE && USER_MODE exit only freed the outer
HSL cfg: HPPE intentionally installed no dev_clean hook, so its C was left
held. These are source-defined gaps, not newly observed router faults.

Only serialized, reader-quiescent lifecycle entry is qualified here.
Per-device phases reject synchronous public reentry; they are not locks,
RCU, ABA protection, concurrent publication or a general restart protocol.
Unknown external clients remain outside the in-tree caller census.

## Entry Contract

- Validate IDs before array access and NULL cfg before any side effects.
- Before API/dev_table/cfg writes, reject held outer cfg, recorded HSL
  HPPE acquisition, direct child C/token/busy, foreign cleanup hook,
  occupied P (except deliberately unowned combined HPPE P), residual
  adapter and any existing VLAN software cache. Do not free residuals.
- Dispatch validation follows the actual old switch and compile guards:
  HPPE/APPE/MRPPE use HPPE; UNSPECIFIED only dispatches ISIS or ISISC.
  The broader current-chip metadata fallback does not authorize HPPE.
- A private-address-validated opaque continuation distinguishes legitimate
  FAL subcalls from independently entered public calls. No ambient
  FAL-active bypass is granted. FAL holds the guard through VLAN/adpt and
  cleanup holds it through UK/VLAN, including failures.
- Public hsl_api_init checks admission before its original table reset.
  The FAL continuation performs the same full API reset once, authorized
  by INIT_RESERVED -> API_READY. Direct HSL need not reset API itself,
  preserving the old direct-entry success policy.
- Guard phase and handle validation precede dereference. End consumes
  the local handle only for reserved/post states, never a running core.
  End cannot replace an earlier failure. Empty versus partial/held is not
  a readiness claim; late FAL failure leaves acquired HSL evidence held.

## Retirement Contract

Record HPPE retirement responsibility only after this HSL's hppe_init_owned
actually returns SW_OK, not from chip metadata or a state-query result.
The success flag alone is insufficient: a serialized direct child cleanup
and reconstruction could replace A by B while the outer flag still says
true. Bind HSL to the captured successful HPPE instance epoch as well.
HPPE increments its per-device64-bit epoch only at nonfallible success
commit, never resets it on cleanup, and rejects exhausted epochs before
child writes. The owned initializer requires an empty output token and
captures the actual successful epoch; owned cleanup rejects zero, absent C
or epoch mismatch before delegating to the original child cleanup.
This covers address reuse during the same serialized module lifetime,
not concurrent atomics, stale external module-generation handles or reader
lifetime. These are internal bookkeeping tokens, not security capabilities.
The normal cleanup invokes that matching child once even if combined
mode has no hook. Dependency failure or a foreign replacement hook must
preserve outer cfg, acquisition record/epoch and child evidence. After successful
paired retirement, clear only that own hook/flag/epoch, then free outer cfg.
Combined cleanup must not touch foreign P. If HSL has not acquired a
directly owned child, reject cleanup before API/cfg/UK rather than adopt it.
Legacy successful callback retirement clears only the unchanged callback;
this is not a generic legacy child ownership or rollback redesign.

Three selected shared-prefix call expressions (SD, UK init, API-lock init)
and UK cleanup are evaluated once through cached rv. The shared macro
and other call sites are unchanged. No failed-prefix compensation or
shared acquisition refcount is implied by these local propagation fixes.

## Required Verification

1. Replay exact27 ->28 at declared context/coordinates without offset,
   fuzz, rejects or extra files; independently compare all692 outputs and
   eight changed files. Read actual mk/obj.mk common/IN_VLAN linkage and
   exact-pin caller/dispatch sources; do not infer target modpost success.
2. Extract complete actual selected FAL/HSL/API/HPPE/helper functions and
   types. Label reduced cfg/API and SD/UK/chip/VLAN/adpt/OS leaves as models,
   not real hardware, installed ABI, whole root or target evidence.
3. Four KERNEL_MODULE/USER_MODE profiles, noHPPE/legacy selection controls,
   HPPE/APPE/MRPPE dispatch and UNSPECIFIED versus real selected branch.
4. Full payload observations before any cleanup for rejected public entry,
   held/partial/foreign/peer resources and failed retirement. Do not let a
   later cleanup erase a bad write. Test same-device nested init/API/
   cleanup at reachable calls and late FAL/cleanup leaves, plus peer scope.
5. Normal FAL must not false-reject its HSL continuation. Verify every
   failure releases only its own guard, returns the first error and does
   not overwrite a retained partial owner or claim readiness.
6. Combined normal retirement reaches C and preserves foreign P; ordinary
   mode P/C retire once. Child mismatch/foreign hook/direct-child ownership
   failure preserves evidence. Invalid/reused/role-mismatched continuation
   handles reject before mutation; no arbitrary alias/ABA claim.
   Serial direct child A->cleanup->B must not authorize B retirement under
   the held outer A epoch, including same-address allocation reuse; zero,
   max-1->max, exhausted namespace and failed constructors are separate
   epoch cases. No counter advance on failure or reset on cleanup.
7. Fixed independent positive/negative inventories and semantic snapshots.
   Each mutant must compile clean, then fail exactly86 with its named
   semantic marker; compiler/crash/timeout/sanitizer failures are not
   negative credit. Source-gate controls are separate from semantics.
8. Freeze assets/inputs/expected outputs before final parent runs; fresh
   Python -O GCC and Clang ASan/UBSan runs with actual97/98 canaries, raw
   and saved/live/generated/source tail hashes, independent source and
   test reviews. No historical sealed execution or inherited host PASS.

## Explicitly Open

Root error masking/SDK-Linux errno domain; complete root/FAL acquired-abort;
adapter cleanup and its allocations; PHY/provider/platform producers;
shared UK/SD/bootstrap ownership/partial-prefix repair and dev_init once
state after cleanup; arbitrary cleanup/reinit and all-chip legacy lifecycle;
live VLAN reset/HW-cache consistency; general readers/locking/ABA/drain;
full28-layer target combination, target ABI/link/modpost, firmware, device,
runtime, throughput/latency and performance. C01 and C04 are only partial
increments. No whole-system no-fault or highest-performance assertion.

The exact cached primary Git pin is the source authority for this phase.
This does not assert all remote upstream HEADs are current or official
endorsement of local040. New common helpers are construction/retirement
only; no hot datapath or performance switch is changed.
