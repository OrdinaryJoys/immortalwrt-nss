#!/usr/bin/env python3
"""HPPE27 isolated serial-owned rollback model, not target/root/lifetime qualification."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
sys.dont_write_bytecode=True
SUPPORT=Path(__file__).resolve().parent/'ssdk-hppe-owned-rollback'
sys.path.insert(0,str(SUPPORT))
import source
from mutations import once,variants
AUDIT=Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-hppe-owned-rollback')
OLD=AUDIT.parents[1]/'20261030/ssdk-dp-retirement'
PROFILES={'neither':[],'kernel':['-DKERNEL_MODULE'],'user':['-DUSER_MODE'],'both':['-DKERNEL_MODULE','-DUSER_MODE']}
ALL=('neither','kernel','user','both')
ACTIVE=('neither','kernel','user')
FIELDS=('profile','name','symbol','case','marker','classification')
def record(path,data,generated=None):
    raw=(json.dumps(data,indent=2)+'\n').encode();path.write_bytes(raw)
    if generated is not None:generated[str(path)]=source.digest(raw)


def expected_tail(root,expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')),'output-symlink')
    source.require({str(p) for p in root.rglob('*.expected') if p.is_file()}==set(expected),'expected-inventory')
    for n,sha in expected.items():source.require(source.identity(n)==sha,'expected-memory-hash')


def generated_tail(root,generated):
    actual={str(p) for p in root.rglob('*') if p.is_file() and p!=root/'RESULTS.json' and not p.is_relative_to(root/'fresh27')}
    source.require(actual==set(generated),'generated-inventory')
    for n,sha in generated.items():source.require(source.identity(n)==sha,'generated-memory-hash')


def tail_controls(out):
    root=out/'tail-controls';root.mkdir();p=root/'valid.expected';raw=b'ALPHA\nBETA\n';p.write_bytes(raw)
    expected={str(p):source.digest(raw)};valid=0;rejects=[]
    def check():
        nonlocal valid
        expected_tail(root,expected);generated_tail(root,expected);valid+=1
    def reject(name,action,restore,marker,gate=expected_tail):
        action()
        try:gate(root,expected)
        except RuntimeError as e:source.require(str(e)==marker,'specific-tail-control')
        else:raise RuntimeError('tail-control-accepted:'+name)
        rejects.append(name);restore();check()
    check()
    reject('modified',lambda:p.write_bytes(b'bad'),lambda:p.write_bytes(raw),'expected-memory-hash')
    reject('truncated',lambda:p.write_bytes(raw[:-1]),lambda:p.write_bytes(raw),'expected-memory-hash')
    reject('deleted',p.unlink,lambda:p.write_bytes(raw),'expected-inventory')
    rename=root/'renamed.data'
    reject('renamed',lambda:p.rename(rename),lambda:rename.rename(p),'expected-inventory')
    extra=root/'rogue.expected'
    reject('extra-expected',lambda:extra.write_bytes(raw),extra.unlink,'expected-inventory')
    extra=root/'rogue.c'
    reject('extra-generated',lambda:extra.write_bytes(raw),extra.unlink,'generated-inventory',generated_tail)
    nested=root/'rogue';nested.mkdir();extra=nested/'RESULTS.json'
    reject('nested-results',lambda:extra.write_bytes(raw),extra.unlink,'generated-inventory',generated_tail)
    nested.rmdir();allowed=root/'RESULTS.json';allowed.write_bytes(b'root only');check();allowed.unlink()
    p.unlink();root.rmdir();return {'valid':valid,'rejects':rejects,'truth':'memory oracle and exact inventories'}


def positive(code,out,err,expected):source.require(code==0 and out==expected and err==b'','positive-exact-trace')


def negative(code,out,err,marker):source.require(code==86 and out==b'' and err==f'HPPE_OWNER {marker}\n'.encode(),'negative-exact-marker')


def output_controls():
    positive(0,b'x',b'',b'x');negative(86,b'',b'HPPE_OWNER X\n','X');rejects=0
    for row in [(1,b'x',b'',b'x'),(0,b'xx',b'',b'x'),(0,b'x',b'warning',b'x')]:
        try:positive(*row)
        except RuntimeError:rejects+=1
        else:raise RuntimeError('positive-gate-control')
    for row in [(1,b'',b'HPPE_OWNER X\n'),(-6,b'',b'HPPE_OWNER X\n'),(None,b'',b'HPPE_OWNER X\n'),
                (86,b'noise',b'HPPE_OWNER X\n'),(86,b'',b'HPPE_OWNER Y\n'),(86,b'',b'HPPE_OWNER X\nHPPE_OWNER X\n'),
                (86,b'',b'HPPE_OWNER X\nERROR: AddressSanitizer')]:
        try:negative(*row,'X')
        except RuntimeError:rejects+=1
        else:raise RuntimeError('negative-gate-control')
    return {'valid':2,'rejects':rejects}


def invoke(argv,prefix,env,generated):
    record(prefix.with_suffix('.command.json'),{'argv':argv,'environment':{k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}},generated)
    try:p=subprocess.run(argv,capture_output=True,env=env,timeout=60)
    except subprocess.TimeoutExpired as e:
        prefix.with_suffix('.stdout').write_bytes(e.stdout or b'');prefix.with_suffix('.stderr').write_bytes(e.stderr or b'')
        record(prefix.with_suffix('.exit.json'),{'returncode':None,'timeout':True});raise RuntimeError('timeout-not-credit') from e
    for suffix,raw in [('.stdout',p.stdout),('.stderr',p.stderr)]:
        path=prefix.with_suffix(suffix);path.write_bytes(raw);generated[str(path)]=source.digest(raw)
    record(prefix.with_suffix('.exit.json'),{'returncode':p.returncode,'timeout':False},generated)
    return p


def compile_c(cc,flags,text,prefix,env,generated):
    path=prefix.with_suffix('.c');binary=prefix.with_suffix('.bin');path.write_text(text);generated[str(path)]=source.digest(text.encode())
    p=invoke([cc,*flags,str(path),'-o',str(binary)],prefix.with_name(prefix.name+'-compile'),env,generated)
    source.require(p.returncode==0 and p.stdout==p.stderr==b'','clean-compile:'+str(prefix));generated[str(binary)]=source.identity(binary)
    bundle=Path(str(binary)+'.dSYM')
    if bundle.exists():
        required={bundle/'Contents/Info.plist',bundle/'Contents/Resources/DWARF'/binary.name}
        arch={'arm64':'aarch64','aarch64':'aarch64','x86_64':'x86_64'}.get(platform.machine());source.require(arch is not None,'debug-arch')
        allowed=required|{bundle/'Contents/Resources/Relocations'/arch/(binary.name+'.yml')}
        members=list(bundle.rglob('*'));files={p for p in members if p.is_file()}
        source.require(bundle.is_dir() and not any(p.is_symlink() for p in members) and required<=files<=allowed,'debug-shape')
        for p in sorted(files):generated[str(p)]=source.identity(p)
    return binary


def san_env(env,code):
    env=dict(env);env['ASAN_OPTIONS']=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    env['UBSAN_OPTIONS']=f'halt_on_error=1:print_stacktrace=1:exitcode={code}';return env


def canaries(cc,flags,out,env,generated):
    result=[]
    for name,code,text,diag in [
        ('asan',97,'#include <stdlib.h>\nint main(int n,char**v){(void)v;volatile int i=n;char*p=malloc(1);p[i]=1;volatile char x=p[i];free(p);return x;}\n',b'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan',98,'#include <limits.h>\nint main(int n,char**v){(void)v;volatile int x=INT_MAX;return x+n;}\n',b'runtime error: signed integer overflow')]:
        binary=compile_c(cc,flags,text,out/('canary-'+name),env,generated);used=san_env(env,code)
        p=invoke([str(binary)],out/('canary-'+name+'-run'),used,generated)
        source.require(p.returncode==code and p.stdout==b'' and diag in p.stderr,'canary-activation:'+name)
        result.append({'name':name,'exit':code,'environment':{k:used[k] for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}})
    return result


def schema(tree,extracted):
    text=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*','',extracted['types'])
    enums={}
    for body,name in re.findall(r'typedef\s+enum\s*\{([^}]*)\}\s*(\w+)\s*;',text):
        value=-1;values={}
        for entry in body.split(','):
            if not entry.strip():continue
            m=re.fullmatch(r'\s*(\w+)\s*(?:=\s*(-?\d+))?\s*',entry)
            source.require(m is not None,'bounded-enum:'+name)
            label,number=m.groups();value=int(number) if number is not None else value+1;values[label]=value
        enums[name]=values
    sdk=enums['sw_error_t'];props=enums['hsl_port_prop_t']
    source.require([props[n] for n in ('HSL_PP_PHY','HSL_PP_INCL_CPU','HSL_PP_EXCL_CPU','HSL_PP_INNER','HSL_PP_CPU','HSL_PP_BUTT')]==list(range(6)), 'actual-property-domain')
    mapping={'a_uint8_t':ctypes.c_uint8,'a_uint16_t':ctypes.c_uint16,'a_uint32_t':ctypes.c_uint32,'a_uint64_t':ctypes.c_uint64,
             'fal_pbmp_t':ctypes.c_uint32}
    for name in enums:mapping[name]=ctypes.c_int
    bounds={n:int(v) for n,v in re.findall(r'^#define (SW_MAX_NR_\w+)\s+(\d+)',text,re.M)}|props
    source.require(bounds['SW_MAX_NR_DEV']==3 and bounds['SW_MAX_NR_PORT']==16,'actual-capacities')
    sizes={};fields={}
    for body,name in re.findall(r'typedef\s+struct(?:\s+\w+)?\s*\{([^}]*)\}\s*(\w+)\s*;',text):
        entries=[];desc=[]
        for field in body.split(';'):
            if not field.strip():continue
            m=re.fullmatch(r'\s*(\w+)\s+(\w+)\s*(?:\[\s*(\w+)\s*\])?\s*',field)
            source.require(m is not None,'small-layout-field:'+field);kind,label,count=m.groups();typ=mapping[kind]
            if count:typ=typ*bounds[count]
            entries.append((label,typ));desc.append({'type':kind,'field':label,'count':bounds[count] if count else 1})
        typ=type(name,(ctypes.Structure,),{'_fields_':entries});mapping[name]=typ;sizes[name]=ctypes.sizeof(typ);fields[name]=desc
    cfg=type('ReducedCfg',(ctypes.Structure,),{'_fields_':[('cpu_mode',ctypes.c_int),('port_cfg',mapping['ssdk_port_cfg']),('cookie',ctypes.c_uint32)]})
    sizes['ssdk_init_cfg']=ctypes.sizeof(cfg)
    source.require(set(sizes)=={'hsl_dev_t','ssdk_port_cfg','port_info_t','ssdk_init_cfg'},'small-layout-inventory')
    return {'errors':sdk,'properties':props,'enums':enums,'sizes':sizes,'fields':fields,
            'note':'actual small declarations; independent ctypes host layout checked by C. ssdk_init_cfg/API are reduced models, not target ABI.'}


def case(name, **changes):
    c=dict(name=name,flow='root',dev=0,cpu=1,lan=0x106,wan=0x204,inner=0x102,
           bmp=0x8002,ibmp=0x4002,borrow=0,hook=0,oom_kind=0,oom_mode=0,
           synth=0,conflict=0,nested=0,attempts=1,clean=0,mismatch=0,nullcfg=0,tokenold=0,baseline=False)
    c.update(changes);return c


def cases():
    rows=[]
    for d in range(3):
        for cpu,label in ((1,'cpu0'),(32768,'cpu15'),(10,'lowest'),(3,'multizero'),(0,'nocpu'),(1<<31,'highcpu')):
            rows.append(case(f'd{d}-{label}',dev=d,cpu=cpu,baseline=label not in ('nocpu','highcpu')))
        for mask in range(4):rows.append(case(f'd{d}-borrow{mask}',dev=d,borrow=mask,clean=2))
        rows += [case(f'd{d}-callback',dev=d,clean=1,baseline=True),case(f'd{d}-direct',dev=d,clean=2,baseline=True),
                 case(f'd{d}-repeat',dev=d,attempts=2),case(f'd{d}-reconstruct',dev=d,attempts=3,clean=2),
                 case(f'd{d}-foreignhook',dev=d,hook=2),case(f'd{d}-retiredhook',dev=d,hook=1,clean=2),
                 case(f'd{d}-tokenold',dev=d,tokenold=1),case(f'd{d}-token-and-port',dev=d,tokenold=1,borrow=2),
                 case(f'd{d}-nested',dev=d,nested=1,clean=2),case(f'd{d}-mismatch',dev=d,clean=2,mismatch=1),
                 case(f'd{d}-nullcfg',dev=d,nullcfg=1),case(f'd{d}-builders',dev=d,flow='builders'),
                 case(f'd{d}-legacy',dev=d,flow='legacy')]
        for kind,label in ((1,'cfg'),(2,'port')):
            for mode,suffix in ((1,'first'),(2,'persistent')):
                rows.append(case(f'd{d}-{label}-{suffix}',dev=d,oom_kind=kind,oom_mode=mode,attempts=2))
        for synth,label in ((1,'map'),(2,'set'),(3,'publish')):
            rows.append(case(f'd{d}-synthetic-{label}',dev=d,synth=synth,attempts=2))
        rows.append(case(f'd{d}-conflict',dev=d,conflict=1,attempts=2))
    for d in (3,4294967295):rows.append(case(f'invalid-{d}',dev=d))
    rows += [case('sparse-overlap',cpu=8,lan=0x8002,wan=2,inner=0x8002,bmp=0x104,ibmp=0x202,baseline=True),
             case('high-global',bmp=0x80000000,ibmp=0x80000000,baseline=True)]
    source.require(len({c['name'] for c in rows})==len(rows),'unique-case-inventory')
    return rows


def builder_expected():
    # Independent mathematical input schedule, never populated from native bytes.
    portmap=1<<15;rows=[0]*5;states=[[portmap,*rows,*([0]*16)]]
    for t in range(5):
        rows[t]|=1<<15;states.append([portmap,*rows,*([0]*16)])
    for t in range(5):
        portmap|=1<<t;rows[t]|=1<<t;states.append([portmap,*rows,*([0]*16)])
    return states+[list(states[-1]),list(states[-1])]


def header(matrix,domain):
    fields=['name','flow','dev','cpu','lan','wan','inner','bmp','ibmp','borrow','hook','oom_kind','oom_mode',
            'synth','conflict','nested','attempts','clean','mismatch','nullcfg','tokenold']
    def val(v):return json.dumps(v) if isinstance(v,str) else str(v)+'u' if v>2147483647 else str(v)
    lines=[f'_Static_assert(sizeof({n})=={v},"actual small host layout");' for n,v in domain['sizes'].items()]
    lines += [f'_Static_assert({n}=={v},"actual enum");' for n,v in domain['properties'].items()]
    lines += ['static const a_uint32_t builder_expected[13][22]={']
    lines += ['{'+','.join(map(str,row))+'},' for row in builder_expected()]
    lines += ['};']
    return '\n'.join(lines+['static const struct input inputs[]={']+
                     ['{'+','.join('.'+k+'='+val(c[k]) for k in fields)+'},' for c in matrix]+['};'])


def oracle(c,profile,domain,old=False):
    e=domain['errors'];sz=domain['sizes'];events=[];add=events.append;rets=[]
    cs={};ps={};ts={d:0 for d in range(3)};busy={d:0 for d in range(3)};meta={};api={};blocks=[]
    allocs=[0,0,0];serial=0;maps=sets=pubs=0
    freshcfg=[1,c['cpu'],c['lan'],c['wan'],c['inner'],0xc0ffee]
    def seed(d,k,tag):
        payload=[0,0,0,0,0,0xbadc0de] if k==1 else [0x88,[1<<i for i in range(5)],[1000+i+d for i in range(16)]]
        row=dict(id=tag,kind=k,live=1,foreign=1,payload=payload);blocks.append(row);return tag
    def obj(tag):return next(b for b in blocks if b['id']==tag)
    for d in range(3):
        mask=c['borrow'] if d==c['dev'] else 3
        cs[d]=seed(d,1,101+d*10) if mask&1 else 0;ps[d]=seed(d,2,102+d*10) if mask&2 else 0
        meta[d]=[d,7,9,11,13,17,0,0,68];api[d]=[c['hook'] if d==c['dev'] else 2]+[2]*10
    if c['tokenold'] and c['dev']<3:ts[c['dev']]=ps[c['dev']] or seed(c['dev'],2,800)
    def allocate(k):
        nonlocal serial
        if c['nested'] and k==1:add(f'NESTED {e["SW_BUSY"]} {e["SW_BUSY"]} {e["SW_ALREADY_EXIST"]}\n')
        serial+=1;allocs[k]+=1;ok=not(c['oom_kind']==k and (c['oom_mode']==2 or allocs[k]==1))
        add(f'ALLOC {serial} {k} {sz["ssdk_init_cfg" if k==1 else "port_info_t"]} {int(ok)}\n')
        if not ok:return 0
        blocks.append(dict(id=serial,kind=k,live=1,foreign=0,payload=[0]*6 if k==1 else [0,[0]*5,[0]*16]));return serial
    def free(tag):
        b=obj(tag);source.require(b['live'] and not b['foreign'],'oracle-owned-free');b['live']=0;add(f'FREE {tag}\n')
    def ret(r):rets.append(r);add(f'RET {r}\n')
    def dump():
        for d in range(3):
            add('META %d %s\n'%(d,' '.join(map(str,meta[d]))));add(f'SLOTS {d} {cs[d]} {ps[d]} {ts[d]} {busy[d]}\n')
            if cs[d]:add('CFG %d %s\n'%(d,' '.join(map(str,obj(cs[d])['payload']))))
            if ps[d]:
                p=obj(ps[d])['payload'];add('PORT %d %s\n'%(d,' '.join(map(str,[p[0]]+p[1]+p[2]))))
            add('API %d %s\n'%(d,' '.join(map(str,api[d]))))
        for b in blocks:
            reach=int(b['id'] in list(cs.values())+list(ps.values())+list(ts.values()))
            add(f'OWNER {b["id"]} {b["kind"]} {b["live"]} {b["foreign"]} {reach}\n')
    def buildalloc(d,owner=0,null=False):
        if null:return e['SW_BAD_PTR'],owner
        if owner:return e['SW_BAD_STATE'],owner
        if d>=3:return e['SW_OUT_OF_RANGE'],owner
        if ps[d]:return e['SW_ALREADY_EXIST'],owner
        p=allocate(2)
        if not p:return e['SW_OUT_OF_MEM'],0
        add(f'ZERO {p} {sz["port_info_t"]}\n');return 0,p
    def mapset(p,port):
        nonlocal maps
        maps+=1;r=e['SW_READ_ERROR'] if c['synth']==1 and maps==1 else e['SW_BAD_PTR'] if not p else e['SW_OUT_OF_RANGE'] if port>=16 else 0
        if not r:obj(p)['payload'][0]|=1<<port
        add(f'MAP {p} {port} {r}\n');return r
    def propset(p,port,t):
        nonlocal sets
        sets+=1;r=e['SW_READ_ERROR'] if c['synth']==2 and sets==1 else e['SW_BAD_PTR'] if not p else e['SW_OUT_OF_RANGE'] if port>=16 else e['SW_BAD_PARAM'] if t<0 or t>=5 else e['SW_OUT_OF_RANGE'] if not(obj(p)['payload'][0]&(1<<port)) else 0
        if not r:obj(p)['payload'][1][t]|=1<<port
        add(f'SET {p} {port} {t} {r}\n');return r
    def publish(d,p,null=False):
        nonlocal pubs
        pubs+=1
        if c['conflict'] and pubs==1:ps[d]=seed(d,2,900);add(f'CONFLICT {d} 900\n')
        r=e['SW_READ_ERROR'] if c['synth']==3 and pubs==1 else e['SW_BAD_PTR'] if null or not p else e['SW_OUT_OF_RANGE'] if d>=3 else e['SW_ALREADY_EXIST'] if ps[d] else 0
        after=p
        if not r:ps[d]=p;after=0
        add(f'PUBLISH {d} {p} {after} {r}\n');return r,after
    def owned(d,p):
        r=e['SW_OUT_OF_RANGE'] if d>=3 else e['SW_BAD_STATE'] if not p or ps[d]!=p else 0
        if not r:free(p);ps[d]=0
        add(f'OWNED_CLEAN {d} {p} {r}\n');return r
    def builder_snapshot(p,local,stage):
        b=obj(p);payload=b['payload'];fields=[payload[0],*payload[1],*payload[2]]
        source.require(b['id']==1 and b['kind']==2 and b['live'] and not b['foreign'] and
                       not cs[d] and not ts[d] and not busy[d] and
                       ((not local and ps[d]==p) if stage==12 else (local==p and not ps[d])),
                       'oracle-builder-identity')
        source.require(fields==builder_expected()[stage],'oracle-builder-mathematical-fields')
        add('BUILDER_PAYLOAD %d %d %d %d %d %s\n'%(stage,d,p,local,ps[d],' '.join(map(str,fields))))
    def dev(d):
        front=bin((c['lan']|c['wan'])&65535).count('1');meta[d][3]=front;cpus=c['cpu']&65535
        if not cpus:return e['SW_BAD_VALUE']
        cpu=(cpus&-cpus).bit_length()-1;nr=front+bin(c['inner']&65535).count('1')+1
        meta[d]=[d,cpu,nr,front,nr,4096,1,1,c['wan']];return 0
    def prop(d,p):
        add(f'BMP {c["bmp"]}\n');add(f'INNER {c["ibmp"]}\n');cpu=meta[d][1]
        for port in range(16):
            if port!=cpu and not((c['bmp']|c['ibmp'])&(1<<port)):continue
            if old:obj(p)['payload'][0]|=1<<port
            else:
                r=mapset(p,port)
                if r:return r
            for t,ok in enumerate([bool(c['bmp']&(1<<port)),True,port!=cpu,bool(c['ibmp']&(1<<port)),port==cpu]):
                if ok:
                    if old:obj(p)['payload'][1][t]|=1<<port
                    else:
                        r=propset(p,port,t)
                        if r:return r
        return 0
    def init(d):
        if d>=3:return e['SW_OUT_OF_RANGE']
        if not old:
            if c['nullcfg']:return e['SW_BAD_PTR']
            if cs[d] or ts[d]:return e['SW_ALREADY_EXIST']
            if profile!='both' and (ps[d] or api[d][0]==2):return e['SW_ALREADY_EXIST']
        saved=list(meta[d]);p=0
        if old and cs[d]:new=cs[d]
        else:new=allocate(1)
        if not new:return e['SW_OUT_OF_MEM']
        if old:cs[d]=new
        obj(new)['payload']=list(freshcfg);add(f'COPY {new} {sz["ssdk_init_cfg"]}\n');r=dev(d)
        if not r and profile!='both':
            if old:
                ps[d]=0;p=allocate(2);r=0 if p else e['SW_OUT_OF_MEM']
                if p:add(f'ZERO {p} {sz["port_info_t"]}\n');ps[d]=p
            else:r,p=buildalloc(d)
            if not r:r=prop(d,p)
            if not r and not old:
                token=p;r,p=publish(d,p)
                if not r:ts[d]=token
        if r:
            if not old:
                if p:free(p)
                meta[d]=saved;free(new)
            return r
        cs[d]=new
        if profile!='both':api[d]=[1]*11
        return 0
    def cleanup(d):
        if d>=3:return e['SW_OUT_OF_RANGE']
        if cs[d]:
            if old:
                if ps[d]:free(ps[d]);ps[d]=0
            elif ts[d]:
                r=owned(d,ts[d])
                if r:return r
                ts[d]=0
            free(cs[d]);cs[d]=0
        return 0
    d=c['dev']
    if c['flow']=='builders':
        ret(0);ret(e['SW_BAD_PTR']);ret(e['SW_OUT_OF_RANGE']);r,p=buildalloc(d);ret(r);r,p=buildalloc(d,p);ret(r)
        for ptr,port in ((0,0),(p,16),(p,4294967295),(p,15)):ret(mapset(ptr,port))
        builder_snapshot(p,p,0)
        for ptr,port,t in ((0,0,0),(p,16,0),(p,15,-1),(p,15,5),(p,0,0)):ret(propset(ptr,port,t))
        for t in range(5):ret(propset(p,15,t));builder_snapshot(p,p,1+t)
        for t in range(5):ret(mapset(p,t));ret(propset(p,t,t));builder_snapshot(p,p,6+t)
        builder_snapshot(p,p,11)
        r,_=publish(d,0,True);ret(r);r,_=publish(d,0);ret(r);r,p=publish(3,p);ret(r)
        ps[d]=seed(d,2,900);r,empty=buildalloc(d);ret(r);source.require(not empty,'oracle-failed-output')
        r,p=publish(d,p);ret(r);ps[d]=0;token=p;r,p=publish(d,p);ret(r)
        builder_snapshot(token,p,12)
        ret(owned(3,token));ret(owned(d,0));ret(owned(d,token));ret(0)
        r,p=buildalloc(d);ret(r);free(p);dump()
    elif c['flow']=='legacy':
        ps[d]=0;ret(0);p=allocate(2);add(f'ZERO {p} {sz["port_info_t"]}\n');ps[d]=p;ret(0)
        obj(p)['payload'][0]|=32768;ret(0);obj(p)['payload'][1][3]|=32768;ret(0);dump();free(p);ps[d]=0;ret(0);dump()
    else:
        for attempt in range(c['attempts']):
            add(f'ATTEMPT {attempt}\n');r=init(d);ret(r);dump()
            if not r and c['clean']:
                if c['mismatch'] and ts[d]:ps[d]=seed(d,2,900);add('DISPLACE 900\n')
                if c['clean']==1:
                    if api[d][0]:add('CALLBACK\n');r=cleanup(d);ret(r)
                    else:add('CALLBACK_ABSENT_OPEN\n')
                else:add('DIRECT_CLEAN\n');r=cleanup(d);ret(r)
                dump()
                if not r and c['clean']==2:add('IDEMPOTENT_CLEAN\n');ret(cleanup(d));dump()
        if d>=3:add('INVALID_CLEAN\n');ret(cleanup(d))
    add('END SERIAL_HOST_ONLY\n');return rets,''.join(events).encode()


# Literal obligations independent of variants(), emitted results or len(variants).
# Each tuple binds profile, symbol, case, exact marker and classification.
CONTRACT=(
    ('nullcfg-error','hppe_init','d0-nullcfg','FIRST_ERROR',ALL),
    ('cfg-admission','hppe_init','d0-borrow1','PRIVATE_BEFORE_PUBLICATION',ACTIVE),
    ('token-admission','hppe_init','d0-tokenold','PRIVATE_BEFORE_PUBLICATION',ACTIVE),
    ('foreign-hook','hppe_init','d0-foreignhook','FIRST_ERROR',ACTIVE),
    ('restore-metadata','hppe_init','d0-nocpu','EXACT_OWNER_TRACE',ALL),
    ('abort-cfg-leak','hppe_init','d0-nocpu','EXACT_OWNER_TRACE',ALL),
    ('abort-private-leak','hppe_init','d0-synthetic-set','EXACT_OWNER_TRACE',ACTIVE),
    ('reverse-free-order','hppe_init','d0-synthetic-set','EXACT_OWNER_TRACE',ACTIVE),
    ('abort-first-error','hppe_init','d0-nocpu','FIRST_ERROR',ALL),
    ('busy-success','hppe_init','d0-repeat','FIRST_ERROR',ALL),
    ('busy-failure','hppe_init','d0-cfg-first','FIRST_ERROR',ALL),
    ('nested-init-domain','hppe_init','d0-nested','NESTED_BUSY_DOMAIN',ALL),
    ('nested-clean-domain','hppe_cleanup','d0-nested','NESTED_BUSY_DOMAIN',ALL),
    ('no-token-store','hppe_init','d0-direct','EXACT_OWNER_TRACE',ACTIVE),
    ('api-wrong-token','hppe_init','d0-direct','API_IDENTITY',ACTIVE),
    ('cleanup-mismatch-error','hsl_port_prop_cleanup_owned','d0-mismatch','FIRST_ERROR',ACTIVE),
    ('combined-unowned-clean','hppe_cleanup','d0-borrow2','FIRST_ERROR',('both',)),
    ('publish-consume','hsl_port_prop_build_publish','d0-builders','PUBLISH_CONSUME',ALL),
    ('publish-conflict-code','hsl_port_prop_build_publish','d0-builders','FIRST_ERROR',ALL),
    ('abort-consume','hsl_port_prop_build_abort','d0-builders','ABORT_CONSUME',ALL),
    ('map-upper-bound','hsl_port_prop_build_portmap_set','d0-builders','FIRST_ERROR',ALL),
    ('setter-negative-enum-error','hsl_port_prop_build_set','d0-builders','FIRST_ERROR',ALL),
    ('setter-row','hsl_port_prop_build_set','d0-cpu0','EXACT_OWNER_TRACE',ACTIVE),
    ('alloc-occupied-out-error','hsl_port_prop_build_alloc','d0-builders','FIRST_ERROR',ALL),
    ('existing-cfg-code','hppe_init','d0-borrow1','FIRST_ERROR',ALL),
    ('private-cfg-early-publish','hppe_init','d0-cpu0','PRIVATE_BEFORE_PUBLICATION',ACTIVE),
    ('abort-frees-foreign','hppe_init','d0-conflict','ONLY_OWNED_FREE',ACTIVE),
    ('cleanup-ignores-identity','hsl_port_prop_cleanup_owned','d0-mismatch','ONLY_OWNED_FREE',ACTIVE),
    ('cleanup-token-not-cleared','hppe_cleanup','d0-direct','OWNER_BEFORE_DEREF',ACTIVE),
    ('cross-device-busy','hppe_init','d0-nested','NESTED_BUSY_DOMAIN',ALL),
    ('builder-valid-wrong-row','hsl_port_prop_build_set','d0-builders','BUILDER_PRIVATE_PAYLOAD',ALL),
    ('builder-delete-map-store','hsl_port_prop_build_portmap_set','d0-builders','BUILDER_PRIVATE_PAYLOAD',ALL),
    ('builder-delete-set-store','hsl_port_prop_build_set','d0-builders','BUILDER_PRIVATE_PAYLOAD',ALL),
    ('builder-private-phy-corrupt','hsl_port_prop_build_set','d0-builders','BUILDER_PRIVATE_PAYLOAD',ALL),
    ('builder-post-map-corrupt','hsl_port_prop_build_publish','d0-builders','BUILDER_PUBLISHED_PAYLOAD',ALL),
    ('builder-post-row-corrupt','hsl_port_prop_build_publish','d0-builders','BUILDER_PUBLISHED_PAYLOAD',ALL),
    ('builder-post-phy-corrupt','hsl_port_prop_build_publish','d0-builders','BUILDER_PUBLISHED_PAYLOAD',ALL))
OLD_CONTRACT=(('old-cpu-abort','d0-nocpu',ALL),('old-port-abort','d0-port-first',ACTIVE))


def contract(kind):
    rows=[]
    if kind=='source':
        for name,symbol,case_name,marker,profiles in CONTRACT:
            for profile in profiles:rows.append(dict(profile=profile,name=name,symbol=symbol,case=case_name,
                marker=marker,classification='directed actual source mutant'))
    elif kind=='old':
        for name,case_name,profiles in OLD_CONTRACT:
            for profile in profiles:rows.append(dict(profile=profile,name=name,symbol='complete26 HPPE entry with unchanged legacy helpers',case=case_name,
                marker='EXACT_OWNER_TRACE',classification='safe complete baseline rollback boundary witness'))
    else:raise RuntimeError('inventory-kind')
    return rows


def inventory_gate(rows,kind,completed=False):
    try:keys=[tuple(r[k] for k in FIELDS) for r in rows]
    except (KeyError,TypeError) as e:raise RuntimeError('NEGATIVE_INVENTORY') from e
    source.require(len(keys)==len(set(keys)),'NEGATIVE_DUPLICATE')
    source.require(set(keys)=={tuple(r[k] for k in FIELDS) for r in contract(kind)},'NEGATIVE_INVENTORY')
    if completed:source.require(all(r.get('execution')=='CLEAN_COMPILE_EXACT86' and
        re.fullmatch('[0-9a-f]{64}',r.get('source_sha256','')) for r in rows),'NEGATIVE_EXECUTION')


def inventory_controls():
    rows=contract('source');inventory_gate(rows,'source');inventory_gate(contract('old'),'old');rejects=[]
    def reject(name,bad,marker,complete=False):
        try:inventory_gate(bad,'source',complete)
        except RuntimeError as e:source.require(str(e)==marker,'exact-inventory-control')
        else:raise RuntimeError('accepted-inventory-pollution:'+name)
        rejects.append(name)
    reject('empty',[],'NEGATIVE_INVENTORY');reject('missing',rows[:-1],'NEGATIVE_INVENTORY')
    reject('duplicate',rows+[rows[0]],'NEGATIVE_DUPLICATE')
    for field in FIELDS:reject('wrong-'+field,[dict(rows[0],**{field:'BAD'})]+rows[1:],'NEGATIVE_INVENTORY')
    reject('extra',rows+[dict(rows[0],name='EXTRA')],'NEGATIVE_INVENTORY')
    reject('unexecuted',rows,'NEGATIVE_EXECUTION',True)
    reject('q01-missing-all',[r for r in rows if not r['name'].startswith('builder-')],'NEGATIVE_INVENTORY')
    reject('q01-missing-both',[r for r in rows if not(r['name'].startswith('builder-') and r['profile']=='both')],'NEGATIVE_INVENTORY')
    q01=next(i for i,r in enumerate(rows) if r['name']=='builder-valid-wrong-row' and r['profile']=='both')
    for field,value in (('marker','EXACT_OWNER_TRACE'),('case','d0-cpu0'),('profile','kernel')):
        bad=[dict(r) for r in rows];bad[q01][field]=value
        reject('q01-wrong-'+field,bad,'NEGATIVE_DUPLICATE' if field=='profile' else 'NEGATIVE_INVENTORY')
    completed=[dict(r,execution='CLEAN_COMPILE_EXACT86',source_sha256='a'*64) for r in rows]
    inventory_gate(completed,'source',True)
    missing=[r for r in completed if not r['name'].startswith('builder-')]
    reject('q01-incomplete-final',missing,'NEGATIVE_INVENTORY',True)
    completed[q01]['execution']='NOT_CALLED';reject('q01-unexecuted-both',completed,'NEGATIVE_EXECUTION',True)
    return {'valid':3,'rejects':rejects,'classification':'pure inventory controls, not source/runtime negative credits'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'HPPE-SINGLE-EVAL-CANDIDATE-20261031-r1')
    p.add_argument('--candidate',type=Path,default=OLD/'HPPE-OWNED-ROLLBACK-CANDIDATE-20261031-r1');a=p.parse_args()
    out=a.output.resolve();source.require(out.parent==AUDIT and out.name.startswith('HPPE-OWNER-TEST-') and not out.exists(),'fresh-output');out.mkdir(parents=True)
    result=dict(status='INCOMPLETE',qualification='SERIAL_OWNED_HOST_MODEL_ONLY',python_optimize=sys.flags.optimize,
                positives=[],baseline_success=[],source_negatives=[],old_witnesses=[],native_model_controls=[],
                open=['not target ABI/HW/root/concurrency/ABA/RCU/reader lifetime','reduced cfg/API and bitmap/OS leaves','LSan unqualified'])
    generated={};expected_files={}
    try:
        tree,inputs=source.prepare(a.base.resolve(),a.candidate.resolve(),out);record(out/'INPUTS.json',inputs,generated)
        new,old=source.extract(tree),source.extract(a.base/'prepared');domain=schema(tree,new);matrix=cases()
        record(out/'SCHEMA.json',domain,generated);record(out/'MATRIX.json',matrix,generated)
        record(out/'BUILDER-PAYLOAD-ORACLE.json',{'stages':builder_expected(),
            'field_order':['dev_portmap','property[0..4]','phy_id[0..15]'],
            'schedule':'0 map15 before valid setters;1..5 setter15 per row;6..10 distinct row prefixes;11 prepublish;12 postpublish before any cleanup',
            'basis':'independent Python arithmetic, not native readback; all four profiles run actual standalone builders'},generated)
        text=source.render(new,old,(SUPPORT/'fixture.c').read_text().replace('/* @CASES@ */',header(matrix,domain)))
        record(out/'EXTRACTED.json',{'candidate':new['records'],'baseline':old['records'],'complete_bodies':list(new['bodies']),
               'transformations':'name-only wrappers real_map/set/publish/owned; historical property/init/cleanup aliases. No body pruning.',
               'header_contract':'actual opaque tag+public declarations and actual tagged definition compiled together; no hidden phase/dev/refcount'},generated)
        result['inventory_controls']=inventory_controls();record(out/'NEGATIVE-CONTRACT.json',{'source':contract('source'),'old':contract('old')},generated)
        planned={profile:variants(new,profile) for profile in PROFILES}
        planned_rows=[dict(v,profile=profile) for profile,vs in planned.items() for v in vs]
        inventory_gate(planned_rows,'source');inventory_gate(contract('old'),'old')
        record(out/'NEGATIVE-PLAN.json',{'source':[{k:r[k] for k in FIELDS} for r in planned_rows],'old':contract('old')},generated)
        result['negative_pre_execution_gate']='EXACT_INDEPENDENT_FIXED_TUPLES'
        cc=shutil.which(a.cc);source.require(cc is not None,'compiler');cc=str(Path(cc).resolve())
        result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function'];env=dict(os.environ)
        env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        version=invoke([cc,'--version'],out/'compiler-version',env,generated);source.require(version.returncode==0 and version.stderr==b'','compiler-version')
        if a.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        result['output_controls']=output_controls();result['tail_controls']=tail_controls(out)
        def execute(binary,c,i,profile,folder,name,oldmode=0):
            returns,expected=oracle(c,profile,domain);ep=folder/(name+'.expected');ep.write_bytes(expected)
            generated[str(ep)]=source.digest(expected);expected_files[str(ep)]=source.digest(expected)
            run=invoke([str(binary),str(i),','.join(map(str,returns)),str(ep),str(oldmode)],folder/name,env,generated)
            return run,expected
        byname={c['name']:(i,c) for i,c in enumerate(matrix)}
        for profile,pf in PROFILES.items():
            folder=out/profile;folder.mkdir();binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for i,c in enumerate(matrix):
                run,expected=execute(binary,c,i,profile,folder,c['name']);positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append(dict(profile=profile,case=c['name'],stdout_sha256=source.digest(run.stdout)))
                if c['flow']=='builders':result['positives'][-1]['builder_complete_payload_snapshots']=13
                if c['baseline']:
                    # Only semantic/state records, not deliberately different private actions/tokens.
                    selected=(b'META ',b'CFG ',b'PORT ',b'API ')
                    current_semantic=b''.join(line+b'\n' for line in run.stdout.splitlines() if line.startswith(selected))
                    returns,expected=oracle(c,profile,domain,True);ep=folder/(c['name']+'-baseline.expected');ep.write_bytes(expected)
                    generated[str(ep)]=source.digest(expected);expected_files[str(ep)]=source.digest(expected)
                    run=invoke([str(binary),str(i),','.join(map(str,returns)),str(ep),'1'],folder/(c['name']+'-baseline'),env,generated)
                    positive(run.returncode,run.stdout,run.stderr,expected)
                    baseline_semantic=b''.join(line+b'\n' for line in run.stdout.splitlines() if line.startswith(selected))
                    source.require(current_semantic==baseline_semantic,'baseline-semantic-fields')
                    result['baseline_success'].append(dict(profile=profile,case=c['name'],stdout_sha256=source.digest(run.stdout),
                        semantic_sha256=source.digest(current_semantic),comparison='actual old/new META CFG PORT API byte equality; private actions/tokens intentionally excluded'))
            if not a.positives_only:
                for v in planned[profile]:
                    mutated=once(text,v['before'],v['after']);mb=compile_c(cc,flags+pf,mutated,folder/v['name'],env,generated)
                    i,c=byname[v['case']];run,_=execute(mb,c,i,profile,folder,v['name']+'-run')
                    negative(run.returncode,run.stdout,run.stderr,v['marker'])
                    result['source_negatives'].append({k:v[k] for k in FIELDS if k!='profile'}|dict(profile=profile,
                        execution='CLEAN_COMPILE_EXACT86',source_sha256=source.digest(mutated.encode())))
                for v in contract('old'):
                    if v['profile']!=profile:continue
                    i,c=byname[v['case']];run,_=execute(binary,c,i,profile,folder,v['name']+'-run',1)
                    negative(run.returncode,run.stdout,run.stderr,v['marker'])
                    result['old_witnesses'].append(dict(v,execution='CLEAN_COMPILE_EXACT86',source_sha256=source.digest(text.encode())))
            record(out/'RESULTS.json',result)
        if not a.positives_only:
            inventory_gate(result['source_negatives'],'source',True);inventory_gate(result['old_witnesses'],'old',True)
            result['negative_completion_gate']='EXACT_UNIQUE_FIXED_OBLIGATIONS_EXECUTED_CLEAN'
        result['end_input_stability']=source.stable(inputs);expected_tail(out,expected_files);generated_tail(out,generated)
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler')
        result['expected_tail']='EXACT_PATHS_MEMORY_ORACLE';result['generated_tail']='EXACT_FILES_ONLY_ROOT_RESULTS_EXCEPTION_FRESH692_SEPARATE'
        result['generated_files']=generated;result['positive_count']=len(result['positives']);result['baseline_success_count']=len(result['baseline_success'])
        result['source_negative_count']=len(result['source_negatives']);result['old_witness_count']=len(result['old_witnesses'])
        result['negative_count']=result['source_negative_count']+result['old_witness_count']
        result['status']='DEV_CHECKPOINT_POSITIVES_ONLY' if a.positives_only else 'HOST_MODEL_ONLY'
        result['outcome']='NOT_FINAL' if a.positives_only else 'PASSED_WITHIN_SERIAL_OWNED_MODEL'
    except Exception as e:result['status']='FAILED';result['error']=str(e);raise
    finally:record(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_count','baseline_success_count','negative_count')}))


if __name__=='__main__':main()
