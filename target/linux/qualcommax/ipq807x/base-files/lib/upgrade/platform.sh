PART_NAME=firmware
REQUIRE_IMAGE_METADATA=1

RAMFS_COPY_BIN='fw_printenv fw_setenv head seq'
RAMFS_COPY_DATA='/etc/fw_env.config /var/lock/fw_printenv.lock'

remove_oem_ubi_volume() {
	local oem_volume_name="$1"
	local oem_ubivol
	local mtdnum
	local ubidev

	mtdnum=$(find_mtd_index "$CI_UBIPART")
	if [ ! "$mtdnum" ]; then
		return
	fi

	ubidev=$(nand_find_ubi "$CI_UBIPART")
	if [ ! "$ubidev" ]; then
		ubiattach --mtdn="$mtdnum"
		ubidev=$(nand_find_ubi "$CI_UBIPART")
	fi

	if [ "$ubidev" ]; then
		oem_ubivol=$(nand_find_volume "$ubidev" "$oem_volume_name")
		[ "$oem_ubivol" ] && ubirmvol "/dev/$ubidev" --name="$oem_volume_name"
	fi
}

xiaomi_stock_get_upgrade_part() {
	local rootfs_mtdnum
	local rootfs1_mtdnum
	local part_num

	rootfs_mtdnum="$(find_mtd_index rootfs)"
	rootfs1_mtdnum="$(find_mtd_index rootfs_1)"

	if [ -n "$rootfs_mtdnum" ] && [ -z "$rootfs1_mtdnum" ]; then
		echo rootfs
		return 0
	fi

	if [ -z "$rootfs_mtdnum" ] && [ -n "$rootfs1_mtdnum" ]; then
		echo rootfs_1
		return 0
	fi

	if [ -n "$rootfs_mtdnum" ] && [ -n "$rootfs1_mtdnum" ]; then
		part_num="$(fw_printenv -n flag_boot_rootfs 2>/dev/null)"
		[ "$part_num" = "1" ] && echo rootfs_1 || echo rootfs
		return 0
	fi

	echo "unable to find rootfs or rootfs_1 MTD partition" >&2
	return 1
}

xiaomi_stock_check_image_size() {
	local file="$1"
	local cmd
	local board_dir
	local kernel_length
	local rootfs_length
	local upgrade_part
	local mtdnum
	local mtd_sysfs
	local erasesize
	local writesize
	local mtdsize
	local bad_blocks
	local lebsize
	local total_pebs
	local nand_size
	local nand_pebs
	local size_file
	local reserve_pebs
	local available_pebs
	local required_pebs

	cmd="$(identify_if_gzip "$file")cat"
	board_dir="$($cmd < "$file" | tar tf - | grep -m 1 '^sysupgrade-.*/$')"
	board_dir="${board_dir%/}"
	[ -n "$board_dir" ] || {
		echo "stock-layout upgrade requires a sysupgrade tar image"
		return 1
	}

	kernel_length="$($cmd < "$file" | tar xOf - "$board_dir/kernel" | wc -c)"
	rootfs_length="$($cmd < "$file" | tar xOf - "$board_dir/root" | wc -c)"
	[ "$kernel_length" -gt 0 ] && [ "$rootfs_length" -gt 0 ] || {
		echo "sysupgrade image is missing kernel or rootfs"
		return 1
	}

	upgrade_part="$(xiaomi_stock_get_upgrade_part)" || return 1
	mtdnum="$(find_mtd_index "$upgrade_part")"
	mtd_sysfs="${MTD_SYSFS:-/sys/class/mtd}/mtd$mtdnum"

	erasesize="$(cat "$mtd_sysfs/erasesize" 2>/dev/null)"
	writesize="$(cat "$mtd_sysfs/writesize" 2>/dev/null)"
	mtdsize="$(cat "$mtd_sysfs/size" 2>/dev/null)"
	bad_blocks="$(cat "$mtd_sysfs/bad_blocks" 2>/dev/null)"
	bad_blocks="${bad_blocks:-0}"

	[ "${erasesize:-0}" -gt 0 ] &&
		[ "${writesize:-0}" -gt 0 ] &&
		[ "${mtdsize:-0}" -gt 0 ] || {
		echo "unable to read geometry for MTD partition $upgrade_part"
		return 1
	}

	lebsize=$((erasesize - 2 * writesize))
	total_pebs=$((mtdsize / erasesize))
	nand_size=0
	for size_file in "${MTD_SYSFS:-/sys/class/mtd}"/mtd*/size; do
		[ -r "$size_file" ] || continue
		nand_size=$((nand_size + $(cat "$size_file")))
	done
	nand_pebs=$((nand_size / erasesize))
	# Match OpenWrt's whole-NAND bad-block reserve model. Keep at least the
	# 128 MiB NAND allowance even if sysfs exposes only the target partition.
	reserve_pebs=$(((nand_pebs * 20 + 1023) / 1024 + 4))
	[ "$reserve_pebs" -ge 24 ] || reserve_pebs=24
	available_pebs=$((total_pebs - bad_blocks - reserve_pebs - 2))
	required_pebs=$((
		(kernel_length + lebsize - 1) / lebsize +
		(rootfs_length + lebsize - 1) / lebsize +
		1
	))

	if [ "$required_pebs" -gt "$available_pebs" ]; then
		echo "image requires $required_pebs UBI PEBs but $upgrade_part has only $available_pebs usable PEBs"
		return 1
	fi

	return 0
}

