#!/bin/sh

set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PATCH="$ROOT/package/kernel/mac80211/patches/nss/ath11k/999-933-ath11k-nss-configure-wifili-tx-desc-from-dt.patch"
DTS="$ROOT/target/linux/qualcommax/dts/ipq8071-ax6.dts"
MAC80211_MAKEFILE="$ROOT/package/kernel/mac80211/Makefile"

fail()
{
	echo "FAIL: $*" >&2
	exit 1
}

grep -q 'qcom,nss-wifili-tx-desc-count = <16384>;' "$DTS" ||
	fail "AX6 does not request the 16384 descriptor candidate"
grep -q '^PKG_RELEASE:=5$' "$MAC80211_MAKEFILE" ||
	fail "mac80211 package release was not bumped for the NSS patch"
grep -q 'u32 limit = ATH11K_WIFILI_DBDC_NUM_TX_DESC;' "$PATCH" ||
	fail "upstream-compatible 8192 default is not preserved"
grep -q 'limit % 1024' "$PATCH" || fail "descriptor alignment guard missing"
grep -q 'total_desc > ATH11K_WIFILI_MAX_TX_DESC' "$PATCH" ||
	fail "device-wide descriptor limit guard missing"
grep -q 'total_pages >= ATH11K_NSS_MAX_NUMBER_OF_PAGE' "$PATCH" ||
	fail "descriptor page-capacity guard missing"
grep -q 'ab->nss.tx_desc_limit ?:' "$PATCH" ||
	fail "radio buffer limit is not coupled to the allocated pool"

# AX6 has two radios. 16K per radio uses 33 of the 96 host/message pages and
# allocates about 7.5 MiB for normal plus extended descriptors.
python3 - <<'PY'
import math

per_radio = 16384
radios = 2
total = per_radio * radios + radios
pages = math.ceil(total * 80 / (240 * 1024))
pages += math.ceil(total * 160 / (240 * 1024))
memory = total * (80 + 160)
assert per_radio * radios <= 65536
assert pages == 33
assert pages < 96
assert 7.49 < memory / 1024 / 1024 < 7.51
PY

echo "PASS: AX6 NSS WiFi TX descriptor candidate is bounded and internally coupled"
