#!/usr/bin/env python3
"""Fixed pinned-tree admission plus actual NSS input-function host fixtures."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve(); SUPPORT=HERE.parent/'nss-command-inputs'


def load(name):
    spec=importlib.util.spec_from_file_location('nss_inputs_'+name,SUPPORT/(name+'.py'))
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


source=load('source'); mutations=load('mutations')
CASES=('sequence-bounds','sequence-first-last','firmware-terminal','firmware-version',
       'ppe-valid','ppe-invalid','ppe-read','ppe-errors','ppe-refbalance','ppe-bounds',
       'mirror-dispatch','mirror-config','mirror-invalid','mirror-errors','mirror-bounds',
       'tunip-frag','tunip-map','tunip-del-flush','tunip-errors','tunip-bounds')
# Independent completion obligations; never inferred from observed failures/variant list.
NEGATIVES=(
 ('sequence-short','sequence-bounds','SEQ_RANGE'),('sequence-first','sequence-first-last','SEQ_FIRST'),
 ('sequence-last','sequence-first-last','SEQ_LAST'),('sequence-match','sequence-first-last','SEQ_FIRST'),
 ('firmware-offset','firmware-version','FW_VERSION'),('ppe-copy','ppe-valid','PPE_VALID'),
 ('ppe-proc','ppe-errors','PPE_ERROR'),('ppe-type','ppe-valid','PPE_TYPE'),('ppe-read','ppe-read','PPE_READ'),
 ('ppe-put','ppe-refbalance','PPE_PUT'),('ppe-shared-request','ppe-valid','PPE_VALID'),
 ('ppe-position','ppe-bounds','PPE_POSITION'),('mirror-copy','mirror-dispatch','MIRROR_DISPATCH'),
 ('mirror-limit','mirror-bounds','MIRROR_LIMIT'),('mirror-proc','mirror-errors','MIRROR_PROC'),
 ('mirror-empty-name','mirror-invalid','MIRROR_EMPTY_NAME'),
 ('tunip-copy','tunip-frag','TUNIP_FRAG'),('tunip-limit','tunip-bounds','TUNIP_LIMIT'),
 ('tunip-size','tunip-bounds','TUNIP_ALLOC'),('tunip-suffix-length','tunip-map','TUNIP_SUFFIX_LENGTH'))


def need(ok,why):
    if not ok: raise ValueError(why)


def obligation_gate(rows):
    rows=[tuple(r) for r in rows]
    need(len(rows)==20 and len(set(rows))==20 and set(rows)==set(NEGATIVES),'FIXED_NEGATIVE_INVENTORY')


def inventory_controls():
    good=list(NEGATIVES); obligation_gate(good)
    changed_case=list(good); changed_case[0]=(good[0][0],'wrong-case',good[0][2])
    changed_marker=list(good); changed_marker[0]=good[0][:2]+('WRONG_MARKER',)
    changed_name=list(good); changed_name[0]=('wrong-name',)+good[0][1:]
    for bad in ([],good[:-1],good+[good[0]],changed_case,changed_marker,changed_name):
        try: obligation_gate(bad)
        except ValueError as e: need(str(e)=='FIXED_NEGATIVE_INVENTORY','CONTROL_DIAGNOSTIC')
        else: raise ValueError('INVENTORY_POLLUTION_ACCEPTED')
    return {'valid':1,'rejected':6,'classification':'PYTHON_INVENTORY_CONTROLS_NOT_SOURCE_MUTANTS'}


def metadata_controls(run):
    stem='metadata-controls'; root=run.root/stem
    run.write(stem+'/input.c',b'TESTONLY metadata admission data, never compiled\n')
    expected={'input.c':source.sha(b'TESTONLY metadata admission data, never compiled\n')}
    run.write(stem+'/version.date',b'1770000000\n')
    stamp='.prepared_'+'a'*32+'_'+'b'*32
    run.write(stem+'/'+stamp,b'')
    def gate(): need(source.partition(root)[0]==expected,'METADATA_CODE_INVENTORY')
    gate(); rejected=0
    for name,raw in [('rogue.c',b'not allowed'),('version.date',b'bad\n'),(stamp,b'not empty'),
                     ('.prepared_'+'c'*32+'_'+'d'*32,b''),('nested/'+stamp,b''),('.configured',b'')]:
        path=root/name; old=path.read_bytes() if path.exists() else None
        run.write(stem+'/'+name,raw)
        try: gate()
        except ValueError: rejected+=1
        else: raise ValueError('METADATA_POLLUTION_ACCEPTED: '+name)
        if old is not None: run.write(stem+'/'+name,old)
        else: path.unlink(); del run.generated[stem+'/'+name]
    link=root/'link'; link.symlink_to(root/'input.c')
    try: gate()
    except ValueError: rejected+=1
    else: raise ValueError('METADATA_SYMLINK_ACCEPTED')
    link.unlink(); gate()
    return {'valid':1,'rejected':rejected,'classification':'METADATA_MODEL_CONTROLS_NOT_SOURCE_MUTANTS'}


class Run:
    def __init__(self,args):
        self.args=args; self.root=args.output; self.generated={}; self.commands=[]
        self.env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
                      UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode=98:print_stacktrace=1')

    def write(self,name,data):
        if isinstance(data,str): data=data.encode()
        p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
        self.generated[name]=source.sha(data); return p

    def invoke(self,name,command,cwd=None,data=None,env=None):
        effective=self.env if env is None else env
        try:
            p=subprocess.run(command,cwd=cwd,input=data,capture_output=True,env=effective,timeout=60)
        except subprocess.TimeoutExpired as e:
            self.write(name+'.stdout',e.stdout or b''); self.write(name+'.stderr',e.stderr or b'')
            self.write(name+'.json',json.dumps({'command':command,'timeout':True},indent=2))
            raise ValueError('TIMEOUT: '+name)
        self.write(name+'.stdout',p.stdout); self.write(name+'.stderr',p.stderr)
        row={'command':command,'returncode':p.returncode,'timeout':False,
             'ASAN_OPTIONS':effective['ASAN_OPTIONS'],'UBSAN_OPTIONS':effective['UBSAN_OPTIONS'],
             'label':name,'stdout_file':name+'.stdout','stderr_file':name+'.stderr',
             'stdout_sha256':source.sha(p.stdout),'stderr_sha256':source.sha(p.stderr)}
        self.commands.append(row); self.write(name+'.json',json.dumps(row,indent=2)+'\n'); return p

    def compile(self,label,bodies,types,provenance,text=None):
        if bodies is not None:
            for group,items in bodies.items():
                code='\n'.join('#line '+str(provenance[n]['line'])+' "'+provenance[n]['path']+'"\n'+b
                               for n,b in items.items())
                self.write(label+'/actual-'+group+'.c',code+'\n')
            self.write(label+'/types.h',types)
            for name in ('model.h','fixture.c'): self.write(label+'/'+name,(SUPPORT/name).read_bytes())
        else: self.write(label+'/fixture.c',text)
        directory=self.root/label; binary=directory/'program.host'
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror']
        if self.args.sanitize: flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
        p=self.invoke(label+'/compile',[self.args.cc,*flags,str(directory/'fixture.c'),'-o',str(binary)])
        need(p.returncode==0 and not p.stdout and not p.stderr,'CLEAN_COMPILE: '+label)
        self.generated[str(binary.relative_to(self.root))]=source.sha(binary.read_bytes())
        dsym=Path(str(binary)+'.dSYM')
        if dsym.exists():
            info='Contents/Info.plist'; dwarf='Contents/Resources/DWARF/program.host'; reloc='Contents/Resources/Relocations/aarch64/program.host.yml'
            names={p.relative_to(dsym).as_posix() for p in dsym.rglob('*') if p.is_file()}
            need(names in ({info,dwarf},{info,reloc},{info,dwarf,reloc}),'DSYM_SHAPE')
            for name in names:
                p=dsym/name; self.generated[p.relative_to(self.root).as_posix()]=source.sha(p.read_bytes())
        return binary

    def roundtrip(self,label,tree,profile):
        code,_=source.partition(tree); relative='roundtrip-'+label; copied=self.root/relative
        for name in code: self.write(relative+'/'+name,(tree/name).read_bytes())
        patch_name='027-checked-command-and-sequence-inputs.patch' if label=='driver' else '026-parse-sysctl-kernel-buffers.patch'
        patch=source.REPO/'package/qca-nss'/profile['package']/'patches'/patch_name
        command=[shutil.which('gpatch') or 'patch','--batch','--fuzz=0','-p1']
        p=self.invoke(label+'-reverse',command+['-R'],cwd=copied,data=patch.read_bytes())
        need(p.returncode==0 and not p.stderr and not re.search(rb'offset|fuzz|FAILED|reject',p.stdout,re.I),'REVERSE_NEW_PATCH')
        need(source.inventory_hash(source.inventory(copied))==profile['baseline_inventory_sha256'],'FIXED_BASELINE_TREE: '+label)
        # Keep an immutable source-data baseline, not a previously compiled program.
        baseline=self.root/('baseline-'+label); shutil.copytree(copied,baseline)
        for name in code: self.generated['baseline-'+label+'/'+name]=source.sha((baseline/name).read_bytes())
        p=self.invoke(label+'-forward',command,cwd=copied,data=patch.read_bytes())
        need(p.returncode==0 and not p.stderr and not re.search(rb'offset|fuzz|FAILED|reject',p.stdout,re.I),'FORWARD_NEW_PATCH')
        need(source.inventory_hash(source.inventory(copied))==profile['candidate_inventory_sha256'],'ROUNDTRIP_CANDIDATE_TREE')
        for name in code: self.generated[relative+'/'+name]=source.sha((copied/name).read_bytes())
        return baseline


def verify_canaries(run):
    main_env=dict(run.env); controls=[]
    for name,text,exitcode,diagnostic in (
        ('asan','#include <stdlib.h>\n__attribute__((noinline)) void write_index(volatile int*p,int i){p[i]=1;}\nint main(int c,char**v){volatile int*p=malloc(sizeof(int));(void)v;write_index(p,c);free((void*)p);return 0;}\n',97,b'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan','#include <limits.h>\nint main(void){volatile int n=INT_MAX;return n+1;}\n',98,b'runtime error: signed integer overflow:')):
        binary=run.compile('canary/'+name,None,None,None,text)
        control_env=dict(run.env)
        # Apple shared flags and GCC's independent runtimes both need explicit
        # matching exit/abort settings. Never let a diagnostic count as rc86.
        control_env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode='+str(exitcode)
        control_env['UBSAN_OPTIONS']='halt_on_error=1:abort_on_error=0:exitcode='+str(exitcode)+':print_stacktrace=1'
        p=run.invoke('canary/'+name+'/run',[str(binary)],env=control_env)
        need(p.returncode==exitcode and not p.stdout and diagnostic in p.stderr,'SANITIZER_ACTIVATION: '+name)
        need((b'WRITE of size 4' if name=='asan' else b'2147483647 + 1') in p.stderr,'DIRECTED_SANITIZER_DIAGNOSTIC')
        controls.append({'name':name,'exitcode':exitcode,'diagnostic':diagnostic.decode(),
                         'ASAN_OPTIONS':control_env['ASAN_OPTIONS'],'UBSAN_OPTIONS':control_env['UBSAN_OPTIONS']})
    need(run.env==main_env,'RESTORE_MAIN_SANITIZER_ENV')
    return controls


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',type=Path,required=True); parser.add_argument('--clients',type=Path,required=True)
    parser.add_argument('--cc',required=True); parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--positives-only',action='store_true',help='DEV_ONLY, never final qualification')
    args=parser.parse_args(); args.output=args.output.resolve()
    need(not args.output.exists(),'FRESH_OUTPUT'); args.output.mkdir(parents=True)
    run=Run(args); report={'status':'INCOMPLETE','qualification':'HOST_MODELS_NOT_TARGET_ABI_FW_OR_LIFETIME',
                         'positives':[],'negatives':[],'commands':run.commands}
    try:
        profile=source.check_profile(args.driver,args.clients)
        report['source_profile_sha256']=source.sha((SUPPORT/'profile.json').read_bytes())
        report['inventory_controls']=inventory_controls()
        report['metadata_controls']=metadata_controls(run)
        assets=[HERE,*sorted(p for p in SUPPORT.rglob('*') if p.is_file() and '__pycache__' not in p.parts)]
        assets += [source.REPO/'tests/nss-dp-containment/extract_prepared_c.py',source.REPO/'tests/edma_patch_context.py']
        assets += [source.REPO/name for name in profile['metadata_rule_inputs']]
        assets += [HERE.parent/'NSS_COMMAND_INPUT_REPAIRS_2026-11-03.md']
        inputs={str(p):source.sha(p.read_bytes()) for p in assets}
        trees={str(p):source.inventory(p) for p in (args.driver,args.clients)}
        for label in ('driver','clients'):
            pkg=source.REPO/'package/qca-nss'/profile[label]['package']
            for p in [pkg/'Makefile',*sorted((pkg/'patches').glob('*.patch'))]: inputs[str(p)]=source.sha(p.read_bytes())
        report.update(inputs=inputs,prepared_metadata={str(p):source.partition(p)[1] for p in (args.driver,args.clients)})
        report['fixed_source_contract']={label:{k:v for k,v in profile[label].items() if k!='patches'}
                                         for label in ('driver','clients')}
        run.write('INPUTS.json',json.dumps(inputs,indent=2,sort_keys=True)+'\n')
        run.write('TREES.json',json.dumps(trees,indent=2,sort_keys=True)+'\n')
        for label,tree in (('driver',args.driver),('clients',args.clients)): run.roundtrip(label,tree,profile[label])
        bodies,types,provenance=source.render(args.driver,args.clients)
        report['actual_functions']=provenance
        need(set(mutations.EDITS)=={r[0] for r in NEGATIVES},'MUTATION_INVENTORY')
        obligation_gate(NEGATIVES)
        run.write('OBLIGATIONS.json',json.dumps(NEGATIVES,indent=2)+'\n')
        binary=run.compile('positive',bodies,types,provenance)
        for case in CASES:
            expected=('PASS '+case+'\n').encode(); run.write('positive/'+case+'.expected',expected)
            p=run.invoke('positive/'+case,[str(binary),case])
            need(p.returncode==0 and p.stdout==expected and not p.stderr,'POSITIVE: '+case)
            report['positives'].append(case)
        if not args.positives_only:
            for name,case,marker in NEGATIVES:
                binary=run.compile('negative/'+name,mutations.changed(bodies,name),types,provenance)
                expected=('NSS_INPUT:'+marker+'\n').encode(); run.write('negative/'+name+'/stderr.expected',expected)
                p=run.invoke('negative/'+name+'/run',[str(binary),case])
                need(p.returncode==86 and not p.stdout and p.stderr==expected,'EXACT_NEGATIVE: '+name)
                report['negatives'].append((name,case,marker))
            obligation_gate(report['negatives'])
        need(tuple(report['positives'])==CASES,'POSITIVE_COMPLETION')
        if args.sanitize:
            report['sanitizer_controls']=verify_canaries(run)
        need(all(source.sha(Path(p).read_bytes())==h for p,h in inputs.items()),'END_INPUT_STABILITY')
        need(all(source.inventory(Path(p))==v for p,v in trees.items()),'END_TREE_STABILITY')
        source.check_profile(args.driver,args.clients)
        observed=source.inventory(run.root); observed.pop('RESULTS.json',None)
        need(observed==run.generated,'GENERATED_EXACT_INVENTORY_AND_BYTES')
        report.update(status='DEV_ONLY' if args.positives_only else 'PASS_HOST_COMMAND_INPUTS_ONLY',
                      positive_count=len(report['positives']),negative_count=len(report['negatives']),
                      end_input_stability=True,generated=run.generated,sanitize=args.sanitize,LSan='NOT_VERIFIED')
    except Exception as e: report['error']=str(e)
    (args.output/'RESULTS.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ('status','error','positive_count','negative_count') if k in report}))
    return 0 if report['status'] in ('PASS_HOST_COMMAND_INPUTS_ONLY','DEV_ONLY') else 1


if __name__=='__main__': sys.exit(main())
