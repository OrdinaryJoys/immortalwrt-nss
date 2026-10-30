# COUNT21 Native Admission Tests

Complete actual DT init/exit/get, `regi_init`, `ssdk_alloc_priv` and
`ssdk_free_priv` definitions are extracted with the current repo A1 pure
extractor. Only `extract` is reused; its actual source hash is bound and checked
at the end. No old prepare gate, runner, audit script, binary or PASS is reused.
Actual `SW_MAX_NR_DEV` is extracted from `include/common/sw_config.h`, must be3
for this campaign, and is compiled rather than hand-defined. Actual hsl register
enum, sw_error_t enum and root error macro are compiled too.

The native OF, allocator, structs and later leaves are explicit models, not
target ABI or actual Linux execution. Zero-size allocation is a tracked non-NULL
token. Later private-slot/PHY/platform/FAL/control initialization leaves fail
if reached. Root execution qualifies only topology errors and the first private
array allocation failure; successful zero-device/full root behavior is OPEN.

Independent Python expected traces specify every OF operation and reference,
typed-read result, allocation kind/shape/fault, free ID/order, root failure log,
permitted existing control calls at NULL-private boundary, observed published
table/count, child data and repeat-exit/reentry. C executes actual functions,
checks resource/foreign-owner invariants, and compares the complete trace before
printing. Python then requires exact full stdout and empty stderr. No suffix-only
or generic nonzero acceptance. Printf wrappers carry format attributes.

Zero/default/1/2/3 and every topology allocation failure at each admitted count
are tested.4/7/UINT32_MAX must be rejected before the allocator, with OF refs
returned;7 is not an accepted new21 count. Existing owner and malformed data
errors retain priority, including combined malformed/oversize and foreign input.
Root rejection must not reach private or global controls. Complete old20
definitions are freshly compiled as runtime counterexamples; no huge allocation
is attempted to demonstrate the missing admission boundary. Source mutations
must compile cleanly, then exit86 with empty stdout and precisely one expected
named diagnostic. Compile failures, sanitizer findings, timeout, signal, extra
diagnostic and arbitrary nonzero exits receive no semantic-negative credit.

Baseline20r10 and candidate21r11 receipts are read as data and bound to exact
archive pin/manifests, saved/live patch hashes and complete692-file derivation.
Current `edma_patch_context.inspect_patch` verifies033 full declared coordinates
and output. Only the complete DT init body may differ; the five other extracted
functions, enums, capacity and all other files remain unchanged. Historical
recipe10 is accepted only if replacing the unique exact current11 release line
reconstructs the entire historical10 hash. Current21 matches every live input
exactly. All assets/inputs/inventories/trees/generated C and oracles are checked
again at the end, not locked atomically. A1/A2 original qualifications stay at
their original hashes; this campaign is not a full integration upgrade.

```sh
python3 tests/test-ssdk-root-count-admission.py \
  --candidate /absolute/path/to/ROOT-COUNT-CANDIDATE-20261030-r1 \
  --candidate-receipt-sha 369005003b0806d4b7c44af39ca0e75d08606dc0d8001b593e8659e46ea393df \
  --cc /opt/homebrew/bin/gcc-16 \
  --output /absolute/audit/ssdk-root-admission/COUNT-TEST-gcc-r1
```

Clang adds `--sanitize`. Both sanitizer exitcodes are97 for the ASan canary,
98 for the UBSan canary, and97 for the body. Halt/no recovery are enabled;
`detect_leaks=0`, so LSan is not qualified. Strict warnings include format checks;
only unused native static leaves are exempt. No make/target/module/firmware/cloud
build, device, target ABI/link, Linux RCU/concurrency, hardware, full root rollback
or FAL/PHY cleanup safety follows. Author results require separate parent reruns
and independent review. Failed directories are retained unchanged.
