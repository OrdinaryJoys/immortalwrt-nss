#!/bin/sh

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=$SCRIPT_DIR/../package/kernel/mac80211/files/qca-nss-pbuf.init
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t pbuf)
trap 'rm -rf "$TMP"' EXIT INT TERM HUP

PASS=0
FAIL=0
MODE=normal
WRITE_COUNT=0
WRITE_LOG=$TMP/write.log

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }

state_file() {
  printf '%s/%s' "$TMP" "$(printf '%s' "$1" | tr '.' '_')"
}

set_value() {
  printf '%s\n' "$2" > "$(state_file "$1")"
}

get_value() {
  file=$(state_file "$1")
  [ -r "$file" ] && sed -n '1p' "$file" || printf '0\n'
}

sysctl() {
  if [ "$1" = "-n" ]; then
    get_value "$3"
    return 0
  fi

  [ "$1" = "-w" ] || return 1
  key=${2%%=*}
  value=${2#*=}
  WRITE_COUNT=$((WRITE_COUNT + 1))
  printf '%s=%s\n' "$key" "$value" >> "$WRITE_LOG"

  case "$MODE:$key" in
    retry:dev.nss.n2hcfg.extra_pbuf_core0)
      [ "$WRITE_COUNT" -gt 1 ] && set_value "$key" 10002432
      ;;
    partial:dev.nss.n2hcfg.extra_pbuf_core0)
      set_value "$key" 4096
      ;;
    mismatch:*)
      set_value "$key" 1
      ;;
    normal:dev.nss.n2hcfg.extra_pbuf_core0)
      set_value "$key" $(((value + 4095) / 4096 * 4096))
      ;;
    coupled:dev.nss.n2hcfg.extra_pbuf_core0)
      set_value "$key" $(((value + 4095) / 4096 * 4096))
      ;;
    coupled:dev.nss.n2hcfg.n2h_wifi_pool_buf)
      set_value "$key" "$value"
      set_value dev.nss.n2hcfg.n2h_high_water_core0 "$value"
      ;;
    *)
      set_value "$key" "$value"
      ;;
  esac
  return 0
}

logger() { :; }
sleep() { :; }
getconf() { printf '4096\n'; }

# shellcheck source=../package/kernel/mac80211/files/qca-nss-pbuf.init
. "$SCRIPT"

KEY=dev.nss.n2hcfg.extra_pbuf_core0

reset_writes() {
  WRITE_COUNT=0
  : > "$WRITE_LOG"
}

test_profile() {
  label=$1
  requested_extra=$2
  expected_extra=$3
  expected_high=$4
  expected_wifi=$5
  high_key=dev.nss.n2hcfg.n2h_high_water_core0
  wifi_key=dev.nss.n2hcfg.n2h_wifi_pool_buf

  set_value "$KEY" 0
  set_value "$high_key" 0
  set_value "$wifi_key" 0
  MODE=coupled
  reset_writes
  # shellcheck disable=SC2034
  board='test'
  # shellcheck disable=SC2034
  extra_pbuf_core0=$requested_extra
  # shellcheck disable=SC2034
  n2h_high_water_core0=$expected_high
  # shellcheck disable=SC2034
  n2h_wifi_pool_buf=$expected_wifi

  if apply_sysctl &&
     [ "$(get_value "$KEY")" = "$expected_extra" ] &&
     [ "$(get_value "$high_key")" = "$expected_high" ] &&
     [ "$(get_value "$wifi_key")" = "$expected_wifi" ] &&
     [ "$(sed 's/=.*//' "$WRITE_LOG" | tr '\n' ' ')" = \
       "$KEY $wifi_key $high_key " ]; then
    ok "$label profile preserves final high-water after the WiFi pool update"
  else
    bad "$label profile preserves final high-water after the WiFi pool update"
  fi
}

set_value test.exact 0
MODE=normal
WRITE_COUNT=0
if write_sysctl_exact test.exact 65536 && [ "$(get_value test.exact)" = 65536 ]; then
  ok "exact sysctl write is verified"
else
  bad "exact sysctl write is verified"
fi

test_profile 1GB 10000000 10002432 65536 32768
test_profile 512MB 8000000 8003584 32768 16384
test_profile 256MB 4000000 4001792 16384 8192

set_value "$KEY" 0
MODE=normal
WRITE_COUNT=0
if configure_extra_pbuf 10000000 && [ "$(get_value "$KEY")" = 10002432 ]; then
  ok "PBUF readback accepts the driver's PAGE_SIZE alignment"
else
  bad "PBUF readback accepts the driver's PAGE_SIZE alignment"
fi

set_value "$KEY" 10002432
MODE=normal
WRITE_COUNT=0
if configure_extra_pbuf 10000000 && [ "$WRITE_COUNT" -eq 0 ]; then
  ok "matching one-shot PBUF allocation is not rewritten"
else
  bad "matching one-shot PBUF allocation is not rewritten"
fi

set_value "$KEY" 0
MODE=retry
WRITE_COUNT=0
if configure_extra_pbuf 10000000 && [ "$WRITE_COUNT" -eq 2 ]; then
  ok "zero readback is retried and then verified"
else
  bad "zero readback is retried and then verified"
fi

set_value "$KEY" 0
MODE=partial
WRITE_COUNT=0
if configure_extra_pbuf 10000000; then
  bad "partial one-shot allocation is rejected"
else
  [ "$WRITE_COUNT" -eq 1 ] \
    && ok "partial one-shot allocation is rejected without duplicate write" \
    || bad "partial one-shot allocation is rejected without duplicate write"
fi

set_value "$KEY" 8003584
MODE=normal
WRITE_COUNT=0
if configure_extra_pbuf 10000000; then
  bad "wrong existing PBUF profile is rejected"
else
  [ "$WRITE_COUNT" -eq 0 ] \
    && ok "wrong existing PBUF profile is rejected without rewrite" \
    || bad "wrong existing PBUF profile is rejected without rewrite"
fi

set_value test.mismatch 0
MODE=mismatch
WRITE_COUNT=0
if write_sysctl_exact test.mismatch 42 2; then
  bad "exact readback mismatch fails"
else
  [ "$WRITE_COUNT" -eq 2 ] \
    && ok "exact readback mismatch retries then fails" \
    || bad "exact readback mismatch retries then fails"
fi

if grep -q 'apply_sysctl || return 1' "$SCRIPT"; then
  ok "profile application propagates verification failures"
else
  bad "profile application propagates verification failures"
fi

echo "=== summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
