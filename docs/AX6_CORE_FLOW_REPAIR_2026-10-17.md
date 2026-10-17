# AX6 Core Flow Correctness Candidate

This isolated candidate starts at f58e128163892af4242c724300a00f3fc69a4a88.
It does not change the kernel, backports archive, QSDK train, firmware,
NSS/EDMA containment, IRQ/RPS/PBUF, Wi-Fi country/channel/width, or offload policy.

## Included

- C01: initialize the HTT completion msdu pointer before bitmap lookup.
- C02: clear pending frames' matching vif references in the bitmap pool,
  under the existing tx_idr_lock, instead of walking the unused IDR.
- C04: preserve a fully valid explicit pair of UDP conntrack priorities,
  mapped by sender and conntrack direction. Zero remains valid. TCP,
  partial-flag fallback, acceleration delay and IGS propagation are retained.
- C05/C06: complete jumbo error accumulation and copy the full MIB struct
  from a locked snapshot. Accumulate only successful reads; preserve software
  counters if a hardware flush fails. GMAC swconfig returns errors, prints
  the complete cumulative tail fields, and formats a local FAL snapshot.
  Periodic capture reports failures with rate limiting and advances to the
  next sample rather than spinning/retrying or recording healthy zeroes.

mac80211 release 7 -> 8, ECM release 15 -> 16, SSDK release 1 -> 2. Upstream
source pins remain backports 6.18.26, ECM 8c7355b, and SSDK d9a196497ece.
No struct layout or exported API signature changes are introduced.

## Sources and Deliberate Exclusions

The Wi-Fi TX patches originate from [qosmio PR127](https://github.com/qosmio/openwrt-ipq/pull/127)
(d865d29bbcdd6483ff2213552c3d1f72d7f8b01d); closed is not merged.
The UDP proposal originates from [qosmio/nss-packages PR78](https://github.com/qosmio/nss-packages/pull/78)
(ddcbe809089774f9d1ab9b1fd2582eeb009a510f), adapted and checked against this
project's current 13.1.r2 source plus its existing patch chain, not copied as
an entire package update.

Existing 999-921/922 and 912 are preserved. The external HTT 0x30 proposal
is excluded because 912 already handles that value. SFP/IPQ5018 changes and
the unneeded mesh debugfs change are not AX6 prerequisites.

C03 is NOT included. Testing REGISTERED before draining QMI can race a
pending registration; skipping core_deinit needs a full resource/cancellation
contract, not just the three-state call-count model. In particular QMI
deinit already cancels event_work, but this alone does not prove restart,
reset/dump, wmi_ast, IRQ/CE and notifier lifetimes are all drained.

The combined XGMAC+GMAC getter still requires platform-specific review:
its original return-code overwrite and mixed-counter semantics must not be
mistaken for a validated AX6 copper-port fix. This candidate targets the
confirmed GMAC/cumulative diagnostic defects, not every SSDK API.

## Offline Reproduction

Run `tests/prepare-core-flow-validation.py` with explicit local driver Git
caches, the recipe-hash-matching backports archive and a NEW output directory.
It replays all three complete package patch chains with zero fuzz.

Then run:

```sh
python3 tests/test-ssdk-mib-errors.py PREPARED/qca-ssdk
python3 tests/test-ecm-directional-qos.py --source PREPARED/qca-nss-ecm
python3 tests/test-ath11k-tx-pool-errors.py PREPARED/mac80211 --output NEW_WIFI_EVIDENCE
python3 tests/test-ath11k-recovery-reset-guard.py PREPARED/mac80211
python3 tests/test-ath11k-rx-alignment.py PREPARED/mac80211
```

The tests compile actual prepared structs/functions/source blocks with
modeled hardware, locks, CT, skb and CREATE messages. Negative controls use
the original fully prepared source. They are not full module, kernel ABI,
DMA/concurrency, firmware, air-interface or performance tests.

## Release Gates Still Required

Target SSDK, ECM IGS ON/OFF and ath11k compilation; all existing containment
and VLAN/multicast regressions; complete stock firmware and independent
rootfs/module/manifest/DTB/FIT/UBI/SHA256 acceptance. Other hardware profiles
require their own builds. No EXPAND, main merge, Release or hardware action
is authorized by merely passing these host tests.

After a separately approved hardware window, test router termination,
bridging, routed/NAT/PPPoE and both Wi-Fi directions with same-window
NSS/PBUF/softnet/IRQ, retransmission and latency samples. These fixes do not
establish the root cause of every historical throughput/Web/DNS/ZT symptom.
