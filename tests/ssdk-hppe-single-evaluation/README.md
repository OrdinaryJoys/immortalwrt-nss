# HPPE Single Evaluation Host Model

Fresh outputs only, from the repository:

```sh
python3 -B -O tests/test-ssdk-hppe-single-evaluation.py --cc gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-hppe-single-eval/HPPE-TEST-parent-gcc-r1
python3 -B -O tests/test-ssdk-hppe-single-evaluation.py --cc clang --sanitize --output /Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-hppe-single-eval/HPPE-TEST-parent-clang-r1
```

`--positives-only` is a development checkpoint, not final qualification.
No make/target/module/firmware/cloud/device build, push or execution of saved
audit scripts/binaries. Author develops GCC only; parent fresh GCC/Clang and
independent test-quality acceptance are separate.

## Inputs And Extraction

Fixed d9a196497ecee2530722d906e0efe1b7408b6ef6,25->26/03880c3fade,
plan de649608, identity7405dbc8, receipts c3956ae5/9f47f173. Hash-bound
current repo pure edma_patch_context.inspect_patch freshly applies all26 at
declared coordinates/full context/zero offset. All692 archive/base/candidate/
fresh files, pin, saved/current patch bytes and inventories are checked.
An independent25+038 derivation changes only src/hsl/hppe/hppe_init.c.
Current recipe16 is strict; only one complete16->15 reversal may match the
whole historical15 recipe hash. Extra patches are rejected, not ignored.
End gates recheck every asset/input, both saved inventories/live26 and all
three692 trees. Snapshot stability is not an atomic filesystem lock. The
generic binder/strict IO patterns follow prior repo tests, but no old PASS
or source qualification transfers to26.

Complete actual hppe_init, hppe_portproperty_init, hppe_dev_init and
hppe_cleanup bodies are extracted, not cropped projections. Complete actual
hsl_port_prop_init/init_by_dev/cleanup_by_dev/set/portmap_set,
hsl_port_validity_check, HSL dev getter and API getter are extracted.
The helper definitions are name-only renamed behind explicit counting/fault
wrappers; successful calls execute their full real bodies. Baseline25
init/cleanup/property are complete name-only aliases; dev/helper bodies are
byte-identical and shared. Extraction records path/line/hash. Wrapper fault
short-circuit is always labeled synthetic, never an unmodified actual path.

SW_RTN_ON_ERROR, SW_RTN_ON_NULL, HSL_DEV_ID_CHECK and bitmap macros remain
actual text. Real hsl_port_prop_t (0..4/BUTT5), a_bool_t/sw_error_t/HSL enum,
capacities3/16, hsl_dev_t, port_info_t, ssdk_port_cfg, scalar aliases and
fal_pbmp_t conditional are actual. Host unsigned bases are explicit uintN_t;
bounded ctypes layouts derive from actual small fields/array dimensions and
are checked by C static assertions. This is not target ABI/header-graph proof.
No fake int property typedef or hand-written1/2 property constants.

ssdk_init_cfg is an explicit reduced model (cpu_mode, actual port_cfg, cookie).
hsl_api_t is a reduced11-field model: dev_clean has the callback signature
used by the caller; ten SD fields are identity-only compatible host tokens,
not their target signatures and never invoked. Actual HSL/API getters use
their actual static-array declarations over these types. Callback identities
are checked individually, not just nonNULL. The installed real dev_clean
function is invoked with the actual dev ID; direct HPPE cleanup and direct
port-helper controller flows are recorded separately.

## Profiles And Fault Contracts

Neither/KERNEL_MODULE/USER_MODE/both are four independent compilations of
the exact source guard. Only both skips port-info/property/API work in
hppe_init. Explicit direct helpers are separately selected, not evidence
that combined hppe_init executes those bodies. Guarded-out schedules are
labeled and cannot earn active-site negative credit. Source relationships
to HPPE/APPE/MRPPE do not mean execution of their hardware initializers.

OS allocation/copy/zero/free are explicit host leaves. Allocation returns
zero storage, consistent with the Linux backend's __GFP_ZERO contract; cfg
and port-info sizes are model/actual-small sizes respectively. OOM is
host-injected at a naturally fallible source branch, not a real-device OOM.
Cfg first/persistent failures, port-info first-fail-next-success and persistent
failures are tested; exact first return and allocator/callee counts are
independent oracles. Explicit retry is a new caller attempt, not hidden
second evaluation. Helper/reset/setter/cleanup/manual DEV/PROP errors are
synthetic schedules before real body execution: on the admitted valid path
these helpers normally cannot fail. Each of ten038 sites has first-error,
different-second-error and persistent-error coverage where actually called.

