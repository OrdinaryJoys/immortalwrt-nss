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
