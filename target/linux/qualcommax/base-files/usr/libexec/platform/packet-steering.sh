#!/bin/sh
# Both netifd and ECM use this platform entry. Keep one RPS/RFS owner when
# NSS is loaded, regardless of the ordering of their reload callbacks.

if [ -d /sys/module/qca_nss_drv ]; then
	/usr/libexec/network/packet-steering.uc -l 0 0 || exit $?
	# The event entry changes queues only, without IRQ changes or boot workers.
	exec /etc/init.d/set-irq-affinity start_rps
fi

# Preserve the generic netifd policy when this target runs without NSS.
flows="$(uci -q get 'network.@globals[0].steering_flows')"
case "$flows" in
	''|*[!0-9]*) flows=0 ;;
esac
exec /usr/libexec/network/packet-steering.uc -l "$flows" "${1:-}"
