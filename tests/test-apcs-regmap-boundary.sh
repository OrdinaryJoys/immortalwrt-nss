#!/bin/sh
# APCS regmap 越界修复 — 静态测试
# ============================================================================
# 依据: AX6_NEXT_PROGRESS_AND_TEST_PLAN_2026-08-03.md §4.2(2)
#   "编写静态测试覆盖 IPQ8074、IPQ6018、SDX55 的 offset/resource/max 关系"
#
# 覆盖:
#   1. 补丁文件存在且格式完整 (hunk 行数一致、无裸空行 — 防 Build #1 复发)
#   2. 补丁内容断言 (resource 边界法、无硬编码 0xffc、保留 SDX55)
#   3. 补丁可对 Linux v6.18 未修补驱动干净应用 (git apply --check + patch --dry-run)
#   4. 应用后驱动仍包含修复逻辑 (grep 断言) 且反向可逆 (apply -R --check)
#   5. 三 SoC offset/resource/max_register 关系矩阵 (不破坏 SDX55, 不越界)
#
# 数据源 (Linux v6.18 主线):
#   drivers/mailbox/qcom-apcs-ipc-mailbox.c  (fixtures/qcom-apcs-ipc-mailbox-v6.18.c)
#   arch/arm64/boot/dts/qcom/ipq8074.dtsi    mailbox@b111000  reg <0x0b111000 0x1000>
#   arch/arm64/boot/dts/qcom/ipq6018.dtsi    mailbox@b111000  reg <0x0 0x0b111000 0x0 0x1000>
#   arch/arm/boot/dts/qcom/qcom-sdx55.dtsi   mailbox@17810000 reg <0x17810000 0x2000>
#   regmap 语义: MMIO 地址 = base + reg (reg 即字节偏移), debugfs 以 reg_stride 步进
#   读到 max_register 为止; 修复后 max_register = resource_size - reg_stride
#
# 返回码: 0 = 全部通过; 1 = 存在失败项

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PATCH="${1:-$REPO_ROOT/target/linux/qualcommax/patches-6.18/1001-mailbox-qcom-apcs-ipc-bound-max_register-by-resource.patch}"
FIXTURE="$SCRIPT_DIR/fixtures/qcom-apcs-ipc-mailbox-v6.18.c"
FIXTURE_SHA256="a1377638524e3422a8000dc3085866e61731e66637490c96adf1a44d3b21ebe9"

PASS=0
FAIL=0

ok()  { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }

SHA_BIN=$(command -v sha256sum || true)
if [ -z "$SHA_BIN" ]; then
    SHA_BIN="shasum -a 256"
else
    SHA_BIN="sha256sum"
fi

echo "=== APCS regmap boundary 静态测试 ==="
echo "patch:   $PATCH"
echo "fixture: $FIXTURE"
echo ""

# ── 1. 文件存在性 ──────────────────────────────────────────────────────────
if [ -f "$PATCH" ]; then ok "补丁文件存在"; else bad "补丁文件存在"; fi
if [ -s "$PATCH" ]; then ok "补丁文件非空"; else bad "补丁文件非空"; fi
if [ -f "$FIXTURE" ]; then ok "v6.18 驱动 fixture 存在"; else bad "v6.18 驱动 fixture 存在"; fi

# ── 2. fixture 完整性 (防篡改) ─────────────────────────────────────────────
ACTUAL_SHA=$($SHA_BIN "$FIXTURE" | awk '{print $1}')
if [ "$ACTUAL_SHA" = "$FIXTURE_SHA256" ]; then
    ok "fixture SHA256 与 v6.18 原始文件一致"
else
    bad "fixture SHA256 不一致 (got $ACTUAL_SHA)"
fi

# ── 3. 补丁内容断言 ────────────────────────────────────────────────────────
grep -q "platform_get_resource(pdev, IORESOURCE_MEM, 0)" "$PATCH" \
    && ok "含 platform_get_resource 资源检查" || bad "含 platform_get_resource 资源检查"
