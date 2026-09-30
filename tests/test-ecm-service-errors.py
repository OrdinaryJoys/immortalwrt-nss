#!/usr/bin/env python3
"""Exercise the complete ECM init and rc.common dispatcher using offline I/O."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
INIT = ROOT / 'package/qca-nss/qca-nss-ecm/files/qca-nss-ecm.init'
RC_COMMON = ROOT / 'package/base-files/files/etc/rc.common'
PLATFORM = ROOT / 'target/linux/qualcommax/base-files/usr/libexec/platform/packet-steering.sh'
# macOS has no native BusyBox ash. CI explicitly selects "busybox ash";
# bash is the portable local fallback for the init's ash-style substitutions.
SHELL = os.environ.get('ECM_TEST_SHELL', 'bash')
checks = 0


def check(label, action='reload', expected=0, *, env=None, platform=True,
          offload=True, require=(), forbid=()):
    global checks
    with tempfile.TemporaryDirectory(prefix='ecm-service-errors-') as tmp:
        base = Path(tmp)

        def write(path, data, executable=False):
            target = base / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data)
            target.chmod(0o755 if executable else 0o644)

        # Translate only filesystem roots, not shell functions or control flow.
        def translate(text):
            return re.sub(r'/(?:usr|etc|sys|proc|lib|sbin)/',
                          lambda match: str(base) + match.group(), text)

        init = translate(INIT.read_text())
        write('etc/init.d/qca-nss-ecm', init)
        write('etc/rc.common', RC_COMMON.read_text())
        write('lib/functions.sh', '''
config_load() { return 0; }
config_get() { eval "$1=0"; }
list_contains() { return 0; }
''')
        write('lib/functions/service.sh', '')
        write('lib/functions/procd.sh', '''
procd_open_service() { printf 'procd-open\n'; }
procd_close_service() { printf 'procd-close\n'; return "${PROCD_CLOSE_RC:-0}"; }
procd_lock() { printf 'procd-lock\n'; }
procd_kill() { return 0; }
''')
        write('bin/uci', '''#!/bin/sh
printf 'uci:%s\n' "$*" >&2
case "$2" in
 set) exit "${SET_RC:-0}";;
 get) [ "${FLOWS_PRESENT:-1}" = 1 ] || exit 1; printf '64\n';;
 delete) exit "${DELETE_RC:-0}";;
 commit) exit "${COMMIT_RC:-0}";;
 *) exit 98;;
esac
''', True)
        write('bin/logger', '#!/bin/sh\nprintf "log:%s\\n" "$*" >&2\nexit "${LOGGER_RC:-0}"\n', True)
        write('bin/uname', '#!/bin/sh\necho 6.18.38\n', True)
        write('bin/sysctl', '''#!/bin/sh
printf 'sysctl:%s\n' "$*" >&2
exit "${SYSCTL_RC:-0}"
''', True)
        write('bin/insmod', '#!/bin/sh\nexit "${INSMOD_RC:-0}"\n', True)
        write('bin/rmmod', '#!/bin/sh\nexit 0\n', True)
        write('bin/sleep', '#!/bin/sh\nexit 0\n', True)
        write('bin/modinfo', '''#!/bin/sh
[ "${MODINFO_RC:-0}" -eq 0 ] || exit "$MODINFO_RC"
echo 'depends: qca_nss_drv'
''', True)
        write('bin/modprobe', '''#!/bin/sh
echo "modprobe:$1"
if [ "$1" = ecm ]; then exit "${MODPROBE_RC:-0}"; fi
exit "${DEPENDENCY_RC:-0}"
''', True)
        write('bin/xargs', '''#!/bin/sh
read -r dependency
[ -z "$dependency" ] || modprobe "$dependency"
''', True)
        write('etc/sysctl.d/qca-nss-ecm.conf', '')
        (base / 'sys/module/ecm').mkdir(parents=True)
        (base / 'sys/module/qca_nss_drv').mkdir()
        if platform:
            write('usr/libexec/platform/packet-steering.sh', translate(PLATFORM.read_text()), True)
        write('etc/init.d/set-irq-affinity', '''#!/bin/sh
echo steering-platform
exit "${STEERING_RC:-0}"
''', True)
        write('usr/libexec/network/packet-steering.uc', '''#!/bin/sh
echo steering-generic
exit "${GENERIC_RC:-0}"
''', True)
        if offload:
            write('lib/netifd/offload/disable_offloads.sh', '''
disable_offload() { echo offload-called; return "${OFFLOAD_RC:-0}"; }
return "${OFFLOAD_SOURCE_RC:-0}"
''')
        settings = dict(env or {})
        if settings.pop('NSS_LOADED', '1') == '0':
            (base / 'sys/module/qca_nss_drv').rmdir()
        if settings.pop('ECM_LOADED', '1') == '0':
            (base / 'sys/module/ecm').rmdir()
        if settings.pop('FW4', '1') == '1':
            write('sbin/fw4', '')
        if settings.pop('OVS', '0') == '1':
            (base / 'sys/module/qca_ovsmgr').mkdir()
        if settings.pop('REDIRECT', '0') == '1':
            (base / 'sys/kernel/debug/ecm/ecm_nss_ipv4').mkdir(parents=True)
            write('proc/sys/dev/nss/general/redirect', '0\n')
        run_env = dict(os.environ, **settings, IPKG_INSTROOT=str(base),
                       PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'])
        result = subprocess.run(
            shlex.split(SHELL) + [str(base / 'etc/rc.common'),
                                  str(base / 'etc/init.d/qca-nss-ecm'), action],
            env=run_env, text=True, capture_output=True, timeout=10)
        output = result.stdout + result.stderr
        assert result.returncode == expected, (label, expected, result.returncode, output)
        for item in require:
            assert item in output, (label, 'missing', item, output)
        for item in forbid:
            assert item not in output, (label, 'unexpected', item, output)
        checks += 1
        print('PASS: ' + label)


check('reload success', require=('steering-platform', 'offload-called'))
check('reload preserves steering failure and still applies offload', expected=7,
      env={'STEERING_RC': '7'}, require=('offload-called', 'packet steering failed'))
check('reload preserves offload callback failure', expected=9, env={'OFFLOAD_RC': '9'},
      require=('steering-platform', 'offload policy failed'))
check('reload does not lose first stage failure', expected=7,
      env={'STEERING_RC': '7', 'OFFLOAD_RC': '9'}, require=('offload-called',))
check('reload catches sourced helper failure', expected=8,
      env={'OFFLOAD_SOURCE_RC': '8'}, forbid=('offload-called',))
check('reload supports platforms without optional helper', offload=False)
check('reload without optional helper cannot hide steering failure', expected=7,
      offload=False, env={'STEERING_RC': '7'})
check('non-NSS generic fallback', platform=False, require=('steering-generic',))
check('generic failure is exposed', expected=7, platform=False, env={'GENERIC_RC': '7'})
check('NSS generic cleanup failure is exposed', expected=9, env={'GENERIC_RC': '9'},
      require=('offload-called',), forbid=('steering-platform',))
check('non-NSS platform keeps native helper', env={'NSS_LOADED': '0'},
      require=('steering-generic',), forbid=('steering-platform',))
check('logger failure cannot replace policy failure', expected=7,
      env={'STEERING_RC': '7', 'LOGGER_RC': '55'})
check('absent optional UCI steering_flows is not an error', env={'FLOWS_PRESENT': '0'},
      forbid=('uci:-q delete',))
for key in ('SET_RC', 'DELETE_RC', 'COMMIT_RC'):
    check('persistence error ' + key + ' still applies live policies', expected=6,
          env={key: '6'}, require=('steering-platform', 'offload-called'))
for action in ('start', 'boot', 'restart'):
    check(action + ' success through actual rc.common', action, require=('procd-close',))
    check(action + ' exposes RPS error after procd-close', action, expected=7,
          env={'STEERING_RC': '7'}, require=('procd-close',))
check('start exposes UCI persistence failure', 'start', expected=6, env={'COMMIT_RC': '6'})
check('start without previously loaded ECM succeeds', 'start', env={'ECM_LOADED': '0'},
      require=('modprobe:ecm',))
check('start propagates modinfo failure', 'start', expected=4,
      env={'ECM_LOADED': '0', 'MODINFO_RC': '4'}, forbid=('modprobe:ecm',))
check('start propagates dependency failure', 'start', expected=6,
      env={'ECM_LOADED': '0', 'DEPENDENCY_RC': '6'}, forbid=('modprobe:ecm',))
check('start propagates ECM module load failure', 'start', expected=7,
      env={'ECM_LOADED': '0', 'MODPROBE_RC': '7'})
check('start propagates offload helper failure', 'start', expected=9,
      env={'OFFLOAD_RC': '9'})
check('start propagates helper source failure', 'start', expected=8,
      env={'OFFLOAD_SOURCE_RC': '8'})
check('start retains fw3 compatibility', 'start', env={'FW4': '0'})
check('start exposes OVS module failure', 'start', expected=9,
      env={'OVS': '1', 'INSMOD_RC': '9'})
check('start exposes NSS Wi-Fi redirect failure', 'start', expected=5,
      env={'REDIRECT': '1', 'SYSCTL_RC': '5'})
print(f'PASS: {checks} ECM dispatcher cases; mocked I/O, no router changes')
