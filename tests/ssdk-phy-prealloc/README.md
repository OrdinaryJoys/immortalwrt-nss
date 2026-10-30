# PHY metadata preallocation native contract

This is a host allocation/state model, not a kernel, module, target ABI,
hardware, RCU, live-reader, work/IRQ drain, performance or complete root-unwind
qualification. Only current repo Python is imported; historical evidence is
data. Every run creates fresh text-derived source and newly compiled fixtures.

## Inputs and derivation

The fixed21 receipt36900500 and fixed22/r2 receipt669ef006 are checked in full,
including saved/live patch inventory, exact archive pin, all692 raw/output
hashes and current inputs. Current22 is strict. The sole historical exception
requires the complete recipe11 hash after reversing exactly one release12
line. All22 patches are applied by current `edma_patch_context.inspect_patch`
to a fresh archive-derived tree, requiring every declared context/coordinate
and output hash. The last patch must be034/98b5cae6 and change exactly three
files; all692 outputs must also equal21+034. No make or target compiler runs.

`EXTRACTED.json` records complete actual prepare/publish/compatibility,
allocator/free/root and two setup function bodies. SDK metadata layout,
DAC/PHY/chip/feature/interface enums and constants come from real headers.
The complete Linux interface enum in `linux-phy-interface.h` is copied from
the exact primary Linux6.18.38 commit:
https://raw.githubusercontent.com/gregkh/linux/e46dc0adfe39724bcf52cea47b8f9c9aed86a394/include/linux/phy.h
It is the full enum at raw-file one-based114..156, not guessed interface numbers.
The rest of Linux/private/lock/work structs are explicit reduced models.

Actual public prepare/publish/legacy prototypes are extracted from the real
header and compiled against the complete definitions, not handwritten externs.
The baseline fresh initializer and conditional QCA table are complete old21
bodies, identifier-renamed to separate globals/functions and a plain reference
allocator. The reference is compiled freshly, never executed from evidence.
Every successful metadata object is checked byte-for-byte against both an
independent field/zero-payload oracle and this old-source result. The QCA
oracle uses the separate baseline table; mutations affect candidate code only.

## Executed boundary

Four profiles exercise QCA on/off and I2C-layout on/off. The complete actual
root body compiles under HPPE/IN_NETLINK/CONFIG_OF. Topology init/count/exit and
cfg-default are explicit leaves, not actual OF or033 coverage. Root failure
executes its real early error gate. Root success with count1..3 longjmps at
the first DT call; count0 separately longjmps on entry to sysfs after the loop.
Neither case performs DT or sysfs work, nor returns a fully successful root
init. Later resources fail-fast if accidentally reached.

Allocation failure covers every vector/private/metadata attempt for counts0..3.
Zero-size kcalloc is modeled by a unique non-NULL host byte, not the kernel
ZERO_SIZE_PTR address. Root topology errors are not injected or qualified.
Setup bodies are real, but their primitives only initialize modeled embedded
fields. Any real queueing, IRQ request or drain is outside the model. Mid-setup
foreign injection is a deterministic guard test, not a concurrent schedule.

The allocation ledger checks every release, reverse order, ownership identity,
foreign payloads and model shared-ops sentinels. Complete stdout is independently
predicted in Python and compared byte-for-byte; stderr must be empty. Metadata
and private records are independently checked in C before any output. Harness
`MODEL_CLEANUP` releases test owners only; it is not actual normal driver cleanup.
No stale saved ledger is attached to normal exit, and normal driver cleanup is
not claimed safe against foreign replacement by this allocation-only suite.

Directed candidate mutations and two complete old21 function witnesses must
compile cleanly and then return86, empty stdout, and exactly one named stderr
line. Compiler errors, timeout, signals, extra diagnostics and sanitizers never
count as semantic negative success. GCC is ordinary; Clang ASan/UBSan uses
activation canaries97/98. Normal sanitizer runs use exit97 for either runtime,
with actual environment saved per command. detect_leaks=0; LSan is not tested.

## Run

`python3 tests/test-ssdk-phy-prealloc.py --cc gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-phy-prealloc/PHY-TEST-gcc-r1`

`python3 tests/test-ssdk-phy-prealloc.py --cc clang --sanitize --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-phy-prealloc/PHY-TEST-clang-r1`

Each output must be new. Final qualification requires all profiles/controls
and end input/asset/compiler/generated/full-tree stability, not partial PASS
labels. Failed runs remain as evidence; README changes require new binding.

## 2026-10-31 test hardening

The production034, recipe12, original plan and exact22 receipt are unchanged.
The following are host-test changes, not additional target-driver fixes.

- The publish oracle always evaluates allocation through an explicit require,
  not assert. Fresh child interpreters check a literal complete publish trace
  at optimization0/1/2. A freshly generated old-assert variant passes at0 and
  demonstrates the exact missing allocation/free trace at1/2; those two exit86
  controls are separate from C source-mutant counts.
- Every profile/case .expected is bound to the in-memory oracle SHA256 when
  written and checked by the same final generated-file shape/hash gate as C
  and binaries. Controls separately accept unchanged bytes and precisely reject
  modified, truncated, deleted and renamed expected files. Deliberately polluted
  control inputs are evidence, not admitted profile expectations. This is a
  byte-identity snapshot, not an atomic filesystem lock or full output inventory.
- Before adopting globals or reading any private/metadata payload, successful
  root/direct-allocator tests prove vector allocation1 identity/live/kind/size,
  private slot i at allocation2+2*i and metadata slot i at3+2*i, non-NULL,
  distinct identities, exact roles/sizes, and complete coverage of the live
  allocation ledger. Count0 checks only its modeled vector token, no slot read.
  Cleanup is still harness disposal and is not used as transfer proof.
- Seven source mutations (private and published-metadata swap/alias/missing,
  plus vector offset) run through both direct allocation and real early root:
  fourteen directed variants across four profiles,56 new negative occurrences.
  They must fail before payload dereference, with clean compilation and the
  same exact86/empty-stdout/single-marker rule. Two guarded mutations are also
  rerun with only the new owner proof disabled: their old false acceptance is
  checked as a separate eight-occurrence harness counterexample, not a safe
  driver result. New totals are476 positives,122 directed source mutations and
  eight complete old21 witnesses; source control names are not bug counts.

The step1-r1 Python control attempt rejected its own ambiguous mutation locator:
it also matched the control source literal. The locator now includes the exact
whole source line. That rejected attempt is retained and receives no pass credit.
Final qualification uses newly frozen assets and new complete GCC/Clang runs;
old476/74 and development runs are not upgraded to the130-control qualification.

## Development failures

- gcc-r1 stopped at the exact negative gate: the model classified the complete
  old allocator's first kzalloc vector as metadata and rejected ALLOC_SHAPE.
  The model now accepts that legitimate old vector allocation before checking
  its premature global publication; no negative credit was assigned to r1.
- gcc-r2 stopped at strict compilation of the QCA bitmap mutant because its
  zero replacement left the local bitmap written but unused. The directed
  mutant now flips one bit while consuming that variable. No compile-failure
  negative credit was assigned. Both runs used obsolete candidate-r1 inputs
  and are not upgraded to frozen source-r2 qualification.
- The physical slot and inside/outside relation are recorded separately in
  MATRIX.json. Case labels alone are not evidence that a slot is outside count;
  count0 has no inside slot, and count3 has no outside fixed-array slot.
