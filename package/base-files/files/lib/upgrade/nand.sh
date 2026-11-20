# Copyright (C) 2014 OpenWrt.org
#

. /lib/functions.sh

# 'kernel' partition or UBI volume on NAND contains the kernel
CI_KERNPART="${CI_KERNPART:-kernel}"

# 'ubi' partition on NAND contains UBI
# There are also CI_KERN_UBIPART and CI_ROOT_UBIPART if kernel
# and rootfs are on separated UBIs.
CI_UBIPART="${CI_UBIPART:-ubi}"

# 'rootfs' UBI volume on NAND contains the rootfs
CI_ROOTPART="${CI_ROOTPART:-rootfs}"

ubi_mknod() {
	local dir="$1"
	local dev="/dev/$(basename $dir)"

	[ -e "$dev" ] && return 0

	local devid="$(cat $dir/dev)"
	local major="${devid%%:*}"
	local minor="${devid##*:}"
	mknod "$dev" c $major $minor
}

nand_find_volume() {
	local ubidevdir ubivoldir
	ubidevdir="/sys/class/ubi/"
	[ ! -d "$ubidevdir" ] && return 1
	for ubivoldir in $ubidevdir/${1}_*; do
		[ ! -d "$ubivoldir" ] && continue
		if [ "$( cat $ubivoldir/name )" = "$2" ]; then
			basename $ubivoldir
			ubi_mknod "$ubivoldir"
			return 0
		fi
	done
}

nand_find_ubi() {
	local ubidevdir ubidev mtdnum cmtdnum
	mtdnum="$( find_mtd_index $1 )"
	[ ! "$mtdnum" ] && return 1
	for ubidevdir in /sys/class/ubi/ubi*; do
		[ ! -e "$ubidevdir/mtd_num" ] && continue
		cmtdnum="$( cat $ubidevdir/mtd_num )"
		if [ "$mtdnum" = "$cmtdnum" ]; then
			ubidev=$( basename $ubidevdir )
			ubi_mknod "$ubidevdir"
			echo $ubidev
			return 0
		fi
	done
}

nand_get_magic_long() {
	($2 < "$1" | dd bs=4 "skip=${3:-0}" count=1 | hexdump -v -n 4 -e '1/1 "%02x"') 2> /dev/null
}

get_magic_long_tar() {
	($2 < "$1" | tar xOf - "$3" | dd bs=4 count=1 | hexdump -v -n 4 -e '1/1 "%02x"') 2> /dev/null
}

identify() {
	identify_magic_long $(nand_get_magic_long "$@")
}

identify_tar() {
	identify_magic_long $(get_magic_long_tar "$@")
}

identify_if_gzip() {
	if [ "$(identify "$1" "cat")" = gzip ]; then echo -n z; fi
}

nand_restore_config() {
	local ubidev=$( nand_find_ubi "${CI_ROOT_UBIPART:-$CI_UBIPART}" )
	local ubivol="$( nand_find_volume $ubidev rootfs_data )"
	if [ ! "$ubivol" ]; then
		ubivol="$( nand_find_volume $ubidev "$CI_ROOTPART" )"
		if [ ! "$ubivol" ]; then
			echo "cannot find ubifs data volume"
			return 1
		fi
	fi
	mkdir /tmp/new_root
	if ! mount -t ubifs /dev/$ubivol /tmp/new_root; then
		echo "cannot mount ubifs volume $ubivol"
		rmdir /tmp/new_root
		return 1
	fi
	if mv "$1" "/tmp/new_root/$BACKUP_FILE"; then
		if umount /tmp/new_root; then
			echo "configuration saved"
			rmdir /tmp/new_root
			return 0
		fi
	else
		umount /tmp/new_root
	fi
	echo "could not save configuration to ubifs volume $ubivol"
	rmdir /tmp/new_root
	return 1
}

nand_remove_ubiblock() {
	local ubivol="$1"

	local ubiblk="ubiblock${ubivol:3}"
	if [ -e "/dev/$ubiblk" ]; then
		umount "/dev/$ubiblk" 2>/dev/null && echo "unmounted /dev/$ubiblk" || :
		if ! ubiblock -r "/dev/$ubivol"; then
			echo "cannot remove $ubiblk"
			return 1
		fi
	fi
}

