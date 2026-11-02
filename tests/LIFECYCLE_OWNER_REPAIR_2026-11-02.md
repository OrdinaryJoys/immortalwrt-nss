# DP bridge owner and SSDK OF-node lifetime

Local candidate based on bcdaec80470bd7fd58b32aebd07f49f2626b4b66.
Branch: `codex/ax6-lifecycle-owner-20261102`. This batch is not in the already
accepted stock run41368954700 or its r0-bcdaec8 firmware. No firmware build,
device access, performance setting change, main merge or release in this batch.

## Confirmed Repairs

DP019 / release10 restricts forwarding restoration to removal of the owning
bridge master after membership ends. A VLAN or other non-master upper removal
must not override the physical port's bridge STP policy. Kernel v6.1 and v6.18
both save `changeupper_info.master` before unlink, then send CHANGEUPPER after
unlink under RTNL. The existing RCU-protected bridge query is reused; no new
packet-path lock or DMA/IRQ/NAPI change. FAL write failure reporting remains
the previous behavior; this repair is not a hardware transaction rollback.

SSDK044 / release22 retains the local `of_parse_phandle` reference until the
I2C MDIO registration call finishes. Lookup and allocation failure release it
once. This is only the temporary node lease: it does not claim to repair adapter
references, bus publication, provider removal or global PHY operation retirement.
The vendor three-argument allocator call shape and conditional feature policy
are unchanged. The optional path has not received a new target compile.

## Local Verification

`prepare-dp-lifecycle.py` exports the exact DP Git object and verifies all19
patches at their declared coordinates with complete pre/post bytes. SSDK uses
the existing strict `ssdk_source_prepare.py` for all32 patches /692 files.
All preceding patches are unchanged. Only `nss_dp_switchdev.c` and
`src/init/ssdk_dts.c`, respectively, differ in the complete prepared trees.

`test-dp-bridge-owner.py` extracts the complete real callback and bridge helper:
4810 scenarios per compiler,8 exact runtime mutants, old18-layer reproduction.
The matrix includes attach/detach, upper kind, original master identity, current
bridge, physical/private eligibility, all five initial STP states, FAL failure,
null payload/device, reader balance and unchanged foreign/input state. Some
combinations are defensive inputs, not claims of reachable Linux topologies.

`test-ssdk-i2c-node-owner.py` executes the complete real helper:45 scenarios per
compiler,8 exact runtime mutants and an old31-layer witness. It tracks acquired
node refs separately from unrelated refs, registration-stage liveness, lookup/
allocation/register failures and existing unpublished-bus rollback. Adapter refs
are deliberately reported as unresolved, not disposed by an invented stub.

Both tests passed GCC16 and Clang17 with ASan/UBSan, and repeated with Python -O.
Mutants must compile without diagnostics and execute with exactly exit86 and
the expected unique semantic message; compiler failures, crashes and sanitizer
exits do not count. The actual legacy DP retirement fixture still passes36
candidate-only positives /21 runtime mutants on the new19-layer tree. Existing
statistics checks also pass; this does not supply a shared hardware reset epoch.

The API substitutes are models, not real RCU, RTNL, FAL, MDIO, firmware or DMA.
Neither scenario counts nor sanitizers prove kernel concurrency or AX6 runtime.

## Open Shared-Resource Contract

`witness-ssdk-shared-ownership.py` executes real cleanup/getter functions and
explicitly reports KNOWN_OPEN_NOT_REPAIRED, not PASS for the SDK. It reproduces:

- PHY cleanup for one device retires a global ops table still used by another,
  including a case where the retiring device has no bitmap ownership. A retained
  raw reader is not drained. Free is recorded, not performed on host storage.
- In the non-HPPE UK_IF profile, per-device HSL cleanup shuts down the global UK
  endpoint while another device configuration survives. Native HPPE guards,
  root reachability and actual UK transport are separate unverified boundaries.

Both GCC and Clang reproduce these three constructed witnesses. They are not
proof of an observed multi-device AX6 failure. SD still stores12 typed global
borrowed callbacks; NULL inherits and matching function addresses do not lease
the dev_id provider. No last-holder or reader drain has been installed here.

Before changing root cleanup: inventory every UK/FAL/SD/direct/PHY reader and
producer, define typed provider/device leases and internal init/exit operations,
then join acquisition ledger, publication, failure rollback, last-holder cleanup
and provider retirement. Resolve sleeping versus IRQ-off contexts first. A
counter-only change, blanket mutex/RCU, per-device global free, or module_exit
BUSY return is not a complete repair. Keep017/018 whole flow and external
HW/FW/DMA idle/epoch ownership open.

## Integration Gate

The build checkout and its exact18-layer DP /31-layer SSDK source manifest remain
unchanged. They intentionally do not qualify this new candidate. Do not update
their hashes from unreviewed input or reuse old cloud acceptance. Before any
later build: add explicit reviewed19/32 profiles, bind the new tests and source
manifest, test rejection of old/mixed profiles, and only then review a new lock.
No such build or version-lock update was requested or performed in this batch.

## Sources

- [Kernel v6.18 unlink contract](https://github.com/torvalds/linux/blob/v6.18/net/core/dev.c)
- [Kernel v6.1 unlink contract](https://github.com/torvalds/linux/blob/v6.1/net/core/dev.c)
- [Kernel OF reference contract](https://github.com/torvalds/linux/blob/v6.18/include/linux/of.h)
- [Kernel MDIO registration](https://github.com/torvalds/linux/blob/v6.18/drivers/net/mdio/of_mdio.c)
- [Kernel referenced bus lookup](https://github.com/torvalds/linux/blob/v6.18/drivers/net/phy/mdio_bus.c)
- [DP mirror switchdev](https://github.com/openwrt/qca-nss-dp/blob/6a5c4716ca258d67202fc7964c9294dfefa3ccfa/nss_dp_switchdev.c)
- [SSDK mirror](https://github.com/openwrt/qca-ssdk/tree/bb4f3f0b947ebfce51c78a8d39f57c7c758521c9)

The SSDK mirror train differs from the pinned vendor source and does not contain
the same I2C helper. Neither whole-tree merging nor deleting that conditional
path is a validated ownership repair. Qualcomm CodeLinaro pins remain unchanged;
no claim of reading inaccessible official content or auditing all upstream code.
