#!/bin/sh
# Host-side mock suite for the NAND/UBI sysupgrade writer transaction
# (package/base-files/files/lib/upgrade/nand.sh).
#
# The suite sources the real nand.sh (with only the host-unavailable
# /lib/functions.sh dependency neutralized) and stubs the UBI sysfs tree, the
# ubi* tools and the volume block devices. It exercises the AX6 install-path
# transaction offline, without root, NAND or a device:
#
#   1. static squashfs layout: capacity preflight, recovery-friendly delete
#      order (rootfs_data -> rootfs -> kernel), mkvol/write/verify success and
#      LEB-rounded data_bytes acceptance;
#   2. ubirmvol failure at each of the three positions: non-zero result and no
#      volume creation afterwards;
#   3. capacity-insufficient abort before the first ubirmvol (zero destructive
#      calls) and fail-open only when the sysfs measurement is unavailable;
#   4. ubiupdatevol rc failure, short data_bytes, dirty upd_marker and missing
#      verification attributes must all fail the writer;
#   5. dynamic UBIFS volume with LEB-rounded data_bytes must pass, while a
#      short static volume must still fail;
#   6. optional CI_UBI_READBACK_HASH=1 evidence mode: matching readback passes,
#      corrupted readback fails;
#   7. failure guidance is printed only after a destructive step started, and
#      "sysupgrade successful" is never printed on a failed write;
#   8. split kernel/rootfs UBI partitions get per-device capacity checks.
#
# Usage: sh tests/test-ax6-nand-writer.sh
set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
NAND_SH="$ROOT/package/base-files/files/lib/upgrade/nand.sh"

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t ax6-nand-writer)
trap 'rm -rf "$TMP"' EXIT INT TERM HUP

PASS=0
FAIL=0
LEB=1024
SYS="$TMP/sys"
DEV="$TMP/dev"
CALL_LOG="$TMP/calls.log"
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

assert_rc_zero() {
	local label="$1"
	if [ "$RC" -eq 0 ]; then
		ok "$label"
	else
		bad "$label (rc=$RC)"
	fi
}

assert_rc_nonzero() {
	local label="$1"
	if [ "$RC" -ne 0 ]; then
		ok "$label"
	else
		bad "$label (expected non-zero rc)"
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

# ---------------------------------------------------------------------------
# Load the real nand.sh. The only adjustment is the host-unavailable
# /lib/functions.sh include; assert it is still exactly one line so a future
# edit cannot silently change what is being tested.
# ---------------------------------------------------------------------------
if [ "$(grep -c '^\. /lib/functions.sh$' "$NAND_SH")" != 1 ]; then
	echo "FAIL: nand.sh no longer sources /lib/functions.sh exactly once"
	exit 1
fi
sed 's|^\. /lib/functions.sh$|: # host mock: /lib/functions.sh is not available|' \
	"$NAND_SH" > "$TMP/nand.sh"
# shellcheck source=/dev/null
. "$TMP/nand.sh"

UBI_SYSFS_ROOT="$SYS"
export UBI_SYSFS_ROOT

# ---------------------------------------------------------------------------
# Mock harness
# ---------------------------------------------------------------------------
volume_name_for() { # <dev> <volume name>
	case "$2" in
	kernel) printf '%s_0' "$1" ;;
	rootfs) printf '%s_1' "$1" ;;
	rootfs_data) printf '%s_2' "$1" ;;
	provisioning) printf '%s_3' "$1" ;;
	esac
}

reset_case() {
	MODE=normal
	CI_UBIPART=rootfs
	CI_KERNPART=kernel
	CI_ROOTPART=rootfs
	CI_UBI_READBACK_HASH=0
	UPGRADE_OPT_ADD_PROVISIONING=0
	NAND_UBI_DESTRUCTIVE_STARTED=0
	CI_KERN_UBIPART=''
	LEB=1024
	CI_ROOT_UBIPART=''
	rm -rf "$SYS" "$DEV"
	mkdir -p "$SYS/class/ubi" "$DEV"
	: > "$CALL_LOG"
	OUT=""
	RC=0
}

