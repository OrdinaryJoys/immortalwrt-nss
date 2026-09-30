#!/bin/sh
# shellcheck disable=SC3043

set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=${IRQ_TEST_SCRIPT:-$SCRIPT_DIR/../target/linux/qualcommax/base-files/etc/init.d/set-irq-affinity}
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t irq-discovery)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }

mkdir -p "$TMP/sys/class/net" "$TMP/bin"
for eth in lan1 lan2 wan eth0 br-lan wlan0 ztabc; do
	mkdir -p "$TMP/sys/class/net/$eth"
done

cat > "$TMP/bin/board-detect" <<'EOF'
#!/bin/sh
[ "${BOARD_DETECT_FAIL:-0}" = 0 ] || exit 1
printf '%s\n' ${BOARD_DETECT_DEVICES:-} > "$1"
EOF
chmod +x "$TMP/bin/board-detect"

cat > "$TMP/functions.sh" <<'EOF'
config_load() { [ "${UCI_FAIL:-0}" = 0 ]; }
config_foreach() { "$1" test; }
config_get() {
	case "$3" in
		device) eval "$1=\${UCI_DEVICE:-}" ;;
		ports) eval "$1=\${UCI_PORTS:-}" ;;
	esac
}
EOF

jsonfilter() {
	local input
	while [ "$#" -gt 0 ]; do
		case "$1" in
			-i) input=$2; shift 2 ;;
			*) shift ;;
		esac
	done
	[ -n "${input:-}" ] && cat "$input"
}

logger() { :; }
make_test_queue() {
	mkdir -p "$IRQ_SYS_CLASS_NET/$1/queues/rx-0" "$IRQ_SYS_CLASS_NET/$1/queues/tx-0"
	printf '0\n' > "$IRQ_SYS_CLASS_NET/$1/queues/rx-0/rps_cpus"
	printf '0\n' > "$IRQ_SYS_CLASS_NET/$1/queues/rx-0/rps_flow_cnt"
	printf '0\n' > "$IRQ_SYS_CLASS_NET/$1/queues/tx-0/xps_cpus"
}
sleep() {
	case "${LATE_DEVICE_PHASE:-}:$1" in
		retry:3)
			make_test_queue wan9
			LATE_DEVICE_PHASE=complete
			;;
		wave:30)
			make_test_queue wan9
			make_test_queue lan1
			LATE_DEVICE_PHASE=complete
			;;
	esac
	return 0
}
extra_command() { :; }

IRQ_BOARD_JSON=$TMP/board.json
IRQ_BOARD_DETECT=$TMP/bin/board-detect
IRQ_CPU_ONLINE=$TMP/cpu-online
IRQ_SYS_CLASS_NET=$TMP/sys/class/net
IRQ_UCI_FUNCTIONS=$TMP/functions.sh
IRQ_RPS_SOCK_FLOW_ENTRIES=$TMP/rps_sock_flow_entries
TMPDIR=$TMP
export IRQ_BOARD_JSON IRQ_BOARD_DETECT IRQ_CPU_ONLINE IRQ_SYS_CLASS_NET
export IRQ_UCI_FUNCTIONS IRQ_RPS_SOCK_FLOW_ENTRIES TMPDIR

# shellcheck source=../target/linux/qualcommax/base-files/etc/init.d/set-irq-affinity
. "$SCRIPT"

assert_devices() {
	label=$1
	expected=$2
	actual=$(get_board_devices | tr '\n' ' ')
	if [ "$actual" = "$expected" ]; then
		ok "$label"
	else
		bad "$label (expected '$expected', got '$actual')"
	fi
}

printf 'lan2\nlan1\nbr-lan\nmissing\n' > "$IRQ_BOARD_JSON"
BOARD_DETECT_DEVICES='wan'
UCI_DEVICE=eth0
UCI_PORTS='lan1 lan2'
export BOARD_DETECT_DEVICES UCI_DEVICE UCI_PORTS
assert_devices '/etc/board.json is preferred and filtered' 'lan1 lan2 '

rm -f "$IRQ_BOARD_JSON"
BOARD_DETECT_DEVICES='wan lan2 bad/name wlan0'
export BOARD_DETECT_DEVICES
assert_devices 'fresh board_detect repairs the first-overlay-boot gap' 'lan2 wan '

BOARD_DETECT_FAIL=1
UCI_DEVICE=eth0
UCI_PORTS='lan2 lan1 br-lan'
export BOARD_DETECT_FAIL UCI_DEVICE UCI_PORTS
assert_devices 'UCI shell API is a valid fallback' 'eth0 lan1 lan2 '

