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

An old-tree baseline must fail while preserving its normal ring/descriptor
signature. The six original compiled negatives remain: plain-unlock,
double-enable, missing-unlock, early-enable (missing the entry BH disable),
missing-access-end and missing-descriptor. Three additional precise negatives
exercise the independently reviewed gaps: bh-enable-before-unlock,
publish-before-descriptor and omit-source-module. All nine must compile,
exit 1 and report failures; the new order negatives must also fail their
specific BH-order or publication checks. Descriptor-mutating negatives must
change the normal signature; order-only negatives must preserve it.

The larger seed/address set changes the signature. No historical signature,
including cf5364152bbdd55a, qualifies this expanded suite. Every --baseline
run recomputes and compares candidate and baseline signatures using the same
current fixture; without --baseline there is no cross-version comparison.
The digest still samples final storage/head/reap state, not temporal order.
The boundary and BH-order checks provide separate observations.

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
