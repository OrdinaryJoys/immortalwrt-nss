# Default and legacy MDIO node leases

Local increment after DP019/SSDK044 on `codex/ax6-lifecycle-owner-20261102`.
SSDK release23 adds045 after the unchanged32-layer chain; pin remains
d9a196497ecee2530722d906e0efe1b7408b6ef6. No target/firmware build or device access.
This does not complete UK/SD/PHY shared ownership or bus/provider retirement.

## Ownership and Change

- `of_parse_phandle` and the compatible/name lookups return local OF references.
  The default-bus phandle branch now releases its node after the bus lookup/add
  operation, preserving the exact return value even when add fails.
- The compatible fallback releases its node after `of_find_device_by_node`,
  including a missing platform device. The returned platform-device reference
  and MDIO bus reference are different resources, not transferred node leases.
- Legacy enumeration releases its parent node after use. The OF child iterator
  consumes the previous child when advancing; a port-limit break does not
  advance, so the still-held child must also be released. Exhaustion leaves
  child=NULL; the same final put is inert and does not double-release it.

No platform/device put, bus unregister/free, PHY ops free or new lock is added.
The borrowed bus table and platform ownership still require a joined reader and
provider contract. Per-port PHY parsing references are not included in045.

## Tests

`test-ssdk-mdio-node-leases.py` inserts complete byte-preserved actual functions:
`ssdk_dt_get_mdio_node`, `ssdk_dt_parse_default_mdio_bus`, `ssdk_dt_parse_mdio`.
It uses actual selected public types/constants via the existing type extractor.
OF lookup/iterator, bus/provider APIs, metadata storage and the PHY-parser
dependency boundary are explicit host models, not the Linux or SDK runtime.

Each of the6.18,6.1,5.15 preprocessor profiles runs1254 scenarios. They exercise
both legacy drvdata shapes, all three compatible-node selection routes,
phandle/fallback/missing lookups, provider/bus absence, add errors, emulation,
PHY-parser return alternatives, empty/exhausted/port-limit enumeration, disabled
children and preservation of existing port metadata/bitmaps. These are host
branch tests, NOT full support/target-build claims for three kernel versions.

Every scenario compares the full modeled non-OF observation and exact return
against the unchanged32-layer implementation, then checks OF lease balance
separately. Existing bus/platform holds are deliberately preserved, not counted
as fixed leaks. A separate return oracle and foreign-reference guards prevent
the old implementation's node leak from becoming the new expected behavior.

GCC16 and Clang17-ASan/UBSan each pass all three profiles,3 exact old-source
witnesses and10 runtime mutants. Python -O repeats the same full gate. Negative
controls must compile without diagnostics, actually execute and exit86 with the
exact selected ownership/error marker. Crashes, compile failures and sanitizer
errors are rejected as invalid witnesses. Earlier GCC-r1 preceded inclusion of
the real compatible selector and is not promoted to the final r2 qualification.

SSDK044's complete helper still passes45 scenarios /8 mutants on the33-layer
tree. The three actual-function shared UK/PHY witnesses still report
KNOWN_OPEN_NOT_REPAIRED. No owner counter, blanket mutex/RCU or forced free is
substituted for the missing global/provider contract.

## Remaining Work

- Per-port MDIO/I2C/external-node references, separately from provider handles.
- Distinguish acquired bus references, borrowed raw drvdata buses and owned
  I2C bus registration before any rollback/unregister change.
- UK/FAL/SD/direct/PHY reader admission, producer drain, typed provider/device
  leases, root failure rollback and last-holder retirement remain open.
- Default-bus `reg_mode` and PHY error/fallback policies are not changed or
  certified by a local-reference repair.
- The build checkout's old18/31 profiles/manifest remain frozen; a reviewed19/33
  integration profile and independent new build qualification are still needed.

## Sources

- [Linux OF lookup and iterator](https://github.com/torvalds/linux/blob/v6.18/include/linux/of.h)
- [Linux OF child traversal](https://github.com/torvalds/linux/blob/v6.18/drivers/of/base.c)
- [Platform-device lookup reference](https://github.com/torvalds/linux/blob/v6.18/drivers/of/platform.c)
- [MDIO bus lookup reference](https://github.com/torvalds/linux/blob/v6.18/drivers/net/phy/mdio_bus.c)

The production patch is replayed on the exact vendor Git object, not transplanted
from a different SSDK mirror train. Public API rules constrain this repair; they
are not Qualcomm approval of the local patch or hardware/runtime certification.
