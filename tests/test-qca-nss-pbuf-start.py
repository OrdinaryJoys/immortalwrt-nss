#!/usr/bin/env python3
"""Complete current PBUF optional helpers/start, isolated paths and side effects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--shell', default='/bin/sh')
parser.add_argument('--mutations', action='store_true')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
shell_command = shlex.split(args.shell)
if not shell_command or not shutil.which(shell_command[0]):
    raise SystemExit('requested shell is unavailable')
shell_command[0] = shutil.which(shell_command[0])
args.output.mkdir(parents=True, exist_ok=False)
path = ROOT / 'package/kernel/mac80211/files/qca-nss-pbuf.init'
source = path.read_text()
NAMES = ['set_stats_disable', 'set_scaling_governor', 'start', 'reload', 'restart']


def function(text, name):
    lines = text.splitlines()
    definitions = [i for i, line in enumerate(lines) if re.match(
        r'^[ \t]*(?:function[ \t]+' + re.escape(name) + r'\b|' + re.escape(name) + r'[ \t]*\()', line)]
    if len(definitions) != 1 or lines[definitions[0]] != name + '() {':
        raise ValueError('unsupported function header: ' + name)
    begin = definitions[0]
    for end in range(begin + 1, len(lines)):
        if lines[end].startswith('}'):
            if lines[end] != '}':
                raise ValueError('unsupported closing suffix: ' + name)
            return '\n'.join(lines[begin:end + 1]) + '\n'
    raise ValueError('missing closing brace: ' + name)


writer = function(source, 'pbuf_write_value')
body = ''.join(function(source, name) for name in NAMES)


def mapped(text):
    replacements = {
        '/sys/devices/system/cpu': '${PBUF_TEST_ROOT}/cpu',
        '/sys/kernel/debug/ath11k': '"${PBUF_TEST_ROOT}/stats"',
        '/proc/sys/dev/nss/rps/hash_bitmap': '"${PBUF_TEST_ROOT}/hash_bitmap"',
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError('path mapping context: ' + old)
        text = text.replace(old, new)
    predicate = '[ -w "$governor_file" ]'
    if text.count(predicate) != 1:
        raise ValueError('governor permission predicate context')
    text = text.replace(predicate, 'pbuf_test_writable "$governor_file"')
    if re.search(r'/(?:sys|proc)/', text):
        raise ValueError('unmapped system path')
    return text


prefix = r'''
NAME=isolated-pbuf
trace() { printf '%s\n' "$1" >> "$PBUF_TEST_ROOT/trace"; }
config_load() { [ "$1" = pbuf ] || return 98; }
config_get() {
  case "$3" in
    scaling_governor) eval "$1=\${PBUF_GOVERNOR-}" ;;
    stats_disable) eval "$1=\${PBUF_STATS-1}" ;;
    *) return 98 ;;
  esac
}
logger() { :; }
cat() {
  [ "$1" = "$PBUF_TEST_ROOT/cpu/cpu0/cpufreq/scaling_available_governors" ] || return 98
  [ "$PBUF_CAT_RC" -eq 0 ] || return "$PBUF_CAT_RC"
  /bin/cat "$1"
}
find() {
  [ "$#" -eq 3 ] && [ "$1" = "$PBUF_TEST_ROOT/stats" ] && [ "$2" = -name ] && [ "$3" = stats_disable ] || return 98
  trace find
  /bin/cat "$PBUF_TEST_ROOT/find-list"
  return "$PBUF_FIND_RC"
}
pbuf_test_writable() {
  [ "$1" != "$PBUF_NOT_WRITABLE" ] && [ -w "$1" ]
}
get_num_cpus() { [ "$PBUF_CPU_RC" -eq 0 ] || return "$PBUF_CPU_RC"; printf '%s\n' "$PBUF_CPUS"; }
seq() {
  [ "$#" -eq 2 ] && [ "$1" = 0 ] && [ "$2" = 2 ] || return 98
  printf '0\n1\n2\n'
}
wait_for_ath11k_nss_offload() { trace offload; return "$PBUF_OFFLOAD_RC"; }
wait_for_nss_sysctls() { trace sysctls; return "$PBUF_SYSCTLS_RC"; }
apply_nss_config() { trace apply; pbuf_config_applied=$PBUF_APPLIED; return "$PBUF_APPLY_RC"; }
write_sysctl_exact() {
  [ "$1" = dev.nss.rps.hash_bitmap ] && [ "$2" = 7 ] || return 98
  trace rps; return "$PBUF_RPS_RC"
}
reload_wifi() { trace wifi; return "$PBUF_WIFI_RC"; }
pbuf_write_value() {
  case "$1" in "$PBUF_TEST_ROOT/"*) ;; *) return 98 ;; esac
  printf '%s|%s\n' "$1" "$2" >> "$PBUF_TEST_ROOT/writes"
  [ "$1" != "$PBUF_FAIL1" ] || return "$PBUF_FAIL_RC1"
  [ "$1" != "$PBUF_FAIL2" ] || return "$PBUF_FAIL_RC2"
  pbuf_write_value_actual "$@"
}
'''


def case(name, entry, rc=0, **options):
    return dict(name=name, entry=entry, rc=rc, **options)


cases = [
    case('governor-normal', 'set_scaling_governor', writes='cpu'),
    case('governor-empty', 'set_scaling_governor', governor='', writes='none'),
    case('governor-no-capability', 'set_scaling_governor', no_cap=True, writes='none'),
    case('governor-empty-capability', 'set_scaling_governor', capability='', writes='none'),
    case('governor-read-failure', 'set_scaling_governor', 13, cat_rc=13, writes='none'),
    case('governor-unsupported', 'set_scaling_governor', 1, governor='not-supported', writes='none'),
    case('governor-offline-cpu', 'set_scaling_governor', missing_cpu=1, writes='cpu02'),
    case('governor-not-writable', 'set_scaling_governor', 1, not_writable='cpu1', writes='cpu0'),
    case('governor-mid-error', 'set_scaling_governor', 37, fail1='cpu1', writes='cpu01'),
    case('governor-last-error', 'set_scaling_governor', 37, fail1='cpu2', writes='cpu'),
    case('governor-real-write-error', 'set_scaling_governor', 1, directory='cpu1', writes='cpu01', real_error=True),
    case('governor-cpu-enumeration-failure', 'set_scaling_governor', 19, cpu_rc=19, writes='none'),
    case('stats-normal', 'set_stats_disable', writes='stats'),
    case('stats-no-root', 'set_stats_disable', no_stats=True, writes='none'),
    case('stats-empty', 'set_stats_disable', empty_list=True, writes='none'),
    case('stats-discovery-failure', 'set_stats_disable', 17, empty_list=True, find_rc=17, writes='none'),
    case('stats-partial-discovery-failure', 'set_stats_disable', 17, find_rc=17, writes='none'),
    case('stats-first-error', 'set_stats_disable', 37, fail1='stats0', writes='stats'),
    case('stats-mid-error', 'set_stats_disable', 37, fail1='stats1', writes='stats'),
    case('stats-multiple-errors', 'set_stats_disable', 37, fail1='stats0', fail2='stats2', writes='stats'),
    case('stats-real-write-error', 'set_stats_disable', 1, directory='stats1', writes='stats', real_error=True),
    case('start-normal', 'start', writes='all'),
    case('start-offload-skip', 'start', offload_rc=1, writes='none'),
    case('start-sysctls-skip', 'start', sysctls_rc=1, writes='none'),
    case('start-profile-skip', 'start', applied=0, writes='none'),
    case('start-apply-error', 'start', 1, apply_rc=7, writes='none'),
    case('start-rps-error', 'start', 1, rps_rc=9, writes='none'),
    case('start-governor-error', 'start', 37, fail1='cpu1', writes='cpu01'),
    case('start-stats-error', 'start', 37, fail1='stats1', writes='all'),
    case('reload-governor-error', 'reload', 37, fail1='cpu1', writes='cpu01'),
    case('restart-stats-error', 'restart', 37, fail1='stats1', writes='all'),
    case('reload-wifi-error', 'reload', 9, wifi_rc=9, writes='all', wifi=1),
    case('restart-normal', 'restart', writes='all', wifi=1),
]
variants = [('candidate', body, True)]
if args.baseline:
    old = args.baseline.read_text()
    variants.append(('baseline', ''.join(function(old, name) for name in NAMES), False))
if args.mutations:
    def mutate(label, before, after, count=1):
        if body.count(before) != count:
            raise ValueError('mutation context: ' + label)
        return (label, body.replace(before, after), False)
    variants += [
        mutate('masked-governor', 'set_scaling_governor || return $?', 'set_scaling_governor'),
        mutate('masked-stats', 'set_stats_disable || return $?', 'set_stats_disable'),
        mutate('normalized-governor-error', 'set_scaling_governor || return $?', 'set_scaling_governor || return 1'),
        mutate('unsupported-success', '      return 1\n      ;;', '      return 0\n      ;;'),
        mutate('masked-capability-read', 'available_governors=$(cat "$available_file") || return $?', 'available_governors=$(cat "$available_file")'),
        mutate('masked-cpu-write', 'pbuf_write_value "$governor_file" "$scaling_governor" || return $?', 'pbuf_write_value "$governor_file" "$scaling_governor"'),
        mutate('masked-discovery', 'stats_files=$(find /sys/kernel/debug/ath11k -name stats_disable) || return $?', 'stats_files=$(find /sys/kernel/debug/ath11k -name stats_disable)'),
        mutate('lost-first-stats-error', '[ "$rc" -ne 0 ] || rc=$write_rc', 'rc=$write_rc'),
        mutate('masked-stats-write', '  return "$rc"\n', '  return 0\n'),
        mutate('broken-compatible-skip', 'wait_for_ath11k_nss_offload 5 || return 0', 'wait_for_ath11k_nss_offload 5 || return 1'),
        mutate('stats-read-splits-paths', 'while IFS= read -r stats_file;', 'while read stats_file;'),
    ]
records = []
for label, code, must_pass in variants:
    folder = args.output / label
    folder.mkdir()
    outcomes = []
    selected = cases if label != 'baseline' else [row for row in cases if row['name'] in {
        'governor-normal', 'stats-normal', 'start-normal', 'governor-unsupported',
        'governor-read-failure', 'governor-real-write-error', 'stats-real-write-error',
        'stats-partial-discovery-failure'}]
    for row in selected:
        work = (folder / row['name']).resolve()
        work.mkdir()
        (work / 'empty-path').mkdir()
        cpus = [work / ('cpu/cpu%d/cpufreq/scaling_governor' % i) for i in range(3)]
        stats = [work / ('stats/' + name + '/stats_disable') for name in ['radio 0', r'radio\one', 'radio-two']]
        keys = dict(zip(['cpu0', 'cpu1', 'cpu2', 'stats0', 'stats1', 'stats2'], cpus + stats))
        for item in cpus + stats:
            item.parent.mkdir(parents=True, exist_ok=True)
            item.write_text('before\n')
        cap = cpus[0].with_name('scaling_available_governors')
        cap.write_text(row.get('capability', 'schedutil performance') + '\n')
        if row.get('no_cap'): cap.unlink()
        if 'missing_cpu' in row: cpus[row['missing_cpu']].unlink()
        if row.get('no_stats'):
            for item in stats: item.unlink(); item.parent.rmdir()
            (work / 'stats').rmdir()
        if row.get('directory'):
            item = keys[row['directory']]; item.unlink(); item.mkdir()
        (work / 'hash_bitmap').write_text('0\n')
        (work / 'find-list').write_text('' if row.get('empty_list') else ''.join(str(item) + '\n' for item in stats))
        env = dict(os.environ, PATH=str(work / 'empty-path'), PBUF_TEST_ROOT=str(work), PBUF_GOVERNOR=row.get('governor', 'schedutil'),
                   PBUF_STATS='1', PBUF_CPUS='3', PBUF_CAT_RC=str(row.get('cat_rc', 0)),
                   PBUF_CPU_RC=str(row.get('cpu_rc', 0)), PBUF_FIND_RC=str(row.get('find_rc', 0)),
                   PBUF_NOT_WRITABLE=str(keys.get(row.get('not_writable'), work / 'unused')),
                   PBUF_FAIL1=str(keys.get(row.get('fail1'), work / 'unused')), PBUF_FAIL_RC1='37',
                   PBUF_FAIL2=str(keys.get(row.get('fail2'), work / 'unused')), PBUF_FAIL_RC2='41',
                   PBUF_OFFLOAD_RC=str(row.get('offload_rc', 0)), PBUF_SYSCTLS_RC=str(row.get('sysctls_rc', 0)),
                   PBUF_APPLIED=str(row.get('applied', 1)), PBUF_APPLY_RC=str(row.get('apply_rc', 0)),
                   PBUF_RPS_RC=str(row.get('rps_rc', 0)), PBUF_WIFI_RC=str(row.get('wifi_rc', 0)))
        script = work / 'isolated.sh'
        script.write_text(prefix + writer.replace('pbuf_write_value()', 'pbuf_write_value_actual()', 1)
                          + mapped(code) + '\n' + row['entry'] + '\n')
        command = shell_command + [str(script)]
        ran = subprocess.run(command, env=env, capture_output=True, timeout=10)
        (work / 'stdout.txt').write_bytes(ran.stdout)
        (work / 'stderr.txt').write_bytes(ran.stderr)
        errors = []
        if row.get('real_error'):
            if ran.returncode == 0: errors.append('missing-write-error')
        elif ran.returncode != row['rc']:
            errors.append('return-status')
        if ran.stdout or (ran.stderr and not row.get('real_error')): errors.append('unexpected-output')
        trace = (work / 'trace').read_text().splitlines() if (work / 'trace').exists() else []
        if trace.count('wifi') != row.get('wifi', 0): errors.append('wifi-after-error-or-missing')
        if label != 'baseline':
            writes = (work / 'writes').read_text().splitlines() if (work / 'writes').exists() else []
            paths = {'none': [], 'cpu': cpus, 'cpu02': [cpus[0], cpus[2]], 'cpu0': cpus[:1],
                     'cpu01': cpus[:2], 'stats': stats, 'all': cpus + stats}[row['writes']]
            expected = [str(item) + '|' + ('schedutil' if item in cpus else '1') for item in paths]
            if writes != expected: errors.append('write-order-path-or-value')
        outcomes.append(dict(name=row['name'], command=command,
                             expected_status='nonzero-native-shell-write-status' if row.get('real_error') else row['rc'],
                             actual_status=ran.returncode, failures=errors))
    count = sum(len(row['failures']) for row in outcomes)
    if (count == 0) != must_pass:
        raise SystemExit('unexpected variant result: ' + label + ' ' + json.dumps(outcomes))
    records.append(dict(label=label, cases=len(outcomes), failures=count, outcomes=outcomes))
if path.read_text() != source:
    raise SystemExit('production source changed during test')
summary = dict(records=records, init_sha256=hashlib.sha256(source.encode()).hexdigest(),
               asset_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               extracted_sha256={name: hashlib.sha256(function(source, name).encode()).hexdigest() for name in NAMES},
               scope='Complete extracted optional helpers/start/reload/restart; explicit sys/proc path mapping and governor writable-predicate substitution; actual writer only on isolated files with injectable errors. Configuration, discovery, readiness, NSS/RPS and Wi-Fi substitutes; no real init sourcing/system paths/device/target/runtime/performance.')
(args.output / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps([dict(label=row['label'], cases=row['cases'], failures=row['failures']) for row in records], indent=2))
