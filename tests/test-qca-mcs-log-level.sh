#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
patch="$root/package/qca-nss/qca-mcs/patches/009-quiet-unconfigured-wifi-leave-events.patch"
makefile="$root/package/qca-nss/qca-mcs/Makefile"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "PASS: $1"; }
bad() { fail=$((fail + 1)); echo "FAIL: $1"; }

[ -s "$patch" ] && ok "qca-mcs quiet leave-event patch exists" || bad "qca-mcs quiet leave-event patch exists"
# r3 introduced this patch; later independent MCS fixes must not fail this gate.
# The build's semantic verifier owns exact release identity, also checked here
# when the workflow exports its expected value.
release_count=$(grep -c '^PKG_RELEASE:=' "$makefile" || true)
release=$(sed -n 's/^PKG_RELEASE:=//p' "$makefile")
numeric() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
if [ "$release_count" -eq 1 ] && numeric "$release" && [ "$release" -ge 3 ] 2>/dev/null; then
    ok "qca-mcs release retains quiet-patch floor r3"
else
    bad "qca-mcs release must be one numeric value at least r3"
fi
if [ "${SOURCE_QCA_MCS_PKG_RELEASE+x}" = x ]; then
    expected=$SOURCE_QCA_MCS_PKG_RELEASE
    if numeric "$expected" && [ "$expected" -gt 0 ] 2>/dev/null && [ "$release" = "$expected" ]; then
        ok "qca-mcs release matches the build lock"
    else
        bad "qca-mcs release differs from the build lock"
    fi
fi
grep -Fq 'Origin: VIKINGYFY/immortalwrt@2e496928a9b1a6e6104fa44aa20f359fa26740a0' "$patch" \
    && ok "patch records reviewed VIKING origin" \
    || bad "patch records reviewed VIKING origin"

added=$(grep -c '^+.*pr_debug(' "$patch" || true)
removed=$(grep -c '^-.*printk(KERN_DEBUG' "$patch" || true)
[ "$added" -eq 4 ] && ok "four leave-event messages use pr_debug" || bad "expected four pr_debug additions, got $added"
[ "$removed" -eq 4 ] && ok "four ring-buffer printk calls are removed" || bad "expected four printk removals, got $removed"

if grep -q '^+.*printk(KERN_DEBUG' "$patch"; then
    bad "patch adds no KERN_DEBUG printk"
else
    ok "patch adds no KERN_DEBUG printk"
fi

echo "=== summary: PASS=$pass FAIL=$fail ==="
[ "$fail" -eq 0 ]
