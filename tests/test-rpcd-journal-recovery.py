#!/usr/bin/env python3
"""Run complete prepared journal functions against real isolated host files."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('extract_c',HERE/'nss-dp-containment/extract_prepared_c.py')
extract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared',type=Path)
parser.add_argument('--baseline',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cc',default='cc')
parser.add_argument('--sanitize',action='store_true')
parser.add_argument('--mutations',action='store_true')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
corpus=args.output/'corpus'
corpus.mkdir()
assets={p:p.read_bytes() for p in (Path(__file__),HERE/'rpcd-journal-recovery/host-fixture.c',HERE/'nss-dp-containment/extract_prepared_c.py')}
defaults=dict(version='1',id='a'*32,request='b'*32,sid='c'*32,state='pending',files='1',cleanup='0',created_ms='1234')
cases=[]


def document(fields,order=None):
    return ''.join(k+'='+fields[k]+'\n' for k in (order or fields)).encode()


def add(label,data=None,expected=3,kind=0,fault=0,files=1,cleanup=0,normal=False):
    index=len(cases)
    name=f'{index:04d}.input'
    (corpus/name).write_bytes(document(defaults) if data is None else data)
    cases.append(dict(label=label,path=name,expected=expected,kind=kind,fault=fault,files=files,cleanup=cleanup,normal=normal))


for state in ('applying','pending','unknown','confirmed','rolled_back'):
    for files in (0,1,4294967295):
        for cleanup in (0,1):
            fields={**defaults,'state':state,'files':str(files),'cleanup':str(cleanup)}
            add(f'valid-{state}-{files}-{cleanup}',document(fields),1 if state in ('applying','pending','unknown') else 2,
                files=files,cleanup=cleanup,normal=True)
for offset in range(8):
    order=list(defaults)[offset:]+list(defaults)[:offset]
    add(f'valid-order-{offset}',document(defaults,order),1,normal=True)
for stamp in ('0','18446744073709551615','0000123'):
    add('valid-stamp-'+stamp,document({**defaults,'created_ms':stamp}),1,normal=True)
for state in ('pending','confirmed'):
    fields={**defaults,'state':state}
    for key in defaults:
        add(f'missing-{state}-{key}',document({k:v for k,v in fields.items() if k!=key}))
        add(f'duplicate-{state}-{key}',document(fields)+(key+'='+fields[key]+'\n').encode())
        add(f'empty-{state}-{key}',document({**fields,key:''}))
    bad_values={
        'version':['0','2','01','+1','1x'],
        'id':['a'*31,'a'*33,'g'*32], 'request':['b'*31,'B'*32], 'sid':['c'*31,'z'*32,'C'*32],
        'state':['idle','success','pending '],
        'files':['-1','+1',' 1','1 ','1x','4294967296','18446744073709551616'],
        'cleanup':['2','00','-1'], 'created_ms':['-1','+1',' 1','1x','18446744073709551616']}
    for key,values in bad_values.items():
        for index,value in enumerate(values):
            add(f'invalid-{state}-{key}-{index}',document({**fields,key:value}))
    data=document(fields)
    add(f'embedded-nul-{state}',data+b'\0ignored=true\n')
    add(f'unknown-field-{state}',data+b'new_version_field=1\n')
    add(f'blank-line-{state}',data+b'\n')
    add(f'trailing-text-{state}',data+b'garbage\n')
    for size in (1022,1023,1024,4096):
        add(f'oversize-{state}-{size}',data+b'x'*(size-len(data)))
data=document(defaults)
for cut in range(len(data)):
    add(f'truncated-at-{cut}',data[:cut])
add('absent',b'',0,kind=1)
add('symlink',expected=3,kind=2)
add('directory',b'',3,kind=3)
add('fifo',b'',3,kind=4)
for label,fault,expected in (('short-reads',1,1),('eintr-once',2,1),('read-eio',3,3),
    ('premature-eof',4,3),('close-eintr',5,3),('fstat-eio',6,3),('open-eacces',7,3)):
    add(label,expected=expected,fault=fault)
add('terminal-unlink-eacces',document({**defaults,'state':'confirmed'}),3,fault=8)
(corpus/'CASES.json').write_text(json.dumps(cases,indent=2)+'\n')
case_code='\n'.join('{'+','.join((json.dumps(row['path']),str(row['expected']),str(row['kind']),str(row['fault']),
    str(row['files'])+'U',str(row['cleanup']),str(int(row['normal']))))+'},' for row in cases)
variants=[('candidate',args.prepared,True)]
if args.baseline:
    variants.append(('baseline',args.baseline,False))
if args.mutations:
    variants.extend((name,args.prepared,False) for name in ('future-version','duplicate-fields','hidden-nul',
        'empty-number','follow-symlink','ignore-close-error'))
records=[]
for variant,root,expected in variants:
    tree=extract.Prepared(root)
    text=tree.read('uci.c')
    common=''.join(tree.function('uci.c',name) for name in ('checked_active','checked_state_name','checked_state_parse',
        'checked_now_ms','checked_journal_clear','checked_journal_write','checked_hex'))
    loader=tree.function('uci.c','checked_journal_load')
    if variant!='baseline':
        loader=tree.function('uci.c','checked_journal_uint')+loader
    edits={
        'future-version':('strcmp(fields[J_VERSION], "1") ||','false ||'),
        'duplicate-fields':('if (i == J_COUNT || fields[i])','if (i == J_COUNT)'),
        'hidden-nul':(" || memchr(data, '\\0', length)",''),
        'empty-number':("if (!text || *text < '0' || *text > '9')",'if (!text)'),
        'follow-symlink':(' | O_NOFOLLOW',''),
        'ignore-close-error':('if (close(fd))','if ((close(fd), false))'),
    }
    if variant in edits:
        before,after=edits[variant]
        assert loader.count(before)==1,variant
        loader=loader.replace(before,after,1)
    structures=extract.structure(text,'checked_state','enum')+extract.structure(text,'checked_transaction')
    code=assets[HERE/'rpcd-journal-recovery/host-fixture.c'].decode()
    code=code.replace('HOST_STRUCTURES',structures).replace('HOST_FUNCTIONS',common+loader).replace('HOST_CASES',case_code)
    target=args.output/(variant+'.c')
    target.write_text(code)
    command=shlex.split(args.cc)+['-std=gnu11','-Wall','-Wextra','-Werror',str(target),'-o',str(target.with_suffix('.host'))]
    if args.sanitize:
        command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
    p=subprocess.run(command,capture_output=True,timeout=60)
    target.with_suffix('.compile.stderr').write_bytes(p.stderr)
    assert p.returncode==0,(variant,p.stderr.decode())
    ran=subprocess.run([str(target.with_suffix('.host')),str(corpus.resolve())],capture_output=True,timeout=120)
    target.with_suffix('.stdout').write_bytes(ran.stdout)
    target.with_suffix('.stderr').write_bytes(ran.stderr)
    assert not ran.stderr,(variant,ran.stderr.decode())
    result=json.loads(ran.stdout)
    assert (ran.returncode==0)==expected and (result['failures']==0)==expected,(variant,result)
    records.append(dict(variant=variant,command=command,**result,**tree.manifest(),generated_sha256=hashlib.sha256(code.encode()).hexdigest()))
assert len({r['normal_signature'] for r in records})==1
assert all(path.read_bytes()==data for path,data in assets.items())
(args.output/'RESULT.json').write_text(json.dumps(dict(records=records,assets={str(p):hashlib.sha256(d).hexdigest() for p,d in assets.items()},
    corpus_sha256=hashlib.sha256((corpus/'CASES.json').read_bytes()).hexdigest(),
    scope='Complete journal loader/writer/helpers on host filesystem. Fault wrappers model syscall interruption/errors. No full daemon, target ABI, real reboot, flash or durable snapshots qualified.',
    target_compiled=False,hardware_accessed=False),indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ('variant','scenarios','checks','failures','normal_signature')} for r in records]))
