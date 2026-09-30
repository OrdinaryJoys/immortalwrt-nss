#!/usr/bin/env python3
"""Run the actual RPS init functions against temporary sysfs/proc fixtures.

IRQ_TEST_SCRIPT selects the source or extracted-rootfs init script.
RPS_TEST_SHELL may be 'sh', '/path/to/bash', or 'busybox ash'. External
cat/logger/sleep/jsonfilter are fixture I/O, never production commands. Only
the global proc read models kernel roundup(65535)=65536; queue files are real
temporary files and all injected values/errors are explicit negative cases.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get('IRQ_TEST_SCRIPT', ROOT / 'target/linux/qualcommax/base-files/etc/init.d/set-irq-affinity')).resolve()
SHELL = shlex.split(os.environ.get('RPS_TEST_SHELL', 'sh'))
if not SCRIPT.is_file() or not SHELL or not shutil.which(SHELL[0]):
    raise SystemExit('FAIL: unavailable IRQ_TEST_SCRIPT or RPS_TEST_SHELL')

CASES = [
    ('complete-event', 'event', 0, ''),
    ('complete-start', 'start', 0, ''),
    ('idempotent-event', 'twice', 0, ''),
    ('padded-bitmap-readback', 'event', 0, 'padded'),
    ('one-rx-mask-write-fails', 'event', 1, 'write-rps'),
    ('one-rx-flow-write-fails', 'event', 1, 'write-flow'),
    ('one-tx-mask-write-fails', 'event', 1, 'write-xps'),
    ('rx-attribute-permission-denied', 'event', 1, 'permission-rps'),
    ('global-attribute-permission-denied', 'event', 1, 'permission-global'),
    ('one-rx-mask-missing', 'event', 1, 'missing-rps'),
    ('one-rx-flow-missing', 'event', 1, 'missing-flow'),
    ('one-tx-mask-missing', 'event', 1, 'missing-xps'),
    ('only-one-rx-policy-completes', 'event', 1, 'one-only'),
    ('missing-expected-device', 'event', 1, 'missing-device'),
    ('device-with-no-rx', 'event', 1, 'no-rx'),
    ('device-with-no-tx', 'event', 1, 'no-tx'),
    ('no-devices', 'event', 1, 'no-devices'),
    ('cpu-mask-readback-clamped', 'event', 1, 'clamped-rps'),
    ('flow-count-readback-clamped', 'event', 1, 'clamped-flow'),
    ('xps-readback-different-bitmap', 'event', 1, 'clamped-xps'),
    ('malformed-cpumap-readback', 'event', 1, 'malformed'),
    ('queue-read-fails', 'event', 1, 'read-fail'),
    ('global-missing', 'event', 1, 'missing-global'),
    ('global-write-fails', 'event', 1, 'write-global'),
    ('global-unrounded-readback', 'event', 1, 'unrounded'),
    ('global-clamped-readback', 'event', 1, 'clamped-global'),
    ('global-read-fails', 'event', 1, 'global-read-fail'),
    ('global-changes-before-final-read', 'event', 1, 'global-second-read'),
    ('device-vanishes-during-apply', 'event', 1, 'vanish-device'),
    ('device-is-recreated-with-new-ifindex', 'event', 1, 'recreate-device'),
    ('queue-vanishes-during-apply', 'event', 1, 'vanish-queue'),
    ('queue-added-during-apply', 'event', 1, 'add-queue'),
    ('earlier-device-reset-while-later-device-applies', 'event', 1, 'late-reset'),
    ('queue-reset-after-global-write', 'event', 1, 'global-reset'),
    ('logger-failure-does-not-hide-success', 'event', 0, 'logger-fail'),
    ('logger-failure-does-not-hide-policy-failure', 'event', 1, 'logger-fail-write'),
    ('startup-retries-incomplete-set-and-recovers', 'start', 0, 'retry-recover'),
    ('startup-exhaustion-remains-failure', 'start', 1, 'retry-exhaust'),
    ('background-failure-is-diagnostic-not-retroactive', 'start', 0, 'wave-fail'),
    ('background-recovery-does-not-erase-initial-failure', 'start', 1, 'wave-recover'),
]
if os.environ.get('RPS_TEST_NEGATIVE_CONTROL') == '1':
    CASES = [case for case in CASES if case[2] == 1]

results = []
for label, entry, expected, mode in CASES:
    with tempfile.TemporaryDirectory(prefix='rps-policy-test-') as tmp:
        base = Path(tmp)
        net = base / 'net'
        binpath = base / 'bin'
        net.mkdir()
        binpath.mkdir()

        def write(path, value, executable=False):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
            if executable:
                path.chmod(0o755)

        def queue(dev, number):
            for kind, attr in [('rx', 'rps_cpus'), ('rx', 'rps_flow_cnt'), ('tx', 'xps_cpus')]:
                write(net / dev / 'queues' / f'{kind}-{number}' / attr, '0\n')

        for number, dev in enumerate(['lan1', 'wan']):
            write(net / dev / 'ifindex', f'{number + 7}\n')
            queue(dev, 0)
            queue(dev, 1)
        board = base / 'board'
        global_file = base / 'rps_sock_flow_entries'
        write(board, 'lan1\nwan\n')
        write(global_file, '0\n')
        write(base / 'cpu', '0-3\n')
        write(base / 'board-detect', '#!/bin/sh\nexit 1\n', True)

        targets = {
            'rps': net / 'lan1/queues/rx-1/rps_cpus',
            'flow': net / 'lan1/queues/rx-1/rps_flow_cnt',
            'xps': net / 'lan1/queues/tx-1/xps_cpus',
            'global': global_file,
        }
        if mode.startswith('missing-') and mode.split('-', 1)[1] in targets:
            targets[mode.split('-', 1)[1]].unlink()
        if mode.startswith('permission-'):
            targets[mode.split('-', 1)[1]].chmod(0o444)
        if mode in ('missing-device', 'wave-recover'):
            shutil.move(str(net / 'wan'), str(base / 'held-wan'))
        if mode in ('no-rx', 'no-tx'):
            kind = mode.split('-', 1)[1]
            for number in range(2):
                shutil.move(str(net / 'wan/queues' / f'{kind}-{number}'), str(base / f'held-{kind}-{number}'))
        if mode == 'no-devices':
            shutil.move(str(net / 'lan1'), str(base / 'held-lan1'))
            shutil.move(str(net / 'wan'), str(base / 'held-wan'))
            write(board, '')
        if mode == 'one-only':
            for dev, number in [('lan1', 1), ('wan', 0), ('wan', 1)]:
                (net / dev / 'queues' / f'rx-{number}' / 'rps_flow_cnt').unlink()
        if mode in ('retry-recover', 'retry-exhaust'):
            targets['flow'].unlink()

        # This wrapper changes readback/objects only beneath TEST_ROOT. Normal
        # attributes still pass through the real cat executable unmodified.
        write(binpath / 'cat', r'''#!/bin/sh
path=${1:-}
if [ "$path" = "$TEST_ROOT/net/lan1/queues/rx-0/rps_cpus" ] && [ ! -e "$TEST_ROOT/changed" ]; then
    case "$TEST_MODE" in
        vanish-device) mv "$TEST_ROOT/net/wan" "$TEST_ROOT/gone-wan" ;;
        recreate-device) printf '99\n' > "$TEST_ROOT/net/lan1/ifindex" ;;
        vanish-queue) mv "$TEST_ROOT/net/lan1/queues/rx-1" "$TEST_ROOT/gone-rx-1" ;;
        add-queue)
            mkdir "$TEST_ROOT/net/lan1/queues/rx-9"
            printf '0\n' > "$TEST_ROOT/net/lan1/queues/rx-9/rps_cpus"
            printf '0\n' > "$TEST_ROOT/net/lan1/queues/rx-9/rps_flow_cnt" ;;
    esac
    : > "$TEST_ROOT/changed"
fi
if [ "$TEST_MODE" = late-reset ] && [ "$path" = "$TEST_ROOT/net/wan/queues/rx-0/rps_cpus" ]; then
    printf '0\n' > "$TEST_ROOT/net/lan1/queues/rx-0/rps_cpus"
fi
case "$TEST_MODE:$path" in
    clamped-rps:*/lan1/queues/rx-1/rps_cpus) printf '7\n'; exit 0 ;;
    clamped-flow:*/lan1/queues/rx-1/rps_flow_cnt) printf '4096\n'; exit 0 ;;
    clamped-xps:*/lan1/queues/tx-1/xps_cpus) printf 'e\n'; exit 0 ;;
    malformed:*/lan1/queues/rx-1/rps_cpus) printf '0,,f\n'; exit 0 ;;
    read-fail:*/lan1/queues/rx-1/rps_cpus) exit 7 ;;
    padded:*/rps_cpus|padded:*/xps_cpus) printf '00000000,0000000f\n'; exit 0 ;;
esac
if [ "$path" = "$TEST_ROOT/rps_sock_flow_entries" ]; then
    case "$TEST_MODE" in
        global-read-fail) exit 8 ;;
        clamped-global) printf '32768\n'; exit 0 ;;
        unrounded) /bin/cat "$@"; exit $? ;;
        global-second-read)
            if [ -e "$TEST_ROOT/global-read" ]; then printf '32768\n'; exit 0; fi
            : > "$TEST_ROOT/global-read" ;;
        global-reset) printf '0\n' > "$TEST_ROOT/net/lan1/queues/rx-0/rps_cpus" ;;
    esac
    actual=$(/bin/cat "$path") || exit $?
    if [ "$actual" = 65535 ]; then
        printf 'read-global:65536\n' >> "$TEST_ROOT/io.log"
        printf '65536\n'
    else printf '%s\n' "$actual"; fi
else
    /bin/cat "$@"
fi
''', True)
        write(binpath / 'jsonfilter', '#!/bin/sh\nwhile [ "$#" -gt 0 ]; do if [ "$1" = -i ]; then /bin/cat "$2"; exit $?; fi; shift; done\nexit 1\n', True)
        write(binpath / 'logger', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_ROOT/logger.log"\ncase "$TEST_MODE" in logger-fail*) exit 9;; esac\n', True)
        write(binpath / 'sleep', r'''#!/bin/sh
printf '%s\n' "$1" >> "$TEST_ROOT/sleeps.log"
case "$TEST_MODE:$1" in
    retry-recover:3) printf '0\n' > "$TEST_ROOT/net/lan1/queues/rx-1/rps_flow_cnt" ;;
    wave-fail:30) mv "$TEST_ROOT/net/wan/queues/tx-1/xps_cpus" "$TEST_ROOT/held-xps" ;;
    wave-recover:30) mv "$TEST_ROOT/held-wan" "$TEST_ROOT/net/wan" ;;
esac
exit 0
''', True)
        write_fail = ''
        if mode.startswith('write-'):
            write_fail = str(targets[mode.split('-', 1)[1]])
        if mode == 'logger-fail-write':
            write_fail = str(targets['flow'])
        if mode.startswith('permission-') and os.geteuid() == 0:
            # Root bypasses ordinary-file DAC. Model the kernel attribute
            # rejecting a write instead; do not claim a real DAC exercise.
            write_fail = str(targets[mode.split('-', 1)[1]])
        env = dict(os.environ, PATH=str(binpath) + os.pathsep + os.environ['PATH'],
                   TEST_ROOT=str(base), TEST_MODE=mode, TEST_WRITE_FAIL=write_fail,
                   IRQ_BOARD_JSON=str(board), IRQ_BOARD_DETECT=str(base / 'board-detect'),
                   IRQ_SYS_CLASS_NET=str(net), IRQ_CPU_ONLINE=str(base / 'cpu'),
                   IRQ_UCI_FUNCTIONS=str(base / 'missing-functions'),
                   IRQ_RPS_SOCK_FLOW_ENTRIES=str(global_file), TMPDIR=str(base))
        calls = {'event': 'start_rps', 'start': 'start', 'twice': 'start_rps && start_rps'}[entry]
        shell_input = r'''
extra_command() { :; }
# Emulate a sysfs write returning failure. 'path' is the actual helper's local
# target; only the data-write printf signature is affected, not diagnostics.
printf() {
    # The old implementation uses i directly; the new writer uses path.
    # Match the data value as well so the old queue-count stdout is untouched.
    case "${2:-}" in
        f|8192|65535)
            if [ -n "$TEST_WRITE_FAIL" ] && [ "${path:-${i:-}}" = "$TEST_WRITE_FAIL" ] && [ "$1" = '%s\n' ]; then
                command printf 'write-denied:%s\n' "$TEST_WRITE_FAIL" >> "$TEST_ROOT/io.log"
                return 13
            fi ;;
    esac
    command printf "$@"
}
''' + '. ' + shlex.quote(str(SCRIPT)) + '\n' + calls + r'''
result=$?
wait
exit "$result"
'''
        run = subprocess.run(SHELL, input=shell_input, env=env, text=True, capture_output=True, timeout=20)
        logs = (base / 'logger.log').read_text() if (base / 'logger.log').exists() else ''
        sleeps = (base / 'sleeps.log').read_text().splitlines() if (base / 'sleeps.log').exists() else []
        ok = (run.returncode == 0) if expected == 0 else (run.returncode != 0)
        diagnostics = []
        if expected and 'RPS' not in logs:
            ok = False
            diagnostics.append('missing policy diagnostic')
        if expected == 0:
            # Confirm the global request remains unchanged, and success came
            # through the explicit 65536 readback contract, not text echo.
            if not global_file.exists() or global_file.read_text().strip() != '65535':
                ok = False
                diagnostics.append('global request changed/not applied')
            if not (base / 'io.log').exists() or 'read-global:65536' not in (base / 'io.log').read_text():
                ok = False
                diagnostics.append('no successful kernel-contract readback')
        if entry == 'start':
            if sleeps.count('30') != 1 or sleeps.count('90') != 1 or sleeps.count('180') != 1 or sleeps.count('300') != 1:
                ok = False
                diagnostics.append('four background reassert delays not preserved')
            if mode == 'retry-recover' and sleeps.count('3') != 1:
                ok = False
                diagnostics.append('partial policy did not retry once then recover')
            if mode in ('retry-exhaust', 'wave-recover') and sleeps.count('3') != 9:
                ok = False
                diagnostics.append('bounded ten-attempt startup contract lost')
            if mode == 'wave-fail' and logs.count('RPS re-assert failed') != 4:
                ok = False
                diagnostics.append('asynchronous failures missing diagnostic')
            if mode == 'wave-recover' and sum('RPS re-assert (wave ' in line and ', complete policy' in line for line in logs.splitlines()) != 4:
                ok = False
                diagnostics.append('asynchronous recovery not observed independently')
        results.append({'case': label, 'pass': ok, 'expected_success': expected == 0,
                        'returncode': run.returncode, 'diagnostics': diagnostics,
                        'stderr': run.stderr.strip(), 'sleep_sequence': sleeps,
                        'policy_log': logs.splitlines()})
        print(('PASS' if ok else 'FAIL') + ': ' + label + f' (rc={run.returncode})')
        if not ok:
            print(json.dumps(results[-1], ensure_ascii=False), file=sys.stderr)

failures = sum(not row['pass'] for row in results)
print(f'=== RPS policy summary: PASS={len(results)-failures} FAIL={failures}; shell={SHELL!r}; actual script={SCRIPT} ===')
raise SystemExit(1 if failures else 0)
