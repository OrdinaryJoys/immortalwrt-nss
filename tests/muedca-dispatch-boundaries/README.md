# MU-EDCA Offline Dispatch Boundaries

TEST ONLY. `wire_ready=false` and `BLOCKED_UNASSIGNED` are invariant. No
command is allocated, aliased, deployed, or inferred from an IE. These tests do
not establish a working kernel/userspace MU protocol or approve counter policy.

## Run

From the source repository, run the new runner with a fresh evidence directory:

```sh
python3 tests/test-muedca-dispatch-boundaries.py --output /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2/MUEDCA-DISPATCH-parent-r1
```

The default input directory is `MUEDCA-DISPATCH-inputs-r1` under that evidence
root. It contains the primary OpenWrt source mirror archive for libnl-tiny
`40493a655d8caa2ccf5206dde1e733abe2920432` and Linux stable v6.18.26 UAPI headers.
The runner verifies their fixed hashes, the live libnl recipe pin, both source
archives, both kernel/hostapd recipes, the ordered 373-patch inventory, and all
38 selected final texts. Seven additional support headers/sources are replayed
too, including the exact backports core allocator/registration/encoding inputs.
No sealed script/program is imported or executed. Only this new source helper
is imported. No make, target compilation, socket, device, or cloud is used.

Fresh reconstruction is selected-file text replay, with full hunk context,
zero fuzz and **27 recorded selected38 kernel offsets**. Additional support
source offsets are counted separately. This is NOT the parent's full303
zero-offset replay or a whole-code audit. Missing/additional/reordered patches,
input drift and ambiguous hunks fail closed. The previous manifest is identity
data, not a previous PASS. `INPUTS.json` records current/prepared identities;
`SCRIPT-IDENTITY.json` binds all four new test files. Source/test input hashes
are rechecked after the run.

## Four Separate Layers

A. Original-route characterization uses the real `process_global_event`,
`process_bss_event`, `nl80211_reply_hook`, pending-list delivery/removal,
`do_process_drv_event`, driver-list lookup, incumbent handler, and old MU decoder
bodies. `do_process_drv_event` has one entry observer inserted; its complete
original switch is retained, but unrelated event leaves are counted stubs and
QCA/NAN/BE conditional paths are off. It is not an unmodified complete daemon
chain. Standard route probes use `WIPHY_REG_CHANGE` with its ordinary identity
attributes and no MU IE. IFINDEX, bridge, WDEV, WIPHY, broadcast, foreign identity,
deferred global/BSS delivery, synchronous reply, and allocation failure are
characterized. Wiphy and bridge lookups are explicit host models, not hardware.

B. Independent `strict_extent`, `strict_radio`, and `typed_ie` TEST oracles
accept explicit received bytes, strict attributes and the exact 16-byte standard
IE. They are never installed in either original dispatcher. The generic framing
oracle characterizes scalar route types; the dedicated radio oracle requires
exactly WIPHY plus IE and rejects IFINDEX/WDEV/missing/foreign identity. Actual
libnl allocation, message construction, conversion, getters, attribute parsing
and min/max policy functions execute. They are not hand-written API substitutes.

C. The complete baseline AP MU helper (symbol rename only), complete
`ieee802_11_update_beacons`, `ieee802_11_set_beacon`, HE IE generator,
`wmm_set_regulatory_limit` and `wmm_calc_regulatory_limit` execute. The separate
TEST consumer prototype uses actual `iface->bss[0]` as canonical, considers all
started/beacon/HE BSSs, updates shared AC state once, increments the shared low
nibble once if any eligible BSS has STA, and increments each eligible STA BSS's
WMM count once. 4096 three-BSS state combinations exercise that policy. Repeated
equal-valued events count as separate events. This is NOT production approval.
Actual WMM regulatory changes can add another original count increment; the
fixture explicitly preserves that difference rather than claiming globally
exactly-once counts through all beacon construction.

D. Explicit `compose_offwire` combines A's observed recipients with B's
independently validated typed data and C's prototype. Its harness binding carries
the separately validated wiphy (not a new wire field). Every observed route must
be a same-wiphy, WIPHY-only standard probe; identity-less broadcast is rejected.
It preflights actual AP iface pointers, not driver pointers. Each targeted
iface's actual bss[0] must be observed exactly once: missing/duplicate canonical
or foreign-radio ctx rejects before any mutation. The shared-driver/two-iface
positive explicitly puts both AP ifaces on the same radio. A test-only AP-context registry rejects
unregistered station-role contexts without casting them as AP structures. This
is a modeled role boundary, NOT a production role-discovery API. The unrelated
standard command is never dispatched as MU. The typed framing container's
command byte is not interpreted, negotiated or accepted as a MU selector.

## Full Bodies Versus Projections

`EXTRACTIONS.json` records original path, line, body hash and whether the whole
body is compiled. Raw/full prepared files are retained. `TRANSFORMATIONS.json`
records all source projections, renames, observers and modeled leaves.

* `hostapd_wpa_event`: only its actual MU case and AX guard are projected. The
  rest of that large switch is NOT compiled. Its full body is saved as data.
  This projection calls the original baseline helper only; the candidate is
  a separate internal prototype, not silently installed in this old callback.
* `supplicant_event`: absence of any MU case is checked against its full body;
  only its actual unknown-event default branch is projected and executed.
  This is not a full supplicant state-machine or process integration test.
* `hostapd_wpa_event_global`: full body saved/reference checked, not executed.
* `__ieee802_11_set_beacon`: exact disabled/CSA/AX-CCA gates are projected. The
  remaining builder/driver submission is a counted, failing leaf. No OTA claim.
