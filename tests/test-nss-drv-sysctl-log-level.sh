#!/bin/sh

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PATCH=$REPO_ROOT/package/qca-nss/qca-nss-drv/patches/022-lower-sysctl-read-log-level.patch

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

[ -s "$PATCH" ] && ok "sysctl log-level patch exists" || bad "sysctl log-level patch exists"

# 读路径六处降级: Frequency Supported / %d Hz / "\n"(freq 表尾) /
# Current Inst Per Ms / core %d: %d (min-reuse 循环) / "\n"(min-reuse 尾)
count_fixed 6 '^+.*pr_debug(' "$PATCH" \
  "six read-path printk calls demoted to pr_debug"
count_fixed 6 '^-.*printk("\(Frequency Supported\|%d Hz\|Current Inst Per Ms\|core %d: %d\|\\n"\)' "$PATCH" \
  "six read-path unqualified printk calls removed"

# 读路径不得残留无级别 printk
[ "$(grep -c '^+.*printk("\(Frequency Supported\|%d Hz\|Current Inst Per Ms\|core %d: %d\|\\n"\)' "$PATCH" || true)" -eq 0 ] \
  && ok "no unqualified read-path printk remains" || bad "no unqualified read-path printk remains"

# 写路径操作打印必须保留 (Frequency Set / Frequency not found / SPI debug / coredump)
count_fixed 0 '^[+-].*printk("\(Frequency Set to\|Frequency not found\|Enabling NSS SPI\|Coredumping to DDR\)' "$PATCH" \
  "write-path operational printk untouched"

# 读契约 *lenp = 0 不变: 补丁不得修改该行
count_fixed 0 '^[+-].*\*lenp = 0;' "$PATCH" \
  "read *lenp = 0 contract unchanged"

grep -q '^--- a/nss_init.c' "$PATCH" \
  && ok "patch targets nss_init.c" || bad "patch targets nss_init.c"

echo "=== summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
