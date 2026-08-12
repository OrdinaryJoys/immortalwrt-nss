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

set_value test.exact 0
MODE=normal
WRITE_COUNT=0
if write_sysctl_exact test.exact 65536 && [ "$(get_value test.exact)" = 65536 ]; then
  ok "exact sysctl write is verified"
else
  bad "exact sysctl write is verified"
fi

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
