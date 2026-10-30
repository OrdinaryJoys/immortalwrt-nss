# WIFILI Opaque Context Fixture

This is a bounded host contract check, not a kernel/module/firmware build.

The runner creates a new output directory, reads the local CodeLinaro commit
6aa14c78e097b29c493ff2fef87e4d35906b2b5a and the SHA-verified backports archive,
then reconstructs selected files using the current patch series. It separately
prepares the cfde3310d6fe3b007775a91c81e35309a29886a2 baseline from Git data.
No archived generator, test script or pre-existing binary is executed.

The C fixture includes the fresh full nss_def.h, nss_cmn.h and nss_wifili_if.h.
It extracts the exact legacy callback typedefs, registry declaration, core
registration/unregistration/normal/virtual/ext functions, WIFILI APIs and message
handler, ath11k message/ext callback bodies, and actual SoC/radio registration
statements. Their hashes and all input patches are recorded in RESULTS.json.
It compares the compiled public message sizes with the old baseline.

The boundary mocks cover skb flags/linearization/free, netdevice operations,
NSS global hardware tables, logging, completion and MIC/stats/peer callees.
The mock ath11k_base is only a context canary/control-field carrier, not the
real kernel object's layout. NSS interface constants come from fresh pinned
headers. Kernel netdevice/skb layout, allocation/COW, DMA and scheduling are not
emulated. This is not whole-header kernel preprocessing or a target ABI test.

Positive controls include SoC/radio registration, ACK/notify context identity,
mixed opaque/legacy slots, per-owner notify callbacks, both directions of slot
exclusion, direct core registration exclusion, same-ndev legacy updates,
post-registration legacy feature changes, and SG/FRAGLIST combinations with
linearization success/failure. Unregistered/no-callback, unknown ath11k packet
metadata, and opaque normal/virtual paths must consume each skb exactly once.
The fake netdev view of an opaque owner is poisoned so a cast-only change cannot
pass merely because the same allocation happens to be addressable.

Negative controls execute the real old baseline, a cast-only old variant, and
nine source mutations. In particular, the registration-guard mutation removes
the check from register_subsys_dp while leaving set_subsys_dp_type protected.
The fixture must catch the direct opaque-to-legacy overwrite, not merely a
wrapper failure. Mutation compilation failure is not counted as rejection;
each compiled mutant must fail runtime semantic assertions.

Run only against fresh outputs outside the source tree, for example:

    python3 tests/test-ath11k-nss-context.py --nss-source <local-nss-git> --backports-archive <verified-backports.tar.zst> --output-dir <new-audit-directory> --compiler /usr/bin/clang --compiler /opt/homebrew/bin/gcc-16

ASan and UBSan are enabled. LeakSanitizer is disabled because this macOS host
does not support it; skb ownership uses explicit semantic counters instead.

Registration changes require caller serialization. Acquire/release publishes
initialized fields but does not drain callbacks or establish request identity.
Unregister tests keep owners alive and invoke it only after synchronous fixture
callbacks finish. They do not prove safety against an already admitted NAPI
callback, late firmware DMA, old request generations, or concurrent parent free.
Legacy global notification fallback and shutdown/drain/FW stop contracts remain
OPEN. No highest-performance, runtime Wi-Fi or exit-lifetime claim is made.
