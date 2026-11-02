# SSDK per-port PHY parser temporary node leases

## Production scope

Patch 046 changes only ssdk_dt_parse_phy_info in src/init/ssdk_dts.c.
SSDK release 24 retains the same d9a196497ecee2530722d906e0efe1b7408b6ef6
source pin and the previous 33 patch layers. Strict preparation yields 34 layers
and 692 files. DP 019/release 10 remains unchanged and local-only.

The parser obtains temporary MDIO, outer I2C-presence, external-child and
switch-handle OF references. Patch 044 separately balances the registration
helper's own inner I2C lookup; it does not balance this outer lookup.
Patch 046 puts the four temporaries after their last uses for each completed
port, clears local pointers before the next iteration, and puts any remaining
temporaries at the existing error label before its iterator/container puts.
Normal iterator exhaustion also reaches that label, so clearing locals is part
of the ownership contract, not an optional cosmetic change.

The input switch_node is borrowed. Published scalar metadata is not an OF
reference. A bus lookup's device reference, an adapter reference and an owned
registered bus are separate resources; this patch does not put, unregister,
free or roll them back. It does not erase published tables, change errors or
alter UK/SD/PHY callback lifetime, locks, performance parameters or upstream pins.

The generic reference rules are verified against Linux v6.18 of.h/base.c.
of_mdio.c/core.c are also inspected: storing a node with device_set_node is not
a transfer of this parser's extra lookup reference. This does not qualify the
complete provider lifetime or dynamic-DT detach path.

The previously accepted stock kernel.config (run 41368954700, artifact
13112061088, SHA256 77cc42acb6c2a4cb8b046c78f1aaff8c9e9aefb44739346fc059e311fab49284)
does not enable CONFIG_OF_DYNAMIC; CONFIG_OF_KOBJ=y is a different option.
Linux v6.18 implements get/put as no-op reference counting without OF_DYNAMIC.
The modeled reference failures therefore do not demonstrate a memory leak,
use-after-free or throughput cause in that stock image. The correction matters
for the general reference contract/configurations with counting enabled; actual
dynamic-DT detach safety still requires the provider lifetime audit above.

## Host tests

test-ssdk-phy-node-leases.py extracts the complete current and previous
ssdk_dt_parse_phy_info plus the real ssdk_dt_get_mdio_node,
ssdk_mdio_i2c_bus_register and ssdk_dt_read_port_values bodies. Current function
bytes are preserved; old symbols are renamed only to link both versions.
Public types/constants and the private port-values structure come from the
prepared source, not guessed ABI declarations. OF/provider/metadata leaves in
ssdk-phy-node-fixture.c are explicit, stateful host models, not kernel or vendor
implementation qualification. In particular the I2C allocator's vendor call
shape is modeled, not independently proven compatible with the target kernel.

Eight feature profiles combine CONFIG_MDIO_I2C, IN_PHY_I2C_MODE and IN_SFP_PHY.
Each runs 5288 scenarios: 5280 matrix cases plus a missing-container case and
seven named probes. The matrix exercises port counts, availability, lookup
layouts, compatible selectors, reference aliases/unrelated holders, selected
property failures, early and later errors, allocation/registration/table
failures and repeated calls. This is not exhaustive property-domain or callback
interleaving coverage. Registered/allocated buses, adapter/device refs, scalar
tables, metadata, private state, actions and return values must match the
previous version; a separate oracle checks the first fresh call's return.
The current parser's temporary nodes must balance after every execution.
Old provider leaks and ignored errors are deliberately not normalized away.

Each compiler run also requires three old-source leak witnesses and seventeen
candidate source mutants. Mutants cover normal/error leaks, stale local double
puts, a foreign switch put, early put/use, freeing a registered bus, swallowed
errors and destroyed published state. A negative must compile, exit exactly 86
and print its unique expected reason; compile failure, crash or sanitizer exit
does not qualify. The old witnesses are not candidate negatives.

GCC 16 and Clang 17 ASan/UBSan pass all profiles/witnesses/mutants. Python -O
repeats the full GCC run. Generated C matches across compilers. -Werror remains
enabled. The real, unchanged I2C helper has an unused dev_id formal parameter;
only that helper is wrapped in a scoped unused-parameter diagnostic exception,
with a token-count guard. No general unused-parameter suppression is added and
no function body is edited for compilation. All other emitted diagnostics fail.
This explicit exception is not a zero-warning claim about the full vendor tree.

The first GCC attempt stopped on that existing unused parameter before profile
1 executed; it is retained as failed harness evidence, not a target-driver
failure or passing negative. An initial patch hunk-count typo was similarly
rejected by strict text preparation and corrected without weakening the gate.

## Regression and boundaries

On the new 34-layer source, Clang ASan/UBSan rechecks patch 045 with three host
kernel-selector profiles, 1254 scenarios each, three old witnesses and ten
runtime mutants. Patch 044 retains 45 scenarios, its old-source witness and
eight mutants. These are not target builds for three kernels. The three
constructed shared UK/PHY ownership witnesses still report
KNOWN_OPEN_NOT_REPAIRED; they do not establish a live router fault.

MDIO table lookup-ref/borrowed/owned discrimination, duplicate/full-table
rollback, provider retirement, per-port partial publication and error
propagation, shared UK/SD/PHY admission/drain/last-holder responsibility and root
FAL/PHY rollback remain open. Real RCU/NAPI/IRQ/HW/FW/DMA, 017/018 integration,
loss/latency, bidirectional throughput and performance qualification remain open.
No new target/firmware/cloud build, device action, push, main merge or Release.
The old build lock intentionally excludes these local repairs.

## Evidence

Local evidence root:
/Volumes/FX-MD87/Review-AX6/audits/20261102/phy-port-node-retirement/

- GCC-r2, CLANG-ASAN-r2, GCC-PYOPT-r2: actual C, compiler/run outputs and RESULTS.
- MDIO045-REGRESSION and I2C044-REGRESSION: previous fixes on current inputs.
- SHARED-STILL-OPEN: three explicitly open shared-resource witnesses.
- LOCAL-QUALITY.json: whole-tree/function scope, prior-input continuity,
  exact case separation, byte readback, source/test and build-worktree checks.
- Strict source prepare: audits/20261030/ssdk-dp-retirement/
  20261102-phy-port-node-owner-34-r2/RESULTS.json.

Frozen earlier 9-file and 13-file quality receipts are historical qualifications,
not silently refreshed expectations for this 17-file/SSDK release 24 batch.
