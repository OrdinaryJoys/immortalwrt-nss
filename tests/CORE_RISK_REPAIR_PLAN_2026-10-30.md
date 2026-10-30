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

## Item 2: ECM denied-port snapshot repair

Patch 029 replaces the private denied-port hlist with bounded immutable TCP
and UDP bitmaps. The pinned upstream 8c7355b hash conversion and inherited
local code were inspected together; a hash-index-only patch would leave
unbounded input/output and concurrent reader reclamation defects unresolved.
Writers validate the complete command before publishing, serialize updates
with a management mutex and free retired maps only after synchronize_rcu.
The packet helper uses one snapshot for both ports, without allocation or a
sleeping lock. Existing public signatures and default DHCP exclusions remain.

Input is capped at 512 bytes. Nonzero positional writes, embedded NUL and
invalid full numeric tokens are rejected; zero-length writes are no-ops.
Text allocation, formatting, copy and free are serialized by the same mutex;
one internal dump is bounded by 393218 bytes. Generic proc-wrapper buffers
and allocator overhead are outside that bound. Read output is sorted, and
separate partial reads may observe different generations. The list excludes
acceleration; it does not drop packets or immediately revoke existing flows.

The v5 host GCC and Clang ASan/UBSan suites each passed 799 cases and 67172
checks with zero live bitmap allocations at completion. Five deliberately
faulty variants were rejected after compilation. Complete actual functions
are extracted, but bitmap/memory/mutex/RCU/kernel API effects are explicit
host substitutes. The pthread grace model is not Linux RCU, lockdep, KCSAN,
full-module, concurrent-unload, target or performance qualification. The
independent final review accepted only this source/host scope. Earlier oracle
and negative-control compilation failures remain preserved as failures.

## Item 3: EDMA unpublished allocation rollback

Patch 013 repairs allocation failure at the pinned d8f802f EDMA v1 source.
The inherited post-decrement loops can select a negative array index. Merely
changing the decrement would still invoke operational cleanup before rings
have been configured and leave the software arrays owned after a failure.
The new helper releases only acquired coherent descriptors, using non-NULL
CPU pointers as ownership even when the valid DMA handle is zero. It neither
accesses MMIO/packet stores nor invokes streaming unmap or completion cleanup.
The outer allocation owner releases and clears all four software arrays.

All unrelated function definitions and nonallocation tokens are unchanged.
Parent review checked edma_hw_init/configure ordering and the outer edma_init
failure path: allocation failure returns before publication, then the outer
owner unmaps/releases register resources rather than calling live ring cleanup.
This helper requires acquired zero-initialized software arrays; it is not a
generic destructor for absent arrays or live/concurrently owned hardware.

GCC ordinary and Clang ASan/UBSan v4 suites each passed 150 matrix cases and
70517 checks, including 66 allocation-failure cases, 50 successful retries
and 46 valid zero-DMA rollback releases. Successful single/multi-ring host
allocation/MMIO/RX-fill traces match the old source byte for byte. Old source,
decrement-only repair and six faulty variants are rejected with specific
diagnostics. All actual allocation/configure functions and ring definitions
are extracted, but allocation/MMIO/reset/RX fill are host substitutes.
Success disposal is fixture-only, not live-teardown validation. Ring geometry,
IRQ/NAPI policy, firmware ownership, B-DP-002/003 and hardware DMA quiescence
remain unchanged and unqualified. Earlier fixture failures remain evidence.

## Item 4: NSS mutating netlink operation permission gate

Patch 025 adds GENL_ADMIN_PERM to exactly 18 existing QRFS, GRE-redirect and
UDP-ST operations, retaining command numbers, handlers and namespace settings.
The four existing IPv4/IPv6 admin gates and 15 actual stats no-op handlers are
unchanged. Linux 6.18.38 actual full-to-split flag propagation and dispatch
checks were inspected and extracted: ADMIN requires initial-user-namespace
CAP_NET_ADMIN, not merely the child's own namespace capability. NETLINK_SKB_DST
can bypass the socket-file check, never the current sender capability check.

All 23 actual op tables (58 entries), exact headers/enums and seven selected
Linux functions feed the host regression. Clang ordinary, Clang ASan/UBSan and
GCC ordinary each passed 1856 positive cases and 4234 checks. The actual
baseline and 40 targeted runtime variants are rejected per compiler; most
flag variants use runtime table mutation, not separate source recompilation.
The independent scoped review found no blocker in the exact 18 additions.

This is not an all-family payload or permission hardening claim. The remaining
21 unchanged dormant/query entries include 19 mutation-capable CAPWAP, DTLS
and IPsec entries plus two OAM entries. Current package selections gate their
registration; alternate enablement requires another permission/payload audit.
Credential masks, reduced family/header parsing and non-stats handlers are
host substitutes. Real sockets, LSM, registration, final configuration, NSS
payload/lifetime and MCS remain unverified. Do not enable dormant families on
the strength of this 18-operation repair.

