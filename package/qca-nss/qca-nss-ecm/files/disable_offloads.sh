#!/bin/sh
# shellcheck disable=3014,3043,2086,1091,2154
#
# Helper script which uses ethtool to disable (most)
# interface offloads, if possible.
#
# Reference:
# https://forum.openwrt.org/t/how-to-make-ethtool-setting-persistent-on-br-lan/6433/14
#
# Keep the production default while allowing the policy to be exercised by
# the repository fixture without requiring an OpenWrt root filesystem.
# shellcheck source=/lib/functions.sh
. "${OFFLOAD_FUNCTIONS_SH:-/lib/functions.sh}"

log() {
	local status="$1"
	local feature="$2"
	local interface="$3"

	if [ "$status" -eq 0 ]; then
		logger "[ethtool] $feature: disabled on $interface"
	fi

	if [ "$status" -eq 1 ]; then
		logger -s "[ethtool] $feature: failed to disable on $interface"
	fi

	if [ "$status" -gt 1 ]; then
		logger "[ethtool] $feature: no changes performed on $interface"
	fi
}

interface_is_virtual() {
	local interface="$1"
	[ -d /sys/devices/virtual/net/"$interface"/ ] || return 1
	return 0
}

get_base_interface() {
	local interface="$1"
	echo "$interface" | grep -Eo '^[a-z]*[0-9]*' 2> /dev/null || return 1
	return 0
}

disable_offloads() {
	local interface="$1"
	local features
	local cmd

	# Check if we can change features
	if ethtool -k "$interface" 1> /dev/null 2> /dev/null; then

		# Filter whitespaces
		# Get only enabled/not fixed features
		# Filter features that are only changeable by global keyword
		# Filter empty lines
		# Cut to First column
		features=$(ethtool -k "$interface" | awk '{$1=$1;print}' \
			| grep -E '^.+: on$' \
			| grep -v -E '^tx-checksum-.+$' \
			| grep -v -E '^tx-scatter-gather.+$' \
			| grep -v -E '^tx-tcp.+segmentation.+$' \
			| grep -v -E '^tx-udp-fragmentation$' \
			| grep -v -E '^tx-generic-segmentation$' \
			| grep -v -E '^rx-gro$' \
			| grep -v -E '^$' \
			| cut -d: -f1)

		# Replace feature name by global keyword
		features=$(echo "$features" | sed -e s/rx-checksumming/rx/ \
			-e s/tx-checksumming/tx/ \
			-e s/scatter-gather/sg/ \
			-e s/tcp-segmentation-offload/tso/ \
			-e s/udp-fragmentation-offload/ufo/ \
			-e s/generic-segmentation-offload/gso/ \
			-e s/generic-receive-offload/gro/ \
			-e s/large-receive-offload/lro/ \
			-e s/rx-vlan-offload/rxvlan/ \
			-e s/tx-vlan-offload/txvlan/ \
			-e s/ntuple-filters/ntuple/ \
			-e s/receive-hashing/rxhash/)

		# Check if we can disable anything
		if [ -z "$features" ]; then
			logger "[ethtool] Offloads						: no changes performed on $interface"
			return 0
		fi

		# Construct ethtool command line
		cmd="-K $interface"

		for feature in $features; do
			cmd="$cmd $feature off"
		done

		# Try to disable offloads
		ethtool $cmd 1> /dev/null 2> /dev/null
		log $? "Offloads" "$interface"

	else
		log $? "Offloads" "$interface"
	fi
}

disable_feature() {
	local feature="$1"
	local interface="$2"
	local cmd
	local current_state

	current_state=$(ethtool -k "$interface" 2>/dev/null | awk -v feature="^$feature:" '$0 ~ feature {print $2}')

	# Only disable and log if the feature is currently enabled
	if [ "$current_state" = "on" ]; then
		# Construct ethtool command line
		cmd="-K $interface $feature off"

		# Try to disable the feature
		ethtool $cmd 1> /dev/null 2> /dev/null
		log $? "Disabling feature: $feature" "($interface)"
	fi
}

disable_flow_control() {
	local interface="$1"
	local cmd

	# Check if we can change settings
	if ethtool -a "$interface" 1> /dev/null 2> /dev/null; then

		# Construct ethtool command line
		cmd="-A $interface autoneg off tx off rx off"

		# Try to disable flow control
		ethtool $cmd 1> /dev/null 2> /dev/null
		log $? "Flow Control" "$interface"

	else
		log $? "Flow Control" "$interface"
	fi
}

