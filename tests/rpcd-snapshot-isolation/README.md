# rpcd snapshot isolation regression

This ucode fixture writes only synthetic `auditfixture` and `auditfixture2`
packages, but it MUST NOT run on a router, the host, or an existing system.
It refuses to start without both an explicitly marked kernel command line and
a disposable guest launcher's isolation sentinel. These checks are accidental
execution guards, not a security boundary against a malicious launcher.

Required environment:

- A newly assembled RAM-only initramfs guest; no NICs, disks or host shares.
- Kernel command line `ax6_rpcd_ram_fixture=1` and loopback as the only interface.
- Launcher confirms no block devices, then writes `/run/audit/isolation` with
  exactly `network=0 storage=0 shares=0` followed by a newline.
- Stock ubus/UCI libraries, a separate ubus socket `/run/audit/ubus.sock`, and
  the actual prepared rpcd daemon under test. Never redirect to a real ubus.
- `/mode` selects `OFF`, `ON`, or the intentionally defective `baseline`.
- `/var/run/rpcd`, `/tmp/.uci`, `/etc/config` exist in guest RAM. Initially no
  `/etc/rpcd` parent exists. No pre-existing configuration is imported.
- A guest-only fault interposer reads `/run/audit/fault`: `mkdir` rejects
  snapshot mkdir, `copy` rejects snapshot fopen, `commit` fails uci_commit,
  `restore` rejects copying a saved file into `/etc/config`. Clearing the
  control file removes the fault. Production rpcd is not modified for injection.

Run with guest ucode only after these launch checks. A successful fixture emits
`DAEMON_RESULT=` JSON: legacy OFF 27 checks, ON 29 checks, or one negative
baseline witness. The launcher must separately require `GUEST_TEST_EXIT=0` and
retain daemon logs, daemon/library hashes, compiler options, kernel/initramfs
hashes, launcher source and fault interposer source. No firmware build or router
command is required or authorized by this test.

The assertions exercise real apply/confirm/rollback/timeout via ubus, complete
snapshot creation before commit, pending owner exclusion, and failed/missing
rollback snapshot retention and retry. Empty legacy apply preserves upstream
`UBUS_STATUS_NO_DATA` (5) without an armed owner. ON exercises separate checked snapshots;
it does not qualify recover, durable media, daemon restart, boot or flash wear.

The first independent run and fault interposer source are preserved outside
the repository at `/Volumes/FX-MD87/Review-AX6/audits/20261019/structural-repair/`.
That local evidence is not a portable CI harness. Current CI host fixtures do
not replace this daemon test; enabling automated VM qualification remains open.
