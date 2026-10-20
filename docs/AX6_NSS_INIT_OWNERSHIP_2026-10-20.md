# ath11k NSS initialization ownership repair

## Scope

Patch `999-953` / mac80211 r19 fixes the bounded N02 initialization rejection
path and N01 descriptor ownership/metadata cleanup. It inherits r18 and changes
only prepared `ath11k/nss.c`; it does not alter NSS/SSDK/ECM driver pins, firmware,
device trees, radio settings, packet processing or acceleration policy.

It is not a complete NSS lifecycle, firmware shutdown or performance repair.
NO-FLASH and NO-RELEASE remain in force.

## Initialization contract

The pinned NSS driver exports `nss_wifili_get_context()`. Both that getter and
`nss_register_wifili_if()` resolve the Wi-Fi NSS core through the existing driver
global. The module dependency already requires the NSS provider to be loaded.

Check its initialized state before allocating descriptors or publishing a host
callback. Preserve the existing post-registration check, because state can change
after admission. On that later rejection, use the common unregister label, which
also releases any external-interface reservation owned by this initialization.

No new ownership flag, global lock, callback API or packet-path operation is
introduced. Unsupported hardware and the existing return-code contract remain.
This presumes a fresh initialization after the caller has resolved any previous
NSS ownership. Reentry after an unconfirmed reset is part of unresolved N03/N04,
not made safe by an initialization-state check.

## Descriptor contract

Coherent allocation success is represented by the CPU pointer, not a nonzero
DMA address. Release that owned allocation even when the DMA address is zero,
then clear CPU pointer, DMA handle and size for every slot, including failed or
unused slots whose allocator may have written an error-valued handle.

Linux 6.18.38 already guards NULL CPU pointers in `dma_free_attrs()`. The old
NULL/old-handle boundary observation is therefore not a demonstrated low-level
double-free. This repair closes metadata and conditional address-zero ownership;
it cannot replace the caller's obligation to stop firmware DMA first.

## Verification

Fresh complete mac80211/SSDK/ECM patch preparation uses exact pinned inputs,
zero fuzz. Of 2891 prepared mac80211 files only `ath11k/nss.c` changes relative
to r18; prepared SSDK and ECM are identical.

GCC16 and Clang ASan/UBSan each pass 2614 scenario combinations and 263216
assertions. Many assertions repeatedly inspect 96 metadata slots; these are not
263216 independent faults or hardware tests. Real r18 fails 65365 assertions
(N01 metadata/API boundary 65010, N02 admission/registry 355). Five mutations
fail 77/109/75/61568/2416 assertions. Normal host signatures match throughout.

Sixteen existing recovery/QMI/IRQ/provider/CE/PCI/DP/SRNG/core/SSDK/ECM/extractor
groups pass on the final prepared tree. These remain bounded API/host tests.
The actual accepted r15 NSS module contains an AArch64 PREL32 export record
for the getter, not just an unverified header declaration; r19 target linking
and execution are still untested.

## Open gates

- No post-timeout firmware/DMA quiescence proof, callback draining or generic
  registry lifetime guarantee. N03/N04 remain open and block runtime release.
- Shared completion needs request/type/generation correlation; type alone does
  not reject an old same-type response. A mutex or sync-API replacement does not
  establish that contract.
- Failure propagation must be integrated through core/recovery/remove callers.
  Returning an errno while the parent still frees DP/HAL is not sufficient.
- Do not unconditionally unregister/free on timeout or change IRQ/RPS/PBUF,
  offload, Wi-Fi, subscription, overwrite or Geo update settings.
- Full target compilation, final package/rootfs validation and hardware tests
  require later separate approval. This local repair is not in cloud r15.
