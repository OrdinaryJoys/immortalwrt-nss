# QCOM MIB width qualification

DP012 changes only the MIB load width in qcom_get_eth_stats, from u32 to
u64. The paired SSDK fal_mib_counter_t consists of accumulated u64 fields.
The IPQ807x/IPQ60xx Makefile selects this QCOM HAL, including EDMA v1.
The XGMAC correction in DP011 did not cover this separate QCOM getter.

The test extracts byte-preserved complete qcom_get_eth_stats,
qcom_get_strings and qcom_get_strset_count functions, the complete QCOM
string/offset tables, private table and count macros, actual SSDK MIB type,
and public dataplane layouts from fully prepared inputs. It calls these
actual QCOM functions, not the generic HAL substitutes used by the separate
DP statistics test. It covers IPQ807x, IPQ60xx, IPQ95xx, IPQ53xx and IPQ54xx.
The first two have no software-prefix counters; the other three have twenty.
All forty-two MIB counters are checked below/at/above the u32 boundary,
with distinct values, bit63 and values close to UINT64_MAX. Output bounds,
software-prefix alignment and read-error propagation are also checked.

The actual stats count must be 42 for v1 or 62 for v2. Actual returned
32-byte string slots must match every source-table entry in order, with
unique names and preserved zero padding. Each returned name is joined
back to its source-table entry and checked against the payload at that
same index for all seven value patterns. Expected offsets and values come
from the actual tables: this checks internal consistency, not an independent
external specification of counter meaning.

Private count/names must match all three actual private-table entries.
Alternating stats/private/unknown/stats calls check set isolation. Six
unsupported IDs (INT32_MIN, -1, ETH_SS_TEST, the next ID after private,
31, INT32_MAX) must return -EPERM from both functions and leave the entire
output unchanged. Buffers have before/after canaries, and only the count
advertised by the actual function is zero-initialized. Unadvertised slots
must remain untouched; private output is checked at its shorter boundary.
This models a zero-initialized ethtool caller: the actual function copies
name bytes only, and is not claimed to terminate or clear dirty slots.

```sh
python3 -B tests/test-qcom-mib-width.py PREPARED_DP --ssdk PREPARED_SSDK \
  --baseline PRE012 --mutations --cc gcc --output NEW_DIRECTORY
```

Repeat using Clang and --sanitize (ASan and UBSan). Keep -std=gnu11,
-Wall -Wextra -Werror and the existing sign-compare/type-limits exceptions;
no additional warning is disabled. A documented host byte-string strlen
adapter accepts the kernel's u8 tables without changing extracted functions.
Every output directory must be new; every helper is freshly compiled.
The baseline extracts its own complete functions, tables and count macros;
it uses the candidate's public layouts and paired SSDK accumulated type.
Baseline and mutations must fail via the expected contract counters, not
crash or fail to compile. Results separate strings/count, payload and
read-error failures, and require each negative control's intended stage
to fail. Getter controls must still pass the strings/count stage. The
wrong-output-offset mutation is applicable only to the three v2 layouts,
because the v1 software prefix is empty. Other controls check truncation,
last-counter omission and ignored MIB errors in all five layouts.

Nine additional controls cover rotated MIB names, omitted last MIB/private
name, wrong slot stride, short stats count, long private count, successful
unknown count/strings returns and an unknown-set output write. All must
be detected in all five layouts. RESULT.json records actual-function,
table, source-input, generated-helper and binary hashes, compiler identity
and compile commands. Input snapshots are revalidated after execution.

MIB transport, device/netdevice wrappers, logging and Linux ethtool constants
are explicit host substitutes; NR_CPUS is fixed at four. This does
not exercise the actual FAL transport, IRQ-off timing, kernel concurrency,
target code generation or hardware. No counter name, meaning, reset epoch,
cache policy, lock, packet path, offload or performance setting is changed.
Raw last-good, epoch association, drop completeness and real throughput
remain separate open contracts. A clean host test is not runtime PASS.

## Local evidence, 2026-10-21

Commands used for this offline run (these output directories now exist;
choose new directory names for a replay):

```sh
SOURCE=/Volumes/FX-MD87/Review-AX6/worktrees/immortalwrt-nss-pci-ssr-shutdown-20261019
DP=/Volumes/FX-MD87/Review-AX6/audits/20261021/multi-agent-repair/combined/qca-nss-dp
SSDK=/Volumes/FX-MD87/Review-AX6/audits/20261021/multi-agent-repair/bh/chain-prepared/qca-ssdk
BASELINE=/Volumes/FX-MD87/Review-AX6/audits/20261021/historical-repair-quality/prepared/qca-nss-dp
EVIDENCE=/Volumes/FX-MD87/Review-AX6/audits/20261021/multi-agent-round2/qcom-contract
python3 -B "$SOURCE/tests/test-qcom-mib-width.py" "$DP" --ssdk "$SSDK" \
  --baseline "$BASELINE" --mutations --cc gcc-16 --output "$EVIDENCE/gcc-16"
python3 -B "$SOURCE/tests/test-qcom-mib-width.py" "$DP" --ssdk "$SSDK" \
  --baseline "$BASELINE" --mutations --cc clang --sanitize --output "$EVIDENCE/clang-asan"
```

GCC 16.2.0 and Apple Clang 17.0.0 ASan/UBSan each compiled and ran 73
helpers. Per compiler, all five candidate layouts passed 22,755 checks with
zero failures; 68 baseline/negative instances were rejected as expected.
Each actual old baseline still failed exactly 168 payload checks and
passed strings/count and read-error checks. All nine new string/count
mutations failed their intended stage in all five layouts. Compile and
runtime stderr files were empty, including the sanitizer run.

Confirmed scope: the previous test coverage gap is closed under the stated
host models; no new production defect was established. Conditional risk:
string padding depends on caller zero-initialization, and shared source
tables are the consistency oracle rather than an independent semantic ABI.
Unverified: target compilation, actual kernel/FAL behavior, concurrency,
hardware and performance. This run is not an independent multi-agent review
or a whole-device qualification, and changes no production getter or patch.
