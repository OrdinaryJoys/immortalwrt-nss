# IGS Sync Completion Control-Flow Regression

## Scope

`test-nss-igs-sync-completion.py` is an offline, deterministic, single-thread
host regression for the actual prepared clients source. It does not run a kernel,
NSS firmware, device, network operation, real RTNL concurrency, or real waiting.
The authoring handoff does not execute this script, a compiler, or tests. The
parent owns production patch 016, protocol/source review, build CI and execution.

The old static `msg_response` contains `sem/wq/response/cond`. Its actual callback
writes response, clears cond, then wakes the queue; the actual sender writes
`cond = 1` only after TX succeeds. A callback before that assignment is overwritten.
The candidate contains `sem/done/response`, initializes completion in actual init,
writes response before actual complete, and reinitializes after down but before TX.
The numeric timeout remains `600*HZ` (10 minutes); the runner retains the actual
header define, including its comment, and rejects a different numeric expression.

S01, S03, S05 and S06 remain **OPEN**. Shared-completion late-ACK request association
also remains **OPEN**. Passing this regression is not a firmware/shutdown-safety
qualification, a kernel completion implementation test, a memory-ordering proof,
or a claim that all replies are associated with their originating requests.

## Parent-Owned Invocation

Run from the repository root with offline prepared clients trees. Output must be
a fresh directory; any existing path, including a symlink, is rejected without
reuse or deletion. The default compiler is the host `cc` from PATH. CI explicitly
passes `--cc cc`; local GCC16 and Clang runs pass their absolute compiler paths.

```sh
python3 tests/test-nss-igs-sync-completion.py \
  /Volumes/FX-MD87/Review-AX6/audits/20261024/igs-sync-completion/candidate-clients \
  --baseline /Volumes/FX-MD87/Review-AX6/audits/20261024/igs-sync-completion/baseline-clients \
  --output /absolute/path/to/a/new/igs-sync-run \
  --mutations --sanitize
```

The positional `clients` is the layer-16 completion candidate. Optional `--baseline`
is the layer-15 condition/waitqueue source. `--cc PATH` selects a compiler, not a
shell command. `--mutations` enables all eight negative controls; `--sanitize`
adds address/undefined sanitizers, disables sanitizer recovery, and records the
sanitizer environment. It does not request unsupported LeakSanitizer on macOS;
no leak-sanitizer qualification is claimed. Compiler timeout is 120 seconds and executable timeout is
30 seconds per variant. At most ten variants run when both options are selected
(candidate, baseline, eight mutations). No archived-directory scripts are invoked.

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
and response values, not their ABI. Every TX status other than model success must
take the error path, tested with four distinct nonzero values. Semaphore operations
check ownership and balance without implementing blocking or threads. Completion
is an initialized token counter: complete adds a token, wait consumes one token,
and reinit clears tokens. Legacy wait evaluates the actual condition before and
after optional callback injection via a GNU11 statement-expression macro. Neither
implementation is Linux's completion/waitqueue code or memory model. `HZ=100` is a
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
function body is instrumented to add these points. The old implementation must
fail both return-edge and before-return early cases, including ACK returning -1
and NACK reaching timeout rather than consuming the reply. Old and candidate
normal late ACK/NACK cases at WAIT_ENTRY and WAIT_DURING must have identical
behavior signatures (return, TX/wait, reply consumption, timeout, callback and
semaphore counts); completion-specific initialization counters are excluded.

The complete 24-case summary includes four SET_NEXTHOP early/late ACK/NACK
contrasts in addition to the SET_IGS_NODE matrix, and also covers init, no-reply timeout, fill failure,
four TX failure statuses with no wait and semaphore return, TX failure followed
by success, NACK followed by success, timeout followed by a late ACK before the
next reinit followed by another no-reply timeout, and two ACKs followed by a
no-reply request. The last two require stale/residual completion tokens to be
cleared. Moving reinit after send is explicitly rejected by an early-ACK negative
control. Every request checks fill/TX/wait/callback counts, consumption vs timeout,
return value and semaphore balance, even when -1 alone would hide a wrong path.

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
function. The move-after-send control uses two separately unique contexts. Every
control retains original and replacement text, function name and before/after
hashes. They mutate only generated in-memory function text, never the input tree.

- M01 omits reinit: `timeout_late_before_reinit` must fail `return`.
- M02 moves reinit after TX: `ack_tx_before_return` must fail `return`.
- M03 drops complete: `ack_wait_during` must fail `return`.
- M04 forces ACK response: `nack_wait_during` must fail `return`.
- M05 makes timeout return success: `timeout` must fail `return`.
- M06 omits semaphore return on TX error: `tx_failure_1` must fail `sem_balance`.
- M07 omits completion initialization: `init` must fail `completion_initialized`.
- M08 accepts NACK: `nack_wait_during` must fail `return`.

A negative control qualifies only with compiler exit 0, executable normal exit 1,
complete consistent JSON for every case/call and an explicit failure record for
its designated case/check. Compile failure, stderr text, sanitizer failure,
termination by signal, absent summary, or arbitrary nonzero exit is never a hit.
The model accumulates failures instead of using C assert/abort so it can report
the whole case set even for initialization and semaphore-leak mutations.

## Evidence

`RESULT.json` contains scope, OPEN items, all adaptation notes, input hashes,
script/extractor hashes, variant verdicts, complete per-case summaries and
per-request observations, explicit assertion failures, baseline signature
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

## Recorded Parent Execution

On 2026-10-24 the parent ran GCC16 and Clang ASan/UBSan against fresh layer-16
candidate and layer-15 baseline inputs. Each compiler completed ten variants
(candidate, baseline, eight runtime negative controls) and all 24 scenario records.
There are 23 bounded contract scenarios and one still-unsafe OPEN diagnostic,
not 24 repaired fault classes. Final evidence is under the new `sync-gcc-v2` and
`sync-clang-v2` directories in the 20261024/igs-sync-completion audit; after the
portable default adjustment, matching final-source runs are recorded as v3.
The initial Clang run aborted before C main because macOS does not support an
explicit `detect_leaks=1`; that failed record is retained. The final runner omits
that unsupported option and still enables address/undefined sanitizers and
nonrecovering failure. No LeakSanitizer or target/runtime qualification is claimed.
