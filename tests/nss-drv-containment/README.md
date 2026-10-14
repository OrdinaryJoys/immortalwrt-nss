# DRV actual-prepared-C host tests

This facility compiles and runs selected byte-preserved C definitions from an
already prepared DRV tree. It is not a replacement DRV state model. The entire
actual common workqueue unit is included with only include directives removed;
the actual private closing/lifecycle globals, registration/table functions,
HAL group drain/remove/admission helpers, structures and emergency poll are
extracted. Original preprocessor branches remain for the native C compiler.
Inputs and exact definition hashes, generated C, native binary, flags, cases,
test assets and diagnostics are recorded in each RESULT.json. Every source
snapshot and runtime asset is rechecked at the end of all macro variants.

## Counts and modes

Full comparison is 44 cases: original baseline 7 defect controls, exact
`NSS_HAL_IPQ807x_SUPPORT` candidate 20, actual candidate other-SoC legacy 7,
wrong-uppercase `NSS_HAL_IPQ807X_SUPPORT` legacy negative controls 7, and exact
IPQ807x without GENERIC 3. A control PASS asserts the historical defect remains
on an intentionally unmodified branch; it is not a repaired containment PASS.

Candidate-only is 37 cases (20 + 7 + 7 + 3), executes no original baseline,
and records that fact. Candidate and other-SoC inputs are never presented as
the old baseline. Baseline-only is 7 and explicitly candidate-INCOMPLETE.
Invalid modes fail before creating an output directory. CLI checks are 7,
shared lexical extractor integrity checks 7, and DRV extraction integrity
checks 3, separately from the C behavior cases.

## Coverage and explicit limits

Closing rejects enqueue; pending work is cancelled and a running actual worker
waits for a returning ACK substitute outside RTNL before IRQ cleanup. Duplicate
registration refuses before ndpp mutation. DOWN and UP registration invoke the
actual readiness call site without changing the host admin-state field. Normal
ops preparation and HAL registration are once-only. DP-only quarantine retains
registry/ndpp until receive drain. Repeated removal and late probe admission are
checked. Two mock contexts have active-poll and post-complete-tail phases held
with pthread conditions so registry clearing and IRQ free order are observed
deterministically, without sleeps or scheduling guesses.

The fixture deliberately uses reduced dimensions: two host core contexts,
two IRQ slots per context (actual fixed IPQ807x header selects ten), four
registry/DP interface slots, and primarily port ifnum 1. Normally slot 0 is
active; a boundary case adds slot 1 on a context whose reported num_irq is 0.
The actual MAX-based loop executes over these reduced fixture dimensions. It
does not establish coverage of all ten real slots or all physical ports, and
two pthread-backed contexts are not real dual-core hardware testing.

The actual emergency poll is tested with a returning host notifier: old and
non-IPQ branches retain ownership, while the repaired IPQ branch calls actual
`napi_complete` after the notifier returns, without rearming IRQ. A held
notifier makes cleanup wait; a post-complete mock tail makes grace wait before
IRQ free. Legacy cleanup controls use an explicitly artificial fixture release
only to finish the test; the actual legacy poll did not complete. No real
coredump notifier, firmware, panic, crash, IRQ or router is invoked.

Kernel workqueues, RTNL, spinlocks, NAPI ownership, grace and DP APIs are host
substitutes. Full ordinary poll bodies, full probe setup, platform-driver
initializer, other registered clients and general driver/module lifetime are
not executed. This is not Linux scheduling, RCU, lockdep, ABI, target-kernel or
AX6 runtime acceptance. DP start/restore/override internals remain a separate
actual-C DP test facility. Native replay here is macOS arm64/Apple clang 17;
Linux/Python 3.9+/native C compiler/pthreads can rerun offline, but Linux is not
claimed as executed by this test author.

## Replay and installation

Run the runner and its unchanged sibling assets together. It performs no
network access, download, package preparation, target build or CI dispatch.
Use an existing already prepared source tree as input. `--output`, if supplied,
must name a new directory; otherwise a new temporary result directory is used.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test-nss-drv-containment.py \
  --candidate-only --candidate /absolute/actual/make-prepared-drv \
  --output /absolute/new-result-directory

PYTHONDONTWRITEBYTECODE=1 python3 test-nss-drv-containment.py \
  --baseline /absolute/original-prepared-drv \
  --candidate /absolute/candidate-prepared-drv

PYTHONDONTWRITEBYTECODE=1 \
DRV_HOST_BASELINE=/absolute/original-prepared-drv \
DRV_HOST_CANDIDATE=/absolute/candidate-prepared-drv \
python3 -m unittest discover -s . -p 'test_*.py' -v
```

Install these siblings without embedding or rewriting: runner,
extract_prepared_c.py, driver_kernel_stubs.h, driver_nss_scaffolding.h,
driver_api_fixtures.c, driver_emergency_cases.c, driver_baseline_cases.c,
driver_candidate_cases.c, driver_nongeneric_cases.c, test_candidate_only_cli.py,
test_driver_extraction.py, test_extract_prepared_c.py, and this README.md.
Only the runner may be renamed if the installation chooses another entrypoint;
the CLI check file refers to its current runner name, so preserve it unless the
parent explicitly updates that packaging check. Case assets remain required
even in candidate-only mode because legacy negative controls execute them.

The old DP tests/seal and all temporary earlier DRV runs are preserved. No
source-worktree, production, router, CI, commit or push action was performed
by this test author. See TESTS-FREEZE.md for the final hashes and replay records.
