# rpcd r2 validation boundary

The original 28faf640 source archive and its mirror SHA256 remain pinned.
Patches 010-013 are exact official rpcd commits:

- https://git.openwrt.org/project/rpcd.git/commit/?id=e37ed9d814699098eb7e26c8b33c054840782dfb
- https://git.openwrt.org/project/rpcd.git/commit/?id=4062f666ecd17a03a153a40e76af6904d3eb6a78
- https://git.openwrt.org/project/rpcd.git/commit/?id=a6c6b63b47bd8f4f762ef2e6787210cd3e0fb8a0
- https://git.openwrt.org/project/rpcd.git/commit/?id=d99f703e4035d03fbcfbada3cb697db346c2b984

Patch 014 is a local experimental transaction backend, adapted to upstream's
private session directory names. It also frees a new session if the second
entropy read (public SID) fails. The official d99 baseline leaks that allocation
in the guest fault-injection counterexample; the patched daemon frees it.

`CONFIG_RPCD_CHECKED_UCI_SUPPORT` defaults to disabled. Disabled builds reject
every `uci.checked` command with NOT_SUPPORTED before parsing/mutation. This
does not repair the legacy frontend confirmation protocol. Restart durability,
LuCI/CGI activation and browser acceptance are still incomplete; do not enable
this flag in a firmware intended for deployment.

`provenance.json` binds all 18 prepared source files and all five patch hashes.
Validation must apply patches in a real, independent Git root and compare the
resulting bytes. A zero exit from git apply in an exported non-repository path
can inherit an ancestor repository and skip paths; it is not sufficient proof.

The integration build compiles ON components, archives them, explicitly cleans,
then compiles OFF components and the stock image. Final installed rpcd/plugin
payloads must equal the OFF IPKs. Existing package selections are unchanged:
rpcsys is compile-tested but remains uninstalled when not selected.

Isolated AArch64 daemon tests use original firmware shared libraries with a
different guest kernel, not AX6 hardware. They do not certify NSS/Wi-Fi, real
network throughput, upgrade, reboot or configuration recovery.
