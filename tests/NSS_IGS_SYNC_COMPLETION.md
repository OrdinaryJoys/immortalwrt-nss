# IGS Sync Reply-Admission Control-Flow Regression

## Scope

`test-nss-igs-sync-completion.py` is an offline, deterministic, single-thread
host regression for the actual prepared clients source. It does not run a kernel,
NSS firmware, device, network operation, real RTNL concurrency, or real waiting.
The authoring handoff does not execute this script, a compiler, or tests. The
parent owns production patch 018, protocol/source review, GCC/Clang execution,
driver-header checks, build CI and the separate 495-interface regression.

Baseline is the actual layer-17 completion source, not the layer-15 waitqueue.
Its static `msg_response` contains `sem/done/response`; its callback unconditionally
stores response and completes. It already preserves early replies. The layer-18
candidate (final prepared `candidate-clients-v3`) contains, in order,
`sem/done/lock/response/expected_interface/expected_type/pending`. Init initializes
the lock and sets pending false. Under the semaphore and irqsave lock, the sender
reinitializes completion, saves the outgoing envelope, sets response to `LAST`
and pending true; it unlocks before TX or wait. The common `sync_done` locks,
retires pending and snapshots response, unlocks, checks ACK and releases the
semaphore. TX error and timeout retain `ret=-1` even if a reply supplied ACK.
In v3 timeout falls through directly to `sync_done`; TX failure explicitly jumps.
The callback holds the same lock, rejects inactive/wrong-interface/wrong-type
or `response >= NOTIFY`, otherwise claims pending false, stores response and
completes before unlocking. This is a bounded envelope guard, not a request token.
The numeric timeout remains `600*HZ` (10 minutes); the runner retains the actual
header define, including its comment, and rejects a different numeric expression.

S01, S03, S05 and S06 remain **OPEN**. Shared-completion late-ACK request association
also remains **OPEN** (S08 same-interface/same-command old ACK). PBUF, SQM and
callback/app_data lifetime remain **OPEN**, unchanged by this work. Passing is not a firmware/shutdown-safety
qualification, a kernel completion implementation test, a memory-ordering proof,
or a claim that all replies are associated with their originating requests.

## Parent-Owned Invocation

Run from the repository root with offline prepared clients trees. Output must be
a fresh directory; any existing path, including a symlink, is rejected without
reuse or deletion. The default compiler is the host `cc` from PATH. CI explicitly
passes `--cc cc`; local GCC16 and Clang runs pass their absolute compiler paths.

```sh
python3 tests/test-nss-igs-sync-completion.py \
  /Volumes/FX-MD87/Review-AX6/audits/20261026/igs-reply-admission/candidate-clients-v3 \
  --baseline /Volumes/FX-MD87/Review-AX6/audits/20261026/igs-reply-admission/baseline-clients \
  --output /absolute/path/to/a/new/igs-sync-run \
  --mutations --sanitize
```

The positional `clients` is the layer-18 guarded completion candidate. Optional
`--baseline` is layer-17 completion without the reply guard. The v1/v2 prepared
candidates are superseded inputs, not final qualification sources. `--cc PATH`
selects a compiler, not a shell command. `--mutations` enables 18 negative controls; `--sanitize`
adds address/undefined sanitizers, disables sanitizer recovery, and records the
sanitizer environment. It does not request unsupported LeakSanitizer on macOS;
no leak-sanitizer qualification is claimed. Compiler timeout is 120 seconds and executable timeout is
30 seconds per variant. With baseline and mutations there are 20 variants
(candidate, baseline, 18 mutations), each with 56 cases and 74 request calls.
These are implemented inventory counts, not execution results. No archived-directory
scripts are invoked.

Exit 0 and `PASS_CONTROL_FLOW_ONLY` require all requested checks, baseline
diagnostics, signature comparisons and negative controls to qualify. Missing
compiler, compile failure, timeout, signal, unexpected stderr, incomplete JSON,
source drift, or a missed negative control yields exit 1 and `FAIL`. A baseline
run's expected exit 1 is separate from the runner's final exit status.

