#!/usr/bin/env python3
"""Fresh 001-015 CPU lifetime extraction; TX integration is independent."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

SOURCE = Path(__file__).resolve().parents[1]
REL = Path('hal/dp_ops/edma_dp/edma_v1')
PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
PATCH = '015-edma-v1-retire-probe-and-host-napi-owners.patch'
TEMPLATE = SOURCE / 'tests/edma-probe-lifetime/fixture.c'
TX_RUNNER = SOURCE / 'tests/test-edma-tx-slot-ownership.py'
spec = importlib.util.spec_from_file_location('edma_current_tx_helpers', TX_RUNNER)
tx = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(tx)
require, sha, run, once = tx.require, tx.sha, tx.run, tx.once
NAMES = {
    str(REL / 'edma_data_plane.c'): [
        'edma_disable_interrupts','edma_enable_interrupts','edma_disable_port','edma_init',
        'edma_free_irqs','edma_stop_napi','edma_release_mmio','edma_cleanup_locked','edma_cleanup',
        'edma_close_member','edma_retire_port','edma_if_open','edma_if_close','edma_if_deinit',
        'edma_irq_init','edma_register_netdevice','edma_if_init'],
    str(REL / 'edma_tx_rx.c'): ['edma_napi','edma_handle_irq','edma_handle_misc_irq'],
    'nss_dp_main.c': ['nss_dp_clear_host_ctx','nss_dp_abort_host_probe','nss_dp_probe',
                      'nss_dp_phy_disconnect','nss_dp_close_data_plane','nss_dp_open_data_plane',
                      'nss_dp_activate_data_plane','nss_dp_close','nss_dp_open','nss_dp_remove'],
    'nss_dp_attach.c': ['nss_dp_reset_netdev_features','nss_dp_plane_init','nss_dp_plane_get',
                       'nss_dp_plane_put','nss_dp_plane_is_quarantined','nss_dp_plane_stop_phy',
                       'nss_dp_plane_quiesce','nss_dp_plane_quarantine','nss_dp_plane_resume',
                       'nss_dp_override_data_plane'],
}


def definition(text, name):
    clean = tx.mask(text)
    matches = list(re.finditer(r'^(?:static (?:inline )?)?(?:int32_t|int|bool|void|uint32_t|irqreturn_t) ' + re.escape(name) + r'\([^;{}]*\)\s*\{', clean, re.M))
    require(len(matches) == 1, 'ambiguous lifetime definition ' + name)
    m = matches[0]; end = m.end(); depth = 1
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}'); end += 1
    require(depth == 0, 'unterminated ' + name)
    return text[m.start():end], text[:m.start()].count('\n') + 1


def prepare(cache, output):
    archive = subprocess.run(['git','-C',str(cache),'archive',PIN], check=True, capture_output=True).stdout
    manifest = {'pin':PIN,'archive_sha256':sha(archive),'patches':[],'method':'new archive and patch data; no archived programs'}
    root = output / 'prepared'; root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tar.getmembers()), 'archive paths')
        tar.extractall(root)
    patches = sorted((SOURCE / 'package/qca-nss/qca-nss-dp/patches').glob('*.patch'))
    selected = [p for p in patches if p.name[:3].isdigit() and int(p.name[:3])<=15]
    require(len(selected)==15 and selected[-1].name==PATCH, 'exact 001-015 required')
    before = {}
    for p in selected:
        if p.name == PATCH:
            before = {str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
        data=p.read_bytes(); saved=output / p.name; saved.write_bytes(data)
        result=subprocess.run(['/usr/bin/patch','-p1','--fuzz=0','--batch','-i',str(saved)],cwd=root,capture_output=True,text=True)
        (output/(p.name+'.log')).write_text(result.stdout+result.stderr)
        require(result.returncode==0 and not re.search(r'fuzz|offset|FAILED|Reversed',result.stdout+result.stderr,re.I),'exact patch '+p.name)
        manifest['patches'].append({'path':str(p),'sha256':sha(data)})
    changed=[p for p,b in before.items() if (root/p).read_bytes()!=b]
    require(set(changed)=={'nss_dp_main.c','nss_dp_attach.c','hal/soc_ops/ipq807x/nss_ipq807x.h',str(REL/'edma_data_plane.h'),str(REL/'edma_data_plane.c'),str(REL/'edma_tx_rx.c')},'015 six-file scope')
    require((root/REL/'edma_cfg.c').read_bytes()==before[str(REL/'edma_cfg.c')],'014 allocation/TX cleanup changed')
    for name in ['edma_tx_slot_take','edma_clean_tx','edma_ring_xmit']:
        require(tx.definition(before[str(REL/'edma_tx_rx.c')].decode(),name)[0]==tx.definition((root/REL/'edma_tx_rx.c').read_text(),name)[0],'014 TX function changed '+name)
    manifest['changed_by_015']=changed
    manifest['files']={str(f.relative_to(root)):sha(f.read_bytes()) for f in root.rglob('*') if f.is_file()}
    (output/'INPUTS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return root,manifest


def extract(root, output):
    headers=[]; fragments=[]; funcs={}
    for rel in ['hal/soc_ops/ipq807x/nss_ipq807x.h',str(REL/'edma_regs.h'),str(REL/'edma_data_plane.h')]:
        text=(root/rel).read_text(); headers.append(re.sub(r'^#include[^\n]*\n','',text,flags=re.M)); fragments.append({'path':str(root/rel),'sha256':sha(text.encode()),'kind':'header minus include directives'})
    for rel,names in NAMES.items():
        text=(root/rel).read_text()
        for name in names:
            code,line=definition(text,name); funcs[name]=code
            fragments.append({'path':str(root/rel),'name':name,'line':line,'sha256':sha(code.encode())})
    rx=definition((root/REL/'edma_tx_rx.c').read_text(),'edma_clean_rx')[0]
    require('rcu_dereference(ehw->netdev_arr[src_port_num - 1])' in rx,'RX raw reader remains')
    require(funcs['edma_napi'].count('rcu_read_lock();')==funcs['edma_napi'].count('rcu_read_unlock();')==1,'full poll section')
    (output/'FRAGMENTS.json').write_text(json.dumps(fragments,indent=2)+'\n')
    return '\n'.join(headers),funcs


def fixture(headers, functions):
    funcs=dict(functions)
    napi=funcs['edma_napi']; m=re.search(r'if \(work_done < budget[^\n]*\) \{',napi)
    require(m is not None,'tail hook anchor'); napi=napi[:m.end()]+'\n\t\tpause_poll(2);'+napi[m.end():];funcs['edma_napi']=napi
    prototypes='\n'.join(code[:code.index('{')].strip()+';' for code in funcs.values())
    text=TEMPLATE.read_text();text=once(text,'/* HEADERS */',headers);text=once(text,'/* PROTOTYPES */',prototypes)
    return once(text,'/* FUNCTIONS */','\n\n'.join(funcs.values()))


def mutants(funcs):
    result={}
    def add(name,fn,old,new,marker):
        changed=dict(funcs);changed[fn]=once(changed[fn],old,new);result[name]=(changed,marker)
    add('physical-napi-owner','edma_register_netdevice','netif_napi_add(edma_hw.napi_dev,','netif_napi_add(netdev,','dummy-napi-owner')
    add('probe-uses-takeover-deinit','nss_dp_abort_host_probe','edma_retire_port(dp->netdev, dp->macid);','edma_if_deinit(host);','probe-failure-no-publication-or-override')
    add('probe-context-not-cleared','nss_dp_abort_host_probe','nss_dp_clear_host_ctx(dp);','(void)0;','free-after-hostctx-clear')
    add('quarantine-leaks-membership','nss_dp_plane_quarantine','edma_retire_port(dp->netdev, dp->macid);','(void)0;','free-after-unpublish')
    add('duplicate-open-increments','edma_if_open','if (edma_hw.host_open[index])','if (false)','duplicate-open-idempotent')
    add('poll-raw-port','edma_napi','rcu_dereference(ehw->netdev_arr[i])','ehw->netdev_arr[i]','port-dereference-protocol')
    add('no-final-tail-mask','edma_stop_napi','synchronize_net();\n\tedma_disable_interrupts();','synchronize_net();','tail-final-mask')
    add('skip-rxfill-irq-unwind','edma_free_irqs','while (edma_hw.rxfill_irqs_owned)','while (false)','reverse-acquired-irq-owner')
    add('recursive-rtnl','edma_if_deinit','edma_cleanup_locked(true);','edma_cleanup(true);','no-recursive-rtnl')
    add('release-mmio-on-override','edma_cleanup_locked','if (!is_dp_override)\n\t\tedma_release_mmio();','edma_release_mmio();','override-retains-mmio-only')
    changed=dict(funcs);changed['edma_cleanup_locked']=changed['edma_cleanup_locked'].replace('edma_disable_port();','(void)0;');result['skip-final-port-disable']=(changed,'exit-final-disable-before-release')
    add('ignore-complete-false','edma_napi','if (work_done < budget && napi_complete(napi))','if (work_done < budget)','complete-false-no-rearm')
    add('allow-overridden-id','edma_register_netdevice','if (edma_hw.override_accounted[macid - 1])','if (false)','overridden-id-reprobe-rejected')
    add('clear-foreign-staticctx','nss_dp_clear_host_ctx','if (host->dev == dp->netdev)','if (true)','foreign-static-context-kept')
    add('retire-without-grace','edma_retire_port','synchronize_net();','(void)0;','retirement-grace-wait')
    add('retire-without-unpublish','edma_retire_port','rcu_assign_pointer(edma_hw.netdev_arr[index], NULL);','(void)0;','free-after-unpublish')
    changed=dict(funcs)
    q=once(changed['nss_dp_plane_quarantine'],'edma_retire_port(dp->netdev, dp->macid);','(void)0;')
    changed['nss_dp_plane_quarantine']=once(q,'nss_dp_plane_quiesce(dp);','edma_retire_port(dp->netdev, dp->macid);\n\tnss_dp_plane_quiesce(dp);')
    result['retire-before-admitted-drain']=(changed,'membership-not-retired-before-admitted-drain')
    add('skip-admitted-drain','nss_dp_plane_quarantine','nss_dp_plane_quiesce(dp);','(void)0;','quarantine-waits-admitted-reference')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream-cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',required=True);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    out=a.output.resolve();require(out.name.startswith('EDMA-LIFETIME-'),'evidence prefix');out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    result={'status':'INCOMPLETE','compiler':a.compiler,'sanitize':a.sanitize,'runs':{},'mutants':{}}
    try:
        result['compiler_version']=subprocess.run([a.compiler,'--version'],capture_output=True,text=True,check=True).stdout
        root,inputs=prepare(a.upstream_cache.resolve(),out);headers,funcs=extract(root,out)
        result['inputs_sha256']=sha((out/'INPUTS.json').read_bytes());result['test_inputs']={str(f):sha(f.read_bytes()) for f in [Path(__file__),TEMPLATE,TX_RUNNER]}
        flags=['-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-function','-Wno-sign-compare','-Wno-pointer-sign']
        if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        def build(name,text,extra=()):
            src=out/(name+'.c');binary=out/name;src.write_text(text)
            r=run([a.compiler,*flags,*extra,src,'-o',binary],out,name+'.compile')
            require(r['returncode']==0 and not r['stdout'] and not r['stderr'],'clean compile '+name);return binary
        binary=build('lifetime-fixture',fixture(headers,funcs));r=run([binary,'suite'],out,'lifetime.suite',env)
        require(r['returncode']==0 and not r['stderr'],'positive lifetime suite');result['runs']['lifetime']=r
        for name,(changed,marker) in mutants(funcs).items():
            b=build('mutant-'+name,fixture(headers,changed));r=run([b,'suite'],out,'mutant-'+name,env)
            require(r['returncode']==86 and 'EDMA_LIFETIME '+marker in r['stderr'],'semantic mutant gate '+name);result['mutants'][name]=r
        result['tx_combination']='DELEGATED_BY_PARENT_TO_INDEPENDENT_INTEGRATION_AUTHOR_NOT_RUN_BY_THIS_SUITE'
        if a.sanitize:
            result['sanitizer_canaries']={}
            for name,code,marker in [('asan','#include <stdlib.h>\nint main(void){volatile int i=2;volatile int *p=malloc(sizeof(int));p[i]=1;free((void *)p);return 0;}\n','AddressSanitizer'),('ubsan','int main(void){volatile int i=32;return 1<<i;}\n','runtime error:')]:
                b=build('canary-'+name,code);r=run([b],out,'canary-'+name,env)
                require(isinstance(r['returncode'],int) and r['returncode']!=0 and marker in r['stderr'],'positive sanitizer canary '+name);result['sanitizer_canaries'][name]=r
        result['status']='PASS'
    except Exception as exc:result['error']=str(exc);raise
    finally:(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'suite':result['runs']['lifetime']['stdout'].strip(),'mutants':len(result['mutants'])}))


if __name__=='__main__':main()
