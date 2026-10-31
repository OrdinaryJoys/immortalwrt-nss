#!/usr/bin/env python3
"""HPPE26 fresh isolated host model; no target/root/ownership qualification."""
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
SUPPORT=Path(__file__).resolve().parent/'ssdk-hppe-single-evaluation'
sys.path.insert(0,str(SUPPORT))
import source
from mutations import once,variants
AUDIT=Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-hppe-single-eval')
OLD=AUDIT.parents[1]/'20261030/ssdk-dp-retirement'
PROFILES={'neither':[],'kernel':['-DKERNEL_MODULE'],'user':['-DUSER_MODE'],'both':['-DKERNEL_MODULE','-DUSER_MODE']}
SITES=['DEV','RESET','PALLOC','PROP','CLEAN','SET0','SET1','SET2','SET3','SET4']
ALL_PROFILES=('neither','kernel','user','both')
ACTIVE_INIT_PROFILES=('neither','kernel','user')
EVAL_CLASS='single038 call site restored to repeated evaluation; synthetic helper failures explicitly artificial'
STATE_CLASS='directed actual source state/callback mutant'
OLD_CLASS='safe baseline host witness; natural allocator/dev error or explicitly synthetic helper schedule. NOT target fault or owner fix.'
# Independent obligations: never derive this manifest from mutations.variants or observed results.
EVAL_CONTRACT=(
    ('DEV','hppe_init',ALL_PROFILES),('RESET','hppe_init',ACTIVE_INIT_PROFILES),
    ('PALLOC','hppe_init',ACTIVE_INIT_PROFILES),('PROP','hppe_init',ACTIVE_INIT_PROFILES),
    ('SET0','hppe_portproperty_init',ALL_PROFILES),('SET1','hppe_portproperty_init',ALL_PROFILES),
    ('SET2','hppe_portproperty_init',ALL_PROFILES),('SET3','hppe_portproperty_init',ALL_PROFILES),
    ('SET4','hppe_portproperty_init',ALL_PROFILES),('CLEAN','hppe_cleanup',ALL_PROFILES))
STATE_CONTRACT=(
    ('dev-union-to-xor','hppe_dev_init','dev0-cpu-zero','EXACT_MODEL_TRACE',STATE_CLASS,ALL_PROFILES),
    ('dev-no-lowest-cpu-break','hppe_dev_init','dev0-cpu-lowest','FIRST_RETURN',STATE_CLASS,ALL_PROFILES),
    ('setter-wrong-row','hsl_port_prop_set','helpers-retain-state','EXACT_MODEL_TRACE',STATE_CLASS,ALL_PROFILES),
    ('api-wrong-sd-token','hppe_init','dev0-callback','API_FIELD_IDENTITY',STATE_CLASS,ACTIVE_INIT_PROFILES),
    ('unapproved-dev-failure-free','hppe_init','dev0-cpu-none','EXACT_MODEL_TRACE',
     'owner-boundary preservation control;038 deliberately adds NO rollback, not an endorsement of owner gap',ALL_PROFILES),
    ('cleanup-frees-cfg-on-dependency-error','hppe_cleanup','synthetic-CLEAN-transient','EXACT_MODEL_TRACE',
     'dependency first-error/owner preservation control, not lifecycle closure',ALL_PROFILES),
    ('reset-silently-frees-old-port','hsl_port_prop_init','dev0-repeat','EXACT_MODEL_TRACE',
     'preserve unchanged reset-loss OPEN boundary; not a proposed owner repair',ACTIVE_INIT_PROFILES))
OLD_CONTRACT=(
    ('old-witness-dev0-cpu-none','dev0-cpu-none','SINGLE_EVALUATION',ALL_PROFILES),
    ('old-witness-synthetic-DEV-different','synthetic-DEV-different','FIRST_RETURN',ALL_PROFILES),
    ('old-witness-synthetic-SET0-transient','synthetic-SET0-transient','FIRST_RETURN',ALL_PROFILES),
    ('old-witness-synthetic-CLEAN-different','synthetic-CLEAN-different','FIRST_RETURN',ALL_PROFILES),
    ('old-witness-dev0-port-oom-transient','dev0-port-oom-transient','FIRST_RETURN',ACTIVE_INIT_PROFILES),
    ('old-witness-dev0-port-oom-persistent','dev0-port-oom-persistent','SINGLE_EVALUATION',ACTIVE_INIT_PROFILES))