## Extraction And Model Boundary

The runner imports the repository's
`tests/nss-dp-containment/extract_prepared_c.py` with bytecode writes disabled.
Its `Prepared.function` extracts complete actual `nss_ifb_init`,
`nss_ifb_wake_up_cb` and `nss_ifb_config_msg_tx_sync`. Their text, comments and
bodies are preserved without deleting or adapting statements in normal runs.
`Prepared.structure` extracts the actual config enum. The static struct-with-
instance declaration is extracted with the shared `code_mask` and `block_end`,
unique whole-token declaration boundaries, and an exact `msg_response;` tail.
Unexpected/ambiguous fields or boundaries fail closed; fields are not invented
from a replacement struct. The actual `600*HZ` define is also extracted lexically.
Extraction helper APIs append a final newline; hashes cover the saved fragments.

The full actual `config_msg_fill` is saved and hashed as **context only**, not
compiled. A clearly named model returns bool failure or installs the actual wake
callback for SET_IGS_NODE and SET_NEXTHOP. Thus fill-failure tests cover only sync caller control
flow (no down, no TX, no wait), not actual device lookup, payload, callback selection
or interface bounds. The parent must separately run the original 495-interface
model; this regression does not replace it.

The harness models reduced message/device/context types and symbolic NSS status
and status/type values, not their full ABI. The response names/order reflect the
reviewed driver enum: ACK, EVERSION, EINTERFACE, ELENGTH, EMSG, NOTIFY, LAST
(0 through 6). There is no invented production NACK constant: scenario names
containing `nack` use EMSG. All four legal error responses are exercised; LAST
is the sender's no-response sentinel and is rejected if injected as a reply.
Value 19 represents an additional invalid high response, not a new protocol value.
The reduced message includes semantic `cm.interface` and `cm.type`; the fill
substitute uses source interface 77 (optionally 88) and distinct symbolic
SET_IGS_NODE/SET_NEXTHOP types. This is still a fill substitute, not actual lookup,
payload, interface validity, or ABI verification. Every TX status other than model success must
take the error path, tested with four distinct nonzero values. Semaphore operations
check ownership and balance without implementing blocking or threads. Completion
is an initialized token counter: complete adds a token, wait consumes one token,
and reinit clears tokens. `MODEL_REPLY_GUARD` selects only candidate-field and
lock assertions; both variants compile their complete actual completion functions.
The explicit single-thread irqsave lock substitute records initialization,
held state, lock/unlock counts and flag pairing. Assertions require reinit under
the guard lock, TX/wait/up outside it, complete under it after claiming pending,
balanced callback/request locking and pending false on every sender exit.
This cannot prove kernel concurrency, IRQ exclusion, publication ordering or a
Linux spinlock/completion implementation. `HZ=100` is a
host-model constant; no 600-second wait occurs.

`nss_igs_error` forwards evaluated arguments to a no-output variadic model.
Compilation uses `-std=gnu11 -O0 -g -Wall -Wextra -Werror
-Wno-unused-parameter`. The sole warning-category exception is explicit because
the actual wake callback does not use app_data. No original body is edited to
silence it; other enabled warnings remain errors. Generated C and the exact
compiler command document all type/API and warning adaptations.

## Schedules And Cases

Four reply schedules each run with ACK and NACK:

- `TX_BEFORE_RETURN`: callback inside modeled TX, before its return.
- `TX_RETURN_EDGE`: callback in an API wrapper after modeled TX returns, before
  the caller assigns ret. This is a modeled boundary, not an actual instruction
  hook after the production `nss_if_tx_msg` call statement.
- `WAIT_ENTRY`: callback after the sender's status branch, before evaluating wait.
- `WAIT_DURING`: callback only after the first wait readiness check is false.

