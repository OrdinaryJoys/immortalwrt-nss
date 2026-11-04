# SSDK SD Publication and PHY Retirement Admission

Local candidate based on source `3f6df667e1dcfc1b7412cffca54e454d1d68922c`.
Patch 051 follows the original, byte-preserved 38 patches; qca-ssdk release29.
This candidate is not in accepted cloud run41771617912 or image r0-3f6df66.

## Bounded Contract

- SD callback pointers are borrowed, not owned allocations. `sd_init` checks
  the device/config and all 12 original typed callback slots before any write.
  A different non-NULL provider in an occupied slot returns SW_BUSY without
  filling other empty slots. Equal pointers and NULL contributions retain the
  original compatibility policy; a compatible retry can fill empty slots.
  The read-only sd_init_check also runs before HSL/FAL API-table mutation
  and before root initialization can enter the legacy FAL-error/PHY continuation.
- `ssdk_cleanup` returns the original FAL error before calling PHY cleanup.
  It does not turn failed FAL retirement into permission to free PHY metadata,
  clear device bitmaps or run PHY exit callbacks. Successful/emulation behavior
  remains unchanged. Invalid device cleanup is rejected before global control
  shutdown. Cache/control shutdown preceding a valid FAL call is not rolled back.
- No SD callback is cleared/freed, no UK endpoint is newly claimed, and no
  sleeping lock, packet-processing branch, ring, IRQ or offload option is added.

This is **not** a shared UK/SD/PHY owner coordinator. Initialization still needs
caller serialization and borrowed providers must outlive every reader. It does
not supply concurrent callback publication/retirement, provider module pins,
old-pointer reader leases, an atomic global reservation before FAL table reset, or
late contribution publication through HSL's existing dev_init latch.

`hsl_dev_cleanup_core` can retire its child/config before UK cleanup returns
SW_BUSY. Empty-slot or peer cleanup can still retire the shared UK endpoint.
The fixture deliberately preserves this OPEN result; do not weaken that
observation to claim the whole teardown is repaired. `regi_exit` is void and
can continue to platform/private cleanup after an error. Neither returning
early from a void module exit nor adding a device counter fixes that contract.

## Verification

The runner archives vendor d9a1964 from a local Git object cache, compares all
38 historical patches with actual frozen Git blobs, and replays 39 complete
patches with declared-context checking, fuzz0 and no offsets. It independently
tracks all 692 resulting file hashes and requires only sd.c/ssdk_init.c/hsl_dev.c/sd.h to
differ after 051. It runs no make, target binary, firmware, device or cloud job.

Complete actual functions are extracted byte-for-byte: sd_init, sd_init_check,
ssdk_init, ssdk_cleanup, hsl_dev_init_available, hsl_dev_cleanup_core,
ssdk_phy_driver_cleanup and the HPPE request predicate. Callback signatures,
hsl_reg_func, SDK error/boolean/PHY enums and device capacity come from the real
prepared headers. FAL's dependency bridge, HPPE provider operations, heap/endpoint
services and quiescence observations remain explicit serial stateful models,
not the real FAL/VLAN/HPPE implementation or a kernel lock/RCU proof.
The typed SD providers trap any unexpected invocation during admission;
they are identity sentinels, not empty implementations accepting dispatch.

Each HPPE/non-HPPE profile executes 266 positive scenarios, 20 precise compiled
source mutants and two old-source witnesses. They cover all 12 callback slots,
late-conflict no-publication, null contributions, every SDK error -29..0,
all three devices, emulation, all actual PHY type slots, peer bitmaps, borrowed
ops, child/UK failures, retry and no double retirement. Negative credit requires
clean Werror compilation, exact exit86, empty stdout and a fixed assertion.
Crashes, compile failures and sanitizer diagnostics do not count as negatives.
ASan/UBSan must first activate with separate fixed97/98 canaries; both exitcode
environment controls are bound to the individual probe, including on Darwin.
Activation probes use address-only and undefined-only instrumentation separately:
GCC11 otherwise diagnoses the ASan probe's object-size UB first. Exact detector
diagnostics, disabled-instrumentation and crossed-identity controls are required.
Formal positive/mutant programs retain combined address,undefined instrumentation.
`--canaries-only --sanitize` runs bounded activation controls without SDK prepare
or a formal campaign, suitable for an early Linux/GCC11 preflight.

Example (fresh output directory required):

```sh
python3 -B tests/test-ssdk-retirement-admission.py \
  --upstream-cache /path/to/qca-ssdk-git-cache \
  --output /path/to/fresh-evidence --cc /usr/bin/clang --hppe --sanitize
```

Repeat without `--hppe` for the non-HPPE profile. Existing
`test-ssdk-uk-transport.py` can independently exercise the unchanged actual UK
transport against the new prepared tree. Tests use exceptions, not Python
assert, for admission. Apple Clang/arm64 Mach-O host results are not Linux
GCC11, target module/header compilation, lockdep, device or performance results.

## Upstream Cross-Check

Vendor d9a1964 and live archived OpenWrt SSDK bb4f3f0 have identical whole sd.c
and identical original ssdk_cleanup function. Neither contains these two
admission repairs. Do not replace the pinned vendor tree with the divergent
OpenWrt mirror merely because the mirror has a different HEAD.

Primary references:
- https://git.codelinaro.org/clo/qsdk/oss/lklm/qca-ssdk.git
- https://github.com/openwrt/qca-ssdk/tree/bb4f3f0b947ebfce51c78a8d39f57c7c758521c9
- https://github.com/torvalds/linux/blob/v6.18/drivers/char/misc.c

Cloud integration needs a new, separately reviewed fixed 39-layer contract and
full target qualification after authorization. Do not refresh accepted 38-layer
expectations from this candidate, reuse its old successful image as051 proof,
or close true shared lifecycle/throughput/latency/firmware/DMA questions.
