# Frozen SSDK FDB S2 Native Tests

Scope is the frozen029 CPU-side FDB controller, shared FDB admission, associated
IRQ work and control/family/sysfs retirement. It is not a full SSDK/module unload
approval. The original freeze1 last-leave counter/window is recorded separately
as a failing unmutated source, not a killed mutant. Parent r2 moves the final
waitqueue wake inside the state lock and adds an unconditional final lock
barrier after the user-count wait. All claims bind the explicit r2 hash.

The runner imports only the current repository source preparation helper. Each
compiler gets a fresh exact-pin 17-layer text tree, complete declared-context and
output-byte checks and a frozen entire patch-chain binding. The saved old16 tree
is read as data only; four old actual functions are compiled into a new local
counterexample executable. No archived program is imported or executed.

The fixture extracts 43 complete actual function definitions unchanged, the real
version/FDB enums, relevant struct field declarations and netlink/sysfs globals.
Exact full definitions, source lines, hashes, full original private struct and
generated C are saved. Only needed fields enter a native host struct: no target
ABI claim. Actual FDB work/controller/task/table reset/free, IRQ acquisition/
entry/work/pause/resume/final drain, actual poll/start errno paths, full netlink
send/family/control functions, sysfs init/exit, allocation/free and cleanup roots
execute against checked lower primitives. The MHT sysfs attribute is on;
IN_LINUX_STD_PTP is not defined, so the optional PTP sysfs attribute is not
part of this campaign; defining IN_PTP does not establish that coverage.

There are 34 positive scenarios with a frozen exact summary in the runner.
The barrier adds six lock-model checks on each of80 final drains: the expected
check count changes from11568 to12048, not34 additional scenarios. A separate
last-leave schedule checks the real wake completes before private free; it
also runs with IN_FDB off using a direct controller user, not a whole no-FDB
module or actual caller-reachability claim. Three source-poison controls check
the barrier is unconditional; they are not semantic runtime negatives.

The first final r3 GCC run found a host-oracle scheduling dependency: the old
arrived helper counted each actual condition wait instead of each completed
progress assertion. Diagnostic tag accounting isolated the difference to
native-hook-progress. It now checks once after the same predicate/error/timeout
loop, including an already-arrived caller; the exact count gate is not widened.
The combined Clang runtime also shares exitcode between sanitizer option
variables. Each diagnostic canary now records matching per-run common options;
its exact diagnostic and exit are still mandatory, not a generic nonzero pass.
The suite covers HPPE/APPE/MRPPE/MHT and unsupported behavior; partial/last/
repeated stop/restart; concurrent start vs partial/final stop; paused direct,
delayed and IRQ FDB consumers; false pending cancellation while work is running;
normal IRQ rearm and duplicate/paused/stopped IRQ admission; failed IRQ request
and retry/owned GPIO retirement; accepted and rejected poll controls; paused
notification sending; sysfs allocation/every-file failure and active callback
drain; partial private allocation and actual cleanup/free ordering.

Pthreads model sleeping locks, short BH locks, workqueue pending/running/sync
cancel, waitqueues, IRQ registration/masking, genl callback serialization and
kernfs active-callback drain. Named barriers and per-edge progress counters are
required; a watchdog timeout is failure. Both ordinary GCC and Clang ASan/UBSan
use -Wall -Wextra -Werror; only unused function/parameter/variable warnings are
disabled because complete definitions/configuration aggregates have uncalled
branches. Type, signedness, implicit declaration and prototype warnings are not
disabled. LSan is disabled explicitly; ASan does not imply LSan qualification.

Every semantic mutant must compile with empty streams, exit86, empty stdout and
exactly one named stderr line. Shared acceptance functions also reject oracle
pollution, wrong counts/fields/status, crashes, sanitizer text and timeouts.
Positive ASan and UBSan fault canaries require their own diagnostic/exit gates;
they are neither semantic mutant kills nor production behavior. All streams,
commands, input hashes and generated artifacts are retained, including failures.

The retained freeze1 characterization executes the real shared task and leave, pauses
after users becomes zero and its BH lock is released, then executes real final
retirement/free before allowing the real wake call to continue. An allocation
ledger emits an exact assertion before touching a freed waitqueue. This exposes
an insufficient component last-use protocol, conditional on a surviving direct
caller. Full module owner/dependency reachability is not reproduced by this
model. It does not demonstrate an observed device or runtime unload failure.
The new candidate succeeds under that schedule; a cleanly compiling variant
that moves wake back after unlock must still hit its exact lifetime assertion.

Limits: actual lower PHY/FAL hardware, IRQ controller and Linux workqueue/kernfs/
genl internals are modeled. Actual sysfs callback bodies, module init/exit caller
placement and DTS GPIO acquisition sites are static-only, not dynamically run.
The legacy PHY-name fallback is unchanged and stubbed; no PHY/DSA ownership or
outer-lock protocol is repaired/tested. QM/MAC workers, external private users,
notifier caches, full module/init-failure unwind, runtime compatibility,
hardware/FW/DMA idle and performance remain OPEN. No DP authorization follows.

Run from the source checkout with a fresh SSDK-FDB-ADOPT-* output:

```sh
/usr/bin/python3 -B tests/test-ssdk-fdb-retirement.py --upstream-cache /Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-ssdk --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/SSDK-FDB-ADOPT-gcc-final --compiler /opt/homebrew/bin/gcc-16 --frozen-029-sha256 a0e19f941d404525dd21bc4c374e577ac3ca8d6663425e2a5a437d36adcf8cd5
```

Clang: select `/usr/bin/clang` with `--compiler` and add `--sanitize`.
No make, kernel/target/firmware build, device, cloud, commit or push is involved.