The two TX-to-wait boundaries are distinct: return edge and wait entry. No source
function body is instrumented to add these points. Both layer-17 baseline and
candidate must preserve all normal early/late reply cases; baseline must not fail
normal cases merely because it has no guard lock. Baseline and candidate
normal late ACK/EMSG cases at WAIT_ENTRY and WAIT_DURING must have identical
behavior signatures (return, TX/wait, reply consumption, timeout, callback and
semaphore counts); lock, admission and initialization counters are excluded.
The original six late signatures are retained in
`late_normal_signature_comparison`; `normal_signature_comparison` includes those,
all six early signatures and three additional legal errors (15 total).

The original 24-case inventory is preserved in order, including four SET_NEXTHOP early/late ACK/EMSG
contrasts in addition to the SET_IGS_NODE matrix, and also covers init, no-reply timeout, fill failure,
four TX failure statuses with no wait and semaphore return, TX failure followed
by success, NACK followed by success, timeout followed by a late ACK before the
next reinit followed by another no-reply timeout, and two ACKs followed by a
no-reply request. The new guard rejects those retired/duplicate callbacks;
reinit still has to clear a token left by an ACK delivered inline during a TX
that returns failure. Moving reinit after send is explicitly rejected by an early-ACK negative
control. Every request checks fill/TX/wait/callback counts, consumption vs timeout,
return value and semaphore balance, even when -1 alone would hide a wrong path.

There are 32 added cases, for 56 total (55 bounded scenarios and one unsafe OPEN
diagnostic), with 74 request calls:

- Six old-reply-only cases: different type, interface or both, each with ACK/EMSG.
  A times out, B changes its actual modeled envelope, and only A replies; B must
  time out, not consume a completion even when the return would also be -1.
- Six old-reply-then-matching cases for the same mismatch matrix and current
  ACK/EMSG. The old reply has the opposite response; only current may supply the
  terminal response/token. Request IDs are not compared for admission.
- Nine response-bound cases: NOTIFY, LAST and 19, each alone (timeout) or followed
  by a matching current ACK/EMSG (normal completion).
- One isolated inactive reply and two retired replies after ACK/EMSG must not
  change the terminal response or add a token.
- ACK then EMSG and EMSG then ACK must use only the first terminal response.
- TX failure followed by a late reply, then a new success or timeout; plus inline
  ACK with TX failure followed by a no-reply timeout (residual-token reset gate).
- EVERSION, EINTERFACE and ELENGTH complete normally with return -1; EMSG is
  already exercised throughout the original and new matrices.

Each callback uses an independent bounded oracle: active/unclaimed, same
interface/type and response below NOTIFY. Its verdict is compared with observed
complete/token/response changes. Ignored callbacks must preserve tokens, response
and candidate pending; accepted callbacks must add exactly one completion and
publish the exact response. Reply JSON records expected admission, observed
completion, envelope, response/token snapshots, pending and lock counts/state.
Call/case JSON reports observed and expected accepted/ignored counts. Model-only
IDs are solely diagnostic. The oracle intentionally accepts a same-pair old ACK,
so it does not silently strengthen the production contract into token matching.

Baseline must fail `ignored_no_completion` in all 28 new guard-sensitive cases,
also expose the original retired/duplicate callback failures, and have no failures
outside those 30 cases. Init, normal replies, fill/TX/timeout flows, token reset
and the same-pair OPEN diagnostic must retain their expected behavior.

`late_ack_misattribution_OPEN` deliberately demonstrates the remaining bug:
request A times out; request B starts/reinitializes; only A's saved callback arrives
during B's wait; B nevertheless returns success. Model-only request IDs establish
that the injected callback belongs to A, not B. They are not production correlation
fields. This case is marked `open: true`, `verdict: OPEN_DIAGNOSTIC`, and
`repair_pass: false` in the variant's `open_diagnostics`. It expects the unsafe
observed success and does **not** certify the repair. Both baseline and candidate must expose this
counterexample. A reply before B's reinit being cleared does not establish safety
for an old reply after B's reinit.

