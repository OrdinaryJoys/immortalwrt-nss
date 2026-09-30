#!/bin/sh
# Run the real helper and isolated init function with offline mocks only.
# Optional helper/init paths support re-running against extracted rootfs bytes.
# No networking, real nft/uci/ubus, init dispatch or service actions are used.
# Literal shell/make text below is deliberate: it is test input, not expansion.
# shellcheck disable=SC2016
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
helper=${1:-$root/package/network/services/dnsmasq/files/dns-redirect-scope.sh}
init=${2:-$root/package/network/services/dnsmasq/files/dnsmasq.init}
[ "$#" -le 2 ] || { echo "usage: $0 [HELPER_PATH] [INIT_PATH]" >&2; exit 64; }
fixture="$root/tests/fixtures/dns-redirect-scope"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/dns-redirect-scope.XXXXXX")
cleanup()
{
	test_status=$?
	trap - EXIT HUP INT TERM
	rm -rf "$tmp"
	exit "$test_status"
}
trap cleanup EXIT HUP INT TERM

checks=0
fail()
{
	printf 'FAIL: %s\n' "$1" >&2
	exit 1
}
pass()
{
	checks=$((checks + 1))
	printf 'PASS: %s\n' "$1"
}
[ -x "$helper" ] || fail 'scope helper missing or not executable'
[ -s "$init" ] || fail 'dnsmasq init missing'

DNS_REDIRECT_UCI="$fixture/uci.sh"
DNS_REDIRECT_LOGGER="$fixture/logger.sh"
DNS_REDIRECT_NETWORK_LIB="$fixture/network.sh"
DNS_SCOPE_TEST_LOG="$tmp/logger.log"
export DNS_REDIRECT_UCI DNS_REDIRECT_LOGGER DNS_REDIRECT_NETWORK_LIB DNS_SCOPE_TEST_LOG
DNS_SCOPE_TEST_STATE=absent
DNS_SCOPE_TEST_NETWORKS=
export DNS_SCOPE_TEST_STATE DNS_SCOPE_TEST_NETWORKS

expect_scope()
{
	label=$1
	expected=$2
	expect_rc=${3:-0}
	: > "$DNS_SCOPE_TEST_LOG"
	actual_rc=0
	actual=$("$helper") || actual_rc=$?
	[ "$actual_rc" -eq "$expect_rc" ] || fail "$label: wrong helper status $actual_rc"
	[ "$actual" = "$expected" ] || fail "$label: unexpected scope [$actual]"
	if [ "$expect_rc" -ne 0 ]; then
		[ -s "$DNS_SCOPE_TEST_LOG" ] || fail "$label: missing failure diagnostic"
	fi
	pass "$label"
}

expect_scope 'absent option defaults only to LAN' 'iifname { "br-lan" }'
DNS_SCOPE_TEST_STATE=deleted-empty
expect_scope 'UCI empty scalar deletion is modeled as absent and defaults to LAN' 'iifname { "br-lan" }'
DNS_SCOPE_TEST_STATE=empty
expect_scope 'successful empty GET fails closed (not CLI empty scalar deletion)' '' 1
DNS_SCOPE_TEST_STATE=unreadable
expect_scope 'unreadable network config fails closed' '' 1
DNS_SCOPE_TEST_STATE=custom
DNS_SCOPE_TEST_NETWORKS=none
expect_scope 'persistent none sentinel disables redirect' '' 1
DNS_SCOPE_TEST_NETWORKS=' 	 none 	 '
expect_scope 'whitespace around none still disables redirect' '' 1
DNS_SCOPE_TEST_NETWORKS='none lan'
expect_scope 'none mixed before a trusted network rejects the entire list' '' 1
DNS_SCOPE_TEST_NETWORKS='lan none'
expect_scope 'none mixed after a trusted network rejects the entire list' '' 1
DNS_SCOPE_TEST_NETWORKS='lan Zerotier'
expect_scope 'explicit ZeroTier network plus LAN' 'iifname { "br-lan", "ztfixture12345" }'
DNS_SCOPE_TEST_NETWORKS='lan alias lan Zerotier vlan'
expect_scope 'deduplicate device names and preserve VLAN device' 'iifname { "br-lan", "ztfixture12345", "br-lan.42" }'
DNS_SCOPE_TEST_NETWORKS='wan wan6 lo loopback'
expect_scope 'WAN and loopback logical names refused' '' 1
DNS_SCOPE_TEST_NETWORKS='lan'
export DNS_SCOPE_TEST_LAN_DEVICE
for denied_device in lo wan wan6 pppoe-wan wwan0; do
	DNS_SCOPE_TEST_LAN_DEVICE=$denied_device
	expect_scope "LAN alias to $denied_device refused" '' 1
