# IPQ807x Private Pdata Ownership Tests

`run.py` extracts the actual `__nss_hal_of_get_pdata` body from an already prepared NSS source tree and inserts it unchanged into `harness.c` for positive tests. Kernel APIs are host substitutions with explicit ownership accounting. No kernel headers, device, or firmware are executed.

```sh
python3 -B run.py --source /absolute/candidate-source \
  --baseline /absolute/pre-032-source \
  --vendor-file /absolute/vendor6aa-nss_hal_pvt.c \
  --output /absolute/new-results --cc clang
python3 -B runner_unit.py --source /absolute/candidate-source \
  --baseline /absolute/pre-032-source \
  --output /absolute/new-runner-results --cc clang
```

Python 3.9+ and Clang or GCC are required. Output must be a new directory outside source, baseline, and this test tree. `--baseline` and `--vendor-file` are optional for a standalone candidate replay. Use `--optimization O0 --sanitize` with Clang for ASan/UBSan; leak sanitizer is disabled. GCC can be selected with an absolute path. On macOS, /usr/bin/clang and /usr/bin/cc are resolved via xcrun to the actual compiler binary before hashing/execution.

## Coverage

- 33 cases under four node/cache API-mode combinations: allocation failure, all required-property failures, ID/IRQ-count bounds, all resource lookups, map failures 1/2/3, all ten IRQ-parse positions, and successful boundary/optional-frequency cases.
- Every failing parser prefix must release only its acquired local maps/pdata, balance its node reference, and make zero NSS TCM writes/barriers. Success must retain maps, run the same TCM clear count and one barrier before feature parsing, and retain IRQ numbers.
- Foreign context map pointers/content and foreign node references remain intact. Legacy selected-context-ID assignment and valid-ID global frequency behavior are intentionally not rolled back.
- Twelve compiling source mutations must fail at their exact runtime assertion, exit 86, and print no other output. Twelve optional baseline witnesses establish original defects; compiler errors, warnings, signals, and wrong assertions never count as passing negatives.
- Off-by-one/baseline ID witnesses pad one host context cell for deterministic detection, not physical OOB execution. Positive builds use exactly NSS_MAX_CORES cells.
- Existing vendor-to-baseline compatibility changes from patch 003 are checked explicitly; the tested function is always the prepared source, not the compatibility-normalized comparison string.

## Evidence Binding

`RESULTS.json` records the source/function hashes, complete frozen input files, actual compiler executable before/after hashes, compiler version and commands, generated-C hashes before/after compilation/execution, and executed-binary hashes before/after every run. All original and frozen inputs must remain stable at completion. A new results directory is required; old results are never overwritten.

The runner rejects python -O. `runner_unit.py` supplies 11 positive and 24 rejection controls for output isolation, symlink resolution, input/artifact stability checks, exact runtime failure matching, optimization rejection, and compiler stderr rejection (including an actual warning with rc=0). Its artifacts are written only below its supplied output directory; it never mutates the real source/baseline/test inputs.

These are host control-flow and ownership tests, not a target module build or proof of FW retirement, IRQ-domain ownership, physical cache coherency, or whole-probe/module-exit correctness.
