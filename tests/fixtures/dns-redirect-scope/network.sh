#!/bin/sh
# Exact logical-network fixtures; never invoke ubus or touch interfaces.
network_flush_cache() { :; }
network_get_device()
{
	# The production network library uses local variables in BusyBox ash.
	# shellcheck disable=SC3043
	local fixture_device
	case "$2" in
		lan) fixture_device="${DNS_SCOPE_TEST_LAN_DEVICE-br-lan}" ;;
		wan) fixture_device="${DNS_SCOPE_TEST_WAN_DEVICE-pppoe-wan}" ;;
		wan6) fixture_device="${DNS_SCOPE_TEST_WAN6_DEVICE-wwan0}" ;;
		Zerotier) fixture_device=ztfixture12345 ;;
		vlan) fixture_device=br-lan.42 ;;
		alias) fixture_device="${DNS_SCOPE_TEST_LAN_DEVICE-br-lan}" ;;
		loopback) fixture_device=lo ;;
		missing) return 1 ;;
		*) return 1 ;;
	esac
	[ -n "$fixture_device" ] || return 1
	export "$1=$fixture_device"
}