nand_attach_ubi() {
	local ubipart="$1"
	local has_env="${2:-0}"

	local mtdnum="$( find_mtd_index "$ubipart" )"
	if [ ! "$mtdnum" ]; then
		>&2 echo "cannot find ubi mtd partition $ubipart"
		return 1
	fi

	local ubidev="$( nand_find_ubi "$ubipart" )"
	if [ ! "$ubidev" ]; then
		>&2 ubiattach -m "$mtdnum"
		ubidev="$( nand_find_ubi "$ubipart" )"

		if [ ! "$ubidev" ]; then
			>&2 ubiformat /dev/mtd$mtdnum -y
			>&2 ubiattach -m "$mtdnum"
			ubidev="$( nand_find_ubi "$ubipart" )"

			if [ ! "$ubidev" ]; then
				>&2 echo "cannot attach ubi mtd partition $ubipart"
				return 1
			fi

			if [ "$has_env" -gt 0 ]; then
				>&2 ubimkvol /dev/$ubidev -n 0 -N ubootenv -s 1MiB
				>&2 ubimkvol /dev/$ubidev -n 1 -N ubootenv2 -s 1MiB
			fi
		fi
	fi

	echo "$ubidev"
	return 0
}

nand_detach_ubi() {
	local ubipart="$1"

	local mtdnum="$( find_mtd_index "$ubipart" )"
	if [ ! "$mtdnum" ]; then
		echo "cannot find ubi mtd partition $ubipart"
		return 1
	fi

	local ubidev="$( nand_find_ubi "$ubipart" )"
	if [ "$ubidev" ]; then
		for ubivol in $(find /dev -name "${ubidev}_*" -maxdepth 1 | sort); do
			ubivol="${ubivol:5}"
			nand_remove_ubiblock "$ubivol" || :
			umount "/dev/$ubivol" && echo "unmounted /dev/$ubivol" || :
		done
		if ! ubidetach -m "$mtdnum"; then
			echo "cannot detach ubi mtd partition $ubipart"
			return 1
		fi
	fi
}

nand_verify_ubi_volume() {
	local vol="$1"
	local expected="$2"
	local root="${UBI_SYSFS_ROOT:-/sys}/class/ubi/${vol}"
	local data_bytes="${root}/data_bytes"
	local upd_marker="${root}/upd_marker"
	[ -n "$vol" ] && [ -n "$expected" ] || return 1
	[ -r "$data_bytes" ] && [ -r "$upd_marker" ] || {
		echo "UBI verification unavailable for ${vol}"
		return 1
	}
	# Dynamic UBI volumes report LEB-rounded capacity, not the requested
	# image length. Only require the written data to fit and the update
	# transaction to be complete.
	local actual
	actual="$(cat "$data_bytes")"
	[ "$actual" -ge "$expected" ] || {
		echo "UBI volume ${vol} too small: expected >= ${expected}, got ${actual}"
		return 1
	}
	[ "$(cat "$upd_marker")" = "0" ] || {
		echo "UBI volume ${vol} update marker is not clear: $(cat "$upd_marker")"
		return 1
	}
	return 0
}

# Read a UBI sysfs attribute as a non-negative integer. Returns 1 when the
# attribute cannot be read or is not a plain decimal number.
nand_ubi_sysfs_int() {
	local attr="$1"
	local value

	value="$(cat "${UBI_SYSFS_ROOT:-/sys}/class/ubi/$attr" 2>/dev/null)" || return 1
	case "$value" in
	''|*[!0-9]*)
		return 1
		;;
	esac
	echo "$value"
}

# Number of whole LEBs required to store $1 bytes with a $2-byte LEB.
nand_ubi_leb_count() {
	local length="$1"
	local leb_size="$2"

	case "$length" in
	''|*[!0-9]*) length=0 ;;
	esac
	case "$leb_size" in
	''|*[!0-9]*) leb_size=0 ;;
	esac
	[ "$leb_size" -gt 0 ] || {
		echo 0
		return 0
	}
	echo $(( (length + leb_size - 1) / leb_size ))
}

# The capacity preflight must never block a valid upgrade just because a
# measurement attribute is missing; the post-write verification below stays
# active in that case.
nand_ubi_preflight_skip() {
	echo "UBI capacity preflight unavailable ($1); continuing without preflight"
	return 0
}

