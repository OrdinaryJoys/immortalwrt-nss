# Local structural repair qualification

Current local batch: mac80211 release15 / patch948 moves restartable RX
retry timer drain to common CE cleanup before RX buffer cleanup. Extracted
native/PCIC stop/start and core recovery functions pass 1802 host and
ASan/UBSan assertions; r14 fails528 and four mutations are rejected.
Only ahb.c/ce.c prepared bytes change; no posting/callback/data-plane policy
change. Complete replay/regression are recorded separately. Timer/IRQ/DMA
boundaries are modeled, not kernel concurrency. QMI partial-remove and
hybrid wake-CE producer shutdown remain OPEN, as do all prior runtime gates.
NO-BUILD/NO-FLASH; frozen source pin/build lock are not updated or dispatched.

Previous local batch: mac80211 release14, patch947 unifies final release of
AHB remoteproc references and hybrid MSI mappings after core workqueue drain.
884 provider assertions pass; the pre947 source has279 assertion failures,
and seven deliberately broken variants are rejected. API/workqueue effects
are modeled; full package replay and combined regression must be recorded
separately. No target compilation or hardware/performance qualification.
No source pin, build lock, firmware blob or data-plane setting changed.
Registered QMI_FAIL/recovery, coldboot, DP epochs/IRQ-off, durable rpcd and
LuCI/restore integration remain open; this is not complete lifecycle closure.

Next local batch: mac80211 release13, patch946 pairs partial PCIC CE/DP/NAPI
ownership with both PCI and hybrid AHB error callers. PCI clears its existing
affinity hint before release; successful NSS/MSI selection remains unchanged.
The host fixture tests 48 success signatures, every lookup/request/allocation
failure, shared owner/IRQ0, repeated release and post-config MSI-data failure.
Five negative mutations include reversed affinity cleanup. Full package replay
changes pcic.c/pcic.h/pci.c/ahb.c only. No target build or hardware qualification;
DMA/coldboot/full recovery, DP epochs, rpcd durable recover and LuCI stay open.
See `ath11k-pcic-irq/README.md`. Earlier batch results below remain historical.

Next local batch: mac80211 release12, patches943-945 repair native AHB IRQ
setup ownership, configure IRQs before QMI/core startup, and release the MSA
node reference on failure. Host/ASan/UBSan fixture781 checks pass; earlier
775-check negative control has562 assertion failures. Six successful native
IRQ ownership profiles match. Only prepared ahb.c changes; real PCIC MSI,
registered failure/recovery and coldboot error propagation remain open.
See `ath11k-ahb-irq/README.md`. No target, firmware or hardware qualification.

Candidate WIP on source 89bdde5, not a qualified firmware release.

- rpcd018 / release6 separates legacy tmpfs and checked persistent snapshots,
  snapshots every file before commit, propagates failures and retains incomplete
  rollback ownership for retry. Checked remains OFF by default. NO_DATA remains
  the upstream empty-apply result. Checked durable recovery is NOT qualified.
- ath11k939-942 / mac80211 release11 pair QMI init failures, close event admission,
  drain handle users before handle release, reject failed/duplicate FW_READY
  registration, null freed tx_status and share AHB shutdown/remove teardown.
  REGISTERED+QMI_FAIL recovery and concurrent teardown remain open.
- DP011 / release3 adds last-good ndo samples and explicit quality fields,
  corrects confirmed HAL error mappings and XGMAC u64 raw-stat extraction.
  Reset epochs, software-drop aggregation, multi-platform atomic-context
  qualification and IRQ-off performance remain open.

Use actual package-prepared trees. New host fixtures:

- `test-ath11k-qmi-ownership.py`: 28 resource checks; workqueue/lock primitives
  are substitutes, not an actual kernel scheduler or firmware.
- `test-ssdk-mib-read-clear.py`: 2184 checks, 129 failed-read positions, true
  software 3-device/16-slot limits and optional baseline/mutation controls.
- `test-nss-dp-statistics.py`: three actual HAL mappings, last-good, concurrent
  readers with injected errors and ethtool count/strings/payload consistency.
- Existing `nss-dp-containment` 21+5 assertions remain. Its fixture also accepts
  prepared trees without the new statistics cache; no production path is
  replaced by test logic.
- `rpcd-snapshot-isolation/`: guarded real-daemon ucode, not an automated CI VM
  launcher. The independent RAM-only test passed OFF27/ON29; it is not an
  OpenWrt GCC build, actual AX6, durable media or frontend/recover qualification.

The build workflow has local uncommitted test wiring, but the frozen build lock
still selects the old source. Do not dispatch that combination. No source pin,
firmware blob, runtime offload, IRQ/RPS/PBUF or device configuration is changed.
Full report and independent evidence are under Review/structural-repair dated
2026-10-19; their existence is not a zero-fault/performance guarantee.
