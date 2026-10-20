# NSS mesh dump ownership

The test executes five byte-preserved prepared functions: MAC allocate/destroy,
mesh path reply processing, and mesh-path/proxy-path dump requests. Eleven list
helpers and seven iteration/declaration macros are extracted unchanged from the
supplied Linux list.h. Dump payload structs come from the pinned NSS driver;
entry structs come from the prepared ath11k header. Other layouts, allocators,
locks, firmware operations and the reply schedule are explicit host contracts.

Six valid NSS/mesh/debug combinations compile with Wall/Wextra/Werror. NSS off
omits the radio's nss member altogether, so an unguarded initialization fails
compilation; that is a compatibility gate, not a successful negative control.
The debug option only changes its macro: these tests do not execute debug_nss.c.

The fixture checks 1/2/3 radio parameter shapes, partial allocation cleanup,
REGISTERED reuse while existing locks are held, and repeated mesh requests with
empty/nonempty old tables, TX failures and payload allocation failures. A reply
can be delivered at the unlock boundary, before the detached old entries are
freed. New entries must remain on the source list. A proxy-path request is an
unchanged sibling-path control, not a test of all proxy-path aging behavior.

120 scenario combinations / 1716 checks pass per compiler. Baseline and six
compiled mutants fail ownership assertions, not compilation or sanitizer errors.
Host payload storage is quarantined until each case ends so a broken list is
observed without intentionally dereferencing freed memory. Failed list-head
invariants stop further traversal in that case; they are not silently repaired.

This is not a Linux spinlock/lockdep test, target ABI test, stress test, complete
mesh protocol or callback-lifetime test. It does not solve simultaneous dump
transaction ordering or validate NSS firmware DMA quiescence. Current AX6 stock
has NSS mesh disabled; no current stock throughput cause is established here.

Example (use fresh output paths):

```sh
python3 tests/test-ath11k-mesh-dump-ownership.py "$BACKPORTS" \
  --driver-prepared "$NSS_DRV" --linux-list-header "$LINUX/include/linux/list.h" \
  --baseline "$OLD_BACKPORTS" --cc gcc --mutations --output "$EVIDENCE/gcc"
```
