#!/usr/bin/env python3
"""VLAN25 fresh host constructor model. No target/root/concurrent qualification."""
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
SUPPORT=Path(__file__).resolve().parent/'ssdk-vlan-init-rollback'
sys.path.insert(0,str(SUPPORT))
import source
from mutations import once, variants

AUDIT=Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-vlan-init-rollback')
OLD=AUDIT.parents[1]/'20261030/ssdk-dp-retirement'
PROFILES={'linux-zero':[], 'generic-poison-stress':['-DSTRESS_POISON']}


def record(path,data,generated=None):
    raw=(json.dumps(data,indent=2)+'\n').encode();path.write_bytes(raw)
    if generated is not None:generated[str(path)]=source.digest(raw)


def expected_tail(root,expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')),'output-symlink')
    source.require({str(p) for p in root.rglob('*.expected') if p.is_file()}==set(expected),'expected-inventory')
    for n,sha in expected.items():source.require(source.identity(n)==sha,'expected-memory-hash')


def generated_tail(root,generated):
    actual={str(p) for p in root.rglob('*') if p.is_file() and p!=root/'RESULTS.json' and not p.is_relative_to(root/'fresh25')}
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


def case(name,**changes):
    c=dict(name=name,flow='vlan',dev=0,nr=257,min=0,flags=3,hw=0,missing=0,borrow=0,rounds=1,steps=1,faults=[0,0,0])
    c.update(changes);return c


def cases():
    rows=[]
    for dev in range(3):
        for n in (0,1,255,256,257,4096,4097,65535,65536,65537,4294967295):
            rows.append(case(f'dev{dev}-nr{n}',dev=dev,nr=n))
            if 1<=n<=4096:
                for f in range(1,5):rows.append(case(f'dev{dev}-nr{n}-fault{f}',dev=dev,nr=n,faults=[f,0,0]))
        for f in range(1,5):rows.append(case(f'dev{dev}-retry{f}',dev=dev,rounds=2,steps=3,faults=[f,0,0]))
        rows += [case(f'dev{dev}-repeat',dev=dev,steps=2,rounds=2),case(f'dev{dev}-missing',dev=dev,missing=1)]
        for mask in range(1,8):
            for n in (1,257):rows.append(case(f'dev{dev}-borrow{mask}-nr{n}',dev=dev,nr=n,borrow=mask,rounds=2))
            rows.append(case(f'dev{dev}-hw-borrow{mask}',dev=dev,nr=0,hw=1,borrow=mask))
        for n in (0,4097,4294967295):rows.append(case(f'dev{dev}-hw-nr{n}',dev=dev,nr=n,hw=1))
        rows.append(case(f'dev{dev}-invalid-count-before-borrow',dev=dev,nr=0,borrow=7))
    for dev in (3,4294967295):rows.append(case(f'invalid-dev{dev}',dev=dev))
    for n in (0,1,255,256,257,65536,65537):
        for f in (0,1,2):rows.append(case(f'pool-nr{n}-fault{f}',flow='pool',nr=n,min=37,faults=[f,0,0]))
    for flags in (0,1,2,3):
        for n in (0,1,257):
            for f in (0,1):rows.append(case(f'list-flags{flags}-nr{n}-fault{f}',flow='list',nr=n,flags=flags,faults=[f,0,0]))
    rows += [case('old-partial-publication',flow='old',faults=[3,0,0]),case('old-borrow-overwrite',flow='old',borrow=1)]
    source.require(len({c['name'] for c in rows})==len(rows),'unique-cases')
    return rows


def layouts(extracted):
    """Independent bounded host layout from actual declarations, not C stdout."""
    text=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*','',extracted['types'])
    mapping={'a_uint8_t':ctypes.c_uint8,'a_uint16_t':ctypes.c_uint16,'a_uint32_t':ctypes.c_uint32,
             'a_uint64_t':ctypes.c_uint64,'void':None,'ll_nd_cmp':ctypes.c_void_p,'ll_nd_dump':ctypes.c_void_p}
    for name in re.findall(r'typedef\s+enum\s*\{[^}]*\}\s*(\w+)\s*;',text):mapping[name]=ctypes.c_int
    port=re.search(r'^#define SW_MAX_NR_PORT\s+(\d+)',text,re.M)
    source.require(port is not None,'actual-port-domain')
    mapping['fal_pbmp_t']=ctypes.c_uint32 if int(port.group(1))<=32 else ctypes.c_uint64
    structs={};fields={}
    for m in re.finditer(r'typedef\s+struct(?:\s+_\w+)?\s*\{([^}]*)\}\s*(\w+)\s*;',text):
        name=m.group(2);description=[];ct=[]
        for raw in m.group(1).split(';'):
            if not raw.strip():continue
            f=re.fullmatch(r'\s*(?:(struct)\s+)?(\w+)\s*(\*)?\s*(\w+)\s*',raw)
            source.require(f is not None,'bounded-layout-field:'+raw)
            _,kind,pointer,field=f.groups();typ=ctypes.c_void_p if pointer else mapping.get(kind)
            source.require(typ is not None,'layout-known-type:'+kind)
            ct.append((field,typ));description.append({'field':field,'type':kind,'pointer':bool(pointer)})
        obj=type(name,(ctypes.Structure,),{'_fields_':ct});mapping[name]=obj
        structs[name]=ctypes.sizeof(obj);fields[name]=description
    source.require(set(structs)=={'hsl_dev_t','fal_vlan_t','v_array_t','sll_node_t','sll_head_t','sid_pool_t'},'layout-inventory')
    return structs,fields


def header(matrix,sizes):
    def value(v):return json.dumps(v) if isinstance(v,str) else str(v)+'u' if v>2147483647 else str(v)
    lines=[f'_Static_assert(sizeof({n})=={size},"independent host layout {n}");' for n,size in sizes.items()]
    lines.append('static const struct input inputs[]={')
    for c in matrix:
        fields=['.'+k+'={'+','.join(map(str,v))+'}' if isinstance(v,list) else '.'+k+'='+value(v) for k,v in c.items()]
        lines.append('{'+','.join(fields)+'},')
    return '\n'.join(lines+['};\n'])


def pool_shape(n):
    return (1,((n+3)//4)*4) if n<=256 else (2,((n+1)//2)*4) if n<=65536 else (4,n*4)


def oracle(c,profile,sdk,sizes):
    events=[];add=events.append
    n=(0 if c['missing'] else c['nr'])&65535 if c['flow'] in ('vlan','old') else c['nr']
    serial=0
    slots={d:[101+d*10 if d!=c['dev'] or c['borrow']&1 else 0,
              103+d*10 if d!=c['dev'] or c['borrow']&2 else 0,
              104+d*10 if d!=c['dev'] or c['borrow']&4 else 0] for d in range(3)}
    # Non-current slots are full foreign sentinels; current absent bits stayNULL.
    width,inner=pool_shape(n)
    ph,db,lh,node=sizes['sid_pool_t'],sizes['v_array_t']*n,sizes['sll_head_t'],sizes['sll_node_t']
    add(f'TYPE {c["nr"]} {n} {c["dev"]}\n')
    def allocate(kind,bytes_,ordinal,fault):
        nonlocal serial
        serial+=1;ok=ordinal!=fault;add(f'ALLOC {serial} {kind} {bytes_} {int(ok)}\n')
        if ok:add(f'ZERO {serial} {bytes_}\n')
        return ok,serial
    def free(ident):add(f'FREE {ident}\n')
    def pool_fields(base,minimum):add(f'POOL {base} {base+1} 0 {n} {minimum} {width} IDS_OK\n')
    def list_fields(ident,flags):
        add(f'LIST {ident} {n} {flags} REVERSE_NODES_OK CALLBACKS_OK\n');add('vid = 7  member = 0x35\n')
    def construct(fault):
        base=serial+1
        ok,_=allocate(1,ph,1,fault)
        if not ok:return sdk['SW_FAIL'],0
        ok,_=allocate(2,inner,2,fault)
        if not ok:free(base);return sdk['SW_FAIL'],0
        ok,_=allocate(3,db,3,fault)
        if not ok:free(base+1);free(base);return sdk['SW_OUT_OF_MEM'],0
        ok,_=allocate(4,lh+node*n,4,fault)
        if not ok:free(base+2);free(base+1);free(base);return sdk['SW_FAIL'],0
        return 0,base
    ret=0
    for r in range(c['rounds']):
        success=0
        for step in range(c['steps']):
            f=c['faults'][step];add(f'BEGIN {r} {step} {f}\n')
            if c['flow']=='pool':
                base=serial+1
                if not n:ret=sdk['SW_FAIL']
                else:
                    ok,_=allocate(1,ph,1,f)
                    if not ok:ret=sdk['SW_FAIL']
                    else:
                        ok,_=allocate(2,inner,2,f)
                        if not ok:free(base);ret=sdk['SW_FAIL']
                        else:pool_fields(base,c['min']);free(base+1);free(base);ret=0
            elif c['flow']=='list':
                ok,ident=allocate(4,lh+(node*n if c['flags']&2 else 0),1,f)
                if ok:list_fields(ident,c['flags']);free(ident);ret=0
                else:ret=sdk['SW_FAIL']
            else:
                if c['dev']>=3:ret=sdk['SW_NOT_INITIALIZED']
                elif c['hw']==1:ret=0
                elif n==0 or n>4096:ret=sdk['SW_FAIL']
                elif c['borrow'] or success:ret=sdk['SW_ALREADY_EXIST']
                else:ret,success=construct(f)
                if ret==0 and c['hw']!=1 and c['dev']<3:
                    source.require(success>0,'oracle-success-owner')
                    pool_fields(success,0);list_fields(success+3,3)
                    slots[c['dev']]=[success,success+2,success+3]
                    add(f'PUBLISH {c["dev"]} {success} {success+2} {success+3}\n')
            add(f'RETURN {ret}\n')
        if success:
            add('NORMAL_CLEANUP\n');free(success+2);free(success+1);free(success);free(success+3)
            slots[c['dev']]=[0,0,0]
        add(f'ROUND_END {r}\n')
    for d,values in slots.items():add('SLOT %u %d %d %d\n' % ((d,)+tuple(values)))
    add('END OWNERS_CLOSED_FOREIGN_UNCHANGED\n')
    return ret,''.join(events).encode()


def positive(code,out,err,expected):source.require(code==0 and out==expected and err==b'','positive-exact-trace')
def negative(code,out,err,marker):source.require(code==86 and out==b'' and err==f'SSDK_VLAN {marker}\n'.encode(),'negative-exact-marker')


def output_controls():
    positive(0,b'x',b'',b'x');negative(86,b'',b'SSDK_VLAN X\n','X');rejects=0
    for row in [(1,b'x',b'',b'x'),(0,b'xx',b'',b'x'),(0,b'x',b'warning',b'x')]:
        try:positive(*row)
        except RuntimeError:rejects+=1
        else:raise RuntimeError('positive-gate-control')
    for row in [(1,b'',b'SSDK_VLAN X\n'),(-6,b'',b'SSDK_VLAN X\n'),(None,b'',b'SSDK_VLAN X\n'),
                (86,b'noise',b'SSDK_VLAN X\n'),(86,b'',b'SSDK_VLAN Y\n'),(86,b'',b'SSDK_VLAN X\nSSDK_VLAN X\n'),
                (86,b'',b'SSDK_VLAN X\nERROR: AddressSanitizer')]:
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


def model_controls(text,byname,profile,sdk,sizes,cc,flags,folder,env,generated):
    """Ledger-record pollution only; not a production or short-allocation mutant."""
    changed=once(text,'/* MODEL_LEDGER_INJECTION */',
                 'for(int j=0;j<nblocks;j++)if(blocks[j].id==success_base+2)blocks[j].kind=4;')
    binary=compile_c(cc,flags,changed,folder/'model-ledger-kind',env,generated)
    i,c=byname['dev0-nr257'];ret,expected=oracle(c,profile,sdk,sizes);ep=folder/(c['name']+'.expected')
    run=invoke([str(binary),str(i),str(ret),str(ep)],folder/'model-ledger-kind-run',env,generated)
    negative(run.returncode,run.stdout,run.stderr,'OWNED_IDENTITY_SHAPE')
    weak=once(changed,'b->kind==kind','(b->kind==kind || kind==3)')
    binary=compile_c(cc,flags,weak,folder/'model-ledger-kind-weakened',env,generated)
    run=invoke([str(binary),str(i),str(ret),str(ep)],folder/'model-ledger-kind-weakened-run',env,generated)
    positive(run.returncode,run.stdout,run.stderr,expected)
    return {'profile':profile,'rejected':1,'weakened_same_trace_counterexamples':1,
            'marker':'OWNED_IDENTITY_SHAPE','strong_source_sha256':source.digest(changed.encode()),
            'weak_source_sha256':source.digest(weak.encode()),
            'classification':'harness DB allocation-record kind pollution; same valid payload/trace passes only when that kind gate is weakened. NOT production mutation, real wrong allocation, or claim that source swaps evade fulltrace.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'PHY-PORT-ADMISSION-CANDIDATE-20261031-r1')
    p.add_argument('--candidate',type=Path,default=OLD/'VLAN-INIT-ROLLBACK-CANDIDATE-20261031-r1');args=p.parse_args()
    out=args.output.resolve();source.require(out.parent==AUDIT and out.name.startswith('VLAN-TEST-') and not out.exists(),'fresh-output');out.mkdir(parents=True)
    result={'status':'INCOMPLETE','qualification':'SERIALIZED_VLAN_CONSTRUCTOR_HOST_MODEL_ONLY','positives':[],'negatives':[],
            'python_optimize':sys.flags.optimize,'open':['target/root/UK/readers/concurrency/ABI','LSan','hardware-query is bypass only',
            'logical storage quarantine is not UAF/kernel allocator certification'],
            'allocator_contracts':{'linux-zero':'actual Linux wrappers request GFP_KERNEL|__GFP_ZERO; kmalloc leaf returns zero storage',
                                  'generic-poison-stress':'deliberate NON-Linux allocator-contract strengthening; never stock fault evidence'},
            'hsl_metadata':'actual bounds getter returns table entries for every valid dev; missing means zero-valued table, not synthetic NULL'};generated={}
    try:
        tree,inputs=source.prepare(args.base.resolve(),args.candidate.resolve(),out);record(out/'INPUTS.json',inputs,generated)
        new=source.extract(tree);sizes,fields=layouts(new);matrix=cases()
        record(out/'LAYOUT.json',{'sizes':sizes,'actual_declaration_fields':fields,'basis':'independent ctypes host layouts checked by C static assertions, NOT target ABI'},generated)
        record(out/'MATRIX.json',matrix,generated)
        sdk={k:int(v) for k,v in re.findall(r'\b(SW_\w+)\s*=\s*(-?\d+)',(tree/'include/common/sw_error.h').read_text())}
        record(out/'SDK-DOMAIN.json',sdk,generated)
        text,new,old=source.render(tree,args.base/'prepared',(SUPPORT/'fixture.c').read_text().replace('/* @CASES@ */',header(matrix,sizes)))
        record(out/'EXTRACTED.json',{'candidate':new['records'],'baseline':old['records'],'complete_bodies':list(new['bodies']),
            'transform':'no body cropping; old init name-only rename; memset scoped to tracked leaf only in actual __aos_mem_zero',
            'model':'kmalloc/kfree/tracked memset/OS storage; actual Linux wrappers retain __GFP_ZERO; separate poison profile deliberately non-Linux'},generated)
        cc=shutil.which(args.cc);source.require(cc is not None,'compiler-path');cc=str(Path(cc).resolve())
        result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function']
        env=dict(os.environ);env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        version=invoke([cc,'--version'],out/'compiler-version',env,generated);source.require(version.returncode==0 and version.stderr==b'','compiler-version')
        if args.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        result['output_controls']=output_controls();result['tail_controls']=tail_controls(out)
        expected_files={};byname={c['name']:(i,c) for i,c in enumerate(matrix)}
        for profile,pf in PROFILES.items():
            folder=out/profile;folder.mkdir();binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for i,c in enumerate(matrix):
                if c['flow']=='old':continue
                ret,expected=oracle(c,profile,sdk,sizes);ep=folder/(c['name']+'.expected');ep.write_bytes(expected)
                generated[str(ep)]=source.digest(expected);expected_files[str(ep)]=source.digest(expected)
                run=invoke([str(binary),str(i),str(ret),str(ep)],folder/c['name'],env,generated)
                positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append({'profile':profile,'case':c['name'],'stdout_sha256':source.digest(run.stdout)})
            if not args.positives_only:
                result.setdefault('model_controls',[]).append(model_controls(text,byname,profile,sdk,sizes,cc,flags+pf,folder,env,generated))
                for v in variants(new,old,profile):
                    mutated=once(text,v['before'],v['after']);mb=compile_c(cc,flags+pf,mutated,folder/v['name'],env,generated)
                    i,c=byname[v['case']];ret,_=oracle(c,profile,sdk,sizes)
                    run=invoke([str(mb),str(i),str(ret),str(folder/(c['name']+'.expected'))],folder/(v['name']+'-run'),env,generated)
                    negative(run.returncode,run.stdout,run.stderr,v['marker'])
                    result['negatives'].append({k:v[k] for k in ('name','symbol','case','marker','classification')}|{'profile':profile,'source_sha256':source.digest(mutated.encode())})
                for name,marker in [('old-partial-publication','EARLY_PUBLICATION'),('old-borrow-overwrite','BORROWED_ALLOCATION')]:
                    i,c=byname[name];ep=folder/(name+'.expected');ep.write_bytes(b'');generated[str(ep)]=source.digest(b'');expected_files[str(ep)]=source.digest(b'')
                    run=invoke([str(binary),str(i),'0',str(ep)],folder/(name+'-run'),env,generated)
                    negative(run.returncode,run.stdout,run.stderr,marker)
                    result['negatives'].append({'profile':profile,'name':name,'marker':marker,'classification':'complete old init with safe model frontier witness, NOT target fault reproduction'})
            record(out/'RESULTS.json',result)
        result['end_input_stability']=source.stable(inputs);expected_tail(out,expected_files);generated_tail(out,generated)
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler')
        result['expected_tail']='EXACT_PATHS_MEMORY_ORACLE_DIGESTS';result['generated_tail']='EXACT_FILES_ROOT_RESULT_EXCEPTION_FRESH692_SEPARATE'
        result['generated_files']=generated;result['positive_count']=len(result['positives']);result['negative_count']=len(result['negatives'])
        result['status']='DEV_CHECKPOINT_POSITIVES_ONLY' if args.positives_only else 'HOST_MODEL_ONLY'
        result['outcome']='NOT_FINAL_QUALIFICATION' if args.positives_only else 'PASSED_WITHIN_SERIALIZED_CONSTRUCTOR_MODEL'
    except Exception as e:result['status']='FAILED';result['error']=str(e);raise
    finally:record(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_count','negative_count')}))


if __name__=='__main__':main()
