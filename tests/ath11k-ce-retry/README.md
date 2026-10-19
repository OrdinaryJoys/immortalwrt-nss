# CE RX retry cleanup scope

Run `python3 tests/test-ath11k-ce-retry.py PREPARED --output NEWDIR`.
Optional `--baseline PRE947_OR_R14_TREE --mutations --sanitize` compares
the same assertions against older input and four broken implementations.

The fixture compiles byte-preserved prepared CE cleanup, RX posting and
retry callback functions, native/PCIC start and stop, and the full core
crash-reconfigure function. Timer, IRQ/tasklet, firmware, DMA posting and
RX cleanup boundaries are modeled. In-flight completion is a deterministic
timer-API contract model, NOT real kernel scheduling or a DMA concurrency test.

For 1..12 modeled CE counts it covers idle/pending/in-flight timers,
native and PCIC stops, recovery success/failure, controlled-reset IRQ
preconditions, late expiry at cleanup, callback rearm, restart without
timer_setup(), normal success/ENOSPC and repeated stop/start. 1802 assertions
over 218 scenarios pass; r14 has 528 failures. No-drain, late-drain,
permanent-shutdown and AHB-only mutants must fail executed assertions.

Callers still own IRQ/tasklet producer shutdown. Native AHB uses the
full CE disable/sync/kill sequence, but hybrid recovery uses an except-wake
HIF operation: this test does not close its wake-CE producer contract.
QMI_FAIL partial remove bypassing common cleanup, final CE/HAL ownership,
shadow timers and complete NSS/MAC/DP recovery remain separate open gates.
Do not infer hardware performance or complete lifetime safety from this test.
