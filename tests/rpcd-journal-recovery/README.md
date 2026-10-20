# Checked journal recovery input

This test executes the complete prepared journal loader, numeric validator,
writer, clear, state conversion, identity validation and active-state helpers.
The checked_transaction and state enum are extracted too. Files, rename,
fsync, symlinks and directory handling use an isolated host filesystem. Read,
open, fstat, close and unlink wrappers inject bounded failures; no configuration
file, real daemon, router or mounted target filesystem is accessed.

354 cases / 1830 assertions pass with GCC16 and Clang ASan/UBSan. This includes
the unchanged writer's active-state roundtrips, valid reordered version-1
records, every byte-prefix truncation of a normal record, duplicate/missing
fields, hidden NUL/trailing bytes, numeric boundaries, unknown versions,
symlink/directory/FIFO input, short reads, EINTR and other injected I/O errors.
The FIFO wrapper rejects a blocking open in broken variants before it can hang;
that particular negative observation is an API-contract check, not a real hang.

The r6 baseline fails 224 assertions. Six compilable mutations separately
allow future versions, duplicate fields, hidden NUL, empty numbers, symlink
following or ignored close errors; all are rejected without sanitizer crashes.
Valid ordinary-record results have the same signature in all versions.

The loader keeps malformed evidence and blocks writes, rather than certifying
recovery or deleting it as a terminal journal. It is not a checksum/authentication
format, full transactional snapshot verifier, concurrent writer protocol or
power-loss guarantee. Directory fsync, snapshot durability, reboot/recover
authorization, LuCI and flash write-amplification remain separate open gates.
checked support stays OFF; preserving its real initialization guard is checked
separately, not simulated here as a full OFF daemon test.

Run against a fresh prepared rpcd tree and evidence directory:

```sh
python3 tests/test-rpcd-journal-recovery.py "$RPCD" --baseline "$OLD_RPCD" \
  --mutations --sanitize --output "$EVIDENCE"
```
