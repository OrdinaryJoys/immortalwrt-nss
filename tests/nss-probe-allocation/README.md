# Bounded NSS probe allocation transaction

This is an offline host test of the early, unpublished dummy-netdev allocation
transaction in patch 030. It consumes **actual prepared driver source**, not a
reimplementation of probe, and never applies production patches or executes
scripts/binaries from an input tree. Python 3.9+ and a native C11 compiler are
the only dependencies. No target toolchain, network, device, cloud, or Git
operation is performed.

## Run

From this directory, with independently prepared before/after driver trees:

```sh
python3 -B test_runner.py -v
python3 run.py --baseline /absolute/baseline/source \
  --candidate /absolute/candidate/source \
  --output /absolute/audit/new-clang-run --cc clang
python3 run.py --baseline /absolute/baseline/source \
  --candidate /absolute/candidate/source \
  --output /absolute/audit/new-gcc-run --cc /opt/homebrew/bin/gcc-16
```

`--output` must not exist and must not overlap either source tree or this test
directory. Source files are hashed before and after execution. Existing output
is never reused. `--cc` accepts one executable, not shell syntax. ASan and UBSan
are enabled by default; `--sanitizers none` is an explicit, reported fallback
for a compiler without sanitizer runtime support. There is no silent fallback.

Compiler flags include `-Wall -Wextra -Werror`. The sole warning exception is
`-Wno-unused-parameter`: the unchanged HAL IRQ registration function has an
unused `netdev` argument, and logging-only arguments lose uses in host logging
macros. No type, conversion, pointer, format, uninitialized, or return-value
diagnostic is suppressed. All compile stderr must be empty. Leak detection is
disabled because the owner model uses static tokens, not allocated kernel
objects; live/foreign/double-free checks are explicit runtime assertions.

## Executed Code And Substitutes

The runner extracts complete definitions of `nss_hal_firmware_load`,
`nss_hal_clean_up_irq`, `nss_hal_register_irq`, `__nss_hal_probe`, and
`nss_hal_probe` from each supplied `nss_hal/nss_hal.c`. Bodies and conditional
compilation blocks are unchanged; original line locations and license are
retained. Missing, ambiguous, or unbalanced definitions are errors. The
IPQ807x IRQ/client/ring limits come from each tree's `nss_core.h` and must
match the reviewed 10/12/15 bounds. This is not preprocessing the entire driver
or compiling against real kernel types.

`fixture.c` supplies small host structures and stateful substitutes for:

- Common/core provider acquisition, enabled state, probing-device ownership,
  common-init publication, and the core0 regulator borrow.
- Pdata, map ownership, real loader copy/release into a host byte array, and
  committed meminfo tokens. Meminfo internals and partial allocation failures
  are **not** executed or certified.
- Dummy allocation, local/context owners, foreign tokens, and exactly-once free.
- IRQ ownership and NAPI add/enable/disable/delete. The failed request helper
  adds then deletes NAPI as the reviewed IPQ807x helper does; generic HAL
  registration and cleanup bodies execute unchanged for every successful prefix.
- A clearly named **modeled** failed-probe devres suffix. This is not actual
  Linux driver-core execution, platform PM, allocator internals, or real provider
  behavior. The model retains enabled state/global borrowing after managed
  release to avoid pretending those unrelated lifetime problems are fixed.

## Matrix And Oracles

Each compiler executes 152 candidate cases: 70 non-DT and 82 DT, on both cores.
An independent baseline-reference build runs the same 152 cases under the old
contract, including the old late-dummy-OOM zero return.

- Warm/cold success, common failure, firmware error/defer/map failure,
  clock and meminfo failures, core-reset failure, closed-group admission.
- All ten IRQ request failure positions on both cores in DT and non-DT.
- DT missing-node/pdata failures, warm and cold.
- 36 admitted dummy-OOM cases, including simultaneous prefix errors and
  nonempty existing target/sibling/global state; four additional OOM injections
  behind the closed-group gate must never reach the allocator.
