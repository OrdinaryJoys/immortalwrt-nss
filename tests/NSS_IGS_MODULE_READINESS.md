# IGS Module Readiness: Bounded Host Regression

Author status: Python AST/syntax and actual-source context checks only. No C
compilation, executable run, sanitizer run, kernel/target build or regression
execution was performed by this worker. All runtime expectations below await
the parent worker's GCC/Clang and nine-invocation CI validation.

Parent validation, 2026-10-26: final runner passed GCC 16 and Clang
ASan/UBSan, each with 28 compile/run variants, 10 candidate scenarios /
779 assertions / 0 failures, baseline18's 290 expected assertion failures,
22 runtime mutation instances and 10 unchanged API-trace comparisons.
Default `cc` with the CI arguments passed 25 variants (no optional baseline).
Seven CLI refusal controls and the nine-call workflow's 277 binding tests
passed locally. These are not a GitHub Actions, target or device run. The
first Clang attempt aborted before `main` because the draft forced
unsupported LeakSanitizer; its failure evidence is retained, not accepted as
a negative control. The final runner removes only that forced option and
retains ASan/UBSan and strict abnormal-exit rejection. Evidence is under
`/Volumes/FX-MD87/Review-AX6/audits/20261026/igs-module-ready`.

## Scope

The 019 change moves the void, allocation-free `nss_ifb_init()` ahead of the
first notifier registration. Publication is allowed during registration and
immediately on successful registration, before that API returns. There is no
assumption that callbacks must wait for module init to finish, or that COMING
automatically blocks acquisition.

The runner extracts complete actual `nss_mirred_init_module()` and
`nss_mirred_cleanup_module()` from `nss_qdisc/igs/nss_mirred.c`, complete actual
`nss_ifb_init()` and the full static struct-with-instance `msg_response` from
`nss_qdisc/igs/nss_ifb.c`, and the actual `nss_cmn_response` enum from the
driver's `exports/nss_cmn.h`. It does not substitute handwritten function
bodies. The existing lexical extractor and the sync runner's
`actual_declaration` helper are imported as definitions, never via their main
entry points. Both dependencies are archived and hashed.

Original function bytes and internal CPP envelopes are retained. The host
compiler selects 4.19.0, 5.4.0 and 6.18.38 independently. This is conditional
branch coverage, NOT three kernel compatibility builds. Notifier/action/NF
APIs and opaque API objects/types are substitutes. Semaphores, locks and
completions are initialization flags/counters, not kernel implementations.
Modern pernet/NF internals are opaque and are not run or claimed covered.
There are no real firmware calls, callbacks, devices, threads, IRQs, RTNL,
memory-ordering tests or module reference acquisitions.

The guard layout must be exactly the current real sem/done/lock/response/
expected_interface/expected_type/pending declaration. The real enum is kept;
there is no invented NACK constant. Pending is poisoned true before each
scenario, then the real helper must establish false. Expected interface/type
and response are recorded without inventing initialization absent in source.
Primitive init while any modeled resource is published fails explicitly.

Owner save/clear order is recorded, not fixed or used as a publication gate.
Owner late publication, cleanup clearing owner first, S08 same-pair late
replies, late callback/app_data lifetime, whole-module lifetime and firmware
compensation remain OPEN. No real concurrent execution is claimed.

## Invocation

CLI: positional `clients`, optional `--baseline`, `--driver`, `--cc` (default
`cc`), `--mutations`, `--sanitize`, and required `--output`.

**CI must explicitly pass `--driver "$nss_drv_dir"`.** A build directory's
driver is not assumed to be a sibling named `prepared-driver`. The default
`clients.parent/prepared-driver` is only convenient for the existing local
audit layout. Driver input must be a prepared directory containing the real
`exports/nss_cmn.h`; the runner never prepares/downloads sources. The parent
owns missing/wrong/old/unquoted-driver CLI negative checks and CI edits.

Example for the parent to execute, not an author-run command:

```sh
audit=/Volumes/FX-MD87/Review-AX6/audits/20261026/igs-module-ready
source=/Volumes/FX-MD87/Review-AX6/worktrees/immortalwrt-nss-pci-ssr-shutdown-20261019
nss_drv_dir="$audit/prepared-driver"
python3 "$source/tests/test-nss-igs-module-readiness.py" \
  "$audit/candidate-clients" --baseline "$audit/baseline-clients" \
  --driver "$nss_drv_dir" --cc gcc --mutations \
  --output "$audit/module-gcc-new"
```

Use a different new output directory for Clang and every sanitizer run.
`--cc` is one executable, not a shell expression. `--sanitize` enables ASan
and UBSan, nonrecovering mode and halt-on-error options. It does not force
LeakSanitizer, which is unsupported by the macOS runtime; no leak-detection
coverage is claimed. The runner rejects
existing output paths, including dangling symlinks, and output overlapping
source/driver/repository trees. It never overwrites prior evidence. Inputs and
Python dependencies are rehashed at completion; drift makes the result FAIL.
Generated C and binary hashes are also checked around execution.

