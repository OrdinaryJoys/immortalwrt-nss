# Complete PBUF Optional-Write Return Chain

The repair retains existing successful skips (no configured governor, missing
CPU0 capability, empty capability list, no stats directory/nodes, and the
permanent offload/readiness/profile skips; see the readiness contract below for
the transient case, which now returns a failure, and for how a retry proves an
actual apply instead of trusting a 0 exit status). It does not change PBUF/RPS
values, governor selection, stats default, one-shot allocation, or Wi-Fi policy.

An applicable governor request now rejects unsupported values and preserves
read/CPU/write failures. Missing offline CPU controls remain skips; an existing
control that is not writable fails. The first actual CPU write failure stops
later optional work. Stats discovery must succeed before any writes; its
same-shell loop retains the first failed write while handling remaining known
nodes. `start` short-circuits on either helper's failure, so reload/restart
cannot report success or request Wi-Fi after that error.

## Bounded readiness retry (S5-02 / AX6-34)

`start` keeps the two bounded fast-path waits (5 s each). After them the
readiness state is classified explicitly:

| readiness state | start return | meaning |
|---|---|---|
| ready | 0 | ath11k exists, `nss_offload=1`, both NSS sysctl trees exist, and `apply_nss_config` set `pbuf_config_applied=1` after the profile readback matched |
| transient | 1 | ath11k exists but its parameter or the NSS sysctls are not published yet, or the sysctl tree vanished again before the apply |
| permanent skip | 0 | no ath11k device, `nss_offload` is explicitly 0, or the pbuf profile is disabled/unconfigured |

A transient state is no longer reported as success with the driver-default N2H
profile left in place: the initial boot attempt logs `user.error`, schedules one
detached retry chain and returns 1. The chain's attempts target cumulative
delays of 15 s, 45 s and 120 s after the chain is launched; the sleeps between
attempts are 15 s, then 30 s, then 75 s (so the cumulative targets are 15/45/120,
not the sleep lengths). The delays are not boot-absolute: the chain starts after
the initial S19 attempt has already spent up to 5 s + 5 s in the readiness waits,
and every retry attempt runs those same bounded waits plus sysctl readback
retries, so an attempt can begin later than its cumulative target. Every attempt
re-runs `/etc/init.d/qca-nss-pbuf start` with `PBUF_RETRY_ACTIVE=1` and a
`PBUF_RETRY_OUTCOME_FILE`; attempts made from inside the chain never schedule
another chain.

A `0` start status alone cannot prove an apply, because a permanent skip also
exits 0 without touching the profile. The child therefore records the outcome of
each attempt in `PBUF_RETRY_OUTCOME_FILE`: `applied` only after
`apply_nss_config` verified the profile, and `skipped` for a deliberate no-op.
The chain logs `profile applied by the bounded retry` only for a recorded
`applied` outcome (noting a non-zero start status when later non-profile steps
failed), stops with one `user.notice` on `skipped`, and treats a start that
returns 0 without any recorded outcome as unconfirmed: it keeps the bounded retry
and finally logs one exhausted `user.error` saying the profile apply was not
confirmed. It never reports success without the recorded outcome, so permanent
skip/offload-disabled/sysctls-absent exits cannot be mislabelled. `flock -n` on
`/var/lock/qca-nss-pbuf-retry.lock` makes a duplicate chain a silent no-op.
Permanent skips keep returning 0 without scheduling anything. The chain is
bounded and deliberately not procd-tracked.

```sh
python3 -B tests/test-qca-nss-pbuf-start.py --shell /bin/sh --mutations \
  --baseline OLD_INIT_SOURCE --output NEW_OUTPUT
python3 -B tests/test-qca-nss-pbuf-start.py --shell /bin/bash --mutations \
  --baseline OLD_INIT_SOURCE --output OTHER_NEW_OUTPUT
python3 -B tests/test-qca-nss-pbuf-retry.py --mutations --output RETRY_OUTPUT
```

Only the complete named functions are extracted, not the whole init. System
paths are explicitly remapped into isolated directories; the governor writable
predicate is substituted to avoid depending on root/chmod behavior. Configuration,
readiness, enumeration, discovery, NSS/RPS and Wi-Fi are controlled substitutes.
The actual writer runs only on isolated files, wrapped with injected errors;
real redirect-to-directory failures are also checked, without assuming Bash,
Dash and ash assign the same numeric status. PATH is empty and the old baseline's
seq command is explicitly substituted. Normal path order/values, partial
discovery failure, unsupported/empty/missing platforms, first/middle/last write
failure, exact injected error propagation, no Wi-Fi after failure, permanent-skip
success, and transient failure/scheduling are checked. The start harness also
records every retry-outcome call site: applied profiles must report `applied`,
permanent skips must report `skipped`, and transient or error exits must report
nothing.

The readiness/retry test extracts the four retry functions (readiness, outcome
recorder, scheduler, transient handler), maps sysfs/proc/lock/outcome/init paths
into a fixture tree, and substitutes the device probe, logger, sleep and the
re-run applier. It asserts the readiness matrix, the outcome recorder contract
(writes only inside an active retry with a file variable; write failure is
non-fatal and logged), the user.notice vs user.error split, the cumulative
15/45/120 s attempt targets (15/30/75 s sleeps), `PBUF_RETRY_ACTIVE=1` and
outcome-file propagation, the no-apply-but-exit-0 regression (no `applied` log,
one unconfirmed error per attempt, one exhausted error), a stale outcome file
that must be cleared before every attempt, permanent-skip handling,
applied-but-later-error reporting, duplicate-chain suppression, missing-flock and
missing-applier fail-safe skips, and static wiring/limits. Mutation variants
(masked readiness, no schedule, unbounded targets, missing retry env, exit-status
only success, no outcome cleanup, skip that does not stop the chain) must fail.
A real util-linux `flock` exclusion case runs only on hosts that ship the binary
and is reported SKIP otherwise.

The historical baseline runs only eight selected existing-function scenarios;
it does not use the new writer and is not used to prove injected writer errors.
This baseline already uses `read -r`; it has no attributed escaped-path bug.
Its five observed failing scenarios concern unsupported/read errors, actual
CPU/stats write failures and partial discovery. They are isolated scenario
failures, not five independent live faults. Current-source runtime negatives
cover propagation, discovery, first-error retention, path reading and
preservation of compatible skips.

The extractor is a fail-closed recognizer for current column-zero declarations
and closing braces, not a general shell parser/security sandbox. Body source
and path mappings require review. No production init is sourced, no real sysfs,
debugfs, proc/sys, network or performance command runs. Host Bash entry modes
do not qualify target BusyBox ash, rc.common/procd, hotplug or real policy/device
behavior. Writes across CPU/radio targets remain non-atomic; prior successful
writes and the earlier NSS/PBUF/RPS stage are not rolled back. Write acceptance
is not readback, firmware/performance or complete system recovery proof.
