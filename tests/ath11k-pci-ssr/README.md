# PCI/MHI Shutdown Regression

The runner extracts the complete `ath11k_mhi_op_status_cb()` and
`ath11k_pci_shutdown()` definitions from a prepared mac80211 tree. It does
not substitute a rewritten shutdown algorithm.

The fixture substitutes Linux workqueue, MHI, DMA and spinlock APIs. A
pthread mutex represents the shared admission lock. Condition variables
pause the callback between its unregistering check and queue operation;
shutdown either blocks on the lock or finishes first. This distinguishes
an actual late queue in the model from a missing-source-token assertion.
Pending and running reset/dump work are tested separately. The workqueue
model waits for a running work marker, but does not execute real kernel
work or MHI DMA teardown.

```sh
python3 tests/test-ath11k-pci-ssr.py /path/to/prepared/backports \
  --baseline /path/to/previous/backports --mutations --sanitize \
  --cc clang --output /path/to/new/evidence
```

Use `--cc gcc` for the ordinary GCC run. `--thread-sanitize` is an
alternative to `--sanitize`; the recorded Clang ThreadSanitizer result
checks this userspace fixture, not Linux driver concurrency.

Every variant must compile with `-Werror`. Sanitizer reports, crashes and
timeouts are not accepted as negative-control successes. Six mutations
must fail resource/ordering checks. Normal MHI callback signatures must
match the baseline and all mutations.

This test qualifies only the upstream PCI/MHI shutdown backport. It does
not qualify AHB, hybrid wake CE, debugfs admission, PCI remove/QMI_FAIL,
timer rearming, full recovery, firmware, hardware reboot or throughput.