add_ubi_device() { # <dev> <avail_eraseblocks>
	mkdir -p "$SYS/class/ubi/$1"
	printf '%s\n' "$2" > "$SYS/class/ubi/$1/avail_eraseblocks"
	printf '%s\n' "$LEB" > "$SYS/class/ubi/$1/eraseblock_size"
}

add_ubi_volume() { # <vol> [reserved_ebs]
	mkdir -p "$SYS/class/ubi/$1"
	printf '%s\n' "${2:-0}" > "$SYS/class/ubi/$1/reserved_ebs"
	printf '0\n' > "$SYS/class/ubi/$1/data_bytes"
	printf '0\n' > "$SYS/class/ubi/$1/upd_marker"
}

setup_default_layout() {
	add_ubi_device ubi0 500
	add_ubi_volume ubi0_0 5
	add_ubi_volume ubi0_1 10
	add_ubi_volume ubi0_2 8
}

write_zeros() { # <file> <bytes>
	if [ $(($2 % 1000)) -eq 0 ]; then
		dd if=/dev/zero of="$1" bs=1000 count=$(($2 / 1000)) 2>/dev/null
	else
		dd if=/dev/zero of="$1" bs=1 count="$2" 2>/dev/null
	fi
}

make_tar() { # <kernel bytes> <root bytes>
	rm -rf "$TMP/tar"
	mkdir -p "$TMP/tar/sysupgrade-redmi_ax6-stock"
	write_zeros "$TMP/tar/sysupgrade-redmi_ax6-stock/kernel" "$1"
	write_zeros "$TMP/tar/sysupgrade-redmi_ax6-stock/root" "$2"
	printf 'BOARD=redmi_ax6-stock\n' > "$TMP/tar/sysupgrade-redmi_ax6-stock/CONTROL"
	tar -C "$TMP/tar" -cf "$TMP/sysupgrade.bin" sysupgrade-redmi_ax6-stock
}

# --- UBI tool stubs ---------------------------------------------------------
nand_attach_ubi() {
	if [ -n "${CI_KERN_UBIPART:-}" ]; then
		case "$1" in
		"$CI_KERN_UBIPART") printf 'ubi0\n' ;;
		*) printf 'ubi1\n' ;;
		esac
	else
		printf 'ubi0\n'
	fi
}

nand_find_ubi() {
	if [ -n "${CI_KERN_UBIPART:-}" ] && [ "$1" = "${CI_ROOT_UBIPART:-}" ]; then
		printf 'ubi1\n'
	else
		printf 'ubi0\n'
	fi
}

nand_find_volume() { # <ubidev> <volume name>
	local idx
	case "$2" in
	kernel) idx=0 ;;
	rootfs) idx=1 ;;
	rootfs_data) idx=2 ;;
	provisioning) idx=3 ;;
	*) return 1 ;;
	esac
	printf '%s_%s\n' "$1" "$idx"
}

nand_remove_ubiblock() {
	:
}

ubirmvol() {
	printf 'ubirmvol %s\n' "$*" >> "$CALL_LOG"
	local dev="${1#/dev/}"
	local name="$3"
	local vol
	vol="$(volume_name_for "$dev" "$name")"
	if [ "${MODE:-normal}" = "ubirmvol-fail-$name" ]; then
		return 1
	fi
	rm -rf "$SYS/class/ubi/$vol"
	return 0
}

