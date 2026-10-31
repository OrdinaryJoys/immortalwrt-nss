#!/usr/bin/env python3
"""Complete actual root exit trace in a bounded serial leaf model."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve(); SUPPORT=HERE.parent/'ssdk-root-exit-order'
spec=importlib.util.spec_from_file_location('root_exit_source',SUPPORT/'source.py')
source=importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
ASSETS=[HERE,*(SUPPORT/n for n in source.MEMBERS)]
CHIPS=('DESS','HPPE','ISISC','ISIS','MP','none')
PROFILES={chip.lower()+('-sfp' if sfp else '-off'):(chip,sfp) for chip in CHIPS for sfp in (0,1)}
PROFILE_NAMES=('dess-off','dess-sfp','hppe-off','hppe-sfp','isisc-off','isisc-sfp',
               'isis-off','isis-sfp','mp-off','mp-sfp','none-off','none-sfp')
ERRORS=((0,0,0),(-1,0,0),(0,-4,0),(0,0,-5),(-7,-8,-9),(0,-2,-3))
CASES=[(n,mask,0,0,0) for n in range(4) for mask in range(1<<n)]
for n in (1,2,3):
    for errors in dict.fromkeys(row[:n] for row in ERRORS):
        if any(errors): CASES.append((n,(1<<n)-1,*errors,*([0]*(3-n))))
NEGATIVE=(('old-interleaved',(2,3,0,0,0),'PRODUCER_BARRIER'),
          ('early-sfp-retire',(2,3,0,0,0),'PRODUCER_BARRIER'),
          ('missing-cleanup',(2,3,0,0,0),'CLEANUP_MISSING'),
          ('overwrite-first-error',(3,7,-7,-8,-9),'FIRST_ERROR'),
          ('early-platform',(2,3,0,0,0),'PLATFORM_EARLY'),
          ('ignore-registered',(1,0,0,0,0),'REGISTERED_GUARD'))
def exact(rows,expected,marker):
    source.require(len(rows)==len(set(rows)) and set(rows)==set(expected),marker)
def expected(indices,profile):
    chip,sfp=PROFILES[profile]; lines=[]
    for ix in indices:
        n,mask,*errors=CASES[ix]; lines.append('CASE '+' '.join(map(str,(ix,n,mask,*errors)))+'\nNOTIFIER\nCONTROLS\nGET '+str(n)+'\n')
        for d in range(n):
            lines.append(f'DRIVER {d}\n')
            if chip!='none' and mask&(1<<d): lines.append(f'SWITCH {d}\n')
        if sfp: lines.extend(f'SFP {d}\n' for d in range(n))
        for d in range(n):
            lines.append(f'CLEANUP {d} {errors[d]}\n')
            if errors[d]: lines.append(f'ERROR qca-host device {d} cleanup failed! (code: {errors[d]})\n')
        first=next((e for e in errors[:n] if e),0)
        lines.append(f'ERROR qca-host module exit failed! (code: {first})\n' if first else 'INFO qca-host module exit  done!\n')
        lines.extend(f'PLATFORM {d}\n' for d in range(n)); lines.append('FREE\nEND\n')
    return ''.join(lines).encode()
def env(code=97):
    return dict(os.environ,ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}',
                UBSAN_OPTIONS=f'halt_on_error=1:print_stacktrace=1:exitcode={code}')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path); p.add_argument('--output',required=True,type=Path)
    p.add_argument('--cc',default='gcc-16'); p.add_argument('--sanitize',action='store_true'); a=p.parse_args()
    source.require(sys.flags.optimize>0,'PYTHON_O'); out=a.output.resolve()
    source.require(not out.exists(),'FRESH_OUTPUT'); out.mkdir(parents=True)
    generated={}; commands=[]; result=dict(status='FAILED',qualification='HOST_MODEL_ONLY',positives=[],negatives=[])
    def put(name,data):
        data=data.encode() if isinstance(data,str) else data; path=out/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data); generated[name]=source.digest(data); return path
    def record(name,value): return put(name,json.dumps(value,indent=2)+'\n')
    def invoke(stem,argv,code=97):
        used=env(code)
        try: r=subprocess.run(argv,capture_output=True,timeout=30,env=used)
        except subprocess.TimeoutExpired as e:
            put(stem+'.stdout',e.stdout or b''); put(stem+'.stderr',e.stderr or b'')
            record(stem+'.json',dict(argv=argv,timeout=True)); raise ValueError('TIMEOUT_NOT_CREDIT') from e
        put(stem+'.stdout',r.stdout); put(stem+'.stderr',r.stderr)
        row=dict(argv=argv,returncode=r.returncode,timeout=False,ASAN_OPTIONS=used['ASAN_OPTIONS'],UBSAN_OPTIONS=used['UBSAN_OPTIONS'])
        record(stem+'.json',row); commands.append(row); return r
    try:
        source.require(len(CASES)==26 and len(set(CASES))==26,'FIXED_CASES')
        source.require(set(PROFILES)==set(PROFILE_NAMES),'FIXED_PROFILES')
        actual,sdk,inputs,extraction=source.prepare(a.source.resolve(),ASSETS); variants=source.variants(actual)
        source.require(set(variants)=={row[0] for row in NEGATIVE} and len(NEGATIVE)==6,'FIXED_SOURCE_VARIANTS')
        positive_plan=[(pr,ix) for pr in PROFILE_NAMES for ix in range(26)]
        negative_plan=[(n,CASES.index(c),m) for n,c,m in NEGATIVE]
        exact(positive_plan,positive_plan,'POSITIVE_PLAN'); exact(negative_plan,negative_plan,'NEGATIVE_PLAN')
        controls=[]
        for name,bad in [('empty',[]),('missing',negative_plan[:-1]),('duplicate',negative_plan+[negative_plan[0]]),
                         ('marker',[(*negative_plan[0][:2],'WRONG')]+negative_plan[1:])]:
            try: exact(bad,negative_plan,'NEGATIVE_INVENTORY')
            except ValueError as e: source.require(str(e)=='NEGATIVE_INVENTORY','CONTROL_MARKER')
            else: raise ValueError('CONTROL_ACCEPTED')
            controls.append(name)
        record('INPUTS.json',inputs); record('EXTRACTED.json',extraction); put('sdk.h',sdk)
        put('fixture.c',(SUPPORT/'fixture.c').read_bytes())
        put('cases.h','static const struct input inputs[]={\n'+''.join('{%d,%d,{%d,%d,%d}},\n'%row for row in CASES)+'};\n')
        record('CONTRACT.json',dict(profiles=PROFILES,cases=CASES,positive=positive_plan,negative=negative_plan))
        cc=shutil.which(a.cc); source.require(cc is not None,'COMPILER'); cc=str(Path(cc).resolve()); cc_sha=source.sha(cc)
        result['compiler']=dict(path=cc,sha256=cc_sha)
        flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wformat=2']
        if a.sanitize: flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        result['flags']=flags
        def compile_case(stem,body,profile):
            chip,sfp=PROFILES[profile]; folder=out/stem; put(stem+'/actual.c',body+'\n')
            fixture=put(stem+'/fixture.c',(SUPPORT/'fixture.c').read_bytes()); binary=folder/'fixture.bin'
            defines=['-DHAS_SWITCH_GUARD='+str(int(chip!='none')),'-DEXPECT_SFP='+str(sfp)]
            if chip!='none': defines+=['-D'+chip]
            if sfp: defines+=['-DIN_SFP_PHY']
            r=invoke(stem+'/compile',[cc,*flags,*defines,'-I'+str(out),str(fixture),'-o',str(binary)])
            source.require(r.returncode==0 and r.stdout==r.stderr==b'','CLEAN_COMPILE:'+stem)
            generated[stem+'/fixture.bin']=source.sha(binary); return binary
        for profile in PROFILE_NAMES:
            stem=profile+'/positive'; binary=compile_case(stem,actual,profile); oracle=expected(range(26),profile)
            put(stem+'/stdout.expected',oracle); r=invoke(stem+'/run',[str(binary)])
            source.require(r.returncode==0 and r.stdout==oracle and r.stderr==b'','POSITIVE_EXACT')
            result['positives'].extend((profile,ix) for ix in range(26))
        for name,ix,marker in negative_plan:
            stem='negative/'+name; binary=compile_case(stem,variants[name],'hppe-sfp')
            put(stem+'/stderr.expected',f'ROOT_ASSERT:{marker}\n'); r=invoke(stem+'/run',[str(binary),str(ix)])
            source.require(r.returncode==86 and r.stdout==b'' and r.stderr==f'ROOT_ASSERT:{marker}\n'.encode(),'NEGATIVE_EXACT:'+name)
            result['negatives'].append((name,ix,marker))
        exact(result['positives'],positive_plan,'POSITIVE_COMPLETION'); exact(result['negatives'],negative_plan,'NEGATIVE_COMPLETION')
        if a.sanitize:
            result['canaries']=[]
            for name,code,text,diagnostic in [
                ('asan',97,'#include <stdlib.h>\nint main(int c,char**v){(void)v;volatile char*p=malloc(1);p[c]=1;free((void*)p);return 0;}\n',b'AddressSanitizer'),
                ('ubsan',98,'#include <limits.h>\nint main(void){volatile int x=INT_MAX;return x+1;}\n',b'runtime error: signed integer overflow')]:
                unit=put('canary/'+name+'.c',text); binary=out/('canary/'+name+'.bin')
                r=invoke('canary/'+name+'-compile',[cc,*flags,str(unit),'-o',str(binary)])
                source.require(r.returncode==0 and r.stdout==r.stderr==b'','CANARY_COMPILE'); generated[str(binary.relative_to(out))]=source.sha(binary)
                r=invoke('canary/'+name+'-run',[str(binary)],code)
                source.require(r.returncode==code and r.stdout==b'' and diagnostic in r.stderr,'CANARY_ACTIVATION'); result['canaries'].append(dict(name=name,exit=code))
        record('ASSET-FREEZE.json',dict(status='FROZEN_INPUT_ASSETS_HOST_MODEL_ONLY',source_sha256=source.SOURCE_SHA,
            assets_sha256={str(p):inputs[str(p)] for p in ASSETS},pending='Independent parent GCC/Clang and review'))
        source.stable(inputs,ASSETS); source.require(source.sha(cc)==cc_sha,'COMPILER_DRIFT')
        source.require(source.inventory(out)==generated,'EXACT_GENERATED_TAIL')
        result.update(status='HOST_MODEL_ONLY',positive_count=len(positive_plan),source_variant_count=6,negative_count=6,
            inputs=inputs,generated=generated,end_inputs=True,end_outputs='EXACT_MEMORY_HASH_AND_PATHS',inventory_controls=controls,LSan='NOT_VERIFIED')
    except Exception as e: result['error']=str(e)
    result['commands']=commands; (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','positive_count','negative_count','error') if k in result}))
    return 0 if result['status']=='HOST_MODEL_ONLY' else 1
if __name__=='__main__': sys.exit(main())
