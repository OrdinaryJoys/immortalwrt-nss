#!/bin/sh
# Host-side logic test for ax6-led-schedule using a fake sysfs and fake uci.
set -eu
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
LEDS="$ROOT/leds"; mkdir -p "$LEDS"/blue:system "$LEDS"/blue:network
for l in blue:system blue:network; do
  printf 'none timer default-on [netdev]\n' > "$LEDS/$l/trigger"
  printf '1\n' > "$LEDS/$l/brightness"
  printf '1\n' > "$LEDS/$l/max_brightness"
  printf 'wan\n' > "$LEDS/$l/device_name"
  printf '50\n' > "$LEDS/$l/interval"
done
cat > "$ROOT/uci" <<'UCI'
#!/bin/sh
# fake uci: uci -q get ax6_led.schedule.<key>
key="${3##*.}"
case "$key" in
 enabled) echo "${TEST_ENABLED:-1}";;
 on_time) echo "${TEST_ON:-00:00}";;
 off_time) echo "${TEST_OFF:-00:01}";;
 days) echo "${TEST_DAYS:-1 2 3 4 5 6 7}";;
 leds) echo "blue:system blue:network";;
esac
UCI
chmod +x "$ROOT/uci"
export PATH="$ROOT:$PATH"
export AX6_LED_SYSFS="$LEDS"
export AX6_LED_STATE="$ROOT/state"
export AX6_LED_MODE="$ROOT/mode"
SCRIPT=$(CDPATH= cd -- "$(dirname "$0")/../../package/base-files/files/usr/sbin" && pwd)/ax6-led-schedule
[ -x "$SCRIPT" ] || { echo "script missing"; exit 1; }
# 1) off window -> off
TEST_ENABLED=1 TEST_ON=00:00 TEST_OFF=00:01 AX6_LED_NOW=12:00 AX6_LED_DAY=1 "$SCRIPT" run
[ "$(cat "$LEDS/blue:system/brightness")" = 0 ] || { echo "off failed"; exit 1; }
# 2) on window -> restore
TEST_ENABLED=1 TEST_ON=00:00 TEST_OFF=00:01 AX6_LED_NOW=00:00 AX6_LED_DAY=1 "$SCRIPT" run
[ "$(cat "$LEDS/blue:system/brightness")" = 1 ] || { echo "on failed"; exit 1; }
# 3) cross-midnight: 23:00-07:00, now 02:00 -> on
TEST_ENABLED=1 TEST_ON=23:00 TEST_OFF=07:00 AX6_LED_NOW=02:00 AX6_LED_DAY=1 "$SCRIPT" run
[ "$(cat "$LEDS/blue:system/brightness")" = 1 ] || { echo "cross-midnight on failed"; exit 1; }
# 4) disabled leaves LEDs unchanged
TEST_ENABLED=0 AX6_LED_NOW=12:00 AX6_LED_DAY=1 "$SCRIPT" run
[ "$(cat "$LEDS/blue:system/brightness")" = 1 ] || { echo "disabled changed LED"; exit 1; }
echo "PASS ax6-led-schedule"