* Actual driver/AP members are projected, preserving declarations but omitting
  unrelated fields; no whole-daemon binary ABI or layout claim. Fixed-width
  Linux types, unused credential storage, logging and utility macros adapt the
  host OS. No mock `nl_msg` layout is used.
* `nl_recv`, `recvmsgs` and kernel MU emitter: complete functions saved/reference
  checked only, not compiled or socket/kernel executed.

The main AX-off route variant deliberately retains HE data fields in a type
superset to characterize the actual AX-guarded event branch. It is named
`AXoff-route-projection`, not a package compatibility PASS. A separate syntax
probe restores the real `he_mu_edca` AX member guard and compiles the complete
baseline AP/WMM bodies. AX-on must compile cleanly; AX-off must produce only
the exact missing-HE-member diagnostics from those existing unguarded accesses.
That is a bounded existing compatibility BLOCKER, not a successful negative
runtime control or a target-build result. BE/MLO remains UNSUPPORTED.

## Received Extent And Legacy Evidence

Real `nl_recv` knows actual received length; `recvmsgs` checks `nlmsg_ok(hdr,n)`
before conversion. `nl_msg.nm_size` / `nlmsg_get_max_size` is allocated capacity,
not received bytes. The dispatcher callback signature supplies no true-extent
API. Production integration would need an explicit front adapter at the receive
boundary, before header/hook/getter access; this fixture does not invent one.
The strict oracle's extent is an explicit harness argument. Physically short
allocations and capacity-larger-than-received cases are tested separately.

Identity domains are distinct. Exact backports allocator/registration/encoder
bodies (unchanged after replay) establish wiphy0 and allocated wiphy maximum
INT_MAX-1; IFINDEX0 is rejected. WDEV high32 is wiphy and low32 is an assigned
nonzero identifier: phy0/id1 is valid, all-zero or zero low32 is not. WIPHY0
original-route/typed positives, foreign-radio and upper/sentinel boundaries are
explicit. The old candidate's erroneous WIPHY0 rejection is a retained mutant.
Original IFINDEX UINT32_MAX becomes signed -1 and broadcasts; original WIPHY
UINT32_MAX does not broadcast because the separate presence flag stays set.
These are exact-train allocation/data-domain checks, not a new production
protocol policy or kernel identifier-wrap/lifetime test.
The actual libnl conversion API receives aligned allocated message storage in
these tests; arbitrary misaligned containers/pointers are not claimed covered.

Original libnl's last-duplicate-wins and malformed-tail-success behaviors are
preserved. A separate tail-characterization subprocess requires exactly the
real parser's expected stderr and success result; ordinary positives must have
empty stderr. Original unsafe payload/scalar behavior is demonstrated using
explicitly zero-padded allocation capacity, not intentional out-of-allocation
reads. This does not establish a real device fault or exploit.

Actual kernel/host enums are compiled independently with namespaced *analysis*
symbols (not wire aliases): local kernel MU command160/attr346 differs from host
MU161/attr351, and host160 is incumbent. Safe counterexamples show that raw13,
full16 IE, or IE shape cannot select a usable protocol. The real BSS decoder
accepts attr351/full16 and misreads its prefix as raw data; global has no MU case;
genuine incumbent control still reaches its original consumer. Old BSS delivery
uses `drv->ctx`, not the selected secondary BSS context.

## Quality Gates And Coverage

Plan MD01: physically short/minimum/declared/received framing, malformed NLA and
aligned span, capacity distinction, original parser-tail characterization.
MD02: identity widths, zero/foreign/missing/conflicting/duplicate identities,
flags, duplicate IE, strict radio schema and real policy min/max.
MD03: exact IE length/prefix, raw13 rejection by typed decoder, distinct AC
mapping; original full16 misparse is retained as a baseline counterexample.
MD04: full original dispatch/reply/queue bodies with the explicit boundaries
above. Internal assertion tags `MD03-route-*` name route tests, not plan MD03.
MD05: per-iface canonical ownership, multiple drivers/ifaces, different ctx,
dedup, canonical present/missing/duplicate, same validated radio, foreign ctx,
null caller topology, secondary eligibility and a modeled station-role exclusion.
The prototype requires caller-owned stable objects throughout the event. Null
iface/conf/bss0/BSS/member mismatch is rejected, but concurrent teardown and
dangling pointers cannot be proved by these guards and remain unsupported.
MD06: all 4096 states, STA counts, nibble wrap/high bits, repeated events.
MD07: real beacon iteration/failure, projected CSA/CCA gates, real IE and WMM
stable/changed regulatory count. Full beacon builder and live driver are gaps.
MD08: both old ABI values, legacy shape ambiguity and genuine incumbent.
MD09: actual AP AX guard and supplicant default projections; separate real
AX-off header incompatibility. Whole supplicant/mixed-process/BE-MLO unsupported.

GCC ordinary and Clang ASan+UBSan must compile without any diagnostics and run
without stderr. LeakSanitizer is unsupported on this macOS host and is explicitly
off, not claimed tested. Each of 26 directed mutants must compile cleanly and
exit86 with exactly its specified runtime assertion, empty stderr. Compile
failure, signal, generic nonzero exit, sanitizer report or wrong assertion never
counts as a semantic rejection. Semantic and nonsemantic exit canaries exercise
that distinction. All commands, stdout/stderr, exit status, C/binary hashes and
exact assertions remain in fresh evidence. Failed development rounds remain;
no old PASS is reused as final evidence.

Extracted libnl-tiny code retains its LGPL-2.1 provenance in the source archive;
hostapd source retains its BSD provenance. All original headers/full files are
saved beside the generated test projections for review.
