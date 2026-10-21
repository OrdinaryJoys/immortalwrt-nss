# Checked journal exclusive creation (rpcd021 / r9)

Actual r8 writer execution on isolated host symlinks and hardlinks overwrites
unrelated files yet returns success. Directory validation from020 cannot
certify a fixed temporary filename. This is a conditional checked-mode flaw,
not an observed stock-router compromise, throughput cause or current outage.

021 changes only the temporary open flags: O_CREAT/O_EXCL/O_NOFOLLOW/O_CLOEXEC
replace O_TRUNC. A pre-existing entry is never reused or deleted after open
fails. On a new entry, the original write/fsync/close/rename sequence is retained.
Legal fresh and replacement publication behavior is unchanged; checked stays
OFF and no driver, firmware, feed or performance configuration is changed.

The new tests execute complete prepared functions. GCC16 and Clang ASan/UBSan
each pass 60 scenarios / 570 checks; actual r8 fails123 assertions (including
close-on-exec hygiene checks), and four compiled wrong variants are rejected.
O_NOFOLLOW alone is deliberately rejected because it cannot prevent hardlink
reuse. Normal behavior signatures remain equal.

Important availability boundary: crash residue now blocks checked publication
instead of being automatically overwritten. It is preserved for an explicitly
authorized recovery policy. This does not implement such recovery. Root-path
replacement, races after creation, directory fsync, persistent snapshots,
power-loss/flash wear, the frontend and new target/runtime acceptance remain
OPEN. r7/r8 functionality is separately regression-tested on the final input.
