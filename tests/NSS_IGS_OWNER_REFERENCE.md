# IGS Owner Reference: Bounded Host Regression

2026-10-27. 025 / qca-nss-drv r23. This is a local host qualification, not a
kernel, firmware, concurrency, callback-lifetime or device qualification.

## Production contract

The driver stores the IGS owner after the client's last fallible registration.
Default NSS_DEBUG_LEVEL=0 removes nss_assert. Linux try_module_get(NULL)
returns true, so an unpublished owner must not be passed through as a successful
module reference. 025 protects save/get/put with one statically initialized
irqsave lock; get rejects NULL; put with NULL unlocks and emits pr_warn_once.
No firmware TX, registration, unregistration or wait is added inside the lock.
Client late-publication/early-clear order remains unchanged.

Scope is the current leaf obj-m recipes for act_nssmirred/qca-nss-qdisc and
normal balanced references. A successful get must be paired before owner
removal; held references exclude normal unload in this model. Arbitrary
owner replacement, duplicate put, force unload, builtin API expansion, NMI
and PREEMPT_RT hardirq are not qualified. save(&ops,NULL) cannot distinguish
hypothetical builtin publication from the current clear operation; a bool
alone is not a complete alternative protocol.

## Inputs and extraction

The runner consumes a prepared driver and a kernel root with
kernel/module/main.c and include/linux/module.h. It downloads/prepares
nothing. It extracts complete actual nss_igs_module_save/get/put, the owner
pointer/lock declaration, real CONFIG_NET_CLS_ACT enclosure and NSS debug
macro block. The existing shared lexical reader is snapshotted and hashed;
it is not changed. A CPP stack rejects nested/branched save enclosures.

Complete actual Linux try_module_get, module_put and module_is_live are
compiled under diagnostic symbol renaming. Extracted definition hashes pin
Linux6.18.38. Atomic operations, module structure/state, IRQ/spinlock, trace,
warning and BUG are explicit host substitutes, not kernel ABI. BUG is counted
and continued only for observing the old debug-enabled path, never claimed
as actual kernel BUG execution. Modern Linux's NULL semantics are obtained
from actual function bodies, not a substitute returning an invented value.

The first following NSS_PKT_STATS_ENABLED block bounds the actual debug
macros; its internal CPP must balance. A later stats conditional is not an
ambiguous second end. Full inputs/extracted fragments are retained, input
identities/hashes checked throughout, and generated C/binary manifests are
checked around execution. The runner never executes archived programs.

## Invocation

```sh
python3 tests/test-nss-igs-owner-reference.py "$nss_drv_dir" \
  --kernel "$linux_module_dir" --cc cc --mutations --sanitize \
  --output "$GITHUB_WORKSPACE/core-flow-evidence/nss-igs-owner-reference"
```

Optional --baseline consumes a distinct old prepared driver. --cc names one
host executable, not a shell expression. Output must be fresh, outside input
and source trees, and contain no symlink component; existing paths are not
overwritten. Default output, if omitted, is a fresh temporary directory.

Wall/Wextra/Werror remain, with only Wno-unused-parameter because the real
DEBUG0 macro removes save's act use, as in kernel compilation. Sanitizers are
ASan/UBSan; runtime nonzero, stderr, signal, timeout or malformed JSON fails
closed, including for negative controls. No forced detect_leaks on macOS.
No LeakSanitizer, target header compatibility or actual lock atomicity claim.

## Matrix and independent oracles

NET_CLS_ACT on/off x DEBUG0/1 gives four host configurations. With ACT on,
nine cases cover absent owner, initially disabled IRQ, Linux NULL semantics,
COMING, GOING, zero refcount, balanced reload, and two deterministic unload
contenders. ACT off runs only the three non-publication cases; it does not
bypass the real save CPP gate. The lock model explicitly defers a contender
until unlock and normal references block unload. This premise is not proof
of real scheduling, RCU or complete module lifecycle.

Each candidate has 24 config/case executions, 538 JSON events and no failed
oracle labels. These are events, not 538 independent assertions or faults.
The Python Reference independently constructs owner/refcount/IRQ/lock/trace
ledgers from explicit fixture operations, not from generated C output.

Six mutations remove get/put NULL guards, each save/get/put lock, or replace
the once-visible warning with the debug-only warning. With baseline enabled,
32 C executables / 192 scenario runs / 224 compiler+run commands are selected.
Only 18 variant/config target runtime detections are applicable: three lock
mutations need ACT on; ACT-off compilation is not counted as their detection.
Baseline gives 144 named mismatch observations, not 144 independent bugs.
Without baseline, CI selects 28 executables / 168 scenarios / 196 commands.

Static checks inspect the precise code-masked statement structure, including
NULL guards and critical-section placement. Three comment-decoy controls are
separate static tests, not additional runtime variants.

For every candidate, baseline and mutation, the **entire actual ledger must
equal its independently defined variant/debug/case ledger**. A target label
alone is insufficient. Unaffected cases must still equal the positive ledger;
extra BUG events, dropped traces and unrelated reference changes are rejected.
Three data-level oracle negative controls inject those unrelated deviations
into get-null/coming and must raise variant mismatch. They are not C runs or
independent kernel concurrency tests.

## Parent execution and review history

The author wrote the runner and inspected sources, but did not finish its own
AST/static execution and wrote no documentation. Parent took over, authored
this document and performed all C runs. No independent execution by author.

First v1 failed before C compilation: the draft required only one stats
conditional end in nss_core.h, but the actual header contains two. Parent
selected the first following balanced block. v2 candidate passed; its baseline
contender produced defined unload.absent that the event whitelist omitted.
That evidence failed closed and was retained. v3 ran, but independent review
R1/P2 found weak negative acceptance could admit unrelated ledger mismatches.
Parent added variant-exact ledgers and three unrelated-deviation controls;
only owner-gcc-final / owner-clang-final and owner-default-final qualify the
final runner. Earlier v1/v2/v3/default-cc files remain historical evidence,
not final acceptance. Initial CI fixture ambiguity is also retained separately.

Final GCC16 and Clang ASan/UBSan passed 32 executables each, default cc with
ASan/UBSan passed 28 without baseline. Evidence root:
/Volumes/FX-MD87/Review-AX6/audits/20261027/igs-owner-admission.

Still OPEN: whole qdisc reference pairing, early put versus async callbacks,
owner replacement, client/driver unload/drain, S08 same-pair reply identity,
firmware compensation, target/real-device/runtime/throughput qualification.
The new lock is a control-path correctness repair, not a highest-performance
benchmark or permission to enable IGS/SQM on the router.
