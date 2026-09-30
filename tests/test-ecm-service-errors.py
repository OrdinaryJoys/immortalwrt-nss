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
          offload=True, real_offload=False, real_procd=False,
          other_service=False, rc_symlink=False, args=(),
          strip_registration=False, require=(), forbid=()):
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
        if strip_registration:
            init, removed = re.subn(r'^EXTRA_COMMANDS=.*ecm_start.*\n', '', init, flags=re.M)
            assert removed == 1, ('private registration mutation anchor drift', removed)
        if other_service:
            init = '''USE_PROCD=1
start_service() { echo unrelated-service; }
'''
        write('etc/init.d/qca-nss-ecm', init)
        write('etc/rc.common', RC_COMMON.read_text())
        functions = (ROOT / 'package/base-files/files/lib/functions.sh').read_text()
        contains = re.findall(r'^list_contains\(\) \{\n.*?^\}', functions, re.M | re.S)
        assert len(contains) == 1, ('list_contains source anchor drift', len(contains))
        write('lib/functions.sh', contains[0] + '\n' + '''
config_load() { return "${CONFIG_LOAD_RC:-0}"; }
config_get() {
    case "$1" in
        offload_host_ifaces) eval "$1=br-lan";;
        offload_physical_policy) eval "$1=report";;
        enable_bridge_filtering) eval "$1=${BRIDGE_ENABLE:-0}";;
        *) eval "$1=0";;
    esac
}
config_get_bool() {
    case "$1" in
        disable_gro_list) eval "$1=1";;
        *) eval "$1=0";;
    esac
}
''')
        write('lib/functions/service.sh', '')
        write('lib/functions/procd.sh', '''
procd_open_service() { printf 'procd-open\n'; return "${PROCD_OPEN_RC:-0}"; }
procd_close_service() { printf 'procd-close\n'; return "${PROCD_CLOSE_RC:-0}"; }
procd_lock() { printf 'procd-lock\n'; }
procd_kill() { echo procd-kill; return "${PROCD_KILL_RC:-0}"; }
''')
        write('usr/share/libubox/jshn.sh', '''
_JSON_NS=original
json_set_namespace() {
    if [ -n "$2" ]; then
        eval "$2=\\\"${_JSON_NS}\\\""
        [ "${JSON_ENTER_RC:-0}" -eq 0 ] || return "$JSON_ENTER_RC"
    elif [ "$1" = original ]; then
        echo namespace-restored >&2
        [ "${JSON_RESTORE_RC:-0}" -eq 0 ] || return "$JSON_RESTORE_RC"
    fi
    _JSON_NS="$1"
}
json_dump() {
    echo "trace-marker:${TRACE_SYSCALLS:-0}" >&2
    printf '{"fixture_namespace":"%s","trace":"%s"}\\n' "$_JSON_NS" "${TRACE_SYSCALLS:-0}"
    return "${JSON_DUMP_RC:-0}"
}
json_cleanup() { echo "json-cleanup:$_JSON_NS" >&2; return "${JSON_CLEANUP_RC:-0}"; }
json_init() { echo "json-init:$_JSON_NS" >&2; return 0; }
json_add_string() { echo "json-string:$1:$2" >&2; return 0; }
json_add_object() { echo "json-object:$1" >&2; return 0; }
json_close_object() { echo json-object-close >&2; return 0; }
json_add_array() { return 0; }
json_close_array() { return 0; }
json_add_int() { return 0; }
json_add_boolean() { return 0; }
json_select() { return 0; }
''')
        if real_procd:
            procd = (ROOT / 'package/system/procd/files/procd.sh').read_text()
            # Deliberately use the locked real helper. If its adapter protocol
            # changes, stop here instead of silently testing a stale mock.
            for anchor in ('_procd_call() {', '_procd_ubus_call() {',
                           '_procd_open_service() {', '_procd_close_service() {',
                           '_procd_kill() {', 'json_set_namespace procd old_cb',
                           'ubus call service "$cmd" "$(json_dump)"'):
                assert anchor in procd, ('procd adapter protocol drift', anchor)
            write('lib/functions/procd.sh', procd)
        else:
            # The small public-API mocks still need JSON cleanup for failed
            # startup, but the dedicated tests below use the real procd file.
            with (base / 'lib/functions/procd.sh').open('a') as stream:
                stream.write('. "$IPKG_INSTROOT/usr/share/libubox/jshn.sh"\n')
        (base / 'var/lock').mkdir(parents=True)
        write('bin/flock', '''#!/bin/sh
echo "fixture-flock:$*" >&2
if [ "$1" = -n ] && [ "${LOCK_INITIAL_MISS:-0}" = 1 ] && [ ! -e "$IPKG_INSTROOT/first-lock-seen" ]; then
    touch "$IPKG_INSTROOT/first-lock-seen"
    exit 1
fi
exit "${LOCK_RC:-0}"
''', True)
        write('bin/ubus', '''#!/bin/sh
echo "ubus:$*" >&2
# A sentinel payload proves the current namespace reached the actual ubus
# call as one argument. JSON tree construction itself remains mocked.
case "$4" in '{"fixture_namespace":"procd",'* ) : ;; *) exit 97;; esac
case "$3" in
 set|add) exit "${UBUS_SET_RC:-0}";;
 delete) exit "${UBUS_DELETE_RC:-0}";;
 *) exit 99;;
esac
''', True)
        write('bin/uci', '''#!/bin/sh
printf 'uci:%s\n' "$*" >&2
case "$2" in
 set) exit "${SET_RC:-0}";;
 get) [ "${FLOWS_PRESENT:-1}" = 1 ] || exit 1; printf '64\n';;
 show) exit "${SHOW_RC:-0}";;
 delete) exit "${DELETE_RC:-0}";;
 commit) exit "${COMMIT_RC:-0}";;
 *) exit 98;;
esac
''', True)
        write('bin/logger', '#!/bin/sh\nprintf "log:%s\\n" "$*" >&2\nexit "${LOGGER_RC:-0}"\n', True)
        write('bin/uname', '#!/bin/sh\necho 6.18.38\n', True)
        write('bin/sysctl', '''#!/bin/sh
printf 'sysctl:%s\n' "$*" >&2
key=${2%%=*}
value=${2#*=}
if [ -z "${FAIL_SYSCTL:-}" ] || [ "$key" = "$FAIL_SYSCTL" ]; then
    [ "${SYSCTL_RC:-0}" -eq 0 ] || exit "$SYSCTL_RC"
fi
path="$IPKG_INSTROOT/proc/sys/$(printf '%s' "$key" | tr . /)"
if [ -f "$path" ] && [ "${SYSCTL_STALE:-0}" = 0 ]; then
    printf '%s\n' "$value" > "$path"
fi
exit 0
''', True)
        write('bin/sed', '''#!/bin/sh
# Persistence side effects are mocked, including a reported write failure.
[ "$1" = -i ] && exit "${SED_RC:-0}"
exec /usr/bin/sed "$@"
''', True)
        write('bin/cat', '''#!/bin/sh
case "$1" in
 *"${BAD_READBACK_PATH:-/not-selected}")
    [ "${READ_ERROR_RC:-0}" -eq 0 ] || exit "$READ_ERROR_RC"
    echo wrong-value; exit 0;;
esac
exec /bin/cat "$@"
''', True)
        write('bin/insmod', '#!/bin/sh\nexit "${INSMOD_RC:-0}"\n', True)
        write('bin/rmmod', '''#!/bin/sh
echo "rmmod:$1" >&2
exit "${RMMOD_RC:-0}"
''', True)
        write('bin/sleep', '#!/bin/sh\nexit 0\n', True)
        write('bin/modinfo', '''#!/bin/sh
[ "${MODINFO_RC:-0}" -eq 0 ] || exit "$MODINFO_RC"
echo "depends: ${DEPENDENCIES-qca_nss_drv}"
echo 'description: this module depends on platform features'
''', True)
        write('bin/modprobe', '''#!/bin/sh
echo "modprobe:$1"
if [ "$1" = ecm ]; then exit "${MODPROBE_RC:-0}"; fi
[ -z "${FAIL_DEPENDENCY:-}" ] || [ "$1" = "$FAIL_DEPENDENCY" ] || exit 0
exit "${DEPENDENCY_RC:-0}"
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
        if real_offload:
            helper = ROOT / 'package/qca-nss/qca-nss-ecm/files/disable_offloads.sh'
            write('lib/netifd/offload/disable_offloads.sh', translate(helper.read_text()))
            (base / 'sys/class/net/br-lan').mkdir(parents=True)
            write('bin/ethtool', '''#!/bin/sh
echo "ethtool:$*" >&2
case "$1" in
  -k)
    state=on
    [ ! -f "$IPKG_INSTROOT/feature-written" ] || state="${READBACK_STATE:-off}"
    printf 'Features for br-lan:\nrx-gro-list: %s\n' "$state"
    ;;
  -K)
    [ "${ETHTOOL_RC:-0}" -eq 0 ] || exit "$ETHTOOL_RC"
    touch "$IPKG_INSTROOT/feature-written"
    ;;
  *) exit 99;;
