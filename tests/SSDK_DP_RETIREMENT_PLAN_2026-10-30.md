# SSDK holder/reader retirement, then DP init rollback

Baseline: bf44050bd8b1545c7d73bc2a2d965ad0192d1646, local branch
codex/ax6-ssdk-dp-retirement-20261030. The old build lock at2bcafb4 remains
frozen and does not contain this stage. No make, target/module/firmware/cloud
build, push, main merge, Release or device operation is authorized. Native
host function fixtures and fresh textual preparation are separate gates.

## Ordered gates before production edits

1. Freshly archive exact SSDK d9a196497ecee2530722d906e0efe1b7408b6ef6 and
   replay all16 existing patches with complete old/new declared coordinates
   and output-byte comparison. Inventory every publisher, raw/copy reader,
   notifier, worker and private-state retirement path. Do not execute old
   evidence programs or import an old PASS.
2. Review the joint owner/reader contract before implementing it. A cache
   cell owns its own reference; a reader pins under that same synchronization
   or consumes a copied name. UNREGISTER retirement precedes fallible hardware
   checks, scans object identity and releases acquired refs before the kernel
   reference wait. Rename/replacement/replay must preserve identity. An added
   hold returned only after unregister completes can deadlock.
3. Legacy PHY-only name/binding and conditional DSA callbacks require their
   actual attachment/child owner and outer lock graph, not just a netdev pin.
   Include ref_misc and ref_vlan DSA readers, MHT power callbacks and the
   NETDEV_CHANGE link-polling path. Do not silently disable a profile, erase
   a useful fallback, invent a new asynchronous power policy, or sleep under
   FDB/HSL/API/MDIO locks to make a fixture pass. Unproved compatibility is
   explicitly blocked, not labeled complete.
4. FDB start/rearm/stop, notifier replay/error, genl/sysfs entrypoint removal
   and private-state lifetime are part of retirement. Stop admission before
   draining workers; never wait for an RTNL-taking consumer while holding
   RTNL or any lock it needs. Preserve MHT and other start/stop profiles.
5. Freeze the SSDK patch/tests, then independently review real functions,
   exact positive ledgers, old-source counterexamples and named semantic
   negative controls. Compile errors, sanitizer crashes and arbitrary nonzero
   exits are not successful semantic negatives. Models do not prove Linux
   lockdep, real kernfs/RCU, firmware/DMA or runtime performance.
6. Only after the required SSDK owner/reader gate is accepted, implement DP
   init first-error propagation and dependency-aware acquired-stage rollback
   against exact d8f802f plus current001-017. Distinguish driver-core self-unwind on
   failed registration from a successfully acquired driver. A failed notifier
   registration is not owned by the caller. Set common_init_done only on
   actual success; never unregister unacquired stages. Platform ports retire
   before acquired netdevice and switchdev notifiers, then HAL: those callbacks
   still need port/VSI/PHY state during unregister. This is not blind reverse
   acquisition order. External NSS/FW/HW owners remain a separate condition.

## Current observed progress

The initial16-layer/692-file preparation is historical text-only evidence.
Source helper/control commit69ba1610b4 now has bounded independent source and
historical-control review. The helper checks declared contexts and full output,
live/saved inventories, recorded inputs/archive and prepared bytes, not an
atomic filesystem snapshot or whole692-file semantic audit.

DP017 local commit59218d59cc retains native PHY through netdev unregister and
keeps the complete disconnect helper. Source/order acceptance is bounded;
new exact-trace r5 tests separately close the previous suffix-only P3 gate.
The failed r4 legacy expected trace was a test error, not a production change.

SSDK029 local commitb59682127a retires scoped FDB/IRQ/control producers. Its
freeze1 was rejected after an actual-source last-user/wake window. Freeze2
a0e19f941d404525dd21bc4c374e577ac3ca8d6663425e2a5a437d36adcf8cd5
moves wake under the state lock and adds an unconditional final lock barrier,
including no-IN_FDB. Fresh17-layer text and final r4 GCC/Clang native suites
pass34/12048 and21 exact semantic mutants; last-leave and a no-FDB controller
user are separate probes, not whole-module profiles. Static source and native
test-quality reviews accept only that scope. Docs distinguish diagnostic
canaries from runtime mutants and current README from historical run hashes.

