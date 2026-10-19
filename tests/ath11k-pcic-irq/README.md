# PCIC partial IRQ ownership (host only)

Run `python3 tests/test-ath11k-pcic-irq-errors.py PREPARED --output NEW_DIR`.
Use `--baseline OLD_PREPARED --mutations --sanitize` for executable old-source
negative controls, five deliberately broken variants, and host ASan/UBSan.

The runner extracts actual prepared PCIC config/free and disable functions,
four hardware ring masks, MSI tables, CE counts and byte-preserved PCI/AHB
config-call/error-label and post-config MSI-data failure snippets. It does not
execute either complete probe.
The assignment API is wrapped for error injection through a macro rename;
the original function body is not rewritten. IRQ/NAPI/tasklet/kernel effects
are host substitutes, not actual interrupt scheduling or hardware qualification.

Coverage includes NSS on/off, single/multi MSI, no/alternating/all CE skips,
all lookup/request/11-group allocation failures, assignment failures, valid
IRQ zero, multiple actions on a shared vector, an unrelated shared owner,
affinity-before-free ordering, and repeated release on the fixed version.
Forty-eight successful action/flag/disable signatures must match the baseline.
Four zero-count assignments test the candidate only, avoiding undefined
division in the old implementation; official static tables remain positive.

The config API owns partial registrations until its caller frees them. PCI
must clear the affinity hint before free; hybrid AHB must free before returning
to the AHB probe error path. Those are the only two callers in the prepared
tree. Cleanup after success still requires the existing stop/disable/drain
sequence. This test does not prove full runtime teardown or coldboot recovery.

The fixed version has extra repeated-cleanup/zero-count assertions, so raw
check totals are not identical to the old negative control. Counts represent
resource assertions, not independent defects or performance measurements.
