#!/usr/bin/env python3
"""Actual pinned jshn/procd composition; only ubus/flock are mocked.

Inputs: optional argv source root; ECM_TEST_JSHN_SH, ECM_TEST_JSHN_BIN and
ECM_TEST_JSHN_BUILD_REPORT are mandatory; ECM_TEST_SHELL selects the shell
(default bash). Optional ECM_TEST_OUTPUT_JSON saves structured evidence.
The build report binds source commit, compiler command, json-c version and
binary/shell SHA256. It is a build attestation, not a reproducible-build proof.

No router contact and no service start/stop callbacks execute. This isolates
serialization/registration from kernel lifecycle behavior covered elsewhere.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import subprocess
import tempfile

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
# Compile jshn from the libubox commit in this source lock, not the target's
# architecture-specific executable. Missing inputs fail instead of skipping.
JSHN = Path(os.environ['ECM_TEST_JSHN_BIN']).resolve()
SHELL_LIB = Path(os.environ['ECM_TEST_JSHN_SH']).resolve()
assert JSHN.is_file() and os.access(JSHN, os.X_OK), JSHN
assert hashlib.sha256(SHELL_LIB.read_bytes()).hexdigest() == '89fb5871dc9f02e952168da2dd311286d5a2fdd4dd39558557611063129c4fec', 'pinned jshn shell drift'
assert 'PKG_SOURCE_VERSION:=7677b7a4f3a46f68e6f5ba6818f7b72fdd7dbaa0' in (ROOT / 'package/libs/libubox/Makefile').read_text(), 'libubox source lock drift'
assert 'PKG_SOURCE_VERSION:=74bfbee8adb8162ee3f1427905af06836f332a37' in (ROOT / 'package/system/procd/Makefile').read_text(), 'procd daemon source lock drift'
BUILD_REPORT_PATH = Path(os.environ['ECM_TEST_JSHN_BUILD_REPORT']).resolve()
BUILD_REPORT = json.loads(BUILD_REPORT_PATH.read_text())
assert BUILD_REPORT['source_commit'] == '7677b7a4f3a46f68e6f5ba6818f7b72fdd7dbaa0', 'build source lock drift'
assert BUILD_REPORT['binary_sha256'] == hashlib.sha256(JSHN.read_bytes()).hexdigest(), 'native binary/report mismatch'
assert BUILD_REPORT['shell_sha256'] == hashlib.sha256(SHELL_LIB.read_bytes()).hexdigest(), 'jshn shell/report mismatch'
assert BUILD_REPORT['json_c_version'], 'missing host json-c identity'
assert isinstance(BUILD_REPORT['compiler_command'], list) and BUILD_REPORT['compiler_command'], 'missing compiler command'
SHELL = shlex.split(os.environ.get('ECM_TEST_SHELL', 'bash'))
INIT = ROOT / 'package/qca-nss/qca-nss-ecm/files/qca-nss-ecm.init'
PROCD = ROOT / 'package/system/procd/files/procd.sh'
results = []

def case(name, operation='set', *, instance='', symlink=False, namespace='',
         missing_jshn=False, ubus_rc=0, expected=0, trace=False, probe_nested=False):
    with tempfile.TemporaryDirectory(prefix='ecm-real-json-') as tmp:
        base = Path(tmp)
        lib = base / 'usr/share/libubox/jshn.sh'
        lib.parent.mkdir(parents=True)
        shutil.copyfile(SHELL_LIB, lib)
        (base / 'bin').mkdir()
        if not missing_jshn:
            shutil.copyfile(JSHN, base / 'bin/jshn')
            (base / 'bin/jshn').chmod(0o755)
        target = base / 'etc/init.d/qca-nss-ecm'
        target.parent.mkdir(parents=True)
        shutil.copyfile(INIT, target)
        entry = target
        if symlink:
            entry = base / 'etc/rc.d/S26qca-nss-ecm'
            entry.parent.mkdir(parents=True)
            entry.symlink_to('../init.d/qca-nss-ecm')
        script = r'''
flock() { return 0; }
# Execute only the attested native binary copied into this fixture. The
# missing-executable case cannot accidentally find an installed system jshn.
jshn() { "$CASE_ROOT/bin/jshn" "$@"; }
ubus() {
    printf '%s\n' "$3" > "$CASE_ROOT/method"
    printf '%s\n' "$4" > "$CASE_ROOT/payload.json"
    return "$UBUS_RC"
}
action=probe_only
initscript="$ENTRY"
. "$REAL_PROCD"
. "$ECM_INIT"
ecm_procd_adapter
JSON_PREFIX="$INITIAL_NS"
if [ -n "$INITIAL_NS" ]; then
    json_init
    json_add_string marker caller-space
    json_add_object nested
    json_add_array values
    json_add_string '' preserved
    json_close_array
    json_close_object
    json_dump > "$CASE_ROOT/caller-before.json"
fi
initscript="$ENTRY"
basescript=$(readlink "$initscript")
if [ "$DO_TRACE" = 1 ]; then TRACE_SYSCALLS=1; fi
if [ "$OPERATION" = delete ]; then
    procd_kill qca-nss-ecm "$INSTANCE"
    status=$?
else
    procd_open_service "$(basename "${basescript:-$initscript}")" "$initscript"
    status=$?
    if [ "$status" -eq 0 ]; then
        if [ "$PROBE_NESTED" = 1 ]; then
            # Instrument only this diagnostic case; other cases execute the
            # unmodified real _procd_close_service. Every called helper is real.
            probe_trigger_status() {
                json_close_object
                _procd_open_trigger
                service_triggers
                printf '%s\n' "$?" > "$CASE_ROOT/trigger-status"
                _procd_close_trigger
                _procd_ubus_call set
            }
            _procd_call probe_trigger_status
        else
            procd_close_service "$OPERATION"
        fi
        status=$?
    fi
fi
printf '%s\n' "${JSON_PREFIX}" > "$CASE_ROOT/restored-namespace"
if [ -n "$INITIAL_NS" ]; then
    json_dump > "$CASE_ROOT/caller-after.json"
fi
env > "$CASE_ROOT/final-env"
printf '%s\n' "${TRACE_SYSCALLS:-0}" > "$CASE_ROOT/trace-state"
exit "$status"
'''
        environment = dict(os.environ, IPKG_INSTROOT=str(base), CASE_ROOT=str(base),
                           REAL_PROCD=str(PROCD), ECM_INIT=str(target), ENTRY=str(entry),
                           INITIAL_NS=namespace, OPERATION=operation, INSTANCE=instance,
                           DO_TRACE='1' if trace else '0', UBUS_RC=str(ubus_rc),
                           PROBE_NESTED='1' if probe_nested else '0',
                           PATH=str(base / 'bin') + ':/usr/bin:/bin')
        completed = subprocess.run(SHELL + ['-c', script], env=environment,
                                   text=True, capture_output=True, timeout=10)
        assert completed.returncode == expected, (name, completed.returncode, completed.stderr)
        if not missing_jshn:
            assert completed.stderr == '', (name, completed.stderr)
        assert (base / 'restored-namespace').read_text() == namespace + '\n', name
        assert not any(line.startswith('procd') for line in (base / 'final-env').read_text().splitlines()), name
        row = {'case': name, 'status': completed.returncode,
               'namespace_restored': True, 'procd_environment_cleaned': True,
               'stderr': completed.stderr, 'trace_state': (base / 'trace-state').read_text().strip()}
        if namespace:
            before = (base / 'caller-before.json').read_bytes()
            after = (base / 'caller-after.json').read_bytes()
            assert before == after, (name, 'caller namespace data changed')
            assert json.loads(after) == {'marker': 'caller-space', 'nested': {'values': ['preserved']}}, name
            row['caller_namespace_data_preserved'] = json.loads(after)
        if missing_jshn:
            assert not (base / 'payload.json').exists(), name
            row['ubus_called'] = False
        else:
            payload = json.loads((base / 'payload.json').read_text())
            assert (base / 'method').read_text() == operation + '\n', name
            assert payload['name'] == 'qca-nss-ecm', (name, payload)
            if operation == 'delete':
                wanted = {'name': 'qca-nss-ecm'}
                if instance:
                    wanted['instance'] = instance
                assert payload == wanted, (name, payload)
            else:
                assert payload['script'] == str(entry), (name, payload)
                assert payload['instances'] == {}, (name, payload)
                assert payload['triggers'] == [
                    ['config.change', ['if', ['eq', 'package', section],
                      ['run_script', '/etc/init.d/qca-nss-ecm', 'reload']], 1000]
                    for section in ('network', 'packet_steering')], (name, payload)
                # ECM declares no procd-managed process; the trace flag has no
                # instance object to decorate. Do not invent a payload trace key.
                assert 'trace' not in payload, (name, payload)
            row.update(ubus_called=True, payload=payload)
        assert row['trace_state'] == ('1' if trace else '0'), name
        if probe_nested:
            assert (base / 'trigger-status').read_text() == '1\n', name
            row['normal_nested_service_triggers_status'] = 1
        results.append(row)
        print('PASS:', name, flush=True)

case('set exact registration and two reload triggers')
case('add keeps same real payload shape', 'add')
case('rc.d symlink keeps canonical name and trigger target', symlink=True)
case('nonempty caller namespace restored', namespace='prior')
case('trace flag retained without inventing an ECM process', trace=True)
case('delete whole service exact request', 'delete')
case('delete one instance exact request', 'delete', instance='probe-instance')
case('real jshn executable absent blocks registration', missing_jshn=True, expected=127)
case('ubus set failure survives real cleanup', ubus_rc=31, expected=31)
case('ubus delete failure survives real cleanup', 'delete', ubus_rc=36, expected=36)
case('nested trigger callback returns one despite correct full payload', probe_nested=True)
identity = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (INIT, PROCD, SHELL_LIB, JSHN, BUILD_REPORT_PATH)}
report = {
    'source_root': str(ROOT), 'shell': SHELL, 'libubox_pin': '7677b7a4f3a46f68e6f5ba6818f7b72fdd7dbaa0',
    'daemon_pin_audited_not_executed': '74bfbee8adb8162ee3f1427905af06836f332a37',
    'json_c_host_version': BUILD_REPORT['json_c_version'], 'sha256': identity,
    'native_binary_build_report': BUILD_REPORT,
    'native_binary_build_report_path': str(BUILD_REPORT_PATH),
    'boundary': 'Real pinned jshn shell+C, real procd shell and ECM adapter. Mock ubus/flock; no daemon, kernel or full service lifecycle run. Selected host shell/json-c are not the exact AX6 binaries/configuration.',
    'cases': results}
if os.environ.get('ECM_TEST_OUTPUT_JSON'):
    Path(os.environ['ECM_TEST_OUTPUT_JSON']).write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS: {len(results)} real pinned JSON composition contracts; daemon not executed')
