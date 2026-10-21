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
    # Deliberately support only the current column-zero, final simple wrappers.
    lines=text.splitlines()
    spans=[]
    for name in ('reload','restart'):
        declaration=r'^[ \t]*(?:function[ \t]+'+name+r'\b|'+name+r'[ \t]*\()'
        found=[i for i,line in enumerate(lines) if re.match(declaration,line)]
        if len(found)!=1:raise ValueError(name+': definition count')
        begin=found[0]
        if lines[begin]!=name+'() {':raise ValueError(name+': unsupported header')
        for end in range(begin+1,len(lines)):
            line=lines[end]
            if line.lstrip().startswith('}'):
                if line!='}':raise ValueError(name+': unsupported closing line')
                break
            if line.strip() and not line[0].isspace():
                raise ValueError(name+': unsupported body line')
        else:
            raise ValueError(name+': missing closing line')
        spans.append((begin,end))
    if spans[0][1]>=spans[1][0]:raise ValueError('wrapper order or overlap')
    outside=lines[spans[0][1]+1:spans[1][0]]+lines[spans[1][1]+1:]
    if any(line.strip() for line in outside):raise ValueError('extra wrapper-tail content')
    return ''.join('\n'.join(lines[begin:end+1])+'\n' for begin,end in spans)

def extraction_controls(source,candidate):
    def changed(old,new):
        if source.count(old)!=1:raise ValueError('extraction control context: '+old)
        return source.replace(old,new,1)

    guard='  start || return $?\n'
    controls=[
        ('current',source,candidate),
        ('old-start-body',changed(guard,'  start\n'),candidate.replace(guard,'  start\n')),
        ('blank-separators',changed('\n\nrestart() {','\n\n\nrestart() {')+'\n',candidate),
    ]
    for name,last in (('reload','  reload_wifi'),('restart','  reload')):
        header=name+'() {'
        closing=last+'\n}'
        for label,old,new in [
            ('header-redirection',header,header+' < /dev/null'),
            ('header-inline-command',header,header+' :'),
            ('header-spaced-parentheses',header,name+' () {'),
            ('header-function-keyword',header,'function '+header),
            ('header-indentation',header,' '+header),
            ('closing-redirection',closing,closing+' < "$PBUF_INPUT"'),
            ('closing-extra-command',closing,closing+'; :'),
            ('closing-comment',closing,closing+' # unsupported'),
            ('missing-closing-line',closing,last),
        ]:
            controls.append((name+'-'+label,changed(old,new),None))
        controls += [
            (name+'-duplicate',source+'\n'+header+'\n  :\n}\n',None),
            (name+'-duplicate-alternate',source+'\nfunction '+name+' {\n  :\n}\n',None),
        ]
    controls += [
        ('interstitial-command',changed('\n\nrestart() {','\n:\nrestart() {'),None),
        ('trailing-command',source+'\n:\n',None),
    ]
    records=[]
    for label,text,expected in controls:
        try:
            extracted=wrappers(text)
        except ValueError as error:
            if expected is not None:raise SystemExit('unexpected extraction rejection: '+label)
            records.append(dict(label=label,result='rejected',reason=str(error)))
        else:
            if expected is None or extracted!=expected:
                raise SystemExit('unexpected extraction acceptance/content: '+label)
            records.append(dict(label=label,result='accepted'))
    return dict(cases=len(records),accepted=sum(r['result']=='accepted' for r in records),
        rejected=sum(r['result']=='rejected' for r in records),failures=0,records=records)

candidate=wrappers(source)
extraction=extraction_controls(source,candidate)
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
    extraction_controls=extraction,
    init_sha256=hashlib.sha256(source.encode()).hexdigest(),
    test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='actual wrappers only; start/Wi-Fi are status/call models; no production init is sourced or executed'),indent=2)+'\n')
print(json.dumps(records,indent=2))