# Compare the eraseblocks (UBI LEBs, reported as PEBs by the writer) required
# by the new volumes against the LEBs that are already free plus the LEBs
# reclaimed by deleting the old volumes.
nand_ubi_capacity_assert() {
	local label="$1"
	local required="$2"
	local avail="$3"
	local freed="$4"
	local usable=$((avail + freed))

	if [ "$required" -gt "$usable" ]; then
		echo "UBI capacity preflight failed: ${label} requires ${required} UBI PEBs but only ${usable} are usable (${avail} free + ${freed} reclaimed)"
		return 1
	fi
	echo "UBI capacity preflight: ${label} requires ${required} UBI PEBs, ${usable} usable (${avail} free + ${freed} reclaimed)"
	return 0
}

# Number of LEBs currently reserved by an existing UBI volume.
nand_ubi_volume_ebs() {
	local vol="$1"
	local reserved

	[ -n "$vol" ] || {
		echo 0
		return 0
	}
	reserved="$(nand_ubi_sysfs_int "$vol/reserved_ebs")" || return 1
	echo "$reserved"
}

# Capacity preflight for the UBI write transaction.
#
# nand_upgrade_prepare_ubi removes the existing kernel/rootfs/rootfs_data
# volumes before it creates the new ones. Make sure that the requested image
# fits into the free LEBs plus the LEBs owned by the volumes that are about to
# be removed *before* the first ubirmvol touches the flash. A failed check
# leaves the flash untouched; after the first removal there is no in-device
# rollback on the merged single-UBI layout.
nand_preflight_ubi_capacity() {
	local kern_ubidev="$1"
	local root_ubidev="$2"
	local kernel_length="$3"
	local rootfs_length="$4"
	local rootfs_type="$5"
	local kern_ubivol="$6"
	local root_ubivol="$7"
	local data_ubivol="$8"
	local kern_reserved=0 root_reserved=0 data_reserved=0
	local kern_leb kern_avail root_leb root_avail
	local kern_required root_required data_required provisioning_required=0
	local existing_provisioning=""
	local value

	[ -n "$kernel_length" ] || [ -n "$rootfs_length" ] || return 0

	if [ -n "$kern_ubivol" ]; then
		value="$(nand_ubi_volume_ebs "$kern_ubivol")" || {
			nand_ubi_preflight_skip "cannot read reserved_ebs for ${kern_ubivol}"
			return 0
		}
		kern_reserved="$value"
	fi
	if [ -n "$root_ubivol" ]; then
		value="$(nand_ubi_volume_ebs "$root_ubivol")" || {
			nand_ubi_preflight_skip "cannot read reserved_ebs for ${root_ubivol}"
			return 0
		}
		root_reserved="$value"
	fi
	if [ -n "$data_ubivol" ]; then
		value="$(nand_ubi_volume_ebs "$data_ubivol")" || {
			nand_ubi_preflight_skip "cannot read reserved_ebs for ${data_ubivol}"
			return 0
		}
		data_reserved="$value"
	fi

	kern_leb="$(nand_ubi_sysfs_int "$kern_ubidev/eraseblock_size")" || {
		nand_ubi_preflight_skip "cannot read eraseblock_size for ${kern_ubidev}"
		return 0
	}
	kern_avail="$(nand_ubi_sysfs_int "$kern_ubidev/avail_eraseblocks")" || {
		nand_ubi_preflight_skip "cannot read avail_eraseblocks for ${kern_ubidev}"
		return 0
	}

	# rootfs_data is created with -m (all remaining space), so one LEB is
	# enough for the conservative preflight. A larger rootfs_data_max is
	# handled by prepare's -m fallback when the static request does not fit,
	# so it must not turn into a preflight failure.
	if [ "$rootfs_type" = "ubifs" ]; then
		data_required=0
	else
		data_required=1
	fi
	kern_required="$(nand_ubi_leb_count "$kernel_length" "$kern_leb")"

	if [ "$kern_ubidev" = "$root_ubidev" ]; then
		root_required="$(nand_ubi_leb_count "$rootfs_length" "$kern_leb")"
		if [ "${UPGRADE_OPT_ADD_PROVISIONING:-0}" -gt 0 ]; then
			existing_provisioning="$(nand_find_volume "$root_ubidev" provisioning)"
			[ -n "$existing_provisioning" ] || \
				provisioning_required="$(nand_ubi_leb_count 131072 "$kern_leb")"
		fi
		nand_ubi_capacity_assert "UBI device ${kern_ubidev}" \
			"$((kern_required + root_required + data_required + provisioning_required))" \
			"$kern_avail" "$((kern_reserved + root_reserved + data_reserved))"
		return $?
	fi

	# Kernel and rootfs live on different UBI devices; check each one.
	root_leb="$(nand_ubi_sysfs_int "$root_ubidev/eraseblock_size")" || {
		nand_ubi_preflight_skip "cannot read eraseblock_size for ${root_ubidev}"
		return 0
	}
	root_avail="$(nand_ubi_sysfs_int "$root_ubidev/avail_eraseblocks")" || {
		nand_ubi_preflight_skip "cannot read avail_eraseblocks for ${root_ubidev}"
		return 0
	}
	root_required="$(nand_ubi_leb_count "$rootfs_length" "$root_leb")"
	if [ "${UPGRADE_OPT_ADD_PROVISIONING:-0}" -gt 0 ]; then
		existing_provisioning="$(nand_find_volume "$root_ubidev" provisioning)"
		[ -n "$existing_provisioning" ] || \
			provisioning_required="$(nand_ubi_leb_count 131072 "$root_leb")"
	fi
	nand_ubi_capacity_assert "UBI device ${kern_ubidev} (kernel)" \
		"$kern_required" "$kern_avail" "$kern_reserved" || return 1
	nand_ubi_capacity_assert "UBI device ${root_ubidev} (rootfs/rootfs_data)" \
		"$((root_required + data_required + provisioning_required))" \
		"$root_avail" "$((root_reserved + data_reserved))"
}

