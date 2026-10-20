# Checked storage setup contract (rpcd020 / r8)

The old initializer treated mkdir EEXIST as success without checking the
object. A file, symlink or writable/public snapshot directory could therefore
be accepted. Actual complete old functions fail 38 assertions on isolated host
paths in the initializer-only test; the final whole-init suite finds 49. This
is not evidence of an observed AX6 compromise or network outage.

020 validates each existing/new directory using a non-following directory open,
fstat owner/type/mode checks, and checked close. The root may be publicly
readable/searchable but not group/world writable; snapshots must be private.
Trailing slashes are removed locally so O_NOFOLLOW applies to the intended
final component. Any uncertain result blocks checked writes; existing objects
are not removed or permissions rewritten. Previous blocked state stays blocked.
The API initializer also skips journal loading after a storage failure; setting
the blocked flag alone would still allow pathname-based journal access.

GCC16 and Clang ASan/UBSan each pass 57 scenarios / 399 assertions. The actual
r7 initialization chain fails 49; six compiled wrong variants are rejected, with normal
behavior signatures unchanged. Faults/alternate owners and Linux trailing-slash
semantics are models; the underlying host files and descriptor closes are real.

This is only initialization validation. Later pathname replacement, all parent
symlinks, durable snapshots/directories, authorized recover, power loss, flash
wear and the frontend remain OPEN. No NSS/data-plane/performance setting or
rpcd journal loader/writer/format/legacy OFF init behavior is changed. Checked stays
OFF; r8 still requires OpenWrt target and actual runtime qualification.
