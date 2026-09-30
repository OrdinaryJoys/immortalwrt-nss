#!/usr/bin/env python3
"""Execute actual ECM/netifd callbacks and platform script with offline mocks."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[1]
failures = []
checks = 0


def function(path, name):
    text = (root / path).read_text()
    match = re.search(rf'(?ms)^{name}\(\) \{{\n.*?^\}}', text)
    assert match, (name, path)
    return match.group(0)


def expect(label, actual, expected):
    global checks
    checks += 1
    if actual != expected:
        failures.append(f'{label}: expected {expected!r}, got {actual!r}')


ecm = function('package/qca-nss/qca-nss-ecm/files/qca-nss-ecm.init', 'disable_packet_steering')
netifd = function('package/network/config/netifd/files/etc/init.d/packet_steering', 'reload_service')
platform = root / 'target/linux/qualcommax/base-files/usr/libexec/platform/packet-steering.sh'

with tempfile.TemporaryDirectory(prefix='ecm-rps-test-') as tmp:
    base = Path(tmp)
    paths = {
        '/usr/libexec/platform/packet-steering.sh': base / 'platform',
        '/usr/libexec/network/packet-steering.uc': base / 'generic',
        '/etc/init.d/set-irq-affinity': base / 'rps-init',
        '/sys/module/qca_nss_drv': base / 'nss-module',
    }

    def substitute(text):
        for original, replacement in paths.items():
            text = text.replace(original, shlex.quote(str(replacement)))
        return text

    def executable(name, text):
        path = base / name
        path.write_text(text)
        path.chmod(0o755)

    executable('generic', '#!/bin/sh\nprintf "generic:%s\\n" "$*"\nexit "${GENERIC_RC:-0}"\n')
    executable('rps-init', '#!/bin/sh\nprintf "rps:%s\\n" "$*"\nexit "${RPS_RC:-0}"\n')
    executable('uci', '''#!/bin/sh
[ "$2" = get ] || exit 0
case "$*" in
  *steering_flows*) printf '%s\\n' "${TEST_FLOWS:-64}" ;;
  *packet_steering*) printf '%s\\n' "${TEST_POLICY:-0}" ;;
esac
''')
    if platform.exists():
        expect('platform entry executable', bool(platform.stat().st_mode & 0o111), True)
        executable('platform', substitute(platform.read_text()))
    else:
        failures.append('qualcommax platform entry missing')
    callbacks = substitute(ecm + '\n' + netifd)
    env = dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'])

    def run(script, extra=None):
        e = dict(env, **(extra or {}))
        result = subprocess.run(['sh'], input=script, text=True, capture_output=True, env=e)
        return result.returncode, result.stderr, result.stdout.splitlines()

    (base / 'nss-module').mkdir()
    for calls in [('disable_packet_steering', 'reload_service'),
                  ('reload_service', 'disable_packet_steering'),
                  ('reload_service', 'reload_service')]:
        expected = ['generic:-l 0 0', 'rps:start_rps'] * 2 + ['rc:0']
        expect('NSS callback ordering ' + ','.join(calls),
               run(callbacks + '\n' + '\n'.join(calls) + '\nprintf "rc:%s\\n" "$?"\n'),
               (0, '', expected))
    if platform.exists():
        call = shlex.quote(str(base / 'platform'))
        expect('NSS overrides conflicting generic steering selection', run(call + ' 2'),
               (0, '', ['generic:-l 0 0', 'rps:start_rps']))
        expect('RPS failure is propagated', run(call + ' 0', {'RPS_RC': '7'}),
               (7, '', ['generic:-l 0 0', 'rps:start_rps']))
        expect('generic cleanup failure is propagated', run(call + ' 0', {'GENERIC_RC': '9'}),
               (9, '', ['generic:-l 0 0']))
        (base / 'nss-module').rmdir()
        for policy, flows, expected_flows in [('0', '64', '64'), ('2', '64', '64'),
                                               ('1', 'invalid', '0')]:
            invocation = call + ' ' + policy if flows == 'invalid' else callbacks + '\nreload_service'
            expect(f'no NSS: policy={policy}, flows={flows}',
                   run(invocation, {'TEST_POLICY': policy, 'TEST_FLOWS': flows}),
                   (0, '', [f'generic:-l {expected_flows} {policy}']))
        (base / 'platform').unlink()
    # Other targets have no platform adapter and retain their original path.
    expect('other targets: ECM generic disable preserved', run(callbacks + '\ndisable_packet_steering'),
           (0, '', ['generic:-l 0 0']))

if failures:
    for failure in failures:
        print('FAIL: ' + failure, file=sys.stderr)
    raise SystemExit(1)
print(f'PASS: {checks} ownership checks; real ECM/netifd callbacks, both orders, native fallback, failures')
