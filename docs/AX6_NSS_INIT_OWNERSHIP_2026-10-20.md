# ath11k NSS initialization ownership repair

## Scope

Patch `999-953` / mac80211 r19 fixes the bounded N02 initialization rejection
path and N01 descriptor ownership/metadata cleanup. It inherits r18 and changes
only prepared `ath11k/nss.c`; it does not alter NSS/SSDK/ECM driver pins, firmware,
device trees, radio settings, packet processing or acceleration policy.

It is not a complete NSS lifecycle, firmware shutdown or performance repair.
NO-FLASH and NO-RELEASE remain in force.

## Initialization contract

The pinned `nss_register_wifili_if()` publishes the host object before returning
the context. If the existing subsequent state check rejects initialization, use
the common unregister label, which also releases an external reservation owned
by that initialization. Previously the rejection went straight to memory free.

Preserve the original admission point. The first local draft queried the exported
getter and rejected an unready core before allocating descriptors. A new positive
control demonstrates why that is too eager: NSS can become ready during sleeping
descriptor allocation, after which the original startup would succeed. The
early guard is removed, retained only as a failing mutation; it was never pushed
or deployed. No new provider API reference remains in production code.

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

GCC16 and Clang ASan/UBSan each pass 2689 scenario combinations and 270716
assertions. Many assertions repeatedly inspect 96 metadata slots; these are not
270716 independent faults or hardware tests. Real r18 fails 66898 assertions
(N01 metadata/API boundary 66620, N02 registry 278). Five mutations fail
75/278/75/64822/2568 assertions. Normal host signatures match throughout.

Sixteen existing recovery/QMI/IRQ/provider/CE/PCI/DP/SRNG/core/SSDK/ECM/extractor
groups pass on the final prepared tree. These remain bounded API/host tests.
The proposed getter was checked against the actual accepted r15 NSS module's
AArch64 PREL32 export record, then intentionally not used because preserving
startup semantics matters more than early rejection. r19 target linking and
execution are still untested.

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
