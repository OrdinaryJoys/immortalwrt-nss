# NSS → EDMA quarantine host test boundary

The test input is an already prepared candidate tree with the actual DP package
patches applied. The harness extracts the actual C function definitions and
compiles them with explicit host implementations of kernel APIs. It does not
rewrite the candidate state machine into a separate model.

The independent checks cover four feature words in UP/DOWN detach; the permanent
quarantine latch; reopen, restart and reoverride refusal; repeated detach and two
ordered teardown callers for one port; init/close failures; in-flight xmit, RFS,
PHY, actual DP ethtool statistics and actual RX delivery callbacks;
rejection of new readers while the writer drains; a woken TX queue still dropping
one packet exactly once; initial NSS override; and an independently compiled
other-SoC branch. Threads coordinate with pthread conditions, never guessed
sleep durations.

The two teardown callers exercise a serialized same-port sequence, not actual
NSS core removal, cross-core RX remapping, firmware or DRV IRQ/NAPI cleanup.
The host wait predicate takes an extra fixture mutex to prevent a C11
mixed-access data race. It is deliberately stronger than the actual kernel
waitqueue memory-order semantics and cannot verify those semantics.

The host substitutes callback behavior, netdevice fields, RTNL, spinlocks and
waitqueues. Successful tests establish the behavior of the extracted candidate
C under these substitutes. They do not establish target-kernel scheduling,
lockdep, interrupt/NAPI safety, compiled module ABI, hardware state, packet
correctness, AX6 runtime behavior, or an actual successful NSS removal. No
network, router, kernel-module operation or CI dispatch is part of this harness.

The runner will record source and extracted-definition SHA256 values, compiler
identity, compile commands, test-asset and compiled-binary hashes, and named test
results. A Linux replay uses the same prepared input and test files with a native
GNU-C11 compiler, pthread support and Python 3.9 or newer. The runner fails if a
required actual definition is missing or ambiguous, or any extracted source
changes before the run completes or between the candidate SoC branches.

Run from any directory (the output directory must not already exist):

```sh
python3 test-nss-dp-detach-quarantine.py --baseline /path/to/prepared-baseline --candidate /path/to/prepared-candidate --output /path/to/new-result-directory
```

Expected result: 5 original baseline controls + 21 IPQ807X candidate assertions
+ 5 other-SoC controls = 31 compiled-C host cases. The baseline controls assert
the original defects rather than treating them as repaired behavior. A run
without `--candidate` is explicitly incomplete and cannot pass candidate gates.

## Candidates With the 015 EDMA Retirement Provider

The runner also detects the actual provider or its SoC prototype, not just the
quarantine call. Removing the call cannot silently select the older profile.
For this profile it binds the actual bool prototype and extracts the complete
`edma_disable_interrupts`, `edma_stop_napi`, `edma_close_member` and
`edma_retire_port` definitions and the EDMA structure/register headers. Only
kernel includes are replaced. A typed observation wrapper around DP calls
checks reader-drain order and delegates to the real retirement function; it is
not an empty retirement stub. Provider callbacks remain explicitly substituted.

Five additional boundary cases exercise invalid/foreign identities, the last valid port, closed
membership, active peers, repeated retirement and a foreign slot during
quarantine. Five further threaded cases retain an actual open host membership
until the admitted xmit/RFS/PHY/statistics/RX callback drains. No-member NSS
takeover cases remain separate. The old "no hardware callback" assertions refer
to no guessed NSS close/link/deinit, not to suppressing valid EDMA masking.

The last-open-member trace must mask, disable NAPI, cross a grace boundary,
mask again, unpublish and cross a second grace boundary. The external grace
substitute injects a modeled final-poll mask rearm so the final mask is not a
check of registers that were already zero. A peer or closed member needs only
unpublish then grace. Rejected identities and repeated retirement have no
effects. State outside owned membership, including host context and override
accounting, must remain unchanged.

This profile has 31 IPQ807X + 5 other-SoC controls = 36 candidate-only cases,
or 41 with the five original baseline controls. Twenty-one one-function source
mutations must compile cleanly and be rejected at runtime with their specified
reason. A compile error, signal, timeout, unrelated diagnostic or sanitizer
failure cannot count as a successful semantic rejection. Result-gate controls
reject polluted output, and positive runs require the exact ordered case-name
inventory, not just its count. Invalid/foreign calls each check the complete
state snapshot and have dedicated false-return-with-side-effects mutants.
`--sanitize` enables ASan/UBSan and verifies both with
separate injected-fault canaries. `NDEBUG` is explicitly forbidden because the
existing host synchronization assertions must execute.

Source, full-header, extracted-definition and generated-C hashes are recorded;
each compile/run has raw stdout/stderr evidence. Test assets and prepared inputs
must remain stable. Profiles before 015 retain 21+5 candidate cases, without
claiming EDMA retirement coverage. Extractor and admission controls can be run
with `python3 -B -m unittest discover -s tests/nss-dp-containment -p 'test_*.py'`;
the existing CLI integration tests require `DP_HOST_BASELINE` and
`DP_HOST_CANDIDATE` to identify the exact prepared trees.

None of this covers complete `nss_dp_remove()` ordering in 017, root rollback in
018, real RCU/poll-tail execution, IRQ/ring/MMIO retirement, hardware/FW idle,
kernel-module linking, runtime performance or router acceptance. Preparing a
current 001-018 tree does not turn unextracted paths into tested paths.
