#!/bin/sh
# Host harness for the merged single-partition AX6 branch of the ipq807x
# upgrade platform.sh (S1-02 merged-layout guard + A-00 rc capture).
#
# The merged layout (mtd12 "rootfs" 0x06640000, no rootfs_1) is the layout in
# which the installed U-Boot has no Xiaomi flag/altboot logic. The upgrade
# path must therefore:
#   - take the single-rootfs branch exactly once (one nand_do_upgrade call),
#   - write the bootloader environment zero times (dead flag writes would only
#     invalidate the 0x40000 U-Boot env; S1-02),
#   - propagate the writer result instead of masking it with "return 0"
#     (the replay witness returned 23 and the old code reported 0; A-00).
# Stock dual-slot layouts must keep their flag writes unchanged.
#
# Usage: sh tests/test-ax6-platform-large-partition.sh
set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
PLATFORM_SH="$ROOT/target/linux/qualcommax/ipq807x/base-files/lib/upgrade/platform.sh"

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t ax6-platform-large-partition)
trap 'rm -rf "$TMP"' EXIT INT TERM HUP

OUT_FILE="$TMP/out.log"
NAND_LOG="$TMP/nand.log"
SETENV_LOG="$TMP/setenv.log"
ENV_BATCH="$TMP/env.batch"

PASS=0
FAIL=0
OUT=""
RC=0

ok() {
	PASS=$((PASS + 1))
	echo "PASS: $1"
}

bad() {
	FAIL=$((FAIL + 1))
	echo "FAIL: $1"
}

assert_eq() {
	local label="$1"
	local expected="$2"
	local actual="$3"
	if [ "$expected" = "$actual" ]; then
		ok "$label"
	else
		bad "$label (expected '$expected', got '$actual')"
	fi
}

assert_contains() {
	local label="$1"
	local needle="$2"
	if printf '%s\n' "$OUT" | grep -Fq -- "$needle"; then
		ok "$label"
	else
		bad "$label (output missing '$needle')"
	fi
}

assert_not_contains() {
	local label="$1"
	local needle="$2"
	if printf '%s\n' "$OUT" | grep -Fq -- "$needle"; then
		bad "$label (output unexpectedly contains '$needle')"
	else
		ok "$label"
	fi
}

assert_file_contains() {
	local label="$1"
	local file="$2"
	local needle="$3"
	if [ -f "$file" ] && grep -Fq -- "$needle" "$file"; then
		ok "$label"
	else
		bad "$label (file $file missing '$needle')"
	fi
}

# platform.sh is a plain function library with no /lib include at the top.
# shellcheck source=/dev/null
. "$PLATFORM_SH"

# ---------------------------------------------------------------------------
# Mock environment
# ---------------------------------------------------------------------------
setup_mocks() {
	BOARD=redmi,ax6-stock
	MTD_ROOTFS=12
	MTD_ROOTFS1=
	FLAG_BOOT_ROOTFS=0
	NAND_RC=0
	FWSETENV_RC=0
	NAND_CALLS=0
	FAILED_CALLS=0
	SETENV_CALLS=0
	CI_UBIPART=rootfs
	OUT=""
	RC=0
	: > "$NAND_LOG"
	: > "$SETENV_LOG"
	: > "$ENV_BATCH"
	: > "$OUT_FILE"
}

board_name() {
	printf '%s\n' "$BOARD"
}

find_mtd_index() {
	case "$1" in
	rootfs) printf '%s\n' "${MTD_ROOTFS:-}" ;;
	rootfs_1) printf '%s\n' "${MTD_ROOTFS1:-}" ;;
	esac
}

fw_printenv() {
	if [ "${1:-}" = -n ] && [ "${2:-}" = flag_boot_rootfs ]; then
		printf '%s\n' "$FLAG_BOOT_ROOTFS"
		return 0
	fi
	return 1
}

fw_setenv() {
	SETENV_CALLS=$((SETENV_CALLS + 1))
	printf 'fw_setenv %s\n' "$*" >> "$SETENV_LOG"
	case "${1:-}" in
	-s) cat > "$ENV_BATCH" ;;
	esac
	[ "${FWSETENV_RC:-0}" -eq 0 ] || return "$FWSETENV_RC"
	return 0
}

nand_do_upgrade() {
	NAND_CALLS=$((NAND_CALLS + 1))
	printf '%s\n' "$CI_UBIPART" > "$NAND_LOG"
	return "$NAND_RC"
}

nand_do_upgrade_failed() {
	FAILED_CALLS=$((FAILED_CALLS + 1))
}

nand_do_platform_check() {
	return 0
}

run_platform() {
	: > "$OUT_FILE"
	platform_do_upgrade "$TMP/sysupgrade.bin" > "$OUT_FILE" 2>&1
	RC=$?
	OUT="$(cat "$OUT_FILE")"
}

# ===========================================================================
# 1. Layout probe
# ===========================================================================
setup_mocks
if xiaomi_stock_is_merged_layout; then
	ok "merged layout is detected (rootfs present, rootfs_1 absent)"
