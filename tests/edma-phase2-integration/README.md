# EDMA Phase 2 TX Integration (TESTONLY)

This runner is written before 015 freezes. Do not run it, import it as a test,
or replay WIP 015 until the parent explicitly releases its SHA256. No numeric
MUEDCA protocol, production patch, existing test, lock, release or Git HEAD is
changed by this task.

## Frozen Run

After explicit parent freeze notification only, use a new output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test-edma-phase2-integration.py \
  --upstream-cache /Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-nss-dp \
  --output /Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2/EDMA-INTEGRATION-frozen-r1 \
  --gcc /opt/homebrew/bin/gcc-16 --clang /usr/bin/clang \
  --frozen-015-sha256 PARENT_CONFIRMED_SHA256
```

The placeholder is deliberately not a runnable hash. The runner rejects a
missing/mismatched freeze hash before preparing source or invoking compilers.
Only a fresh `EDMA-INTEGRATION-*` directory immediately under the phase2 audit
root is accepted. A hash does not itself authorize execution: wait for the
parent's notification. Future revisions of 015 require a fresh confirmation.
By default only 001-015 is selected. After the separate OF016 freeze/review,
add --frozen-016-sha256 PARENT_CONFIRMED_016_SHA256 to explicitly unlock 001-016.
An absent option excludes 016 even when it is present. A malformed or
mismatched supplied hash stops before output preparation or compiler calls;
the command-line hash is not itself authorization to run WIP.

## Exact Inputs And Source Contract

The current package recipe must pin
`d8f802f08fd8ff31057ba58edb20bbe448e7b505`. One new Git archive supplies two
full package trees: `before15` replays current 001-014 and `after` replays
current 001-015 or the separately unlocked 001-016. The result records
qualified_through and both confirmed hashes. Later patches are explicitly excluded and recorded by name;
this runner does not certify a later complete candidate. Every full selected
patch is first checked at its declared old AND new coordinates with all
context/counts, then its actual output must equal the independently calculated
bytes. No searching, dropping context or relying solely on patch diagnostics.
This is not a selected-file hunk simulation.
`-V none` explicitly disables ordinary patch backup files (Apple patch can
otherwise retain `.orig` even on successful replay); rejection,
fuzz, offset and unexpected stderr checks remain mandatory.
Raw archive/all-file hashes, each saved patch, replay logs, recipe, runner,
imported repository TX helper and fixture identities are retained. Inputs
are rehashed during replay and after execution so another owner's edit
cannot silently produce a PASS. Final validation also rechecks the complete
selected inventory, both prepared trees, saved patch data and raw Git
archive. No archived program or sealed fixture is
imported/executed; only current source-repository TX and context helpers are imported.
The 014 patch/helper/fixture must also match their accepted Git objects at
`914fa57048d6e543d7aef46c1b0de5d4eb4669dd`; this does not move HEAD. The
package recipe is captured, not edited. The separate OF016
node/device-reference work is not inferred from the TX result; new header
fields outside the explicit allowance stop for review.

The existing TX runner's `extract`, `fixture` and all 16 `mutants` are reused,
not its <=014 `prepare` entry point. The nine real TX/config/wrapper functions
are extracted from each fresh tree and must have identical complete bodies.
All functions in `edma_cfg.c`, including complete ring setup/cleanup callers,
are also saved/hashed and must be identical; the entire file must match.
Actual `.xmit = edma_if_xmit`, poll-to-completion and TX setup/retirement call
expressions are saved and compared with balanced-parenthesis extraction,
including tuple-take calls inside `if (unlikely(...))` conditions. The
complete changed `edma_napi`,
`edma_cleanup` and new `edma_cleanup_locked` caller bodies are saved as data;
they are NOT claimed unchanged, executed or lifecycle-qualified here.

Both fixtures include their own actual IPQ807x architecture, EDMA register
and dataplane headers, with only include directives removed by the existing
extractor. No old handwritten `edma_hw` layout replaces the after015 header.
The current explicit header allowance is `__rcu` on `netdev_arr`, these eight
host-only fields: `napi_dev`, `napi_enabled`, `host_open`,
`override_accounted`, `tx_irqs_owned`, `rxfill_irqs_owned`,
`rxdesc_irqs_owned`, `misc_irq_owned`, plus the architecture's forward netdev
declaration/`edma_retire_port` prototype. All other declaration/macro content
must match after comments/whitespace are ignored. Unexpected final015 header
changes require review, not a broad allow-all refresh. `#define __rcu` erases
only the host annotation; it does NOT model or validate RCU or grace periods.

Replay follow-up: frozen-r5/parent-r1 TX behavior evidence remains scoped and
valid, but their log-only zero-offset assertion was rejected by independent
review. The old 012 hunk needed silent -3 old-line displacement. Parent also
found an inconsistent new-side coordinate in the existing 008 F1 hunk. Only
these headers were maintained; the fresh 80-file prepared tree is byte-equal
to the prior accepted source. New runs use edma_patch_context.py and bind its
identity. Old results must not be cited as having exercised this new gate.

## Host Qualification

For GCC and Clang ASan/UBSan, compile both before15 and final after fixtures
diagnostic-free and require identical successful map/publish/unmap traces.
Run the complete existing TX suite and its 16 semantic mutants against the
final selected source/headers. Also compare successful traces across compilers.
The fixture's existing full tuple/lock/map/owner/length/zero-DMA/cleanup and
deterministic race coverage is retained, with its existing hooks and stubs.

Compile failure/output, timeout, signal, unexpected runtime stderr, sanitizer
error or an unrelated assertion is a harness failure, NOT a successful
negative control. A mutant must exit 86 with exactly its intended single
`EDMA_TX_CONTRACT <marker>` line and no stdout. ASan/UBSan both use exit 97,
distinct from semantic rejection 86: combined runtimes share common exit-code
options, so setting different codes is not portable. Each intentionally faulty
activation canary must emit its own sanitizer diagnostic and exit 97 to
demonstrate both runtimes are active. Canaries are not among the 16 mutants.
Positive runtime stderr must be empty. Raw compiler/runtime stdout/stderr,
commands, versions, executable/generated-source hashes and manifests are
bound into final evidence, including failed attempts.

Passing only qualifies 014 TX tuple behavior under the recorded selected
001-015 or 001-016 source/header layout. This does not execute the global
OF init/final functions or borrow their separate lifecycle acceptance.
The unchanged TX setup fixture assumes PRE-LIVE owner
setup and modeled retirement before cleanup. RX/poll behavior, NAPI/IRQ CPU
lifetime, real RCU, callback drain, FW idle/epoch, DMA stop, hardware/target
ABI, throughput and device behavior remain separate acceptance boundaries.
No make, target/module/firmware build, network, cloud, device or push occurs.
