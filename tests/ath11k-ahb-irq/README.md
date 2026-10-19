# AHB IRQ and probe ownership fixture

The provider companion `test-ath11k-ahb-providers.py` extracts the actual
remoteproc getter, MSI setup, MSI profile selector/table, probe, finalizer and
free-resources functions, plus the AHB private structure. It separately
models reference/DMA/IRQ/core APIs and a last workqueue user. It covers
native IPQ8074 and hybrid WCN6750/QCN6122 setup failures, each native IRQ
failure, every hybrid MSI IRQ lookup, failed/zero/wide DMA addresses, normal
release and repeated independent lifetimes. Wide-address cases check the
source contract, not an assertion that this 32-bit DMA mask permits them.

`--baseline` must be the pre-947 prepared tree (already containing943-946).
`--mutations` rejects missing/early put, early unmap, zero-address ownership,
failed-map publication and missing probe/normal finalizers by executed
assertions. ASan/UBSan diagnostics are rejected separately, never counted as
an expected negative. The runner poisons base fields at modeled core_free;
this is not real kernel allocation, MSI/IOMMU, workqueue scheduling or a full
QMI/remove test. The existing IRQ fixture keeps provider APIs as stubs and
rejects releasing an unacquired provider; that scope is not expanded by its
own passing count. Default build/source locks remain frozen until separately
authorized target qualification.

The runner inserts actual prepared AHB functions and the actual IPQ8074 ring
mask, MAC mapping, IRQ names and constants. Host callbacks track ownership;
they do not implement or validate Linux IRQ/NAPI/tasklet/remoteproc scheduling.

Pass a package-prepared backports tree to `tests/test-ath11k-ahb-irq-errors.py`.
Use a fresh `--output` directory. `--baseline` is optional and must identify the
pre-943/944/945 prepared tree; it is an intentionally failing negative control,
not a compiler failure. `--sanitize` enables host ASan/UBSan and separately
rejects sanitizer diagnostics, including for a failing negative control.

Candidate checks cover native AHB NSS on/off, CE skip masks, each IRQ lookup,
request and NAPI allocation failure, IRQ0, exact ownership release, probe
ordering/error unwinds and fixed-memory node/IOMMU cleanup. Core/QMI side
effects and PCIC delegation are substitutes; do not call this full recovery,
hybrid MSI or multi-platform target qualification. The early probe tests stub
firmware allocation separately from the actual firmware init/deinit fixture.

The compiler retains the actual signed/unsigned loops with host sign-compare
warnings disabled, as well as unused callback substitutes. Other warnings are
errors. Prepared source hashes and byte-preserved extraction identities are
stored in RESULT.json; baseline/candidate counts differ by six extra repeated
native cleanup assertions, enabled only for the new ownership helper.

References: Linux commits 8ab38bbac02298e3fb03008ed4a0227485c0fd62 and
0e120ee0822b7cc650bd7b29682a34e137cec10d. IRQ-before-core ordering and the
additional lookup/sentinel guards are local adaptations, not claims that those
changes were reviewed by the upstream commit reviewers.
