# DP allocation rollback qualification

Run from the source repository after the complete locked package patch replay:

```sh
python3 -B tests/test-ath11k-dp-allocation.py PREPARED_MAC80211 \
  --baseline PREVIOUS_PREPARED_MAC80211 --mutations --cc gcc --output NEW_DIRECTORY
python3 -B tests/test-ath11k-dp-allocation.py PREPARED_MAC80211 \
  --baseline PREVIOUS_PREPARED_MAC80211 --mutations --cc clang --sanitize --output ANOTHER_NEW_DIRECTORY
```

The script extracts the entire `ath11k_dp_alloc` plus the real guarded ring,
bank, scatter and link cleanup functions. Descriptor layouts, ring limits and
both memory-profile sizes come from prepared headers. Setup, allocation, DMA,
locks and IRQ behavior are host API models, not actual hardware operations.

Both default and 512M profiles run the same 42 scenarios: successful setup,
idle-ring failure, three link-setup failure contracts, common-ring failure,
each TX-status allocation failure, cached/noncached cleanup and retry on the
same object without caller-side repair. Running the 512M host model does not
select that profile in the firmware configuration.

The resource ledger checks return values, all allocations, pointer clearing,
double-free detection and normal setup order. It executes cleanup after each
successful setup; that cleanup is not a qualification of the full `dp_free`.
Assertion-negative runs record leaks before emergency host cleanup, so they
stay sanitizer-clean without turning leaks into a positive result.

The parent's cached/noncached ledger variants exercise cleanup metadata; the
current actual WBM idle-ring type itself uses coherent allocation. The SRNG
test below separately verifies the real per-ring cache-selection branches.

Old source and four compiled mutations must fail runtime assertions. Compiler
errors, sanitizer findings, crashes and timeouts are not valid negative
controls. Every input and generated C file is hashed; outputs must be new.

These are sequential failure-injection tests. They do not establish kernel
concurrency, DMA lifetime, complete firmware recovery or measured performance.

Also run the complete SRNG helper qualification, whose rollback contract is
used by the parent model:

```sh
python3 -B tests/test-ath11k-srng-allocation.py PREPARED_MAC80211 \
  --baseline PREVIOUS_PREPARED_MAC80211 --mutations --cc gcc --output NEW_SRNG_DIRECTORY
```

It extracts full `ath11k_dp_srng_setup` and cleanup with actual enums and
parameter layouts. It covers all ring types, cached/coherent allocation,
stale cache metadata, clamping, HAL rejection, allocation failure and repeated
cleanup. HAL/DMA APIs remain models. Normal signatures compare fresh objects;
correcting stale cache metadata is an intentional change, not a claimed
unchanged behavior. The selected HAL implementation rejects an invalid ring
ID before publishing initialization; post-initialization hardware failures
are not injected or qualified here.
