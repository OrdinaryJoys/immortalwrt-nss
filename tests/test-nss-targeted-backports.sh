#!/bin/sh

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
FREQ_PATCH=$REPO_ROOT/package/qca-nss/qca-nss-drv/patches/017-guard-auto-scale-against-uninit-core.patch
ECM_PATCH=$REPO_ROOT/package/qca-nss/qca-nss-ecm/patches/027-fix-multicast-destination-count-signedness.patch

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }

count_fixed() {
  expected=$1
  pattern=$2
  file=$3
  label=$4
  actual=$(grep -c "$pattern" "$file" || true)
  [ "$actual" -eq "$expected" ] && ok "$label" || bad "$label (got $actual, expected $expected)"
}

[ -s "$FREQ_PATCH" ] && ok "frequency guard patch exists" || bad "frequency guard patch exists"
count_fixed 2 '^+.*if (nss_top_main\.nss\[NSS_CORE_0\]\.state !=' "$FREQ_PATCH" \
  "both frequency sysctl handlers check core state"
count_fixed 2 '^+.*frequency request before IPQ' "$FREQ_PATCH" \
  "IPQ60xx and IPQ807x consumers have fallback guards"
grep -q '^+.*NSS_CORE_STATE_INITIALIZED || !npu_reg' "$FREQ_PATCH" \
  && ok "IPQ807x consumer also checks npu_reg" || bad "IPQ807x consumer also checks npu_reg"
grep -q '^+.*kfree((void \*)work);' "$FREQ_PATCH" \
  && ok "rejected work items are freed" || bad "rejected work items are freed"

[ -s "$ECM_PATCH" ] && ok "ECM signed-count patch exists" || bad "ECM signed-count patch exists"
grep -q '5ff84400cfc9de77f45e4b3da581bf803051a466' "$ECM_PATCH" \
  && ok "ECM patch records the official commit" || bad "ECM patch records the official commit"
count_fixed 4 '^+.*int dst_if_cnt;' "$ECM_PATCH" \
  "all four multicast paths use a signed destination count"
count_fixed 4 '^-.*uint32_t dst_if_cnt;' "$ECM_PATCH" \
  "all four unsigned destination counts are removed"

for path in \
  frontends/nss/ecm_nss_multicast_ipv4.c \
  frontends/nss/ecm_nss_multicast_ipv6.c \
  frontends/sfe/ecm_sfe_multicast_ipv4.c \
  frontends/sfe/ecm_sfe_multicast_ipv6.c; do
  grep -q -- "--- a/$path" "$ECM_PATCH" \
    && ok "$path is covered" || bad "$path is covered"
done

echo "=== summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