# Print the MD5 hash (normalized to the bare hash) of a byte stream read from
# stdin. Only used when CI_UBI_READBACK_HASH=1.
nand_ubi_source_hash() {
	local hash

	hash="$(md5sum 2>/dev/null)" || return 1
	hash="${hash%% *}"
	[ -n "$hash" ] || return 1
	echo "$hash"
}

# Optional evidence-only readback: re-read the written bytes from the UBI
# volume and compare them with the MD5 of the source stream. Default off;
# enable with CI_UBI_READBACK_HASH=1 for RT-3/RT-6 evidence. md5sum, dd and
# head are installed into the ramfs by the stage2 default binary list.
nand_verify_ubi_readback() {
	local vol="$1"
	local expected="$2"
	local source_hash="$3"
	local readback_hash

	[ "${CI_UBI_READBACK_HASH:-0}" = "1" ] || return 0
	if [ -z "$vol" ] || [ -z "$expected" ] || [ -z "$source_hash" ]; then
		echo "UBI readback verification failed for ${vol}: missing volume, length or source hash"
		return 1
	fi
	readback_hash="$( dd if="/dev/$vol" bs=65536 2>/dev/null | head -c "$expected" | md5sum 2>/dev/null )"
	readback_hash="${readback_hash%% *}"
	if [ -z "$readback_hash" ]; then
		echo "UBI readback verification failed for ${vol}: cannot hash the volume"
		return 1
	fi
	if [ "$readback_hash" != "$source_hash" ]; then
		echo "UBI readback mismatch for ${vol}: source ${source_hash}, volume ${readback_hash}"
		echo "UBI readback verification failed for ${vol}"
		return 1
	fi
	echo "UBI readback verified for ${vol}: ${readback_hash}"
	return 0
}

