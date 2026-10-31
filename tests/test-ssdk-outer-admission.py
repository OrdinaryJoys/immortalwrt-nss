#!/usr/bin/env python3
"""Actual FAL/HSL28 lifecycle body host model; no target/HW/bootstrap qualification."""
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
SUPPORT=Path(__file__).resolve().parent/'ssdk-outer-admission'
sys.path.insert(0,str(SUPPORT))
import source
from mutations import once,variants
AUDIT=Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-outer-admission')
OLD=AUDIT.parents[1]/'20261030/ssdk-dp-retirement'
COMMON=['-DIN_VLAN','-DUK_IF','-DAPI_LOCK']
LEGACY=('ISIS','ISISC','MHT','DESS','SCOMPHY')
PROFILES={
    'hppe':dict(chips=('HPPE',),flags=[]),
    'kernel':dict(chips=('HPPE',),flags=['-DKERNEL_MODULE']),
    'user':dict(chips=('HPPE',),flags=['-DUSER_MODE']),
    'combined':dict(chips=('HPPE',),flags=['-DKERNEL_MODULE','-DUSER_MODE']),
    'nohppe':dict(chips=LEGACY,flags=[]),
    'isisc':dict(chips=('ISISC',),flags=[]),
    'isis':dict(chips=('ISIS',),flags=[]),
    'mht':dict(chips=('MHT',),flags=[]),
    'bare':dict(chips=(),flags=[]),
    'stock-kernel':dict(chips=('HPPE',),flags=['-DKERNEL_MODULE','-DUK_MINOR_DEV=254'],features=['-DIN_VLAN','-DUK_IF'],minor=254)}
HPPE_PROFILES=('hppe','kernel','user','combined')
ALL=tuple(PROFILES)
FIELDS=('profile','name','symbol','case','marker','classification')
def record(path,data,generated=None):
    raw=(json.dumps(data,indent=2)+'\n').encode();path.write_bytes(raw)
    if generated is not None:generated[str(path)]=source.digest(raw)


