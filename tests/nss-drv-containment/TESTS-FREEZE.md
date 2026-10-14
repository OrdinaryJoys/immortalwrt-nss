# DRV host actual-C tests freeze

Frozen 2026-10-09 15:39 UTC, after fresh final replays following the previous
interruption. Test source/assets and final records are frozen pending explicit
peer/root-requested repair. Old evidence and temporary earlier runs remain
unchanged; this is not a declaration of continuous background execution.

Actual input is original raw DRV
`6aa14c78e097b29c493ff2fef87e4d35906b2b5a` plus the author's repaired-context
20-package-patch baseline, and that prepared baseline plus final 023:
`92f2a80f43e74753d00103243c6156c95bb6b854b344b6018799ab2df9cd08d9`.
The actual candidate emergency-containing nss_core.c is
`e61bef2f7110dd6d5066dd0c7791dc0ddd822ac0ba2fc1b6d3ab47f19056619c`.
The candidate runner extracts 18 actual function definitions, four actual
structures and six actual private declarations; the whole actual common unit
preserves its private state and function bytes except include directives.

## Final records

- `final-full44/RESULT.json`:
  `a382b7e64ff38a2de312a26e3031cfbf43dcc74e5415ec303c12599c1f9d4477`.
  44/44 = original baseline defect controls 7 + IPQ candidate 20 + actual
  candidate other-SoC legacy controls 7 + wrong-uppercase macro negatives 7 +
  exact-IPQ non-GENERIC controls 3.
- `final-candidate-only37/RESULT.json`:
  `5e0cfb6ab821296e53368a8436cc96da0b0c241d62f9c27d762f51bee9e0369e`.
  37/37 = 20 + 7 + 7 + 3, no original baseline executed. All four runs point
  to the actual prepared candidate and have explicit roles.
- `INTEGRITY-REPLAY.md`: 17/17 = CLI 7 + DRV extraction 3 + lexical extractor 7.
  These are separate, not added to the unique C behavior count.

All final C compiler diagnostics and execution stderr are empty. Both modes
compile the same candidate C bytes. The generated candidate C SHA is
`80d09abae0e9c6d9f65e9737bb3702485e981a1ae17b19b3876dd1afda45d984`;
other-SoC and wrong-uppercase variants retain identical source C bytes
`54516a9bbe69d22d1be8bb3270656b19d651b69969af5b802224397ed30bb6fe`
with different compiler macro arguments; nongeneric generated C is
`a9afa34fcc6d0176fd9cd7762e9eb5efe9054d97cdefe9437ceb9968198b8785`.

## Installation assets and hashes

Preserve these sibling filenames/bytes when installing under the parent's
chosen `tests/nss-drv-containment/`. No result directories or native macOS
binaries are required for execution elsewhere.

```text
b759838d6cc515b7c5d96cd9068579f02e0ef8b6a819f13d52f5a6dea458bcc4  test-nss-drv-containment.py
40d7e906bc8bb0afd94ab60d76677a32c1ccec736dd56e71183b27bcabed53d2  extract_prepared_c.py
3075adec59209c287a8cd0b3b622e2a158e6577d2c10d4fe0977da404e7b3c1d  driver_kernel_stubs.h
92265ba7db61fbe531d946c49e1534bee6996008479240342bdc01c801778297  driver_nss_scaffolding.h
ab240702c9debcf8a1ae61f8fa22c0c5c64d0302b594fdeac911d1f2c10edb9d  driver_api_fixtures.c
7bee122e803c34ddab6d04f4aa321dac4e7651c2a2fa3d69a35ad77af1e19674  driver_emergency_cases.c
03eb5563f2a0b093b5f84d8fcf21364ea572350c24386ee4b6c4bf6232cc212d  driver_baseline_cases.c
cbf9ad9ce8f219ec69c0a03ba7f058f7142ba83aeabf61b46edbaa8b95365cbd  driver_candidate_cases.c
a8fb7770d3d0ff3aa8f54ed920f7e76888c4b9647669684a26d7ded68253958f  driver_nongeneric_cases.c
ceac7f66fc6afa08f792f1cddddab5647d0e346c009786592a09525e49969221  test_candidate_only_cli.py
05b767a3f50cbdb8eeefd360661952a1c50eaf4e5693beb8a58638ec5e3bfca3  test_driver_extraction.py
90431405d61a70db6346fe7f423af360e8005ca9415893d60bde36c4e76e5b96  test_extract_prepared_c.py
d332bfc05d7c04261fac75551bae38592e51957db97563cb87f951d77b4ba3ac  README.md
```

`SHA256SUMS-FINAL.txt` seals the above assets, freeze/integrity notes, and every
file in the two final replay directories. The manifest excludes only itself.
Earlier provisional result directories remain preserved, not promoted to final
acceptance. Independent review writes its own separate evidence directory.

## Replay and scope

From this directory on native macOS or offline Linux with Python 3.9+, a C
compiler and pthreads:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test-nss-drv-containment.py \
  --candidate-only \
  --candidate /absolute/actual/already-prepared-drv \
  --output /absolute/new-result-directory
```

Add `--baseline /absolute/original-prepared-drv` and omit `--candidate-only`
for full 44. The runner never fetches, prepares sources, accesses a router,
dispatches CI or builds a target kernel. It rejects invalid CLI modes before
creating output.

Host dimensions remain deliberately reduced: two mock core contexts, IRQ2
versus actual IPQ807x IRQ10, four interface slots, primary port1 and normal
slot0 plus boundary slot1. This exercises actual MAX loops over the reduced
fixtures, not every real IRQ slot or port. Kernel workqueue/RTNL/NAPI ownership
and grace, ACK/notifier and DP APIs are substitutes. The actual emergency poll
completion returning path and absence of rearm are checked without invoking
real firmware, crash or panic. Legacy defect tests use artificial ownership
release only to terminate the fixture; they are not repaired PASS claims.

No ordinary-poll/full-probe/platform-initializer/general-client/module lifetime,
Linux RCU/scheduling/lockdep/ABI/real dual-core/AX6 runtime PASS is claimed.
Native execution recorded here is macOS arm64 only. Old sealed DP artifacts,
source worktrees, production, router, CI, commits and pushes were not mutated
by this test author.