G1/G3 cache/value-reader030 is local commit07c6a3fbf0, with native managed
tombstones, optional-notifier failure cleanup, copied names, typed sysfs output
and explicit ready/producer-mark APIs. Final property-domain campaigns each pass
165 positives/32 exact source-function negatives plus one separately classified
old-test-model projection control. Limited source/test review and its T01
correction erratum accept only the declared native model scope.
Generic legacy PHY/BH and DSA child/callback safety are not closed by copies
or local netdev references. Separate018 now wires native admission and rollback;
its own bounded source/test acceptance below is not borrowed from029/030.
Package release maintenance is now8-to9 only for DP/SSDK; source pins are
unchanged and new native runs bind both actual/baseline recipes. The build lock
remains deliberately frozen. No target build is authorized at this point.

The native chip/HSL/admission failure gap requires producer-first classification
before PHY attachment; ready alone is insufficient. An explicit030 mark API is
approved for the bounded native HPPE/device0 physical-port profile, using real
CPU metadata and permanent per-provider-life tombstones, not new refs or a
notifier veto. This API's source/test scope is now accepted as described above;
unchanged DP production did not call it until the separate018 candidate. An actual
sysfs positive also exposed the old u8-to-fal_pbmp_t pointer cast; an aligned
full-width local output with the original u8 assignment/layout/error policy is
qualified only by030's stated native tests. Do not suppress the sanitizer or skip
that consumer. DP018 must acquire N before P: ports may be published and enslaved
while platform registration is still running. Cleanup remains P before N/S/H.
The old P-before-N acquisition contract is historical, not the current plan.

DP018r3/c9 additionally initializes the shared slowproto bitmap before all S/N/P
publication and guards out the selected per-probe reset. Its individual source
delta and H-failure ownership are independently bounded-reviewed. The parent
has now independently run frozen joint GCC/Clang release9 campaigns, each with
102 exact positives/30 source mutants plus separately counted framework/header,
oracle and metadata controls. Final independent test-quality review accepts
the frozen bounded host scope and closes Q01/Q02 in that scope, with no new
mustfix. See DP-INIT-TEST-FINAL-INDEPENDENT-REVIEW.json; this is not51-function
all-branch coverage, whole SDK/FDB, target or runtime approval.
H=false is not acquired; lower EDMA
CPU/OF unwind is not proof of hardware/reset/DMA restoration, and the bool HAL
API still compresses its internal detailed errno to the existing EFAULT policy.

The stricter Q02 VSI model produced an actual r13 host FAIL, but its premise
that every raw successful setter creates a new exclusive DP resource was not
supported. Current provider initialization may already assign the same default
hardware value and software map. Exact upstream bodies and official history
were crosschecked; no abort-side invalidation is authorized merely to satisfy
that oracle. Keep r13 and the provisional design unchanged, with explicit
ownership errata. The corrected model separates provider HW/SW prestate and DP
call history, tests fresh successful defaults/no other FAL writer, requires
normal remove invalidation, and requires failed probe to preserve that bounded
prestate. Precise missing-write, wrong-argument and wrong-abort-clear controls
are necessary. Reprobe/mismatched HW/SW/partial FAL error/concurrent writers
remain OPEN, not qualified by the corrected fresh-provider scenario.

New018 requires030's real exported ready/mark APIs. Future integration must
pair them; old source/build locks or new-DP/old-SDK mixing are unsupported.
Installed-header host syntax is not a target linkage/modpost/module-lifetime
proof. Final package metadata remains a separate recorded input, never a
retroactive upgrade of earlier recipe8 native results.

Designs and reviews are written to the new active evidence directory:
/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement.
The previous phase2 index remains a historical scoped index, not this stage
or a complete archive manifest. MU wire numbering remains blocked and no
Wi-Fi, IRQ, ring, RPS/PBUF, offload, subscription or Geo setting changes belong
to this work.
