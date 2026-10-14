# Export runner mode extension

Only the exported runner changed. Its extractor, kernel stubs, C cases, extractor
tests and original README are byte-identical copies of the old frozen assets.
The original README describes the 31-case baseline comparison mode; this file
adds the new mode without editing that frozen README.

`--candidate-only --candidate /actual/make-prepared/tree` runs exactly 26 host
cases: actual IPQ807X candidate C 21 + that same candidate's other-SoC branch 5.
It does not run or claim the original baseline 5. The JSON records mode,
`original_baseline_executed=false`, actual selected inputs, individual input
roles and original source/extracted-definition/generated-C/binary hashes.
Other-SoC cases retain historical case identifiers from the unchanged C asset;
their explicit input role is candidate control, not original baseline evidence.

`--baseline /original/prepared/tree --candidate /actual/prepared/candidate`
retains all 31. `--baseline /original/prepared/tree` retains 5 controls and marks
candidate status `INCOMPLETE_NO_CANDIDATE_EXECUTED`. Candidate-only requires a
candidate and forbids a baseline; a candidate without the explicit mode or a
baseline is an argument error before any output mutation.

CLI regression checks require exact already-prepared inputs:

```sh
DP_HOST_BASELINE=/path/to/baseline DP_HOST_CANDIDATE=/path/to/candidate PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p test_candidate_only_cli.py -v
```

All original host-substitute-only limitations remain. No target kernel build,
Linux concurrency, NSS core removal, registry lifetime or AX6 runtime result is
implied; no network/router/CI/source-worktree action is performed by this export.
