# PBUF reload/restart status

reload must stop when start fails, preserve its exact status, and not attempt
reload_wifi. When start succeeds it still returns the optional Wi-Fi step's
status. restart delegates to the same wrapper. No PBUF values, readiness,
one-shot allocation, CPU policy or Wi-Fi behavior is otherwise changed.

The test extracts the supported actual wrappers, never sources the init file,
and substitutes status/call-count functions for start and reload_wifi. It
checks two entry points, four start statuses and three Wi-Fi statuses, with
an actual old-source baseline and five executed-shell negative controls.

Extraction is deliberately fail-closed, not a general shell parser. It accepts
only column-zero `reload() {` / `restart() {` headers, indented body lines,
and an exact column-zero `}` closing line, in that order at the source tail.
Only blank lines may separate or follow these wrappers. Alternate headers,
closing-line redirections, comments or extra commands, missing closers and
duplicate definitions (including `function name` forms) are rejected, not
silently truncated. Other shell syntax is outside this extractor's contract.

Each run also executes 27 extraction controls: three accepted inputs (current
source, old start-body shape, extra blank separators) and 24 rejected inputs
covering both wrapper names and interstitial/trailing commands. Counts and
per-control results are recorded under `extraction_controls` in `RESULT.json`,
separately from the unchanged shell behavior records. The old-body extraction
control is synthetic; `--baseline` separately runs the supplied old-source
wrappers as data-derived fixtures. Extraction controls run even without
`--mutations`; rejected source strings are never executed.

Use a fresh output directory for every interpreter:

```sh
python3 -B tests/test-qca-nss-pbuf-reload.py --baseline OLD_INIT \
  --mutations --shell /bin/sh --output NEW_DIRECTORY
```

Repeat with host Bash and available BusyBox ash. These are wrapper contracts,
not rc.common/procd, sysctl, readiness, actual firmware or Wi-Fi tests.
In particular, start's existing successful not-ready skip is unchanged.
