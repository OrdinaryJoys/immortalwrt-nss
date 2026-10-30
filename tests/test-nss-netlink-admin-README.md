# NSS Netlink Admin Regression

Host-only coverage: 18 new QRFS/GRE-redirect/UDP-ST admin operations,
four existing IPv4/IPv6 admin operations, 15 actual stats no-op handlers,
and 21 unchanged dormant/query operations. All 23 actual tables (58 ops)
are compiled, not replaced by a handwritten op table.

Production changes are limited to 025-netlink-admin-for-all-mutating-ops.patch.
Tests never execute programs from prepared input directories.

## Exact Inputs

test-nss-netlink-admin-ops.json is the independent complete cmd/handler/
policy oracle. Actual order, handler binding, namespace setting, and numeric
command enums from actual headers are checked. Removing exactly 18 flag
additions must restore all 23 netlink C files byte-for-byte to the baseline.

Linux stable v6.18.38 is pinned to e46dc0adfe39724bcf52cea47b8f9c9aed86a394.
Every official input is SHA-256 checked. Raw sources, API provenance and
hashes are saved under core-risk-repairs/nss-netlink-admin-inputs/manifest.json.

The actual genl_ops/genl_split_ops types, flags, NSS command enums, and
complete official functions are extracted without edits: genl_op_from_full,
genl_get_cmd_full, genl_cmd_full_to_split, genl_family_rcv_msg,
__netlink_ns_capable, netlink_ns_capable, netlink_capable.

GENL_ADMIN_PERM checks init_user_ns. GENL_UNS_ADMIN_PERM checks the network
namespace's user namespace. The exact helper checks socket-file capability
unless NETLINK_SKB_DST is set, and always checks sender capability.

## Run

From the source checkout, use a fresh output path for each run:

```sh
python3 -B tests/test-nss-netlink-admin.py \
  /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-repairs/prepared/nss-netlink-admin-v1 \
  --baseline /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-repairs/prepared/baseline/qca-nss-clients \
  --driver /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-repairs/prepared/baseline/qca-nss-drv \
  --kernel-inputs /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-repairs/nss-netlink-admin-inputs/linux-v6.18.38 \
  --output /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-repairs/nss-netlink-admin-example-new \
  --cc clang --sanitize --mutations
```

The test refuses output inside production or input trees and existing
output directories. Compile, link and runtime argv/exit/stdout/stderr are
recorded separately. Compilation failure or sanitizer diagnostics never
count as a successful negative control.

With --mutations: four host compiles/links and 42 runs are expected:
one repaired positive control, one actual baseline, 18 separate new-flag
omissions, four old-flag omissions, 15 erroneous stats restrictions, one
wrong userns flag, one permission-branch bypass and one lost flag transfer.
Every expected-red control must independently fail dispatch expectations.
The repaired run covers 1,856 cases / 4,234 checks across all 58 operations
and eight credential/namespace/destination profiles, plus short-header,
rejected-header and unsupported-dump controls.

## Proof Limits

This runs selected official functions as host C, not the original in-kernel
framework. Family layout, file_ns_capable/ns_capable credentials, attribute/
header parsing and NSS handlers are substitutes. Actual stats no-op bodies
run unchanged; other handlers are inert counters. No real sockets, namespaces,
netdevices, modules, firmware, DMA, target compiler/build or make are used.

Dormant operations are not enabled or declared safe. Runtime registration,
NSS payload parsing and MCS are outside this patch. Host success is not proof
of target ABI, firmware behavior or a device fault cause.
