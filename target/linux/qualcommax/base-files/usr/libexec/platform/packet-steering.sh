#!/bin/sh
# Both netifd and ECM use this platform entry. Keep one RPS/RFS owner when
# NSS is loaded, regardless of the ordering of their reload callbacks.

if [ -d /sys/module/qca_nss_drv ]; then
	# set-irq-affinity owns the complete NSS queue policy. Do not clear every
	# physical queue first: a failed/partial start_rps would otherwise leave
	# RPS/RFS at zero. On failure only, fall back to the generic policy and
	# preserve the RPS failure status.
	/etc/init.d/set-irq-affinity start_rps
	rc=$?
	[ "$rc" -eq 0 ] && exit 0
	/usr/libexec/network/packet-steering.uc -l 0 0
	generic_rc=$?
	[ "$generic_rc" -eq 0 ] || exit "$generic_rc"
	exit "$rc"
fi

# Preserve the generic netifd policy when this target runs without NSS.
flows="$(uci -q get 'network.@globals[0].steering_flows')"
case "$flows" in
	''|*[!0-9]*) flows=0 ;;
esac
exec /usr/libexec/network/packet-steering.uc -l "$flows" "${1:-}"
