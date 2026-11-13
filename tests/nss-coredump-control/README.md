# NSS Coredump Empty-Write Control

This host test extracts the complete `nss_coredump_handler()` from two prepared
driver trees and nine complete parser functions from Linux v6.18.38
`kernel/sysctl.c`. It never builds or runs a firmware image and never writes to
either input tree. Python 3.9+ and a C compiler with ASan/UBSan are required.

```sh
python3 tests/nss-coredump-control/test_runner.py
python3 tests/nss-coredump-control/run.py \
  --baseline /path/to/prepared-001-through-029 \
  --candidate /path/to/prepared-with-coredump-guard \
  --kernel /path/to/linux-6.18.38 \
  --cc clang \
  --output /path/to/new-host-results
```

`--output` must be new and outside the input and test directories. All generated
C, executables, compiler temporaries and JSON evidence stay there. Source input
hashes, extracted-function hashes, commands, exit codes and complete stdout/stderr
are recorded. The candidate handler must differ only by the reviewed
`|| !*lenp` guard. The kernel parser hash is deliberately pinned; source drift
requires a contract review instead of silently replacing the parser with a mock.

## Confirmed Boundary

A zero-length write makes the real parser return zero with length zero and no
value assignment. The old NSS handler nevertheless republishes its stale local
policy snapshot. A completing concurrent policy write can therefore be lost,
including with `nss_ctl_debug == 0`. Debug-enabled paths additionally repeat an
old dump request or report readiness/shutdown errors for an empty write.
The guard makes this one path a no-op. Nonempty writes, policy-only writes,
normal reads, parser errors and existing request-error policy are unchanged.

The deterministic interleaving hook completes another scalar policy store just
after the handler snapshot load. It is not a pthread/kernel concurrency proof.
NSS readiness/request dependencies are stand-ins: no real interrupt is sent.
The parser decision tree and conversion/whitespace/output functions are actual
source. Only `strtoul_lenient` uses libc `strtoul`; test inputs are small decimal
values, so no general kernel number-parser equivalence is claimed. Linux's
`sprintf` is retained verbatim; the host deprecation warning is suppressed.

## Acceptance

- Candidate: 19 cases, zero failures.
- Unchanged baseline: exactly 11 named runtime failures.
- Inverted empty-length guard: exactly 28 named runtime failures.
- Disabled valid trigger: exactly two named runtime failures.

All variants must compile. Timeout, signals, compiler failures, sanitizer output,
unexpected output, missing summaries or merely nonzero exit status do not count
as successful negative controls. The runner's extractor and acceptance rules
have five disk-free unit tests.

## Parser Caveat

The pinned 6.18.38 source uses `proc_dointvec -> do_proc_dointvec ->
__do_proc_dointvec`; it contains no `proc_dointvec_single`. The public header
likewise declares only the vector API. `table.maxlen == sizeof(int)` limits this
call to one integer; it does not select a different single-value implementation.

For **nonempty** writes at nonzero position in strict mode, the parser returns
success, preserves the old value and nonzero length, and advances the position.
Consequently `!*lenp` is not a general "did the parser assign?" test. Three direct
parser cases and two NSS offset cases preserve and expose this distinction.
Ignored nonempty writes remain open, not repaired or certified by this patch.

Primary sources: [parser](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/kernel/sysctl.c),
[public API](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/include/linux/sysctl.h),
[proc dispatch](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/fs/proc/proc_sysctl.c),
[write syscall path](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/fs/read_write.c).
The ordinary write syscall reaches proc's handler for length zero; this is not
inferred from writev/io_uring paths that may reject empty iterators earlier.

No queue/gate/ACK/HOT policy, ownership, provider lifetime, committed DMA,
connection-table release or FW retirement semantics are changed or validated.
