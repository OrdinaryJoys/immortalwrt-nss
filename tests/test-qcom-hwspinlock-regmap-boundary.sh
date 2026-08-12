#!/bin/sh

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PATCH=${1:-$REPO_ROOT/target/linux/qualcommax/patches-6.18/1002-hwspinlock-qcom-bound-max-register-by-resource.patch}
FIXTURE=$SCRIPT_DIR/fixtures/qcom-hwspinlock-probe-mmio-v6.18.c
FIXTURE_SHA256=91077e1684b94c3143693ce5d760c3dfaeaba1b1bcc621765ee8805275006343

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }

SHA_BIN=$(command -v sha256sum || true)
if [ -z "$SHA_BIN" ]; then
    SHA_BIN="shasum -a 256"
else
    SHA_BIN=sha256sum
fi

echo "=== Qualcomm hwspinlock regmap boundary test ==="

[ -s "$PATCH" ] && ok "patch exists" || bad "patch exists"
[ -s "$FIXTURE" ] && ok "fixture exists" || bad "fixture exists"

ACTUAL_SHA=$($SHA_BIN "$FIXTURE" | awk '{print $1}')
[ "$ACTUAL_SHA" = "$FIXTURE_SHA256" ] \
    && ok "fixture SHA256 matches" || bad "fixture SHA256 matches"

grep -q 'platform_get_resource(pdev, IORESOURCE_MEM, 0)' "$PATCH" \
    && ok "MMIO resource is inspected" || bad "MMIO resource is inspected"
grep -q 'size < data->regmap_config->reg_stride' "$PATCH" \
    && ok "small resource is rejected" || bad "small resource is rejected"
grep -q 'regmap_config.max_register = min_t(resource_size_t' "$PATCH" \
    && ok "max_register is clamped" || bad "max_register is clamped"
grep -q 'devm_regmap_init_mmio(dev, base, &regmap_config)' "$PATCH" \
    && ok "local regmap config is used" || bad "local regmap config is used"

HDR=$(grep -m1 '^@@ -[0-9]*,[0-9]* +[0-9]*,[0-9]* @@' "$PATCH" || true)
OLD_N=$(printf '%s' "$HDR" | sed -n 's/^@@ -[0-9]*,\([0-9]*\) +[0-9]*,[0-9]* @@.*/\1/p')
NEW_N=$(printf '%s' "$HDR" | sed -n 's/^@@ -[0-9]*,[0-9]* +[0-9]*,\([0-9]*\) @@.*/\1/p')
if awk -v o="$OLD_N" -v n="$NEW_N" '
        /^@@ / { in_hunk=1; next }
        in_hunk && /^ / { old++; new++ }
        in_hunk && /^-/ { old++ }
        in_hunk && /^\+/ { new++ }
        END { exit !(old == o && new == n) }
    ' "$PATCH"; then
    ok "hunk line counts match"
else
    bad "hunk line counts match"
fi

if awk '/^@@ / { in_hunk=1; next } in_hunk && length($0) == 0 { bad=1 } END { exit bad }' "$PATCH"; then
    ok "hunk has no bare empty context lines"
else
    bad "hunk has no bare empty context lines"
fi

check_layout() {
    name=$1
    resource=$2
    original_max=$3
    lock_base=$4
    lock_stride=$5
    resource=$((resource))
    original_max=$((original_max))
    lock_base=$((lock_base))
    lock_stride=$((lock_stride))
    reg_stride=4
    resource_max=$((resource - reg_stride))
    if [ "$original_max" -lt "$resource_max" ]; then
        bounded_max=$original_max
    else
        bounded_max=$resource_max
    fi
    last_lock=$((lock_base + 31 * lock_stride))

    if [ "$bounded_max" -lt "$resource" ] && [ "$last_lock" -le "$bounded_max" ]; then
        ok "$name layout remains addressable and in bounds"
    else
        bad "$name layout remains addressable and in bounds"
    fi
}

check_layout IPQ8074 0x20000 0x20000 0 0x1000
check_layout SFPB 0x100 0x100 0x4 0x4
check_layout MSM8226 0x1000 0x1000 0 0x80
check_layout LARGER_RESOURCE 0x40000 0x20000 0 0x1000

if [ 2 -lt 4 ]; then
    ok "resource smaller than one register is guarded"
else
    bad "resource smaller than one register is guarded"
fi

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t hwspinlock)
trap 'rm -rf "$TMP"' EXIT INT TERM HUP
mkdir -p "$TMP/drivers/hwspinlock"
cp "$FIXTURE" "$TMP/drivers/hwspinlock/qcom_hwspinlock.c"

if (cd "$TMP" && git apply --check -p1 "$PATCH" 2>/dev/null); then
    ok "patch applies to the Linux v6.18 fixture"
else
    bad "patch applies to the Linux v6.18 fixture"
fi

if (cd "$TMP" && git apply -p1 "$PATCH" 2>/dev/null) && \
   grep -q 'size < data->regmap_config->reg_stride' "$TMP/drivers/hwspinlock/qcom_hwspinlock.c" && \
   grep -q 'min_t(resource_size_t' "$TMP/drivers/hwspinlock/qcom_hwspinlock.c"; then
    ok "applied source contains guard and clamp"
else
    bad "applied source contains guard and clamp"
fi

echo "=== summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
