#!/usr/bin/env python3
"""Execute complete prepared storage initialization on isolated host paths."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
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
asset_paths=(Path(__file__),here/'rpcd-storage-paths/host-fixture.c',here/'nss-dp-containment/extract_prepared_c.py')
assets={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in asset_paths}
cases=[]
def case(label,position=-1,kind='directory',mode=0o700,fault=0,at=0,blocked=True,initial=False,normal=False,enabled=True):
 cases.append(dict(label=label,position=position,kind=kind,mode=mode,fault=fault,at=at,blocked=blocked,initial=initial,normal=normal,enabled=enabled))
case('new-tree',kind='missing',blocked=False,normal=True)
case('existing-private',blocked=False,normal=True)
for mode in (0o700,0o755,0o750,0o711):
 case('valid-parent-'+oct(mode),position=0,mode=mode,blocked=False,normal=True)
case('keep-earlier-block',initial=True,blocked=True)
case('off-does-not-create',kind='missing',blocked=False,normal=True,enabled=False)
case('off-does-not-follow',position=0,kind='symlink-directory',blocked=False,normal=True,enabled=False)
case('allocation-fails-before-storage',kind='missing',fault=6,blocked=False,normal=True)
for position in range(3):
 for kind in ('file','symlink-directory','symlink-file','fifo'):
  case(str(position)+'-'+kind,position=position,kind=kind)
 for mode in ((0o722,0o720,0o702,0o777) if position==0 else (0o755,0o750,0o710,0o705,0o701,0o720,0o702,0o777)):
  case(str(position)+'-mode-'+oct(mode),position=position,mode=mode)
 for fault in range(1,6):case(str(position)+'-fault-'+str(fault),fault=fault,at=position+1)

def snapshot(path):
 return sorted((str(p.relative_to(path)),p.is_dir(),p.read_bytes().hex() if p.is_file() else '') for p in path.rglob('*'))
variants=[('candidate',a.prepared,True)]
if a.baseline:variants.append(('baseline',a.baseline,False))
edits={
 'follow-final-link':(' | O_NOFOLLOW',''),
 'skip-owner':('info.st_uid != geteuid() ||','false ||'),
 'skip-mode':('(info.st_mode & (private ? 0077 : 0022))','(private && false)'),
 'ignore-close-error':('if (close(fd))\n\t\trc = -1;','(void)close(fd);'),
 'keep-trailing-slash':("while (len > 1 && name[len - 1] == '/')","while (false && len > 1 && name[len - 1] == '/')"),
 'load-after-storage-failure':('if (!checked_journal_blocked)\n\t\t\tchecked_journal_load();','checked_journal_load();'),
}
if a.mutations:variants.extend((name,a.prepared,False) for name in edits)
records=[]
for variant,prepared,expected in variants:
 tree=extract.Prepared(prepared)
 functions=tree.function('uci.c','checked_storage_init')
 if variant!='baseline':functions=tree.function('uci.c','checked_storage_dir')+functions
 functions+=tree.function('uci.c','rpc_uci_api_init')
 if variant in edits:
  before,after=edits[variant];assert functions.count(before)==1,variant
  functions=functions.replace(before,after,1)
 code=(here/'rpcd-storage-paths/host-fixture.c').read_text().replace('HOST_FUNCTIONS',functions)
 target=a.output/(variant+'.c');target.write_text(code)
 command=shlex.split(a.cc)+['-std=gnu11','-Wall','-Wextra','-Werror',str(target),'-o',str(target.with_suffix('.host'))]
 if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
 compiled=subprocess.run(command,capture_output=True,timeout=90)
 target.with_suffix('.compile.stderr').write_bytes(compiled.stderr)
 assert compiled.returncode==0,(variant,compiled.stderr.decode())
 results=[];normal=[]
 for test in cases:
  with tempfile.TemporaryDirectory(prefix='ax6-storage-') as tmp:
   base=Path(tmp);storage=base/'rpcd';external=base/'external';external.mkdir(mode=0o700)
   (external/'marker').write_text('unchanged')
   paths=[storage,storage/'snapshot-files',storage/'snapshot-delta']
   if test['kind']!='missing':
    for i,path in enumerate(paths):
     if test['position']==i:
      kind=test['kind']
      if kind=='file':path.write_text('not a directory')
      elif kind=='symlink-directory':path.symlink_to(external,target_is_directory=True)
      elif kind=='symlink-file':path.symlink_to(external/'marker')
      elif kind=='fifo':os.mkfifo(path)
      else:path.mkdir(mode=test['mode']);path.chmod(test['mode'])
      if i==0 and kind!='directory':break
     else:path.mkdir(mode=0o700)
   before=snapshot(external)
   argv=[str(target.with_suffix('.host')),str(storage),str(test['fault']),str(test['at']),str(int(test['blocked'])),str(int(test['initial'])),str(int(test['enabled']))]
   ran=subprocess.run(argv,capture_output=True,timeout=15)
   assert not ran.stderr,(variant,test['label'],ran.stderr.decode())
   result=json.loads(ran.stdout)
   assert ran.returncode in (0,1),(variant,test,result)
   result['external_changed']=snapshot(external)!=before
   result['failures']+=int(result['external_changed'])
   result['label']=test['label'];results.append(result)
   if test['normal']:normal.append((test['label'],result['blocked'],result['leaks'],result['fd_errors'],result['journal_load_calls']))
 failures=sum(r['failures'] for r in results)
 assert (failures==0)==expected,(variant,[r for r in results if r['failures']])
 records.append(dict(variant=variant,scenarios=len(cases),checks=sum(r['checks']+1 for r in results),failures=failures,
  normal_signature=hashlib.sha256(json.dumps(normal).encode()).hexdigest(),cases=results,command=command,
  generated_sha256=hashlib.sha256(code.encode()).hexdigest(),**tree.manifest()))
assert len({r['normal_signature'] for r in records})==1
for path,digest in assets.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
(a.output/'RESULT.json').write_text(json.dumps(dict(records=records,assets=assets,
 scope='Exact prepared storage functions and real host paths. I/O faults and alternate owner metadata are injected. No filesystem race, directory durability, daemon, target or router qualification.',
 target_compiled=False,hardware_accessed=False),indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ('variant','scenarios','checks','failures','normal_signature')} for r in records],indent=2))
