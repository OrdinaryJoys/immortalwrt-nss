# IGS Action Admission (Bounded Host Regression)

This regression consumes offline prepared clients, not patches or an OpenWrt
build tree. It extracts complete actual modern `nss_mirred_init` and
`nss_mirred_release`, plus actual IFB create/delete/bind helpers and the relevant
action/map declarations and configuration enum. It reuses
`tests/nss-dp-containment/extract_prepared_c.py`. It does not invoke any archived
audit program, prepare sources, access firmware/devices/network/cloud, build a
kernel/module/package, or commit anything.

## Run

The authoring task did not run compilation or tests. Parent execution on
2026-10-23 subsequently passed GCC16 and Clang ASan/UBSan, each with both modern
version selections, the freshly prepared 015 candidate, 014 baseline and all
seven runtime negative controls (18 compiled/running variants per compiler).
These are bounded host results, not target or deployment qualification.
Run from the repository root, using different, previously nonexistent output
directories for every invocation. The script rejects existing output paths.

```sh
python3 -B tests/test-nss-igs-action-admission.py \
  /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/prepared-clients \
  --baseline /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/baseline-clients \
  --cc /opt/homebrew/bin/gcc-16 --mutations \
  --output /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/action-gcc16-new

python3 -B tests/test-nss-igs-action-admission.py \
  /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/prepared-clients \
  --baseline /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/baseline-clients \
  --cc /usr/bin/clang --mutations --sanitize \
  --output /Volumes/FX-MD87/Review-AX6/audits/20261023/igs-action-admission/action-clang-asan-new
```

`clients` is positional; `--output` is required. `--cc` defaults to
`/opt/homebrew/bin/gcc-16`; Clang is `/usr/bin/clang`. Compiler commands may contain
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

The 50 finite scenarios cover missing nla, parser error, missing parms, both zero
ifindices, missing source/target devices, unknown NSS source, IFB source and
non-IFB target; IDR check/race error; create allocation failure; both map-conflict
exits; dynamic allocation and registration failures; SET_IGS, SET_NEXTHOP and map
allocation failures. Post-admission new-object errors run with bind both true
and false. Existing nonbind errors replay three times on the same object without
resetting its state: refs/binds, module ownership, list links, action fields,
device references and unrelated mapping must remain intact. New/borrowed
registrations, reuse of an unmapped local entry, existing-bind with and without
map conflicts, normal new bind/nonbind and existing nonbind success are included.
Release also runs directly on empty/linked NULL-dev objects, a live mapping, a
missing map entry, and failed reset/clear replies. NULL-dev release is repeated.

Success checks preserve NSS create/register -> SET_IGS -> SET_NEXTHOP -> bind ->
dev_hold -> action publication order (existing map reuse need not allocate or
republish a map). The baseline must fail IDR check/create and existing-bind
sensitivity cases while preserving the successful-state signature. That signature
deliberately excludes IDR timing. Existing successful nonbind behavior is only a
contrast against the old implementation; no new replace semantics, device-ref
rebalance, idempotency or expanded replace correctness is claimed.

Seven strict-context source mutations must compile and then fail their intended
runtime cases: missing acquired-reference return, early release of an existing
bound action, missing list initialization, NULL-dev release reset/clear side
effects, NSS configuration before IDR, missing placeholder cleanup, and an
inverted release bind flag. The original source bodies remain untouched for
candidate/baseline; mutated bodies are generated only in the new output folder.
The missing-cleanup mutation retains a void reference to the helper symbol (not
a call), so an unused static helper warning cannot masquerade as a runtime kill.

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
lookup, config replies, reset/clear, module refs and device holds/puts are explicit
substitutes. Host errno numbers are not target Linux errno/ABI qualification.

## Still OPEN

**S01:** a failed configuration has UNKNOWN firmware effect. Existing code may
leave the new registration present; the model intentionally retains registration
and marks a failed config's effect unknown. It neither fabricates rollback nor
automatically clears/deletes unknown firmware state. Returning the action object
does not repair this finding.

**S03:** binding allocation failure still calls delete for a borrowed registration.
The regression records and expects that current behavior as an OPEN finding,
not as successful ownership repair. Unregister/dealloc do not implicitly erase
the modeled firmware relationship or its unknown effect.

The complete SQM transaction remains **OPEN**. A bounded host PASS means only
the tested action-admission/ref/list contract and preserved success contrasts
passed. It does not grant firmware, kernel ABI, real concurrency, module/target
build, deployment, end-to-end SQM, performance or overall repair PASS.