done
DNS_SCOPE_TEST_LAN_DEVICE='usb-uplink0'
DNS_SCOPE_TEST_WAN_DEVICE='usb-uplink0'
export DNS_SCOPE_TEST_WAN_DEVICE
expect_scope 'renamed WAN L3 device is never allowed by alias' '' 1
unset DNS_SCOPE_TEST_WAN_DEVICE DNS_SCOPE_TEST_LAN_DEVICE
DNS_SCOPE_TEST_NETWORKS='missing'
expect_scope 'unresolved trusted network fails closed' '' 1
DNS_SCOPE_TEST_NETWORKS='missing lan'
expect_scope 'unresolved member skipped while explicit LAN remains' 'iifname { "br-lan" }'
[ -s "$DNS_SCOPE_TEST_LOG" ] || fail 'unresolved partial member diagnostic missing'
DNS_SCOPE_TEST_NETWORKS='lan zt* lan;reject "wan" $(touch)'
expect_scope 'wildcards and shell/nft metacharacters rejected' 'iifname { "br-lan" }'
DNS_SCOPE_TEST_NETWORKS='lan'
export DNS_SCOPE_TEST_LAN_DEVICE
for invalid_device in 'br-*' 'br"lan' 'br;lan' 'br lan' 'br\lan' 'abcdefghijklmnop'; do
	DNS_SCOPE_TEST_LAN_DEVICE=$invalid_device
	expect_scope "invalid device [$invalid_device] fails closed" '' 1
done
DNS_SCOPE_TEST_LAN_DEVICE=
expect_scope 'empty resolved device fails closed' '' 1
unset DNS_SCOPE_TEST_LAN_DEVICE
DNS_REDIRECT_NETWORK_LIB="$tmp/missing-network-library"
expect_scope 'missing network library fails closed' '' 1
DNS_REDIRECT_NETWORK_LIB="$fixture/network.sh"
DNS_SCOPE_TEST_NETWORKS='   '
expect_scope 'whitespace-only allowlist fails closed' '' 1

# Extract only the function under test; never source/dispatch the full init.
awk '
	/^dnsmasq_dns_redirect\(\)$/ { in_function=1 }
	in_function { print }
	in_function && /^}$/ { exit }
' "$init" > "$tmp/dnsmasq-function.sh"
[ -s "$tmp/dnsmasq-function.sh" ] || fail 'isolated dnsmasq scope function missing'
grep -Fq 'DNS_REDIRECT_SCOPE="${DNS_REDIRECT_SCOPE:-/usr/libexec/dns-redirect-scope}"' "$init" ||
	fail 'production helper default not installed path'
grep -Fq 'dnsmasq_dns_redirect "$cfg"' "$init" || fail 'redirect callback not wired'
# shellcheck source=/dev/null
. "$tmp/dnsmasq-function.sh"

