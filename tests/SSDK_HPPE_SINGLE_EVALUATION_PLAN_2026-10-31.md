# HPPE single evaluation and first-error preservation

Base b863e01676b67e1391b8366cc4f6b3e8bbb048c6; exact SSDK pin
d9a196497ecee2530722d906e0efe1b7408b6ef6 plus25 patches/release15.
No make/target/module/firmware/cloud build, push/main/Release or device.
Only source preparation and fresh isolated native host fixtures.

## First increment: FAL-C05

The real shared SW_RTN_ON_ERROR operand is evaluated in both the condition
and return on failure. HPPE passes calls with side effects, including the
port-info allocator: failure followed by a successful second call can return
SW_OK before remaining properties/API/dev_clean publication. Two different
errors also discard the first error. Persistent failure still repeats work.

Evaluate each of the ten HPPE call expressions once into a local sw_error_t
rv before the existing macro: four in hppe_init, five setter branches in
hppe_portproperty_init, one in hppe_cleanup. Keep the shared macro unchanged.
Preserve order, loop/bitmap policy, all actual guards, successful values and
callback installation. Do not add a root fatal return or any new cleanup,
free, allocation, owner flag, metadata reset or public ABI change.

The setter/map/cleanup helpers normally cannot fail on the admitted valid
path; artificial failure schedules must be labeled as such. Port-info
allocation OOM is a natural source failure. The existing valid-ID-only
cleanup contract is not expanded: do not execute invalid-ID cleanup to
obtain a crash or claim its indexing is repaired.

## Required checks

- Exact25->26 complete692-file derivation at declared full context/zero
  offset; only src/hsl/hppe/hppe_init.c differs, recipe15->16 only, pin/DP
  and build lock unchanged. Previous037 tests are not26-layer qualification.
- Complete actual HPPE init/property/dev/cleanup bodies and real shared
  macros, actual error/enum/capacity types and property helpers where feasible.
  Any cfg/API/OS leaves must be explicit host models, not target ABI proof.
- Four KERNEL_MODULE/USER_MODE truth-table profiles, including the combined
  mode that skips property/API work but still initializes cfg/metadata.
- Transient and persistent port allocation failure: exact first error and
  allocator/call counts, no falsely successful API installation. cfg OOM,
  no CPU bit, lowest of multiple CPU bits, CPU0/15/high-only bits, sparse/
  overlapping LAN/WAN/inner and deliberately different cfg/global sources.
- Each five property cases and each init/cleanup call site gets single
  evaluation/first-error coverage with named artificial fault schedules;
  successful real-helper trajectories remain identical to25.
- Failed init retains the pre-existing ownership gaps explicitly: do not
  fake all references/allocations closed. Cleanup error must neither call
  cleanup twice nor free cfg as if its dependency had retired successfully.
- Full independent return/action/state/callback/ownership oracles, exact
  compiler/runtime classification, safe old-source witnesses separate from
  source mutants; no compiler/signal/sanitizer/timeout negative credit.
- Frozen assets/input/generated/expected inventories and tail hashes;
  Python -O, fresh GCC and Clang ASan/UBSan with activation canaries. LSan
  remains unqualified. Independent source and test quality review required.

## Second increment: ownership design, not blind cleanup

After first-error behavior is established, resolve independently occupied
hppe_cfg and private port_info slots before destructive writes. Distinguish
fresh, borrowed, repeated and combined-mode cases; use additive scoped
acquisition or an explicit reject/preserve policy without changing other
chips' shared reset semantics. Outer HSL cfg, static metadata/API, shared UK,
adapter and PHY/provider ownership are separate. Keep dev_clean until its
dependent owner retirement is complete and do not infer ownership from
non-NULL or an init-success flag alone.

Current ssdk_init still can mask FAL error with PHY success and root errno
handling still collides at SDK -19/Linux -ENODEV. Correct HPPE return values
do not repair these callers or make partial construction failure safe for
every subsequent reader. Source/host acceptance is not deployment approval.
Resource rollback, full root/target/kernel/HW/FW/DMA/RCU/runtime/performance
remain open until their own exact integration and validation are complete.