esac
''', True)
        elif offload:
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
        if settings.pop('CONTROLS', '0') == '1':
            for control in ('proc/sys/net/netfilter/nf_conntrack_events',
                            'sys/kernel/debug/ecm/ecm_classifier_default/accel_delay_pkts',
                            'sys/kernel/debug/ecm/front_end_ipv4_stop',
                            'sys/kernel/debug/ecm/front_end_ipv6_stop',
                            'sys/kernel/debug/ecm/ecm_db/defunct_all',
                            'proc/net/nf_conntrack'):
                write(control, '0\n')
        if settings.pop('BRIDGE_CONTROLS', '0') == '1':
            for family in ('arptables', 'iptables', 'ip6tables'):
                write('proc/sys/net/bridge/bridge-nf-call-' + family, '1\n')
        readonly = settings.pop('READONLY_CONTROL', '')
        if readonly:
            (base / readonly).chmod(0o444)
        run_env = dict(os.environ, **settings, IPKG_INSTROOT=str(base),
                       PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'])
        entry = base / 'etc/init.d/qca-nss-ecm'
        if rc_symlink:
            entry = base / 'etc/rc.d/S26qca-nss-ecm'
            entry.parent.mkdir(parents=True)
            entry.symlink_to('../init.d/qca-nss-ecm')
        result = subprocess.run(
            shlex.split(SHELL) + [str(base / 'etc/rc.common'),
                                  str(entry), action] + list(args),
            env=run_env, text=True, capture_output=True, timeout=10)
        output = result.stdout + result.stderr
        # BSD and GNU xargs map child failures to different nonzero statuses.
        valid_status = result.returncode != 0 if expected is None else result.returncode == expected
        assert valid_status, (label, expected, result.returncode, output)
        for item in require:
            assert item in output, (label, 'missing', item, output)
        for item in forbid:
            assert item not in output, (label, 'unexpected', item, output)
        if rc_symlink and settings.get('LOCK_INITIAL_MISS') == '1':
            assert (base / 'var/lock/procd_qca-nss-ecm.lock').is_file(), (label, output)
            assert not (base / 'var/lock/procd_S26qca-nss-ecm.lock').exists(), (label, output)
        checks += 1
        print('PASS: ' + label)


for action in ('reload', 'start', 'restart'):
    check(action + ' with real offload helper succeeds', action, real_offload=True)
    check(action + ' with real helper propagates ethtool failure', action, expected=92,
          real_offload=True, env={'ETHTOOL_RC': '92'}, require=('offload policy failed',))
    check(action + ' with real helper rejects partial success', action, expected=1,
          real_offload=True, env={'READBACK_STATE': 'on'}, require=("readback is 'on'",))

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
    check(action + ' rejects partial startup without procd registration', action, expected=7,
          env={'STEERING_RC': '7'}, require=('json-cleanup',), forbid=('procd-close',))
check('start exposes UCI persistence failure', 'start', expected=6, env={'COMMIT_RC': '6'})
check('start without previously loaded ECM succeeds', 'start', env={'ECM_LOADED': '0'},
      require=('modprobe:ecm',))
check('empty module dependency list is valid', 'start',
      env={'ECM_LOADED': '0', 'DEPENDENCIES': '', 'DEPENDENCY_RC': '6'},
      require=('modprobe:ecm',), forbid=('modprobe:depends:', 'modprobe:features'))
check('start propagates modinfo failure', 'start', expected=4,
      env={'ECM_LOADED': '0', 'MODINFO_RC': '4'}, forbid=('modprobe:ecm',))
check('start propagates dependency failure', 'start', expected=None,
      env={'ECM_LOADED': '0', 'DEPENDENCY_RC': '6'}, forbid=('modprobe:ecm',))
check('all comma-separated dependencies load', 'start',
      env={'ECM_LOADED': '0', 'DEPENDENCIES': 'qca_nss_drv,qca_nss_ipv4'},
      require=('modprobe:qca_nss_drv', 'modprobe:qca_nss_ipv4', 'modprobe:ecm'))
check('later dependency failure prevents ECM load', 'start', expected=None,
      env={'ECM_LOADED': '0', 'DEPENDENCIES': 'qca_nss_drv,qca_nss_ipv4',
           'FAIL_DEPENDENCY': 'qca_nss_ipv4', 'DEPENDENCY_RC': '6'},
      require=('modprobe:qca_nss_drv', 'modprobe:qca_nss_ipv4'), forbid=('modprobe:ecm',))
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
check('first UCI failure survives later failures', expected=6,
      env={'SET_RC': '6', 'DELETE_RC': '7', 'COMMIT_RC': '8'}, require=('offload-called',))
check('unreadable UCI globals is not optional absence', expected=8,
      env={'FLOWS_PRESENT': '0', 'SHOW_RC': '8'}, require=('offload-called',))
check('procd public open error stops startup', 'start', expected=12,
      env={'PROCD_OPEN_RC': '12'}, forbid=('offload-called', 'procd-close'))
check('procd public close error survives', 'start', expected=17,
      env={'PROCD_CLOSE_RC': '17'})
check('stop preserves module unload error and registration', 'stop', expected=19,
      env={'RMMOD_RC': '19'}, require=('rmmod:ecm',), forbid=('procd-kill',))
check('restart cannot start after failed stop', 'restart', expected=19,
      env={'RMMOD_RC': '19'}, forbid=('procd-open', 'offload-called'))
check('shutdown preserves unload error', 'shutdown', expected=19, env={'RMMOD_RC': '19'})
check('stop propagates procd deletion failure', 'stop', expected=20,
      env={'PROCD_KILL_RC': '20'})
check('restart cannot start after failed procd deletion', 'restart', expected=20,
      env={'PROCD_KILL_RC': '20'}, forbid=('procd-open',))
check('start preserves first module error, does not activate redirect or OVS', 'start', expected=4,
      env={'ECM_LOADED': '0', 'MODINFO_RC': '4', 'STEERING_RC': '7', 'REDIRECT': '1', 'OVS': '1'},
      forbid=('sysctl:-w dev.nss.general.redirect=1', 'procd-close'))
for action in ('start', 'stop'):
    check(action + ' reads back available scalar controls', action,
          env={'CONTROLS': '1'})
    check(action + ' rejects scalar readback mismatch', action, expected=1,
          env={'CONTROLS': '1', 'BAD_READBACK_PATH': 'nf_conntrack_events'},
          forbid=('procd-close', 'procd-kill'))
    check(action + ' preserves scalar read error', action, expected=23,
          env={'CONTROLS': '1', 'BAD_READBACK_PATH': 'nf_conntrack_events', 'READ_ERROR_RC': '23'})
    check(action + ' rejects unwritable existing command control', action, expected=1,
          env={'CONTROLS': '1', 'READONLY_CONTROL': 'sys/kernel/debug/ecm/ecm_db/defunct_all'})
check('stop quiesce failure prevents rmmod', 'stop', expected=1,
      env={'CONTROLS': '1', 'READONLY_CONTROL': 'sys/kernel/debug/ecm/front_end_ipv4_stop'},
      forbid=('rmmod:ecm', 'procd-kill'))
check('fw4 bridge first failure survives later successes', 'start', expected=27,
      env={'BRIDGE_CONTROLS': '1', 'FAIL_SYSCTL': 'net.bridge.bridge-nf-call-arptables', 'SYSCTL_RC': '27'},
      require=('sysctl:-w net.bridge.bridge-nf-call-ip6tables=0',), forbid=('procd-close',))
check('fw3 enable bridge failure survives later successes', 'start', expected=27,
      env={'FW4': '0', 'BRIDGE_ENABLE': '1', 'BRIDGE_CONTROLS': '1',
           'FAIL_SYSCTL': 'net.bridge.bridge-nf-call-arptables', 'SYSCTL_RC': '27'},
      require=('sysctl:-w net.bridge.bridge-nf-call-ip6tables=1',))
check('bridge persistence error does not skip live policy', 'start', expected=28,
      env={'BRIDGE_CONTROLS': '1', 'SED_RC': '28'},
      require=('sysctl:-w net.bridge.bridge-nf-call-ip6tables=0',))
check('bridge stale successful write fails readback', 'start', expected=1,
      env={'BRIDGE_CONTROLS': '1', 'SYSCTL_STALE': '1'})
check('redirect stale successful write fails readback', 'start', expected=1,
      env={'REDIRECT': '1', 'SYSCTL_STALE': '1'})
for action in ('start', 'boot', 'restart', 'stop', 'shutdown', 'reload', 'trace'):
    check(action + ' uses real procd helper', action, real_procd=True,
          require=('trace-marker:1',) if action == 'trace' else ())
check('real procd start payload and registration contract', 'start', real_procd=True,
      require=('json-init:procd', 'json-string:name:qca-nss-ecm', 'json-object:instances',
               'json-object-close', 'ubus:call service set {"fixture_namespace":"procd","trace":"0"}',
               'json-cleanup:procd', 'namespace-restored'))
check('real procd trace propagates trace flag into payload context', 'trace', real_procd=True,
      require=('ubus:call service set {"fixture_namespace":"procd","trace":"1"}',))
check('real procd boot preserves registration method', 'boot', real_procd=True,
      require=('ubus:call service set ', 'json-cleanup:procd', 'namespace-restored'))
check('rc.d symlink boot keeps canonical service and lock name', 'boot', real_procd=True,
      rc_symlink=True, env={'LOCK_INITIAL_MISS': '1'},
      require=('json-string:name:qca-nss-ecm', 'ubus:call service set '),
      forbid=('json-string:name:S26qca-nss-ecm',))
check('instance start preserves procd add registration method', 'start', real_procd=True,
      args=('instance-a',), require=('ubus:call service add ',),
      forbid=('ubus:call service set ',))
check('real procd lock is acquired after an initial miss', 'start', real_procd=True,
      env={'LOCK_INITIAL_MISS': '1'}, require=('fixture-flock:1000', 'ubus:call service set'))
check('real procd lock failure stops all startup effects', 'start', expected=42,
      real_procd=True, env={'LOCK_RC': '42'}, forbid=('offload-called', 'ubus:call service'))
for action in ('start', 'boot', 'trace'):
    check(action + ' exposes real ubus service set failure', action, expected=31,
          real_procd=True, env={'UBUS_SET_RC': '31'}, require=('json-cleanup', 'namespace-restored'))
check('real procd ubus failure wins over cleanup failure', 'start', expected=31,
      real_procd=True, env={'UBUS_SET_RC': '31', 'JSON_CLEANUP_RC': '32'})
check('real procd cleanup failure is not discarded', 'start', expected=32,
      real_procd=True, env={'JSON_CLEANUP_RC': '32'})
check('real procd serialization failure prevents ubus commit', 'start', expected=33,
      real_procd=True, env={'JSON_DUMP_RC': '33'}, forbid=('ubus:call service set',))
check('real procd namespace restore failure stops startup', 'start', expected=34,
      real_procd=True, env={'JSON_RESTORE_RC': '34'}, forbid=('offload-called',))
check('real procd namespace entry failure stops startup', 'start', expected=35,
      real_procd=True, env={'JSON_ENTER_RC': '35'}, forbid=('offload-called',))
check('real procd stop returns ubus delete failure', 'stop', expected=36,
      real_procd=True, env={'UBUS_DELETE_RC': '36'})
check('real procd restart cannot start after delete failure', 'restart', expected=36,
      real_procd=True, env={'UBUS_DELETE_RC': '36'}, forbid=('ubus:call service set', 'offload-called'))
check('real procd failed startup never commits declaration', 'start', expected=7,
      real_procd=True, env={'STEERING_RC': '7', 'JSON_CLEANUP_RC': '32'},
      forbid=('ubus:call service set',))
# Separate process, no ECM init: proving this patch did not silently change
# every other service's framework semantics. Existing global masking remains.
check('unrelated service keeps unmodified real framework behavior', 'start', expected=0,
      real_procd=True, other_service=True, env={'UBUS_SET_RC': '31'},
      require=('unrelated-service', 'ubus:call service set'))
# Removing the private action registration must not pass a normal start
# contract: the actual list_contains implementation sends it to help instead.
try:
    check('missing private action registration mutation', 'start', real_procd=True,
          strip_registration=True, require=('offload-called',))
except AssertionError as error:
    assert error.args[0][1:3] == ('missing', 'offload-called'), error
    assert 'Syntax:' in error.args[0][3], error
    checks += 1
    print('PASS: unregistered private action mutation rejected by real command membership')
else:
    raise AssertionError('unregistered private action mutation falsely passed')
print(f'PASS: {checks} ECM dispatcher cases; mocked I/O, no router changes')