nand_upgrade_prepare_ubi() {
	local rootfs_length="$1"
	local rootfs_type="$2"
	local rootfs_data_max="$(fw_printenv -n rootfs_data_max 2> /dev/null)"
	[ -n "$rootfs_data_max" ] && rootfs_data_max=$((rootfs_data_max))

	local kernel_length="$3"
	local has_env="${4:-0}"
	local kern_ubidev
	local root_ubidev

	[ -n "$rootfs_length" -o -n "$kernel_length" ] || return 1

	if [ -n "$CI_KERN_UBIPART" -a -n "$CI_ROOT_UBIPART" ]; then
		kern_ubidev="$( nand_attach_ubi "$CI_KERN_UBIPART" "$has_env" )"
		[ -n "$kern_ubidev" ] || return 1
		root_ubidev="$( nand_attach_ubi "$CI_ROOT_UBIPART" )"
		[ -n "$root_ubidev" ] || return 1
	else
		kern_ubidev="$( nand_attach_ubi "$CI_UBIPART" "$has_env" )"
		[ -n "$kern_ubidev" ] || return 1
		root_ubidev="$kern_ubidev"
	fi

	local kern_ubivol="$( nand_find_volume $kern_ubidev "$CI_KERNPART" )"
	local root_ubivol="$( nand_find_volume $root_ubidev "$CI_ROOTPART" )"
	local data_ubivol="$( nand_find_volume $root_ubidev rootfs_data )"
	[ "$root_ubivol" = "$kern_ubivol" ] && root_ubivol=

	# Refuse an image that cannot fit before deleting anything. This must run
	# before the first ubirmvol: once a volume is removed the previous
	# kernel/rootfs are gone and there is no in-device rollback.
	nand_preflight_ubi_capacity "$kern_ubidev" "$root_ubidev" \
		"$kernel_length" "$rootfs_length" "$rootfs_type" \
		"$kern_ubivol" "$root_ubivol" "$data_ubivol" || return 1

	# remove ubiblocks
	[ "$kern_ubivol" ] && { nand_remove_ubiblock $kern_ubivol || return 1; }
	[ "$root_ubivol" ] && { nand_remove_ubiblock $root_ubivol || return 1; }
	[ "$data_ubivol" ] && { nand_remove_ubiblock $data_ubivol || return 1; }

	# Delete in recovery-friendly order: rootfs_data first, then rootfs, and
	# the kernel last. A true atomic swap is impossible on the merged AX6
	# layout (2 * kernel 46 LEBs + 2 * rootfs 403 LEBs > 818 PEB); keeping the
	# kernel until the end minimizes the window in which the device has no
	# bootable kernel. A failed removal must stop the upgrade before
	# mkvol/write.
	NAND_UBI_DESTRUCTIVE_STARTED=1
	if [ "$data_ubivol" ] && ! ubirmvol /dev/$root_ubidev -N rootfs_data; then
		echo "cannot remove rootfs_data volume"
		return 1
	fi
	if [ "$root_ubivol" ] && ! ubirmvol /dev/$root_ubidev -N "$CI_ROOTPART"; then
		echo "cannot remove rootfs volume $CI_ROOTPART"
		return 1
	fi
	if [ "$kern_ubivol" ] && ! ubirmvol /dev/$kern_ubidev -N "$CI_KERNPART"; then
		echo "cannot remove kernel volume $CI_KERNPART"
		return 1
	fi

	# create provisioning vol
	if [ "${UPGRADE_OPT_ADD_PROVISIONING:-0}" -gt 0 ]; then
		[ -n "$(nand_find_volume $root_ubidev provisioning)" ] || {
			if ! ubimkvol /dev/$root_ubidev -N provisioning -s 131072; then
				echo "cannot create provisioning volume"
				return 1
			fi
		}
	fi

	# create kernel vol
	if [ -n "$kernel_length" ]; then
		if ! ubimkvol /dev/$kern_ubidev -N "$CI_KERNPART" -s $kernel_length; then
			echo "cannot create kernel volume"
			return 1;
		fi
	fi

	# create rootfs vol
	if [ -n "$rootfs_length" ]; then
		local rootfs_size_param
		if [ "$rootfs_type" = "ubifs" ]; then
			rootfs_size_param="-m"
		else
			rootfs_size_param="-s $rootfs_length"
		fi
		if ! ubimkvol /dev/$root_ubidev -N "$CI_ROOTPART" $rootfs_size_param; then
			echo "cannot create rootfs volume"
			return 1;
		fi
	fi

	# create rootfs_data vol for non-ubifs rootfs
	if [ "$rootfs_type" != "ubifs" ]; then
		local rootfs_data_size_param="-m"
		if [ -n "$rootfs_data_max" ]; then
			rootfs_data_size_param="-s $rootfs_data_max"
		fi
		if ! ubimkvol /dev/$root_ubidev -N rootfs_data $rootfs_data_size_param; then
			if ! ubimkvol /dev/$root_ubidev -N rootfs_data -m; then
				echo "cannot initialize rootfs_data volume"
				return 1
			fi
		fi
	fi

	return 0
}