grep -q "regmap_config_local.max_register = resource_size(res)" "$PATCH" \
    && ok "max_register 绑定 resource_size" || bad "max_register 绑定 resource_size"
grep -q "apcs_regmap_config.reg_stride" "$PATCH" \
    && ok "减去 reg_stride (本地副本模板)" || bad "减去 reg_stride (本地副本模板)"
grep -q "regmap_config_local = apcs_regmap_config" "$PATCH" \
    && ok "使用本地 regmap_config 副本 (不污染全局)" || bad "使用本地 regmap_config 副本"
grep -q "devm_regmap_init_mmio(&pdev->dev, base, &regmap_config_local)" "$PATCH" \
    && ok "regmap 初始化使用本地副本" || bad "regmap 初始化使用本地副本"
grep -q "if (!res)" "$PATCH" && grep -q "return -ENODEV;" "$PATCH" \
    && ok "资源缺失时返回 -ENODEV" || bad "资源缺失时返回 -ENODEV"
if grep -qE "max_register[[:space:]]*=[[:space:]]*0xffc|^[+-].*0xffc" "$PATCH"; then
    bad "补丁不得硬编码 0xffc (会破坏 SDX55)"
else
    ok "无硬编码 0xffc (SDX55 0x1008 不受全局缩小影响)"
fi

# ── 4. hunk 行数完整性 (防 Build #1 malformed 复发) ───────────────────────
HDR=$(grep -m1 '^@@ -[0-9]*,[0-9]* +[0-9]*,[0-9]* @@' "$PATCH" || true)
if [ -n "$HDR" ]; then
    OLD_N=$(printf '%s' "$HDR" | sed -n 's/^@@ -[0-9]*,\([0-9]*\) +[0-9]*,[0-9]* @@.*/\1/p')
    NEW_N=$(printf '%s' "$HDR" | sed -n 's/^@@ -[0-9]*,[0-9]* +[0-9]*,\([0-9]*\) @@.*/\1/p')
    if awk -v o="$OLD_N" -v n="$NEW_N" '
            /^@@ / { in_h=1; next }
            in_h && /^ / { c_old++; c_new++ }
            in_h && /^-/ { c_old++ }
            in_h && /^\+/ { c_new++ }
            END { if (c_old == o && c_new == n) exit 0; exit 1 }
        ' "$PATCH"; then
        ok "hunk 行数一致 (旧=$OLD_N 新=$NEW_N)"
    else
        bad "hunk 行数与正文不符 (header 旧=$OLD_N 新=$NEW_N)"
    fi
    # 裸空行检查: hunk 体内不允许 length==0 的行 (空 context 行必须是 " \n")
    if awk '/^@@ / { in_h=1; next } in_h && length($0) == 0 { bad=1 } END { exit bad }' "$PATCH"; then
        ok "hunk 体内无裸空行 (空白 context 行均带空格前缀)"
    else
        bad "hunk 体内存在裸空行 (patch 将 malformed)"
    fi
else
    bad "未找到 hunk 头"
fi

# ── 5. 三 SoC offset/resource/max 关系矩阵 ─────────────────────────────────
# 常量来自 v6.18 驱动 + mainline DTS (见文件头); 断言公式:
#   max_register = resource_size - reg_stride(4)
#   合法: offset <= max_register        (mailbox 读写可达)
#   安全: max_register < resource_size  (debugfs 步进读到 max 不越界)
STRIDE=4
check_soc() {
    SOC=$1; OFF=$2; RES=$3
    MAX=$((RES - STRIDE))
    if [ $((MAX)) -ge $((OFF)) ] && [ $((MAX)) -lt $((RES)) ]; then
        ok "$SOC: offset=0x$(printf '%x' "$((OFF))") resource=0x$(printf '%x' "$((RES))") max=0x$(printf '%x' "$MAX") (offset≤max 且不越界)"
    else
        bad "$SOC: offset=0x$(printf '%x' "$((OFF))") resource=0x$(printf '%x' "$((RES))") max=0x$(printf '%x' "$MAX") 关系不成立"
    fi
}
check_soc "IPQ8074" "0x8"   "0x1000"
check_soc "IPQ6018" "0x8"   "0x1000"
check_soc "SDX55"   "0x1008" "0x2000"