ubimkvol() {
	printf 'ubimkvol %s\n' "$*" >> "$CALL_LOG"
	local dev="${1#/dev/}"
	local name=""
	local size=""
	local max=0
	shift
	while [ $# -gt 0 ]; do
		case "$1" in
		-N) name="$2"; shift 2 ;;
		-s) size="$2"; shift 2 ;;
		-m) max=1; shift ;;
		*) shift ;;
		esac
	done
	local vol reserved
	vol="$(volume_name_for "$dev" "$name")"
	rm -rf "$SYS/class/ubi/$vol"
	mkdir -p "$SYS/class/ubi/$vol"
	printf '0\n' > "$SYS/class/ubi/$vol/data_bytes"
	printf '0\n' > "$SYS/class/ubi/$vol/upd_marker"
	if [ "$max" -eq 1 ]; then
		reserved="$(cat "$SYS/class/ubi/$dev/avail_eraseblocks" 2>/dev/null)" || reserved=0
	else
		reserved=$(( (${size:-0} + LEB - 1) / LEB ))
	fi
	printf '%s\n' "$reserved" > "$SYS/class/ubi/$vol/reserved_ebs"
	return 0
}

ubiupdatevol() {
	printf 'ubiupdatevol %s\n' "$*" >> "$CALL_LOG"
	local dev="${1#/dev/}"
	local size=""
	shift
	while [ $# -gt 0 ]; do
		case "$1" in
		-s) size="$2"; shift 2 ;;
		*) shift ;;
		esac
	done
	local target="$DEV/$dev"
	local data_bytes
	case "${MODE:-normal}" in
	update-fail)
		cat > /dev/null
		return 1
		;;
	corrupt-readback)
		cat > /dev/null
		printf 'corrupt-readback\n' > "$target"
		;;
	*)
		cat > "$target"
		;;
	esac
	data_bytes=$(( (${size:-0} + LEB - 1) / LEB * LEB ))
	printf '%s\n' "$data_bytes" > "$SYS/class/ubi/$dev/data_bytes"
	printf '0\n' > "$SYS/class/ubi/$dev/upd_marker"
	case "${MODE:-normal}" in
	update-short)
		printf '%s\n' "$((size - 1))" > "$SYS/class/ubi/$dev/data_bytes"
		;;
	update-marker)
		printf '1\n' > "$SYS/class/ubi/$dev/upd_marker"
		;;
	no-verify-sysfs)
		rm -rf "$SYS/class/ubi/$dev"
		;;
	esac
	return 0
}

# --- generic command stubs --------------------------------------------------
# BSD wc pads the stdin byte count with spaces; the busybox wc used on the
# target does not. Normalize so nand.sh sees device-equivalent numbers.
wc() {
	command wc "$@" | awk '{$1 = $1; print}'
}

find_mtd_index() {
	:
}

fw_printenv() {
	return 1
}

identify_magic_long() {
	printf 'squashfs\n'
}

identify_if_gzip() {
	:
}

identify() {
	printf 'unknown\n'
}

sync() {
	:
}

umount() {
	:
}

reboot() {
	# nand_do_upgrade()/nand_do_upgrade_success() end in "reboot -f" on the
	# target; end the command-substitution subshell instead of falling
	# through to the failed handler.
	exit 0
}

# The writer reads the written bytes back through /dev/<volume> in the
# optional evidence mode; map that path to the mock capture file. Every other
# dd invocation (the upgrade scripts use it for magic probing) stays real.
dd() {
	case "${1:-}" in
	if=/dev/ubi*)
		cat "$DEV/${1#if=/dev/}" 2>/dev/null || :
		return 0
		;;
	esac
	command dd "$@"
}

run_upgrade_tar() {
	OUT="$(nand_upgrade_tar "$TMP/sysupgrade.bin" cat 2>&1)"
	RC=$?
}

run_upgrade_ubifs() {
	OUT="$(nand_upgrade_ubifs "$TMP/root.ubifs" cat 2>&1)"
	RC=$?
}

run_nand_do_upgrade() {
	OUT="$(nand_do_upgrade "$TMP/sysupgrade.bin" cat 2>&1)"
	RC=$?
}

