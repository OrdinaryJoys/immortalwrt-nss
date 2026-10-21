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
Checks cover BH restoration, lock release, ring/reap indices, exact changed
descriptor bytes and untouched rings. An old-tree baseline must fail while
preserving its normal ring/descriptor signature. Six compiled mutations
exercise mismatched/missing unlock, enable order and publication omissions.

Use a new output directory and a completely package-prepared input:

```sh
python3 -B tests/test-ath11k-nss-link-return.py PREPARED \
  --baseline PRE955 --mutations --cc gcc --output NEW-DIR
```

Repeat with Clang and --sanitize. These are host contract results, not
Linux softirq scheduling, lockdep, target compilation, AX6/FW events,
teardown safety or throughput acceptance.
