# SSDK A1 Root Topology Native Tests

Scope: complete extracted `ssdk_switch_device_num_init/exit/get`,
`ssdk_alloc_priv`, `ssdk_free_priv`, and `regi_init`. The latter is compiled
with CONFIG_OF, HPPE and IN_NETLINK enabled; only its topology-error return
and first private-array allocation failure are executed. All later private
slot, platform, FAL/PHY, sysfs, genl and notifier leaves fail immediately if
reached. Their success, rollback and lifetime are not qualified. A2 is excluded.

The OS, allocator, OF and structure layouts are explicitly native boundary
models, not Linux target ABI. Zero-size allocation returns a non-NULL tracked
token, preserving Linux's logical zero-count behavior without imitating a
particular ZERO_SIZE_PTR address. The actual hsl_reg_mode enum and actual root
error macro are extracted. The two DT access-mode fields and untouched zeroed
payload are checked; other DT fields and DT parsing are outside this model.

Every positive process has an independent expected JSON ledger: exact return,
OF calls/refcounts, allocation shape and result, ordered frees, control calls,
unrelated-global preservation, final topology state and real NULL-private
state. C also checks initialized child data and distinct identities before
exit, absence of publication at every allocation, reentry, and repeat exit.
Typed OF behavior includes missing property, NULL value, short data, exact
and extra cells; count zero and UINT32_MAX are not normalized or capped.
UINT32_MAX is faulted at the array allocator, not physically allocated.

Baseline18 complete-function counterexamples and single-fault source mutations
must compile cleanly and execute with exactly exit86, empty stdout and one
unique diagnostic line. Baseline free_priv is additionally isolated unchanged
against candidate DT functions, so the old OF/publication defects cannot mask
the NULL-private counterexample. A compile failure, timeout, signal, arbitrary
nonzero status, additional diagnostic or sanitizer finding receives no negative
credit. Pure acceptance-gate pollution controls test these rules separately.

The runner reads parent baseline18 and candidate19 receipts as data, validates
their exact hashes, Git archive pin/data and derived full manifests, and binds
all saved/live patches, recipe, helpers, plan and owned assets. Current
`edma_patch_context.inspect_patch` checks 031 at its exact declared coordinates
and derives its whole-file output; the full 692-file candidate must equal
baseline18 plus those outputs. Old preparation scripts/binaries are not run.
All inventories, raw inputs and prepared trees are checked again at the end;
this is not an atomic filesystem lock. No historical parser control or PASS is
borrowed as new runtime qualification. Recipe changes require new receipts.

Use a new `A1-TEST-*` directory under the authorized ssdk-root-rollback root:

```sh
python3 tests/test-ssdk-root-lifecycle.py \
  --candidate /absolute/path/to/ROOT-A1-CANDIDATE-20261030-r2 \
  --candidate-receipt-sha SHA256 --cc /opt/homebrew/bin/gcc-16 \
  --output /absolute/audit/ssdk-root-rollback/A1-TEST-gcc-r1
```

For Clang add `--sanitize`. ASan/UBSan use halt and nonrecovering compilation;
each activation canary sets both exitcodes to its required97/98, and the body
uses both97. LSan is disabled (`detect_leaks=0`), never claimed as passed.
Allocation/ref ledgers are model checks, not a replacement for LSan or kernel
instrumentation. Strict warnings remain errors except unused static functions
that the deliberately bounded profile does not call. No target/kernel/module
build, hardware, RCU/concurrency, full module lifecycle or FAL/PHY proof follows.

Author-run results are not an independent acceptance review. Failed directories
are retained unchanged; a later PASS qualifies only its exact bound asset set.

For the current20/release10 chain add `--integration DIR` and
`--integration-receipt-sha SHA256`. This is a new run, not an upgrade of an old
PASS. It accepts only the exact032 hash after the unchanged19-layer prefix,
derives its full692-file output, and requires all extracted A1 functions and
types to remain byte-identical. The old18/19 receipt recipe may differ from
the live recipe only by the single release9-to10 line, proven by its original
hash. The current20 receipt must match every live input without that exception.
The current inventory, recipes, receipts and all three trees are rebound and
checked at the end. A2 behavior is still not exercised by this A1 fixture.