# Write the UBI image to MTD ubi partition
nand_upgrade_ubinized() {
	local ubi_file="$1"
	local cmd="$2"

	local ubi_length=$( ($cmd < "$ubi_file" | wc -c) 2> /dev/null)

	nand_detach_ubi "$CI_UBIPART" || return 1

	local mtdnum="$( find_mtd_index "$CI_UBIPART" )"
	$cmd < "$ubi_file" | ubiformat "/dev/mtd$mtdnum" -S "$ubi_length" -y -f - && ubiattach -m "$mtdnum"
}

# Write the UBIFS image to UBI rootfs volume
nand_upgrade_ubifs() {
	local ubifs_file="$1"
	local cmd="$2"
	local ubifs_hash=""

	local ubifs_length=$( ($cmd < "$ubifs_file" | wc -c) 2> /dev/null)

	nand_upgrade_prepare_ubi "$ubifs_length" "ubifs" "" "" || return 1

	local ubidev="$( nand_find_ubi "$CI_UBIPART" )"
	local root_ubivol="$(nand_find_volume $ubidev "$CI_ROOTPART")"
	if [ "${CI_UBI_READBACK_HASH:-0}" = "1" ]; then
		ubifs_hash="$( $cmd < "$ubifs_file" | nand_ubi_source_hash )"
	fi
	if ! $cmd < "$ubifs_file" | ubiupdatevol /dev/$root_ubivol -s "$ubifs_length" -; then
		echo "failed to write UBIFS rootfs volume"
		return 1
	fi
	if ! nand_verify_ubi_volume "$root_ubivol" "$ubifs_length"; then
		echo "UBIFS rootfs volume verification failed"
		return 1
	fi
	nand_verify_ubi_readback "$root_ubivol" "$ubifs_length" "$ubifs_hash"
}

# Write the FIT image to UBI kernel volume
nand_upgrade_fit() {
	local fit_file="$1"
	local cmd="$2"
	local fit_hash=""

	local fit_length=$( ($cmd < "$fit_file" | wc -c) 2> /dev/null)

	nand_upgrade_prepare_ubi "" "" "$fit_length" "1" || return 1

	local fit_ubidev="$(nand_find_ubi "$CI_UBIPART")"
	local fit_ubivol="$(nand_find_volume $fit_ubidev "$CI_KERNPART")"
	if [ "${CI_UBI_READBACK_HASH:-0}" = "1" ]; then
		fit_hash="$( $cmd < "$fit_file" | nand_ubi_source_hash )"
	fi
	if ! $cmd < "$fit_file" | ubiupdatevol /dev/$fit_ubivol -s "$fit_length" -; then
		echo "failed to write FIT kernel volume"
		return 1
	fi
	if ! nand_verify_ubi_volume "$fit_ubivol" "$fit_length"; then
		echo "FIT kernel volume verification failed"
		return 1
	fi
	nand_verify_ubi_readback "$fit_ubivol" "$fit_length" "$fit_hash"
}