else
	bad "merged layout is detected (rootfs present, rootfs_1 absent)"
fi

setup_mocks
MTD_ROOTFS=12
MTD_ROOTFS1=13
if xiaomi_stock_is_merged_layout; then
	bad "dual-slot layout is not reported as merged"
else
	ok "dual-slot layout is not reported as merged"
fi

setup_mocks
MTD_ROOTFS=''
MTD_ROOTFS1=''
if xiaomi_stock_is_merged_layout; then
	bad "layout without rootfs is not reported as merged"
else
	ok "layout without rootfs is not reported as merged"
fi

# ===========================================================================
# 2. Merged layout: exactly one upgrade, zero env writes, branch marker
# ===========================================================================
for board in redmi,ax6-stock xiaomi,ax3600-stock xiaomi,ax9000-stock; do
	setup_mocks
	BOARD="$board"
	run_platform
	assert_eq "merged ${board}: rc" 0 "$RC"
	assert_eq "merged ${board}: exactly one nand_do_upgrade" 1 "$NAND_CALLS"
	assert_eq "merged ${board}: zero fw_setenv writes (S1-02)" 0 "$SETENV_CALLS"
	assert_eq "merged ${board}: upgrade partition is rootfs" "rootfs" "$(cat "$NAND_LOG")"
	assert_contains "merged ${board}: branch marker printed" \
		"AX6-LARGE-PARTITION-BRANCH: upgrading single rootfs"
done

# ===========================================================================
# 3. Merged layout: writer rc is propagated (replay witness 23)
# ===========================================================================
setup_mocks
NAND_RC=23
run_platform
assert_eq "merged layout propagates writer rc 23 (A-00)" 23 "$RC"
assert_eq "merged layout still calls the writer once" 1 "$NAND_CALLS"
assert_contains "merged layout failure guidance is not swallowed" \
	"AX6-LARGE-PARTITION-BRANCH: upgrading single rootfs"

# ===========================================================================
# 4. Stock dual-slot layout: flag writes preserved, slot selection unchanged
# ===========================================================================
setup_mocks
MTD_ROOTFS=12
MTD_ROOTFS1=13
FLAG_BOOT_ROOTFS=0
run_platform
assert_eq "dual-slot rootfs: rc" 0 "$RC"
assert_eq "dual-slot rootfs: one nand_do_upgrade" 1 "$NAND_CALLS"
assert_eq "dual-slot rootfs: one batched fw_setenv" 1 "$SETENV_CALLS"
assert_eq "dual-slot rootfs: upgrade partition is rootfs" "rootfs" "$(cat "$NAND_LOG")"
assert_file_contains "dual-slot rootfs: try flag reset" "$ENV_BATCH" "flag_try_sys1_failed 0"
assert_file_contains "dual-slot rootfs: boot slot flag" "$ENV_BATCH" "flag_boot_rootfs 0"
assert_file_contains "dual-slot rootfs: last success flag" "$ENV_BATCH" "flag_last_success 0"
assert_file_contains "dual-slot rootfs: boot success flag" "$ENV_BATCH" "flag_boot_success 0"

setup_mocks
MTD_ROOTFS=12
MTD_ROOTFS1=13
FLAG_BOOT_ROOTFS=1
run_platform
assert_eq "dual-slot rootfs_1: rc" 0 "$RC"
assert_eq "dual-slot rootfs_1: upgrade partition is rootfs_1" "rootfs_1" "$(cat "$NAND_LOG")"
assert_eq "dual-slot rootfs_1: one batched fw_setenv" 1 "$SETENV_CALLS"
assert_file_contains "dual-slot rootfs_1: try flag reset" "$ENV_BATCH" "flag_try_sys2_failed 0"
assert_file_contains "dual-slot rootfs_1: boot slot flag" "$ENV_BATCH" "flag_boot_rootfs 1"

# ===========================================================================
# 5. Failure paths stop before the writer
# ===========================================================================
setup_mocks
MTD_ROOTFS=12
MTD_ROOTFS1=13
FLAG_BOOT_ROOTFS=0
FWSETENV_RC=1
run_platform
assert_eq "fw_setenv failure: rc" 1 "$RC"
assert_eq "fw_setenv failure: writer not called" 0 "$NAND_CALLS"
assert_eq "fw_setenv failure: upgrade failure handler called" 1 "$FAILED_CALLS"

setup_mocks
MTD_ROOTFS=''
MTD_ROOTFS1=''
run_platform
assert_eq "unknown layout: rc" 1 "$RC"
assert_eq "unknown layout: writer not called" 0 "$NAND_CALLS"
assert_eq "unknown layout: upgrade failure handler called" 1 "$FAILED_CALLS"
assert_eq "unknown layout: no env writes" 0 "$SETENV_CALLS"

# ===========================================================================
# Summary
# ===========================================================================
echo "test-ax6-platform-large-partition: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