# ===========================================================================
# 1. Static squashfs success: capacity preflight, delete order, LEB rounding
# ===========================================================================
reset_case
setup_default_layout
make_tar 1000 2500
run_upgrade_tar
assert_rc_zero "static writer succeeds"
assert_contains "capacity preflight ran" "UBI capacity preflight: UBI device ubi0 requires 5 UBI PEBs"
assert_file_contains "rootfs volume written" "$CALL_LOG" "ubiupdatevol /dev/ubi0_1 -s 2500 -"
assert_file_contains "kernel volume written" "$CALL_LOG" "ubiupdatevol /dev/ubi0_0 -s 1000 -"
assert_eq "delete order is rootfs_data -> rootfs -> kernel" \
	"rootfs_data rootfs kernel" \
	"$(grep '^ubirmvol ' "$CALL_LOG" | sed 's/.*-N //' | tr '\n' ' ' | sed 's/ $//')"
assert_eq "three volumes created" "3" "$(grep -c '^ubimkvol ' "$CALL_LOG")"
assert_eq "rootfs_data created with -m" "1" \
	"$(grep -c '^ubimkvol /dev/ubi0 -N rootfs_data -m$' "$CALL_LOG")"
assert_not_contains "no verification failure" "verification failed"

# 2 (continued). LEB-rounded static data_bytes (1000 -> 1024, 2500 -> 3072)
assert_eq "static kernel data_bytes is LEB rounded" "1024" "$(cat "$SYS/class/ubi/ubi0_0/data_bytes")"
assert_eq "static rootfs data_bytes is LEB rounded" "3072" "$(cat "$SYS/class/ubi/ubi0_1/data_bytes")"

# ===========================================================================
# 3. ubirmvol failure at each position: fail, stop, never create volumes
# ===========================================================================
test_ubirmvol_failure() {
	local target="$1"
	local expected_deletes="$2"
	reset_case
	setup_default_layout
	make_tar 1000 2500
	MODE="ubirmvol-fail-$target"
	run_upgrade_tar
	assert_rc_nonzero "ubirmvol failure ($target) fails the writer"
	assert_contains "ubirmvol failure ($target) is reported" "cannot remove $target volume"
	assert_eq "ubirmvol failure ($target) does not create volumes" "0" \
		"$(grep -c '^ubimkvol ' "$CALL_LOG")"
	assert_eq "ubirmvol failure ($target) stops deleting" "$expected_deletes" \
		"$(grep -c '^ubirmvol ' "$CALL_LOG")"
}

test_ubirmvol_failure rootfs_data 1
test_ubirmvol_failure rootfs 2
test_ubirmvol_failure kernel 3

# ===========================================================================
# 4. Capacity preflight: insufficient space aborts with zero destructive calls
# ===========================================================================
reset_case
add_ubi_device ubi0 1
add_ubi_volume ubi0_0 1
add_ubi_volume ubi0_1 1
add_ubi_volume ubi0_2 1
make_tar 1000 2500
run_upgrade_tar
assert_rc_nonzero "capacity-insufficient image is rejected"
assert_contains "capacity failure prints the exact requirement" \
	"UBI capacity preflight failed: UBI device ubi0 requires 5 UBI PEBs but only 4 are usable (1 free + 3 reclaimed)"
assert_eq "capacity failure performs zero destructive calls" "0" \
	"$(grep -c '^ubirmvol \|^ubimkvol ' "$CALL_LOG")"

# 5. Capacity preflight fails open when the sysfs measurement is unavailable
reset_case
setup_default_layout
rm -f "$SYS/class/ubi/ubi0/avail_eraseblocks"
make_tar 1000 2500
run_upgrade_tar
assert_rc_zero "capacity preflight fails open without sysfs"
assert_contains "capacity preflight reports the skip" \
	"UBI capacity preflight unavailable (cannot read avail_eraseblocks for ubi0); continuing without preflight"
assert_eq "fail-open still deletes the old volumes" "3" \
	"$(grep -c '^ubirmvol ' "$CALL_LOG")"

# 6. Realistic AX6 geometry: 128 KiB PEBs, volume table 46/404/345
reset_case
LEB=126976
add_ubi_device ubi0 20
add_ubi_volume ubi0_0 46
add_ubi_volume ubi0_1 404
add_ubi_volume ubi0_2 345
make_tar 6000000 55000000
run_upgrade_tar
assert_rc_zero "realistic AX6 image fits and succeeds"
assert_contains "realistic AX6 capacity is computed in PEBs" \
	"UBI capacity preflight: UBI device ubi0 requires 483 UBI PEBs, 815 usable (20 free + 795 reclaimed)"
