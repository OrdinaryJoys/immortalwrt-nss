# IFB cross-translation-unit linkage regression

023 exposes nss_ifb_info_put in nss_ifb.h and calls it from nss_mirred.c.
Its definition must have external linkage in nss_ifb.c. Both objects are
members of act_nssmirred; no new inter-module EXPORT_SYMBOL is needed.
The repair changes only that definition's linkage, not reference semantics,
mapping publication, packet processing, firmware protocol or performance.

The test includes the complete actual prepared nss_ifb.h in two separate C
translation units and compiles the complete actual put definition. It links
the objects and calls the helper across the translation-unit boundary.
Kernel types, refcount and kfree have explicit host substitutes. A two-ref
object checks the ordinary decrement/free path only, not Linux saturation,
underflow, module lifetime, concurrent access, device or firmware behavior.

```sh
python3 -B tests/test-nss-igs-ifb-linkage.py PREPARED_CLIENTS \
  --baseline PRE_FIX_CLIENTS --cc gcc-16 --mutations --output NEW_DIRECTORY
```

Repeat with Clang and --sanitize. GCC without --sanitize is plain host
compilation, not GCC sanitizer qualification. The pre-fix baseline and
static-definition control must fail with the exact C linkage conflict;
missing declaration, missing definition and signature controls must fail at
their designated compiler/linker phase. These are language/linkage negative
controls, deliberately not counted as runtime fault detections. Two further
compiled controls must fail the complete small runtime oracle without any
sanitizer failure. Output is exclusive and cannot be inside a prepared tree.

This closes only IFB-LINKAGE-01 and its missing header/TU regression coverage.
CLEAR single-retirement/no-reply quota, callback tails, object/RCU lifetime,
S08 request identity, N2H/SQM transactions and target/device validation remain
open. Host success is not a completed AX6 firmware build.
