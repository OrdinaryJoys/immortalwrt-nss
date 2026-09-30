#!/usr/bin/env python3
"""Run the complete offload helper against stateful offline ethtool I/O."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
HELPER = Path(os.environ.get('OFFLOAD_TEST_SCRIPT',
                            ROOT / 'package/qca-nss/qca-nss-ecm/files/disable_offloads.sh'))
SHELL = shlex.split(os.environ.get('ECM_TEST_SHELL', 'sh'))
checks = 0

MOCK = r'''
import json, os, sys
from pathlib import Path
base = Path(os.environ['MOCK_ROOT'])
opts = json.loads(os.environ['MOCK_OPTIONS'])
cmd, dev, *args = sys.argv[1:]
with (base / 'commands').open('a') as log:
    log.write(' '.join(sys.argv[1:]) + '\n')
path = base / ('state-' + dev + '.json')
state = json.loads(path.read_text()) if path.exists() else {
    'features': opts.get('features', {
        'generic-receive-offload': 'on', 'rx-gro-list': 'on',
        'rx-checksumming': 'on', 'tx-checksum-ip-generic': 'off [fixed]'}),
    'get_count': 0, 'coalesce_count': 0}
def done(rc=0):
    path.write_text(json.dumps(state))
    sys.exit(rc)
if cmd == '-k':
    state['get_count'] += 1
    if opts.get('query_rc') and (not opts.get('fail_dev') or dev == opts['fail_dev']):
        done(opts['query_rc'])
    if state['get_count'] > 1 and opts.get('readback_rc'):
        done(opts['readback_rc'])
    print('Features for ' + dev + ':')
    for key, value in state['features'].items():
        if state['get_count'] > 1 and key == opts.get('disappear'):
            continue
        print(key + ': ' + value)
    done()
if cmd == '-K':
    if opts.get('write_rc') and (not opts.get('fail_dev') or dev == opts['fail_dev']):
        done(opts['write_rc'])
    aliases = {'gro': 'generic-receive-offload', 'rx': 'rx-checksumming',
               'gso': 'generic-segmentation-offload'}
    for key, value in zip(args[::2], args[1::2]):
        key = aliases.get(key, key)
        if key not in state['features'] or '[fixed]' in state['features'][key]:
            done(91)
        if key != opts.get('ignore'):
            state['features'][key] = value
    done()
if cmd == '-a':
    done(opts.get('pause_query_rc', 0))
if cmd == '-A':
    done(opts.get('pause_set_rc', 0))
if cmd == '-c':
    state['coalesce_count'] += 1
    if opts.get('coalesce_query_rc'):
        done(opts['coalesce_query_rc'])
    if state['coalesce_count'] > 1 and opts.get('coalesce_second_query_rc'):
        done(opts['coalesce_second_query_rc'])
    print('Coalesce parameters for ' + dev + ':')
    print('Adaptive RX: off  TX: off')
    print('rx-usecs: ' + str(opts.get('coalesce_value', 2)))
    done()
if cmd == '-C':
    done(opts.get('adaptive_rc' if args[0] == 'adaptive-tx' else 'coalesce_set_rc', 0))
done(99)
'''


def check(label, call='disable_offload br-lan', expected=0, *, options=None,
          config=None, require=(), forbid=(), log_contains=()):
    global checks
    with tempfile.TemporaryDirectory(prefix='ecm-offload-errors-') as temp:
        base = Path(temp)
        (base / 'bin').mkdir()
        (base / 'net/eth0/device').mkdir(parents=True)
        (base / 'net/br-lan').mkdir()
        functions = base / 'functions.sh'
        functions.write_text('''
config_load() { return "${CONFIG_RC:-0}"; }
config_get() {
    case "$1" in
      offload_host_ifaces) eval "$1=\\\"${HOST_IFACES-br-lan}\\\"";;
      offload_physical_policy) eval "$1=\\\"${PHYSICAL_POLICY-report}\\\"";;
    esac
}
config_get_bool() {
    case "$1" in
      disable_offloads) eval "$1=${DISABLE_ALL:-1}";;
      disable_gro) eval "$1=${DISABLE_GRO:-0}";;
      disable_gro_list) eval "$1=${DISABLE_GRO_LIST:-1}";;
      disable_flow_control) eval "$1=${DISABLE_FLOW:-0}";;
      disable_interrupt_moderation) eval "$1=${DISABLE_COALESCE:-0}";;
      *) eval "$1=$4";;
    esac
}
''')
        for name, content in {
            'ethtool': '#!' + sys.executable + '\n' + MOCK,
            'logger': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_ROOT/log"\nexit "${LOGGER_RC:-0}"\n',
        }.items():
            path = base / 'bin' / name
            path.write_text(content)
            path.chmod(0o755)
        env = dict(os.environ, **(config or {}),
                   PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'],
                   OFFLOAD_FUNCTIONS_SH=str(functions), OFFLOAD_SYS_CLASS_NET=str(base / 'net'),
                   MOCK_ROOT=str(base), MOCK_OPTIONS=json.dumps(options or {}), HELPER=str(HELPER))
        result = subprocess.run(SHELL + ['-c', '. "$HELPER"; ' + call],
                                env=env, text=True, capture_output=True, timeout=15)
        commands = (base / 'commands').read_text() if (base / 'commands').exists() else ''
        log = (base / 'log').read_text() if (base / 'log').exists() else ''
        assert result.returncode == expected, (label, expected, result.returncode, result.stderr, commands, log)
        for item in require:
            assert item in commands, (label, 'missing command', item, commands)
        for item in forbid:
            assert item not in commands, (label, 'forbidden command', item, commands)
        for item in log_contains:
            assert item in log, (label, 'missing diagnostic', item, log)
        checks += 1
        print('PASS: ' + label)


check('complete policy with readback', require=('-K br-lan rx-gro-list off', '-K br-lan gro off rx off'))
check('explicit GRO maps to full feature name', config={'DISABLE_ALL': '0', 'DISABLE_GRO': '1'},
      require=('-K br-lan gro off',))
check('already off is a successful noop', options={'features': {'rx-gro-list': 'off [fixed]'}}, forbid=('-K',))
check('missing optional GRO-list on older kernel is skipped', options={'features': {'rx-checksumming': 'off'}},
      forbid=('-K',), log_contains=('not exposed',))
check('fixed enabled requested feature cannot be claimed disabled', expected=1,
      options={'features': {'rx-gro-list': 'on [fixed]'}}, forbid=('-K',))
check('bulk fixed features remain untouched', options={'features': {'rx-checksumming': 'on', 'rx-gro-list': 'off [fixed]', 'tx-checksum-ip-generic': 'on [fixed]'}},
      require=('-K br-lan rx off',), forbid=('tx-checksum-ip-generic off',))
for rc in (1, 2, 80, 92):
    check('write failure status ' + str(rc), expected=rc, options={'write_rc': rc},
          log_contains=('status ' + str(rc),))
check('query failure survives parser pipeline', expected=92, options={'query_rc': 92}, forbid=('-K',))
check('bulk query failure is retained', call='disable_offloads br-lan', expected=80,
      options={'query_rc': 80}, forbid=('-K',))
check('single feature readback still on', call='disable_feature gro br-lan', expected=1,
      options={'ignore': 'generic-receive-offload'}, log_contains=("readback is 'on'",))
check('bulk partial success is not full success', call='disable_offloads br-lan', expected=1,
      options={'ignore': 'rx-checksumming'}, log_contains=("readback is 'on'",))
check('missing feature at readback is a failure', call='disable_feature gro br-lan', expected=1,
      options={'disappear': 'generic-receive-offload'}, log_contains=("readback is 'missing'",))
check('single readback query failure', call='disable_feature gro br-lan', expected=92,
      options={'readback_rc': 92})
check('bulk readback query failure', call='disable_offloads br-lan', expected=92,
      options={'readback_rc': 92})
check('logger cannot erase failure', expected=92, options={'write_rc': 92}, config={'LOGGER_RC': '55'})
check('logger cannot turn success into policy failure', config={'LOGGER_RC': '55'})
check('later interface success cannot erase earlier failure', call='disable_offload br-lan eth0',
      expected=92, options={'write_rc': 92, 'fail_dev': 'br-lan'}, config={'HOST_IFACES': ''}, require=('-K eth0',))
check('first error wins but later independent actions run', expected=92,
      options={'write_rc': 92, 'pause_set_rc': 6}, config={'DISABLE_FLOW': '1'}, require=('-A br-lan',))
check('automatic discovery respects physical report policy', call='disable_offload',
      require=('-k eth0', '-K br-lan'), forbid=('-K eth0', '-A eth0', '-C eth0'))
check('physical report failure is visible without writes', call='disable_offload eth0',
      expected=92, options={'query_rc': 92}, forbid=('-K', '-A', '-C'))
check('explicit physical report remains read only', call='disable_offload eth0',
      require=('-k eth0',), forbid=('-K', '-A', '-C'))
check('missing configuration is not success', expected=7, config={'CONFIG_RC': '7'}, forbid=('-k',))
check('pause query failure', call='disable_flow_control br-lan', expected=80, options={'pause_query_rc': 80}, forbid=('-A',))
check('pause write failure', call='disable_flow_control br-lan', expected=81, options={'pause_set_rc': 81})
check('pause success', call='disable_flow_control br-lan', require=('-A br-lan autoneg off tx off rx off',))
check('coalescing query failure', call='disable_interrupt_moderation br-lan', expected=80,
      options={'coalesce_query_rc': 80}, forbid=('-C',))
check('adaptive failure survives later success', call='disable_interrupt_moderation br-lan', expected=81,
      options={'adaptive_rc': 81}, require=('-C br-lan rx-usecs 0',))
check('adaptive failure survives no remaining fields', call='disable_interrupt_moderation br-lan', expected=81,
      options={'adaptive_rc': 81, 'coalesce_value': 0})
check('second coalescing query failure is not empty success', call='disable_interrupt_moderation br-lan', expected=82,
      options={'coalesce_second_query_rc': 82}, forbid=('rx-usecs 0',))
check('first coalescing failure wins', call='disable_interrupt_moderation br-lan', expected=81,
      options={'adaptive_rc': 81, 'coalesce_second_query_rc': 82})
check('coalescing write failure', call='disable_interrupt_moderation br-lan', expected=83,
      options={'coalesce_set_rc': 83})
check('coalescing success', call='disable_interrupt_moderation br-lan', require=('-C br-lan rx-usecs 0',))
check('coalescing failure reaches full policy', expected=83, config={'DISABLE_COALESCE': '1'},
      options={'coalesce_set_rc': 83})
print('test-ecm-offload-errors: PASS (%d cases)' % checks)