## Full-stack integration finding: QMI 939 stale context

A fresh complete mac80211 patch replay, rather than the earlier selected-file
fixtures, rejected the target_mem memset hunk in 939. Patch 938 had already
inserted callback-lock initialization after qmi.ab; 939 still required the old
blank line and target_mem_mode context there. The array-clear change itself
was intentional and remains identical. Only that hunk's position/context was
refreshed; all ordered added/removed code lines remain unchanged. No QMI
lifecycle logic or timing was changed to make patch application pass.

The corrected full replay applies 16 SSDK, 18 ECM and 303 mac80211 patches.
Saved logs contain no fuzz/offset/failure marker. This is textual integration
only. It does not validate full kernel compilation, QMI_FAIL cleanup, firmware
handle lifetime or the already-open callback/event-drain contracts.

The existing NSS init ownership fixture must track the new opaque registration
API and actual registry structure. Its provider-loss hook observes publication,
not an assumption that every registration acquires the legacy global lock.
Legacy netdevice and opaque registrations are both counted; the pre-existing
foreign-interface, failure, retry and DMA-zero assertions are retained.

## Next repair batches and stop conditions

### MCS A03: input, output and nested consumers as one protocol

The command ledger covers all 22 inbound commands and outbound event 100.
Before implementation, confirm native 36-byte private-header ABI and real
userspace callers, especially fixed SET requests with buf_len=0. Validate the
actual nlmsg length before any private-field access, every fixed/array payload,
nested source counts and output item capacity before side effects. Do not
add sleeping allocations under the current receive-side RCU critical section.
Use trusted sender capability/portid, not a supplied nlmsg_pid, and initialize
all response/event bytes. Preserve event/group command semantics and native
control-field endianness rather than inventing a new protocol.

Include adjacent actual defects: full MLD ACL update must select the matched
index, deletion uses overlapping ranges, IPv6 source translation confuses byte
size with source count, and GET item serialization has its own source bound.
Length-only or capability-only changes cannot close this group. Required
fixtures cover each command with short/exact/oversized input, nested counts,
full-table update, overlap deletion, allocation/ref/RCU ownership and poisoned
output. Real transport/framework behavior remains a later target gate.

### EDMA B-DP-002/003: shared lifetime and slot ownership

Probe abort can retain a failed netdevice in the registry and leave shared
NAPI attached to its first provisional owner. Inventory every registry reader,
NAPI/IRQ owner and SSDK notifier before defining a stable shared owner and
reader drain. A NULL write is not a drain, and a netdev reference alone is not
NAPI lifetime. Failure paths must not reuse NSS takeover/final module teardown.

For TX, both producers and both completion/cleanup routes must use one skb/DMA
slot protocol. Capture/retire the pair before advertising a slot reusable, and
specify lock/order and streaming-DMA ownership for wrap and teardown. A producer
lock that completion never takes or a single read reorder is insufficient.
Use extracted functions and forced interleavings before changing packet-path
code. Performance cost of a proposed common lock must later be measured; no
ring/IRQ/budget tuning is authorized here.

### Wi-Fi ABI, dispatch and firmware lifetime

Treat MU-EDCA command/attribute mismatch and global event dispatch together.
Current kernel 160/346 collides with standard hostapd allocations; its local
extension is 161/351. A same-image paired allocation is a candidate, not an
upstream reservation. Check both actual headers/policies and the global MLME
socket dispatch, strict payload size and one update per radio/interface across
multiple BSSes. Do not merely add the case to every BSS or change one enum.

Opaque host context repair does not supply firmware reply identity or drain.
STOP/PDEV_DEINIT/RESET timeout, late replies, descriptor release and QMI_FAIL
resource cleanup require separate request/session and DMA-quiescence contracts.
Keep UNKNOWN when firmware status is unknown; no stack callback data, forced
timeout free or assumed cancellation is an acceptable shortcut.

### Uncovered and later validation

A06/A07 management parsers and A08 firmware-version search need complete
input/read/offset/error contracts, not mechanical copy_from_user replacement.
DP bridge/VLAN/VSI, topology helpers, stats epoch, SSDK bounds, IGS/CLEAR/N2H,
SQM, rpcd/LuCI, DNS/TUN/backup and other records in the original coverage ledger
remain open. Inventory/parser coverage is not line-by-line semantic review.

After reviewed source commits, separately update the build input lock, patch
manifest and future CI test wiring. The frozen old build repository must not
be used as if it already contains this batch. No cloud dispatch, target build,
artifact/runtime qualification or performance claim is obtained in this round.
