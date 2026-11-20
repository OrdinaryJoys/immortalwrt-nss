#!/usr/bin/env python3
"""Offline contract/behaviour test for the qca-nss-pbuf bounded readiness retry.

Covers the S5-02 (AX6-34) change in package/kernel/mac80211/files/qca-nss-pbuf.init:
  * readiness contract 0=ready / 1=transient / 2=permanent skip;
  * start()'s transient path logs user.error and schedules one bounded chain;
  * the detached chain targets cumulative delays of 15 s, 45 s and 120 s after
    the chain starts by sleeping 15/30/75 s between attempts (the cumulative
    targets are 15/45/120, not the sleep lengths), re-running the init start
    with PBUF_RETRY_ACTIVE=1 and PBUF_RETRY_OUTCOME_FILE;
  * the chain reports "profile applied" only for a child-recorded "applied"
    outcome, never from a 0 exit status alone: a permanent skip also exits 0
    without applying, and a start that returns 0 without any outcome is
    unconfirmed and is reported as such when the 120 s target attempt fails;
  * a "skipped" outcome stops the chain truthfully, and an applied outcome with
    a later non-profile error is reported with the start status;
  * flock suppresses a duplicate chain and the bounded failure logs the
    exhausted error exactly once.

The real functions are extracted from the init and executed under /bin/sh with
stubbed device state, logger, sleep and applier script; sys/proc/lock/outcome and
init paths are mapped into an isolated fixture tree. The production init is never
sourced and no system path is touched. Static gates assert the wiring/markers;
mutation variants must fail the same cases.

Limitations: the shell harness does not qualify target BusyBox ash, procd/rcS
scheduling or real boot timing; a real flock exclusion can only be exercised on
hosts that ship util-linux flock (skipped otherwise).
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / 'package/kernel/mac80211/files/qca-nss-pbuf.init'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--shell', default='/bin/sh')
parser.add_argument('--mutations', action='store_true')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
shell_command = shlex.split(args.shell)
if not shell_command or not shutil.which(shell_command[0]):
    raise SystemExit('requested shell is unavailable')
shell_command[0] = shutil.which(shell_command[0])
args.output.mkdir(parents=True, exist_ok=False)

source = INIT.read_text()
NAMES = ['pbuf_readiness_state', 'pbuf_retry_outcome', 'schedule_pbuf_retry',
         'pbuf_start_transient_failure']


def function(text, name):
    lines = text.splitlines()
    found = [i for i, line in enumerate(lines) if re.match(
        r'^[ \t]*(?:function[ \t]+' + re.escape(name) + r'\b|' + re.escape(name) + r'[ \t]*\()', line)]
    if len(found) != 1 or lines[found[0]] != name + '() {':
        raise ValueError('unsupported function header: ' + name)
    begin = found[0]
    for end in range(begin + 1, len(lines)):
        if lines[end].startswith('}'):
            if lines[end] != '}':
                raise ValueError('unsupported closing suffix: ' + name)
            return '\n'.join(lines[begin:end + 1]) + '\n'
    raise ValueError('missing closing brace: ' + name)


def mapped(text):
    replacements = {
        '/sys/module/ath11k/parameters/nss_offload': '"${PBUF_TEST_ROOT}/ath11k/nss_offload"',
        '/proc/sys/dev/nss/rps': '"${PBUF_TEST_ROOT}/nss/rps"',
        '/proc/sys/dev/nss/n2hcfg': '"${PBUF_TEST_ROOT}/nss/n2hcfg"',
        '/var/lock/qca-nss-pbuf-retry.lock': '"${PBUF_TEST_ROOT}/pbuf-retry.lock"',
        '/var/run/qca-nss-pbuf-retry.outcome': '"${PBUF_TEST_ROOT}/pbuf-retry.outcome"',
        '/etc/init.d/qca-nss-pbuf': '"${PBUF_TEST_ROOT}/init.d/qca-nss-pbuf"',
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError('path mapping context: ' + old)
        text = text.replace(old, new)
    if re.search(r'/(?:sys|proc)/|/var/(?:lock|run)/|/etc/init\.d/', text):
        raise ValueError('unmapped system path')
    return text


body = mapped(''.join(function(source, name) for name in NAMES))
STUBS = r'''
NAME=qca-nss-pbuf
logger() { printf '%s\n' "$*" >> "$LOGGER_LOG"; }
sleep() { printf '%s\n' "$1" >> "$SLEEP_LOG"; }
ath11k_device_available() { return "${DEVICE_RC:-0}"; }
flock() { printf '%s\n' "$*" >> "$FLOCK_LOG"; return "${FLOCK_RC:-0}"; }
'''
NO_FLOCK = 'flock() { printf \'%s\\n\' "$*" >> "$FLOCK_LOG"; return "${FLOCK_RC:-0}"; }\n'

# The re-run init substitute writes the outcome contract file the same way the
# real start() does, so the chain must decide from the recorded outcome and not
# from the exit status. APPLY_MODE=rc0-no-apply is the regression case: exit 0
# without applying (permanent skip / offload disabled / sysctls absent) must not
# be reported as "profile applied".
APPLIER = '''#!/bin/sh
n=$(cat "$COUNTER_FILE" 2> /dev/null || echo 0)
n=$((n + 1))
printf '%s\\n' "$n" > "$COUNTER_FILE"
printf 'call=%s retry_active=%s\\n' "$n" "${PBUF_RETRY_ACTIVE:-unset}" >> "$APPLY_LOG"
[ -n "${PBUF_RETRY_OUTCOME_FILE:-}" ] || exit 99
case "${APPLY_MODE:-applied}" in
  applied)
    [ "$n" -le "${FAIL_ATTEMPTS:-0}" ] && exit 1
    printf 'applied\\n' > "$PBUF_RETRY_OUTCOME_FILE"
    exit "${APPLY_RC:-0}"
    ;;
  rc0-no-apply)
    [ "$n" -le "${FAIL_ATTEMPTS:-0}" ] && exit 1
    exit 0
    ;;
  skipped)
    printf 'skipped\\n' > "$PBUF_RETRY_OUTCOME_FILE"
    exit 0
    ;;
  *)
    exit 1
    ;;
esac
'''

records = []


def record(name, ok, detail):
    records.append(dict(name=name, result='PASS' if ok else 'FAIL', detail=detail))
    if not ok:
        raise SystemExit('case failed: ' + name + ': ' + json.dumps(detail))


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def run_scenario(folder, scenario, env, keep_flock=True, stale_outcome=None):
    folder.mkdir(parents=True, exist_ok=True)
    for log in ('logger', 'sleep', 'flock', 'applier', 'schedule', 'counter'):
        (folder / (log + '.log')).write_text('')
    (folder / 'counter.log').write_text('0\n')
    if stale_outcome is not None:
        (folder / 'pbuf-retry.outcome').write_text(stale_outcome + '\n')
    prefix = STUBS if keep_flock else STUBS.replace(NO_FLOCK, '')
    script = folder / 'scenario.sh'
    script.write_text(prefix + body + '\n' + scenario + '\n')
    script.chmod(0o755)
    full_env = dict(os.environ,
                    PBUF_TEST_ROOT=str(folder),
                    LOGGER_LOG=str(folder / 'logger.log'),
                    SLEEP_LOG=str(folder / 'sleep.log'),
                    FLOCK_LOG=str(folder / 'flock.log'),
                    SCHEDULE_LOG=str(folder / 'schedule.log'),
                    APPLY_LOG=str(folder / 'applier.log'),
                    COUNTER_FILE=str(folder / 'counter.log'))
    full_env.update(env)
    ran = subprocess.run(shell_command + [str(script)], env=full_env,
                         capture_output=True, timeout=30)
    (folder / 'stdout.txt').write_bytes(ran.stdout)
    (folder / 'stderr.txt').write_bytes(ran.stderr)
    return ran, folder


def read_lines(folder, name):
    return [line for line in (folder / (name + '.log')).read_text().splitlines() if line]


def prepare_state(folder, device=True, param=None, rps=True, n2hcfg=True):
    ath11k = folder / 'ath11k'
    ath11k.mkdir(parents=True, exist_ok=True)
    if param is not None:
        write(ath11k / 'nss_offload', param + '\n')
    nss = folder / 'nss'
    nss.mkdir(parents=True, exist_ok=True)
    for name, present in (('rps', rps), ('n2hcfg', n2hcfg)):
        if present:
            (nss / name).mkdir(exist_ok=True)
    return dict(DEVICE_RC='0' if device else '1')


def readiness_case(folder, expected, **state):
    env = prepare_state(folder, **state)
    ran, work = run_scenario(folder, 'pbuf_readiness_state\nprintf "%s\\n" "$?"\n', env)
    lines = ran.stdout.decode().split()
    ok = ran.returncode == 0 and lines and int(lines[-1]) == expected
    record('readiness-' + folder.name, ok,
           dict(expected=expected, stdout=ran.stdout.decode(), stderr=ran.stderr.decode()))


def outcome_case(folder, value, active=True, file_set=True, write_failure=False):
    env = dict(DEVICE_RC='0')
    if active:
        env['PBUF_RETRY_ACTIVE'] = '1'
    if file_set:
        outcome = (folder / 'missing-dir' / 'outcome') if write_failure else (folder / 'outcome')
        env['PBUF_RETRY_OUTCOME_FILE'] = str(outcome)
    ran, work = run_scenario(folder, 'pbuf_retry_outcome %s\n' % value, env)
    logs = read_lines(work, 'logger')
    outcome = folder / 'outcome'
    if active and file_set and not write_failure:
        ok = (ran.returncode == 0 and not ran.stdout and not ran.stderr
              and outcome.exists() and outcome.read_text() == value + '\n' and not logs)
    elif write_failure:
        ok = (ran.returncode == 0 and not outcome.exists()
              and any('cannot record the retry outcome' in line for line in logs))
    else:
        ok = (ran.returncode == 0 and not outcome.exists() and not logs)
    record('outcome-' + folder.name, ok,
           dict(logs=logs, exists=outcome.exists(), stdout=ran.stdout.decode(),
                stderr=ran.stderr.decode()))


def transient_case(folder, active):
    env = dict(prepare_state(folder), PBUF_RETRY_ACTIVE='1' if active else '')
    scenario = ('schedule_pbuf_retry() { printf "scheduled\\n" >> "$SCHEDULE_LOG"; }\n'
                'pbuf_start_transient_failure\n')
    ran, work = run_scenario(folder, scenario, env)
    logs = read_lines(work, 'logger')
    scheduled = read_lines(work, 'schedule')
    if active:
        ok = (ran.returncode == 0 and not scheduled
              and any('still transient' in line for line in logs)
              and not any('user.error' in line for line in logs))
    else:
        ok = (ran.returncode == 0 and len(scheduled) == 1 and any(
            'user.error' in line
            and 'scheduling a bounded retry chain (cumulative 15/45/120s targets)' in line
            for line in logs))
    record('transient-active-' + str(active).lower(), ok,
           dict(logs=logs, scheduled=scheduled, stderr=ran.stderr.decode()))


def chain_case(folder, mode='applied', fail_attempts=0, expected_sleeps=(15,),
               expected_calls=1, expected_applied=None, expected_applied_rc=None,
               expected_skip=0, expected_unconfirmed=0, expected_exhausted=0,
               apply_rc=0, flock_rc=0, applier=True, keep_flock=True,
               stale_outcome=None):
    if applier:
        write(folder / 'init.d/qca-nss-pbuf', APPLIER, 0o755)
    run_env = dict(APPLY_MODE=mode, FAIL_ATTEMPTS=str(fail_attempts),
                   APPLY_RC=str(apply_rc), FLOCK_RC=str(flock_rc))
    ran, work = run_scenario(folder, 'schedule_pbuf_retry\nwait\n', run_env,
                             keep_flock=keep_flock, stale_outcome=stale_outcome)
    sleeps = read_lines(work, 'sleep')
    calls = read_lines(work, 'applier')
    logs = read_lines(work, 'logger')
    applied_logs = [line for line in logs if 'profile applied by the bounded retry' in line]
    skip_logs = [line for line in logs if 'the profile is a permanent skip' in line]
    unconfirmed = [line for line in logs if 'without confirming a profile apply' in line]
    exhausted = [line for line in logs if 'the profile apply was not confirmed' in line]

    if expected_applied is None:
        applied_ok = not applied_logs
    else:
        applied_ok = (len(applied_logs) == 1
                      and '(cumulative target %ds)' % expected_applied in applied_logs[0])
        if expected_applied_rc is not None:
            applied_ok = applied_ok and ('start returned %d' % expected_applied_rc
                                         in applied_logs[0])
        else:
            applied_ok = applied_ok and 'start returned' not in applied_logs[0]

    ok = (ran.returncode == 0
          and sleeps == [str(item) for item in expected_sleeps]
          and len(calls) == expected_calls
          and all('retry_active=1' in line for line in calls)
          and applied_ok
          and len(skip_logs) == expected_skip
          and len(unconfirmed) == expected_unconfirmed
          and len(exhausted) == expected_exhausted
          and (expected_exhausted == 0 or 'not confirmed' in exhausted[0])
          and not (work / 'pbuf-retry.outcome').exists())
    record('chain-' + folder.name, ok,
           dict(sleeps=sleeps, calls=calls, applied_logs=applied_logs,
                skip_logs=skip_logs, unconfirmed=unconfirmed,
                exhausted=exhausted, stderr=ran.stderr.decode()))


def real_flock_case(folder):
    flock_bin = shutil.which('flock')
    if not flock_bin:
        records.append(dict(name='chain-real-flock-exclusion', result='SKIP',
                            detail='util-linux flock is unavailable on this host'))
        return
    write(folder / 'init.d/qca-nss-pbuf', APPLIER, 0o755)
    lock_path = folder / 'pbuf-retry.lock'
    lock_path.write_text('')
    holder = open(lock_path, 'w')
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ran, work = run_scenario(folder, 'schedule_pbuf_retry\nwait\n',
                                 dict(APPLY_MODE='applied'), keep_flock=False)
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()
    sleeps = read_lines(work, 'sleep')
    calls = read_lines(work, 'applier')
    ok = ran.returncode == 0 and not sleeps and not calls
    record('chain-real-flock-exclusion', ok,
           dict(sleeps=sleeps, calls=calls, stderr=ran.stderr.decode()))


def missing_flock_case(folder):
    write(folder / 'init.d/qca-nss-pbuf', APPLIER, 0o755)
    empty = folder / 'empty-path'
    empty.mkdir(parents=True)
    ran, work = run_scenario(folder, 'schedule_pbuf_retry\nwait\n',
                             dict(APPLY_MODE='applied', PATH=str(empty)), keep_flock=False)
    logs = read_lines(work, 'logger')
    sleeps = read_lines(work, 'sleep')
    ok = ran.returncode == 0 and not sleeps and any(
        'flock applet is missing' in line for line in logs)
    record('chain-missing-flock', ok,
           dict(logs=logs, sleeps=sleeps, stderr=ran.stderr.decode()))


def missing_applier_case(folder):
    ran, work = run_scenario(folder, 'schedule_pbuf_retry\nwait\n',
                             dict(APPLY_MODE='applied'))
    logs = read_lines(work, 'logger')
    sleeps = read_lines(work, 'sleep')
    ok = ran.returncode == 0 and not sleeps and any(
        'is not executable' in line for line in logs)
    record('chain-missing-applier', ok,
           dict(logs=logs, sleeps=sleeps, stderr=ran.stderr.decode()))


def static_gates():
    text = INIT.read_text()
    checks = {
        'single-readiness-definition': text.count('pbuf_readiness_state() {') == 1,
        'readiness-wired-in-start': text.count('pbuf_readiness_state\n') == 2,
        'outcome-helper-definition': text.count('pbuf_retry_outcome() {') == 1,
        'outcome-applied-once': text.count('pbuf_retry_outcome applied') == 1,
        'outcome-skipped-twice': text.count('pbuf_retry_outcome skipped') == 2,
        'outcome-gated-by-retry-active': text.count('${PBUF_RETRY_ACTIVE:-0}" = "1"') == 2,
        'outcome-gated-by-file-env': text.count('${PBUF_RETRY_OUTCOME_FILE:-}') == 1,
        'outcome-removed-twice': text.count('rm -f "$outcome_file"') == 2,
        'outcome-required-for-applied-claim': text.count('case "$outcome" in') == 1,
        'transient-helper-definition': text.count('pbuf_start_transient_failure() {') == 1,
        'transient-helper-wired-thrice': text.count('pbuf_start_transient_failure') == 4,
        'transient-return-1-twice': text.count('pbuf_start_transient_failure; return 1') == 2,
        'single-scheduler-definition': text.count('schedule_pbuf_retry() {') == 1,
        'scheduler-called-once': text.count('  schedule_pbuf_retry\n') == 1,
        'bounded-cumulative-targets': text.count('for target in 15 45 120; do') == 1,
        'cumulative-sleep-booking': text.count('sleep $((target - delay))') == 1,
        'retry-active-and-outcome-env': text.count(
            'PBUF_RETRY_ACTIVE=1 PBUF_RETRY_OUTCOME_FILE="$outcome_file"') == 1,
        'flock-single-chain': text.count('flock -n 9 || exit 0') == 1,
        'no-unbounded-loop': 'while true' not in text,
        'fast-path-waits-retained': text.count('wait_for_ath11k_nss_offload 5 || {') == 1
        and text.count('wait_for_nss_sysctls 5 || {') == 1,
        'unconfirmed-zero-exit-error': text.count('without confirming a profile apply') == 1,
        'skip-outcome-stops-chain': text.count('the profile is a permanent skip') == 1,
        'exhausted-error-once': text.count('the profile apply was not confirmed') == 1,
        'no-false-applied-message': text.count('profile applied by the bounded retry') == 2,
    }
    failed = {name: value for name, value in checks.items() if not value}
    record('static-gates', not failed, dict(failed=sorted(failed)))
    ran = subprocess.run(['sh', '-n', str(INIT)], capture_output=True)
    record('sh-n', ran.returncode == 0, dict(stderr=ran.stderr.decode()))


# --- readiness contract ---------------------------------------------------
readiness_case(args.output / 'no-device', 2, device=False, param='1')
readiness_case(args.output / 'param-missing', 1, device=True, param=None)
readiness_case(args.output / 'param-zero', 2, device=True, param='0')
readiness_case(args.output / 'param-n', 2, device=True, param='N')
readiness_case(args.output / 'sysctls-missing', 1, device=True, param='1', rps=False)
readiness_case(args.output / 'half-sysctls', 1, device=True, param='1', n2hcfg=False)
readiness_case(args.output / 'ready', 0, device=True, param='1')
for value in ('Y', 'y', 'yes', 'true', 'on'):
    readiness_case(args.output / ('value-' + value), 0, device=True, param=value)

# --- outcome recording helper --------------------------------------------
outcome_case(args.output / 'applied', 'applied')
outcome_case(args.output / 'skipped', 'skipped')
outcome_case(args.output / 'inactive', 'applied', active=False)
outcome_case(args.output / 'no-file-var', 'applied', file_set=False)
outcome_case(args.output / 'write-failure', 'applied', write_failure=True)

# --- transient reporting --------------------------------------------------
transient_case(args.output / 'transient-initial', active=False)
transient_case(args.output / 'transient-retry', active=True)

# --- bounded retry chain --------------------------------------------------
chain_case(args.output / 'success-first-try', 'applied', 0, (15,), 1, expected_applied=15)
chain_case(args.output / 'success-third-try', 'applied', 2, (15, 30, 75), 3,
           expected_applied=120)
chain_case(args.output / 'applied-late-error', 'applied', 0, (15,), 1,
           expected_applied=15, expected_applied_rc=7, apply_rc=7)
chain_case(args.output / 'exhausted', 'applied', 3, (15, 30, 75), 3, expected_exhausted=1)
chain_case(args.output / 'false-success-rc0-no-apply', 'rc0-no-apply', 0, (15, 30, 75), 3,
           expected_unconfirmed=3, expected_exhausted=1)
chain_case(args.output / 'false-success-stale-outcome', 'rc0-no-apply', 0, (15, 30, 75), 3,
           expected_unconfirmed=3, expected_exhausted=1, stale_outcome='applied')
chain_case(args.output / 'permanent-skip', 'skipped', 0, (15,), 1, expected_skip=1)
chain_case(args.output / 'duplicate-suppressed', 'applied', 0, (), 0, flock_rc=1)
real_flock_case(args.output / 'real-flock-exclusion')
missing_flock_case(args.output / 'missing-flock')
missing_applier_case(args.output / 'missing-applier')

# --- static gates ---------------------------------------------------------
static_gates()

# --- mutations ------------------------------------------------------------
MUTATIONS = [
    ('readiness-masks-missing-device',
     '  if ! ath11k_device_available; then\n    return 2\n  fi\n\n', ''),
    ('readiness-masks-param-zero',
     '    *) return 2 ;;\n', '    *) return 0 ;;\n'),
    ('readiness-masks-sysctl-transient',
     '    return 1\n  fi\n\n  return 0\n}\n', '    :\n  fi\n\n  return 0\n}\n'),
    ('no-retry-schedule',
     '  schedule_pbuf_retry\n}\n', '  :\n}\n'),
    ('no-bounded-targets',
     'for target in 15 45 120; do', 'for target in 15; do'),
    ('no-retry-active-env',
     'PBUF_RETRY_ACTIVE=1 PBUF_RETRY_OUTCOME_FILE="$outcome_file"',
     'PBUF_RETRY_ACTIVE=1'),
    ('rc-only-success',
     '      case "$outcome" in\n', '      case "applied" in\n'),
    ('no-outcome-cleanup',
     '      rm -f "$outcome_file"\n      PBUF_RETRY_ACTIVE=1',
     '      PBUF_RETRY_ACTIVE=1'),
    ('skip-does-not-stop',
     '        skipped)\n          logger -t "$NAME" -p user.notice \\\n'
     '            "NSS pbuf bounded retry stopped: the profile is a permanent skip '
     '(no ath11k device, nss_offload=0 or pbuf disabled); nothing was applied"\n'
     '          exit 0\n          ;;\n',
     '        skipped)\n          :\n'),
]
if args.mutations:
    candidate_cases = (
        ('no-device', lambda f: readiness_case(f, 2, device=False, param='1')),
        ('param-zero', lambda f: readiness_case(f, 2, device=True, param='0')),
        ('sysctls-missing', lambda f: readiness_case(f, 1, device=True, param='1', rps=False)),
        ('transient-initial', lambda f: transient_case(f, active=False)),
        ('success-first-try', lambda f: chain_case(
            f, 'applied', 0, (15,), 1, expected_applied=15)),
        ('false-success', lambda f: chain_case(
            f, 'rc0-no-apply', 0, (15, 30, 75), 3,
            expected_unconfirmed=3, expected_exhausted=1)),
        ('permanent-skip', lambda f: chain_case(
            f, 'skipped', 0, (15,), 1, expected_skip=1)),
        ('stale-outcome', lambda f: chain_case(
            f, 'rc0-no-apply', 0, (15, 30, 75), 3,
            expected_unconfirmed=3, expected_exhausted=1, stale_outcome='applied')),
    )
    for label, before, after in MUTATIONS:
        if body.count(before) != 1:
            raise SystemExit('mutation context: ' + label)
        mutated = body.replace(before, after)
        saved_body, saved_records = body, len(records)
        body = mutated
        row = args.output / ('mutation-' + label)
        failures = 0
        detected = []
        try:
            for case_name, factory in candidate_cases:
                try:
                    factory(row / case_name)
                except SystemExit:
                    failures += 1
                    detected.append(case_name)
        finally:
            body = saved_body
            del records[saved_records:]
        record('mutation-' + label, failures > 0,
               dict(failures=failures, detected=detected))

if INIT.read_text() != source:
    raise SystemExit('production init changed during test')

passed = sum(1 for row in records if row['result'] == 'PASS')
failed = sum(1 for row in records if row['result'] == 'FAIL')
skipped = sum(1 for row in records if row['result'] == 'SKIP')
summary = dict(records=records, passed=passed, failed=failed, skipped=skipped,
               init_sha256=hashlib.sha256(source.encode()).hexdigest(),
               test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               scope='Extracted readiness/outcome/retry functions executed under /bin/sh with mapped '
                     'sys/proc/lock/outcome/init paths plus stubbed device state, logger, sleep and '
                     'applier; no production init sourcing, real sysfs/proc, real boot, rcS/procd or '
                     'device behaviour is qualified.')
(args.output / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(dict(passed=passed, failed=failed, skipped=skipped), indent=2))
if failed:
    sys.exit(1)
