#!/usr/bin/env python3
"""Run real init callbacks against offline procd/network mocks, never services.

Checks ordering and API contracts, not kernel ifindex notifications or ujail races.
An optional source root allows the same tests to reject an older source tree.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[1]


def function(path, name, optional=False):
    text = (root / path).read_text()
    pattern = rf'(?ms)^([\t ]*){name}\(\)[\t ]*(?:\n\1)?\{{\n.*?^\1\}}'
    match = re.search(pattern, text)
    if not match:
        if optional:
            return ''
        raise AssertionError(f'missing function {name} in {path}')
    return match.group(0) + '\n'


def run(script):
    result = subprocess.run(['sh'], input=script, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f'shell exited {result.returncode}: {result.stderr}')
    if result.stderr:
        raise AssertionError(f'unexpected shell diagnostics: {result.stderr}')
    return result.stdout.splitlines()


dns = 'package/network/services/dnsmasq/files/dnsmasq.init'
procd = 'package/system/procd/files/procd.sh'
dns_functions = (
    function('package/base-files/files/etc/rc.common', 'rc_procd') +
    function(dns, 'reload_dnsmasq', optional=True) + function(dns, 'reload_service') +
    function(procd, '_procd_send_signal')
)
dns_mocks = r'''
initscript=/etc/init.d/dnsmasq
basescript=
pending=
nftables_clear() { printf 'clear\n'; }
procd_open_service() { pending=open; printf 'open:%s\n' "$1"; }
start_service() { pending="instances:$*"; printf 'prepare:%s\n' "$*"; }
json_init() { pending=signal; }
json_add_string() { pending="$pending:$1=$2"; }
json_add_int() { pending="$pending:$1=$2"; }
_procd_ubus_call() { printf '%s:%s\n' "$1" "$pending"; return "${signal_rc:-0}"; }
procd_send_signal() { _procd_send_signal "$@"; }
procd_close_service() { printf 'commit:%s:%s\n' "$1" "$pending"; }
'''

drop = 'package/network/services/dropbear/files/dropbear.init'
drop_functions = function(drop, 'normalize_list') + function(drop, 'dropbear_instance')
drop_mocks = r'''
enable=1 DirectInterface= Interface= BOOT= NAME=dropbear PROG=/usr/sbin/dropbear
Port=22 PasswordAuth=1 GatewayPorts=0 LocalPortForward=1 RemotePortForward=1
RootPasswordAuth=1 RootLogin=1 IdleTimeout=0 MaxSessionDuration=0 SSHKeepAlive=300
MaxAuthTries=3 RecvWindowSize=0 mdns=0 rsakeyfile= BannerFile= ForceCommand=
logger() { :; }
warn_multiple_interfaces() { :; }
config_list_foreach() { :; }
network_is_up() { test "${network_up:-1}" = 1; }
network_get_device() { eval "$1=\${device-br-lan}"; }
network_get_ipaddrs_all() { eval "$1=192.0.2.1"; }
procd_open_instance() { printf 'open\n'; }
procd_set_param() { printf 'set:%s\n' "$*"; }
procd_append_param() { printf 'append:%s\n' "$*"; }
procd_close_instance() { printf 'close\n'; }
'''

failures = []
checks = 0


def expect(label, actual, expected):
    global checks
    checks += 1
    if actual != expected:
        failures.append(f'{label}: expected {expected!r}, got {actual!r}')


for instance, signal_rc in [('', 0), ('lan', 0), ('lan', 1)]:
    lines = run(dns_mocks + dns_functions +
                f'\nsignal_rc={signal_rc}\nreload_service {instance}\n' +
                'printf "rc:%s\\n" "$?"\n')
    signal = 'signal:signal:name=dnsmasq' + (f':instance={instance}' if instance else '')
    method = 'add' if instance else 'set'
    expect(f'dnsmasq instance={instance!r} signal_rc={signal_rc}', lines,
           ['clear', 'open:dnsmasq', f'prepare:{instance}', signal,
            f'commit:{method}:instances:{instance}', 'rc:0'])

cases = [
    ('direct', 'DirectInterface=lan', ['netdev br-lan'], ['command -l br-lan -p 22'], 0),
    ('unbound', '', [], ['command -p 22'], 0),
    ('legacy address binding', 'Interface=lan', [], ['command -p 192.0.2.1:22'], 0),
    ('disabled', 'enable=0', [], [], 1),
    ('device missing', 'DirectInterface=lan; device=', [], [], 1),
    ('network down', 'DirectInterface=lan; network_up=0', [], [], 1),
    ('boot network down', 'DirectInterface=lan; network_up=0; BOOT=1', [], [], 0),
]
for label, setup, netdev, bindings, status in cases:
    lines = run(drop_mocks + drop_functions + '\n' + setup +
                '\ndropbear_instance main 0\nprintf "rc:%s\\n" "$?"\n')
    expected_lines = []
    if bindings:
        expected_lines = ['open', 'set:command /usr/sbin/dropbear -F -P /var/run/dropbear.main.pid']
        expected_lines += ['set:' + value for value in netdev]
        expected_lines += ['append:' + value for value in bindings]
        expected_lines += ['append:command -K 300', 'append:command -T 3', 'set:respawn', 'close']
    expect('dropbear ' + label, lines, expected_lines + [f'rc:{status}'])

if failures:
    for failure in failures:
        print('FAIL: ' + failure, file=sys.stderr)
    raise SystemExit(1)
print(f'PASS: {checks} service lifecycle scenarios; callback order, JSON isolation and netdev registration')
