#!/usr/bin/env python3
"""Two-TU native once host qualification. No target build or old program."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
SUPPORT = HERE.parent / 'ssdk-api-lock-once'
def load(name):
    spec = importlib.util.spec_from_file_location('lock_once_' + name, SUPPORT / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
source, mutations = load('source'), load('mutations')
ASSETS = [HERE, *(SUPPORT / n for n in source.MEMBERS)]
PROFILES = {
    'native-off': (1, ['KERNEL_MODULE', 'KVER32']),
    'native-paired': (1, ['KERNEL_MODULE', 'KVER32', 'API_LOCK', 'SW_API_LOCK']),
    'user': (0, ['USER_MODE', 'KVER32']),
    'combined': (0, ['KERNEL_MODULE', 'USER_MODE', 'KVER32']),
    'standalone': (0, ['KERNEL_MODULE', 'KVER32', 'HSL_STANDALONG']),
    'old': (0, ['KERNEL_MODULE']), 'bare': (0, ['KVER32'])}
POSITIVE = [(p,c) for p in ('native-off','native-paired') for c in ('load','repeat','held','bootstrap')]
POSITIVE += [(p,'legacy') for p in ('user','combined','standalone','old','bare')]
NEGATIVE = [
    (p,'missing-static','load','NATIVE_LOAD') for p in ('native-off','native-paired')]
NEGATIVE += [(p,'native-runtime-reset','held','HELD_PRESERVE') for p in ('native-off','native-paired')]
NEGATIVE += [(p,n,'legacy','LEGACY_INITIAL') for p,n in (
    ('bare','scope-without-kernel'),('old','scope-without-kver32'),
    ('combined','scope-includes-user'),('standalone','scope-includes-standalone'))]
NEGATIVE += [(p,'destroy-on-init','repeat','REPEAT_PRESERVE') for p in ('native-off','native-paired')]
NEGATIVE += [(p,'legacy-init-missing','legacy','LEGACY_INIT') for p in ('user','combined','standalone','old','bare')]
def exact(rows, expected, marker):
    source.require(len(rows)==len(set(rows)) and set(rows)==set(expected),marker)
def controls():
    rejected=[]; exact(NEGATIVE,NEGATIVE,'NEGATIVE_INVENTORY'); exact(POSITIVE,POSITIVE,'POSITIVE_INVENTORY')
    for name, bad in [('empty',[]),('missing',NEGATIVE[:-1]),('duplicate',NEGATIVE+[NEGATIVE[0]]),
                      ('profile',[('WRONG',*NEGATIVE[0][1:])]+NEGATIVE[1:]),
                      ('marker',[(*NEGATIVE[0][:3],'WRONG')]+NEGATIVE[1:])]:
        try: exact(bad,NEGATIVE,'NEGATIVE_INVENTORY')
        except ValueError as e: source.require(str(e)=='NEGATIVE_INVENTORY','CONTROL_MARKER')
        else: raise ValueError('CONTROL_ACCEPTED')
        rejected.append(name)
    return dict(valid=2,rejected=rejected,classification='PURE_INVENTORY_NOT_SOURCE')
def environment(code=97):
    return dict(os.environ, ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}',
                UBSAN_OPTIONS=f'halt_on_error=1:print_stacktrace=1:exitcode={code}')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cc',default='gcc-16'); parser.add_argument('--sanitize',action='store_true'); a=parser.parse_args()
    source.require(sys.flags.optimize>0,'PYTHON_O'); out=a.output.resolve()
    source.require(not out.exists(),'FRESH_OUTPUT'); out.mkdir(parents=True)
    generated={}; commands=[]; result=dict(status='FAILED',qualification='HOST_MODEL_ONLY',positives=[],negatives=[])
    def put(rel,raw):
        raw=raw.encode() if isinstance(raw,str) else raw; path=out/rel; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw); generated[rel]=source.digest(raw); return path
    def record(rel,obj): return put(rel,json.dumps(obj,indent=2)+'\n')
    def invoke(stem,argv,code=97):
        env=environment(code)
        try: p=subprocess.run(argv,capture_output=True,timeout=30,env=env)
        except subprocess.TimeoutExpired as e:
            put(stem+'.stdout',e.stdout or b''); put(stem+'.stderr',e.stderr or b'')
            record(stem+'.json',dict(argv=argv,timeout=True)); raise ValueError('TIMEOUT_NOT_CREDIT') from e
        put(stem+'.stdout',p.stdout); put(stem+'.stderr',p.stderr)
        row=dict(argv=argv,returncode=p.returncode,timeout=False,ASAN_OPTIONS=env['ASAN_OPTIONS'],UBSAN_OPTIONS=env['UBSAN_OPTIONS'])
        record(stem+'.json',row); commands.append(row); return p
    try:
        actual,sdk,extracted,inputs=source.prepare(a.candidate.resolve(),ASSETS)
        record('INPUTS.json',inputs); record('EXTRACTED.json',extracted); put('sdk.h',sdk)
        fixture=put('fixture.c',(SUPPORT/'fixture.c').read_bytes()); changed=mutations.variants(actual)
        source.require(set(changed)=={n for _,n,_,_ in NEGATIVE},'SOURCE_VARIANT_INVENTORY')
        planned=[(p,n,c,m) for p,n,c,m in NEGATIVE if p in PROFILES and n in changed]
        exact(planned,NEGATIVE,'NEGATIVE_PLAN'); result['inventory_controls']=controls()
        record('CONTRACT.json',dict(positive=POSITIVE,negative=NEGATIVE,profiles=PROFILES))
        cc=shutil.which(a.cc); source.require(cc is not None,'COMPILER'); cc=str(Path(cc).resolve())
        compiler_sha=source.sha(cc); result['compiler']=dict(path=cc,sha256=compiler_sha)
        flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wformat=2']
        if a.sanitize: flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        result['flags']=flags
        def compile_unit(stem,body,profile):
            unit=put(stem+'.c',body); native,defines=PROFILES[profile]; binary=out/(stem+'.bin')
            p=invoke(stem+'-compile',[cc,*flags,'-I'+str(out),'-DEXPECT_NATIVE='+str(native),
                *['-D'+n for n in defines],str(unit),str(fixture),'-o',str(binary)])
            source.require(p.returncode==0 and p.stdout==p.stderr==b'','CLEAN_COMPILE:'+stem)
            generated[stem+'.bin']=source.sha(binary); return binary
        binaries={p:compile_unit(p+'/positive',actual,p) for p in PROFILES}
        for profile,case in POSITIVE:
            stem=profile+'/'+case; expected=f'OK {case}\n'.encode(); put(stem+'.expected',expected)
            p=invoke(stem,[str(binaries[profile]),case])
            source.require(p.returncode==0 and p.stdout==expected and p.stderr==b'','POSITIVE_EXACT')
            result['positives'].append((profile,case))
        for profile,name,case,marker in NEGATIVE:
            stem=profile+'/'+name; binary=compile_unit(stem,changed[name],profile)
            expected=f'LOCK_ASSERT:{marker}\n'.encode(); put(stem+'.expected',expected)
            p=invoke(stem+'-run',[str(binary),case])
            source.require(p.returncode==86 and p.stdout==b'' and p.stderr==expected,'NEGATIVE_EXACT')
            result['negatives'].append((profile,name,case,marker))
        exact(result['positives'],POSITIVE,'POSITIVE_COMPLETION'); exact(result['negatives'],NEGATIVE,'NEGATIVE_COMPLETION')
        if a.sanitize:
            result['canaries']=[]
            for name,code,text,diagnostic in [
                ('asan',97,'#include <stdlib.h>\nint main(int c,char**v){(void)v;volatile char*p=malloc(1);p[c]=1;free((void*)p);return 0;}\n',b'AddressSanitizer'),
                ('ubsan',98,'#include <limits.h>\nint main(void){volatile int x=INT_MAX;return x+1;}\n',b'runtime error: signed integer overflow')]:
                unit=put('canary/'+name+'.c',text); binary=out/('canary/'+name+'.bin')
                p=invoke('canary/'+name+'-compile',[cc,*flags,str(unit),'-o',str(binary)])
                source.require(p.returncode==0 and p.stdout==p.stderr==b'','CANARY_COMPILE'); generated[str(binary.relative_to(out))]=source.sha(binary)
                p=invoke('canary/'+name+'-run',[str(binary)],code)
                source.require(p.returncode==code and p.stdout==b'' and diagnostic in p.stderr,'CANARY_ACTIVATION')
                result['canaries'].append(dict(name=name,exit=code))
        record('ASSET-FREEZE.json',dict(status='FROZEN_INPUT_ASSETS_HOST_MODEL_ONLY',source_sha256=source.C_SHA,
            assets_sha256={str(p):inputs[str(p)] for p in ASSETS},pending='Independent parent verification; no target claim'))
        source.stable(inputs,ASSETS); source.require(source.sha(cc)==compiler_sha,'COMPILER_DRIFT')
        source.require(source.inventory(out)==generated,'EXACT_OUTPUT_TAIL')
        result.update(status='HOST_MODEL_ONLY',positive_count=len(POSITIVE),source_variant_count=len(changed),negative_count=len(NEGATIVE),
                      inputs=inputs,generated=generated,end_inputs=True,end_outputs='EXACT_MEMORY_HASH_AND_PATHS',LSan='NOT_VERIFIED')
    except Exception as e: result['error']=str(e)
    result['commands']=commands; (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','positive_count','negative_count','error') if k in result}))
    return 0 if result['status']=='HOST_MODEL_ONLY' else 1
if __name__=='__main__': sys.exit(main())
