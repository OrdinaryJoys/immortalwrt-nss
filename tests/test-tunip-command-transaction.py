#!/usr/bin/env python3
"""Independent pinned tunip command ownership/error host qualification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
SUPPORT = HERE.parent/'tunip-command-transaction'


def load(name):
    spec = importlib.util.spec_from_file_location('new_tunip_'+name, SUPPORT/(name+'.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


source, contract, mutations = (load(n) for n in ('source','contract','mutations'))
need = source.need
CASE_NAMES = (
    'add-bmr','add-fmr','delete-bmr','delete-fmr','flush','frag-one','frag-zero',
    'frag-missing','frag-unknown-only','frag-forbidden-netdev','frag-repeat-valid',
    'duplicate-different','duplicate-same','duplicate-three','duplicate-last-missing',
    'first-missing','empty-netdev','duplicate-empty-netdev','missing-value-after-netdev','zero-rule',
    'duplicate-parse-error','missing-netdev','missing-rule','missing-map-fields',
    'empty-request','whitespace-map','null-buffer','null-lenp','read','size-max','oversized',
    'full-buffer','oom','oom-retry','invalid-mode','invalid-frag-value','empty-rule_type',
    'empty-ipv4_prefix_len','empty-ipv6_prefix_len','empty-ipv6_suffix_len','empty-ea_len',
    'empty-psid_offset','empty-frag','zero-fields','lower-add-invalid-param','lower-add-invalid-rule',
    'lower-add-no-node','lower-add-tx-failure','lower-del-invalid-param','lower-del-invalid-rule',
    'lower-del-no-node','lower-del-tx-failure','lower-flush-invalid-param','lower-flush-invalid-rule',
    'lower-flush-no-node','lower-flush-tx-failure','lower-unknown','lower-retry')
NEGATIVES = (
    ('replace-leaks-old','duplicate-different','REF_BALANCE'),
    ('replace-puts-new','duplicate-different','PROVIDER_REF'),
    ('missing-loses-old','duplicate-last-missing','REF_BALANCE'),
    ('exit-leaks-ref','flush','REF_BALANCE'),('missing-errno','first-missing','RETURN'),
    ('semantic-success','missing-rule','RETURN'),('swallow-final-error','missing-rule','RETURN'),
    ('ignore-frag-presence','frag-missing','RETURN'),('never-frag-present','frag-one','RETURN'),
    ('wrong-frag-value','frag-one','FRAG_STATE'),('skip-provider-error','lower-flush-tx-failure','RETURN'),
    ('invalid-map-error','lower-add-invalid-param','RETURN'),('node-map-error','lower-flush-no-node','RETURN'),
    ('io-map-success','lower-flush-tx-failure','RETURN'),('success-map-error','flush','RETURN'),
    ('exit-leaks-buffer','duplicate-parse-error','ALLOC_BALANCE'),
    ('double-free-buffer','flush','FREE_OWNER'),('no-publish-device','flush','PROVIDER_REF'),
    ('wrapper-add','missing-map-fields','RETURN'),('wrapper-del','missing-rule','RETURN'),
    ('wrapper-flush','first-missing','RETURN'),('wrapper-frag','frag-missing','RETURN'))
BASELINE_EQUIVALENT = ('add-bmr','add-fmr','delete-bmr','delete-fmr','flush','frag-one',
                       'frag-zero','frag-repeat-valid','zero-fields','full-buffer')
BASELINE_WITNESSES = (('duplicate-different','REF_BALANCE'),('frag-missing','RETURN'),
                      ('missing-rule','RETURN'),('lower-flush-tx-failure','RETURN'))


def obligations(rows):
    rows = [tuple(r) for r in rows]
    need(len(rows) == 22 and len(set(rows)) == 22 and set(rows) == set(NEGATIVES), 'FIXED_NEGATIVE_CONTRACT')


def inventory_controls():
    obligations(NEGATIVES); rows = list(NEGATIVES)
    bad_marker = list(rows); bad_marker[0] = rows[0][:2]+('WRONG',)
    bad_case = list(rows); bad_case[0] = (rows[0][0],'wrong-case',rows[0][2])
    bad_name = list(rows); bad_name[0] = ('wrong-name',)+rows[0][1:]
    for bad in ([],rows[:-1],rows+[rows[0]],bad_marker,bad_case,bad_name):
        try:
            obligations(bad)
        except ValueError as e:
            need(str(e) == 'FIXED_NEGATIVE_CONTRACT', 'CONTROL_DIAGNOSTIC')
        else:
            raise ValueError('INVENTORY_CONTROL_ACCEPTED')
    return {'valid':1,'rejected':6,'classification':'PURE_TEST_INVENTORY_NOT_SOURCE_MUTANTS'}


class Run:
    def __init__(self, args):
        self.args=args; self.root=args.output; self.generated={}; self.commands=[]
        self.env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
                      UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode=98:print_stacktrace=1')

    def write(self, name, raw):
        if isinstance(raw,str):
            raw=raw.encode()
        path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
        self.generated[name]=source.sha(raw); return path

    def invoke(self, name, command, cwd=None, data=None, env=None):
        effective=self.env if env is None else env
        try:
            p=subprocess.run(command,cwd=cwd,input=data,capture_output=True,env=effective,timeout=60)
        except subprocess.TimeoutExpired as e:
            self.write(name+'.stdout',e.stdout or b''); self.write(name+'.stderr',e.stderr or b'')
            self.write(name+'.json',json.dumps({'command':command,'timeout':True},indent=2)+'\n')
            raise ValueError('TIMEOUT: '+name)
        self.write(name+'.stdout',p.stdout); self.write(name+'.stderr',p.stderr)
        row={'label':name,'command':command,'returncode':p.returncode,'timeout':False,
             'stdout_file':name+'.stdout','stderr_file':name+'.stderr',
             'stdout_sha256':source.sha(p.stdout),'stderr_sha256':source.sha(p.stderr),
             'ASAN_OPTIONS':effective['ASAN_OPTIONS'],'UBSAN_OPTIONS':effective['UBSAN_OPTIONS']}
        self.commands.append(row); self.write(name+'.json',json.dumps(row,indent=2)+'\n'); return p

    def compile(self, name, bodies=None, types=None, provenance=None, text=None):
        if bodies is not None:
            raw='\n'.join('#line '+str(provenance[n]['line'])+' "'+provenance[n]['path']+'"\n'+body
                          for n,body in bodies.items())+'\n'
            self.write(name+'/actual.c',raw); self.write(name+'/types.h',types)
            for file in ('fixture.c','model.h'):
                self.write(name+'/'+file,(SUPPORT/file).read_bytes())
        else:
            self.write(name+'/fixture.c',text)
        directory=self.root/name; binary=directory/'program.host'
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror']
        if self.args.sanitize:
            flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
        p=self.invoke(name+'/compile',[self.args.cc,*flags,str(directory/'fixture.c'),'-o',str(binary)])
        need(p.returncode == 0 and not p.stdout and not p.stderr,'CLEAN_COMPILE: '+name)
        self.generated[binary.relative_to(self.root).as_posix()]=source.sha(binary.read_bytes())
        dsym=Path(str(binary)+'.dSYM')
        if dsym.exists():
            a='Contents/Info.plist'; b='Contents/Resources/DWARF/program.host'
            c='Contents/Resources/Relocations/aarch64/program.host.yml'
            files={p.relative_to(dsym).as_posix() for p in dsym.rglob('*') if p.is_file()}
            need(files in ({a,b},{a,c},{a,b,c}), 'DSYM_EXACT_SHAPE')
            for file in files:
                p=dsym/file; self.generated[p.relative_to(self.root).as_posix()]=source.sha(p.read_bytes())
        return binary

    def case(self, label, binary, case, marker=None, expected_override=None):
        request=self.write(label+'/request.input',case['command'])
        expected=contract.expected_trace(case) if expected_override is None else expected_override
        expected_path=self.write(label+'/trace.expected',expected)
        p=self.invoke(label+'/run',[str(binary),*contract.argv(case,request,expected_path)])
        if marker is None:
            need(p.returncode == 0 and p.stdout == expected and not p.stderr,'EXACT_POSITIVE: '+label)
        else:
            error=('TUNIP:'+marker+'\n').encode(); self.write(label+'/stderr.expected',error)
            need(p.returncode == 86 and not p.stdout and p.stderr == error,'EXACT_NEGATIVE: '+label)
        return p

    def roundtrip(self, clients):
        code,_=source.partition(clients)
        for name in code:
            self.write('roundtrip/'+name,(clients/name).read_bytes())
        tree=self.root/'roundtrip'; patch=(source.PACKAGE/'patches'/source.PATCH).read_bytes()
        command=[shutil.which('gpatch') or 'patch','--batch','--fuzz=0','-p1']
        p=self.invoke('roundtrip-reverse',command+['-R'],cwd=tree,data=patch)
        need(p.returncode == 0 and not p.stderr and not re.search(rb'offset|fuzz|FAILED|reject',p.stdout,re.I),'EXACT_REVERSE027')
        source.check_tree(tree,True)
        baseline=self.root/'baseline26'; shutil.copytree(tree,baseline)
        for name in code:
            self.generated['baseline26/'+name]=source.sha((baseline/name).read_bytes())
        p=self.invoke('roundtrip-forward',command,cwd=tree,data=patch)
        need(p.returncode == 0 and not p.stderr and not re.search(rb'offset|fuzz|FAILED|reject',p.stdout,re.I),'EXACT_FORWARD027')
        source.check_tree(tree)
        for name in code:
            self.generated['roundtrip/'+name]=source.sha((tree/name).read_bytes())
        return baseline


def canaries(run):
    original=dict(run.env); controls=[]
    for name,text,code,diagnostic,detail in (
        ('asan','#include <stdlib.h>\n__attribute__((noinline)) void store(volatile int*p,int i){p[i]=1;}\nint main(int c,char**v){volatile int*p=malloc(sizeof(int));(void)v;store(p,c);free((void*)p);return 0;}\n',97,
         b'ERROR: AddressSanitizer: heap-buffer-overflow',b'WRITE of size 4'),
        ('ubsan','#include <limits.h>\nint main(void){volatile int i=INT_MAX;return i+1;}\n',98,
         b'runtime error: signed integer overflow:',b'2147483647 + 1')):
        binary=run.compile('canary/'+name,text=text)
        env=dict(run.env, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode='+str(code),
                 UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode='+str(code)+':print_stacktrace=1')
        p=run.invoke('canary/'+name+'/run',[str(binary)],env=env)
        need(p.returncode == code and not p.stdout and diagnostic in p.stderr and detail in p.stderr,'DIRECTED_CANARY: '+name)
        controls.append({'name':name,'exitcode':code,'diagnostic':diagnostic.decode(),
                         'ASAN_OPTIONS':env['ASAN_OPTIONS'],'UBSAN_OPTIONS':env['UBSAN_OPTIONS']})
    need(run.env == original,'RESTORE_MAIN_ENV')
    return controls


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clients',required=True,type=Path); parser.add_argument('--cc',required=True)
    parser.add_argument('--sanitize',action='store_true'); parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(); args.output=args.output.resolve()
    need(not args.output.exists(),'FRESH_OUTPUT'); args.output.mkdir(parents=True)
    run=Run(args); report={'status':'INCOMPLETE','qualification':'HOST_MODEL_ONLY_NOT_TARGET_OR_FW',
                         'positives':[],'source_negatives':[],'baseline_equivalence':[],
                         'baseline_witnesses':[],'commands':run.commands}
    try:
        metadata=source.check_tree(args.clients); profile,patches=source.check_inputs()
        need(tuple(c['name'] for c in contract.CASES) == CASE_NAMES and len(set(CASE_NAMES)) == 58,'FIXED_CASE_INVENTORY')
        obligations(NEGATIVES); need(set(mutations.EDITS) == {r[0] for r in NEGATIVES},'FIXED_MUTATION_INVENTORY')
        report['inventory_controls']=inventory_controls()
        report['prepared_metadata']=metadata
        assets=[HERE,*sorted(p for p in SUPPORT.rglob('*') if p.is_file())]
        assets += [source.OLD_PROFILE,source.PACKAGE/'Makefile',
                   *sorted((source.PACKAGE/'patches').glob('*.patch')),
                   *(source.REPO/n for n in profile['helper_inputs'])]
        inputs={str(p):source.sha(p.read_bytes()) for p in assets}
        support_inventory=source.inventory(SUPPORT); tree_inventory=source.inventory(args.clients)
        report['inputs']=inputs; report['source_profile']=profile
        run.write('INPUTS.json',json.dumps(inputs,indent=2,sort_keys=True)+'\n')
        run.write('PREPARED-TREE.json',json.dumps(tree_inventory,indent=2,sort_keys=True)+'\n')
        for name,digest in patches.items():
            path=run.write('saved-patches/'+name,(source.PACKAGE/'patches'/name).read_bytes())
            need(source.sha(path.read_bytes()) == digest,'SAVED_PATCH_COPY')
        baseline=run.roundtrip(args.clients)
        bodies,types,provenance=source.render(args.clients)
        old_bodies,old_types,old_provenance=source.render(baseline,True)
        need(types == old_types,'UNCHANGED_ACTUAL_TYPES')
        report['actual_functions']=provenance; report['baseline_actual_functions']=old_provenance
        report['fixed_obligations']=NEGATIVES
        run.write('OBLIGATIONS.json',json.dumps(NEGATIVES,indent=2)+'\n')
        cases={c['name']:c for c in contract.CASES}
        binary=run.compile('positive',bodies,types,provenance)
        for name in CASE_NAMES:
            run.case('positive/'+name,binary,cases[name]); report['positives'].append(name)
        old_binary=run.compile('baseline-program',old_bodies,old_types,old_provenance)
        for name in BASELINE_EQUIVALENT:
            p=run.case('baseline-equivalent/'+name,old_binary,cases[name])
            need(p.stdout == (run.root/'positive'/name/'run.stdout').read_bytes(),'EXACT_BASELINE_SUCCESS_EQUIVALENCE')
            report['baseline_equivalence'].append(name)
        for name,marker in BASELINE_WITNESSES:
            run.case('baseline-witness/'+name,old_binary,cases[name],marker)
            report['baseline_witnesses'].append((name,marker))
        for variant,name,marker in NEGATIVES:
            mutated=run.compile('negative/'+variant,mutations.changed(bodies,variant),types,provenance)
            run.case('negative/'+variant,mutated,cases[name],marker)
            report['source_negatives'].append((variant,name,marker))
        obligations(report['source_negatives'])
        need(tuple(report['positives']) == CASE_NAMES and tuple(report['baseline_equivalence']) == BASELINE_EQUIVALENT and
             tuple(report['baseline_witnesses']) == BASELINE_WITNESSES,'COMPLETE_FIXED_CASES')
        polluted=contract.expected_trace(cases['flush']).replace(b'CALL flush 0',b'CALL flush 1',1)
        need(polluted != contract.expected_trace(cases['flush']),'ORACLE_CONTROL_DIFFERENT')
        run.case('oracle-control/wrong-recipient',binary,cases['flush'],'TRACE',polluted)
        report['oracle_control']={'rejected':1,'marker':'TRACE','classification':'TEST_EXPECTED_TRACE_POLLUTION_NOT_SOURCE_MUTANT'}
        if args.sanitize:
            report['sanitizer_controls']=canaries(run)
        need(all(source.sha(Path(p).read_bytes()) == h for p,h in inputs.items()),'END_INPUT_STABILITY')
        need(source.inventory(SUPPORT) == support_inventory,'END_SUPPORT_INVENTORY')
        need(source.inventory(args.clients) == tree_inventory,'END_PREPARED_TREE_STABILITY')
        source.check_tree(args.clients); source.check_tree(baseline,True); source.check_tree(run.root/'roundtrip')
        _,current_patches=source.check_inputs()
        need({p.name:source.sha(p.read_bytes()) for p in (run.root/'saved-patches').glob('*.patch')} == current_patches,'END_SAVED_PATCH_INVENTORY')
        observed=source.inventory(run.root); observed.pop('RESULTS.json',None)
        need(observed == run.generated,'EXACT_GENERATED_INVENTORY_AND_BYTES')
        report.update(status='PASS_HOST_TUNIP_COMMAND_CONTRACT_ONLY',positive_count=len(report['positives']),
                      source_negative_count=len(report['source_negatives']),baseline_equivalence_count=10,
                      baseline_witness_count=4,generated=run.generated,end_input_stability=True,
                      sanitize=args.sanitize,LSan='NOT_VERIFIED')
    except Exception as e:
        report['error']=str(e)
    (args.output/'RESULTS.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ('status','error','positive_count','source_negative_count') if k in report}))
    return 0 if report['status'] == 'PASS_HOST_TUNIP_COMMAND_CONTRACT_ONLY' else 1


if __name__ == '__main__':
    sys.exit(main())
