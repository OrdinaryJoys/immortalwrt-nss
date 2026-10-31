# UK041a isolated ioctl transport host test

Run with Python optimization enabled and a fresh output directory:

```sh
python3 -O tests/test-ssdk-uk-transport.py --prepared /absolute/current/prepared --output /absolute/new/output --cc /absolute/gcc
python3 -O tests/test-ssdk-uk-transport.py --prepared /absolute/current/prepared --output /absolute/new/clang-output --cc /absolute/clang --sanitize
```

This suite binds candidate C SHA256
`dfa07229ff945bcc063b5d3cc0803cb41dfe816237e8add7c4a27b36c1065a64`.
It compiles the complete actual production C after removing only `#include`
lines (blank lines preserve original line coordinates). All bodies, globals,
guards, parsers, dispatch arities 1..10, native/COMPAT ioctl paths, open,
release, init and cleanup remain. Real SDK error enum, parameter structures,
capacities, parameter flags and `SW_OUT_ON_ERROR` are copied from the pinned
baseline28 headers. Scalar storage and Linux structure layouts are explicit
host models, not installation-header or target ABI validation.

Two profiles use current KVER32 paths and CONFIG_COMPAT: fixed minor254 and
no UK_MINOR_DEV (including the dynamic minor request255 -> assigned42 model).
Each runs the same fixed 15-case inventory. Fourteen actual-source variants
have an independent fixed case/marker/profile contract (27 executions; a
conflicting protocol is meaningful only in the nonconstant profile). Empty,
missing, duplicate, wrong-profile and wrong-marker inventory controls are
separate Python model controls, not production mutants.

The serial mutex model detects self-lock and API-lock -> misc-lock inversion.
Registration/deregistration hooks hold the modeled misc mutex and call the
actual open/native/COMPAT and lifecycle functions. Immediate snapshots include
all logical allocations and their entire payloads, not only current slots.
This is not threading, lockdep, scheduling, module/VFS pinning or reader drain.
`DEFINE_MUTEX` has static lifetime; no modeled init/destroy operation exists.

Allocator failures target command buffer and per-file context. Quarantined
allocations retain physical bytes until each case finishes so owner assertions
can inspect them safely. This does not prove real free/UAF behavior or
same-address reuse. Close is tested once and a second NULL close is a model
ownership check, not proof that VFS calls release twice. Epochs are full64 bit;
max and max-1 cases are intentionally seeded state boundaries.

Native user addresses are registered host regions. COMPAT uses explicit32-bit
handles mapped to regions, never truncated host addresses. Actual input parser
uses host unsigned-long rounding for both paths; COMPAT output rounds to4 bytes.
Copy failures, inner SDK result words and actual ioctl return SW_OK semantics
are distinguished. The descriptor lookup and command provider are controlled
typed leaves, not the real command table, hardware API or a target compat ABI.
Other pointer faults, malformed descriptor tables, legacy pre-KVER32 kernels,
non-COMPAT builds, SD/cohort/root integration and performance remain untested.

Compilation requires clean stdout/stderr, `-Wall -Wextra -Werror`; the sole
warning exception is `-Wno-unused-parameter` for existing actual callback
signatures (inode/cmd) in the unmodified whole bodies. No function is pruned or
silenced globally for other warning classes. Every mutant must compile clean
then exit86 with exactly one fixed assertion marker and empty stdout. Compiler
errors, timeout, crash or sanitizer reports never count as semantic rejection.
No assert-dependent side effects are used. Sanitized mode requires ASan97 and
UBSan98 activation controls, with leak detection disabled (LSan unverified).
Combined runtimes share the common exitcode flag. Each activation probe sets
both ASAN_OPTIONS and UBSAN_OPTIONS to its own expected exit code and logs
that local environment, while still requiring the correct diagnostic text.
Ordinary fixture invocations keep their original environment and exact86
semantic markers; no instrumentation or completion gate is relaxed.
The first parent Clang campaign is retained as FAILED: its ASan diagnostic
was present but UBSAN_OPTIONS'98 overrode ASAN_OPTIONS'97. This is a probe
configuration error, not a driver fault or a successful full campaign.
Reference: https://raw.githubusercontent.com/llvm/llvm-project/main/compiler-rt/lib/asan/asan_flags.cpp
(RegisterCommonFlags for both parsers, then ASAN_OPTIONS before UBSAN_OPTIONS).
Darwin dSYM files, if emitted, require Info.plist plus DWARF/fixture.bin and/or
the exact aarch64 relocation fixture.bin.yml path. Relocation-only GCC debug
output is opaque compiler data, not a symbol/debug-info validation claim.

Source trees, selected real headers, five owned assets, expected bytes and all
generated paths/bytes are checked at the end. Expected output hashes come from
in-memory oracles; compiler products are explicitly opaque outputs. Source
tree snapshots are stability records, not a new text-preparation qualification
or proof of a complete29-patch runtime. No prior audit program is executed.