UCI_FUNCTIONS=$TMP/missing-functions.sh
assert_devices 'restricted sysfs scan is the final fallback' 'eth0 lan1 lan2 wan '

printf '0-3\n' > "$IRQ_CPU_ONLINE"
mkdir -p "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0" "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_cpus"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_flow_cnt"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0/xps_cpus"
: > "$IRQ_RPS_SOCK_FLOW_ENTRIES"
printf 'lan1\n' > "$IRQ_BOARD_JSON"
BOARD_DETECT_FAIL=0
export BOARD_DETECT_FAIL
start
# The boot path spawns background re-assert waves; wait for them so their
# idempotent writes cannot race the readback assertions below.
wait 2>/dev/null || true

if [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_cpus")" = f ] &&
   [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_flow_cnt")" = 8192 ] &&
   [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0/xps_cpus")" = f ] &&
   [ "$(cat "$IRQ_RPS_SOCK_FLOW_ENTRIES")" = 65535 ]; then
	ok 'discovered device receives the complete RPS/RFS/XPS policy'
else
	bad 'discovered device receives the complete RPS/RFS/XPS policy'
fi

# No queues at all (first-boot gap): the retry loop must exhaust and finish
# instead of hanging; the warning path is exercised with sleep mocked out.
rm -rf "$IRQ_SYS_CLASS_NET"/*/queues
BOARD_DETECT_FAIL=1
UCI_DEVICE=eth0
UCI_PORTS=
export BOARD_DETECT_FAIL UCI_DEVICE UCI_PORTS
if start; then
	wait 2>/dev/null || true
	ok 'queue-less first boot retries and finishes without hanging'
else
	bad 'queue-less first boot retries and finishes without hanging'
fi

# The hotplug event entry must apply the full policy including RFS flow
# counts (a previous version left flow_cnt unset and zeroed the queues).
mkdir -p "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0" "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_cpus"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_flow_cnt"
: > "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0/xps_cpus"
start_rps
wait 2>/dev/null || true
if [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_cpus")" = f ] &&
   [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/rx-0/rps_flow_cnt")" = 8192 ] &&
   [ "$(cat "$IRQ_SYS_CLASS_NET/lan1/queues/tx-0/xps_cpus")" = f ]; then
	ok 'event re-assert entry applies the complete RPS/RFS/XPS policy'
else
	bad 'event re-assert entry applies the complete RPS/RFS/XPS policy'
fi

if grep -q "Zerotier" "$SCRIPT_DIR/../target/linux/qualcommax/base-files/etc/hotplug.d/net/25-set-irq-affinity"; then
	ok 'hotplug filter covers the ZeroTier interface name (runtime reload re-assert)'
else
	bad 'hotplug filter covers the ZeroTier interface name (runtime reload re-assert)'
fi

assert_queue_policy() {
	label=$1
	eth=$2
	if [ "$(cat "$IRQ_SYS_CLASS_NET/$eth/queues/rx-0/rps_cpus")" = f ] &&
	   [ "$(cat "$IRQ_SYS_CLASS_NET/$eth/queues/rx-0/rps_flow_cnt")" = 8192 ] &&
	   [ "$(cat "$IRQ_SYS_CLASS_NET/$eth/queues/tx-0/xps_cpus")" = f ]; then
		ok "$label"
	else
		bad "$label"
	fi
}

# The old implementation captured an empty list before sleep(3), so retries
# and delayed waves could never discover the port created by deferred probe.
printf 'wan9\n' > "$IRQ_BOARD_JSON"
LATE_DEVICE_PHASE=retry
start
wait 2>/dev/null || true
assert_queue_policy 'retry discovers a port absent at initial sysfs scan' wan9

# One existing port makes start() stop retrying. A later port still needs
# discovery in the delayed wave, together with re-created existing queues.
rm -rf "$IRQ_SYS_CLASS_NET/wan9"
printf 'lan1\nwan9\n' > "$IRQ_BOARD_JSON"
LATE_DEVICE_PHASE=wave
start
wait 2>/dev/null || true
assert_queue_policy 'delayed wave discovers an additional data-plane port' wan9
assert_queue_policy 'delayed wave restores re-created queues on an existing port' lan1

LATE_DEVICE_PHASE=complete
make_test_queue wan9
start_rps
assert_queue_policy 'event entry rediscovers ports and restores their queues' wan9

rm -rf "$IRQ_SYS_CLASS_NET"/*/queues
if start_rps; then
	bad 'event entry must report failure when no writable queue exists'
else
	ok 'event entry reports failure when no writable queue exists'
fi

echo "=== summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