platform_check_image() {
	case "$(board_name)" in
	redmi,ax6-stock|\
	xiaomi,ax3600-stock|\
	xiaomi,ax9000-stock)
		nand_do_platform_check "$(board_name)" "$1" || return $?
		xiaomi_stock_check_image_size "$1" || return 74
		;;
	*)
		return 0
		;;
	esac
}

platform_pre_upgrade() {
	case "$(board_name)" in
	asus,rt-ax89x)
		asus_initial_setup
		;;
	redmi,ax6|\
	xiaomi,ax3600|\
	xiaomi,ax9000)
		xiaomi_initramfs_prepare
		;;
	esac
}

platform_do_upgrade() {
	case "$(board_name)" in
	aliyun,ap8220|\
	zte,mf269-stock)
		CI_UBIPART="rootfs"
		nand_do_upgrade "$1"
		;;
	arcadyan,aw1000|\
	cmcc,rm2-6|\
	compex,wpq873|\
	dynalink,dl-wrx36|\
	edimax,cax1800|\
	netgear,rax120v2|\
	netgear,rbr750|\
	netgear,rbs750|\
	netgear,sxr80|\
	netgear,sxs80|\
	netgear,wax218|\
	netgear,wax620|\
	netgear,wax630|\
	zyxel,nwa110ax|\
	zyxel,nwa210ax)
		nand_do_upgrade "$1"
		;;
	asus,rt-ax89x)
		CI_UBIPART="UBI_DEV"
		CI_KERNPART="linux"
		CI_ROOTPART="jffs2"
		nand_do_upgrade "$1"
		;;
	buffalo,wxr-5950ax12)
		CI_KERN_UBIPART="rootfs"
		CI_ROOT_UBIPART="user_property"
		buffalo_upgrade_prepare
		nand_do_flash_file "$1" || nand_do_upgrade_failed
		nand_do_restore_config || nand_do_upgrade_failed
		buffalo_upgrade_optvol
		;;
	edgecore,eap102)
		active="$(fw_printenv -n active)"
		if [ "$active" -eq "1" ]; then
			CI_UBIPART="rootfs2"
		else
			CI_UBIPART="rootfs1"
		fi
		# force altbootcmd which handles partition change in u-boot
		fw_setenv bootcount 3
		fw_setenv upgrade_available 1
		nand_do_upgrade "$1"
		;;
	linksys,homewrk)
		CI_UBIPART="rootfs"
		remove_oem_ubi_volume ubi_rootfs
		nand_do_upgrade "$1"
		;;
	linksys,mx4200v1|\
	linksys,mx4200v2|\
	linksys,mx4300)
		linksys_pre_upgrade "$1"
		remove_oem_ubi_volume squashfs
		nand_do_upgrade "$1"
		;;
	linksys,mx5300|\
	linksys,mx8500)
		linksys_pre_upgrade "$1"
		remove_oem_ubi_volume ubifs
		nand_do_upgrade "$1"
		;;
	prpl,haze|\
	qnap,301w)
		CI_KERNPART="0:HLOS"
		CI_ROOTPART="rootfs"
		emmc_do_upgrade "$1"
		;;
	redmi,ax6|\
	xiaomi,ax3600|\
	xiaomi,ax9000)
		# Make sure that UART is enabled
		fw_setenv boot_wait on
		fw_setenv uart_en 1

		# Enforce single partition.
		fw_setenv flag_boot_rootfs 0
		fw_setenv flag_last_success 0
		fw_setenv flag_boot_success 1
		fw_setenv flag_try_sys1_failed 8
		fw_setenv flag_try_sys2_failed 8

		# Kernel and rootfs are placed in 2 different UBI
		CI_KERN_UBIPART="ubi_kernel"
		CI_ROOT_UBIPART="rootfs"
		nand_do_upgrade "$1"
		;;
	redmi,ax6-stock|\
	xiaomi,ax3600-stock|\
	xiaomi,ax9000-stock)
		CI_UBIPART="$(xiaomi_stock_get_upgrade_part)" ||
			nand_do_upgrade_failed
		if [ "$CI_UBIPART" = "rootfs_1" ]; then
			target_num=1
			try_flag=flag_try_sys2_failed
		else
			target_num=0
			try_flag=flag_try_sys1_failed
		fi

		fw_setenv -s - <<-EOF || nand_do_upgrade_failed
			$try_flag 0
			flag_boot_rootfs $target_num
			flag_last_success $target_num
			flag_boot_success 0
		EOF

		nand_do_upgrade "$1"
		;;
	spectrum,sax1v1k)
		CI_KERNPART="0:HLOS"
		CI_ROOTPART="rootfs"
		CI_DATAPART="rootfs_data"
		emmc_do_upgrade "$1"
		;;
	tcl,linkhub-hh500v)
		tcl_upgrade_prepare
		nand_do_upgrade "$1"
		;;
	tplink,deco-x80-5g|\
	tplink,eap620-hd-v1|\
	tplink,eap660-hd-v1)
		remove_oem_ubi_volume ubi_rootfs
		tplink_do_upgrade "$1"
		;;
	yuncore,ax880)
		active="$(fw_printenv -n active)"
		if [ "$active" -eq "1" ]; then
			CI_UBIPART="rootfs_1"
		else
			CI_UBIPART="rootfs"
		fi
		# force altbootcmd which handles partition change in u-boot
		fw_setenv bootcount 3
		fw_setenv upgrade_available 1
		nand_do_upgrade "$1"
		;;
	zbtlink,zbt-z800ax)
		local mtdnum="$(find_mtd_index 0:bootconfig)"
		local alt_mtdnum="$(find_mtd_index 0:bootconfig1)"
		part_num="$(hexdump -e '1/1 "%01x|"' -n 1 -s 168 -C /dev/mtd$mtdnum | cut -f 1 -d "|" | head -n1)"
		# vendor firmware may swap the rootfs partition location, u-boot append: ubi.mtd=rootfs
		# since we use fixed-partitions, need to force boot from the first rootfs partition
		if [ "$part_num" -eq "1" ]; then
			mtd erase /dev/mtd$mtdnum
			mtd erase /dev/mtd$alt_mtdnum
		fi
		nand_do_upgrade "$1"
		;;
	zte,mf269)
		CI_KERN_UBIPART="ubi_kernel"
		CI_ROOT_UBIPART="rootfs"
		nand_do_upgrade "$1"
		;;
	zyxel,nbg7815)
		local config_mtdnum="$(find_mtd_index 0:bootconfig)"
		[ -z "$config_mtdnum" ] && reboot
		part_num="$(hexdump -e '1/1 "%01x|"' -n 1 -s 168 -C /dev/mtd$config_mtdnum | cut -f 1 -d "|" | head -n1)"
		if [ "$part_num" -eq "0" ]; then
			CI_KERNPART="0:HLOS"
			CI_ROOTPART="rootfs"
		else
			CI_KERNPART="0:HLOS_1"
			CI_ROOTPART="rootfs_1"
		fi
		emmc_do_upgrade "$1"
		;;
	verizon,cr1000a)
		CI_KERNPART="0:HLOS"
		CI_ROOTPART="rootfs"
		rootpart=$(find_mmc_part "$CI_ROOTPART")
		mmcblk_hlos=$(find_mmc_part "$CI_KERNPART" | sed -e "s/^\/dev\///")
		hlos_start=$(cat /sys/class/block/$mmcblk_hlos/start)
		hlos_size=$(cat /sys/class/block/$mmcblk_hlos/size)
		hlos_start_hex=$(printf "%X\n" "$hlos_start")
		hlos_size_hex=$(printf "%X\n" "$hlos_size")
		fw_setenv set_custom_bootargs "setenv bootargs console=ttyMSM0,115200n8 root=$rootpart rootwait fstools_ignore_partname=1"
		fw_setenv read_hlos_emmc "mmc read 44000000 0x$hlos_start_hex 0x$hlos_size_hex"
		fw_setenv setup_and_boot "run set_custom_bootargs;run read_hlos_emmc; bootm 44000000"
		fw_setenv bootcmd "run setup_and_boot"
		emmc_do_upgrade "$1"
		;;
	*)
		default_do_upgrade "$1"
		;;
	esac
}

platform_copy_config() {
	case "$(board_name)" in
	prpl,haze|\
	qnap,301w|\
	spectrum,sax1v1k|\
	zyxel,nbg7815|\
	verizon,cr1000a)
		emmc_copy_config
		;;
	esac
}
