# QCOM MIB width qualification

DP012 changes only the MIB load width in qcom_get_eth_stats, from u32 to
u64. The paired SSDK fal_mib_counter_t consists of accumulated u64 fields.
The IPQ807x/IPQ60xx Makefile selects this QCOM HAL, including EDMA v1.
The XGMAC correction in DP011 did not cover this separate QCOM getter.

The test extracts the complete getter, complete QCOM string/offset tables,
actual SSDK MIB type, and public dataplane layouts from fully prepared
inputs. It covers IPQ807x, IPQ60xx, IPQ95xx, IPQ53xx and IPQ54xx. The first
two have no software-prefix counters; the other three have twenty.
All forty-two MIB counters are checked below/at/above the u32 boundary,
with distinct values, bit63 and values close to UINT64_MAX. Output bounds,
software-prefix alignment and read-error propagation are also checked.

```sh
python3 -B tests/test-qcom-mib-width.py PREPARED_DP --ssdk PREPARED_SSDK \
  --baseline PRE012 --mutations --cc gcc --output NEW_DIRECTORY
```

Repeat using Clang and --sanitize. Every output directory must be new;
every helper is freshly compiled. Baseline and mutations must fail via
the expected contract counters, not crash or fail to compile. The
wrong-output-offset mutation is applicable only to the three v2 layouts,
because the v1 software prefix is empty. Other controls check truncation,
last-counter omission and ignored MIB errors in all five layouts.

MIB transport and the device wrapper are explicit substitutes. This does
not exercise the actual FAL transport, IRQ-off timing, kernel concurrency,
target code generation or hardware. No counter name, meaning, reset epoch,
cache policy, lock, packet path, offload or performance setting is changed.
Raw last-good, epoch association, drop completeness and real throughput
remain separate open contracts. A clean host test is not runtime PASS.