TUPLE_FIELDS=('profile','name','symbol','case','marker','classification')


def contract_rows(kind):
    rows=[]
    if kind=='source':
        for site,symbol,profiles in EVAL_CONTRACT:
            for profile in profiles:
                for mode,marker in (('transient','FIRST_RETURN'),('different','FIRST_RETURN'),('persistent','SINGLE_EVALUATION')):
                    rows.append(dict(profile=profile,name='double-evaluate-'+site,symbol=symbol,
                                     case='synthetic-'+site+'-'+mode,marker=marker,classification=EVAL_CLASS))
        for name,symbol,case,marker,classification,profiles in STATE_CONTRACT:
            for profile in profiles:rows.append(dict(profile=profile,name=name,symbol=symbol,case=case,marker=marker,classification=classification))
    elif kind=='old':
        for name,case,marker,profiles in OLD_CONTRACT:
            for profile in profiles:rows.append(dict(profile=profile,name=name,symbol='complete baseline init/cleanup/property with same actual helpers',
                                                    case=case,marker=marker,classification=OLD_CLASS))
    elif kind=='all':return contract_rows('source')+contract_rows('old')
    else:raise RuntimeError('NEGATIVE_INVENTORY_KIND')
    return rows


def inventory_gate(rows,kind,completed=False):
    try:keys=[tuple(row[k] for k in TUPLE_FIELDS) for row in rows]
    except (KeyError,TypeError) as e:raise RuntimeError('NEGATIVE_INVENTORY') from e
    source.require(len(keys)==len(set(keys)),'NEGATIVE_DUPLICATE')
    expected={tuple(row[k] for k in TUPLE_FIELDS) for row in contract_rows(kind)}
    source.require(set(keys)==expected,'NEGATIVE_INVENTORY')
    if completed:source.require(all(row.get('execution')=='CLEAN_COMPILE_AND_EXACT86' and
                                   re.fullmatch(r'[0-9a-f]{64}',row.get('source_sha256','')) for row in rows),'NEGATIVE_EXECUTION')


def inventory_controls():
    original=contract_rows('source');old=contract_rows('old');valid=0;rejects=[]
    inventory_gate(original,'source');inventory_gate(old,'old');valid+=2
    completed=[dict(r,execution='CLEAN_COMPILE_AND_EXACT86',source_sha256='a'*64) for r in original]
    inventory_gate(completed,'source',True);valid+=1
    def reject(name,rows,marker,done=False):
        try:inventory_gate(rows,'source',done)
        except RuntimeError as e:source.require(str(e)==marker,'inventory-control-specific-marker')
        else:raise RuntimeError('inventory-control-accepted:'+name)
        rejects.append(name)
    reject('empty',[],'NEGATIVE_INVENTORY');reject('missing',original[1:],'NEGATIVE_INVENTORY')
    reject('duplicate',original+[dict(original[0])],'NEGATIVE_DUPLICATE')
    for field,value in [('profile','wrong-profile'),('name','wrong-name'),('symbol','wrong-symbol'),
                        ('case','wrong-case'),('marker','WRONG_MARKER'),('classification','wrong-classification')]:
        bad=[dict(r) for r in original];bad[0][field]=value;reject('wrong-'+field,bad,'NEGATIVE_INVENTORY')
    extra=dict(original[0],name='unexpected-extra');reject('extra',original+[extra],'NEGATIVE_INVENTORY')
    reject('old-ledger-as-source',old,'NEGATIVE_INVENTORY')
    bad=[dict(r) for r in completed];bad[0]['execution']='NOT_EXECUTED';reject('unexecuted',bad,'NEGATIVE_EXECUTION',True)
    return {'valid':valid,'rejects':rejects,'classification':'pure inventory/completion gate pollution controls; NOT production failures/native mutant credit'}


