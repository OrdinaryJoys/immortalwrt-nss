# SSDK41 Cold Platform Resource Ownership

This is a prerequisite layer, not a complete UK/SD/PHY root repair. Patch053
changes only ssdk_plat.c on the frozen complete692-file SSDK40 prefix. It
does not change headers, exported signatures, provider/reader protocols,
NSS/EDMA, clock rates, resets, IRQs, packet steering or performance policies.

The platform transaction privately accumulates UNIPHY/switch/PSGMII mappings,
the PSGMII region identity and successful ESS prepare/enable rights. All
fallible mappings/regions finish BEFORE clock initialization: a mapping
failure must neither invoke nor unwind the opaque void GCC initializer. Mapping
or region failure releases only that invocation's acquired prefix and leaves
the caller configuration/private addresses unchanged. Successful publication
records the actual private owner. Reentry and foreign mapping/instance exit
cannot transfer or erase retirement rights. Repeated normal exit is a no-op.

The zero-argument GCC helpers use module-global clock state. Their invocation
is shared across admitted platform participants and retired after the last
participant, including a failed later participant. This is invocation
ownership, NOT proof that the nested void GCC initializer configured hardware
successfully. ESS failure is observed without claiming an enable right, but
its legacy nonfatal return is retained: adding a new root fatal path before
the root transaction exists would expose unsafe cleanup. First-error
propagation and nested GCC acquisition failures remain open.

Only cold module-root init/exit call these helpers in the locked source. The
new mutex is NOT a provider/reader lock and adds no packet fast-path locking.
The root caller must quiesce its producers/readers before platform exit and
must keep topology/private storage alive through that call. Returning from
this void exit on foreign ownership does not veto module unload; global
root failure/exit and owner-generation/ABA handling remain separate work.

Run locally with fresh output and complete prepared inputs:

```sh
python3 -B tests/test-ssdk-platform-oracles.py
python3 -B tests/test-ssdk-platform-resources.py \
  --baseline40 /absolute/frozen/ssdk40 --prepared /absolute/reviewed/ssdk41 \
  --cc /absolute/host/compiler --sanitize --output /absolute/fresh/output
```

The runner binds the full baseline inventory, reviewed final file hash,
actual patch coordinates and replay output.
The live source package must also retain the exact frozen40-patch prefix,
reviewed053 bytes and release31 recipe; the complete patch directory is
rechecked at the end. No header-only check can substitute for that inventory.
It compiles actual complete
init/exit/release functions, state definitions and real header typedefs.
Nine conditional profiles include HPPE, MP, UNIPHY, DESS and synthetic feature
combinations; they are compiler branch tests, not claims of supported boards.
Typed serial host models record mapping/region/clock identities and rights.
They model harmless NULL iounmap, optional NULL CCF clocks, failed enables,
invalid/empty slots, peer identity, foreign replacement, changed DT metadata,
duplicate exit, failure retry and successful reinitialization. Each invocation
uses its own entry configuration snapshot rather than assuming every retry
starts with the very first configuration's bytes.

Each of1705 positive cases has strict process/JSON admission; ordinary
single-device cases also have independently calculated exact resource counts.
Twenty source mutations must compile cleanly and execute with precisely
exit86, no stdout and the required one-line diagnostic. Compilation failures,
signals, timeout, sanitizer findings or arbitrary nonzero status receive no
negative credit. Four unchanged SSDK40 witnesses are explicitly old-source
host counterexamples, not newly observed router incidents. Pure oracle tests
reject duplicate JSON keys, Boolean counts, wrong diagnostics and pollution.

Sanitized runs execute separately instrumented ASan and UBSan activation
canaries plus disabled/crossed controls; both detectors instrument the formal
campaign. SDK-only tests use the actual qca808x four-field register callback
view and ensure no Linux resource types leak into its no-platform stubs.

Generated full C, compile/run commands, stdout/stderr and692-file replay are
retained. A local PASS does not qualify Linux GCC11, target kernel ABI,
concurrent module load/unload, MMIO, clock/reset hardware, root rollback,
RCU/provider retirement or throughput. Do not refresh fixed hashes from
unreviewed inputs, relax warnings, replace leaves with empty success stubs,
run sealed generated programs, dispatch firmware builds or operate a router
as part of this test.
