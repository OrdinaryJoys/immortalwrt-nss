#!/bin/sh
# Print one complete nft expression for DNS prerouting redirect producers.
# network.globals.dns_redirect_networks is an explicit logical-network allowlist.
# An absent option defaults to lan. Use the nonempty sentinel "none" to disable.
# UCI set option='' deletes the option and therefore restores the lan default;
# it does NOT disable redirect. A successfully read empty value is rejected
# defensively (e.g. an empty list item). "none" mixed with networks is rejected.
# Additional trusted networks (including ZeroTier) must be explicitly named.
# This does not modify nftables, UCI, interfaces or services.

set -f
LC_ALL=C
export LC_ALL

DNS_REDIRECT_UCI="${DNS_REDIRECT_UCI:-/sbin/uci}"
DNS_REDIRECT_LOGGER="${DNS_REDIRECT_LOGGER:-/usr/bin/logger}"
DNS_REDIRECT_NETWORK_LIB="${DNS_REDIRECT_NETWORK_LIB:-/lib/functions/network.sh}"

scope_log()
{
	"$DNS_REDIRECT_LOGGER" -t dns-redirect-scope -p daemon.warn -- "$1" 2>/dev/null || :
}

valid_network()
{
	case "$1" in
		''|*[!a-zA-Z0-9_-]*|[!a-zA-Z0-9_]*) return 1 ;;
	esac
}

valid_device()
{
	# IFNAMSIZ is 16 including NUL. Reject nft wildcards/quoting/metacharacters.
	[ "${#1}" -le 15 ] || return 1
	case "$1" in
		''|*[!a-zA-Z0-9_.:-]*|[!a-zA-Z0-9_]*) return 1 ;;
	esac
}

if ! "$DNS_REDIRECT_UCI" -q export network >/dev/null 2>&1; then
	scope_log "DNS redirect disabled: network configuration unavailable"
	exit 1
fi
if networks="$("$DNS_REDIRECT_UCI" -q get network.globals.dns_redirect_networks 2>/dev/null)"; then
	: # Successfully reading an empty value must not inherit the default.
else
	networks=lan
fi
if [ -z "$networks" ]; then
	scope_log "DNS redirect disabled: trusted network allowlist is empty"
	exit 1
fi

# UCI persists this nonempty sentinel, unlike an empty scalar option. Reject a
# mixed list in full so an ambiguous disable request can never enable members.
network_count=0
has_none=0
for logical in $networks; do
	network_count=$((network_count + 1))
	[ "$logical" != none ] || has_none=1
done
if [ "$has_none" -eq 1 ]; then
	if [ "$network_count" -eq 1 ]; then
		scope_log "DNS redirect disabled: explicit none sentinel"
	else
		scope_log "DNS redirect disabled: none must not be mixed with trusted networks"
	fi
	exit 1
fi
if [ ! -r "$DNS_REDIRECT_NETWORK_LIB" ]; then
	scope_log "DNS redirect disabled: network resolver unavailable"
	exit 1
fi
# shellcheck source=/dev/null
. "$DNS_REDIRECT_NETWORK_LIB"
if ! command -v network_get_device >/dev/null 2>&1 ||
   ! command -v network_flush_cache >/dev/null 2>&1; then
	scope_log "DNS redirect disabled: network resolver contract unavailable"
	exit 1
fi
network_flush_cache

# Secondary safeguards, not the trust boundary: only the explicit allowlist
# above grants access. WAN renaming or an unknown device never grants access.
wan_devices=" lo wan wan6 "
for logical in wan wan6; do
	dev=
	if network_get_device dev "$logical" >/dev/null 2>&1 && valid_device "$dev"; then
		wan_devices="$wan_devices$dev "
	fi
done

devices=" "
expression=
separator=
for logical in $networks; do
	if ! valid_network "$logical"; then
		scope_log "DNS redirect: skipping invalid logical network name"
		continue
	fi
	case "$logical" in
		lo|loopback|wan|wan6)
			scope_log "DNS redirect: refusing loopback/WAN logical network"
			continue
			;;
	esac
	dev=
	if ! network_get_device dev "$logical" >/dev/null 2>&1 || [ -z "$dev" ]; then
		scope_log "DNS redirect: skipping unresolved trusted network"
		continue
	fi
	if ! valid_device "$dev"; then
		scope_log "DNS redirect: skipping invalid network device name"
		continue
	fi
	case "$wan_devices" in
		*" $dev "*)
			scope_log "DNS redirect: refusing loopback/WAN device"
			continue
			;;
	esac
	case "$devices" in *" $dev "*) continue ;; esac
	devices="$devices$dev "
	expression="$expression$separator\"$dev\""
	separator=", "
done

if [ -z "$expression" ]; then
	scope_log "DNS redirect disabled: no resolved trusted ingress devices"
	exit 1
fi
printf 'iifname { %s }\n' "$expression"