- Prefix failures preserve the foreign dummy owner and release only the new
  local owner. OOM compares entire context/device snapshots and exact traces:
  only lock/alloc/unlock, with zero NSS acquisition/publication or managed release.
  Sibling context and foreign token preservation are checked in every case.
- Successful transfer retains the dummy, enables all IRQs, initializes callbacks
  and rings, and reaches reset/bootwait. Failed transfer cleanup requires
  NAPI disable/delete and IRQ release before the dummy is freed once.

There are **224 non-OOM phase comparisons across 112 cases**. Compare every
event in order and the pointer-normalized state vector at probe return and
after the modeled failure suffix. Only `alloc` and `free-local` trace events,
their counters, and assertion counts are omitted. Return codes, owned frees,
all represented context fields, firmware bytes, map/pdata/provider ownership,
handler/reset activity, and per-IRQ/NAPI state remain comparable. This is not
timing, scheduler, allocation-pressure, or hardware equivalence.

**20 negative executions** must first compile successfully, then exit 86 with
one exact assertion line and empty stdout. Crashes, timeouts, compiler errors,
sanitizer reports, wrong assertions, or unexpected passes fail the suite.
There are 24 fresh executables per compiler: four reference/candidate builds,
two baseline-against-new-contract controls, and 18 applicable mutation builds.
DT-only mutations are not run or counted in non-DT mode.

| Mutation | Selected case | Required assertion |
| --- | --- | --- |
| Original baseline, new contract | dummy-oom-cold | oom-no-provider |
| OOM returns zero | dummy-oom | return-errno |
| Provider before allocation | dummy-oom-cold | oom-no-provider |
| Omit local free | firmware-error | local-owner-released |
| Retain local alias after transfer | irq9-fail | dummy-live-on-free |
| Publish before firmware | firmware-error | foreign-owner-preserved |
| Free foreign context dummy | firmware-error | free-only-owned-dummy |
| Lose local owner on common failure | common-fail | local-owner-released |
| Lose local owner on missing DT node | no-node | local-owner-released |
| Lose local owner on pdata failure | pdata-fail | local-owner-released |
| Omit IRQ-owner free | irq9-fail | irq-owner-released |

`test_runner.py` also tests comment/literal-safe extraction, preserved
preprocessor branches, duplicate/missing definitions, unique mutation anchors,
backend bounds, strict negative acceptance, and differential-oracle sensitivity
to state/errno/event/order/matrix changes. These are runner tests, not additional
probe scenarios or runtime mutation kills.

## Evidence And Limits

Each run retains `provenance.json`, complete input hash manifests,
`commands.json` (argv, cwd, environment, return codes), compiler identity/hash,
extracted C, copied fixture, fresh binaries, compile/run stdout/stderr,
structured observations, `results.json`, and `artifacts.json` hashes.

The runner rechecks the complete test asset set/content and compiler executable
around each build/run and before PASS. Each variant's `bindings.json` binds its
generated source/fixture/bounds before and after compilation, the freshly built
binary immediately after compilation, and all four files before and after
execution. All previously executed source/binaries are rechecked before PASS.
Changed, added, removed, or substituted assets fail the suite; unit tests cover
changed content (including same-size changes), additions, and removals. These
pre/post checks detect observed drift, not an adversarial swap-and-restore that
occurs entirely between checks.

The guarantee is bounded dummy ownership and OOM noninterference only. Real
firmware execution, FW/DMA cessation, provider lifetime, platform/driver-core
prefix/suffix behavior, optional feature handlers, other SoC backends,
concurrency, live-device reprobe, target/kernel builds, flash, and reboot remain
unverified. Foreign sentinels test noninterference, not live-device reprobe
support. Later non-OOM failures can still have committed backing or borrowed
resources; matching the baseline does not make that behavior safe.
