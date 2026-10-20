# Checked recovery input repair (rpcd019 / r7)

This candidate preserves the upstream rpcd pin and checked=OFF default. It
inherits mac80211 r20/953/954 unchanged and does not alter NSS/Wi-Fi settings.

The old journal loader ignored version/created_ms, accepted duplicate keys and
valid prefixes of malformed files, and did not retry short or interrupted reads.
A malformed record claiming confirmed could be removed and no longer block
writes. This was reproduced by executing the whole old loader on isolated host
files; it is not an observed router crash or power-loss event.

019 requires exactly one of every version-1 field, valid IDs/SID, bounded unsigned
numbers and cleanup=0/1. It reads a complete bounded regular file, retries EINTR,
handles short reads, rejects a symlink at the final filename or special files,
and treats close/read/fstat
errors as uncertain. The original file remains and writes remain blocked on
failure. Only fully validated terminal records reach the existing clear helper.
The current writer's normal version-1 records remain compatible. No new journal
format or automatic recovery policy is introduced.
Parent path components are not protected against symlinks by this change.

Local GCC16 and Clang ASan/UBSan each pass 354 cases / 1830 checks. The r6 baseline
has 224 failing assertions; six compiled negative controls are rejected. Tests
use exact prepared functions and host files, with documented syscall faults.
They are not target compilation, a full rpcd daemon or AX6 runtime acceptance.
Clang also checks six complete translation units in each ON/OFF mode against
AArch64-musl headers. This is syntax-only, without objects, linking or execution;
it is not the OpenWrt SDK component qualification.

The future component validator runs this host test only after binding the
prepared source hash during the ON component phase. It retains ON-clean-OFF
target builds and final OFF rootfs/IPK binding; no cloud run is dispatched here.

This closes only strict journal input validation. Snapshot/parent directory
durability, recovery authorization, reboot/power loss, flash write amplification
and LuCI remain open. N03/N04 still require request/instance correlation,
callback lifetime, actual NSS DMA quiescence and parent cleanup together.
No force-free, errno-only or sync-helper shortcut is introduced.