def expected_tail(root,expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')),'output-symlink')
    source.require({str(p) for p in root.rglob('*.expected') if p.is_file()}==set(expected),'expected-inventory')
    for n,sha in expected.items():source.require(source.identity(n)==sha,'expected-memory-hash')


def generated_tail(root,generated):
    actual={str(p) for p in root.rglob('*') if p.is_file() and p!=root/'RESULTS.json' and not p.is_relative_to(root/'fresh28')}
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


def negative(code,out,err,marker):source.require(code==86 and out==b'' and err==f'OUTER {marker}\n'.encode(),'negative-exact-marker')


def output_controls():
    positive(0,b'x',b'',b'x');negative(86,b'',b'OUTER X\n','X');rejects=0
    for row in [(1,b'x',b'',b'x'),(0,b'xx',b'',b'x'),(0,b'x',b'warning',b'x')]:
        try:positive(*row)
        except RuntimeError:rejects+=1
        else:raise RuntimeError('positive-gate-control')
    for row in [(1,b'',b'OUTER X\n'),(-6,b'',b'OUTER X\n'),(None,b'',b'OUTER X\n'),
                (86,b'noise',b'OUTER X\n'),(86,b'',b'OUTER Y\n'),(86,b'',b'OUTER X\nOUTER X\n'),
                (86,b'',b'OUTER X\nERROR: AddressSanitizer')]:
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
    cfg=type('ReducedCfg',(ctypes.Structure,),{'_fields_':[('cpu_mode',ctypes.c_int),('chip_type',ctypes.c_int),('port_cfg',mapping['ssdk_port_cfg']),('nl_prot',ctypes.c_uint32),('cookie',ctypes.c_uint32)]})
    sizes['ssdk_init_cfg']=ctypes.sizeof(cfg)
    source.require(set(sizes)=={'hsl_dev_t','ssdk_port_cfg','port_info_t','ssdk_init_cfg'},'small-layout-inventory')
    return {'errors':sdk,'properties':props,'enums':enums,'sizes':sizes,'fields':fields,
            'note':'actual small declarations; independent ctypes host layout checked by C. ssdk_init_cfg/API are reduced models, not target ABI.'}


BASE=('hppe','kernel','user','combined','nohppe')


def case(name,**kw):
    c=dict(name=name,flow='fal',fault='',probe='',dev=0,chip='CHIP_HPPE',cpu=1,lan=0x106,wan=0x204,
           inner=0x102,bmp=0x8002,residue=0,oom=0,clean=0,repeat=1,replace=0,partial=0,childbusy=0,nullcfg=0,start_epoch=0,schedule=2,profiles=HPPE_PROFILES)
    c.update(kw);return c


def cases():
    rows=[case('fal-hppe',clean=1),case('fal-dev1',dev=1,clean=1),case('fal-dev2',dev=2,clean=1),case('fal-appe',chip='CHIP_APPE',clean=1),
          case('fal-mrppe',chip='CHIP_MRPPE',clean=1),case('hsl-hppe',flow='hsl',clean=1),
          case('cpu15',cpu=32768,clean=1),case('multicpu',cpu=10,clean=1),case('nocpu',cpu=0,clean=2),
          case('hppe-repeat',repeat=2),case('foreign-P',residue=1,clean=1,profiles=BASE),
          case('held-outer',residue=2,profiles=BASE),case('foreign-hook',residue=3,profiles=BASE),
          case('held-outer-changed',residue=2,chip='CHIP_MHT',profiles=('nohppe','mht')),
          case('adapter-residue',residue=4,profiles=BASE),case('cleanup-foreign-hook',clean=1,replace=1),
          case('cleanup-mismatch',clean=1,replace=2,profiles=('hppe','kernel','user')),
          case('cleanup-mismatch-retry',clean=1,replace=2,partial=2,profiles=('hppe','kernel','user')),
          case('cleanup-foreign-retry',clean=1,replace=1,partial=2),
          case('partial-serial',flow='partial-serial'),case('sd-direct-child',flow='sd-child',clean=2),
          case('unowned',flow='unowned',chip='CHIP_HPPE'),
          case('unowned-init-only',flow='unowned-init'),
          case('unowned-changed-type',flow='unowned',chip='CHIP_ISIS'),
          case('unowned-partial',flow='unowned',partial=1),case('unowned-busy',flow='unowned',childbusy=1),
          case('api-empty',flow='api',profiles=ALL),case('api-P',flow='api',residue=1,profiles=ALL),
          case('api-outer',flow='api',residue=2,profiles=ALL),case('api-hook',flow='api',residue=3,profiles=ALL),
          case('api-vlan',flow='api',residue=9,profiles=ALL),
          case('token-hppe',flow='token'),case('token-isisc',flow='token',chip='CHIP_ISISC',profiles=('nohppe','isisc')),
          case('token-mht',flow='token',chip='CHIP_MHT',profiles=('mht',)),
          case('invalid3',dev=3,profiles=ALL),case('invalidmax',dev=4294967295,profiles=ALL),
          case('invalid-chip',chip='BAD',profiles=ALL),case('fal-null',nullcfg=1,profiles=ALL),
          case('hsl-null',flow='hsl',nullcfg=1,profiles=ALL)]
    rows += [case('epoch-recreate',flow='recreate'),case('epoch-retire-only',flow='retire-only'),
             case('epoch-api',flow='epoch-api'),case('epoch-max',flow='epoch-max',start_epoch=(1<<64)-2),
             case('epoch-retry-cpu',flow='epoch-retry',partial=1),case('epoch-retry-cfg',flow='epoch-retry',oom=1),
             case('epoch-retry-port',flow='epoch-retry',oom=2,profiles=('hppe','kernel','user')),
             case('cleanup-zero-epoch',clean=1,replace=3),case('cleanup-false-flag',clean=1,replace=4),
             case('cleanup-stale-epoch',clean=1,replace=5),case('cleanup-no-outer',clean=1,replace=6),
             case('ledger-flag-only',residue=5,clean=2),case('ledger-epoch-only',residue=6,clean=2)]
    for chip in ('ISIS','ISISC','MHT','DESS','SCOMPHY','UNSPECIFIED','HPPE','APPE','MRPPE'):
        rows.append(case('dispatch-'+chip,chip='CHIP_'+chip,clean=1,profiles=ALL))
    for mask in range(1,8):rows.append(case('vlan-residue'+str(mask),residue=8+mask,profiles=BASE))
    for number in (1,2,3):rows.append(case('oom'+str(number),oom=number,clean=2))
    for fault in ('SD','UK_INIT','LOCK','VLAN_INIT','ADPT','UK_CLEAN','VLAN_CLEAN'):
        rows.append(case('fault-'+fault,fault=fault,clean=1 if fault.endswith('CLEAN') else 2))
    rows.append(case('fault-LEGACY_CLEAN',fault='LEGACY_CLEAN',chip='CHIP_ISIS',clean=1,profiles=('nohppe',)))
    rows.append(case('fault-SD-no-clean',fault='SD'))
    rows.append(case('hsl-fault-SD',flow='hsl',fault='SD',clean=2))
    rows.append(case('hsl-fault-UK_CLEAN',flow='hsl',fault='UK_CLEAN',clean=1))
    rows.append(case('legacy-hook-replacement',chip='CHIP_ISIS',clean=1,replace=7,profiles=('nohppe','isis')))
    for fault in ('SD','UK_INIT','LOCK','UK_CLEAN'):
        for schedule,label in ((1,'transient'),(3,'persistent')):
            rows.append(case('fault-'+fault+'-'+label,fault=fault,schedule=schedule,clean=1 if fault=='UK_CLEAN' else 2))
    for site in ('APISET','METASET','SD','UK_INIT','LOCK','ALLOC','HPPE','VLAN_INIT','ADPT','CHILD_CLEAN','UK_CLEAN','VLAN_CLEAN'):
        rows.append(case('probe-'+site,probe=site,clean=1))
    rows.append(case('probe-VLAN_INIT-error',probe='VLAN_INIT',fault='VLAN_INIT',clean=2))
    rows.append(case('probe-ADPT-error',probe='ADPT',fault='ADPT',clean=2))
    stock=('fal-hppe','fal-appe','fal-mrppe','epoch-recreate','epoch-retire-only','epoch-max','epoch-api')
    for row in rows:
        if row['name'] in stock:row['profiles']=(*row['profiles'],'stock-kernel')
    source.require(len({c['name'] for c in rows})==len(rows),'unique-positive-cases')
    return rows


# Independent positive obligations, not calculated from cases() or observed execution.
P_ALL=('api-empty','api-P','api-outer','api-hook','api-vlan','invalid3','invalidmax','invalid-chip','fal-null','hsl-null',
       'dispatch-ISIS','dispatch-ISISC','dispatch-MHT','dispatch-DESS','dispatch-SCOMPHY','dispatch-UNSPECIFIED',
       'dispatch-HPPE','dispatch-APPE','dispatch-MRPPE')
P_BASE=('foreign-P','held-outer','foreign-hook','adapter-residue','vlan-residue1','vlan-residue2','vlan-residue3',
        'vlan-residue4','vlan-residue5','vlan-residue6','vlan-residue7')
P_HPPE=('fal-hppe','fal-dev1','fal-dev2','fal-appe','fal-mrppe','hsl-hppe','cpu15','multicpu','nocpu','hppe-repeat','cleanup-foreign-hook',
        'cleanup-foreign-retry','partial-serial','sd-direct-child','fault-SD-no-clean','hsl-fault-SD','hsl-fault-UK_CLEAN',
        'unowned','unowned-init-only','unowned-changed-type','unowned-partial','unowned-busy','token-hppe','oom1','oom2','oom3',
        'fault-SD','fault-UK_INIT','fault-LOCK','fault-VLAN_INIT','fault-ADPT','fault-UK_CLEAN','fault-VLAN_CLEAN',
        'probe-APISET','probe-METASET','probe-SD','probe-UK_INIT','probe-LOCK','probe-ALLOC','probe-HPPE',
        'probe-VLAN_INIT','probe-ADPT','probe-CHILD_CLEAN','probe-UK_CLEAN','probe-VLAN_CLEAN',
        'epoch-recreate','epoch-retire-only','epoch-api','epoch-max','epoch-retry-cpu','epoch-retry-cfg',
        'cleanup-zero-epoch','cleanup-false-flag','cleanup-stale-epoch','cleanup-no-outer','ledger-flag-only','ledger-epoch-only',
        'fault-SD-transient','fault-SD-persistent','fault-UK_INIT-transient','fault-UK_INIT-persistent',
        'fault-LOCK-transient','fault-LOCK-persistent','fault-UK_CLEAN-transient','fault-UK_CLEAN-persistent',
        'probe-VLAN_INIT-error','probe-ADPT-error')


def positive_contract():
    return {(p,n) for p in ALL for n in P_ALL} | {(p,n) for p in BASE for n in P_BASE} | \
           {(p,n) for p in HPPE_PROFILES for n in P_HPPE} | {('hppe','cleanup-mismatch'),('kernel','cleanup-mismatch'),
           ('user','cleanup-mismatch'),('nohppe','token-isisc'),('isisc','token-isisc'),('mht','token-mht'),
           ('hppe','epoch-retry-port'),('kernel','epoch-retry-port'),('user','epoch-retry-port'),('nohppe','fault-LEGACY_CLEAN'),
           ('hppe','cleanup-mismatch-retry'),('kernel','cleanup-mismatch-retry'),('user','cleanup-mismatch-retry'),
           ('nohppe','legacy-hook-replacement'),('isis','legacy-hook-replacement'),
           ('nohppe','held-outer-changed'),('mht','held-outer-changed')} | \
           {('stock-kernel',n) for n in ('fal-hppe','fal-appe','fal-mrppe','epoch-recreate','epoch-retire-only','epoch-max','epoch-api')}


def positive_inventory(rows):
    keys=[(r['profile'],r['case']) for r in rows]
    source.require(len(set(keys))==len(keys) and set(keys)==positive_contract(),'POSITIVE_INVENTORY')


def chip_value(c,domain):return 2049 if c['chip']=='BAD' else domain['enums']['ssdk_chip_type'][c['chip']]


def header(matrix,domain):
    fields=['name','flow','fault','probe','dev','chip','cpu','lan','wan','inner','bmp','residue','oom','clean','repeat','replace','partial','childbusy','nullcfg','start_epoch','schedule']
    def val(v):return json.dumps(v) if isinstance(v,str) else str(v)+'ULL' if v>4294967295 else str(v)+'u' if v>2147483647 else str(v)
    lines=[f'_Static_assert(sizeof({n})=={v},"actual small host type");' for n,v in domain['sizes'].items()]
    lines+=['static const struct input inputs[]={']
    for c in matrix:
        d=dict(c,chip=chip_value(c,domain));lines.append('{'+','.join('.'+k+'='+val(d[k]) for k in fields)+'},')
    return '\n'.join(lines+['};'])


def oracle(c,profile,domain):
    e=domain['errors'];sizes=domain['sizes'];chips=domain['enums']['ssdk_chip_type'];compiled=PROFILES[profile]['chips']
    hppe='HPPE' in compiled;combined=profile=='combined';d=c['dev'];chip=chip_value(c,domain)
    events=[];add=events.append;returns=[];blocks=[];serial=allocs=0;calls={};boot=False
    O={i:0 for i in range(3)};C=dict(O);P=dict(O);T=dict(O);busy=dict(O);acq=dict(O);phase=dict(O);G=dict(O);typ=dict(O);epoch=dict(O);OE=dict(O)
    meta={i:[i,7,9,11,13,17,0,0,68] for i in range(3)};api={i:[0 if i==d else 2]+[2]*10+[10000+i*10+j for j in range(3)] for i in range(3)}
    res={i:[0]*4 for i in range(3)}
    cfg=[1,chip,c['cpu'],c['lan'],c['wan'],c['inner'],77,0xc0ffee]
    def obj(ident):return next(b for b in blocks if b['id']==ident)
    def seed(dev,kind,ident):
        value=[0,chips['CHIP_DESS'],0,0,0,0,0,0xbadc0de] if kind!=3 else [0x88,[1<<i for i in range(5)],[1000+dev*16+i for i in range(16)]]
        blocks.append(dict(id=ident,kind=kind,live=1,foreign=1,value=value));return ident
    for i in range(3):
        if i!=d:O[i]=seed(i,1,100+i*10);P[i]=seed(i,3,102+i*10)
    if d<3:
        epoch[d]=c['start_epoch']
        if c['residue']==1:P[d]=seed(d,3,900)
        if c['residue']==2:O[d]=seed(d,1,901)
        if c['residue']==3:api[d][0]=2
        if c['residue']==4:res[d][0]=1
        if c['residue']==5:acq[d]=1
        if c['residue']==6:OE[d]=13
        if c['residue']>=8:res[d][1:]=[int(bool((c['residue']-8)&(1<<i))) for i in range(3)]
    def probe(site):
        if c['probe']!=site:return
        if phase[d] in (3,6):add(f'RUNNING_END {site} {phase[d]} {e["SW_BAD_STATE"]}\n')
        add(f'PROBE {site} {phase[d]} '+' '.join(map(str,[e['SW_BUSY']]*5+[e['SW_ALREADY_EXIST']]))+'\n')
    def leaf(name,a=0,b=0):
        probe(name);calls[name]=calls.get(name,0)+1
        r=0 if c['fault']!=name else e['SW_READ_ERROR'] if calls[name]==1 else 0 if c['schedule']==1 else e['SW_READ_ERROR'] if c['schedule']==3 else e['SW_WRITE_ERROR']
        add(f'LEAF {name} {a} {b} {calls[name]} {r}\n');return r
    def alloc(kind):
        nonlocal serial,allocs
        probe('ALLOC');serial+=1;allocs+=1;ok=allocs!=c['oom'];size=sizes['port_info_t' if kind==3 else 'ssdk_init_cfg']
        add(f'ALLOC {serial} {kind} {size} {int(ok)}\n')
        if not ok:return 0
        value=[0,[0]*5,[0]*16] if kind==3 else [0]*8
        blocks.append(dict(id=serial,kind=kind,live=1,foreign=0,value=value));return serial
    def free(ident):
        b=obj(ident);source.require(b['live'] and not b['foreign'],'oracle-free-owned');b['live']=0;add(f'FREE {ident}\n')
    def copy(ident,config):obj(ident)['value']=list(config);add(f'COPY {ident} {sizes["ssdk_init_cfg"]}\n')
    def cfg_line(name,dev,ident):
        if ident:add('CFG %s %d %d %s\n'%(name,dev,ident,' '.join(map(str,obj(ident)['value']))))
    def snap(label):
        add('SNAP '+label+'\n')
        for i in range(3):
            add('META %d %s\n'%(i,' '.join(map(str,meta[i]))));add(f'OUTER {i} {O[i]} {acq[i]} {phase[i]} {G[i]} {typ[i]}\n')
            add(f'EPOCH {i} {epoch[i]} {OE[i]}\n')
            cfg_line('O',i,O[i]);cfg_line('C',i,C[i]);add(f'CHILD {i} {C[i]} {P[i]} {T[i]} {busy[i]}\n')
            if P[i]:
                v=obj(P[i])['value'];add('PORT %d %s\n'%(i,' '.join(map(str,[v[0]]+v[1]+v[2]))))
            add('API %d %s\n'%(i,' '.join(map(str,api[i]))));add('RESIDUE %d %s\n'%(i,' '.join(map(str,res[i]))))
        for b in blocks:
            reach=int(b['id'] in list(O.values())+list(C.values())+list(P.values())+list(T.values()))
            add(f'OWNER {b["id"]} {b["kind"]} {b["live"]} {b["foreign"]} {reach}\n')
            if b['live']:
                v=b['value'];values=[v[0],*v[1],*v[2]] if b['kind']==3 else v
                add(('PORTBLOCK' if b['kind']==3 else 'CFGBLOCK')+' %d %s\n'%(b['id'],' '.join(map(str,values))))
        add('COUNTERS'+''.join(f' {k}={v}' for k,v in calls.items())+f' ALLOC={allocs}\n')
    def ret(r):returns.append(r);add(f'RETURN {r}\n');snap('AFTER_CALL')
    def query():return e['SW_BUSY'] if busy[d] else e['SW_ALREADY_EXIST'] if C[d] or T[d] else 0
    def available(request=True):
        if d>=3:return e['SW_OUT_OF_RANGE']
        if phase[d]:return e['SW_BUSY']
        if O[d]:return e['SW_ALREADY_EXIST']
        if hppe:
            if acq[d] or OE[d]:return e['SW_ALREADY_EXIST']
            q=query()
            if q:return q
        if api[d][0] and (not hppe or api[d][0]!=1 or (request and chip not in (chips['CHIP_HPPE'],chips['CHIP_APPE'],chips['CHIP_MRPPE']))):return e['SW_ALREADY_EXIST']
        is_hp=request and chip in (chips['CHIP_HPPE'],chips['CHIP_APPE'],chips['CHIP_MRPPE'])
        if P[d] and not(combined and is_hp):return e['SW_ALREADY_EXIST']
        if any(res[d]):return e['SW_ALREADY_EXIST']
        return 0
    def dispatch():
        if chip==chips['CHIP_UNSPECIFIED']:
            return 0 if ('ISIS' in compiled or 'ISISC' in compiled) else e['SW_INIT_ERROR']
        known={chips['CHIP_'+n]:n for n in ('ISIS','ISISC','MHT','DESS','SCOMPHY','HPPE','APPE','MRPPE')}
        if chip not in known:return e['SW_BAD_PARAM']
        kind=known[chip];return 0 if ('HPPE' in compiled if kind in ('HPPE','APPE','MRPPE') else kind in compiled) else e['SW_INIT_ERROR']
    def begin():
        if d>=3:return e['SW_OUT_OF_RANGE']
        if c['nullcfg']:return e['SW_BAD_PTR']
        r=available()
        if not r:r=dispatch()
        if not r:G[d]=-1;phase[d]=1
        return r
    def api_reset():probe('APISET');add(f'SET API {d}\n');api[d]=[0]*14
    def child(config):
        probe('HPPE')
        if busy[d]:return e['SW_BUSY']
        if C[d] or T[d]:return e['SW_ALREADY_EXIST']
        if epoch[d]==(1<<64)-1:return e['SW_BAD_STATE']
        saved=list(meta[d]);ident=alloc(2)
        if not ident:return e['SW_OUT_OF_MEM']
        copy(ident,config);front=bin((config[3]|config[4])&65535).count('1');meta[d][3]=front;cpus=config[2]&65535
        if not cpus:meta[d]=saved;free(ident);return e['SW_BAD_VALUE']
        cpu=(cpus&-cpus).bit_length()-1;nr=front+bin(config[5]&65535).count('1')+1
        meta[d]=[meta[d][0],cpu,nr,front,nr,4096,1,config[0],config[4]]
        p=0
        if not combined:
            p=alloc(3)
            if not p:meta[d]=saved;free(ident);return e['SW_OUT_OF_MEM']
            add(f'ZERO {p} {sizes["port_info_t"]}\n');v=obj(p)['value'];inner=obj(O[d])['value'][5] if O[d] else 0
            for port in range(16):
                if port==cpu or ((c['bmp']|inner)&(1<<port)):
                    v[0]|=1<<port
                    for t,yes in enumerate((bool(c['bmp']&(1<<port)),True,port!=cpu,bool(inner&(1<<port)),port==cpu)):
                        if yes:v[1][t]|=1<<port
            P[d]=p;T[d]=p
        C[d]=ident;epoch[d]+=1
        if not combined:api[d][:11]=[1]*11
        return 0
    def core():
        nonlocal boot
        probe('METASET');add(f'SET META {d}\n');meta[d]=[0]*9
        if not boot:
            sequence=[('SD',d,chip),('UK_INIT',77,0)]
            if profile!='stock-kernel':sequence.append(('LOCK',0,0))
            for name,a,b in sequence:
                r=leaf(name,a,b)
                if r:return r
                if name=='SD' and c['flow']=='sd-child':
                    r=child(cfg);source.require(r==0,'oracle-sd-actor');add(f'SD_CHILD_RETURN {r}\n')
            boot=True
        typ[d]=chip
        if chip==chips['CHIP_UNSPECIFIED']:
            typ[d]=next(chips['CHIP_'+n] for n in ('ISIS','ISISC','MHT','DESS','HPPE','SCOMPHY') if n in compiled)
        ident=alloc(1)
        if not ident:return e['SW_OUT_OF_MEM']
        O[d]=ident;copy(ident,cfg)
        if profile=='stock-kernel':obj(ident)['value'][6]=254
        if chip in (chips['CHIP_HPPE'],chips['CHIP_APPE'],chips['CHIP_MRPPE']):
            r=child(cfg)
            if not r:acq[d]=1;OE[d]=epoch[d]
            return r
        name=next(n for n in ('ISIS','ISISC','MHT','DESS','SCOMPHY','UNSPECIFIED') if chips['CHIP_'+n]==chip)
        if name=='UNSPECIFIED':name='ISIS' if 'ISIS' in compiled else 'ISISC'
        r=leaf(name,d,chip)
        if not r:meta[d]=[d,0,6,5,4,4096,1,1,c['wan']];api[d][0]=3
        return r
    def init(fal=True):
        if not fal and d>=3:return e['SW_BAD_PARAM']
        r=begin()
        if r:return r
        if fal:phase[d]=2;api_reset()
        phase[d]=3;r=core();phase[d]=4
        if not r and fal:r=leaf('VLAN_INIT',d,0)
        if not r and fal:r=leaf('ADPT',d,chip)
        G[d]=0;phase[d]=0;return r
    def clean(fal=True):
        if d>=3:return e['SW_OUT_OF_RANGE']
        phase[d]=6;r=0
        if hppe and acq[d] and (not O[d] or not OE[d]):r=e['SW_BAD_STATE']
        if not r and hppe and not acq[d]:r=e['SW_BAD_STATE'] if OE[d] else query()
        if not r and O[d]:
            if hppe and acq[d]:
                if api[d][0] not in (0,1):r=e['SW_BAD_STATE']
                else:
                    if busy[d]:r=e['SW_BUSY']
                    elif not OE[d] or not C[d] or epoch[d]!=OE[d]:r=e['SW_BAD_STATE']
                    else:
                        r=direct_clean()
                        if not r:
                            acq[d]=0;OE[d]=0
                            if api[d][0]==1:api[d][0]=0
            elif api[d][0]:
                r=leaf('LEGACY_CLEAN',d,0)
                if not r:api[d][0]=2 if c['replace']==7 else 0
            if not r:free(O[d]);O[d]=0
        if not r:r=leaf('UK_CLEAN')
        phase[d]=7
        if not r and fal:r=leaf('VLAN_CLEAN',d,0)
        G[d]=0;phase[d]=0;return r
    def direct_clean():
        probe('CHILD_CLEAN')
        if busy[d]:return e['SW_BUSY']
        if C[d]:
            if T[d] and P[d]!=T[d]:return e['SW_BAD_STATE']
            if T[d]:free(P[d]);P[d]=0;T[d]=0
            free(C[d]);C[d]=0
        return 0
    snap('ENTRY')
    if c['flow']=='token':
        for code in ('SW_BAD_PTR','SW_BAD_PTR','SW_BAD_STATE','SW_BAD_PTR','SW_BAD_PTR','SW_BAD_PTR','SW_BAD_PTR','SW_BAD_PTR','SW_BAD_PTR'):ret(e[code])
        ret(begin())
        for _ in range(4):ret(e['SW_BAD_PTR'])
        ret(e['SW_BAD_STATE']);phase[d]=2;api_reset();ret(0);ret(e['SW_BAD_STATE']);phase[d]=0;G[d]=0;ret(0)
        for code in ('SW_BAD_STATE','SW_BAD_STATE','SW_BAD_STATE','SW_BAD_PTR'):ret(e[code])
        phase[d]=5;ret(0);ret(e['SW_BAD_STATE']);ret(e['SW_BAD_STATE']);r=clean(False);phase[d]=7;ret(r)
        ret(e['SW_BAD_STATE']);phase[d]=0;ret(0);ret(e['SW_BAD_STATE'])
    elif c['flow']=='partial-serial':
        cfg[2]=0;ret(init(False));cfg[2]=c['cpu'];ret(child(cfg));snap('SERIAL_PARTIAL_BEFORE_CLEAN');ret(clean(False))
    elif c['flow'] in ('recreate','retire-only'):
        ret(init());old_ident=C[d];snap('BEFORE_DIRECT_RETIRE');ret(direct_clean())
        if c['flow']=='recreate':other=list(cfg);other[-1]+=1;ret(child(other));add(f'REPLACEMENT {old_ident} {C[d]}\n')
        snap('BEFORE_STALE_OUTER_CLEAN');ret(clean())
    elif c['flow']=='epoch-api':
        for code in ('SW_BAD_PTR','SW_OUT_OF_RANGE','SW_OUT_OF_RANGE','SW_BAD_STATE'):ret(e[code])
        add('OWNED_OUTPUT 77\n');ret(e['SW_BAD_PTR']);add('OWNED_OUTPUT 0\n');ret(child(cfg));add(f'OWNED_OUTPUT {epoch[d]}\n')
        ret(e['SW_ALREADY_EXIST']);add('OWNED_OUTPUT 0\n')
        busy[d]=1;ret(e['SW_BUSY']);ret(e['SW_BUSY']);busy[d]=0
        ret(e['SW_BAD_STATE']);ret(e['SW_BAD_STATE']);busy[d]=1;ret(e['SW_BUSY']);busy[d]=0
        snap('BEFORE_OWNED_CLEAN');ret(direct_clean());ret(e['SW_BAD_STATE'])
    elif c['flow']=='epoch-retry':
        first=list(cfg)
        if c['partial']:first[2]=0
        ret(child(first));add('OWNED_OUTPUT 0\n');ret(child(cfg));add(f'OWNED_OUTPUT {epoch[d]}\n');snap('BEFORE_OWNED_CLEAN');ret(direct_clean())
    elif c['flow']=='epoch-max':
        ret(init());ret(child(cfg));snap('BEFORE_MAX_CLEAN');ret(clean());snap('BEFORE_EXHAUST_DIRECT');ret(child(cfg));ret(init())
    elif c['flow'] in ('unowned','unowned-init'):
        config=list(cfg);config[1]=chips['CHIP_HPPE'];ret(child(config))
        if c['partial']:O[d]=seed(d,1,901)
        if c['childbusy']:busy[d]=1
        snap('UNOWNED_BEFORE_OUTER')
        if c['flow']=='unowned':ret(clean())
        ret(init())
    elif c['flow']=='api':
        r=e['SW_BAD_PARAM'] if d>=3 else available(False)
        if not r:api_reset()
        ret(r)
    else:
        for _ in range(c['repeat']):r=init(c['flow']!='hsl');ret(r)
        if c['clean'] and (not r or c['clean']==2):
            if c['replace']==1:api[d][0]=2
            if c['replace']==2 and T[d]:P[d]=seed(d,3,900)
            if c['replace']==3:OE[d]=0
            if c['replace']==4:acq[d]=0
            if c['replace']==5:OE[d]+=1
            if c['replace']==6:O[d]=0
            snap('BEFORE_CLEAN');ret(clean(c['flow']!='hsl'))
            if c['partial']==2:snap('BEFORE_RETRY_CLEAN');ret(clean(c['flow']!='hsl'))
        if d>=3:
            for code in ('SW_BAD_PARAM','SW_BAD_PARAM','SW_OUT_OF_RANGE','SW_OUT_OF_RANGE'):ret(e[code])
    add('END SERIAL_REDUCED_MODEL\n');return returns,''.join(events).encode()


# Fixed source obligations are independent of variants(), host output and completion.
NEGATIVE_CONTRACT=(
 ('public-api-bypass','hsl_api_init','api-P','FIRST_ERROR',ALL),
 ('port-residue-bypass','hsl_port_prop_slot_available','api-P','FIRST_ERROR',ALL),
 ('ambient-busy-bypass','hsl_dev_init_available','probe-APISET','REENTRY_BUSY',HPPE_PROFILES),
 ('busy-silent-api-write','hsl_dev_api_init_check','probe-APISET','REENTRY_STATE_UNCHANGED',HPPE_PROFILES),
 ('busy-silent-metadata-write','hsl_dev_init_available','probe-APISET','REENTRY_STATE_UNCHANGED',HPPE_PROFILES),
 ('missing-child-query','hppe_init_state_check','unowned','FIRST_ERROR',HPPE_PROFILES),
 ('missing-acquisition-flag','hsl_dev_init_core','fal-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('skip-owned-child-retirement','hsl_dev_cleanup_core','fal-hppe','EXACT_STATE_TRACE',HPPE_PROFILES),
 ('adopt-direct-child','hsl_dev_cleanup_core','unowned','FIRST_ERROR',HPPE_PROFILES),
 ('failed-clean-silent-old-token-write','hsl_port_prop_cleanup_owned','cleanup-mismatch','EXACT_STATE_TRACE',('hppe','kernel','user')),
 ('fal-release-before-adapter','fal_init','probe-ADPT','REENTRY_BUSY',HPPE_PROFILES),
 ('fal-release-before-vlan-clean','fal_cleanup','probe-VLAN_CLEAN','REENTRY_BUSY',HPPE_PROFILES),
 ('sd-repeated','hsl_dev_init_core','fault-SD','FIRST_ERROR',HPPE_PROFILES),
 ('uk-init-repeated','hsl_dev_init_core','fault-UK_INIT','FIRST_ERROR',HPPE_PROFILES),
 ('api-lock-repeated','hsl_dev_init_core','fault-LOCK','FIRST_ERROR',HPPE_PROFILES),
 ('uk-clean-repeated','hsl_dev_cleanup_core','fault-UK_CLEAN','FIRST_ERROR',HPPE_PROFILES),
 ('wrong-unspecified-dispatch','hsl_dev_dispatch_check','dispatch-UNSPECIFIED','EXACT_STATE_TRACE',('mht',)),
 ('vlan-residue-bypass','fal_vlan_init_available','vlan-residue1','FIRST_ERROR',HPPE_PROFILES),
 ('guard-not-consumed','hsl_dev_guard_end','token-hppe','GUARD_CONSUME',HPPE_PROFILES),
 ('api-token-reused','hsl_dev_api_init_guarded','token-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('own-flag-after-failed-child','hsl_dev_init_core','nocpu','FIRST_ERROR',HPPE_PROFILES))

EXTRA_NEGATIVE_CONTRACT=(
 ('fal-unauthorized-api','fal_init','fal-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('fal-unauthorized-hsl','fal_init','fal-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('lower-child-init-query-omitted','hsl_dev_init_available','unowned-init-only','EXACT_STATE_TRACE',('combined',)),
 ('adapter-gate-omitted','hsl_dev_init_available','adapter-residue','FIRST_ERROR',HPPE_PROFILES),
 ('preclear-port-gate-omitted','hsl_dev_init_available','foreign-P','EXACT_STATE_TRACE',('hppe','kernel','user')),
 ('adopt-serial-partial-child','hsl_dev_cleanup_core','partial-serial','FIRST_ERROR',HPPE_PROFILES),
 ('adopt-sd-model-child','hsl_dev_cleanup_core','sd-direct-child','FIRST_ERROR',HPPE_PROFILES),
 ('fal-release-before-vlan','fal_init','probe-VLAN_INIT-error','REENTRY_BUSY',HPPE_PROFILES),
 ('cleanup-release-before-uk','hsl_dev_cleanup_guarded','probe-UK_CLEAN','REENTRY_BUSY',HPPE_PROFILES),
 ('vlan-pool-bypass','fal_vlan_init_available','vlan-residue1','FIRST_ERROR',HPPE_PROFILES),
 ('vlan-db-bypass','fal_vlan_init_available','vlan-residue2','FIRST_ERROR',HPPE_PROFILES),
 ('vlan-list-bypass','fal_vlan_init_available','vlan-residue4','FIRST_ERROR',HPPE_PROFILES),
 ('copied-guard-accepted','hsl_dev_guard_id','token-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('running-end-init','hsl_dev_guard_end','probe-SD','RUNNING_END_REJECT',HPPE_PROFILES),
 ('running-end-clean','hsl_dev_guard_end','probe-UK_CLEAN','RUNNING_END_REJECT',HPPE_PROFILES),
 ('fal-first-error-lost','fal_init','fault-SD','FIRST_ERROR',HPPE_PROFILES),
 ('fal-clean-first-error-lost','fal_cleanup','fault-UK_CLEAN','FIRST_ERROR',HPPE_PROFILES),
 ('fal-error-guard-stuck','fal_init','fault-SD-no-clean','EXACT_STATE_TRACE',HPPE_PROFILES),
 ('legacy-new-hook-cleared','hsl_dev_cleanup_core','legacy-hook-replacement','EXACT_STATE_TRACE',('nohppe','isis')),
 ('epoch-match-omitted','hppe_cleanup_owned','epoch-recreate','FIRST_ERROR',HPPE_PROFILES),
 ('epoch-reset-on-cleanup','hppe_cleanup','fal-hppe','EXACT_STATE_TRACE',HPPE_PROFILES),
 ('epoch-success-not-incremented','hppe_init','fal-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('epoch-failed-constructor-increment','hppe_init','epoch-retry-cpu','EXACT_STATE_TRACE',HPPE_PROFILES),
 ('owned-output-pregranted','hppe_init_owned','epoch-retry-cpu','FIRST_ERROR',HPPE_PROFILES),
 ('owned-output-missing','hppe_init_owned','fal-hppe','FIRST_ERROR',HPPE_PROFILES),
 ('epoch-output-truncated','hppe_init_owned','epoch-max','FIRST_ERROR',HPPE_PROFILES),
 ('epoch-cap-omitted','hppe_init','epoch-max','FIRST_ERROR',HPPE_PROFILES),
 ('hsl-epoch-cleared-before-child','hsl_dev_cleanup_core','cleanup-mismatch','EXACT_STATE_TRACE',('hppe','kernel','user')),
 ('hsl-epoch-not-cleared','hsl_dev_cleanup_core','fal-hppe','EXACT_STATE_TRACE',HPPE_PROFILES),
 ('hsl-flag-cleared-before-child','hsl_dev_cleanup_core','cleanup-mismatch-retry','EXACT_STATE_TRACE',('hppe','kernel','user')),
 ('hsl-epoch-only-init-accepted','hsl_dev_init_available','ledger-epoch-only','FIRST_ERROR',HPPE_PROFILES),
 ('hsl-flag-only-init-accepted','hsl_dev_init_available','ledger-flag-only','FIRST_ERROR',HPPE_PROFILES),
 ('hsl-no-outer-clean-accepted','hsl_dev_cleanup_core','cleanup-no-outer','FIRST_ERROR',HPPE_PROFILES),
 ('hsl-false-flag-epoch-clean-accepted','hsl_dev_cleanup_core','ledger-epoch-only','FIRST_ERROR',HPPE_PROFILES),
 ('changed-owner-availability-bypass','hsl_dev_init_begin','held-outer-changed','CFG_COPY_OWNER',('nohppe','mht')),
 ('fal-id-priority','fal_init','invalid3','FIRST_ERROR',ALL),
 ('cleanup-id-priority','hsl_dev_cleanup','invalid3','FIRST_ERROR',ALL),
 ('null-admission-priority','hsl_dev_init_begin','fal-null','FIRST_ERROR',ALL))

FINAL_NEGATIVE_CONTRACT=(
 ('busy-silent-hook-write','hsl_dev_api_init_check','probe-SD','REENTRY_STATE_UNCHANGED',('hppe','kernel','user')),
 ('busy-silent-nrphy-write','hsl_dev_init_available','probe-SD','REENTRY_STATE_UNCHANGED',HPPE_PROFILES),
 ('hsl-first-error-lost','hsl_dev_init','hsl-fault-SD','FIRST_ERROR',HPPE_PROFILES),
 ('hsl-clean-first-error-lost','hsl_dev_cleanup','hsl-fault-UK_CLEAN','FIRST_ERROR',HPPE_PROFILES),
 ('foreign-hook-clean-guard-omitted','hsl_dev_cleanup_core','cleanup-foreign-retry','FIRST_ERROR',HPPE_PROFILES),
 ('failed-clean-silent-old-token-phy-write','hsl_port_prop_cleanup_owned','cleanup-mismatch','EXACT_STATE_TRACE',('hppe','kernel','user')),
 ('owned-output-busy-priority','hppe_init_owned','epoch-api','FIRST_ERROR',HPPE_PROFILES),
 ('owned-output-null-priority','hppe_init_owned','epoch-api','FIRST_ERROR',HPPE_PROFILES),
 ('owned-clean-boundary-priority','hppe_cleanup_owned','epoch-api','FIRST_ERROR',HPPE_PROFILES),
 ('owned-absent-C-check-omitted','hppe_cleanup_owned','epoch-retire-only','FIRST_ERROR',HPPE_PROFILES))


def negative_contract(kind):
    if kind=='source':
        fixed=list(NEGATIVE_CONTRACT)+list(EXTRA_NEGATIVE_CONTRACT)+list(FINAL_NEGATIVE_CONTRACT)
        for name,symbol,case in (('sd-repeated','hsl_dev_init_core','fault-SD'),('uk-init-repeated','hsl_dev_init_core','fault-UK_INIT'),
                                 ('api-lock-repeated','hsl_dev_init_core','fault-LOCK'),('uk-clean-repeated','hsl_dev_cleanup_core','fault-UK_CLEAN')):
            fixed += [(name,symbol,case+'-transient','FIRST_ERROR',HPPE_PROFILES),
                      (name,symbol,case+'-persistent','EXACT_STATE_TRACE',HPPE_PROFILES)]
        return [dict(profile=p,name=n,symbol=s,case=c,marker=m,classification='directed actual source semantic mutant')
                for n,s,c,m,ps in fixed for p in ps]
    if kind=='old':return [dict(profile=p,name='old-public-api',symbol='complete27 hsl_api_init',case='probe-APISET',
                               marker='REENTRY_BUSY',classification='safe old public API guard bypass witness') for p in HPPE_PROFILES]
    raise RuntimeError('inventory-kind')


def negative_inventory(rows,kind,completed=False):
    try:keys=[tuple(r[k] for k in FIELDS) for r in rows]
    except (KeyError,TypeError) as ex:raise RuntimeError('NEGATIVE_INVENTORY') from ex
    source.require(len(keys)==len(set(keys)),'NEGATIVE_DUPLICATE')
    source.require(set(keys)=={tuple(r[k] for k in FIELDS) for r in negative_contract(kind)},'NEGATIVE_INVENTORY')
    if completed:source.require(all(r.get('execution')=='CLEAN_COMPILE_EXACT86' and re.fullmatch('[0-9a-f]{64}',r.get('source_sha256','')) for r in rows),'NEGATIVE_EXECUTION')


def inventory_controls():
    rows=negative_contract('source');negative_inventory(rows,'source');negative_inventory(negative_contract('old'),'old');rejected=[]
    def reject(name,bad,error,completed=False):
        try:negative_inventory(bad,'source',completed)
        except RuntimeError as ex:source.require(str(ex)==error,'inventory-specific-control')
        else:raise RuntimeError('accepted-inventory-pollution:'+name)
        rejected.append(name)
    reject('empty',[],'NEGATIVE_INVENTORY');reject('missing',rows[:-1],'NEGATIVE_INVENTORY');reject('duplicate',rows+[rows[0]],'NEGATIVE_DUPLICATE')
    for field in FIELDS:reject('wrong-'+field,[dict(rows[0],**{field:'WRONG'})]+rows[1:],'NEGATIVE_INVENTORY')
    completed=[dict(r,execution='CLEAN_COMPILE_EXACT86',source_sha256='a'*64) for r in rows];negative_inventory(completed,'source',True)
    reject('unexecuted',rows,'NEGATIVE_EXECUTION',True)
    reject('missing-immediate-state',[r for r in rows if r['name'] not in ('busy-silent-api-write','busy-silent-metadata-write')],'NEGATIVE_INVENTORY')
    reject('missing-old-token-payload',[r for r in completed if r['name']!='failed-clean-silent-old-token-write'],'NEGATIVE_INVENTORY',True)
    p=[dict(profile=p,case=n) for p,n in sorted(positive_contract())];positive_inventory(p)
    positive_rejects=[]
    for name,bad in [('empty',[]),('missing',p[:-1]),('duplicate',p+[p[0]]),('wrong-profile',[dict(p[0],profile='WRONG')]+p[1:])]:
        try:positive_inventory(bad)
        except RuntimeError as ex:source.require(str(ex)=='POSITIVE_INVENTORY','positive-specific-control')
        else:raise RuntimeError('accepted-positive-pollution')
        positive_rejects.append(name)
    return dict(valid=4,negative_rejects=rejected,positive_rejects=positive_rejects,classification='pure inventory controls, not source fault credits')


PRIVATE_TUS={
    **{n:'src/hsl/hsl_dev.c' for n in ('dev_table','dev_ssdk_cfg','hsl_dev_guards','hsl_hppe_owned','hsl_hppe_owner_epoch')},
    **{n:source.HPPE for n in ('hppe_cfg','hppe_port_owner','hppe_initializing','hppe_owner_epoch')},
    'hsl_api_table':'src/hsl/hsl_api.c','p_port_info':'src/hsl/hsl_port_prop.c',
    **{n:'src/fal/fal_vlan.c' for n in ('vlan_pool','vlan_db','vlan_list')}}


def source_visibility(path,text):
    code=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*','',text)
    source.require(not re.search(r'(?:->|\.)\s*extra\b',code),'MUTANT_MODEL_FIELD')
    source.require(not re.search(r'\b(?:foreign_clean|foreign_sd|legacy_clean|probe|leaf|snapshot|blocks|alloc_role)\b',code),'MUTANT_MODEL_SYMBOL')
    for name,owner in PRIVATE_TUS.items():
        source.require(path==owner or not re.search(r'\b'+name+r'\b',code),'MUTANT_TU_PRIVATE')
    if path=='src/fal/fal_init.c':source.require(not re.search(r'\bguard\s*->',code),'MUTANT_OPAQUE_GUARD')


def source_visibility_controls():
    source_visibility('src/hsl/hsl_dev.c','hsl_api_ptr_get(dev_id)->dev_clean = hppe_cleanup;')
    source_visibility('src/hsl/hsl_dev.c','guard->phase = HSL_DEV_INIT_POST;')
    source_visibility('src/fal/fal_init.c','hsl_dev_guard_end(&guard);')
    rejects=[]
    for name,path,text,marker in (
        ('api-private','src/hsl/hsl_dev.c','hsl_api_table[dev_id].dev_clean = hppe_cleanup;','MUTANT_TU_PRIVATE'),
        ('api-extra','src/hsl/hsl_dev.c','hsl_api_ptr_get(dev_id)->extra[0] = 1;','MUTANT_MODEL_FIELD'),
        ('opaque-phase','src/fal/fal_init.c','guard->phase = HSL_DEV_IDLE;','MUTANT_OPAQUE_GUARD'),
        ('actor-name','src/hsl/hsl_dev.c','probe("SD");','MUTANT_MODEL_SYMBOL'),
        ('foreign-epoch','src/hsl/hsl_dev.c','hppe_owner_epoch[dev_id] = 0;','MUTANT_TU_PRIVATE')):
        try:source_visibility(path,text)
        except RuntimeError as ex:source.require(str(ex)==marker,'source-admission-specific-control')
        else:raise RuntimeError('source-admission-pollution-accepted')
        rejects.append(name)
    return dict(valid=3,rejects=rejects,scope='known TU-private/opaque/model-field identifier gate only; not target header/link/ABI compilation')


def obligation_map():
    # Fixed38 independent semantic IDs, backed by fixed case/control names above.
    rows={}
    def row(key,positives,controls,notes=''):
        rows[key]=dict(positive_cases=positives.split(),source_controls=controls.split(),limits=notes)
    row('OA-T01','fal-hppe fal-appe fal-mrppe','fal-unauthorized-api')
    row('OA-T02','fal-hppe hsl-hppe','fal-unauthorized-hsl')
    row('OA-T03','api-P api-outer api-hook api-vlan','public-api-bypass port-residue-bypass')
    row('OA-T04','unowned-init-only','lower-child-init-query-omitted','Combined init-only: no cleanup-first shortcut; same ALREADY_EXIST after incorrect pre-clear is caught by full state trace.')
    row('OA-T05','held-outer-changed unowned-changed-type','changed-owner-availability-bypass','Changed legacy request is supported in nohppe/MHT profiles; actual child remains protected for unsupported requests too.')
    row('OA-T06','foreign-P adapter-residue vlan-residue1 vlan-residue2 vlan-residue4','preclear-port-gate-omitted adapter-gate-omitted vlan-pool-bypass vlan-db-bypass vlan-list-bypass')
    row('OA-T07','invalid3 invalidmax fal-null hsl-null token-hppe epoch-api','fal-id-priority cleanup-id-priority null-admission-priority owned-output-null-priority owned-output-busy-priority','Safe wrong-error controls, never unsafe removed-ID-guard crash credit.')
    row('OA-T08','token-hppe token-isisc token-mht','copied-guard-accepted','Foreign copied token is a real well-backed struct inside a holder, not unsafe raw interior-pointer dereference or arbitrary capability security.')
    row('OA-T09','token-hppe probe-SD probe-UK_CLEAN','guard-not-consumed api-token-reused running-end-init running-end-clean')
    row('OA-T10','probe-APISET probe-METASET probe-SD probe-ALLOC probe-HPPE probe-VLAN_INIT probe-ADPT probe-CHILD_CLEAN probe-UK_CLEAN probe-VLAN_CLEAN','ambient-busy-bypass busy-silent-api-write busy-silent-metadata-write')
    row('OA-T11','probe-SD','busy-silent-hook-write','Real getter/real dev_clean field, active property profiles only; no flattened cross-TU table or model-only extra-field mutation.')
    row('OA-T12','probe-SD','busy-silent-nrphy-write')
    row('OA-T13','probe-VLAN_INIT probe-VLAN_INIT-error probe-ADPT probe-ADPT-error','fal-release-before-vlan fal-release-before-adapter')
    row('OA-T14','probe-UK_CLEAN probe-VLAN_CLEAN','cleanup-release-before-uk fal-release-before-vlan-clean')
    row('OA-T15','fault-SD-no-clean hsl-fault-SD hsl-fault-UK_CLEAN fault-ADPT fault-VLAN_CLEAN','fal-first-error-lost fal-clean-first-error-lost hsl-first-error-lost hsl-clean-first-error-lost fal-error-guard-stuck')
    for key,site,control in (('OA-T16','SD','sd-repeated'),('OA-T17','UK_INIT','uk-init-repeated'),('OA-T18','LOCK','api-lock-repeated'),('OA-T19','UK_CLEAN','uk-clean-repeated')):
        row(key,' '.join('fault-'+site+s for s in ('','-transient','-persistent')),control,'All three fixed schedules; SD/LOCK failure is synthetic. No shared UK/bootstrap compensation claim.')
    row('OA-T20','dispatch-HPPE dispatch-APPE dispatch-MRPPE dispatch-UNSPECIFIED dispatch-ISIS dispatch-ISISC dispatch-MHT dispatch-DESS dispatch-SCOMPHY invalid-chip','wrong-unspecified-dispatch missing-acquisition-flag own-flag-after-failed-child','Four HPPE-only modes, noHPPE, ISIS-only/ISISC-only/both priority; stock-kernel includes UK_MINOR_DEV254. Legacy leaf HW unqualified.')
    row('OA-T21','unowned unowned-busy','adopt-direct-child')
    row('OA-T22','partial-serial sd-direct-child','adopt-serial-partial-child adopt-sd-model-child','partial-serial obtains outer through actual failed HSL CPU constructor; SD actor is separately synthetic because real sd_init has no such callback.')
    row('OA-T23','foreign-P fal-hppe','skip-owned-child-retirement','Combined foreign-P C-only retirement uses actual FAL/HSL path, not direct child cleanup.')
    row('OA-T24','fal-hppe cleanup-mismatch cleanup-foreign-hook','skip-owned-child-retirement epoch-match-omitted foreign-hook-clean-guard-omitted')
    row('OA-T25','cleanup-mismatch','failed-clean-silent-old-token-write failed-clean-silent-old-token-phy-write','All live displaced-token payloads observed, not only current P/OWNER metadata.')
    row('OA-T26','cleanup-mismatch-retry cleanup-foreign-retry','hsl-epoch-cleared-before-child hsl-flag-cleared-before-child foreign-hook-clean-guard-omitted')
    row('OA-T27','dispatch-ISIS legacy-hook-replacement fault-LEGACY_CLEAN','legacy-new-hook-cleared','Typed legacy callback leaves; not generic chip lifecycle proof.')
    row('OA-T28','epoch-recreate epoch-retire-only','epoch-match-omitted owned-absent-C-check-omitted','r2 challenge addressed by actual r3 epoch API, exactly bridged to r4; no invented identity fields.')
    row('E01','fal-hppe fal-appe fal-mrppe','missing-acquisition-flag owned-output-missing epoch-success-not-incremented')
    row('E02','oom1 oom2 oom3 nocpu epoch-retry-cpu epoch-retry-cfg epoch-retry-port','epoch-failed-constructor-increment owned-output-pregranted own-flag-after-failed-child')
    row('E03','epoch-recreate','epoch-match-omitted')
    row('E04','epoch-retire-only','owned-absent-C-check-omitted')
    row('E05','epoch-recreate','epoch-match-omitted','Distinct-address semantic proof and explicit native DISTINCT_CHILD_ALLOCATIONS check. Actual allocator address-reuse execution UNQUALIFIED, no ABA/reader proof.')
    row('E06','epoch-api','owned-output-null-priority owned-output-busy-priority owned-clean-boundary-priority','Zero epoch check overlaps epoch mismatch in legal nonzero namespaces; no fabricated isolated zero-guard kill is claimed.')
    row('E07','epoch-max','epoch-cap-omitted epoch-output-truncated epoch-reset-on-cleanup','Full64 decimal observations, no int truncation; actual max-1 to max and matching owned cleanup.')
    row('E08','ledger-flag-only ledger-epoch-only cleanup-zero-epoch cleanup-false-flag cleanup-no-outer cleanup-stale-epoch','hsl-epoch-only-init-accepted hsl-flag-only-init-accepted hsl-no-outer-clean-accepted hsl-false-flag-epoch-clean-accepted','Inconsistent tuples are explicit state-boundary actors. Early true-flag/zero-epoch cleanup guard is redundant with hppe_cleanup_owned zero/mismatch rejection: no isolated semantic kill is claimed.')
    row('E09','fal-hppe foreign-P cleanup-mismatch cleanup-foreign-retry','hsl-epoch-cleared-before-child hsl-flag-cleared-before-child hsl-epoch-not-cleared epoch-match-omitted')
    row('E10','fal-dev1 fal-dev2 epoch-retry-cpu epoch-retry-cfg epoch-retry-port','epoch-failed-constructor-increment epoch-reset-on-cleanup','Peers checked fully; actual once state retained. Cross-peer probe checks occupied peer, not successful concurrent construction.')
    source.require(set(rows)=={'OA-T%02d'%i for i in range(1,29)}|{'E%02d'%i for i in range(1,11)},'OBLIGATION_IDS')
    positives=positive_contract();negatives=negative_contract('source')
    for spec in rows.values():
        spec['positive_tuples']=[dict(profile=p,case=c) for p,c in sorted(positives) if c in spec['positive_cases']]
        spec['negative_tuples']=[r for r in negatives if r['name'] in spec['source_controls']]
        source.require({r['case'] for r in spec['positive_tuples']}==set(spec['positive_cases']) and
            {r['name'] for r in spec['negative_tuples']}==set(spec['source_controls']),'OBLIGATION_FIXED_REFERENCES')
        spec['status']='DECLARED_BEFORE_EXECUTION'
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'HPPE-OWNED-ROLLBACK-CANDIDATE-20261031-r1')
    p.add_argument('--candidate',type=Path,default=OLD/'OUTER-ADMISSION-CANDIDATE-20261031-r4');a=p.parse_args()
    source.require(sys.flags.optimize>0,'python-O-required')
    out=a.output.resolve();source.require(out.parent==AUDIT and out.name.startswith('OUTER-TEST-') and not out.exists(),'fresh-output');out.mkdir(parents=True)
    result=dict(status='INCOMPLETE',qualification='SERIAL_OUTER_HOST_MODEL_ONLY',positives=[],source_negatives=[],old_witnesses=[],native_model_controls=[],python_optimize=sys.flags.optimize,
        open=['actual allocator address reuse and target ABA/readers unqualified; E05 uses distinct-address semantic proof','reduced cfg/API/OS/legacy/VLAN/adapter/SD/UK/lock leaves, not resource or ABI qualification',
              'shared dev_init/UK ownership, full root/HW/target/concurrency/RCU/ABA/LSan unqualified'])
    generated={};expected_files={}
    try:
        tree,inputs=source.prepare(a.base.resolve(),a.candidate.resolve(),out);record(out/'INPUTS.json',inputs,generated)
        new=source.extract(tree);domain=schema(tree,new);matrix=cases();record(out/'SCHEMA.json',domain,generated);record(out/'MATRIX.json',matrix,generated)
        planned_positive=[dict(profile=pr,case=c['name']) for c in matrix for pr in c['profiles']];positive_inventory(planned_positive)
        old_api=source.baseline_api(a.base/'prepared')
        text=source.render(new,old_api,(SUPPORT/'fixture.c').read_text().replace('/* @CASES@ */',header(matrix,domain)))
        record(out/'EXTRACTED.json',{'actual':new['records'],'complete_bodies':list(new['bodies']),
            'baseline_api':{'path':'src/hsl/hsl_api.c','sha256':source.digest(old_api.encode()),'alias':'old_hsl_api_init','complete_body':True},
            'transformations':'definition-only aliases for actual HSL core/HPPE init/cleanup behind explicit OS context/probe wrappers; no function body pruning. Exact original request/acquired preprocessor conditions retained.',
            'models':'Reduced cfg/API/VLAN/adpt structs; OS logical quarantine. SD/UK/API-lock/VLAN/adpt/legacy leaves model parameters/first-error/reentry only; not actual HW/UK partial acquisition.'},generated)
        result['inventory_controls']=inventory_controls();record(out/'CONTRACTS.json',{'positive':planned_positive,'source':negative_contract('source'),'old':negative_contract('old')},generated)
        obligations=obligation_map();record(out/'OBLIGATION-COVERAGE-PLAN.json',obligations,generated)
        result['source_admission_controls']=source_visibility_controls()
        planned={pr:variants(new,pr) for pr in PROFILES}
        paths={r['symbol']:r['path'] for r in new['records'] if r['symbol'] in new['bodies']}
        for rows in planned.values():
            for v in rows:source_visibility(paths[v['symbol']],v['after'])
        negative_inventory([dict(v,profile=pr) for pr,vs in planned.items() for v in vs],'source')
        record(out/'NEGATIVE-PLAN.json',{pr:[{k:v[k] for k in FIELDS if k!='profile'} for v in vs] for pr,vs in planned.items()},generated)
        result['negative_pre_execution_gate']='EXACT_FIXED_INDEPENDENT_OBLIGATIONS'
        cc=shutil.which(a.cc);source.require(cc is not None,'compiler-path');cc=str(Path(cc).resolve());result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function'];env=dict(os.environ);env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        version=invoke([cc,'--version'],out/'compiler-version',env,generated);source.require(version.returncode==0 and version.stderr==b'','compiler-version')
        if a.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        result['output_controls']=output_controls();result['tail_controls']=tail_controls(out)
        byname={c['name']:(i,c) for i,c in enumerate(matrix)}
        def execute(binary,c,ix,pr,folder,name,oldapi=0):
            returns,expected=oracle(c,pr,domain);ep=folder/(name+'.expected');ep.write_bytes(expected);expected_files[str(ep)]=source.digest(expected);generated[str(ep)]=source.digest(expected)
            run=invoke([str(binary),str(ix),','.join(map(str,returns)),str(ep),str(oldapi)],folder/name,env,generated);return run,expected
        for pr,profile in PROFILES.items():
            folder=out/pr;folder.mkdir();pf=profile.get('features',COMMON)+['-D'+n for n in profile['chips']]+profile['flags']
            result.setdefault('profile_flags',{})[pr]=flags+pf
            binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for ix,c in enumerate(matrix):
                if pr not in c['profiles']:continue
                run,expected=execute(binary,c,ix,pr,folder,c['name']);positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append(dict(profile=pr,case=c['name'],stdout_sha256=source.digest(run.stdout)))
            if not a.positives_only:
                for v in planned[pr]:
                    prefix=v['name']+'-'+v['case'];mutated=once(text,v['before'],v['after']);binary_mut=compile_c(cc,flags+pf,mutated,folder/prefix,env,generated)
                    ix,c=byname[v['case']];run,_=execute(binary_mut,c,ix,pr,folder,prefix+'-run');negative(run.returncode,run.stdout,run.stderr,v['marker'])
                    result['source_negatives'].append({k:v[k] for k in FIELDS if k!='profile'}|dict(profile=pr,execution='CLEAN_COMPILE_EXACT86',source_sha256=source.digest(mutated.encode())))
                for v in negative_contract('old'):
                    if v['profile']!=pr:continue
                    ix,c=byname[v['case']];run,_=execute(binary,c,ix,pr,folder,v['name']+'-run',1);negative(run.returncode,run.stdout,run.stderr,v['marker'])
                    result['old_witnesses'].append(dict(v,execution='CLEAN_COMPILE_EXACT86',source_sha256=source.digest(text.encode())))
            record(out/'RESULTS.json',result)
        positive_inventory(result['positives'])
        if not a.positives_only:
            negative_inventory(result['source_negatives'],'source',True);negative_inventory(result['old_witnesses'],'old',True)
            result['negative_completion_gate']='EXACT_UNIQUE_FIXED_EXECUTED_OBLIGATIONS'
            observed_positive={(r['profile'],r['case']) for r in result['positives']}
            observed_negative={tuple(r[k] for k in FIELDS) for r in result['source_negatives']}
            for spec in obligations.values():
                source.require({(r['profile'],r['case']) for r in spec['positive_tuples']}<=observed_positive and
                    {tuple(r[k] for k in FIELDS) for r in spec['negative_tuples']}<=observed_negative,'OBLIGATION_COMPLETION')
                spec['status']='EXECUTED_FIXED_TUPLES_WITH_DECLARED_LIMITS'
            record(out/'OBLIGATION-COVERAGE-RESULT.json',obligations,generated)
            result['obligation_coverage']={'count':38,'path':str(out/'OBLIGATION-COVERAGE-RESULT.json'),
                'scope':'28 OA +10 epoch fixed cases/controls executed; explicit redundant subguards and reuse/HW/ABI limits are not separately credited mutants'}
        result['end_input_stability']=source.stable(inputs);expected_tail(out,expected_files);generated_tail(out,generated)
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler')
        result['expected_tail']='EXACT_MEMORY_DERIVED_ORACLES_AND_PATHS';result['generated_tail']='EXACT_INVENTORY_ROOT_RESULT_ONLY_EXCEPTION_FRESH28_SEPARATE';result['generated_files']=generated
        result['positive_count']=len(result['positives']);result['source_negative_count']=len(result['source_negatives']);result['old_witness_count']=len(result['old_witnesses'])
        result['status']='DEV_ONLY' if a.positives_only else 'HOST_MODEL_ONLY';result['outcome']='NOT_FINAL' if a.positives_only else 'PASSED_WITHIN_OUTER_SERIAL_HOST_MODEL'
    except Exception as ex:result['status']='FAILED';result['error']=str(ex);raise
    finally:record(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_count','source_negative_count','old_witness_count')}))


if __name__=='__main__':main()
