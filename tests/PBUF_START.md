# Complete PBUF Optional-Write Return Chain

The repair retains existing successful skips (no configured governor, missing
CPU0 capability, empty capability list, no stats directory/nodes, and the
existing offload/readiness/profile skips). It does not change PBUF/RPS values,
governor selection, stats default, one-shot allocation, or Wi-Fi policy.

An applicable governor request now rejects unsupported values and preserves
read/CPU/write failures. Missing offline CPU controls remain skips; an existing
control that is not writable fails. The first actual CPU write failure stops
later optional work. Stats discovery must succeed before any writes; its
same-shell loop retains the first failed write while handling remaining known
nodes. `start` short-circuits on either helper's failure, so reload/restart
cannot report success or request Wi-Fi after that error.

```sh
python3 -B tests/test-qca-nss-pbuf-start.py --shell /bin/sh --mutations \
  --baseline OLD_INIT_SOURCE --output NEW_OUTPUT
python3 -B tests/test-qca-nss-pbuf-start.py --shell /bin/bash --mutations \
  --baseline OLD_INIT_SOURCE --output OTHER_NEW_OUTPUT
```

Only the complete named functions are extracted, not the whole init. System
paths are explicitly remapped into isolated directories; the governor writable
predicate is substituted to avoid depending on root/chmod behavior. Configuration,
readiness, enumeration, discovery, NSS/RPS and Wi-Fi are controlled substitutes.
The actual writer runs only on isolated files, wrapped with injected errors;
real redirect-to-directory failures are also checked, without assuming Bash,
Dash and ash assign the same numeric status. PATH is empty and the old baseline's
seq command is explicitly substituted. Normal path order/values, partial
discovery failure, unsupported/empty/missing platforms, first/middle/last write
failure, exact injected error propagation, and no Wi-Fi after failure are checked.

The historical baseline runs only eight selected existing-function scenarios;
it does not use the new writer and is not used to prove injected writer errors.
This baseline already uses `read -r`; it has no attributed escaped-path bug.
Its five observed failing scenarios concern unsupported/read errors, actual
CPU/stats write failures and partial discovery. They are isolated scenario
failures, not five independent live faults. Eleven current-source
runtime negatives cover propagation, discovery, first-error retention, path
reading and preservation of compatible skips.

The extractor is a fail-closed recognizer for current column-zero declarations
and closing braces, not a general shell parser/security sandbox. Body source
and path mappings require review. No production init is sourced, no real sysfs,
debugfs, proc/sys, network or performance command runs. Host Bash entry modes
do not qualify target BusyBox ash, rc.common/procd, hotplug or real policy/device
behavior. Writes across CPU/radio targets remain non-atomic; prior successful
writes and the earlier NSS/PBUF/RPS stage are not rolled back. Write acceptance
is not readback, firmware/performance or complete system recovery proof.