## Cases and Oracles

Each branch runs `success`, `notifier_fail_retry`, `action_fail_retry`; 4.19
also runs `nf_fail_retry`. Failure scenarios inject distinct negative host
codes (-41/-52/-73), require exact propagation and balanced notifier/action/NF
ledgers, then retry successfully without resetting the scenario's resource
ledger or synchronization counters. Only successful init calls cleanup. The
actual cleanup function is compiled and exercised after success and retry.

Every applicable registration probes sem(count=1), lock, completion(tokens=0)
and pending=false at entry and successful publication. These are deterministic
early-publication observations, not executed asynchronous callbacks. Failed
registration never acquires its resource. Legacy NF reject/error/unwind and
modern two-argument action registration/unregistration are separate branches;
unused legacy API implementations are CPP-excluded on modern branches.

An independently constructed expected API-event sequence checks registration,
reject, error logging, unregister, owner save/clear and return order. The Python
reader also checks observed return/ledger/API traces against failure records.
Candidate and baseline observable signatures must match for every scenario
and attempt, excluding private initialization/probe timing. Baseline must
fail the four designated `notifier.entry` readiness checks in every scenario;
only readiness/reinitialization assertion categories are allowed. It is
expected-negative evidence, never candidate qualification.

The extracted cleanup must match the pinned author-read baseline18 SHA-256
`8d824447dcf7c7de41f044eaa05ac73876bf5f162925f78dd3120ae9b671e8f2`
(520 bytes, including the extractor's final newline), even without
`--baseline`. With baseline supplied, cleanup/helper/declaration must be
byte-identical, and module init must equal exactly the baseline with only the
observed 019 declaration split, explanatory comment and call relocation.
This preserves error-message literals as well as all other statements/CPP.
Without baseline, no dynamic differential comparison is claimed.

## Negative Controls

There are eight exact-context mutation definitions, applied only to the
extracted candidate module init. Cleanup/helper/declaration stay unmodified.
Seven run on all three branches; NF unwind omission runs on 4.19 only:

- `omit_init`: success / attempt 1 / `notifier.entry.sem_ready`.
- `after_notifier`: success / attempt 1 / `notifier.entry.sem_ready`.
- `after_action`: success / attempt 1 / `action.publish.sem_ready`.
- `success_tail`: success / attempt 1 / `notifier.entry.sem_ready`.
- `reinit_published`: success / attempt 1 / `init.not_published`.
- `omit_action_failure_unwind`: action_fail_retry / attempt 1 / `attempt.resources_balanced`.
- `wrong_action_failure_return`: action_fail_retry / attempt 1 / `attempt.returncode`.
- `omit_nf_failure_unwind`: nf_fail_retry / attempt 1 / `attempt.resources_balanced`.

The omit-init variant retains a void use of the real helper's address to avoid
an unused-function false negative. No warning suppressions are used:
`-std=gnu11 -O0 -g -Wall -Wextra -Werror`. API stubs are conditional to avoid
unused legacy functions in modern builds.

Every negative control requires compile rc=0, normal run rc=1, empty stderr,
complete ordered JSON, totals agreeing with explicit failure records, the
specified case/attempt/check, and an allowlisted failure category. Ledger
mutations may fail only within their designated failure/retry scenario.
Compiler errors, missing executables, timeout, signal, malformed/incomplete
JSON and sanitizer failures are never accepted as successful controls.
Compile timeout is 120 seconds; execution timeout is 30 seconds per variant.

Without optional inputs there are 3 candidate executables and 10 scenario
summaries. Baseline adds 3 executables/10 scenarios; mutations add 22
executables/74 scenarios. Maximum: 28 compile/run variants and 94 scenario
summaries per invocation. This is deliberately finite, not schedule fuzzing.

## Evidence and Handoff

`RESULT.json` contains arguments, scope/OPEN limitations, script/extractor/helper
hashes, full input-file and extracted-fragment hashes, mutation originals and
replacements, compiler argv/rc/timeout, raw stdout/stderr hashes, per-scenario
summaries, raw state records, exact assertion failures and differential
signatures. The new output directory also archives dependencies, full input
snapshots, extracted original C, actual response enum, each generated C file,
compiler/run stdout/stderr and per-command JSON results. A final artifact
inventory hashes all evidence except the self-referential `RESULT.json`.

`PASS_BOUNDED_HOST_MODEL_ONLY` requires every selected variant to meet its
specific oracle and every selected baseline signature comparison to agree.
Input/dependency hash drift overrides success. This label does not close any
OPEN item or imply a kernel/target build. The parent must run GCC/Clang,
sanitizers and the requested CI integration; this worker did not.
