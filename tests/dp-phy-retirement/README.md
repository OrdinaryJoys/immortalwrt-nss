# DP PHY retirement order

Test only: compile actual complete nss_dp_remove and nss_dp_phy_disconnect,
and the exact Linux6.18.38 phy_disconnect body. Netdevice/PHY layout, RTNL,
notifier delivery, PHY stop/IRQ/detach and hardware are explicit host models.
This is not a target/module build, real callback drain or runtime acceptance.

The source runner freshly replays001-016 with the accepted repository context
helper, clones the actual16-layer tree, then checks/applies017 at its declared
coordinates. Only remove tokens may change; the probe PHY helper stays exact.
IPQ807x must unregister outside RTNL before PHY/VSI/HAL retirement. The old
nonIPQ807x path has identical observable traces before and after. Cases cover
two ports, no PHY/up/down, PHY IRQ/poll, fixed links, repeated remove and
never-registered probe-abort helper calls. The modeled notifier checks the
dependency contract, not any implemented SSDK cache/reader repair.

The current kernel conditional stop, PHY IRQ free, adjust_link clearing and
detach are retained, unlike a blind historical phy_detach substitution.
Old source and directed faulty variants require exact exit86, empty stdout
and the single assigned stderr line. Compile failure, sanitizer diagnostics,
signals and generic nonzero exits are not semantic negative success.

The positive gate compares the complete ordered trace and summary against
an independent per-profile operation matrix, not a PASS suffix or compiler
agreement alone. Four valid and24 rejecting pure-data controls exercise that
gate; they are not additional driver scenarios. The first strengthening run
rejected an incorrectly ordered legacy expected trace; the oracle was corrected
against the actual remove body, without changing production or C fixture code.

Use a new phase3 output directory:

```sh
python3 -B tests/test-dp-phy-retirement.py --upstream-cache /Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-nss-dp --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/DP-PHY-parent-r1
```

GCC ordinary and Clang ASan/UBSan are distinct. LSan is unavailable on this
macOS host and disabled. Sources/patch inventory, saved patches/archive and
prepared trees are rechecked; this is not an atomic workspace lock. True
kernel structs, RCU, ref-wait, PHY state-machine/IRQs, NSS/FW external owners,
non-DP legacy ownership, SSDK retirement and DP init rollback remain open.
