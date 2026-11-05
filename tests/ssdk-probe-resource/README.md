# SSDK40 Probe Resource Boundary

This suite compiles the complete probe extracted from the actual prepared
SSDK source, not a replacement implementation. The frozen SSDK39 prefix and
SSDK40 file hashes differ only in this function. The fixture models allocation,
publication, populate results and dynamic OF reference ownership. It detects a
missing private allocation at the call boundary before a host null-member
address is formed. It does not execute undefined behavior as a passing test.

The actual AX6 kernel has CONFIG_OF_DYNAMIC disabled. Reference pairing here is
a cross-configuration contract, not proof of an active AX6 reference leak.
Missing device_id retains the existing zero default; ID admission and child
population rollback are deliberately not changed by this patch.

Each compiler run requires twelve positive cases, seven precise source-mutant
failures and three old-source witnesses. A compiler failure, signal, sanitizer
failure, timeout, extra output or wrong diagnostic does not qualify a mutant.
The native kernel adapters are serial models, not OF/devres concurrency or
target ABI proof. ASan/UBSan activation is independently required by the
unchanged SSDK39 parent gate before this suite grants host qualification.

This patch is not a complete shared UK/SD/PHY root transaction. The module once
latch, acquired root prefix, publication ordering, borrowed providers, reader
retirement and void module exit remain open. No hot-path lock, performance
switch, device reload or root cleanup guess is introduced here.
