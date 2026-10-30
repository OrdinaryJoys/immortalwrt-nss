# MCS control contract regression

This is a native-host function fixture, not a kernel, module, target, firmware,
socket, hardware or performance test. Do not run programs from sealed evidence.
Supply a fresh prepared baseline and candidate with the exact qca-mcs source
pin and the complete local patch chain applied without fuzz or offsets.

```sh
python3 -B tests/test-mcs-control.py /fresh/candidate/qca-mcs \
  --baseline /fresh/baseline/qca-mcs \
  --linux-netlink /fresh/linux-v6.18.38/include/uapi/linux/netlink.h \
  --linux-ip-header /fresh/linux-v6.18.38/include/uapi/linux/ip.h \
  --linux-ipv6-header /fresh/linux-v6.18.38/include/uapi/linux/ipv6.h \
  --cc gcc-16 --mutations --output /fresh/evidence/gcc
python3 -B tests/test-mcs-control.py /fresh/candidate/qca-mcs \
  --baseline /fresh/baseline/qca-mcs \
  --linux-netlink /fresh/linux-v6.18.38/include/uapi/linux/netlink.h \
  --linux-ip-header /fresh/linux-v6.18.38/include/uapi/linux/ip.h \
  --linux-ipv6-header /fresh/linux-v6.18.38/include/uapi/linux/ipv6.h \
  --cc clang --sanitize --mutations --output /fresh/evidence/clang
```

The runner extracts mc_api.h, eleven complete private structures, the actual
mc_netlink.c translation unit before module initialization, actual source
filter functions and the complete ECM get-interface consumer chain. The
supplied Linux nlmsghdr, iphdr and ipv6hdr structures are extracted; the host
struct-group macro and little-endian profile are explicit substitutes, with
IPv4/IPv6 source offsets and header sizes asserted. Source/fixture/
compiler identities and every command result are recorded in RESULT.json.
Missing or ambiguous extraction, positive diagnostics, sanitizer findings,
unexpected compilation failures and missed semantic negative controls fail.

Positive coverage includes all 22 commands, fixed actual-byte bounds and
legacy buf_len=0, the observed igmpproxy declared-4/actual-36 ENABLE request
with flags=0, malformed headers/arrays, packed consecutive ENCAP elements,
outer-count clamps, nested source bounds, bounded source consumers, ACL
update/deletion, GET capacity floor/zeroing/metadata, MDB internal-count
validation, event initialization/routing and selected allocation/ref failures.
Actual ECM IPv4/IPv6 INCLUDE/EXCLUDE hit/miss, packed address comparisons,
internal flood source counts and zero destination capacity are exercised.
The ENCAP lookup has a nonmatching first packed entry and a matching second
entry with distinct ifindex, MAC and source bytes; the stored full entry is
compared. Nonempty MDB tables exercise IPv4 and IPv6 source serialization,
and nonempty router-port lists exercise both protocol lists in order. Each
MDB/router consumer scans byte capacities through the full table plus one byte,
checking complete-item floor, status, sizing, item contents and cleared tail.
The missing-instance request uses DEBUG, not ENABLE, and verifies the actual
MC_DEV lookup, failure status, absent effects and retired references. Nonempty
SET_NOTIFY requests check callback family, order and exact group address;
an invalid last group must cause no callback. Fixed commands also check their
actual value, mask, timer, ACL, attach/detach and MDB-delete effects.
The real packet-header helper and private raw-address helper retain distinct
contracts. A capability stub requires nonzero trusted sender portid before it
can run; the unicast stub refuses kernel destination zero. This models the
reviewed endpoint restriction, not the Linux kernel's NULL-file crash itself.
MLD-on and MLD-off are separate profiles. The old MLD-off DEL_MDB translation
has an unguarded ip6 member and is an expected *compile* counterexample; only
the old MLD-on source supplies executed old-handler counterexamples. The old
ECM semantic counterexample runs only with the ordinary compiler, since old
packed source loads can independently trip sanitizer alignment checks before
that assertion. The candidate runs both ECM families under sanitizers.

The smaller HOST_JIFFY_MAX profile exercises the range boundary numerically
on the same LP64 host. It is not a 32-bit ABI, ULONG overflow, kernel timer or
target-config test. HZ=100 and the host jiffy limit are explicit substitutes.
Negative controls include permission removal, shared response buffers,
untrusted portid, missing header/declared/source bounds, uninitialized event,
unbounded MDB source count, overlapping deletion, wrong MLD update index,
u32 interval truncation, jiffy-limit bypass, short-circuited ACL sizing,
zero endpoint guards, ECM address/header mixup and zero-capacity writes.
A separately labeled sanitizer negative restores an unaligned IPv4 load;
its expected diagnostic is not counted as a semantic-negative runtime pass.

Transport/capabilities, skb references, lists (MC_HASH_SIZE=4), timers,
devices, callbacks, locks and RCU are deterministic host substitutes, not
Linux concurrency or credential implementations. checked_memcpy explicitly
rejects overlap; this is not a claim that ordinary libc detects it. An old
function or negative control may stop before later cases. Clang ASan/UBSan
runs halt on errors; leak sanitizer is disabled, while modeled allocations
and references have explicit ledgers. Warning exceptions are listed in the
runner and are not full-module warning qualification.
Semantic negatives declare an exact allowed-and-required diagnostic set and
exit type. Every stderr line must be a declared FAIL or HOST_CONTRACT marker;
ordinary failures must match the JSON failure count, and fatal controls must
end at their sole declared invariant without a JSON summary. The baseline ACL
control permits exactly its known MLD-update failure and overlapping-copy
invariant, not arbitrary trailing failures. The runner tests this oracle with
unexpected-marker, substring, exit, signal, sanitizer and summary controls.
Counter records observed per-marker counts; it does not compare a complete
independent expected multiset for each marker or scenario. The checked contract
is the exact marker set, exit type and total ordinary FAIL count, not that
stronger per-scenario multiplicity claim. An unknown fixture testcase can
return zero cases with exit zero; the runner's positive minimum-case/check
gate rejects that result. This is not general-purpose CLI safety validation.
Function-scoped mutants target second-entry selection, MDB/router floor and
contents, missing-instance status, callback addresses and DSCP masking.

These additions are authored test completion, not an independent review or
self-approval of the production patch. Fresh output directories preserve
failed attempts as well as later successful runs. The r8 review and evidence
remain historical and are not overwritten by this completion work.

Patch 021 keeps the wire structures, low raw command numbers, flags=0
behavior, fixed SET compatibility and explicit privileged event destination.
It adds an initial-user-namespace CAP_NET_ADMIN requirement to this management
endpoint, including GET; unknown unprivileged query clients are not certified.
No unconditional Linux-bridge master predicate is added because the existing
OVS path uses the generic device attachment mechanism.

Event destination zero is explicitly rejected without changing the previous
destination, and emission to zero is defensively refused. It is not redefined
as disable; the actual sentinel remains MC_INVALID_PID. Nonzero high-bit
proxy destinations are retained. Global recipient ownership/portid
reuse, real userspace event receivers, attach/detach/timer lifetime, the full
MCS packet engine and target/runtime/performance qualification remain open.
READ_ONCE/WRITE_ONCE is not a recipient or callback lifetime proof.
