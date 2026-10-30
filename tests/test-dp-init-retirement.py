#!/usr/bin/env python3
"""Fresh host-only actual DP018/SSDK030 composition, never a target build."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FIX = HERE / 'dp-init-retirement'
spec = importlib.util.spec_from_file_location('dp_init_source', FIX / 'source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
sys.modules['source'] = source
mspec = importlib.util.spec_from_file_location('dp_init_mutations', FIX/'mutations.py')
mutations = importlib.util.module_from_spec(mspec);mspec.loader.exec_module(mutations)
require, sha = source.require, source.sha
ROOT = HERE.parent
AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')
DP = ROOT / 'package/qca-nss/qca-nss-dp/patches'
SSDK = ROOT / 'package/qca-nss/qca-ssdk/patches'
FROZEN018 = 'c9f6f83ff7277379fed402ddf07bd3726df2d2e3e7f9281233480358f04c740c'
FROZEN030 = 'd99c275b58d73910108e1cd92c07ac07dd27dcc6b0530f5fac6b18ce933b066f'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def expected(case, switchdev):
    s = ['Sb+', 'Sa+'] if switchdev else []
    n = ['N+'] if switchdev else []
    tail = ['N-', 'Sa-', 'Sb-'] if switchdev else []
    count = 0 if case in {'zero','g3-missing','property-domain','atomic-drain','blocking-drain','blocking-fail-N'} else 2 if case in {'two','two-actor'} else 1
    early = case in {'ready-false','fail-1','fail-2','fail-3','fail-4','fail-9'}
    if early: count=0
    if case == 'ready-false':
        trace = []
    elif case == 'fail-1':
        trace = ['H+']
    elif case == 'fail-2':
        trace = ['H+', 'Sb+', 'H-']
    elif case == 'fail-3':
        trace = ['H+', 'Sb+', 'Sa+', 'Sb-', 'H-']
    elif case == 'fail-4':
        trace = ['H+'] + s + n + ['P+'] + tail + ['H-']
    elif case == 'fail-9':
        trace = ['H+'] + s + n + ['Sa-', 'Sb-', 'H-']
    elif case == 'blocking-fail-N':
        trace = ['H+'] + s + n + ['callback','Sa-','rtnl-wait','release','callback-exit','Sb-','H-']
    else:
        trace = ['H+'] + s + n + ['P+']
        for port in range(count):
            if case == 'mark-false':
                trace += ['alloc', 'free']
            elif case == 'fail-5':
                trace += ['alloc', 'gmac+', 'retire', 'free']
            elif case in {'fail-6', 'fail-7'}:
                trace += ['alloc', 'gmac+', 'plane+', 'retire', 'gmac-', 'free']
            elif case == 'fail-8':
                trace += ['alloc', 'gmac+', 'plane+', 'phy+', 'retire', 'phy-', 'gmac-', 'free']
            else:
                trace += ['alloc', 'gmac+', 'plane+']
                if case!='g3-no-phy': trace += ['phy+']
                trace += ['vsi+', 'register']
                if case in {'actor','late-P','two-actor'}:
                    trace += ['actor','filter+'] + (['etype+'] if port==0 else []) + ['stp']
                if case in {'prelist','veto','veto-reader'}:
                    if case=='veto-reader': trace += ['reader']
                    if case!='prelist':
                        trace += ['unlist']
                        if case=='veto-reader': trace += ['wait','release','reader-put']
                        trace += ['refwait']
                    trace += ['retire','phy-','gmac-','free']
        if case=='g3-reader': trace += ['reader']
        if case in {'atomic-drain','blocking-drain'}: trace += ['callback']
        trace += ['core-comp' if case=='late-P' else 'P-']
        if case not in {'mark-false', 'fail-5', 'fail-6', 'fail-7', 'fail-8','prelist','veto','veto-reader'}:
            for port in range(count):
                trace += ['quarantine']
                if case in {'actor','late-P','two-actor'}:
                    trace += ['filter-'] + (['etype-'] if port==count-1 else []) + ['stp','fdb']
                trace += ['unlist']
                if case=='g3-reader': trace += ['wait','release','reader-put']
                trace += ['refwait']
                if case!='g3-no-phy': trace += ['phy-']
                trace += ['vsi-','gmac-','free']
        if case=='atomic-drain': trace += ['N-','Sa-wait','release','callback-exit','Sa-','Sb-','H-']
        elif case=='blocking-drain': trace += ['rtnl-wait','release','callback-exit'] + tail + ['H-']
        else: trace += tail + ['H-']
    errors = count if case in {'mark-false','fail-5','fail-6','fail-7','fail-8','prelist','veto','veto-reader'} else 0
    attaches = 0 if case in {'mark-false','fail-5','fail-6','fail-7','g3-no-phy'} else count
    holds = 0 if case in {'mark-false','fail-5','fail-6','fail-7','fail-8','prelist'} else count
    if case in {'g3-reader','g3-zero','g3-unmapped','g3-no-phy','veto-reader'}: holds+=1
    maps = int(case in {'g3-reader','g3-zero','g3-unmapped','veto-reader'})
    summary = '\nPASS DP_INIT alloc=%d free=%d attach=%d detach=%d errors=%d holds=%d puts=%d maps=%d\n' % (
        count,count,attaches,attaches,errors,holds,holds,maps)
    return ((' '.join(trace) + ' ') if trace else '').encode() + summary.encode()


def positive(p, wanted):
    return p.returncode == 0 and not p.stderr and p.stdout == wanted


def negative(p, marker):
    return p.returncode == 86 and not p.stdout and p.stderr == ('DP_INIT ' + marker + '\n').encode()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--compiler', default='/opt/homebrew/bin/gcc-16')
    ap.add_argument('--sanitizers', action='store_true')
    ap.add_argument('--matrix', choices=['smoke', 'stages', 'joint', 'bounded'], default='smoke')
    args = ap.parse_args()
    full_scaffolding=args.matrix in {'joint','bounded'}
    out = args.output.resolve()
    require(out.parent == AUDIT and out.name.startswith('DP-INIT-ADOPT-') and not out.exists(), 'fresh output scope')
    dp_base = AUDIT / 'DP-PHY-parent-r3/candidate17'
    ssdk_tree = AUDIT / 'SSDK-CACHE-ADOPT-gcc-r7/source/prepared'
    patches = sorted(DP.glob('*.patch'))
    require([p.name[:3] for p in patches] == ['%03d' % i for i in range(1, 19)], '001-018 selected inventory')
    ssdk_patches = sorted(SSDK.glob('*.patch'))
    require(sha(patches[-1].read_bytes()) == FROZEN018, '018 source drift')
    require(sha((SSDK / '030-ssdk-netdev-cache-retirement.patch').read_bytes()) == FROZEN030, '030 source drift')
    assets = [Path(__file__).resolve(), FIX/'source.py', FIX/'mutations.py', FIX/'fixture.c',
              FIX/'header-shim.h', FIX/'README.md',
              HERE/'edma_patch_context.py', ROOT/'package/qca-nss/qca-ssdk/Makefile',
              ROOT/'package/qca-nss/qca-nss-dp/Makefile',
              AUDIT/'DP-INIT-ADOPT-VSI-MODEL-CONTRACT-r2.json',
              AUDIT/'DP-INIT-VSI-ORACLE-CONTRACT-REVIEW.json',
              AUDIT/'DP-INIT-REVIEW-VSI-OWNERSHIP-BOUNDARY.json', *patches, *ssdk_patches]
    dp_expected, ssdk_expected, receipt_inputs, recipe_metadata = source.receipt_chain(ROOT, AUDIT, dp_base, ssdk_tree)
    assets = list(dict.fromkeys(assets + receipt_inputs))
    identities = {str(p): sha(p.read_bytes()) for p in assets}
    trees = {str(p): source.tree_hashes(p) for p in [dp_base, ssdk_tree]}
    ssdk_result = ssdk_tree.parent/'RESULTS.json'
    ssdk_metadata = json.loads(ssdk_result.read_text())
    require(trees[str(ssdk_tree)] == ssdk_metadata['prepared_files'], 'SSDK full prepared binding')
    out.mkdir()
    result = {'status':'INCOMPLETE', 'scope':'WIP_NATIVE_HOST_COMPOSITION',
              'source018':FROZEN018, 'source030':FROZEN030, 'runs':[], 'mutants':[],
              'recipe_metadata':recipe_metadata,
              'vsi_contract':'Fresh successful SDK default prestate/no concurrent FAL writer; HW binding, software mapping and call ledger separate; no transfer/restore generalization',
              'remaining':'Author host qualification only; independent acceptance and external boundaries remain OPEN'}
    save(out/'INPUTS.json', {'live_inputs':identities, 'trees':trees,
                            'expected_origin':'Exact bound pin/archive/patch/recipe/helper receipts; not self-recorded tree identity',
                            'derived_DP17':dp_expected,'derived_SSDK18':ssdk_expected,
                            'recipe_metadata':recipe_metadata,
                            'ssdk_result_sha256':sha(ssdk_result.read_bytes())})
    generated, header_trees = {}, {}
    try:
        ctxspec = importlib.util.spec_from_file_location('dp_init_context', HERE/'edma_patch_context.py')
        context = importlib.util.module_from_spec(ctxspec);ctxspec.loader.exec_module(context)
        candidate = out/'candidate18'
        shutil.copytree(dp_base, candidate)
        outputs, report = context.inspect_patch(dp_base, patches[-1].read_bytes())
        require(set(outputs)=={'include/nss_dp_dev.h','nss_dp_main.c','nss_dp_switchdev.c'}, '018 bounded source files')
        for rel, data in outputs.items(): (candidate/rel).write_bytes(data)
        context.verify_applied(candidate, outputs)
        derived = dict(dp_expected)
        derived.update({rel:sha(data) for rel,data in outputs.items()})
        require(source.tree_hashes(candidate)==derived, '018 complete derived output tree')
        save(out/'DERIVED18.json',derived)
        save(out/'CONTEXT.json', report)
        bodies, types, globals_, public, records = source.extract(candidate, ssdk_tree, out/'actual')
        code = source.render((FIX/'fixture.c').read_text(), bodies, types, globals_, public)
        cfile = out/'candidate.c';cfile.write_text(code);generated[str(cfile)] = sha(cfile.read_bytes())
        env = dict(os.environ, LC_ALL='C')
        if args.sanitizers:
            env.update(ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:exitcode=97',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1:exitcode=97:abort_on_error=0')
            env['ASAN_OPTIONS'] += ':abort_on_error=0'
        result['runtime_environment'] = {k:env.get(k) for k in ['LC_ALL','ASAN_OPTIONS','UBSAN_OPTIONS']}
        result['lsan'] = 'Not qualified; disabled on the sanitizer profile on this host'

        def run(argv, name, run_env=None):
            argv = [str(v) for v in argv]
            actual_env=env if run_env is None else run_env
            try:
                p = subprocess.run(argv, capture_output=True, env=actual_env, timeout=60)
            except subprocess.TimeoutExpired as exc:
                (out/(name+'.stdout')).write_bytes(exc.stdout or b'')
                (out/(name+'.stderr')).write_bytes(exc.stderr or b'')
                save(out/(name+'.json'), {'argv':argv,'returncode':'timeout'})
                raise RuntimeError('timeout is not semantic success: '+name) from exc
            (out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr)
            save(out/(name+'.json'), {'argv':argv,'returncode':p.returncode,
                'runtime_environment':{k:actual_env.get(k) for k in ['LC_ALL','ASAN_OPTIONS','UBSAN_OPTIONS']}})
            return p

        flags = ['-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror',
                 '-Wno-unused-function','-Wno-unused-parameter']
        if args.sanitizers: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
        compiler = shutil.which(args.compiler)
        require(compiler is not None, 'host compiler missing')
        version = run([compiler,'--version'],'compiler-version')
        require(version.returncode==0 and not version.stderr, 'compiler version')
        result['compiler'] = version.stdout.decode().splitlines()[0]
        if full_scaffolding:
            result['nonselected_CPP_preservation']=[]
            for label,kernel,defines in [
                ('no-ppe',(6<<16)|(18<<8)|38,['NSS_DP_IPQ807X','CONFIG_NET_SWITCHDEV']),
                ('swbr',(6<<16)|(18<<8)|38,['NSS_DP_IPQ807X','NSS_DP_PPE_SUPPORT','NSS_DP_SW_BR_OPS','CONFIG_NET_SWITCHDEV']),
                ('foreign',(6<<16)|(18<<8)|38,['NSS_DP_PPE_SUPPORT','CONFIG_NET_SWITCHDEV']),
                ('old-kernel',(5<<16)|(15<<8),['NSS_DP_IPQ807X','NSS_DP_PPE_SUPPORT','CONFIG_NET_SWITCHDEV'])]:
                projections=[]
                for stage,root in [('before',dp_base),('after',candidate)]:
                    path=out/('preserve-'+label+'-'+stage+'.c')
                    path.write_text(source.preservation_input(root,kernel,defines));generated[str(path)]=sha(path.read_bytes())
                    p=run([compiler,'-E','-P','-x','c',path], 'preserve-'+label+'-'+stage)
                    require(p.returncode==0 and not p.stderr,'nonselected source CPP')
                    projections.append(source.preserved_tokens(p.stdout.decode()))
                require(projections[0]==projections[1], 'nonselected tokens/order changed: '+label)
                result['nonselected_CPP_preservation'].append(label)
        if args.sanitizers:
            canaries={
                'asan':('#include <stdlib.h>\nint main(void) { volatile char *p=malloc(8); volatile int i=8; p[i]=1; free((void *)p); return 0; }\n',97,b'AddressSanitizer'),
                'ubsan':('#include <limits.h>\nint main(void) { volatile int n=INT_MAX; return n+1; }\n',98,b'runtime error:')}
            result['sanitizer_canaries']=[]
            for label,(text,exitcode,diagnostic) in canaries.items():
                path=out/(label+'-canary.c');path.write_text(text);generated[str(path)]=sha(path.read_bytes())
                binary=out/(label+'-canary')
                p=run([compiler,*flags,path,'-o',binary],label+'-canary-compile')
                require(p.returncode==0 and not p.stdout and not p.stderr,'sanitizer canary compile')
                canary_env=dict(env)
                for key in ['ASAN_OPTIONS','UBSAN_OPTIONS']:
                    canary_env[key]=canary_env[key].replace('exitcode=97','exitcode='+str(exitcode))
                p=run([binary],label+'-canary-run',canary_env)
                require(p.returncode==exitcode and not p.stdout and diagnostic in p.stderr,'sanitizer halt/code canary')
                result['sanitizer_canaries'].append({'name':label,'exitcode':exitcode,'semantic_negative':False,
                    'runtime_environment':{k:canary_env[k] for k in ['ASAN_OPTIONS','UBSAN_OPTIONS']}})
        if full_scaffolding:
            installed, os_headers, consumer = source.installed_header_consumer(
                candidate, ssdk_tree, out, FIX/'header-shim.h')
            header_trees = {str(p):source.tree_hashes(p) for p in [installed,os_headers]}
            generated[str(consumer)] = sha(consumer.read_bytes())
            result['public_header_consumers'] = []
            for sw in [False,True]:
                for mac in [False,True]:
                    stem='header-sw%d-mac%d' % (sw,mac)
                    hdr_flags=['-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function',
                        '-Wno-unused-parameter','-DKVER32','-DLNX26_22','-D__KERNEL__',
                        '-DNSS_DP_IPQ807X','-DNSS_DP_PPE_SUPPORT',
                        '-include',FIX/'header-shim.h','-I',os_headers,'-I',installed]
                    if sw:hdr_flags+=['-DCONFIG_NET_SWITCHDEV']
                    if mac:hdr_flags+=['-DNSS_DP_MAC_POLL_SUPPORT']
                    p=run([compiler,*hdr_flags,'-fsyntax-only',consumer],stem+'-compile')
                    require(p.returncode==0 and not p.stdout and not p.stderr,'full installed header: '+stem)
                    p=run([compiler,*hdr_flags,'-E','-P',consumer],stem+'-cpp')
                    require(p.returncode==0 and not p.stderr and b'ssdk_netdev_cache_mark_native_port' in p.stdout,
                            'actual header CPP: '+stem)
                    result['public_header_consumers'].append(stem)
            result['header_gate_controls']=[]
            no_mac_flags=[f for f in hdr_flags if f!='-DNSS_DP_MAC_POLL_SUPPORT']
            header=installed/'init/ssdk_init.h';original=header.read_bytes()
            require(original.count(b'bool ssdk_netdev_cache_ready(void);')==1,'header control anchor')
            try:
                header.write_bytes(original.replace(b'bool ssdk_netdev_cache_ready(void);',b'',1))
                p=run([compiler,*no_mac_flags,'-fsyntax-only',consumer],'header-missing-declaration')
                require(p.returncode!=0 and not p.stdout and b'ssdk_netdev_cache_ready' in p.stderr
                        and b'undeclared' in p.stderr,'missing actual declaration must reject')
            finally:header.write_bytes(original)
            result['header_gate_controls'].append({'name':'missing-declaration','expected_compile_rejection':True,
                                                  'runtime_negative_credit':False})
            text=consumer.read_text();prefix=text[:text.index('#include <ref/ref_vsi.h>')]
            guard_only=prefix+'''\n#ifndef NSS_DP_NATIVE_INIT_STAGES
#error selected guard missing
#endif
_Static_assert(__builtin_types_compatible_p(__typeof__(&ssdk_netdev_cache_ready),bool (*)(void)),"ready");
bool guard_only(void) { return ssdk_netdev_cache_ready(); }\n'''
            guard=out/'header-guard-only.c';guard.write_text(guard_only);generated[str(guard)]=sha(guard.read_bytes())
            p=run([compiler,*no_mac_flags,'-fsyntax-only',guard],'header-guard-only-valid')
            require(p.returncode==0 and not p.stdout and not p.stderr,'valid isolated guard consumer')
            first=guard_only[:guard_only.index('#endif')+len('#endif')]
            bad=source.once(guard_only,first,'#if defined(NSS_DP_MAC_POLL_SUPPORT)\n#include <init/ssdk_init.h>\n#endif')
            path=out/'header-mac-only.c';path.write_text(bad);generated[str(path)]=sha(path.read_bytes())
            p=run([compiler,*no_mac_flags,'-fsyntax-only',path],'header-mac-only-reject')
            require(p.returncode!=0 and not p.stdout and b'ssdk_netdev_cache_ready' in p.stderr
                    and b'undeclared' in p.stderr,'MAC-only guard must reject selected no-MAC')
            result['header_gate_controls'].append({'name':'MAC-only-include','expected_compile_rejection':True,
                                                  'runtime_negative_credit':False})
            require(header_trees=={str(p):source.tree_hashes(p) for p in [installed,os_headers]},'staged headers drift')
        profiles = [(True,False)] if args.matrix=='smoke' else [
            (sw,small) for sw in [False,True] for small in ([False,True] if full_scaffolding else [False])]
        for sw,small in profiles:
            name = ('sw-on' if sw else 'sw-off') + ('-small' if small else '-global')
            defines = ['-DCONFIG_NET_SWITCHDEV'] if sw else []
            if small:defines+=['-DCONFIG_DEBUG_NET_SMALL_RTNL']
            binary = out/name
            p = run([compiler,*flags,*defines,cfile,'-o',binary],name+'-compile')
            require(p.returncode==0 and not p.stdout and not p.stderr, 'compile failed, no runtime credit: '+name)
            cases = ['normal','mark-false'] if args.matrix=='smoke' else [
                'normal','zero','two','mdio','mark-false','ready-false','fail-1','fail-4',
                'fail-5','fail-6','fail-7','fail-8'] + (['fail-2','fail-3','fail-9'] if sw else [])
            if full_scaffolding:
                cases += ['prelist','veto','veto-reader','g3-reader','g3-zero','g3-unmapped','g3-no-phy',
                          'g3-missing','property-domain']
                if sw: cases += ['actor','two-actor','late-P','atomic-drain','blocking-drain','blocking-fail-N']
            if args.matrix=='bounded':
                cases=[case for case in cases if case not in {'prelist','veto','veto-reader'}]
                result['blocked_positive_cases']={case:'SUBSET_EXCLUDED_NOT_PASSED_IN_THIS_RUN'
                    for case in ['prelist','veto','veto-reader']}
            for case in cases:
                p = run([binary,case],name+'-'+case)
                require(positive(p,expected(case,sw)), 'exact case oracle: '+name+'/'+case)
                result['runs'].append({'profile':name,'case':case,'exact_trace':expected(case,sw).decode()})
        if full_scaffolding:
            for label, changed, case, marker in mutations.variants(bodies):
                c=out/(label+'.c');c.write_text(source.render((FIX/'fixture.c').read_text(),changed,types,globals_,public))
                generated[str(c)]=sha(c.read_bytes());binary=out/label
                p=run([compiler,*flags,'-DCONFIG_NET_SWITCHDEV',c,'-o',binary],label+'-compile')
                require(p.returncode==0 and not p.stdout and not p.stderr,'mutant must compile: '+label)
                p=run([binary,case],label+'-run')
                require(negative(p,marker),'exact semantic negative: '+label)
                result['mutants'].append({'name':label,'case':case,'marker':marker})
            result['framework_model_controls']=[]
            template=(FIX/'fixture.c').read_text()
            for label,old,new,case in [
                ('model-no-atomic-drain',
                 'while(atomic_readers) { blocked("Sa-wait");pthread_cond_wait(&atomic_cond,&atomic_mutex); }',
                 '(void)atomic_readers;', 'atomic-drain'),
                ('model-no-blocking-lock',
                 'rtnl_lock();blocking_live=false;registered_sb=NULL;rtnl_unlock();',
                 'blocking_live=false;registered_sb=NULL;', 'blocking-fail-N')]:
                changed=source.once(template,old,new)
                path=out/(label+'.c');path.write_text(source.render(changed,bodies,types,globals_,public))
                generated[str(path)]=sha(path.read_bytes());binary=out/label
                p=run([compiler,*flags,'-DCONFIG_NET_SWITCHDEV',path,'-o',binary],label+'-compile')
                require(p.returncode==0 and not p.stdout and not p.stderr,'model control compile')
                p=run([binary,case],label+'-run')
                require(negative(p,'callback-drain'),'model drain control runtime')
                result['framework_model_controls'].append({'name':label,'case':case,'marker':'callback-drain'})
        valid_negative=subprocess.CompletedProcess([],86,b'',b'DP_INIT example\n')
        valid_positive=subprocess.CompletedProcess([],0,expected('normal',True),b'')
        require(negative(valid_negative,'example') and positive(valid_positive,expected('normal',True)),'valid acceptance controls')
        rejected=0
        for code,out_,err in [(0,b'',valid_negative.stderr),(97,b'',valid_negative.stderr),
                (98,b'',valid_negative.stderr),(-6,b'',valid_negative.stderr),
                (86,b'noise',valid_negative.stderr),(86,b'',valid_negative.stderr+b'extra\n'),
                (86,b'',valid_negative.stderr*2),(86,b'',b'DP_INIT wrong\n'),
                (86,b'',valid_negative.stderr+b'AddressSanitizer\n')]:
            require(not negative(subprocess.CompletedProcess([],code,out_,err),'example'),'negative oracle pollution');rejected+=1
        wanted=expected('normal',True)
        for code,out_,err in [(86,wanted,b''),(97,wanted,b''),(98,wanted,b''),
                (0,wanted+b'extra\n',b''),(0,b'noise\n'+wanted,b''),(0,wanted,b'warning\n'),
                (0,wanted[:-1],b''),(0,wanted.replace(b'holds=1',b'holds=2'),b'')]:
            require(not positive(subprocess.CompletedProcess([],code,out_,err),wanted),'positive oracle pollution');rejected+=1
        result['pure_gate_controls']={'valid':2,'rejected':rejected,'driver_cases':False}
        recipe_valid=recipe_rejected=0
        for path,record in recipe_metadata.items():
            original=Path(path).read_bytes()
            baseline=original.replace(b'PKG_RELEASE:=9\n',b'PKG_RELEASE:=8\n',1)
            upgraded=baseline.replace(b'PKG_RELEASE:=8\n',b'PKG_RELEASE:=9\n',1)
            source.recipe_binding(baseline,record['baseline_sha256'])
            source.recipe_binding(upgraded,record['baseline_sha256']);recipe_valid+=2
            for bad,tag in [
                (upgraded.replace(b'PKG_RELEASE:=9\n',b'PKG_RELEASE:=10\n'), 'recipe delta must be single8-to9 release line'),
                (upgraded+b'PKG_RELEASE:=9\n', 'recipe delta must be single8-to9 release line'),
                (upgraded+b'# noise\n', 'recipe bytes outside allowed release delta'),
                (upgraded.replace(b'PKG_SOURCE_VERSION:=',b'PKG_SOURCE_VERSION:=0',1), 'recipe bytes outside allowed release delta')]:
                try: source.recipe_binding(bad,record['baseline_sha256'])
                except RuntimeError as exc: require(str(exc)==tag,'recipe control wrong gate')
                else: raise RuntimeError('recipe pollution accepted')
                recipe_rejected+=1
        result['recipe_delta_controls']={'valid':recipe_valid,'rejected':recipe_rejected,'driver_cases':False}
        require(patches == sorted(DP.glob('*.patch')) and ssdk_patches == sorted(SSDK.glob('*.patch')), 'final inventory drift')
        require(identities == {str(p):sha(p.read_bytes()) for p in assets}, 'live input drift')
        require(trees == {str(p):source.tree_hashes(p) for p in [dp_base, ssdk_tree]}, 'source tree drift')
        require(all(sha(Path(p).read_bytes())==h for p,h in generated.items()), 'generated C drift')
        context.verify_applied(candidate, outputs)
        require(source.tree_hashes(candidate)==derived, 'final complete derived output tree')
        require(header_trees=={p:source.tree_hashes(Path(p)) for p in header_trees},'final staged headers drift')
        result['functions'] = records
        result['status'] = {'smoke':'PASS_WIP_SMOKE_ONLY','stages':'PASS_WIP_STAGE_MATRIX_ONLY',
                            'joint':'HOST_MODEL_ONLY',
                            'bounded':'PASS_SUBSET_HOST_ONLY_NOT_FINAL'}[args.matrix]
        result['outcome']='PASS'
    except Exception as exc:
        result['status']='FAIL';result['outcome']='FAIL';result['error']=str(exc);raise
    finally:
        save(out/'RESULTS.json',result)
    print(json.dumps({'status':result['status'],'runs':len(result['runs']), 'output':str(out)}))


if __name__=='__main__':
    main()
