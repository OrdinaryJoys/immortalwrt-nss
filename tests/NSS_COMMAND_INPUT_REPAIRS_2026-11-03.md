# NSS-A06/A07/A08 bounded leaf repairs

Vendor pins remain driver6aa14c78e097b29c493ff2fef87e4d35906b2b5a and
clients51be82d43ef85079f78aa163d014223b05baa6a2. Only new driver027 and
clients026 patches carry production changes. Parent owns release/CI integration.
No old patch, Makefile, SSDK, build checkout, lock or ref is changed by this task.

A06: Linux6.18 proc_sys_call_handler allocates a private kernel request buffer
and passes it to proc_handler after copy_from_iter_full. Mirror and tunipip6
therefore copy bounded kernel bytes, not copy_from_user. Counts are size_t,
oversized/empty requests reject before allocation and NUL storage is explicit.
Mirror rejects an empty first token before strlen-minus-one. Its int-returning
netdev helper also rejects NULL/empty names with -1 before copy/strlen, leaving
the caller's output pointer/held reference untouched on that early failure.
Existing 15-character IFNAME plus echo-newline behavior is retained. Strict compilation
also exposed the existing unused suffix-length-valid flag: tunipip6 now requires
that actual field before copying its length into a map request. The ordinary
parsed-error return0 behavior is not changed. No remote or unprivileged trigger
is claimed; relevant registered privileged sysctl/module paths are required.

A07: PPE parses a private copy of the current bounded request, never its shared
proc backing array. proc errors are returned; write offsets must be0. Real
create/destroy callers stop on read and preserve parser errors. The actual name
and optional decimal type are parsed with real production string/numeric APIs,
including overflow/trailing-token rejection; no wire/FW parameter value changes.

A08: sequence null/zero/short checks precede size_t subtraction. A terminal
Version marker with no NUL suffix fails version diagnosis without over-read.
An empty NUL-terminated version remains accepted and long version logging stays
bounded. Firmware loader handling of the diagnostic result is untouched: this
does not validate/reject an image, establish FW safety, or prove a device fault.

Verification: fixed vendor/full-tree inputs, exact reverse/forward new patches,
20 actual-function cases,20 directed controls, ordinary GCC plus Clang ASan/
UBSan activation controls, exact stdout/marker/exit/clean compile and end hashes.
Models and safe boundary witnesses are detailed in tests/nss-command-inputs/README.md.
Fixed code inventory excludes only proven prepare metadata, individually bound.
All failures remain in distinct fresh output directories, never upgraded.