Bitmap providers are explicit leaves returning global_bmp/global_inner,
deliberately different from cfg LAN/WAN/inner. Dev metadata derives from cfg;
property rows derive from global providers plus selected CPU. CPU0/15,
multiple lowest-bit, no CPU/high-only, sparse/overlapping front/inner, all
valid devs and invalid init IDs are covered. Original overlap counting is
preserved, not normalized. Loops only exercise actual0..15; no invalid
cleanup or unsafe port16 is run to obtain crash credit. Existing helper's
port16 comparison and arbitrary negative property enum domains stay OPEN.

## Owners Are Not Repaired

No automatic normal cleanup occurs after failed init. Cfg OOM creates no
owner; downstream failure after cfg acquisition leaves cfg live. Failed
cleanup returns the dependency's first error and retains cfg (and port-info
when the synthetic helper did not execute). Both callback absence leaves
cfg live. A separately explicit direct-cleanup test is not a registry/drain
fix or proof that callers do that in combined mode.

Preexisting cfg is reused and copied into; it is NOT rejected as borrowed.
The old reset sets p_port_infoNULL without freeing old storage; repeated
init can displace a previous owned object, borrowed port-info remains live
but unreachable, and these states are required by the unchanged contract.
All FOREIGN and OWNER IDs, kind/live/reachability are printed and matched;
no blanket live==0 oracle hides gaps. Peer tuples/metadata/API and unrelated
foreign bytes remain stable. Current borrowed cfg writes are explicitly
allowed because actual source copies it, not falsely called preserved bytes.
Logical frees quarantine storage until after reporting the owner ledger;
final fixture storage release is not driver cleanup, UAF or kernel lifetime
certification. LSan disabled/unqualified.

## Oracles And Gates

Independent Python uses mathematical bitsets/enum domains, complete metadata,
property rows/phy IDs, cfg copy, callback tokens and owner ledgers. It emits
full selected MODEL action/argument/return/state trace, not all driver logs.
Native first-return list and all ten call counts are checked before output;
then the entire memory-oracle expected trace is compared. Runner requires
byte-identical stdout and empty stderr. No assert side effects; Python -O
recorded and3.9-compatible population counting. Expected hashes derive from
memory, never read-back files as truth.

The direct helper retain-state case deliberately does not clean port-info
before state comparison; its full five rows remain observable even in both
profile. The wrong-row source probe uses this case, not a successful cleanup
trajectory that legitimately removes the state before the terminal snapshot.

Current-source negatives restore one call site to repeated evaluation or
mutate selected state/callback/owner-boundary behavior. Source bodies remain
complete and compile cleanly before each probe. All negative probes require
exit86, empty stdout, one exact named SSDK_HPPE marker. Compile failure,
timeout, signal, crash or sanitizer diagnostics earn no credit. Ten repeated-
evaluation controls use three bounded schedules per compiled variant. Complete
baseline success traces are compared separately. Safe old-source witnesses
show first-return/call-count mismatches at natural allocator/dev-error or
explicit synthetic helper paths; no claim of target OOM, leak or HW diagnosis.
Owner-preservation mutants deliberately test unchanged OPEN boundaries; they
are not endorsements of resource leakage or proposed rollback repairs.

An independent runner manifest fixes each profile/name/symbol/case/marker/
classification tuple, including all three schedules at each active site.
Expected inventory never comes from variants(), observed results or len>0.
Before compiler execution, the flattened actual source/witness plans must
match exact unique obligations. Before HOST_MODEL_ONLY, separate actual
source_negatives/old_witnesses and their aggregate must match again, with
clean-compile/exact86 execution verdict and source hash. Empty/missing/
duplicate/wrong profile/name/symbol/case/marker/classification/extra ledger
or unexecuted records are rejected by precise gate controls. These pure
inventory controls are NOT native model controls or production failures.
No final completion claim is available to --positives-only (DEV only).

IO gate pollution controls and modified/truncated/deleted/renamed/extra
expected/generated/nested rogue RESULTS controls are separate, not production
mutants. Exact generated regular-file inventory excludes only this run's
root RESULTS.json and separately verified fresh26. Optional binary.dSYM
requires Info.plist/DWARF/binary and permits only host Relocations/binary.yml;
unknown members rejected before opaque compiler outputs are hash-bound.
Only -Wno-unused-function is allowed alongside -Wall/-Wextra/-Werror/
-Wformat=2. Clang ASan97/UBSan98 activation canaries are required; normal
runtime environments both exit97 and are recorded. Author GCC alone does
not qualify parent sanitizers or independent test-quality acceptance.

## Open / Test P2

No root/HSL outer cfg/adapter/UK/PHY/shared-bootstrap ownership repair,
SDK/Linux errno fix, APPE/MRPPE/HW/FW/DMA/RCU/device/throughput result, real
kernel allocator/refcount/ABI/concurrency/drain or arbitrary helper-domain
qualification. No invalid cleanup, actual SD IO callbacks or full huge
cfg/API installed-header graph. Single evaluation/first-error acceptance
does not grant safe publication/rollback or close existing displaced owners.
