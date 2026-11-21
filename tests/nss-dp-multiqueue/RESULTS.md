# Local Verification, 2026-11-21

## Results

| Saved run | Candidate | B12 baseline | Source mutations |
|---|---|---|---|
| results-clang-final, plain | 32/32 pass | 29 controls pass, 3 exact runtime failures | 13/13 exact runtime rejections |
| results-clang-final, ASan+UBSan | 32/32 pass | 29 controls pass, 3 exact runtime failures | 13/13 exact runtime rejections |
| results-cc-final, plain | 32/32 pass | 29 controls pass, 3 exact runtime failures | 13/13 exact runtime rejections |

All programs, including every mutation, compiled without diagnostics with
`-Wall -Wextra -Werror -Wno-unused-parameter`. Compile failure was not accepted
as rejection. Baseline and mutation failures returned exactly 86 and the
designated case/assertion marker; sanitizer failures/signals/timeouts are
distinct and would fail the run. Result-oracle negative controls also reject
wrong exit codes, wrong markers, noise, missing traces and false PASS records.

The sanitizer clean canary returned zero without diagnostics. ASan heap-OOB and
UBSan invalid-shift canaries each emitted their own required diagnostic and
returned exactly 98 before the complete fixture matrix ran.

`cc` and `clang` both report Apple Clang 17.0.0
`clang-1700.0.13.3`, arm64-apple-darwin24.6.0. These are two driver-entry runs,
not independent compiler implementations.

## Baseline Witness

The unchanged B12 program compiled and executed the real DOWN takeover and
later open paths. In down-phy, down-no-phy and down-uninitialized:

1. After quiesce: queues `[1,1,1,1]`, absent, blocked.
2. After readiness while DOWN: queues `[1,1,1,1]`, present, not blocked.
3. After successful ndo_open: queues `[0,1,1,1]`, running.
4. Exact failure: `MQ_FAIL <case> queues-ready`, exit 86.

The candidate executes the same fixture with only the extracted activation
call changed and reaches `[0,0,0,0]` after open, without scheduling from start.
The other bits and failure paths are tested separately.

The `wake-instead-of-start` rejection is a design-fidelity check for this
successful-open change's retained start-without-scheduling semantics. It is not
a general claim that `netif_tx_wake_all_queues()` is incorrect; flow-control
recovery can appropriately use wake under a different contract.

## Binding and Evidence

The runner captures 37 complete source definitions/initializers per input.
Its pair check compares seven complete input files and permits only the single
activation-call delta in nss_dp_main.c. All 14 recorded file hashes were also
independently compared with the main task's existing
`/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/patch-replay-v2/RESULT.json`;
all matched. That replay record identifies B12
`8e73e59a440e80f5475d1147aca909f9459ba77f` and vendor
`d8f802f08fd8ff31057ba58edb20bbe448e7b505`.

- Baseline nss_dp_main.c SHA256:
  `b6fb3231cefa29234c0384864d4369154f8be2342795c049b4295d04622bbdf7`
- Candidate nss_dp_main.c SHA256:
  `dbd747a45508108df5bc3959982515e44cb4469a806ff1932d9ccb33e9d4a216`

Use [results-clang-final/RESULT.json](/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/results-clang-final/RESULT.json)
and [results-cc-final/RESULT.json](/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/results-cc-final/RESULT.json) for
complete commands, per-case outcomes, source/definition/asset hashes and the
artifact inventory. Generated C, executables, input snapshots, canaries and all
compile/run logs remain beside each manifest.

results-dev-01 is an intentionally retained failed development run: the new
fixture initially attempted open before completing DOWN readiness, and its
open-present assertion rejected that setup. The fixture was corrected to call
the actual readiness function before open. This was a test setup defect, not a
firmware failure. results-dev-02 passed the ordinary matrix before the final
prepared queue-count binding check was added; it is superseded by final runs.

## Evidence Relocation

All four generated directories were moved, not deleted or regenerated, from
the source test directory to:
`/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/`.
Their internal relative paths and every file's bytes and permissions are
unchanged. Original command logs, generated sources, binaries and RESULT.json
still contain historical absolute invocation paths; these were deliberately
not rewritten.

| Moved directory | Files | Bytes | Before SHA256 = After SHA256 |
|---|---:|---:|---|
| results-dev-01 | 69 | 436964 | `eb02724bfb0fb9686f4947eefd294ffdc1e2c859e5909bdcf7f291717a588ddc` |
| results-dev-02 | 373 | 2889894 | `9b435c23e94e1bd89d69a8270191cabccb72556451d0e6215bad981e5f75cb0a` |
| results-clang-final | 757 | 8807406 | `fb320bd74d64164ccfb801c9e81609d32785842de1ba8a387216f8a5ed834cd7` |
| results-cc-final | 373 | 2892052 | `66635f26024dd41b69194b31e40e1f0c25430e04898be8449596874f829a89d6` |

Total: 1572 regular files, 15026316 bytes. Both complete relative-path entry
lists were recomputed and compared, not just the pre-existing artifact
manifests. Tree hashes cover sorted entries with path/type/mode and, for files,
size/content SHA256; root location, timestamps and inode are excluded.
[MOVE-VERIFICATION.json](/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/MOVE-VERIFICATION.json)
records the precise canonical serialization, source/destination mapping,
before/after hashes and complete unchanged entry list. No tests were rerun.

## Write Set and Limits

During implementation this worker only created files below
tests/nss-dp-multiqueue and added one compatibility macro to
tests/nss-dp-containment/host_kernel_stubs.h. During final housekeeping the four
generated directories were relocated to the audit evidence directory, a move
verification manifest was added there, and only README.md/RESULTS.md were
updated in the test source directory. No runner, fixture or production code
was changed in this housekeeping step. The old
single-boolean fixture was not used as the four-queue oracle, and its prior
assertions were not changed. Existing containment acceptance is owned/run by
the main task; this worker did not duplicate it.

These results are extracted-production-C tests against sequential host API
substitutes. They establish the precise static multiqueue counterexample and
the candidate's behavior under the tested API contract. They do not establish
kernel scheduling/concurrency, target ABI, actual NSS/EDMA delivery, B12 runtime
root cause, performance, or device acceptance. No firmware build, CI or device
operation was performed. FW/DMA retirement, 035 and LIVE/unbind remain HOLD.