def old_probes(profile):
    # Executable plan kept separate from the independent OLD_CONTRACT obligations.
    rows=[('dev0-cpu-none','SINGLE_EVALUATION'),('synthetic-DEV-different','FIRST_RETURN'),
          ('synthetic-SET0-transient','FIRST_RETURN'),('synthetic-CLEAN-different','FIRST_RETURN')]
    if profile!='both':rows += [('dev0-port-oom-transient','FIRST_RETURN'),('dev0-port-oom-persistent','SINGLE_EVALUATION')]
    return rows


def negative_plans(new,old,text):
    planned={};source_rows=[];old_rows=[]
    for profile in PROFILES:
        planned[profile]=variants(new,old,profile)
        source.require(len({v['name'] for v in planned[profile]})==len(planned[profile]),'NEGATIVE_VARIANT_DUPLICATE')
        for v in planned[profile]:
            source.require(v['before']!=v['after'] and text.count(v['before'])==1,'NEGATIVE_SOURCE_TARGET')
            for name,marker in v['probes']:
                source_rows.append(dict(profile=profile,name=v['name'],symbol=v['symbol'],case=name,marker=marker,classification=v['classification']))
        for name,marker in old_probes(profile):
            old_rows.append(dict(profile=profile,name='old-witness-'+name,case=name,marker=marker,
                symbol='complete baseline init/cleanup/property with same actual helpers',classification=OLD_CLASS))
    inventory_gate(source_rows,'source');inventory_gate(old_rows,'old');inventory_gate(source_rows+old_rows,'all')
    return planned,{'source':source_rows,'old':old_rows,'status':'EXACT_INDEPENDENT_TUPLE_INVENTORY_BEFORE_EXECUTION'}


def record(path,data,generated=None):
    raw=(json.dumps(data,indent=2)+'\n').encode();path.write_bytes(raw)
    if generated is not None:generated[str(path)]=source.digest(raw)


