# Checked journal temporary ownership

Run `tests/test-rpcd-journal-publication.py PREPARED --baseline R8 --mutations
--output NEW`. Add `--sanitize --cc /usr/bin/clang` for ASan/UBSan.

The fixture executes the complete prepared writer, formatter, timestamp,
clear and storage-initialization functions with real isolated host files.
Existing regular temporaries, symlinks, hardlinks to unrelated files or the old
journal, dangling links, directories and FIFO paths must remain untouched.
For normal creation the mode and FD_CLOEXEC are checked; old journal contents
must survive rejected publication. Partial writes and I/O/close/rename/cleanup
faults are bounded wrappers. The old blocking FIFO open is intercepted before
the system call, so this is a contract failure, not a reproduced live hang.

Only temporaries created by this writer may reach its existing cleanup path.
Pre-existing residue is retained and causes a blocked/uncertain result. This
intentionally favors preservation over automatic recovery. There is no new
authorization to remove stale files, and checked remains disabled by default.

Real pathname races after creation, directory anchoring, atomicity on every
filesystem, directory/snapshot durability, power loss, daemon execution,
target compilation and AX6 runtime are not qualified by this test.
