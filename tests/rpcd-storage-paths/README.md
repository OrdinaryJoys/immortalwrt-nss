# Checked storage directory validation

Run `tests/test-rpcd-storage-paths.py PREPARED --baseline OLD --output NEW`
with `--mutations` and optionally `--sanitize --cc /usr/bin/clang`.

The runner extracts the complete prepared API/storage initializers and helper.
It creates real isolated host directories, files, symlinks and FIFOs, checks
unrelated symlink targets for changes, and tracks every opened descriptor.
Owner mismatch and mkdir/open/fstat/close failures are injected. Close faults
close the real descriptor before reporting EINTR; there is no unsafe retry.
UCI allocation and ubus/session registration are boundary stubs. The complete
API initializer is executed with checked ON/OFF, allocation failure and a
journal-call counter; invalid storage must never reach the journal loader.

The open wrapper models Linux trailing-slash resolution by removing final-only
O_NOFOLLOW when the path still ends in a slash. This is explicitly a platform
contract model, not a Linux kernel execution. It prevents macOS behavior or
an unrelated public-directory permission check from hiding the wrong variant.

Parent mode 0755/0750/0711 is allowed if owned by the effective user and not
group/world writable. Snapshot directories must have no group/other access.
Incorrect existing objects are rejected, not chmod/chown/deleted. Normal
fresh/existing directory behavior and a pre-existing blocked state are retained.

This test does not prove resistance to parent-path replacement, persistent
directory/snapshot durability, reboot/power loss, ACLs, a full daemon, OpenWrt
target compilation or router runtime. Checked support remains OFF by default.
