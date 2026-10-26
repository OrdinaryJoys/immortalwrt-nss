# IGS Action Admission (Bounded Host Regression)

This regression consumes offline prepared clients, not patches or an OpenWrt
build tree. It extracts complete actual modern `nss_mirred_init` and
`nss_mirred_release`, plus actual IFB prepare/abort/bind/create/delete helpers and the relevant
action/map declarations and configuration enum. It reuses
`tests/nss-dp-containment/extract_prepared_c.py`. It does not invoke any archived
audit program, prepare sources, access firmware/devices/network/cloud, build a
kernel/module/package, or commit anything.

## Run

The 017 extension covers private host binding preflight as well as the prior
015 action-admission contract. Its explicit baseline must contain 015 admission
but predate 017 preflight (the author's baseline includes 016). With a baseline
and all thirteen runtime negative controls there are thirty compiled/running
variants per compiler, covering both modern version selections. These are
bounded host tests, not target or deployment qualification. Consult the actual
invocation's RESULT.json for execution status, rather than this usage document.
Run from the repository root, using different, previously nonexistent output
directories for every invocation. The script rejects existing output paths.

```sh
python3 -B tests/test-nss-igs-action-admission.py \
  /path/to/freshly-prepared-017-clients \
  --baseline /path/to/freshly-prepared-016-clients \
  --cc /opt/homebrew/bin/gcc-16 --mutations \
  --output /path/to/new-action-gcc16-output

python3 -B tests/test-nss-igs-action-admission.py \
  /path/to/freshly-prepared-017-clients \
  --baseline /path/to/freshly-prepared-016-clients \
  --cc /usr/bin/clang --mutations --sanitize \
  --output /path/to/new-action-clang-asan-output
```

`clients` is positional; `--output` is required. `--cc` defaults to
the host `cc` from PATH; local GCC16 is `/opt/homebrew/bin/gcc-16` and Clang is
`/usr/bin/clang`. CI explicitly passes `--cc cc`. Compiler commands may contain
arguments (parsed with `shlex`). `--baseline`, `--mutations`, and `--sanitize` are
optional, but omit them only for narrower local investigations, not final
baseline/mutation qualification. Both modern version selections, 5.4.0 and
6.18.38, run in every invocation. Sanitizers apply to every selected variant.
`-Wall -Wextra -Werror` remain enabled; no warning is disabled. Compile failures,
timeouts, signals, sanitizer diagnostics, missing summaries, and unrelated
negative-control failures are errors, never evidence that a mutation was killed.

## Contract And Coverage

IDR check/create precedes all NSS mutations and local map publication. Parameter
validation still precedes IDR. An existing action with bind returns zero, retains
the extra ref/bind for its caller, and does not configure NSS, create a map, hold
a device, or release that reference inside init. Fresh actions have a valid
empty list and a NULL device before NSS operations. IDR check errors own no
placeholder and must not clean one up; create failure removes exactly its own
placeholder. Subsequent errors return exactly the acquired action reference
using the original bind flag. Refcount zero invokes the actual release callback;
that callback must unlink safely before returning for NULL dev, without looking
up/resetting/clearing an unrelated mapping or dropping an unheld device.

The 54 finite scenarios cover missing nla, parser error, missing parms, both zero
ifindices, missing source/target devices, unknown NSS source, IFB source and
non-IFB target; IDR check/race error; create allocation failure; both map-conflict
exits; dynamic allocation and registration failures; SET_IGS, SET_NEXTHOP and map
allocation failures. Post-admission new-object errors run with bind both true
and false. Existing nonbind errors replay three times on the same object without
resetting its state: refs/binds, module ownership, list links, action fields,
device references and unrelated mapping must remain intact. New/borrowed
registrations, reuse of an unmapped local entry, existing-bind with and without
map conflicts, normal new bind/nonbind and existing nonbind success are included.
Additional cases keep an unmapped borrowed entry usable with allocation disabled,
keep existing-bind independent of allocation failure, and preserve borrowed
storage on SET_IGS failure and three repeated existing-nonbind SET_NEXTHOP failures.
Release also runs directly on empty/linked NULL-dev objects, a live mapping, a
missing map entry, and failed reset/clear replies. NULL-dev release is repeated.

Fallible private host reservation must precede any NSS create/register/config
side effect. Allocation failure must leave both new and borrowed registrations
untouched. Later errors free only private unpublished host storage; borrowing an
unmapped local entry allocates and frees nothing. Successful configuration is
followed by nonallocating binding publication, then dev_hold and action
publication (existing map reuse need not allocate or republish a map). Actual
private initialization and list publication are checked. The 016 baseline must
fail new/borrowed allocation-failure and normal-new ordering sensitivity cases
while preserving the successful-state signature. That signature deliberately
excludes reservation/IDR timing. Existing successful nonbind behavior is only a
contrast against the old implementation; no new replace semantics, device-ref
rebalance, idempotency or expanded replace correctness is claimed.

Thirteen strict-context source mutations must compile and then fail their intended
runtime cases: missing acquired-reference return, early release of an existing
bound action, missing list initialization, NULL-dev release reset/clear side
effects, NSS configuration before IDR, missing placeholder cleanup, and an
inverted release bind flag; plus late host reservation, missing private abort,
freeing borrowed storage, lost private ownership, claiming borrowed ownership,
and omitted binding publication. The original source bodies remain untouched for
candidate/baseline; mutated bodies are generated only in the new output folder.
Missing-cleanup/abort/publication mutations retain void references to their
omitted helper symbols (not calls). The older baseline similarly retains a
reference to the unused kfree substitute, so an unused static helper warning
cannot masquerade as a runtime kill. No warning is disabled.

## Extraction And Host Adaptations

Signature selection is exact and unique, with the original legacy/modern
conditional envelope retained as an artifact. Modern init includes its entire
brace-delimited body, including its original internal `#endif`. Modern release
has `#endif` between its signature and `{`: exactly those six directive
characters are replaced with spaces **only in the lexical discovery copy**.
The shared extractor finds its bounds; the original source bytes supply the
complete body. A synthetic `#if 0 / #error / #else` prefix balances the retained
original directive when compiled. Any unexpected signature/seam/definition count
fails closed; the body is neither truncated nor edited to silence parameters.
Legacy signatures and body branches are retained in envelope records, but legacy
execution is outside this modern host model. Preservation of legacy behavior
requires the parent's patch review/target validation, not a host-model claim.

`RESULT.json` records complete input-file hashes, definition/body/envelope and
adapted-text hashes, source line bounds, script/extractor hashes, complete host
prefix/model macro text, compiler commands, build/runtime return codes, per-case
state/traces, expected outcomes, and a bounded status. Each raw definition,
original envelope, adapted definition, full generated C translation unit,
compiler stdout/stderr and runtime stdout/stderr is saved. Input identity and
hashes are rechecked while saving results. A fresh output directory may remain
partial on failure and must not be reused.

The host prefix defines reduced netlink/action/device/message types and constants,
`__u32`, removes `__rcu` through a macro, aliases `tcf_action`, selects the kernel
version, discards logging, substitutes RCU assignment/dereference and locks, and
uses `ASSERT_RTNL()` to consume the actual init's otherwise unused `tp`. None
models actual RTNL, RCU, IRQ or scheduling. A defensive doubly linked-list model
reports invalid uninitialized nodes without crashing, so a negative control has
to produce a complete runtime result. IDR models an empty slot, a reserved
placeholder, a new action or an existing action; it tracks ref/bind counts and
module object ownership, and invokes the actual release on zero refs. It is not
the kernel IDR implementation, a concurrency proof or complete tc-core lifetime
model. New objects and map allocation use bounded static storage. Registration,
lookup, config replies, reset/clear, private storage ownership/publication,
module refs and device holds/puts are explicit
substitutes. Host errno numbers are not target Linux errno/ABI qualification.

## Still OPEN

**S01:** a failed configuration has UNKNOWN firmware effect. Existing code may
leave the new registration present; the model intentionally retains registration
and marks a failed config's effect unknown. It neither fabricates rollback nor
automatically clears/deletes unknown firmware state. Returning the action object
does not repair this finding.

**S03:** 017 removes the host-allocation failure trigger by reserving storage
before NSS mutation and making subsequent publication nonallocating. The new
entry flag owns only private unpublished host storage, never a firmware node or
a borrowed registration. Complete registration ownership and firmware
compensation remain OPEN. Unregister/dealloc do not implicitly erase a modeled
firmware relationship or its unknown effect.

**S05/S06/S08:** duplicate-mapping idempotency, existing-nonbind replacement
semantics, late reply correlation and module/request lifetime remain OPEN.
No asynchronous callback in the tested SET operations uses the private binding
record before publication; this allocation ownership does not establish a
general callback lifetime contract.

The complete SQM transaction remains **OPEN**. A bounded host PASS means only
the tested action-admission/ref/list and private-storage contract and preserved success contrasts
passed. It does not grant firmware, kernel ABI, real concurrency, module/target
build, deployment, end-to-end SQM, performance or overall repair PASS.