## Negative Controls

All replacements require exactly one full context within the selected extracted
function. The move-after-send and pending-after-TX controls use two unique contexts. Every
control retains original and replacement text, function name and before/after
hashes. They mutate only generated in-memory function text, never the input tree.

- M01 omits reinit: `tx_failure_inline_ack_then_timeout` must fail `wait_consumed`.
- M02 moves reinit after TX: `ack_tx_before_return` must fail `return`.
- M03 drops complete: `ack_wait_during` must fail `return`.
- M04 forces ACK response: `nack_wait_during` must fail `return`.
- M05 makes timeout return success: `timeout` must fail `return`.
- M06 omits the common semaphore return: `tx_failure_1` must fail `sem_balance`.
- M07 omits completion initialization: `init` must fail `completion_initialized`.
- M08 accepts EMSG as success: `nack_wait_during` must fail `return`.
- M09 omits interface check: `stale_wrong_interface_ack_only` fails `ignored_no_completion`.
- M10 omits type check: `stale_wrong_type_ack_only` fails `ignored_no_completion`.
- M11 omits response bound: `notify_only` fails `ignored_no_completion`.
- M12 omits pending check: `retired_after_ack` fails `ignored_no_completion`.
- M13 callback does not claim pending: `ack_then_nack_first_only` fails `ignored_no_completion`.
- M14 sender does not retire: `timeout` fails `pending_false_on_return`.
- M15 moves complete after unlock: `ack_wait_during` fails `complete_under_guard_lock`.
- M16 publishes pending only after TX: `ack_tx_before_return` fails `pending_before_tx`.
- M17 omits lock init: `init` fails `lock_initialized`.
- M18 weakens `>= NOTIFY` to `== NOTIFY`: `last_only` fails `ignored_no_completion`.

These are required future runtime failures, not claimed observed results. M01's
old retired-ACK gate is no longer sensitive because the guard rejects that ACK;
the replacement residual-token case exercises a valid accepted inline ACK.

A negative control qualifies only with compiler exit 0, executable normal exit 1,
complete consistent JSON for every case/call and an explicit failure record for
its designated case/check. Compile failure, stderr text, sanitizer failure,
termination by signal, absent summary, or arbitrary nonzero exit is never a hit.
The model accumulates failures instead of using C assert/abort so it can report
the whole case set even for initialization and semaphore-leak mutations.

## Evidence

`RESULT.json` contains scope, OPEN items, all adaptation notes, input hashes,
script/extractor hashes, variant verdicts, complete per-case summaries and
per-request and per-reply observations, explicit assertion failures, baseline signature
comparisons, and mutation records. Each input manifest records actual source
file hashes and extracted-definition hashes. Source files and script/extractor
are checked for drift before the final result is written.

`candidate-original/` and optional `baseline-original/` save original fragments,
including the unused actual fill context. Each variant saves `generated.c`,
`compile.command.json`, `compile.command.txt`, `compile.stdout`, `compile.stderr`,
`compile.result.json`, and corresponding `run.*` files when compilation succeeds.
These include exact argv, return codes, stream hashes and timeout results. An
infrastructure failure may have no runnable case summary and is explicitly FAIL;
it cannot be presented as a completed test run or successful negative control.

No result archive is claimed by merely authoring these two source files. Actual
compiler compatibility, test outcomes, sanitizer availability and baseline
diagnostics remain for the parent's authorized execution and CI evidence.

## Authoring Handoff

This revision was checked only by Python syntax/AST inspection and read-only
exact-context matching against v3. All 18 mutation recipes have unique actual
source contexts. No generated C was compiled, no regression was run, no archived
audit helper was executed, and no network/device/target action was taken by this
worker. Parent GCC/Clang execution remains required; no historical 016/015 pass is
evidence for this 018/017 revision. The worker handoff is
`20261026/igs-reply-admission/SYNC-TEST-WORKER.md` in the audit tree.