# ── 6. 补丁对 v6.18 驱动可干净应用 + 应用后语义 ────────────────────────────
if [ -f "$FIXTURE" ]; then
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t apcs)
    if [ -n "$TMP" ]; then
        trap 'rm -rf "$TMP"' EXIT INT TERM HUP
        mkdir -p "$TMP/drivers/mailbox"
        cp "$FIXTURE" "$TMP/drivers/mailbox/qcom-apcs-ipc-mailbox.c"
        (
            cd "$TMP" || exit 1
            git init -q
            git -c user.email=test@local -c user.name=test add -A >/dev/null 2>&1
            git -c user.email=test@local -c user.name=test commit -qm "fixture" >/dev/null 2>&1
            if git apply --check -p1 "$PATCH" 2>/dev/null; then
                echo "APPLY_OK"
            else
                echo "APPLY_FAIL"
            fi
            if git apply -p1 "$PATCH" 2>/dev/null && \
               grep -q "regmap_config_local.max_register = resource_size(res)" \
                    drivers/mailbox/qcom-apcs-ipc-mailbox.c && \
               grep -q "platform_get_resource(pdev, IORESOURCE_MEM, 0)" \
                    drivers/mailbox/qcom-apcs-ipc-mailbox.c && \
               grep -q "struct resource \*res;" drivers/mailbox/qcom-apcs-ipc-mailbox.c; then
                echo "SEMANTICS_OK"
            else
                echo "SEMANTICS_FAIL"
            fi
            if git apply --check -R -p1 "$PATCH" 2>/dev/null; then
                echo "REVERSE_OK"
            else
                echo "REVERSE_FAIL"
            fi
            # BSD/GNU patch 双通道校验 (git apply 之外的独立实现)
            rm -f drivers/mailbox/qcom-apcs-ipc-mailbox.c
            cp "$FIXTURE" drivers/mailbox/qcom-apcs-ipc-mailbox.c
            if patch -p1 --dry-run --forward -d "$TMP" < "$PATCH" >/dev/null 2>&1; then
                echo "PATCH_DRYRUN_OK"
            else
                echo "PATCH_DRYRUN_FAIL"
            fi
        ) > "$TMP/result.txt" 2>&1
        R=$(cat "$TMP/result.txt")
        case "$R" in
            *APPLY_OK*)     ok "git apply --check: 补丁对 v6.18 驱动干净应用" ;;
            *APPLY_FAIL*)   bad "git apply --check: 补丁应用失败" ;;
        esac
        case "$R" in
            *SEMANTICS_OK*) ok "应用后驱动含修复逻辑 (resource 检查 + 本地 regmap 副本)" ;;
            *SEMANTICS_FAIL*) bad "应用后驱动缺少修复逻辑" ;;
        esac
        case "$R" in
            *REVERSE_OK*)   ok "git apply --check -R: 反向可逆" ;;
            *REVERSE_FAIL*) bad "git apply --check -R: 反向校验失败" ;;
        esac
        case "$R" in
            *PATCH_DRYRUN_OK*)  ok "patch --dry-run: 独立通道应用通过" ;;
            *PATCH_DRYRUN_FAIL*) bad "patch --dry-run: 应用失败" ;;
        esac
        rm -rf "$TMP"
    else
        bad "无法创建临时目录"
    fi
fi

# ── 汇总 ──────────────────────────────────────────────────────────────────
echo ""
echo "=== 汇总: PASS=$PASS FAIL=$FAIL ==="
if [ "$FAIL" -eq 0 ]; then
    echo "状态: ✓ 全部通过"
    exit 0
else
    echo "状态: ✗ 存在失败项"
    exit 1
fi
