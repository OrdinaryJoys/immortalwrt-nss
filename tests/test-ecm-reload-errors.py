#!/usr/bin/env python3
"""Run the real rc.common reload dispatcher/init/platform against offline mocks.

This is NOT a kernel/sysfs/procd or ethtool test. Only the reload entry is called;
all external effects and absolute reload paths resolve inside a private fixture.
An optional source-root supports old-source negatives and extracted-image tests.
"""
from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[1]
ecm_path = 'package/qca-nss/qca-nss-ecm/files/qca-nss-ecm.init'
platform_path = 'target/linux/qualcommax/base-files/usr/libexec/platform/packet-steering.sh'
rc_path = 'package/base-files/files/etc/rc.common'
failures = []
checks = 0


def check(name, condition, detail):
    global checks
    checks += 1
    if not condition:
        failures.append(f'{name}: {detail}')


with tempfile.TemporaryDirectory(prefix='ecm-full-reload-') as directory:
    base = Path(directory)
    binary = base / 'bin'
    binary.mkdir()
    library = base / 'lib/functions'
    library.mkdir(parents=True)
    nss = base / 'nss-module'
    nss.mkdir()
    trace = base / 'trace'
    logs = base / 'log'
    helper = base / 'offload-helper'
    paths = {
        '/usr/libexec/platform/packet-steering.sh': str(binary / 'platform'),
        '/usr/libexec/network/packet-steering.uc': str(binary / 'generic'),
        '/etc/init.d/set-irq-affinity': str(binary / 'rps-init'),
        '/sys/module/qca_nss_drv': str(nss),
        '/lib/netifd/offload/disable_offloads.sh': str(helper),
    }

    def substitute(text):
        for original, replacement in paths.items():
            text = text.replace(original, shlex.quote(replacement))
        return text

    def write(path, text, executable=False):
        path.write_text(text)
        if executable:
            path.chmod(0o755)

    write(base / 'rc.common', (root / rc_path).read_text())
    write(base / 'ecm-init', substitute((root / ecm_path).read_text()), True)
    platform = substitute((root / platform_path).read_text())
    write(binary / 'platform', platform, True)
    write(base / 'lib/functions.sh', '''list_contains() {
    [ "$1" = ALL_COMMANDS ] && [ "$2" = reload ]
}
''')
    write(library / 'service.sh', '# no system services in this fixture\n')
    write(library / 'procd.sh', '''procd_lock() { printf 'lock\n' >> "$TRACE"; }
''')
    write(binary / 'uci', '''#!/bin/sh
case "$*" in
  '-q get network.@globals[0].steering_flows') echo 0 ;;
  '-q set network.globals.packet_steering=0'|'-q delete network.globals.steering_flows'|'-q commit network') exit 0 ;;
  *) echo "Unexpected UCI invocation: $*" >&2; exit 99 ;;
esac
''', True)
    write(binary / 'generic', '''#!/bin/sh
printf 'generic:%s\n' "$*" >> "$TRACE"
exit "${GENERIC_RC:-0}"
''', True)
    write(binary / 'rps-init', '''#!/bin/sh
printf 'rps:%s\n' "$*" >> "$TRACE"
exit "${RPS_RC:-0}"
''', True)
    write(binary / 'logger', '''#!/bin/sh
printf '%s\n' "$*" >> "$LOG"
exit "${LOGGER_RC:-0}"
''', True)
    for command in ('modprobe', 'rmmod', 'insmod', 'sysctl', 'ethtool', 'tc', 'ip', 'ubus', 'sleep'):
        write(binary / command, '#!/bin/sh\necho "unexpected effect: $0 $*" >&2\nexit 98\n', True)

    def offload_fixture():
        write(helper, '''printf 'offload-source\n' >> "$TRACE"
disable_offload() {
    printf 'offload-call\n' >> "$TRACE"
    return "${OFFLOAD_RC:-0}"
}
return "${SOURCE_RC:-0}"
''')

    env = {
        'PATH': str(binary) + ':/usr/bin:/bin',
        'IPKG_INSTROOT': str(base), 'TRACE': str(trace), 'LOG': str(logs),
        'LC_ALL': 'C',
    }
    cases = [
        ('all stages succeed', {}, 0, ['rps:start_rps', 'offload-call'], []),
        ('RPS failure survives successful offload', {'RPS_RC': '7'}, 7, ['rps:start_rps', 'offload-call'], ['packet steering failed (status 7)']),
        ('generic cleanup fails but offload still runs', {'GENERIC_RC': '9'}, 9, ['offload-call'], ['packet steering failed (status 9)']),
        ('offload failure survives success', {'OFFLOAD_RC': '11'}, 11, ['rps:start_rps', 'offload-call'], ['offload policy failed (status 11)']),
        ('both fail: first error wins, both logged', {'RPS_RC': '7', 'OFFLOAD_RC': '11'}, 7, ['rps:start_rps', 'offload-call'], ['packet steering failed (status 7)', 'offload policy failed (status 11)']),
        ('cleanup/offload fail: first error wins', {'GENERIC_RC': '9', 'OFFLOAD_RC': '11'}, 9, ['offload-call'], ['packet steering failed (status 9)', 'offload policy failed (status 11)']),
        ('source failure must not call defined stale helper', {'SOURCE_RC': '13'}, 13, ['rps:start_rps'], ['offload policy failed (status 13)']),
        ('RPS and source fail', {'RPS_RC': '7', 'SOURCE_RC': '13'}, 7, ['rps:start_rps'], ['packet steering failed (status 7)', 'offload policy failed (status 13)']),
        ('logger cannot replace primary errors', {'RPS_RC': '7', 'OFFLOAD_RC': '11', 'LOGGER_RC': '55'}, 7, ['rps:start_rps', 'offload-call'], ['packet steering failed (status 7)', 'offload policy failed (status 11)']),
        ('next invocation recovers', {}, 0, ['rps:start_rps', 'offload-call'], []),
    ]

    def run_case(name, values, expected_status, stages, messages, missing=False):
        offload_fixture()
        if missing:
            helper.unlink()
        trace.write_text('')
        logs.write_text('')
        result = subprocess.run(['sh', str(base / 'rc.common'), str(base / 'ecm-init'), 'reload'], env={**env, **values}, text=True, capture_output=True, timeout=5)
        lines = trace.read_text().splitlines()
        message_lines = logs.read_text().splitlines()
        expected = ['lock', 'generic:-l 0 0']
        if 'rps:start_rps' in stages:
            expected.append('rps:start_rps')
        if not missing:
            expected.append('offload-source')
        if 'offload-call' in stages:
            expected.append('offload-call')
        expected_messages = ['-t qca-nss-ecm -p daemon.err reload: ' + message for message in messages]
        actual = (result.returncode, result.stdout, result.stderr, lines, message_lines)
        wanted = (expected_status, '', '', expected, expected_messages)
        check(name, actual == wanted, f'expected {wanted!r}, got {actual!r}')

    for case in cases:
        run_case(*case)
    run_case('optional helper missing succeeds', {}, 0, ['rps:start_rps'], [], missing=True)
    run_case('missing helper cannot hide RPS failure', {'RPS_RC': '7'}, 7, ['rps:start_rps'], ['packet steering failed (status 7)'], missing=True)
    nss.rmdir()
    run_case('no NSS keeps generic fallback', {}, 0, ['offload-call'], [])
    (binary / 'platform').unlink()
    run_case('other platform generic failure', {'GENERIC_RC': '9'}, 9, ['offload-call'], ['packet steering failed (status 9)'])

if failures:
    for failure in failures:
        print('FAIL: ' + failure, file=sys.stderr)
    raise SystemExit(1)
print(f'PASS: {checks} complete rc.common/ECM reload CLI cases; mocked effects, not live procd or ethtool')
