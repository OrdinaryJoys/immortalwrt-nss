# Native API mutex once: isolated two-TU host test

Only the exact small hsl_lock.c candidate is compiled, with its sole sw.h
include replaced by generated sdk.h. It is one translation unit; fixture.c is
another and calls the actual function through the actual hsl_lock.h prototype.
The extern object declaration comes from hsl_api.h. Real public/private AOS
spin/mutex typedefs and mutex init/lock/unlock macros are extracted from the
exact29 baseline headers and checked against that receipt's manifest. Linux
DEFINE_MUTEX, mutex storage and operations are explicit serial host models.

The independent profile matrix expects static readiness only for native
KERNEL_MODULE+KVER32 without USER_MODE or HSL_STANDALONG. Default-off and
API_LOCK/SW_API_LOCK paired-on native profiles run load, repeat, held and
bootstrap-actor cases. User, combined, standalone, no-KVER32 and no-kernel
profiles run only the legacy dynamic-init contract. They do not include the
conflicting combined/standalone hsl.h graph and do not claim that type fixed.
Changing feature defaults or real UK/HSL ordering is outside this suite.

Thirteen positive rows and eight fixed actual-source variants expand to15
negative executions. The literal expected profile/name/case/marker inventory
is independent of mutation generation, checked before and after execution.
Clean compile with no suppressed warnings is mandatory before exact exit86,
empty stdout and a unique complete LOCK_ASSERT marker. Timeout, compile failure,
signal or sanitizer diagnosis is not semantic credit. Python -O is required;
no assertion side effects or old generated program are used.

Full modeled mutex fields are compared across repeated/held init and simulated
failed/peer bootstrap calls. Those actors only call the real init function;
they do not execute or qualify real HSL/root rollback, constructor publication,
SD callbacks, thread scheduling, reader drain, mutex ABI or lockdep. Static
readiness is modeled, not a real module loader run. No destructor exists in the
actual candidate; its modeled absence is also checked by a source negative.

Use a new output directory. The author runs only one fresh GCC campaign:

```sh
python3 -B -O tests/test-ssdk-api-lock-once.py --candidate /Volumes/FX-MD87/Review-AX6/audits/20261101/ssdk-cohort-contract/NATIVE-LOCK-CANDIDATE-r1/src/hsl/hsl_lock.c --cc gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261101/ssdk-cohort-contract/LOCK-AUTHOR-r1
```

Parent runs use independent fresh directories; --sanitize enables ASan/UBSan
with97/98 canaries and both local option exitcodes equal to that canary's code.
LSan is disabled/unqualified. Inputs, five asset identities, compiler identity
and exact output inventory/bytes are checked at the end. ASSET-FREEZE.json
binds the successful campaign inputs, not an independent reviewer signature.
No archive replay, full29-tree validation or target/build/device qualification
is inferred. No production, recipe, plan, old test or git/ref is edited here.
