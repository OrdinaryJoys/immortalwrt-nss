#!/bin/sh

set -eu

SCRIPT=${1:-package/qca-nss/qca-nss-ecm/files/disable_offloads.sh}
SCRIPT=$(cd "$(dirname "$SCRIPT")" && pwd)/$(basename "$SCRIPT")
TMPDIR_ROOT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_ROOT"' EXIT HUP INT TERM

mkdir -p \
    "$TMPDIR_ROOT/bin" \
    "$TMPDIR_ROOT/sys/class/net/eth0/device" \
    "$TMPDIR_ROOT/sys/class/net/br-lan"

cat > "$TMPDIR_ROOT/functions.sh" <<'EOF'
config_load() { :; }

config_get_bool() {
    case "$1" in
        disable_offloads) eval "$1=\${TEST_DISABLE_OFFLOADS:-$4}" ;;
        disable_flow_control) eval "$1=\${TEST_DISABLE_FLOW_CONTROL:-$4}" ;;
        disable_interrupt_moderation) eval "$1=\${TEST_DISABLE_INTERRUPT_MODERATION:-$4}" ;;
        disable_gro) eval "$1=\${TEST_DISABLE_GRO:-$4}" ;;
        disable_gro_list) eval "$1=\${TEST_DISABLE_GRO_LIST:-$4}" ;;
        *) eval "$1=$4" ;;
    esac
}

config_get() {
    case "$1" in
        offload_host_ifaces) eval "$1=\${TEST_HOST_IFACES:-$4}" ;;
        offload_physical_policy) eval "$1=\${TEST_PHYSICAL_POLICY:-$4}" ;;
        *) eval "$1=$4" ;;
    esac
}
EOF

cat > "$TMPDIR_ROOT/bin/ethtool" <<'EOF'
#!/bin/sh
printf 'ethtool' >> "$TEST_COMMAND_LOG"
printf ' %s' "$@" >> "$TEST_COMMAND_LOG"
printf '\n' >> "$TEST_COMMAND_LOG"

case "${1:-}" in
    -k)
        cat <<'FEATURES'
Features for interface:
rx-checksumming: on
generic-segmentation-offload: on
rx-gro-list: off
FEATURES
        ;;
esac
EOF
chmod +x "$TMPDIR_ROOT/bin/ethtool"

cat > "$TMPDIR_ROOT/bin/logger" <<'EOF'
#!/bin/sh
printf 'logger' >> "$TEST_COMMAND_LOG"
printf ' %s' "$@" >> "$TEST_COMMAND_LOG"
printf '\n' >> "$TEST_COMMAND_LOG"
EOF
chmod +x "$TMPDIR_ROOT/bin/logger"

run_policy() {
    : > "$TMPDIR_ROOT/commands.log"
    PATH="$TMPDIR_ROOT/bin:$PATH" \
    OFFLOAD_FUNCTIONS_SH="$TMPDIR_ROOT/functions.sh" \
    OFFLOAD_SYS_CLASS_NET="$TMPDIR_ROOT/sys/class/net" \
    TEST_COMMAND_LOG="$TMPDIR_ROOT/commands.log" \
    TEST_DISABLE_OFFLOADS=1 \
    TEST_DISABLE_GRO_LIST=0 \
    TEST_HOST_IFACES=br-lan \
    TEST_PHYSICAL_POLICY="$1" \
    SCRIPT="$SCRIPT" \
        sh -c '. "$SCRIPT"; shift; disable_offload "$@"' sh "$@"
}

assert_count() {
    expected=$1
    pattern=$2
    description=$3
    actual=$(grep -Ec -- "$pattern" "$TMPDIR_ROOT/commands.log" || true)
    if [ "$actual" -ne "$expected" ]; then
        echo "FAIL: $description (expected $expected, got $actual)" >&2
        cat "$TMPDIR_ROOT/commands.log" >&2
        exit 1
    fi
}

assert_contains() {
    pattern=$1
    description=$2
    if ! grep -Eq -- "$pattern" "$TMPDIR_ROOT/commands.log"; then
        echo "FAIL: $description" >&2
        cat "$TMPDIR_ROOT/commands.log" >&2
        exit 1
    fi
}

# Parameterless init/reload: physical eth0 is report-only and virtual br-lan
# is hard-disabled exactly once through the unified interface list.
run_policy report
assert_count 0 '^ethtool -K eth0 ' "report policy must not change the physical NSS port"
assert_count 1 '^ethtool -K br-lan ' "parameterless call must process br-lan once"
assert_contains '^logger -t \[offload-report\] eth0: offloads ON ' "physical report must list enabled features"

# Explicit hotplug invocation must not run a second virtual-host pass.
run_policy report br-lan
assert_count 1 '^ethtool -K br-lan ' "explicit br-lan call must process the interface once"

# Unknown physical policy falls back to the conservative disable behavior.
run_policy unexpected eth0
assert_count 1 '^ethtool -K eth0 ' "unknown policy must disable the physical interface"
assert_contains "unknown physical policy 'unexpected' -- defaulting to disable for eth0" \
    "unknown policy must emit an ASCII diagnostic"

echo "test-disable-offloads: PASS"