def expected_tail(root,expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')),'output-symlink')
    source.require({str(p) for p in root.rglob('*.expected') if p.is_file()}==set(expected),'expected-inventory')
    for n,sha in expected.items():source.require(source.identity(n)==sha,'expected-memory-hash')


def generated_tail(root,generated):
    actual={str(p) for p in root.rglob('*') if p.is_file() and p!=root/'RESULTS.json' and not p.is_relative_to(root/'fresh26')}
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


def negative(code,out,err,marker):source.require(code==86 and out==b'' and err==f'SSDK_HPPE {marker}\n'.encode(),'negative-exact-marker')


def output_controls():
    positive(0,b'x',b'',b'x');negative(86,b'',b'SSDK_HPPE X\n','X');rejects=0
    for row in [(1,b'x',b'',b'x'),(0,b'xx',b'',b'x'),(0,b'x',b'warning',b'x')]:
        try:positive(*row)
        except RuntimeError:rejects+=1
        else:raise RuntimeError('positive-gate-control')
    for row in [(1,b'',b'SSDK_HPPE X\n'),(-6,b'',b'SSDK_HPPE X\n'),(None,b'',b'SSDK_HPPE X\n'),
                (86,b'noise',b'SSDK_HPPE X\n'),(86,b'',b'SSDK_HPPE Y\n'),(86,b'',b'SSDK_HPPE X\nSSDK_HPPE X\n'),
                (86,b'',b'SSDK_HPPE X\nERROR: AddressSanitizer')]:
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


def case(name,**changes):
    c=dict(name=name,flow='init',dev=0,cpu=1,lan=0x106,wan=0x204,inner=0x102,
           global_bmp=0x8002,global_inner=0x4002,synth=-1,first='SW_READ_ERROR',second='SW_OK',
           oom_kind=0,oom_mode=0,borrow=0,attempts=1,clean=0,old_compare=False)
    c.update(changes);return c


def cases():
    rows=[]
    for d in range(3):
        for cpu,label in [(1,'zero'),(1<<15,'fifteen'),(10,'lowest'),(0,'none'),(1<<31,'high-only'),(3,'multi-zero')]:
            rows.append(case(f'dev{d}-cpu-{label}',dev=d,cpu=cpu,old_compare=label not in ('none','high-only')))
        rows += [case(f'dev{d}-callback',dev=d,clean=1,old_compare=True),
                 case(f'dev{d}-direct',dev=d,clean=2,old_compare=True),
                 case(f'dev{d}-helpers',dev=d,flow='helpers',clean=3,old_compare=True),
                 case(f'dev{d}-repeat',dev=d,attempts=2,old_compare=True)]
        for mask in (1,2,3):rows.append(case(f'dev{d}-borrow{mask}',dev=d,borrow=mask,old_compare=True))
        for kind,name in [(1,'cfg'),(2,'port')]:
            for mode,label in [(1,'transient'),(2,'persistent')]:
                rows.append(case(f'dev{d}-{name}-oom-{label}',dev=d,oom_kind=kind,oom_mode=mode))
    for dev in (3,4294967295):rows.append(case(f'invalid-{dev}',dev=dev))
    rows += [case('cfg-explicit-retry',oom_kind=1,oom_mode=1,attempts=2),
             case('port-explicit-retry',oom_kind=2,oom_mode=1,attempts=2),
             case('sparse',lan=0x8000,wan=2,inner=0x8002,global_bmp=0x104,global_inner=0x202,cpu=8,old_compare=True),
             case('high-global-bits',global_bmp=0x80000000,global_inner=0x80000000,old_compare=True),
             case('helpers-retain-state',flow='helpers',old_compare=True)]
    for site in range(10):
        for label,second in [('transient','SW_OK'),('different','SW_WRITE_ERROR'),('persistent','SW_READ_ERROR')]:
            changes=dict(synth=site,second=second)
            if site==4:changes['clean']=2
            if site>=5:changes['flow']='helpers'
            rows.append(case(f'synthetic-{SITES[site]}-{label}',**changes))
    for t in range(5):rows.append(case(f'init-set{t}-error',synth=5+t))
    source.require(len({c['name'] for c in rows})==len(rows),'unique-cases')
    return rows


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
    for body,name in re.findall(r'typedef\s+struct\s*\{([^}]*)\}\s*(\w+)\s*;',text):
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


def header(matrix,domain):
    def value(v):return json.dumps(v) if isinstance(v,str) else str(int(v))+'u' if int(v)>2147483647 else str(int(v))
    fields=['name','flow','dev','cpu','lan','wan','inner','global_bmp','global_inner','synth','first','second','oom_kind','oom_mode','borrow','attempts','clean']
    lines=[f'_Static_assert(sizeof({name})=={size},"host layout {name}");' for name,size in domain['sizes'].items()]
    for name,val in domain['properties'].items():lines.append(f'_Static_assert({name}=={val},"actual property domain");')
    lines.append('static const struct input inputs[]={')
    for c in matrix:
        d=dict(c);d['first']=domain['errors'][d['first']];d['second']=domain['errors'][d['second']]
        lines.append('{'+','.join('.'+k+'='+value(d[k]) for k in fields)+'},')
    return '\n'.join(lines+['};\n'])


def oracle(c,profile,domain):
    err,sz=domain['errors'],domain['sizes'];events=[];add=events.append;counts=[0]*10;returns=[]
    cfgs={};ports={};meta={};api={};owners=[];serial=0;alloc=[0,0,0]
    defaultcfg=[0,0,0,0,0,0xbadc0de];newcfg=[1,c['cpu'],c['lan'],c['wan'],c['inner'],0xc0ffee]
    for d in range(3):
        mask=c['borrow'] if d==c['dev'] else 3
        cfgs[d]=[101+d*10,list(defaultcfg)] if mask&1 else None
        ports[d]=[102+d*10,0x88,[1<<i for i in range(5)],[1000+i for i in range(16)]] if mask&2 else None
        meta[d]=[d,7,9,11,13,17,0,0,68];api[d]=[0]*11
    def allocate(kind):
        nonlocal serial
        serial+=1;alloc[kind]+=1
        ok=not(c['oom_kind']==kind and (c['oom_mode']==2 or alloc[kind]==1))
        add(f'ALLOC {serial} {kind} {sz["ssdk_init_cfg" if kind==1 else "port_info_t"]} {int(ok)}\n')
        if ok:owners.append([serial,kind,1]);return serial
        return 0
    def free(ident):
        row=next(o for o in owners if o[0]==ident);source.require(row[2]==1,'oracle-free-once');row[2]=0;add(f'FREE {ident}\n')
    def call(site,body,p=0,t=0):
        counts[site]+=1;add(f'CALL {SITES[site]} {c["dev"]} {p} {t} {counts[site]}\n')
        fault=err[c['first'] if counts[site]==1 else c['second']] if c['synth']==site else 0
        if fault:add(f'SYNTH {SITES[site]} {fault}\n');ret=fault
        else:ret=body()
        add(f'DONE {SITES[site]} {ret}\n');return ret
    def dev():
        if c['dev']>=3:return err['SW_NOT_INITIALIZED']
        v=meta[c['dev']];front=bin((c['lan']|c['wan'])&65535).count('1');v[3]=front
        cpus=c['cpu']&65535
        if not cpus:return err['SW_BAD_VALUE']
        cpu=(cpus&-cpus).bit_length()-1;nr=front+bin(c['inner']&65535).count('1')+1
        meta[c['dev']]=[v[0],cpu,nr,front,nr,4096,1,1,c['wan']];return 0
    def reset():ports[c['dev']]=None;return 0
    def palloc():
        ident=allocate(2)
        if not ident:return err['SW_OUT_OF_MEM']
        add(f'ZERO {ident} {sz["port_info_t"]}\n');ports[c['dev']]=[ident,0,[0]*5,[0]*16];return 0
    def prop():
        d=c['dev'];add(f'GLOBAL_BMP {c["global_bmp"]}\n');add(f'GLOBAL_INNER {c["global_inner"]}\n');cpu=meta[d][1]
        for p in sorted({cpu}|{i for i in range(16) if ((c['global_bmp']|c['global_inner'])>>i)&1}):
            if p>=16:continue
            add(f'MAP {d} {p}\n');ports[d][1]|=1<<p
            conditions=[bool(c['global_bmp']&(1<<p)),True,p!=cpu,bool(c['global_inner']&(1<<p)),p==cpu]
            for t,active in enumerate(conditions):
                if not active:continue
                def setter(t=t,p=p):ports[d][2][t]|=1<<p;return 0
                ret=call(5+t,setter,p,t)
                if ret:return ret
        return 0
    def clean_port():
        if ports[c['dev']]:free(ports[c['dev']][0]);ports[c['dev']]=None
        return 0
    def cleanup():
        if cfgs[c['dev']]:
            ret=call(4,clean_port)
            if ret:return ret
            free(cfgs[c['dev']][0]);cfgs[c['dev']]=None
        return 0
    ret=0
    for attempt in range(c['attempts']):
        add(f'ATTEMPT {attempt}\n');d=c['dev']
        if c['flow']=='init':
            if d>=3:ret=err['SW_OUT_OF_RANGE']
            else:
                if not cfgs[d]:
                    ident=allocate(1)
                    if ident:cfgs[d]=[ident,[0]*6]
                if not cfgs[d]:ret=err['SW_OUT_OF_MEM']
                else:
                    cfgs[d][1]=list(newcfg);add(f'COPY {cfgs[d][0]} {sz["ssdk_init_cfg"]}\n');ret=call(0,dev)
                    if not ret and profile!='both':
                        ret=call(1,reset)
                        if not ret:ret=call(2,palloc)
                        if not ret:ret=call(3,prop)
                        if not ret:api[d]=[1]*11
        else:
            ret=call(0,dev)
            if not ret:ret=call(1,reset)
            if not ret:ret=call(2,palloc)
            if not ret:ret=call(3,prop)
        returns.append(ret);add(f'RETURN {ret}\n')
    if c['clean'] and not ret:
        if c['clean']==1:
            if api[c['dev']][0]:add('CALLBACK\n');ret=cleanup();returns.append(ret);add(f'RETURN {ret}\n')
            else:add('CALLBACK_ABSENT_OPEN_CFG\n')
        else:
            add('DIRECT_PORT_HELPER\n' if c['clean']==3 else 'DIRECT_HPPE_HELPER\n')
            ret=call(4,clean_port) if c['clean']==3 else cleanup();returns.append(ret);add(f'RETURN {ret}\n')
    for d in range(3):
        add('DEVSTATE %u %s\n'%(d,' '.join(map(str,meta[d]))))
        add(f'SLOTS {d} {cfgs[d][0] if cfgs[d] else 0} {ports[d][0] if ports[d] else 0}\n')
        if cfgs[d]:add('CFG %u %s\n'%(d,' '.join(map(str,cfgs[d][1]))))
        if ports[d]:add('PORT %u %u %s\n'%(d,ports[d][1],' '.join(map(str,ports[d][2]+ports[d][3]))))
        if d==c['dev']:add('API %u %s\n'%(d,' '.join(map(str,api[d]))))
    for d in range(3):
        mask=c['borrow'] if d==c['dev'] else 3
        if mask&1:add(f'FOREIGN {101+d*10} 1 1 {int(cfgs[d] is not None and cfgs[d][0]==101+d*10)}\n')
        if mask&2:add(f'FOREIGN {102+d*10} 2 1 {int(ports[d] is not None and ports[d][0]==102+d*10)}\n')
    for ident,kind,live in owners:
        d=c['dev'];reachable=int(d<3 and ((cfgs[d] and cfgs[d][0]==ident) or (ports[d] and ports[d][0]==ident) or False))
        add(f'OWNER {ident} {kind} {live} {reachable}\n')
    add('OPEN_FOREIGN_CFG_COPY_AND_DISPLACED_PORTS\n');add('END MODEL_ONLY_NO_FAILURE_UNWIND\n')
    return returns,counts,''.join(events).encode()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'VLAN-INIT-ROLLBACK-CANDIDATE-20261031-r1')
    p.add_argument('--candidate',type=Path,default=OLD/'HPPE-SINGLE-EVAL-CANDIDATE-20261031-r1');args=p.parse_args()
    out=args.output.resolve();source.require(out.parent==AUDIT and out.name.startswith('HPPE-TEST-') and not out.exists(),'fresh-output');out.mkdir(parents=True)
    result={'status':'INCOMPLETE','qualification':'SINGLE_EVALUATION_HOST_MODEL_ONLY','positives':[],'baseline_success':[],'negatives':[],
            'source_negatives':[],'old_witnesses':[],'native_model_controls':[],
            'python_optimize':sys.flags.optimize,'open':['partial owners/borrowed/repeated port reset','no target ABI/root/HW/concurrency','LSan',
            'cfg/API reduced; logical OS quarantine not UAF proof']};generated={}
    try:
        tree,inputs=source.prepare(args.base.resolve(),args.candidate.resolve(),out);record(out/'INPUTS.json',inputs,generated)
        new=source.extract(tree);domain=schema(tree,new);matrix=cases();record(out/'SCHEMA.json',domain,generated);record(out/'MATRIX.json',matrix,generated)
        text,new,old=source.render(tree,args.base/'prepared',(SUPPORT/'fixture.c').read_text().replace('/* @CASES@ */',header(matrix,domain)))
        record(out/'EXTRACTED.json',{'candidate':new['records'],'baseline':old['records'],'complete_bodies':list(new['bodies']),
            'renaming':'HSL helper function definitions name-only renamed real_* behind explicit call/fault wrappers; all four actual HPPE bodies retained; baseline init/cleanup/property name-only aliases',
            'models':'ssdk_init_cfg and hsl_api_t reduced; bitmap sources explicit and differ from cfg; SD symbols identity-only, not invoked/ABI. Natural allocator vs synthetic faults separate.'},generated)
        result['inventory_controls']=inventory_controls()
        record(out/'NEGATIVE-CONTRACT.json',{'source':contract_rows('source'),'old':contract_rows('old'),
            'basis':'independent literal obligations in runner; not derived from variants or results; pure inventory controls are NOT native/source credits'},generated)
        planned={}
        if not args.positives_only:
            planned,plan_receipt=negative_plans(new,old,text);record(out/'NEGATIVE-PLAN.json',plan_receipt,generated)
            result['negative_pre_execution_gate']=plan_receipt['status']
        cc=shutil.which(args.cc);source.require(cc is not None,'compiler-path');cc=str(Path(cc).resolve());result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function'];env=dict(os.environ)
        env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        version=invoke([cc,'--version'],out/'compiler-version',env,generated);source.require(version.returncode==0 and version.stderr==b'','compiler-version')
        if args.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        result['output_controls']=output_controls();result['tail_controls']=tail_controls(out)
        byname={c['name']:(i,c) for i,c in enumerate(matrix)};expected_files={}
        def execute(binary,c,i,profile,folder,name,version=0):
            returns,counts,expected=oracle(c,profile,domain);ep=folder/(name+'.expected');ep.write_bytes(expected)
            generated[str(ep)]=source.digest(expected);expected_files[str(ep)]=source.digest(expected)
            run=invoke([str(binary),str(i),','.join(map(str,returns)),','.join(map(str,counts)),str(ep),str(version)],folder/name,env,generated)
            return run,expected
        for profile,pf in PROFILES.items():
            folder=out/profile;folder.mkdir();binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for i,c in enumerate(matrix):
                run,expected=execute(binary,c,i,profile,folder,c['name']);positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append({'profile':profile,'case':c['name'],'stdout_sha256':source.digest(run.stdout),
                    'fault_class':'guarded-out schedule: both skips port/property/API' if profile=='both' and c['flow']=='init' and
                       (c['oom_kind']==2 or c['synth'] in (1,2,3,5,6,7,8,9)) else
                       'explicitly synthetic helper schedule' if c['synth']>=0 else 'host-injected OOM at naturally fallible allocator' if c['oom_kind'] else 'actual helper success/admission/owner-boundary'})
                if c['old_compare']:
                    run,expected=execute(binary,c,i,profile,folder,c['name']+'-baseline',1);positive(run.returncode,run.stdout,run.stderr,expected)
                    result['baseline_success'].append({'profile':profile,'case':c['name'],'stdout_sha256':source.digest(run.stdout)})
            if not args.positives_only:
                for v in planned[profile]:
                    mutated=once(text,v['before'],v['after']);mb=compile_c(cc,flags+pf,mutated,folder/v['name'],env,generated)
                    for case_name,marker in v['probes']:
                        i,c=byname[case_name];run,_=execute(mb,c,i,profile,folder,v['name']+'-'+case_name+'-run')
                        negative(run.returncode,run.stdout,run.stderr,marker)
                        entry={k:v[k] for k in ('name','symbol','classification')}|{'profile':profile,'case':case_name,'marker':marker,
                            'source_sha256':source.digest(mutated.encode()),'execution':'CLEAN_COMPILE_AND_EXACT86'}
                        result['source_negatives'].append(entry);result['negatives'].append(entry)
                for name,marker in old_probes(profile):
                    i,c=byname[name];run,_=execute(binary,c,i,profile,folder,'old-witness-'+name,1)
                    negative(run.returncode,run.stdout,run.stderr,marker)
                    entry={'profile':profile,'name':'old-witness-'+name,'case':name,'marker':marker,
                        'symbol':'complete baseline init/cleanup/property with same actual helpers',
                        'classification':OLD_CLASS,'source_sha256':source.digest(text.encode()),'execution':'CLEAN_COMPILE_AND_EXACT86'}
                    result['old_witnesses'].append(entry);result['negatives'].append(entry)
            record(out/'RESULTS.json',result)
        if not args.positives_only:
            inventory_gate(result['source_negatives'],'source',True);inventory_gate(result['old_witnesses'],'old',True)
            inventory_gate(result['negatives'],'all',True)
            result['negative_completion_gate']='EXACT_UNIQUE_INDEPENDENT_SOURCE_AND_OLD_TUPLES_ALL_EXECUTED_CLEAN'
        result['end_input_stability']=source.stable(inputs);expected_tail(out,expected_files);generated_tail(out,generated)
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler');result['expected_tail']='EXACT_PATHS_MEMORY_ORACLE_DIGESTS'
        result['generated_tail']='EXACT_FILES_ROOT_RESULT_EXCEPTION_FRESH692_SEPARATE';result['generated_files']=generated
        result['positive_count']=len(result['positives']);result['baseline_success_count']=len(result['baseline_success']);result['negative_count']=len(result['negatives'])
        result['status']='DEV_CHECKPOINT_POSITIVES_ONLY' if args.positives_only else 'HOST_MODEL_ONLY'
        result['outcome']='NOT_FINAL_QUALIFICATION' if args.positives_only else 'PASSED_WITHIN_SINGLE_EVALUATION_MODEL'
    except Exception as e:result['status']='FAILED';result['error']=str(e);raise
    finally:record(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_count','baseline_success_count','negative_count')}))


if __name__=='__main__':main()