# Write images in the TAR file to MTD partitions and/or UBI volumes as required
nand_upgrade_tar() {
	local tar_file="$1"
	local cmd="${2:-cat}"
	local jffs2_markers="${CI_JFFS2_CLEAN_MARKERS:-0}"

	# WARNING: This fails if tar contains more than one 'sysupgrade-*' directory.
	local board_dir="$($cmd < "$tar_file" | tar tf - | grep -m 1 '^sysupgrade-.*/$')"
	board_dir="${board_dir%/}"

	local kernel_mtd kernel_length
	if [ "$CI_KERNPART" != "none" ]; then
		kernel_mtd="$(find_mtd_index "$CI_KERNPART")"
		kernel_length=$( ($cmd < "$tar_file" | tar xOf - "$board_dir/kernel" | wc -c) 2> /dev/null)
		[ "$kernel_length" = 0 ] && kernel_length=
	fi
	local rootfs_length=$( ($cmd < "$tar_file" | tar xOf - "$board_dir/root" | wc -c) 2> /dev/null)
	[ "$rootfs_length" = 0 ] && rootfs_length=
	local rootfs_type
	[ "$rootfs_length" ] && rootfs_type="$(identify_tar "$tar_file" "$cmd" "$board_dir/root")"

	local ubi_kernel_length
	if [ "$kernel_length" ]; then
		if [ "$kernel_mtd" ]; then
			# On some devices, the raw kernel and ubi partitions overlap.
			# These devices brick if the kernel partition is erased.
			# Hence only invalidate kernel for now.
			dd if=/dev/zero bs=4096 count=1 2> /dev/null | \
				mtd write - "$CI_KERNPART"
		else
			ubi_kernel_length="$kernel_length"
		fi
	fi

	local has_env=0
	nand_upgrade_prepare_ubi "$rootfs_length" "$rootfs_type" "$ubi_kernel_length" "$has_env" || return 1

	local rootfs_hash="" kern_hash=""
	if [ "${CI_UBI_READBACK_HASH:-0}" = "1" ]; then
		if [ -n "$rootfs_length" ]; then
			rootfs_hash="$( $cmd < "$tar_file" | tar xOf - "$board_dir/root" | nand_ubi_source_hash )"
		fi
		if [ -n "$kernel_length" ] && [ -z "$kernel_mtd" ]; then
			kern_hash="$( $cmd < "$tar_file" | tar xOf - "$board_dir/kernel" | nand_ubi_source_hash )"
		fi
	fi

	if [ "$rootfs_length" ]; then
		local ubidev="$( nand_find_ubi "${CI_ROOT_UBIPART:-$CI_UBIPART}" )"
		local root_ubivol="$( nand_find_volume $ubidev "$CI_ROOTPART" )"
		if ! $cmd < "$tar_file" | tar xOf - "$board_dir/root" | \
			ubiupdatevol /dev/$root_ubivol -s "$rootfs_length" -; then
			echo "failed to write rootfs volume"
			return 1
		fi
		if ! nand_verify_ubi_volume "$root_ubivol" "$rootfs_length"; then
			echo "rootfs volume verification failed"
			return 1
		fi
		nand_verify_ubi_readback "$root_ubivol" "$rootfs_length" "$rootfs_hash" || return 1
	fi
	if [ "$kernel_length" ]; then
		if [ "$kernel_mtd" ]; then
			if [ "$jffs2_markers" = 1 ]; then
				flash_erase -j "/dev/mtd${kernel_mtd}" 0 0
				$cmd < "$tar_file" | tar xOf - "$board_dir/kernel" | \
					nandwrite "/dev/mtd${kernel_mtd}" -
			else
				$cmd < "$tar_file" | tar xOf - "$board_dir/kernel" | \
					mtd write - "$CI_KERNPART"
			fi
		else
			local ubidev="$( nand_find_ubi "${CI_KERN_UBIPART:-$CI_UBIPART}" )"
			local kern_ubivol="$( nand_find_volume $ubidev "$CI_KERNPART" )"
			if ! $cmd < "$tar_file" | tar xOf - "$board_dir/kernel" | \
				ubiupdatevol /dev/$kern_ubivol -s "$kernel_length" -; then
				echo "failed to write kernel volume"
				return 1
			fi
			if ! nand_verify_ubi_volume "$kern_ubivol" "$kernel_length"; then
				echo "kernel volume verification failed"
				return 1
			fi
			nand_verify_ubi_readback "$kern_ubivol" "$kernel_length" "$kern_hash" || return 1
		fi
	fi

	return 0
}

nand_verify_if_gzip_file() {
	local file="$1"
	local cmd="$2"

	if [ "$cmd" = zcat ]; then
		echo "verifying compressed sysupgrade file integrity"
		if ! gzip -t "$file"; then
			echo "corrupted compressed sysupgrade file"
			return 1
		fi
	fi
}

nand_verify_tar_file() {
	local file="$1"
	local cmd="$2"

	echo "verifying sysupgrade tar file integrity"
	if ! $cmd < "$file" | tar xOf - > /dev/null; then
		echo "corrupted sysupgrade tar file"
		return 1
	fi
}

