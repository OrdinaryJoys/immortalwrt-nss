#!/usr/bin/env python3
"""Actual reload/restart wrappers with start/Wi-Fi status substitutes only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline',type=Path,help='old init source, read as data only')
p.add_argument('--shell',default='/bin/sh')
p.add_argument('--mutations',action='store_true')
p.add_argument('--output',type=Path,required=True)
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
path=root/'package/kernel/mac80211/files/qca-nss-pbuf.init'
source=path.read_text()

def wrappers(text):
    result=''
    for name in ('reload','restart'):
        found=re.findall(r'^'+name+r'\(\) \{\n.*?^\}',text,re.M|re.S)
        if len(found)!=1:raise ValueError(name)
        result+=found[0]+'\n'
    return result

candidate=wrappers(source)
variants=[('candidate',candidate,True)]
if args.baseline:variants.append(('baseline',wrappers(args.baseline.read_text()),False))
if args.mutations:
    anchor='start || return $?'
    if candidate.count(anchor)!=1:raise ValueError('guard context')
    variants += [
        ('masked-start',candidate.replace(anchor,'start'),False),
        ('wrong-errno',candidate.replace(anchor,'start || return 1'),False),
        ('unconditional-wifi',candidate.replace(anchor,'start\n  rc=$?\n  reload_wifi\n  return "$rc"'),False),
        ('masked-wifi',candidate.replace('  reload_wifi\n','  reload_wifi\n  return 0\n'),False),
        ('masked-restart',candidate.replace('  reload\n','  reload\n  return 0\n'),False),
    ]
prefix='''
start() { start_calls=$((start_calls+1)); return "$START_RC"; }
reload_wifi() { wifi_calls=$((wifi_calls+1)); return "$WIFI_RC"; }
'''
main='''
failures=0; checks=0; cases=0
for entry in reload restart; do
  for START_RC in 0 1 7 75; do
    for WIFI_RC in 0 2 9; do
      start_calls=0; wifi_calls=0; cases=$((cases+1))
      "$entry"; rc=$?
      expected=$START_RC; expected_wifi=0
      if [ "$START_RC" -eq 0 ]; then expected=$WIFI_RC; expected_wifi=1; fi
      checks=$((checks+3))
      [ "$rc" -eq "$expected" ] || failures=$((failures+1))
      [ "$start_calls" -eq 1 ] || failures=$((failures+1))
      [ "$wifi_calls" -eq "$expected_wifi" ] || failures=$((failures+1))
    done
  done
done
printf '{"cases":%s,"checks":%s,"failures":%s}\\n' "$cases" "$checks" "$failures"
[ "$failures" -eq 0 ]
'''
records=[]
for label,body,expected in variants:
    script=args.output/(label+'.sh')
    script.write_text(prefix+body+main)
    command=shlex.split(args.shell)+[str(script)]
    ran=subprocess.run(command,capture_output=True,timeout=20)
    (args.output/(label+'.stdout')).write_bytes(ran.stdout)
    (args.output/(label+'.stderr')).write_bytes(ran.stderr)
    result=json.loads(ran.stdout)
    if ran.stderr or ran.returncode!=(0 if expected else 1) or (result['failures']==0)!=expected:
        raise SystemExit('unexpected '+label)
    records.append(dict(label=label,command=command,**result))
assert path.read_text()==source
(args.output/'RESULT.json').write_text(json.dumps(dict(records=records,
    init_sha256=hashlib.sha256(source.encode()).hexdigest(),
    test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='actual wrappers only; start/Wi-Fi are status/call models; no production init is sourced or executed'),indent=2)+'\n')
print(json.dumps(records,indent=2))
