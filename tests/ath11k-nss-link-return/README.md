# NSS link descriptor return qualification

Patch955 pairs the existing spin_lock_bh with spin_unlock_bh at the common
success/no-entry exit. It does not change descriptor, ring, offload or
firmware policy and does not solve callback lifetime or DMA quiescence.

The test extracts the complete prepared return function, descriptor setter
and HAL source-ring next-entry function. Descriptor structures, field masks,
enums and SRNG structure come from the same prepared headers. Explicit host
BH/spinlock/lockdep and MMIO access contracts replace kernel primitives.

Three selected ring indices, nesting0/1/4, two/three/eight-entry rings,
every initial slot and full/available cases run four repeated notifications.
Each combination runs with 68 word seeds: zero, all ones, A5/5A patterns,
and walking-one/walking-zero patterns for every one of the 32 bits. Input
addresses change between repetitions so reused slots must be updated.
Checks cover BH restoration, lock release, ring/reap indices, exact changed
descriptor bytes and untouched rings. The last BH enable transition must
occur after releasing all modeled locks; nested enables are not mistaken
for the last transition. At access_end, the contract checks the selected
ring, original slot, expected head/reap indices and descriptor bytes before
publication. The caller builds these expectations independently of the
extracted setter, including the no-write expectation for a full ring.
The begin/end contract also tracks the selected ring's lock as an open
transaction. Unlocking that lock before access_end finishes is a failure,
even if it is acquired again before publication. Releasing an unrelated
ring lock does not violate this selected-lock contract. Transaction state
is checked at begin/end and after each return, including the full-ring
path. The host still performs an invalid unlock after recording it, so the
negative's final storage signature remains comparable. The actual extracted
getter, setter and candidate/baseline return functions are not instrumented.

An old-tree baseline must fail while preserving its normal ring/descriptor
signature. The six original compiled negatives remain: plain-unlock,
double-enable, missing-unlock, early-enable (missing the entry BH disable),
missing-access-end and missing-descriptor. Three additional precise negatives
exercise the independently reviewed gaps: bh-enable-before-unlock,
publish-before-descriptor and omit-source-module. A tenth negative,
unlock-window, releases the selected lock after the getter and reacquires
it at the common exit before access_end; its real setter is unchanged.
All ten must compile,
exit 1 and report failures; the new order negatives must also fail their
specific BH-order or publication checks. The unlock-window negative must
fail only the dedicated unlock_window_failures check, once per call, with
transaction_state_failures, BH-order and publication counters still zero.
Descriptor-mutating negatives must
change the normal signature; order-only negatives must preserve it.

The larger seed/address set changes the signature. No historical signature,
including cf5364152bbdd55a, qualifies this expanded suite. Every --baseline
run recomputes and compares candidate and baseline signatures using the same
current fixture; without --baseline there is no cross-version comparison.
The digest still samples final storage/head/reap state, not temporal order.
The boundary, BH-order and transaction-lock checks provide separate
observations. The lock-window extension preserves the 68-seed normal
signature 236422c1ac845043; it adds observations, not descriptor semantics.

Use a new output directory and a completely package-prepared input:

```sh
python3 -B tests/test-ath11k-nss-link-return.py PREPARED \
  --baseline PRE955 --mutations --cc gcc --output NEW-DIR
```

Repeat with Clang and --sanitize. These are host contract results, not
Linux softirq scheduling, lockdep, target compilation, AX6/FW events,
teardown safety or throughput acceptance.
The MMIO boundary oracle does not execute the real access_begin/access_end
functions, model hardware consumption, or prove DMA visibility or barriers.
The full SRNG declaration still embeds substitute host lock/scalar types;
this is not complete target ABI qualification. Production descriptor OR
semantics, ring behavior and patch955 are unchanged by these test changes.