config_get_bool()
{
	[ "$3" = dns_redirect ] || fail 'unexpected boolean config read'
	export "$1=${DNS_SCOPE_TEST_REDIRECT:-1}"
}
config_get()
{
	[ "$3" = port ] || fail 'unexpected config read'
	export "$1=${DNS_SCOPE_TEST_PORT:-53}"
}
nft() { printf '%s\n' "$*" >> "$tmp/nft.log"; }
logger() { printf '%s\n' "$*" >> "$DNS_SCOPE_TEST_LOG"; }
DNS_REDIRECT_SCOPE=$helper
export DNS_REDIRECT_SCOPE
DNS_SCOPE_TEST_STATE=absent
: > "$tmp/nft.log"
dnsmasq_dns_redirect main
[ "$(wc -l < "$tmp/nft.log" | tr -d ' ')" = 3 ] || fail 'expected table, chain and one rule'
expected_rule='add rule inet dnsmasq prerouting meta nfproto { ipv4, ipv6 } iifname { "br-lan" } udp dport 53 counter redirect to :53 comment "DNSMASQ HIJACK"'
grep -Fxq "$expected_rule" "$tmp/nft.log" || fail 'real init emits incorrect dual-stack scoped rule'
if grep -q 'tcp' "$tmp/nft.log"; then fail 'UDP-only producer expanded to TCP'; fi
pass 'actual dnsmasq callback emits one scoped IPv4/IPv6 UDP rule'

DNS_SCOPE_TEST_STATE=custom
DNS_SCOPE_TEST_NETWORKS='lan Zerotier'
DNS_SCOPE_TEST_PORT=5353
: > "$tmp/nft.log"
dnsmasq_dns_redirect main
grep -Fq 'iifname { "br-lan", "ztfixture12345" } udp dport 53 counter redirect to :5353' "$tmp/nft.log" ||
	fail 'actual init lost explicit ZeroTier or configured DNS port'
pass 'actual dnsmasq callback preserves trusted ZeroTier and configured port'

for scenario in empty none mixed-none unresolved disabled port-zero port-invalid helper-missing helper-empty helper-failure; do
	DNS_SCOPE_TEST_STATE=absent
	DNS_SCOPE_TEST_REDIRECT=1
	DNS_SCOPE_TEST_PORT=53
	DNS_REDIRECT_SCOPE=$helper
	case "$scenario" in
		empty) DNS_SCOPE_TEST_STATE=empty ;;
		none) DNS_SCOPE_TEST_STATE=custom; DNS_SCOPE_TEST_NETWORKS=none ;;
		mixed-none) DNS_SCOPE_TEST_STATE=custom; DNS_SCOPE_TEST_NETWORKS='none lan' ;;
		unresolved) DNS_SCOPE_TEST_STATE=custom; DNS_SCOPE_TEST_NETWORKS=missing ;;
		disabled) DNS_SCOPE_TEST_REDIRECT=0 ;;
		port-zero) DNS_SCOPE_TEST_PORT=0 ;;
		port-invalid) DNS_SCOPE_TEST_PORT='53;accept' ;;
		helper-missing) DNS_REDIRECT_SCOPE="$tmp/missing-helper" ;;
		helper-empty) DNS_REDIRECT_SCOPE=/usr/bin/true ;;
		helper-failure) DNS_REDIRECT_SCOPE=/usr/bin/false ;;
	esac
	: > "$tmp/nft.log"
	dnsmasq_dns_redirect main 2> "$tmp/diagnostics"
	[ ! -s "$tmp/nft.log" ] || fail "$scenario: unexpected nft side effect"
	pass "actual callback $scenario returns success with no nft calls"
done

# Packaging and implementation gates apply only to the source defaults.
if [ "$#" -eq 0 ]; then
	grep -Fxq 'PKG_RELEASE:=3' "$root/package/network/services/dnsmasq/Makefile" || fail 'package release not bumped'
	grep -Fq '$(INSTALL_BIN) ./files/dns-redirect-scope.sh $(1)/usr/libexec/dns-redirect-scope' \
		"$root/package/network/services/dnsmasq/Makefile" || fail 'scope helper not installed'
	pass 'scope helper installed for dnsmasq variants and package release bumped'
fi
printf 'PASS: %s DNS ingress scope checks; offline mocks, no runtime or wire proof\n' "$checks"
