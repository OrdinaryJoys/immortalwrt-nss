#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
PLATFORM="$ROOT/target/linux/qualcommax/ipq807x/base-files/lib/upgrade/platform.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

MTD_ROOTFS=
MTD_ROOTFS1=
BOOT_ROOTFS=0

find_mtd_index() {
	case "$1" in
	rootfs) printf '%s' "$MTD_ROOTFS" ;;
	rootfs_1) printf '%s' "$MTD_ROOTFS1" ;;
	esac
}

fw_printenv() {
	[ "${1:-}" = -n ] && [ "${2:-}" = flag_boot_rootfs ] || return 1
	printf '%s\n' "$BOOT_ROOTFS"
}

identify_if_gzip() {
	:
}

nand_do_platform_check() {
	return 0
}

board_name() {
	printf '%s\n' redmi,ax6-stock
}

# shellcheck source=/dev/null
. "$PLATFORM"

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

assert_eq() {
	[ "$1" = "$2" ] || fail "expected '$2', got '$1'"
}

assert_success() {
	"$@" || fail "command should succeed: $*"
}

assert_failure() {
	if "$@"; then
		fail "command should fail: $*"
	fi
}

make_image() {
	image_dir="$TMP/image"
	rm -rf "$image_dir"
	mkdir -p "$image_dir/sysupgrade-redmi_ax6-stock"
	dd if=/dev/zero of="$image_dir/sysupgrade-redmi_ax6-stock/kernel" bs=1 count=0 seek="$1" 2>/dev/null
	dd if=/dev/zero of="$image_dir/sysupgrade-redmi_ax6-stock/root" bs=1 count=0 seek="$2" 2>/dev/null
	printf 'BOARD=redmi_ax6-stock\n' > "$image_dir/sysupgrade-redmi_ax6-stock/CONTROL"
	tar -C "$image_dir" -cf "$TMP/sysupgrade.bin" sysupgrade-redmi_ax6-stock
}

make_geometry() {
	rootfs_size="$1"
	bad_blocks="${2:-0}"
	rm -rf "$TMP/mtd"
	mkdir -p "$TMP/mtd/mtd0" "$TMP/mtd/mtd1"
	printf '%s\n' 131072 > "$TMP/mtd/mtd0/erasesize"
	printf '%s\n' 2048 > "$TMP/mtd/mtd0/writesize"
	printf '%s\n' "$rootfs_size" > "$TMP/mtd/mtd0/size"
	printf '%s\n' "$bad_blocks" > "$TMP/mtd/mtd0/bad_blocks"
	# Make the mock whole-NAND size 128 MiB for reserve calculation.
	printf '%s\n' $((128 * 1024 * 1024 - rootfs_size)) > "$TMP/mtd/mtd1/size"
	MTD_SYSFS="$TMP/mtd"
	export MTD_SYSFS
}

# Upgrade partition selection.
MTD_ROOTFS=0 MTD_ROOTFS1=
assert_eq "$(xiaomi_stock_get_upgrade_part)" rootfs

MTD_ROOTFS=''
MTD_ROOTFS1=1
assert_eq "$(xiaomi_stock_get_upgrade_part)" rootfs_1

MTD_ROOTFS=0 MTD_ROOTFS1=1 BOOT_ROOTFS=0
assert_eq "$(xiaomi_stock_get_upgrade_part)" rootfs

BOOT_ROOTFS=1
assert_eq "$(xiaomi_stock_get_upgrade_part)" rootfs_1

MTD_ROOTFS=''
MTD_ROOTFS1=''
assert_failure xiaomi_stock_get_upgrade_part

# Capacity checks use the current release-scale kernel/root sizes.
make_image $((6 * 1024 * 1024)) $((54 * 1024 * 1024))
MTD_ROOTFS=0
MTD_ROOTFS1=''
BOOT_ROOTFS=0

make_geometry $((0x06640000)) 1
assert_success xiaomi_stock_check_image_size "$TMP/sysupgrade.bin"
assert_success platform_check_image "$TMP/sysupgrade.bin"

make_geometry $((0x023c0000)) 0
assert_failure xiaomi_stock_check_image_size "$TMP/sysupgrade.bin"
set +e
platform_check_image "$TMP/sysupgrade.bin" >/dev/null 2>&1
platform_rc=$?
set -e
assert_eq "$platform_rc" 74

make_geometry $((0x06640000)) 500
assert_failure xiaomi_stock_check_image_size "$TMP/sysupgrade.bin"

rm -f "$TMP/mtd/mtd0/writesize"
assert_failure xiaomi_stock_check_image_size "$TMP/sysupgrade.bin"

echo "qualcommax-xiaomi-stock-upgrade: PASS"
