# Extra-pbuf sysctl failure propagation

DRV024 only fixes the two sysctl boundary handlers. NSS_TX_FAILURE is
positive; returning it as a proc-handler result exposes a positive byte
count rather than a negative error. The handlers also printed the
successful-addition message after a failed request.

After the existing allocated-byte readback, unsuccessful NSS configuration
now returns -EIO and prints a failure message. The success message and zero
result are reserved for NSS_TX_SUCCESS. Parser errors, reads, invalid
values and the existing allocation guard retain their behavior.

```sh
python3 -B tests/test-nss-n2h-sysctl-errors.py FINAL_PREPARED_DRIVER \
  --baseline PRE024 --mutations --cc gcc --output NEW_DIRECTORY
```

Repeat with Clang and --sanitize. Complete actual handlers, actual NSS
status/core enums and the actual size limit are extracted. Both cores,
three valid sizes, zero/partial allocated-byte readbacks, parser/read/limit
and one-shot exits are checked. All exported non-success enum values are
tested defensively, but the current pool helper collapses its failures to
NSS_TX_FAILURE; they are not eleven observed firmware failure modes.
Four compiled negative controls must fail contract checks, not compilation
or sanitizers. Unchanged success/rejection behavior has an identical
signature against the actual old source.

The parser, NSS outcome, device wrapper and logging are explicit models.
This is not a kernel VFS, NSS allocator, DMA, concurrency or FW test.
No allocation, mapping, ACK/completion, timeout, pool size or performance
parameter is changed. Partial accepted buffers are not rolled back or
retried. The shared static-message/ledger ownership bug remains OPEN.

Primary cross-check: Linux v6.18 fs/proc/proc_sysctl.c,
proc_sys_call_handler returns a nonzero handler result as ssize_t; the
full byte count is used only after a zero result. The code is available at
https://github.com/torvalds/linux/blob/v6.18/fs/proc/proc_sysctl.c .
