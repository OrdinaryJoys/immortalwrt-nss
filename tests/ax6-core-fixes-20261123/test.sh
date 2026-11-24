#!/bin/sh
# Host-side static contract test for the B32 core fixes.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
fail() { echo "FAIL: $*" >&2; exit 1; }

P="$ROOT/target/linux/qualcommax/patches-6.18/0604-1-qca-add-mcs-support.patch"
cb_line=$(grep -n 'ipmr_sync_entry_delete(c->mfc_origin' "$P" | cut -d: -f1 | head -1)
put_line=$(grep -n 'mr_cache_put(&c->_c)' "$P" | cut -d: -f1 | tail -1)
[ -n "$cb_line" ] && [ -n "$put_line" ] || fail "0604 callback/cache put anchors missing"
[ "$cb_line" -lt "$put_line" ] || fail "0604 offload callback still after mr_cache_put"
P="$ROOT/target/linux/qualcommax/patches-6.18/0982-ax6-skb-recycler-corrections.patch"
[ -f "$P" ] || fail "0982 correction patch missing"
grep -Fq -- "$(printf -- '-\tsize = SKB_HEAD_ALIGN(size);')" "$P" || fail "0982 does not remove duplicate align"
grep -Fq -- "$(printf -- '-\t\tdev_kfree_skb(skb);')" "$P" || fail "0982 does not remove double free"
R="$ROOT/target/linux/qualcommax/files/net/core/skbuff_recycle.c"
grep -Fq 'skb_queue_splice_init(skb_list,h);' "$R" || fail "splice_init missing"
grep -Fq 'skb_recycler_max_skbs_core[smp_processor_id()]' "$R" || fail "smp_processor_id missing"
grep -Fq 'spin_lock_irqsave(&glob_recycler.lock, flags);' "$R" || fail "cpu callback lock not irqsave"
grep -Fq 'S_IRUSR | S_IWUSR' "$R" || fail "proc perms not restricted"
grep -Fq 'skb->pp_recycle' "$ROOT/target/linux/qualcommax/files/net/core/skbuff_recycle.h" || fail "pp_recycle guard missing"

P="$ROOT/package/kernel/mac80211/patches/nss/subsys/785-wifi-mac80211-Add-mac-hw-flag-to-avoid-queue-skb.patch"
grep -Fq 'queue = skb_get_queue_mapping(skb);' "$P" || fail "785 queue fallback missing"
grep -Fq 'queue = IEEE80211_AC_BE;' "$P" || fail "785 queue clamp missing"

P="$ROOT/package/kernel/mac80211/patches/nss/ath11k/199-002-ath11k_nss-add-nss-driver-interface.patch"
grep -Fq 'sizeof(struct nss_wifili_radio_cfg_msg)' "$P" || fail "radio_buf_cfg length not fixed"
grep -Fq '+			continue;' "$P" || fail "peer stats return not fixed"

P="$ROOT/package/qca-nss/qca-nss-drv/patches/058-wifili-peer-stats-actual-length.patch"
grep -Fq 'if (skb_shared(nbuf))' "$P" || fail "058 shared check missing"
grep -Fq 'skb_is_nonlinear(nbuf) && skb_linearize(nbuf)' "$P" || fail "058 linearize missing"
grep -Fq 'skb_ensure_writable(nbuf, sizeof(*ncm))' "$P" || fail "058 writable check missing"
grep -Fq 'U16_MAX' "$P" || fail "058 U16_MAX rejection missing"
grep -Fq 'NSS_CMN_RESPONSE_NOTIFY' "$P" || fail "058 notify gate missing"
! grep -Fq 'actual_len = 0xffff;' "$P" || fail "058 unsafe U16 clamp still present"
! grep -Fq 'NSS_WIFILI_EXTERNAL_INTERFACE0' "$P" || fail "058 unsafe external interface gate still present"
shared_line=$(grep -n 'if (skb_shared(nbuf))' "$P" | cut -d: -f1 | head -1)
linear_line=$(grep -n 'skb_is_nonlinear(nbuf) && skb_linearize(nbuf)' "$P" | cut -d: -f1 | head -1)
[ -n "$shared_line" ] && [ -n "$linear_line" ] && [ "$shared_line" -lt "$linear_line" ] || fail "058 shared check must precede linearize"

P="$ROOT/package/kernel/mac80211/patches/nss/ath11k/373-ath11k-Add-retry-mechanism-for-update_rx_qu.patch"
grep -Fq 'rx_tid->active = false;' "$P" || fail "373 ownership invalidation missing"
grep -Fq 'elem_tid = &elem->data;' "$P" || fail "373 elem-owned tid missing"
grep -Fq 'dma_free_noncoherent(ab->dev, rx_tid->unaligned_size' "$P" || fail "373 symmetric DMA free missing"
! grep -Fq 'dma_unmap_single(ab->dev, rx_tid->paddr' "$P" || fail "373 asymmetric DMA unmap still present"

P="$ROOT/target/linux/qualcommax/patches-6.18/0604-1-qca-add-mcs-support.patch"
grep -Fq '__ipmr_get_table' "$P" || fail "0604 RCU table lookup missing"
C="$ROOT/target/linux/qualcommax/config-6.18"
grep -Fxq 'CONFIG_ARM64_ERRATUM_843419=y' "$C" || fail "A53 843419 not enabled"
grep -Fxq 'CONFIG_ARM64_ERRATUM_845719=y' "$C" || fail "A53 845719 not enabled"
E="$ROOT/package/qca-nss/qca-nss-ecm/files/qca-nss-ecm.init"
grep -Fq 'startup: packet steering policy failed' "$E" || fail "ECM steering failure not observable"
grep -Fq 'continuing' "$E" || fail "ECM steering failure still aborts startup"
P="$ROOT/target/linux/qualcommax/base-files/usr/libexec/platform/packet-steering.sh"
grep -Fq '/etc/init.d/set-irq-affinity start_rps' "$P" || fail "start_rps owner missing"
grep -Fq 'packet-steering.uc -l 0 0' "$P" || fail "RPS failure fallback missing"
# fallback may exist, but it must not execute before start_rps
rps_line=$(grep -n 'set-irq-affinity start_rps' "$P" | cut -d: -f1)
gen_line=$(grep -n 'packet-steering.uc -l 0 0' "$P" | cut -d: -f1)
[ "$rps_line" -lt "$gen_line" ] || fail "generic steering runs before start_rps"
P="$ROOT/target/linux/qualcommax/patches-6.18/0982-ax6-skb-recycler-corrections.patch"
[ -f "$P" ] || fail "0982 missing"
grep -Fq -- "$(printf -- '-\tsize = SKB_HEAD_ALIGN(size);')" "$P" || fail "0982 align removal missing"
grep -Fq -- "$(printf -- '-\t\tdev_kfree_skb(skb);')" "$P" || fail "0982 double free removal missing"
echo "PASS ax6-core-fixes-20261123"
