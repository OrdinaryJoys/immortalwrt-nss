# NSS mesh dump ownership repair (954 / mac80211 r20)

This local candidate inherits 953/r19 unchanged. It is not target-compiled,
deployed or released; NSS control lifecycle and real performance remain open.

## Root causes and bounded repair

1. The prepared tree uses ar->nss.dump_lock but never initializes it. Qosmio
   main-nss@92a2d104 has an initialization in pdev_init, introduced in the large
   49126c7c patch. Here it is initialized once in ath11k_mac_allocate, before
   publishing pdev->ar. The REGISTERED recovery no-op must not reset an existing
   lock. The NSS guard matches the guarded struct member. No packet hot path,
   NSS firmware parameter or default feature configuration changes.
2. ath11k_nss_dump_mpath_request moves old entries to a local list and frees
   them, but list_splice_tail leaves the reusable source head pointing at them.
   Replace it with list_splice_tail_init under the existing lock. The source
   is empty before unlock, so a new reply cannot link through the old entries.
   The failure-to-send path needs the same invariant. Proxy dump and vdev free
   already use the initializing form. Qosmio's current 300 mesh patch retains
   the non-initializing request form too; wholesale upstream merging is not a
   repair for this defect.

## Verification and limitations

Five complete prepared functions, exact Linux 6.18.38 list helpers/macros,
accurate NSS dump payload structs, six valid feature shapes, partial allocation,
REGISTERED reuse, repeated dumps and controlled reply interleavings are tested.
GCC16 and Clang ASan/UBSan each pass 120 combinations / 1716 checks. Old code
fails 172 checks; six compiled mutations reject omitted/per-first-radio init,
stale source head, omitted free, post-unlock list reset and recovery lock reset.
See tests/ath11k-mesh-dump-ownership/README.md for contracts and negative-control
safety. Counts are not real device events or performance evidence.

The stock image disables NSS mesh. This is a conditional correctness repair,
not an explanation or fix for current wired/bidirectional throughput. Target
compilation and actual mesh/lockdep remain unverified. No claim is made about
all mesh transaction ordering, reply length validation or callback draining.

## NSS control lifecycle remains a separate joint gate

The pinned nss_wifili_handler uses registry ndev as callback context; clearing
it does not drain a CPU which already fetched the old object. The sync helper
has global completion/callback storage and is not a verified transaction fix.
N03/N04 need instance/request correlation, callback lifetime, actual NSS DMA
quiescence and parent cleanup together. No errno-only, force-free or global
reset is introduced. Generic app_data documentation does not by itself prove
every selected binary firmware command's echo contract.

Sources:
- https://docs.kernel.org/core-api/list.html#splicing-two-lists-together
- https://github.com/qosmio/openwrt-ipq/blob/92a2d104145c8d265851c4b388a41bd8e9c21cd9/package/kernel/mac80211/patches/nss/ath11k/300-ath11k-nss-mesh-offload-support.patch
- https://github.com/qosmio/openwrt-ipq/blob/92a2d104145c8d265851c4b388a41bd8e9c21cd9/package/kernel/mac80211/patches/nss/ath11k/999-900-bss-transition-handling.patch
- https://github.com/gregkh/linux/blob/v6.18.38/include/linux/list.h
