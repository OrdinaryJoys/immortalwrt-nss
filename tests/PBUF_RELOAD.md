# PBUF reload/restart status

reload must stop when start fails, preserve its exact status, and not attempt
reload_wifi. When start succeeds it still returns the optional Wi-Fi step's
status. restart delegates to the same wrapper. No PBUF values, readiness,
one-shot allocation, CPU policy or Wi-Fi behavior is otherwise changed.

The test extracts the complete actual wrappers, never sources the init file,
and substitutes status/call-count functions for start and reload_wifi. It
checks two entry points, four start statuses and three Wi-Fi statuses, with
an actual old-source baseline and five executed-shell negative controls.
Use a fresh output directory for every interpreter:

```sh
python3 -B tests/test-qca-nss-pbuf-reload.py --baseline OLD_INIT \
  --mutations --shell /bin/sh --output NEW_DIRECTORY
```

Repeat with host Bash and available BusyBox ash. These are wrapper contracts,
not rc.common/procd, sysctl, readiness, actual firmware or Wi-Fi tests.
In particular, start's existing successful not-ready skip is unchanged.