disable_interrupt_moderation() {
	local interface="$1"
	local features
	local cmd

	# Check if we can change settings
	if ethtool -c "$interface" 1> /dev/null 2> /dev/null; then
		# Construct ethtool command line
		cmd="-C $interface adaptive-tx off adaptive-rx off"

		# Try to disable adaptive interrupt moderation
		ethtool $cmd 1> /dev/null 2> /dev/null
		log $? "Adaptive Interrupt Moderation" "$interface"

		features=$(ethtool -c "$interface" | awk '{$1=$1;print}' \
			| grep -v -E '^.+: 0$|Adaptive|Coalesce' \
			| grep -v -E '^$' \
			| cut -d: -f1)

		# Check if we can disable anything
		if [ -z "$features" ]; then
			logger "[ethtool] Interrupt Moderation: no changes performed on $interface"
			return 0
		fi

		# Construct ethtool command line
		cmd="-C $interface"

		for feature in $features; do
			cmd="$cmd $feature 0"
		done

		# Try to disable interrupt Moderation
		ethtool $cmd 1> /dev/null 2> /dev/null
		log $? "Interrupt Moderation" "$interface"

	else
		log $? "Interrupt Moderation" "$interface"
	fi
}

disable_offload() {
	local interface
	local device_path
	local offload_sys_class_net

	config_load ecm

	config_get_bool enable_bridge_filtering			general enable_bridge_filtering 0
	config_get_bool disable_offloads						 general disable_offloads 0
	config_get_bool disable_flow_control				 general disable_flow_control 0
	config_get_bool disable_interrupt_moderation general disable_interrupt_moderation 0
	config_get_bool disable_gro									general disable_gro 0
	config_get_bool disable_gro_list						 general disable_gro_list 1
	config_get offload_host_ifaces              general offload_host_ifaces ""
	config_get offload_physical_policy          general offload_physical_policy "disable"

	offload_sys_class_net="${OFFLOAD_SYS_CLASS_NET:-/sys/class/net}"
	if [ "$#" -eq 0 ]; then
		interface=""
		for device_path in "$offload_sys_class_net"/*/device; do
			[ -e "$device_path" ] || continue
			interface="${interface}${interface:+ }${device_path}"
		done

		# Virtual host-path interfaces do not have a device node and are not
		# included by the physical interface enumeration above. Add each one
		# to the same list so every interface follows exactly one policy pass.
		for h in $offload_host_ifaces; do
			[ -d "$offload_sys_class_net/$h" ] || continue
			[ -e "$offload_sys_class_net/$h/device" ] && continue
			interface="${interface}${interface:+ }${h}"
		done
	else
		interface="$*"
	fi

	for iface in $interface; do
		i=${iface%/*}
		i=${i##*/}

		# Skip Loopback and Bonding Masters
		if [ "$i" = lo ] || [ -f "$iface" ]; then
			continue
		fi

		#
		# Per-interface offload policy (P0-C, AX6 corrective plan 2026-07-26).
		# When offload_host_ifaces is empty (default for non-AX6 platforms),
		# every physical interface gets the full disable treatment.
		# When set (e.g. "br-lan" on AX6 stock), only those get hard-disabled;
		# remaining ports follow offload_physical_policy.
		#
		iface_policy="disable"

		if [ -n "$offload_host_ifaces" ]; then
			is_host=0
			for h in $offload_host_ifaces; do
				[ "$i" = "$h" ] && { is_host=1; break; }
			done

			if [ "$is_host" -eq 0 ]; then
				iface_policy="$offload_physical_policy"
			fi
		fi

		case "$iface_policy" in
			report)
				#
				# Physical port: log current state without changing it.
				# Forwarded traffic on NSS data-plane ports goes through
				# NSS/PPE hardware; blanket-disable may reduce fallback
				# performance without a proven correctness benefit.
				#
				if [ "$disable_offloads" -eq 1 ] && ethtool -k "$i" 1>/dev/null 2>/dev/null; then
					enabled_features=$(ethtool -k "$i" 2>/dev/null | awk '$2 == "on" {printf "%s%s", sep, $1; sep=", "}')
					if [ -n "$enabled_features" ]; then
						logger -t "[offload-report]" \
							"$i: offloads ON ($enabled_features) -- physical NSS data-plane port; per-feature A/B pending"
					else
						logger -t "[offload-report]" \
							"$i: all offloads off"
					fi
				fi
				continue
				;;
			disable)
				;;
			*)
				logger -t "[offload]" "unknown physical policy '$offload_physical_policy' -- defaulting to disable for $i"
				;;
		esac

		if [ "$disable_gro" -eq 1 ]; then
			disable_feature gro "$i"
		fi

		if [ "$disable_gro_list" -eq 1 ]; then
			disable_feature "rx-gro-list" "$i"
		else
			logger -p user.warn -s "[ethtool] Enabling rx-gro-list (GRO Fraglist) will break UDP related traffic. (e.g. DNS, DHCP)"
			logger -p user.warn -s "[ethtool] Leave this feature disabled unless you know what you are doing."
			logger -p user.warn -s "[ethtool] Run \`uci set ecm.general.disable_gro_list=1 && uci commit ecm && service qca-nss-ecm restart\`"
		fi

		if [ "$disable_offloads" -eq 1 ]; then
			disable_offloads "$i"
		fi

		if [ "$disable_flow_control" -eq 1 ]; then
			disable_flow_control "$i"
		fi

		if [ "$disable_interrupt_moderation" -eq 1 ]; then
			disable_interrupt_moderation "$i"
		fi
	done
}
