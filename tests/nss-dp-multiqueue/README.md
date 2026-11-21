# IPQ807x Actual-C Multiqueue Regression

This suite compiles complete, byte-preserved definitions from two supplied
prepared DP trees. It does not apply patches, run archived scripts, contact a
device, dispatch CI, or build firmware. Python only extracts C, orchestrates the
compiler/processes, checks outcomes, and records evidence. The queue transitions
under test are executed by the extracted C, not a Python behavior model.

## Inputs

The baseline must be B12-compatible vendor d8f802f08fd8ff31057ba58edb20bbe448e7b505
with package patches 001-019 applied. The candidate must differ only in
`nss_dp_activate_data_plane()`: `netif_start_queue(dp->netdev)` becomes
`netif_tx_start_all_queues(dp->netdev)`. This is production patch 020; the suite
does not manufacture the candidate. The runner compares all seven captured
input files, requiring precisely this change in the complete main source and
no change in the other six. It checks the prepared IPQ807x queue count is four.
It records source hashes; the caller must additionally bind these prepared
trees to the source commit, vendor pin and successful patch-replay evidence.

The locally verified inputs were supplied by the main task:

- Baseline: `/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/patch-replay-v2/dp-b12`
- Candidate: `/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/patch-replay-v2/dp-r11`
- Replay provenance: their parent directory's `RESULT.json`, owned by the main
  task. The old `/private/tmp/dp-b12` is not an accepted provenance substitute.

## Run

Use a new output directory. Existing results are never overwritten.

```sh
python3 -B tests/nss-dp-multiqueue/run.py \
  --baseline /absolute/prepared/dp-b12 \
  --candidate /absolute/prepared/dp-r11 \
  --cc clang --sanitize \
  --output /Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/results-clang-next
```

All compilations use `-Wall -Wextra -Werror`; only unused API parameters are
suppressed because the extracted production quarantine callbacks intentionally
do not use them. Assertions/checks are not disabled. There is no suppression of
implicit declarations, type diagnostics, unused functions, or unused variables.

With `--sanitize`, clean, ASan heap-OOB and UBSan invalid-shift canaries run
before the matrix. Both canaries must emit the correct diagnostic and exact
exit 98. Then baseline, candidate and every mutation run both plain and under
ASan+UBSan. LeakSanitizer is disabled for host portability; no leak-detection
acceptance is claimed. A sanitizer report, signal, timeout, compile failure,
wrong failure marker or missing case is an error, never a successful mutation
rejection.

## Coverage

There are 32 scenarios per input per compiler mode:

- Linux API controls: running independent of queue state; single-start only
  clears Q0; all-start clears DRV_XOFF for every allocated queue; STACK_XOFF and
  FROZEN survive; start does not schedule; wake schedules only an XOFF-to-on
  transition; attach only wakes on absent-to-present plus running, and repeated
  attach is inert.
- DOWN takeover then first open, with PHY, without PHY, and with previously
  uninitialized native ops. All four queues must remain stopped at readiness
  while administratively DOWN, then become available only after successful open.
- UP takeover, both PHY variants, then three close/reopen cycles on each.
- Pending open refusal; wrong readiness context; permanent quarantine followed
  by resume/start/open/override/close and dropped xmit without backend dispatch.
- Initial open init failure; six partial-open stages (VSI, MAC, MTU, plane open,
  GMAC start, no-PHY link-up), each at first open and UP readiness.
- Four takeover errors (new init, old deinit, old close, old link-down) and four
  normal close errors (link-down, VSI unassign, GMAC stop, plane close).

Every DP scenario protects a second instance with mixed per-queue state and
checks its complete fixture remains unchanged. Failure cases check start/wake
counters, not just final bits: an erroneous temporary activation followed by
quarantine stopping queues again is rejected. Calls to injected stages must
actually occur. Reader balance, callback pair, pending/blocked/quarantine,
PRESENT, carrier, PHY state and polling-init count are checked as applicable.

The unchanged B12 program must compile successfully and fail at the exact
`queues-ready` runtime assertion in three DOWN cases, showing queues
`[0,1,1,1]`. Its other 29 cases must pass. The candidate must pass all 32 with
the same unmodified fixture. Expected baseline failures are not baseline PASS.

Thirteen candidate source mutations must compile and fail at their named
runtime witness: single-start regression, no start, skipping Q3, starting a
different instance, wake in place of start, activation after failed open,
unconditional resume wake, activation in quarantine, omission of failed-open
quarantine, admitting a pending reader, skipping readiness open, ignoring GMAC
failure and treating VSI failure as success. Mutations edit one extracted
production function in the generated translation unit, never the input tree.

The `wake-instead-of-start` mutation is a design-fidelity negative control for
this specific successful-open fix: the selected minimal change retains start
semantics and does not add qdisc scheduling. Rejecting that mutation does not
establish that wake-all is generally wrong or unsafe. Flow-control recovery
can legitimately require wake and scheduling under its own reviewed contract.

## Evidence and Limits

Each run saves complete generated C and binaries, seven full input snapshots
per tree, test/extractor snapshots, compiler version, exact argv, compile/run
stdout/stderr and exit status, source/extracted-definition hashes, all artifact
hashes, per-queue transition records, and `RESULT.json`. Failed development
runs remain separate and must not be presented as successful verification.

All four generated result directories have been relocated, without rerunning,
to [the audit evidence directory](/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue).
The source test directory now contains only this README, RESULTS.md, run.py,
host_api.h and cases.c. See [RESULTS.md](RESULTS.md) for the move list and
[MOVE-VERIFICATION.json](/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/dp-multiqueue/MOVE-VERIFICATION.json)
for identical before/after file-tree hashes and the complete relative-path
inventory. Original command/DWARF/JSON absolute paths remain historical evidence;
use the recorded source-to-destination prefix mapping to locate moved files.

The Linux API substitutes follow 6.18.38 `include/linux/netdevice.h:3613-3685,
3967,4840-4857` and `net/core/dev.c:1660-1705,1729-1775,3416-3427,3467-3489`.
The last-reviewed local kernel files are under:
`/Volumes/FX-MD87/Review/RXDROP_ROOT_CAUSE_20261008/source/kernel-peer/linux-v6.18.38/`.
They are not kernel objects linked into this host binary. The START-bit
open/close envelope is substituted; qdisc activation, linkwatch, notifier chains,
PM and watchdog execution are not simulated.

The IPQ807x, PPE and MAC-poll compile-time branches are enabled as in the DP
Makefile. API/hardware callbacks are fault-injected substitutes; EDMA retirement
only checks caller identity and does not retire real backing storage. Scalar
locks enforce sequential balance, and the reader-drain substitute refuses
outstanding readers rather than pretending to wait. This suite does not prove
concurrency, scheduler progress, kernel memory ordering, lockdep, target ABI,
NSS H2N/PHIF delivery, EDMA IRQ/DMA safety, line transmission, or the runtime
cause of the B12 LAN fault. Published FW/DMA retirement, 035, LIVE/unbind remain
HOLD. Existing containment tests are a separate acceptance surface.
