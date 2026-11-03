# Tunip per-command ownership and error propagation

This independent suite qualifies only additive clients027 after exact vendor
51be82d43ef85079f78aa163d014223b05baa6a2 plus the26 frozen local patches.
The old NSS input suite/profile is unchanged and remains baseline-only.

Contract: each request owns its kernel-copy buffer and at most one selected
netdev hold. A successful repeated netdev lookup replaces the previous hold;
lookup failure releases the previous hold at the common exit. Last valid
selection wins, including same-pointer replacement. This is serial request
ownership, not module/netdev/provider lifetime or concurrent unregister proof.

FRAG requires an explicitly parsed0/1 value. Parse/missing-field failures use
-EINVAL; missing lookup or lower NSS node uses -ENODEV. Client status success
is0, its parameter/rule-type errors map -EINVAL, and all other failures map
-EIO. Positive SDK enums are not Linux errno. Provider failure is reported,
not rolled back; a failed FW command may have effects that this suite cannot
observe. Existing accepted scalar repetition, unknown-token handling, numeric
lexical/value policies and offsets are not generally redesigned.

The real parser, errno mapper and four complete write-wrapper bodies are
extracted from the prepared tree. Actual public enum/map types are retained;
Linux allocation/netdev/inet/numeric and lower provider APIs are explicit host
models, not target ABI or FW execution. Linux v6.18.38 sysctl calls the handler
with a kernel buffer, propagates a nonzero return, and returns count only on
success. A reduced transport check is not the complete proc/BPF/permission path.

No target/module/firmware/cloud build, make or device operation is used. No
saved audit program or binary is executed. New output directories are required.
Final CLI/count/hash details are recorded by the author freeze after validation.

```sh
python3 -B tests/tunip-command-transaction/source.py --prepare-output FRESH_PREP
python3 -B -O tests/test-tunip-command-transaction.py --clients FRESH_PREP/clients --cc CC --output FRESH_RUN
python3 -B -O tests/test-tunip-command-transaction.py --clients FRESH_PREP/clients --cc CC --sanitize --output FRESH_SAN_RUN
```

The source helper reads a fixed local Git cache, never a floating upstream HEAD.
It replays all26 baseline patches, checks all298 files against the immutable
baseline digest, then applies new027 under strict declared context/no fuzz or
offset and checks all298 candidate files. Only one C file may differ. All27
patch inputs/saved copies and the recipe are bound and tail-checked. Existing
005 EOF/023 declared-coordinate checker exceptions are explicitly logged;
the new027 has no such waiver. The frozen old input profile is read as data
under its fixed SHA, never updated or executed to accept the new27 tree.
Default version.date/empty prepared-stamp metadata has the same narrow proven
exception as the original source gate; arbitrary extra files/symlinks reject.

The fixed specification is58 positive case plans (including two explicit
two-request retry plans),22 source mutants,10 full-baseline legal-request
trace comparisons and4 safe old-body witnesses. Independent fixed inventories
are checked before execution and after completion. Six pure inventory
pollutions and a wrong-recipient expected-trace pollution are test-quality
controls, not driver defects. Results qualify only after every prescribed gate.
The old-body witnesses exercise defined duplicate/reference and return-state
paths, not old NULL dereferences or uninitialized reads.

The independent Python oracle does not parse native output into expectations:
each command has separate expected lookup selections, failure stage, errno,
provider operation and mathematical IP/map fields. Complete ordered traces
include every alloc/get/replacement put/free, immediate provider payload/status,
return value and per-request owner/frag ledger. Foreign device bytes and all
base holds must remain identical after each request. Provider calls observe a
held selected netdev and fully parsed fields before the local stack disappears.
The libc numeric leaf performs real conversions but models the selected Linux
vsscanf no-digit return0; overflow/full lexical equivalence remains excluded.

Every source mutant must compile clean with -Wall -Wextra -Werror, then fail
exact86 with empty stdout and one fixed marker. Compiler errors, timeouts,
crashes and sanitizer reports are not accepted negative evidence. The deliberate
postparse-buffer double-free mutant is caught by the model's exact owner guard
before a second real free, and is a safe boundary witness, not target crash
reproduction. Other ref/payload assertions are host ownership/API contracts.
The SDK memcpy macro is explicitly undefined only at the fixture's actual-C
copy-leaf boundary; production body bytes are not edited for host compilation.

ASan/UBSan controls must diagnose directed heap-buffer write/signed overflow
with exits97/98. Both runtime exit/abort options are set per canary and the
main environment remains unchanged. LSan is not verified. Derived source,
expected bytes (hashed from memory), binary/dSYM shapes, every raw command and
the exact output/input/saved-patch inventories are checked at the end.

All lower statuses in fault tests are controlled provider outcomes, not
natural reproductions of FW failures. The three actual public provider bodies
were read for return-domain/call obligations but are NOT compiled by this
suite: it does not execute message construction, tx_sync, firmware, netns/RCU,
module teardown or concurrent unregister. Unknown token and pre-existing FRAG
extra-field policy are not broadly repaired. The global frag flag is not made
transactional across concurrent requests. No old input gate is granted27-layer
qualification; it intentionally stays fail-closed for a changed patch inventory.
The new suite admits actual recipe30 only. Earlier recipe29 development results
are retained as history and are not current recipe30/asset qualification.