reset_case

# ===========================================================================
# 7. Write/verification failures
# ===========================================================================
test_write_failure() { # <mode> <expected message>
	reset_case
	setup_default_layout
	make_tar 1000 2500
	MODE="$1"
	run_upgrade_tar
	assert_rc_nonzero "writer failure ($1) is not swallowed"
	assert_contains "writer failure ($1) is reported" "$2"
}

test_write_failure update-fail "failed to write rootfs volume"
test_write_failure update-short "UBI volume ubi0_1 too small: expected >= 2500, got 2499"
test_write_failure update-marker "UBI volume ubi0_1 update marker is not clear: 1"
test_write_failure no-verify-sysfs "UBI verification unavailable for ubi0_1"
assert_not_contains "no success message on failed write" "sysupgrade successful"

# ===========================================================================
# 8. Dynamic UBIFS LEB-rounded acceptance (the landed false-fail regression)
# ===========================================================================
reset_case
setup_default_layout
printf '32768\n' > "$SYS/class/ubi/ubi0_1/data_bytes"
printf '0\n' > "$SYS/class/ubi/ubi0_1/upd_marker"
OUT="$(nand_verify_ubi_volume ubi0_1 20992 2>&1)"
RC=$?
assert_rc_zero "dynamic UBIFS LEB-rounded data_bytes passes (20992 vs 32768)"

reset_case
setup_default_layout
printf '20480\n' > "$SYS/class/ubi/ubi0_1/data_bytes"
printf '0\n' > "$SYS/class/ubi/ubi0_1/upd_marker"
OUT="$(nand_verify_ubi_volume ubi0_1 20992 2>&1)"
RC=$?
assert_rc_nonzero "short data_bytes still fails"
assert_contains "short data_bytes is reported" "too small: expected >= 20992, got 20480"

reset_case
setup_default_layout
printf '32768\n' > "$SYS/class/ubi/ubi0_1/data_bytes"
printf '1\n' > "$SYS/class/ubi/ubi0_1/upd_marker"
OUT="$(nand_verify_ubi_volume ubi0_1 20992 2>&1)"
RC=$?
assert_rc_nonzero "dirty upd_marker still fails"
assert_contains "dirty upd_marker is reported" "update marker is not clear"

reset_case
setup_default_layout
rm -f "$SYS/class/ubi/ubi0_1/upd_marker"
OUT="$(nand_verify_ubi_volume ubi0_1 20992 2>&1)"
RC=$?
assert_rc_nonzero "missing verification attributes fail"
assert_contains "missing verification attributes are reported" "UBI verification unavailable for ubi0_1"

# Full dynamic UBIFS writer path (rootfs volume created with -m)
reset_case
setup_default_layout
write_zeros "$TMP/root.ubifs" 20992
run_upgrade_ubifs
assert_rc_zero "UBIFS writer accepts LEB-rounded volume"
assert_eq "UBIFS writer created only the rootfs volume" "1" \
	"$(grep -c '^ubimkvol ' "$CALL_LOG")"
assert_eq "UBIFS rootfs volume used -m" "1" \
	"$(grep -c '^ubimkvol /dev/ubi0 -N rootfs -m$' "$CALL_LOG")"

# ===========================================================================
# 9. Optional CI_UBI_READBACK_HASH evidence mode
# ===========================================================================
reset_case
setup_default_layout
make_tar 1000 2500
CI_UBI_READBACK_HASH=1
run_upgrade_tar
assert_rc_zero "readback evidence mode succeeds on matching data"
assert_contains "readback verifies the rootfs volume" "UBI readback verified for ubi0_1"
assert_contains "readback verifies the kernel volume" "UBI readback verified for ubi0_0"

