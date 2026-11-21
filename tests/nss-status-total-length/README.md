# NSS Status Total-Length Regression

This is a narrow defensive host regression for DRV056. It replays the relevant
locked B12 source blobs, compiles the complete status-dispatch function and real
common-header length helper, and observes dispatch. It does not prepare/build
OpenWrt, run firmware, contact a router, or retire any published resource.

```sh
python3 -B tests/nss-status-total-length/run.py \
  --upstream /absolute/local/drv-git-object-store \
  --output /absolute/new-evidence-directory --cc clang
```

The source baseline is `8e73e59a440e80f5475d1147aca909f9459ba77f`, vendor pin
`6aa14c78e097b29c493ff2fef87e4d35906b2b5a`. The recipe's abbreviated pin must
resolve to that exact object. Existing patches must match their B12 blobs;
only the new 056 patch and release 30 to 31 are allowed. The selected old
core postimage must match the separately reviewed SHA256. The candidate may
change only the payload-length condition to the declared total-length check.

The complete common header, enums, interface macros, length helper, table
classifier and dispatch function are extracted without rewriting their bodies.
The LP64 fixture substitutes skb APIs, callback registration and a table-entry
observer. It is not the kernel skb implementation or a protocol-body parser.

## Verified Range

The saved local run is
`/Volumes/FX-MD87/Review-AX6/audits/20261121/core-repair-wave1/nss-rx-r31-v3/`.
It compiled cleanly with Apple Clang and `-Wall -Wextra -Werror`:

- 22 candidate scenarios passed.
- B12 passed 18 controls and failed four specified dispatch-count assertions:
  one byte short, payload-only length, short page-backed packet and maximum
  u16 payload with total one byte short.
- Five compiled source mutations failed their exact runtime assertion. A
  compile error, crash, unrelated marker or wrong exit cannot count as rejection.
- Exact-fit and zero-payload transport frames, header availability, first-page
  offset/remaining range with zero linear head, version/interface, alignment, absent callback,
  ordinary cross-core routing and table cross-core/contiguous rejection are
  checked. Zero payload passing transport does not establish any message type
  permits a header-only response.
- A padded linear packet has one extra active byte (not merely spare capacity)
  and is accepted with its original context and app_data. Requiring equality
  instead of an upper bound must fail this positive. Requiring a linear header
  before selecting a page must fail the page positive.

`sg-residual` intentionally shows aggregate total length can be valid while
the first contiguous range contains only the common header. The sink reads
only that header. Its PASS is a transport behavior observation, **not** safe
body access or a whole-message memory-safety result. Do not turn it into a
requirement to discard all segmented firmware messages without compatibility
evidence.

INPUTS.json, commands.jsonl, complete old/new source blobs, generated C and
RESULT.json preserve the provenance and results. The first run in the sibling
`nss-rx-r31/` stopped before replay because the test initially expected a full
pin in the recipe, which actually uses a seven-character pin. It remains failed
evidence; v2 verifies exact Git resolution instead of weakening pin identity.
v2's 21/3 run is superseded for coverage: independent review found no T<N
positive and its page model incorrectly retained a nonzero linear head. v3
adds those exact positive and mutation controls; production 056 is unchanged.

No sanitizer execution, native Linux/target build, true page/frag_list assembly,
descriptor ownership, handler minimum/count bounds, callback drain, FW/DMA
retirement, device operation or performance acceptance is claimed here.
