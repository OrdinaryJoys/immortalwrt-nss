# Core-risk repair and validation plan

Baseline: source cfde3310d6fe3b007775a91c81e35309a29886a2,
build 2bcafb435bb316da0f74da1f6ec0817020201ed1. No target/firmware
build, make, push, main merge, Release, device access or performance setting
changes are authorized. Host-only function fixtures are not target builds.

## Per-item gate

1. Read the exact pinned upstream definition, local adaptations and all direct
   callers/owners. A default upstream HEAD is not a compatible release train.
2. Record an input, ownership, error and lifetime contract before editing.
   Correct a prior finding if the full control flow contradicts it.
3. Apply a narrowly scoped source patch; do not change firmware ABI or tuning
   to make a test pass. Keep normal-path behavior unless it is itself wrong.
4. Prepare fresh baseline/candidate source with every patch, zero fuzz/offset.
   Execute actual complete functions with explicit host substitutes, positive
   cases, old-source counterexamples and targeted negative controls.
5. Review the changed code, caller compatibility and the oracle independently.
   Record compiler, sanitizer and unsupported coverage separately.
6. Bind package releases and the build lock only to the reviewed final source.
   Local tests do not close target, firmware, boot, runtime or performance gates.

## Priority 1: memory, authorization and object ownership

- NSS-A01: repair both MATCH next-hop handlers as one command contract. Use
  request-local bounded storage, preserve signed interface errors, validate
  required tokens and the full numeric token before acquiring a netdev,
  release each acquired reference once, and propagate send failures. Preserve
  read handling and physical/VAP APIs; do not change their wire messages.
- NSS-A02/A03: audit every mutating generic-netlink operation and every MCS
  command payload before choosing capability and length checks. A family-wide
  permission assertion alone is not payload validation.
- NSS-A04/A05/P-ECM-BOUNDS: jointly repair denied-port hashing, packet-reader
  lifetime, bounded input and aggregate output. Do not add a sleeping lock to
  packet paths. Include repeated writes, invalid batches, allocation failure,
  read offsets and concurrent lookup/update ownership in the design.
- B-DP-001: cleanup only the previously successful ring interval on allocation
  failure, including first-ring failure. Do not change ring counts or IRQs.
- B-DP-002/003: distinguish probe abort from NSS takeover and final teardown;
  define per-port reader drain and paired skb/DMA slot retirement before code.
  Do not free an object after merely writing NULL or assuming an IRQ stopped.
- WIFI-C-NEW-01: jointly verify opaque context, actual net_device use and
  non-linear ext-buffer handling in NSS core. A cast-only change is insufficient.

## Priority 2: cross-layer protocols and remaining management APIs

- MU-EDCA: agree on a stable command/attribute allocation and validate actual
  kernel, hostapd headers, attribute policy and global/BSS event dispatch.
  Fixing one enum cannot establish end-to-end behavior.
- NSS-A06/A07/A08: verify exact Linux sysctl buffer semantics, actual ctl.data
  ownership and firmware search length before any bounded fix. Include read,
  empty/max input, errors, offsets and malformed-firmware cases.
- Review adjacent uninspected branches and tests. A disabled stock feature is
  not an active device fault, but shared packages must retain multi-config safety.

## Design/qualification blockers remain open

S08, N2H and Wi-Fi teardown need firmware reply identity, cancellation/retirement
and callback/DMA quiescence contracts. Do not invent a cookie, use stack callback
data, force a free after timeout, or relabel UNKNOWN as safe. Existing IFB/CLEAR,
qdisc, SQM, QMI_FAIL recovery, stats epoch, rpcd/LuCI and runtime throughput gaps
stay open until their own gates are satisfied.

The initial audit's complete records and unread coverage remain at
`/Volumes/FX-MD87/Review-AX6/audits/20261030/component-deep-audit`.
That sealed directory is data only; never execute its generated programs.
New evidence belongs to `core-risk-repairs`, not a rewrite of old PASS/failure.

## Item 1: MATCH bounded command repair

Local patch 024 repairs the set/reset handlers together. The exact upstream
51be82d implementation allocated set-command storage; local adaptation 008
removed that allocation and left a NULL buffer. The new local arrays are
bounded, signed interface lookup errors are preserved and acquired device
references are released exactly once on all enumerated returns. Complete
numeric tokens are required and send failure returns -EIO.

Command writes must start at position zero. Nonzero/negative writes are
rejected before proc_dostring or NSS effects; zero-length writes are no-ops.
Reads retain actual proc_dostring behavior. As in the old implementation,
the shared sysctl display string may change before a later command validation
or NSS failure; this is not a transaction for that display buffer and no
concurrent display/read qualification is claimed.

`test-nss-match-nexthop.py` compiles the complete actual handlers, the pinned
driver's constants/enums, and the exact Linux 6.18.38 `_proc_do_string` and
`proc_dostring` definitions supplied with `--kernel-sysctl`. Warning policy,
netdev/type/table/TX effects and numeric conversion are explicit host
substitutes. No full kernel/module or firmware is run.

Final host GCC ordinary and Clang ASan/UBSan suites each passed 83 cases and
285 checks. Old source and six faulty variants were rejected; old execution
terminates before all cases, so its later cases are not claimed executed.
Initial fixture/compiler and mutation-anchor failures remain saved. The
independent v5 review closed IR01/IR02 within this limited scope, not target,
concurrency, MATCH-table lifetime or firmware timeout/callback qualification.
