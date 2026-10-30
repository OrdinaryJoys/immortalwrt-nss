# A2 Cleanup Error Reporting Host Tests

Only complete actual `ssdk_cleanup` and `regi_exit` definitions are extracted
from the bound prepared source, together with the actual complete `sw_error_t`
enum. Structures, device-table setup and all called OS/driver leaves are native
models. A leaf records its exact action/argument and returns an injected enum
result; it does not implement FAL/PHY rollback or claim underlying cleanup is
safe. `ssdk_free_priv` is an explicit action leaf, not A1 execution or reuse.

The independent Python oracle specifies a complete ordered stream including
actions, exact log severity/text/device/code, direct return and void module
return. The native process consumes that oracle only after actual functions
finish; it emits nothing until every event and return matches. Python then
also compares the entire stdout byte-for-byte and requires empty stderr.
Both printf wrappers have format attributes; warnings remain errors, including
real driver log argument checking. No log-suffix/contains-only acceptance.

All actual error enum values are injected in both component positions against
success and another error, with and without emulation. Multi-device cases put
each component error at each device, exercise distinct earlier/later errors,
zero devices, every three-device registration/emulation mask, and the four
HPPE-switch/SFP compile-time combinations. These are branch profiles of the
two extracted functions, not four target build configurations. Emulation must
still skip PHY; all existing control/driver/switch/SFP/FAL/PHY/platform/free
actions, ordering and gates must exactly match baseline19 at runtime.

Baseline19 is freshly compiled and run against an independent old-reporting
oracle for every positive case. Its action projection must equal candidate's;
both complete actual emitted streams must match their respective full oracles.
Old actual definitions additionally reject the new first-error/log contract.
An unchanged complete baseline `regi_exit` is isolated with candidate cleanup
to expose the old accumulator separately from missing component/device logs;
only that named witness allows the old lack of per-device log in its expected
stream. It is not a full candidate PASS or a whole-baseline root proof.

Single-fault source mutants must compile cleanly and execute with exactly86,
empty stdout and one named `SSDK_A2` diagnostic line. Compiler failures,
timeouts, signals, arbitrary nonzero statuses, extra diagnostics or sanitizer
reports are campaign failures, not successful semantic negatives. Separate
pure gate pollution controls check those acceptance rules.

The new runner imports no A1 test asset or old audit program. Parent recipe10
baseline/candidate data are verified through exact receipts, archive pin and
manifests, full before/after patch-hash derivation and all692 prepared files.
Current `edma_patch_context.inspect_patch` checks actual032 name/SHA and full
old/new contexts at declared coordinates. Replacing only the two complete
functions in baseline19 must reconstruct every candidate byte. All other
files must remain identical. Historical baseline19 recipe9 is accepted only
if replacing the unique exact current `PKG_RELEASE:=10` line by9 reconstructs
its complete historical hash; this is recorded, not a general recipe waiver.
Current recipe/patch/helper/plan/test inputs, saved inputs, both trees and
generated C/oracles are rehashed at the end. This is not an atomic lock.

```sh
python3 tests/test-ssdk-root-cleanup-errors.py \
  --candidate /absolute/path/to/ROOT-A2-CANDIDATE-20261030-r2 \
  --candidate-receipt-sha 04d4e1017874d8354d2a6f77d1ff963efa6d102926a6a77da27813dacbde59e0 \
  --cc /opt/homebrew/bin/gcc-16 \
  --output /absolute/audit/ssdk-root-rollback/A2-TEST-gcc-r1
```

Clang adds `--sanitize`: ASan/UBSan halt and no recovery; each canary uses the
same exitcode in both environments (ASan97, UBSan98), normal body both97.
LSan is disabled and unqualified. Only unused native static leaves are exempt
from warnings; format/type/control-flow warnings remain errors.

Qualification is `HOST_MODEL_ONLY_A2_REPORTING`, not independent acceptance.
Module exit remains void and cannot prevent unloading. No FAL/PHY safe cleanup,
partial-init unwind, Linux concurrency/RCU, target ABI/link/modpost, hardware,
build or device qualification follows. A1 files and their historical records
are not edited; old failures remain at their original hashes.