reset_case
setup_default_layout
make_tar 1000 2500
CI_UBI_READBACK_HASH=1
MODE=corrupt-readback
run_upgrade_tar
assert_rc_nonzero "readback mismatch fails the writer"
assert_contains "readback mismatch is reported" "UBI readback mismatch for ubi0_1"
assert_not_contains "readback mismatch does not print success" "sysupgrade successful"

# Disabled by default (no readback output)
reset_case
setup_default_layout
make_tar 1000 2500
run_upgrade_tar
assert_not_contains "readback is disabled by default" "UBI readback"

# ===========================================================================
# 10. Failure guidance and success/failure messaging
# ===========================================================================
reset_case
setup_default_layout
make_tar 1000 2500
MODE=update-fail
run_nand_do_upgrade
assert_contains "failed upgrade prints sysupgrade failed" "sysupgrade failed"
assert_contains "failed upgrade points at the U-Boot Web recovery" \
	"recover via the U-Boot Web page (factory.ubi) at 192.168.1.1"
assert_contains "failed upgrade points at UART/TFTP ubiformat" "UART/TFTP ubiformat"
assert_not_contains "failed upgrade never prints sysupgrade successful" "sysupgrade successful"

# Success path: a complete write prints the success message and no guidance.
reset_case
setup_default_layout
make_tar 1000 2500
if [ -f /tmp/sysupgrade.tgz ]; then
	echo "SKIP: /tmp/sysupgrade.tgz exists, not exercising the success reboot path"
else
	run_nand_do_upgrade
	assert_rc_zero "successful upgrade returns zero"
	assert_contains "successful upgrade prints sysupgrade successful" "sysupgrade successful"
	assert_not_contains "successful upgrade prints no failure guidance" "SYSUPGRADE:"
fi

reset_case
add_ubi_device ubi0 1
add_ubi_volume ubi0_0 1
add_ubi_volume ubi0_1 1
add_ubi_volume ubi0_2 1
make_tar 1000 2500
run_nand_do_upgrade
assert_contains "capacity abort still reports sysupgrade failed" "sysupgrade failed"
assert_not_contains "capacity abort (no destructive step) omits corruption guidance" \
	"SYSUPGRADE: the kernel/rootfs volumes are incomplete"
assert_not_contains "capacity abort never prints sysupgrade successful" "sysupgrade successful"

# ===========================================================================
# 11. Split kernel/rootfs UBI partitions: per-device capacity checks
# ===========================================================================
reset_case
CI_KERN_UBIPART=ubi_kernel
CI_ROOT_UBIPART=rootfs
add_ubi_device ubi0 100
add_ubi_volume ubi0_0 1
add_ubi_device ubi1 1
add_ubi_volume ubi1_1 2
add_ubi_volume ubi1_2 1
make_tar 1000 2500
run_upgrade_tar
assert_rc_zero "split-UBI layout fits exactly and succeeds"
assert_contains "split kernel device is checked" \
	"UBI capacity preflight: UBI device ubi0 (kernel) requires 1 UBI PEBs"
assert_contains "split rootfs device is checked with reclaimed LEBs" \
	"UBI capacity preflight: UBI device ubi1 (rootfs/rootfs_data) requires 4 UBI PEBs, 4 usable (1 free + 3 reclaimed)"

reset_case
CI_KERN_UBIPART=ubi_kernel
CI_ROOT_UBIPART=rootfs
add_ubi_device ubi0 100
add_ubi_volume ubi0_0 1
add_ubi_device ubi1 0
add_ubi_volume ubi1_1 2
add_ubi_volume ubi1_2 1
make_tar 1000 2500
run_upgrade_tar
assert_rc_nonzero "split-UBI rootfs device overflow is rejected"
assert_contains "split-UBI overflow prints the rootfs device numbers" \
	"UBI capacity preflight failed: UBI device ubi1 (rootfs/rootfs_data) requires 4 UBI PEBs but only 3 are usable (0 free + 3 reclaimed)"

# ===========================================================================
# Summary
# ===========================================================================
echo "test-ax6-nand-writer: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
