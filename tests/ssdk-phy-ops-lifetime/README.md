# Shared PHY Ops: Bounded Module-Lifetime Repair

The baseline is exactly the 692-file, 36-layer d9a1964 prepared tree. Its
canonical sorted inventory hash is fixed in source.py; it is not automatically
refreshed from an input receipt. The runner applies live 049 at its exact declared
coordinates, with zero fuzz/offset, to a fresh complete candidate37 tree.
The repository's strict inspect_patch checks every complete hunk first;
verify_applied requires the patch engine output to equal those declared bytes.
The formerly truncated final-context-line specimen must be rejected before
native compilation. --patch-tool can select an explicit GNU patch binary.
Only hsl_phy.c and aquantia_phy.c may differ. Required --prepared supplies the actual
complete37 tree: all 692 files must equal that derivation before actual-function
extraction uses --prepared. PREPARED-COMPARISON.json records both paths, full
inventory and identity, and is rechecked at the end. This is source text preparation, not
make, target compilation, module linking or a full parent provenance receipt.
Only actual-prepared root version.date (decimal digits plus one newline) and
empty root .prepared_* files are classified as recipe metadata, recorded with
kind/size/hash and rechecked, not counted as code. Other extra files/directories,
dirty metadata and symlinks are rejected. Baseline stays exactly692, with no
metadata exemption. Three positive parser controls cover the two forms alone
and together; seven dirty/extra controls are separate from native SDK cases.

Seven complete actual functions, the registry initializer, the static Aquantia
initializer, actual ops callback typedefs, ops/metadata structures, PHY/error
enums and fixed capacity macros are extracted. Original Aquantia assignments
independently generate the field oracle; every field/function association and
MINI guard must match before native compilation. Callback declaration prefixes
come from the original Aquantia or qcaphy_c45_common definitions. Callback bodies,
hardware initialization, Linux allocation and locking are host substitutes.
Dependent fal value types are unsigned host aliases, not a target ABI proof.

The lock model uses pthread mutexes, per-thread IRQ/ownership state, actual
exclusion, acquisition/release counters and callback reentry. It is not an empty
spinlock stub and does not prove Linux IRQ/lockdep scheduling. Metadata is never
retired concurrently by this fixture: getter admission does not solve that
separate lifetime problem.

Four profiles cover full/MINI times I2C-metadata off/on, explicitly enabling
Aquantia. They are not evidence that default AX6 enables Aquantia. Seventeen
ordered positive cases per profile include the two original PHY witnesses
(device0 with no matching ports, and device0 sharing the type), now requiring
no ops free and a still-queryable peer. Borrowed heap/static ops, empty-device
cleanup, identity-sensitive busy unregister, exact error propagation, retry,
metadata-only freeing and competing publishers are also checked. Constructed
exit callbacks and transient registration failure are injected controls; the
baseline registry has no non-NULL exit callbacks.

Twenty source mutants per profile must compile cleanly and fail a selected
case with exit86, empty stdout, and one exact PHY_OPS marker. Two complete old
getter/cleanup counterexamples per profile are separately rejected. They do
not reclassify the old UK witness: UK/cohort remains KNOWN_OPEN_NOT_REPAIRED.
Compile failures, timeouts, signals and sanitizer failures earn no semantic
credit. Exact ordered stdout is independent of C output. Result pollution
controls and sanitizer activation canaries are reported separately.
LeakSanitizer is disabled (unsupported by this Apple runtime); no LSan/leak
qualification is claimed. Explicit modeled ownership/free counters remain
active. Borrowed heap test storage is released only by fixture module teardown,
after fixture publications are dropped, never by the SDK under test.

Example host invocation:

```sh
python3 -B tests/test-ssdk-phy-ops-lifetime.py --baseline /absolute/prepared36 --prepared /absolute/actual37 --cc /opt/homebrew/bin/gcc-16 --output /absolute/fresh-evidence
```

Use --sanitize with a sanitizer-capable host compiler. Output is RESULTS.json,
complete candidate37, generated C/binaries, and separate raw compile/run
stdout/stderr/commands/exit records. All input assets and both source inventories
are checked at the end. This runner does not change recipe, CI, old tests or git.
The short getter lock intentionally shares the writer arbitration protocol;
no performance benchmark or complete raw-reader-drain claim is made. An
acquire/release-only getter is not part of this patch.

No full unload/reader drain, borrowed provider/code pin, PHY attachment, MDIO,
global UK/SD ownership, root-fatal unwind, hardware/FW or device approval follows.
