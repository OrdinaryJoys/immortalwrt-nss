#!/usr/bin/env python3
"""Actual prepared writer with isolated host files and bounded syscall faults."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile

here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('extract_c',here/'nss-dp-containment/extract_prepared_c.py')
extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared',type=Path);p.add_argument('--baseline',type=Path)
p.add_argument('--output',type=Path,required=True);p.add_argument('--cc',default='cc')
p.add_argument('--sanitize',action='store_true');p.add_argument('--mutations',action='store_true')
a=p.parse_args();a.output.mkdir(exist_ok=False)
asset_paths=(Path(__file__),here/'rpcd-journal-publication/host-fixture.c',here/'nss-dp-containment/extract_prepared_c.py')
assets={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in asset_paths}
cases=[]
for state in (1,2,5):
 for previous in (False,True):
  for mask in ('022','077'):cases.append(dict(state=state,kind=0,fault=0,previous=previous,mask=mask,normal=True))
 for kind in range(1,8):cases.append(dict(state=state,kind=kind,fault=0,previous=True,mask='022',normal=False))
 for fault in range(1,10):cases.append(dict(state=state,kind=0,fault=fault,previous=True,mask='022',normal=False))

def identity(path):
 try:info=path.lstat()
 except FileNotFoundError:return None
 if stat.S_ISLNK(info.st_mode):value=os.readlink(path)
 elif stat.S_ISREG(info.st_mode):value=path.read_bytes().hex()
 else:value='special'
 return (info.st_ino,stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),value)

variants=[('candidate',a.prepared,True)]
if a.baseline:variants.append(('baseline',a.baseline,False))
edits={
 'reuse-truncate':('O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC','O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC'),
 'nofollow-only':('O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC','O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC'),
 'delete-unowned-temporary':('if (fd < 0) {','if (fd < 0) {\n\t\tunlink(tmp);'),
 'report-open-success':('checked_journal_blocked = true;\n\t\treturn -1;\n\t}\n\twhile (off < len)',
    'checked_journal_blocked = true;\n\t\treturn 0;\n\t}\n\twhile (off < len)'),
}
if a.mutations:variants.extend((name,a.prepared,False) for name in edits)
records=[]
for variant,prepared,expected in variants:
 tree=extract.Prepared(prepared);text=tree.read('uci.c')
 writer=tree.function('uci.c','checked_journal_write')
 if variant in edits:
  before,after=edits[variant];assert writer.count(before)==1,variant
  writer=writer.replace(before,after,1)
 functions=''.join(tree.function('uci.c',name) for name in ('checked_state_name','checked_now_ms','checked_journal_clear',
  'checked_storage_dir','checked_storage_init'))+writer
 code=(here/'rpcd-journal-publication/host-fixture.c').read_text().replace('HOST_STRUCTURES',
  extract.structure(text,'checked_state','enum')+extract.structure(text,'checked_transaction')).replace('HOST_FUNCTIONS',functions)
 target=a.output/(variant+'.c');target.write_text(code)
 command=shlex.split(a.cc)+['-std=gnu11','-Wall','-Wextra','-Werror',str(target),'-o',str(target.with_suffix('.host'))]
 if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
 compiled=subprocess.run(command,capture_output=True,timeout=90)
 target.with_suffix('.compile.stderr').write_bytes(compiled.stderr)
 assert compiled.returncode==0,(variant,compiled.stderr.decode())
 results=[];normal=[]
 for test in cases:
  with tempfile.TemporaryDirectory(prefix='ax6-publication-',dir='/tmp') as tmp:
   base=Path(tmp);storage=base/'rpcd';storage.mkdir(mode=0o700)
   for name in ('snapshot-files','snapshot-delta'):(storage/name).mkdir(mode=0o700)
   journal=storage/'checked.journal';temporary=storage/'checked.journal.tmp';other=base/'unrelated'
   prior=b'Previous journal must survive any rejected publication.\n';marker=b'Unrelated data must remain unchanged.\n'
   if test['previous']:journal.write_bytes(prior)
   kind=test['kind']
   if kind==1:temporary.write_bytes(marker)
   elif kind==2:other.write_bytes(marker);temporary.symlink_to(other)
   elif kind==3:other.write_bytes(marker);os.link(other,temporary)
   elif kind==4:os.link(journal,temporary)
   elif kind==5:temporary.symlink_to(other)
   elif kind==6:os.mkfifo(temporary,0o600)
   elif kind==7:temporary.mkdir(mode=0o700)
   before=identity(temporary);other_before=identity(other)
   ran=subprocess.run([str(target.with_suffix('.host')),str(storage),str(kind),str(test['fault']),str(test['state']),test['mask']],capture_output=True,timeout=15)
   assert ran.returncode==0 and not ran.stderr,(variant,test,ran.returncode,ran.stderr.decode())
   result=json.loads(ran.stdout)
   success=kind==0 and test['fault'] in (0,2)
   expectations=[(result['result']==0)==success,result['blocked']==(not success),
    result['fd_errors']==0,result['fd_leaks']==0,result['cloexec_errors']==0,result['unsafe_fifo']==0,
    identity(other)==other_before]
   if success:
    data=journal.read_bytes() if journal.is_file() else b''
    expectations+=[not temporary.exists(),b'id='+b'a'*32+b'\n' in data,b'files=2\ncleanup=1\n' in data,
     stat.S_IMODE(journal.stat().st_mode)==0o600 if journal.exists() else False]
   else:
    expectations+=[journal.read_bytes()==prior if journal.is_file() else not test['previous']]
    if kind:expectations+=[identity(temporary)==before]
    elif test['fault']==9:expectations+=[temporary.is_file()]
    else:expectations+=[identity(temporary) is None]
   failures=sum(not value for value in expectations);checks=len(expectations)
   results.append(dict(test=test,**result,checks=checks,failures=failures,
    unrelated_preserved=identity(other)==other_before,temporary_preserved=identity(temporary)==before))
   if test['normal']:
    normal.append((test['state'],test['previous'],test['mask'],result['result'],result['blocked'],
     journal.is_file(),temporary.exists(),identity(other)==other_before))
 failures=sum(row['failures'] for row in results)
 assert (failures==0)==expected,(variant,[r for r in results if r['failures']])
 records.append(dict(variant=variant,scenarios=len(cases),checks=sum(r['checks'] for r in results),failures=failures,cases=results,
  normal_signature=hashlib.sha256(json.dumps(normal).encode()).hexdigest(),command=command,
  generated_sha256=hashlib.sha256(code.encode()).hexdigest(),**tree.manifest()))
assert len({r['normal_signature'] for r in records})==1
for path,digest in assets.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
(a.output/'RESULT.json').write_text(json.dumps(dict(records=records,assets=assets,
 scope='Exact prepared writer/storage functions and actual host files. Syscall errors are injected; unsafe old FIFO open is intercepted before blocking. No daemon, parent-directory races, flash/power loss or target qualification.',
 target_compiled=False,hardware_accessed=False),indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ('variant','scenarios','checks','failures','normal_signature')} for r in records],indent=2))