nand_do_flash_file() {
	local file="$1"
	local cmd="$2"
	local file_type

	[ -z "$cmd" ] && cmd="$(identify_if_gzip "$file")cat"
	file_type="$(identify "$file" "$cmd" "")"

	[ ! "$(find_mtd_index "$CI_UBIPART")" ] && CI_UBIPART=rootfs

	case "$file_type" in
		"fit")
			nand_verify_if_gzip_file "$file" "$cmd" || return 1
			nand_upgrade_fit "$file" "$cmd"
			;;
		"ubi")
			nand_verify_if_gzip_file "$file" "$cmd" || return 1
			nand_upgrade_ubinized "$file" "$cmd"
			;;
		"ubifs")
			nand_verify_if_gzip_file "$file" "$cmd" || return 1
			nand_upgrade_ubifs "$file" "$cmd"
			;;
		*)
			nand_verify_tar_file "$file" "$cmd" || return 1
			nand_upgrade_tar "$file" "$cmd"
			;;
	esac
}

nand_do_restore_config() {
	local conf_tar="/tmp/sysupgrade.tgz"
	[ ! -f "$conf_tar" ] || nand_restore_config "$conf_tar"
}

# Recognize type of passed file and start the upgrade process
#
# Supported firmware containers:
# 1. Raw file
# 2. Gzip
# 3. Custom (requires passing extracting command)
#
# Supported data formats:
# 1. Tar with kernel/rootfs
# 2. UBI image (built using "ubinized")
# 3. UBIFS image (to update UBI volume with)
# 4. FIT image (to update UBI volume with)
#
# $(1): firmware file path
# $(2): (optional) pipe command to extract firmware
nand_do_upgrade() {
	local file="$1"
	local cmd="$2"

	sync
	nand_do_flash_file "$file" "$cmd" && nand_do_upgrade_success
	nand_do_upgrade_failed
}

nand_do_upgrade_success() {
	if nand_do_restore_config && sync; then
		echo "sysupgrade successful"
		umount -a
		reboot -f
	fi
	nand_do_upgrade_failed
}

# Print the recovery instructions for a failure that happened after the UBI
# transaction started. There is no in-device failover on the merged AX6
# layout, so the serial console message is the only recovery pointer.
nand_upgrade_failure_guidance() {
	cat <<-EOF
	SYSUPGRADE: the kernel/rootfs volumes are incomplete; the device may not boot.
	SYSUPGRADE: recover via the U-Boot Web page (factory.ubi) at 192.168.1.1 or UART/TFTP ubiformat.
	SYSUPGRADE: keep this console attached and do not power off until recovery has started.
	EOF
}

nand_do_upgrade_failed() {
	sync
	echo "sysupgrade failed"
	# Only print the corruption/recovery guidance once a destructive step was
	# attempted; a preflight failure leaves the installed system bootable.
	[ "${NAND_UBI_DESTRUCTIVE_STARTED:-0}" -gt 0 ] && nand_upgrade_failure_guidance
	# Should we reboot or bring up some failsafe mode instead?
	umount -a
	reboot -f
}

# Check if passed file is a valid one for NAND sysupgrade.
# Currently it accepts 4 types of files:
# 1) UBI: a ubinized image containing required UBI volumes.
# 2) UBIFS: a UBIFS rootfs volume image.
# 3) FIT: a FIT image containing kernel and rootfs.
# 4) TAR: an archive that includes directory "sysupgrade-${BOARD_NAME}" containing
#         a non-empty "CONTROL" file and required partition and/or volume images.
#
# You usually want to call this function in platform_check_image.
#
# $(1): board name, used in case of passing TAR file
# $(2): file to be checked
nand_do_platform_check() {
	local board_name="$1"
	local file="$2"

	local cmd="$(identify_if_gzip "$file")cat"
	local file_type="$(identify "$file" "$cmd" "")"
	local control_length=$( ($cmd < "$file" | tar xOf - "sysupgrade-${board_name//,/_}/CONTROL" | wc -c) 2> /dev/null)

	if [ "$control_length" = 0 ]; then
		control_length=$( ($cmd < "$file" | tar xOf - "sysupgrade-${board_name//_/,}/CONTROL" | wc -c) 2> /dev/null)
	fi

	if [ "$control_length" != 0 ]; then
		nand_verify_tar_file "$file" "$cmd" || return 1
	else
		nand_verify_if_gzip_file "$file" "$cmd" || return 1
		if [ "$file_type" != "fit" -a "$file_type" != "ubi" -a "$file_type" != "ubifs" ]; then
			echo "invalid sysupgrade file"
			return 1
		fi
	fi

	return 0
}
