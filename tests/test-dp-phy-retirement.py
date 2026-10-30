#!/usr/bin/env python3
"""Host-only IPQ807x unregister/PHY order fixture; no target/module build."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')
PATCHES = SOURCE / 'package/qca-nss/qca-nss-dp/patches'
PATCH = '017-ipq807x-unregister-before-phy-retirement.patch'
LINUX = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2/EDMA-SSDK-DEPENDENCY-REVIEW-inputs/linux-v6.18.38/linux-phy_device.c')
LINUX_HASH = '9c45cc833de9007324fe4526c5124d8f82dbd9fee850639c580eb76b57fae5ad'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def negative(process, marker):
    return (process.returncode == 86 and not process.stdout and
            process.stderr == ('DP_PHY017 ' + marker + '\n').encode())


def positive_trace(profile):
    native = profile.startswith('v1')
    extras = profile.endswith('-ppe-switch')
    counts = {'v1': (1024, 272), 'v1-ppe-switch': (1088, 336),
              'legacy': (768, 240), 'legacy-ppe-switch': (832, 304)}
    events = []
    for bits in range(16):
        for port in range(2):
            stages = 'qcu' if native else ''
            if bits & 8:
                stages += ('s' if bits & 1 else '') + ('i' if bits & 2 else '')
                stages += 'd' + ('f' if bits & 4 else '')
            stages += 'v' if extras else ''
            stages += '' if native else 'p'
            stages += 'w' if extras else ''
            stages += 'ghx' if native else 'guhx'
            events.extend('%d:%s;' % (port, code) for code in stages)
    for bits in range(8):
        for port in range(2):
            stages = ('s' if bits & 1 else '') + ('i' if bits & 2 else '')
            stages += 'd' + ('f' if bits & 4 else '')
            events.extend('%d:%s;' % (port, code) for code in stages)
    checks, stages = counts[profile]
    require(len(events) == stages, 'independent positive stage count')
    return (''.join(events) + '\nPASS DP_PHY017 cases=24 checks=%d stages=%d\n'
            % (checks, stages)).encode()


def positive(process, expected):
    return process.returncode == 0 and not process.stderr and process.stdout == expected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--upstream-cache', type=Path, required=True)
    ap.add_argument('--gcc', default='/opt/homebrew/bin/gcc-16')
    ap.add_argument('--clang', default='/usr/bin/clang')
    args = ap.parse_args()
    out = args.output.resolve()
    require(out.parent == AUDIT and out.name.startswith('DP-PHY-') and not out.exists(), 'fresh output scope')
    paths = sorted(PATCHES.glob('*.patch'))
    require([p.name[:3] for p in paths] == ['%03d' % i for i in range(1,18)] and
            paths[-1].name == PATCH, 'explicit frozen 001-017 inventory')
    assets = [Path(__file__).resolve(), HERE/'dp-phy-retirement/fixture.c',
              HERE/'dp-phy-retirement/README.md', HERE/'test-edma-phase2-integration.py',
              HERE/'test-edma-tx-slot-ownership.py', HERE/'edma_patch_context.py',
              SOURCE/'package/qca-nss/qca-nss-dp/Makefile', LINUX, *paths]
    identities = {str(p): sha(p) for p in assets}
    require(sha(LINUX) == LINUX_HASH, 'exact Linux6.18.38 PHY source identity')
    out.mkdir()
    result = {'status':'INCOMPLETE', 'qualification':'HOST_ORDER_ONLY', 'inputs':identities,
              'profiles':[], 'mutants':[], 'limits':[
                  'Actual DP remove/helper and Linux phy_disconnect bodies; model structs and kernel/driver leaves',
                  'No Linux notifier/refwait/RTNL/PHY worker/IRQ execution or object ABI proof',
                  'Only IPQ807X order repair; not SSDK cache, non-DP legacy owner, NSS/FW or DP init rollback',
                  'No hardware/target/module/firmware/cloud build, device or performance qualification']}
    try:
        prep = load('dp_phy_prepare', HERE/'test-edma-phase2-integration.py')
        tx = load('dp_phy_extract', HERE/'test-edma-tx-slot-ownership.py')
        context = load('dp_phy_context', HERE/'edma_patch_context.py')
        require(re.search(r'^PKG_SOURCE_VERSION:=' + prep.PIN + r'\s*$',
                (SOURCE/'package/qca-nss/qca-nss-dp/Makefile').read_text(),re.M), 'exact DP recipe pin')
        roots, inputs = prep.prepare(args.upstream_cache, out, paths[:-1], identities)
        baseline = roots['after']
        candidate = out/'candidate17'
        shutil.copytree(baseline, candidate)
        expected, declared = context.inspect_patch(candidate, paths[-1].read_bytes())
        require(set(expected)=={'nss_dp_main.c'}, '017 single-file scope')
        (out/'patches'/PATCH).write_bytes(paths[-1].read_bytes())
        process = subprocess.run(['patch','-p1','--batch','--fuzz=0','-V','none'],
                                 input=paths[-1].read_bytes(), cwd=candidate, capture_output=True)
        (out/'017.stdout').write_bytes(process.stdout)
        (out/'017.stderr').write_bytes(process.stderr)
        require(process.returncode == 0 and not process.stderr and not re.search(
            rb'fuzz|offset|FAILED|reject|Reversed',process.stdout,re.I), '017 text replay')
        context.verify_applied(candidate, expected)
        base_files, new_files = prep.file_hashes(baseline), prep.file_hashes(candidate)
        require(set(base_files)==set(new_files) and [p for p in base_files
                if base_files[p]!=new_files[p]]==['nss_dp_main.c'], '017 complete-tree scope')
        result['017_context'] = declared
        old = (baseline/'nss_dp_main.c').read_text()
        new = (candidate/'nss_dp_main.c').read_text()
        names = ['nss_dp_phy_disconnect','nss_dp_remove']
        before = {n:tx.definition(old,n)[0] for n in names}
        after = {n:tx.definition(new,n)[0] for n in names}
        require(before['nss_dp_phy_disconnect'] == after['nss_dp_phy_disconnect'], 'PHY helper changed')
        require(tx.outside_functions(old,['nss_dp_remove']) ==
                tx.outside_functions(new,['nss_dp_remove']), '017 tokens outside remove')
        linux = tx.definition(LINUX.read_text(),'phy_disconnect')[0]
        for name, code in {**after,'linux_phy_disconnect':linux}.items():
            (out/(name+'.c.txt')).write_text(code+'\n')
        template = (HERE/'dp-phy-retirement/fixture.c').read_text()
        def fixture(functions):
            return template.replace('/* @functions@ */',linux+'\n'+functions['nss_dp_phy_disconnect']+
                                    '\n'+functions['nss_dp_remove'])
        prepared = {str(root):prep.file_hashes(root) for root in [*roots.values(),candidate]}
        write(out/'PREPARED.json',prepared)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1', LC_ALL='C')
        def execute(command, stem):
            p = subprocess.run([str(x) for x in command],capture_output=True,env=env,timeout=90)
            (out/(stem+'.stdout')).write_bytes(p.stdout)
            (out/(stem+'.stderr')).write_bytes(p.stderr)
            write(out/(stem+'.json'),{'argv':[str(x) for x in command], 'returncode':p.returncode})
            return p
        flags = ['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
                 '-Wno-unused-function','-Wno-unused-parameter']
        traces = {}
        generated = {}
        for label, compiler, extra in [('gcc',args.gcc,[]),('clang',args.clang,
                ['-fsanitize=address,undefined','-fno-omit-frame-pointer'])]:
            require(shutil.which(compiler), 'compiler missing')
            version = execute([compiler,'--version'],label+'-version')
            require(version.returncode==0 and not version.stderr, 'compiler version')
            result.setdefault('compilers',{})[label]=version.stdout.decode().splitlines()[0]
            def build(code,defines,stem):
                cfile=out/(stem+'.c'); cfile.write_text(code)
                generated[str(cfile)]=sha(cfile)
                binary=out/stem
                p=execute([compiler,*flags,*extra,*defines,cfile,'-o',binary],stem+'-compile')
                require(p.returncode==0 and not p.stdout and not p.stderr,'compile not runtime acceptance: '+stem)
                return binary
            for profile, defines in [('v1', ['-DNSS_DP_IPQ807X']),('v1-ppe-switch',
                    ['-DNSS_DP_IPQ807X','-DNSS_DP_PPE_SUPPORT','-DCONFIG_NET_SWITCHDEV']),
                    ('legacy',[]),('legacy-ppe-switch',['-DNSS_DP_PPE_SUPPORT','-DCONFIG_NET_SWITCHDEV'])]:
                stem=label+'-'+profile
                binary=build(fixture(after),defines,stem)
                p=execute([binary],stem+'-run')
                require(positive(p, positive_trace(profile)),
                        'candidate exact complete runtime trace '+stem)
                if label=='gcc': traces[profile]=p.stdout
                else: require(p.stdout==traces[profile],'cross-compiler ledger drift')
                result['profiles'].append({'compiler':label,'profile':profile,
                    'summary':p.stdout.decode().splitlines()[-1], 'c_sha256':sha(out/(stem+'.c'))})
                basebin=build(fixture(before),defines,stem+'-old')
                oldp=execute([basebin],stem+'-old-run')
                if profile.startswith('v1'):
                    require(negative(oldp,'registered-detach'),'old source exact lifetime counterexample')
                else:
                    require(oldp.returncode==0 and not oldp.stderr and oldp.stdout==p.stdout,
                            'nonIPQ807x behavior changed')
            functions = dict(after)
            call = '\t\tunregister_netdev(dp_priv->netdev);'
            require(after['nss_dp_remove'].count(call)==2, 'exact profile-specific unregister calls')
            variants = [('old-remove',before['nss_dp_remove'],None,'registered-detach'),
                ('duplicate-unregister',after['nss_dp_remove'].replace(call,call+'\n'+call,1),
                    None,'unregister-once'),
                ('plain-detach',None,tx.once(after['nss_dp_phy_disconnect'],
                    'phy_disconnect(dp_priv->phydev);','phy_detach(dp_priv->phydev);'),'complete-disconnect'),
                ('missing-fixed-put',None,tx.once(after['nss_dp_phy_disconnect'],
                    'of_phy_deregister_fixed_link(np);','(void)np;'),'fixed-ledger')]
            for name, remove, helper, marker in variants:
                changed=dict(functions)
                if remove is not None: changed['nss_dp_remove']=remove
                if helper is not None: changed['nss_dp_phy_disconnect']=helper
                binary=build(fixture(changed),['-DNSS_DP_IPQ807X'],label+'-'+name)
                p=execute([binary],label+'-'+name+'-run')
                require(negative(p,marker),'not exact semantic failure '+name)
                result['mutants'].append({'compiler':label,'name':name,'marker':marker})
            binary=out/(label+'-v1')
            p=execute([binary,'semantic-canary'],label+'-semantic-canary')
            require(negative(p,'semantic-canary'),'semantic canary')
            p=execute([binary,'nonsemantic-canary'],label+'-nonsemantic-canary')
            require(p.returncode==97 and not p.stdout and not p.stderr and not negative(p,'semantic-canary'),
                    'nonsemantic anomaly must not qualify')
        marker='semantic-canary'
        valid=subprocess.CompletedProcess([],86,b'',b'DP_PHY017 semantic-canary\n')
        require(negative(valid,marker),'valid oracle control')
        for code, stdout, stderr in [(0,b'',valid.stderr),(97,b'',valid.stderr),
                (-6,b'',valid.stderr),(86,b'noise',valid.stderr),
                (86,b'',valid.stderr+b'extra\n'),(86,b'',b'DP_PHY017 wrong\n')]:
            require(not negative(subprocess.CompletedProcess([],code,stdout,stderr),marker),
                    'oracle pollution accepted')
        result['pure_oracle_controls']={'valid':1,'rejected':6}
        for profile in ['v1', 'v1-ppe-switch', 'legacy', 'legacy-ppe-switch']:
            expected = positive_trace(profile)
            require(positive(subprocess.CompletedProcess([], 0, expected, b''), expected),
                    'valid positive oracle control')
            for code, stdout, stderr in [(86, expected, b''), (-6, expected, b''),
                    (0, b'noise\n' + expected, b''), (0, expected + b'extra\n', b''),
                    (0, b'9' + expected[1:], b''), (0, expected, b'warning\n')]:
                require(not positive(subprocess.CompletedProcess([], code, stdout, stderr), expected),
                        'positive oracle pollution accepted')
        result['positive_oracle_controls']={'valid':4,'rejected':24,
            'scope':'Exact independent ordered trace and summary bytes; pure data controls, not driver cases'}
        require(paths == sorted(PATCHES.glob('*.patch')), 'final patch inventory drift')
        require(identities == {str(p):sha(p) for p in assets}, 'final input drift')
        require(prepared == {str(root):prep.file_hashes(root) for root in [*roots.values(),candidate]},
                'prepared tree drift')
        require(sha(out/'upstream.tar')==inputs['git_archive_sha256'],'saved archive drift')
        for path in paths:
            require(sha(out/'patches'/path.name)==identities[str(path)],'saved patch drift')
        require(generated=={p:sha(Path(p)) for p in generated},'generated C drift')
        result['generated_c']=generated
        result['status']='PASS_HOST_ORDER_ONLY'
    except Exception as error:
        result['failure']=str(error)
        raise
    finally:
        write(out/'RESULTS.json',result)
    print(json.dumps({'status':result['status'],'profiles':result['profiles'],
                      'semantic_mutants':len(result['mutants'])}))


if __name__ == '__main__':
    main()
