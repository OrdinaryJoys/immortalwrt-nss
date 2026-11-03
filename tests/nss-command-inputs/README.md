# NSS command-input leaf fixtures

Use a new output directory and the actual fully prepared driver/clients trees:

```sh
python3 -B tests/test-nss-command-inputs.py --driver DRV_PREP --clients CLIENTS_PREP --cc CC --sanitize --output NEW_DIR
```

`--sanitize` enables ASan/UBSan and requires activation controls with exits97/98.
Each canary sets BOTH runtime exitcode options to its one expected code because
Apple shares common sanitizer flags. The main environment is not mutated; each
raw invocation records the actual options. ASan must diagnose a heap-buffer
write and UBSan the designated signed overflow. Semantic negatives remain86.
The ASan indexed write is in a noinline helper so a GCC object-size UBSan
diagnostic does not preempt that directed store observation; both stay enabled.
Without that flag this is an ordinary host run. `--positives-only` always yields
DEV_ONLY, never a completed qualification. No make, module, firmware or device
operation is run. Saved audit programs/binaries are never imported or executed.

The fixed `profile.json` was authored from exact offline Git archives and full
existing patch replay. It is not refreshed from CLI trees. All code paths and
bytes must match its whole-tree inventory digests. The new patches are reversed
in a private copy to the fixed old-tree digest, then replayed to the fixed new
digest. Both copies are retained as source data. Runtime inputs and every output
are hashed; expected output hashes originate from in-memory expected bytes.
Only the explicitly authorized release pairs are ignored in a whole-recipe
normalization; all other recipe bytes and all patches remain fixed.

Default Build/Prepare generates only version.date plus a prepared stamp for
these two recipes. No recipe Build/Prepare override or src overlay is selected.
The checked default rules admit only a root version.date containing1..19 decimal
digits plus LF, and at most one empty root `.prepared_<md5>_<md5>` stamp. These
metadata bytes are individually recorded and end-checked, not included in code
digests. Malformed/nested/duplicate stamps, symlinks and arbitrary extra code or
build products fail. Nondefault QUILT/DUMP/configured/build trees are unsupported.

Twenty fixed cases cover the complete extracted scanner and firmware-info
functions; PPE parser plus both actual create/destroy callers; every mirror
command subparser/helper and the handler; full tunipip6 parser plus its four
actual write wrappers. Real vendor enums, constants and map-rule structure are
extracted. Linux structures, allocation, netdev references, strscpy/strim,
kstrtou32, sysctl transport and firmware/hardware APIs are explicit host leaves,
not target headers, ABI or firmware execution. Kernel proc string behavior was
checked against cached Linux6.18.38 sources. The actual core parsers are NOT
substituted or cropped to compile; `-Wall -Wextra -Werror` remains enabled.

Twenty fixed negative obligations are separate from metadata/inventory model
controls. Every mutant must compile clean, then exit86 with empty stdout and
one exact NSS_INPUT marker. Timeout, compiler failure, crash and sanitizer noise
never count. Four witnesses have narrower classifications: sequence-short
uses a memcmp range-check leaf before the old underflow can access memory;
tunip-size checks the actual allocation argument before unsafe token traversal;
tunip-suffix-length seeds the removed-validation variant's missing length to0
to avoid executing an uninitialized read. These do not reproduce a target OOB,
allocator failure mode or target uninitialized-read symptom.
The mirror-empty-name variant removes only the actual helper's NULL/empty
guard. A checked mirror strscpy leaf rejects those inputs before NULL access or
strlen-minus-one under-read. This is an instrumented boundary witness, not
credit for a sanitizer/crash. Direct NULL/empty inputs must return -1 without
overwriting an externally held output pointer, changing its bytes/references,
or calling lookup/put. Terminal mirrordev= is also passed through real parsers.
Normal/newline names and the existing 15-character IFNAME plus echo-newline
behavior remain covered; no overlong-name policy is changed.

PPE proc storage is deliberately overwritten by another modeled request after
proc_dostring. The actual parser must still use this request's private kernel
buffer. This serial interleave is not a threaded concurrency proof. Nonzero
write offsets are rejected before proc side effects. Read and proc errors must
not issue create/destroy calls. Netdev holds/puts and exact command arguments
are checked at success/failure boundaries. Proc backing-text updates remain
observable and are not claimed to roll back on later parse/provider failure.

The kernel user's copy boundary is modeled: old copy_from_user on a designated
kernel request returns a copy failure, never dereferences a fake userspace
address. Provider callbacks record actual received parameters and return
controlled outcomes; they do not emulate NSS firmware or real network devices.
Tunipip6's pre-existing semantic-failure return0 and FW diagnostic-only loader
behavior are retained. Legacy subparser defects beyond the repaired memory/input
boundaries (including duplicate/missing argument reference unwinds) are OPEN,
not swept into a claim that every malformed root command is transactional.

Prep history is explicit: old driver022 needs +18 coordinates; clients005 has
an EOF-without-newline outside this repair and clients023 has stale coordinates.
No old patch was edited. Old-chain parser exceptions are retained, so do not
describe the entire historical chain as declared-line zero-offset validation.
Both new patches require full declared context and whole-result verification.
