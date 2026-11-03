# SSDK I2C IO Result And Local Reference Contract

This tests the complete prepared `src/init/ssdk_phy_i2c.c`, not rewritten
function bodies. The real PHY-I2C header and error enum are compiled unchanged;
the two hsl_phy constants are copied from exact complete prepared headers.
Linux adapter, reference, segment-lock and transfer leaves are observable
substitutes. They are not a kernel implementation or physical I2C certification.
The log leaf records calls; exported symbol declarations are preprocessing only.

The fixed baseline is all692 files from CodeLinaro SSDK d9a1964 plus the37
previously reviewed patches. The new050 is checked by full hash, declared hunk
context, exact GNU application/reversal and all692 resulting files. It changes
only the I2C C file. The runner never learns an expected input hash from its
test input. Extra source files, symlinks or unclassified metadata reject.

Profile data compiles the original conditional PHY path OFF and has12 fixed
cases/eight precise source controls. Profile phy enables IN_PHY_I2C_MODE and
has20 cases/fifteen controls. Together they require32 positives,23 source
negatives and six separately classified old-source witnesses. Every negative
must compile cleanly, exit86, have empty stdout and exactly its assigned marker.
Compiler failure, arbitrary nonzero, crash, timeout or sanitizer output is not
a semantic negative. Each invocation gets fresh state, and all raw C, headers,
executables, command/exit/stdout/stderr records and input hashes are retained.

The models enforce a held adapter reference and a caller-held segment lock at
the actual __i2c_transfer leaf. They test complete, zero/partial, first and
midstream failed transfers; preserve byte/register framing and eight-byte
chunks; cover lengths around32768 and65536, zero and NULL inputs, missing
outer/inner lookups, C22/C45, MMD1/3/7 policy and signed backend status.
Reads start with poison, not the expected result. A directed whole-source
wrong-recipient mutant must fail the caller's actual output check; complete
transfer counts alone are insufficient. Each case checks local references and
lock balance. Failed operations can have
completed earlier chunks; no data/hardware rollback or output atomicity claim
follows. The MMD scalar output is only published after complete transfer.

Sanitized runs compile the same whole unit with ASan/UBSan and execute separate
positive-instrumentation canaries. Both runtimes receive the same explicit
exit policy for each invocation, with97/98 distinguished by actual diagnostics.
LeakSanitizer is not enabled or claimed. Python-O still checks every obligation.
`RESULTS.json` is explicitly excluded from its own generated-file inventory;
all other generated files are hashed at emission or immediately after compiler
completion and strictly compared at the tail, not learned from the final tree.
Known, missing, changed and extra actual-file controls test that exact gate.
End-of-run source/support hashes recheck
input stability; this is not an atomic lock against arbitrary external writers.

The four outer API signatures, public header, conditional split, default bus0,
address encoding and MMD frames are unchanged. The __ APIs still require a
caller-held lock and do not recursively call i2c_transfer or acquire a new lock.
050 returns existing SDK status categories, not arbitrary Linux errno, upwards.

Still OPEN: HSL cross-operation adapter identity/lease and failed-lock admission,
SFP scalar/sentinel error publication, provider hot removal, adapter registration
and QCOM MDIO devres ownership, UK/SD/PHY reader retirement and root rollback.
Repeated bus-number lookup still assumes a stable provider during the operation;
the native model does not prove that assumption for hot replacement. No target
toolchain, kernel ABI, hardware, live router or throughput approval is implied.
An active AX6 failure requires actual selected build flags, DTS and caller
evidence. In particular CONFIG_MDIO_I2C is a different allocator path; its OFF
state does not prove SSDK SFP/data-I2C calls are absent. No performance knobs,
pins or bus speed change.

Primary contracts: Linux v6.18.38 `drivers/i2c/i2c-core-base.c` and
`include/linux/i2c.h`: transfer results are message counts, __ transfers are
unlocked, and a successful i2c_get_adapter owns both module/device references.
The exact upstream source is authoritative; the divergent openwrt mirror is
comparison evidence, not a safe whole-tree upgrade or vendor endorsement.
