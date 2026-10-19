#!/usr/bin/env python3
"""Exercise prepared PCIC IRQ ownership plus exact caller error-path snippets."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE/'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec); spec.loader.exec_module(extract)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared', type=Path); p.add_argument('--baseline', type=Path)
p.add_argument('--output', type=Path, required=True); p.add_argument('--cc', default='cc')
p.add_argument('--sanitize', action='store_true')
p.add_argument('--mutations', action='store_true', help='reject five deliberately broken generated-C variants')
args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
cc=shutil.which(args.cc)
if not cc: raise SystemExit('host C compiler required')
assets={x:x.read_bytes() for x in (Path(__file__).resolve(), HERE/'ath11k-pcic-irq/host-fixture.c',
                                   HERE/'nss-dp-containment/extract_prepared_c.py')}

def variable(text, name):
    found=list(re.finditer(r'^(?:static\s+)?const[^;=]+\b'+re.escape(name)+r'\b[^;=]*=\s*\{',extract.code_mask(text),re.M))
    if len(found)!=1: raise ValueError('ambiguous variable '+name)
    m=found[0]; return text[m.start():extract.block_end(text,m.end()-1)]+';\n'

def callers(prepared, directory):
    pci=prepared.function(directory+'pci.c','ath11k_pci_probe')
    start=pci.index('\tret = ath11k_pcic_config_irq(ab);')
    block=pci.index('{',start)
    call=pci[start:extract.block_end(pci,block)]
    post_start=pci.index('\tret = ath11k_pci_config_msi_data(ab_pci);',start)
    post_block=pci.index('{',post_start)
    post_call=pci[post_start:extract.block_end(pci,post_block)]
    cleanup=pci[pci.index('err_free_irq:'):pci.index('\tath11k_ce_free_pipes(ab);',start)]
    wrapped='static int host_pci_config_call(struct ath11k_base *ab) {\nint ret; struct ath11k_pci p={.ab=ab}, *ab_pci=&p;\n'
    wrapped+=call+'\n'+post_call+'\nreturn 0;\n'+cleanup+'\nath11k_ce_free_pipes(ab); return ret;\n}\n'
    ahb=prepared.function(directory+'ahb.c','ath11k_ahb_config_irq')
    start=ahb.index('\tif (ab->hw_params.hybrid_bus_type)')
    opening=ahb.index(')',start)+1
    tail=ahb[opening:].lstrip()
    if tail.startswith('{'):
        opening=ahb.index('{',opening); end=extract.block_end(ahb,opening)
    else:
        end=ahb.index(';',opening)+1
    wrapped+='static int host_ahb_config_call(struct ath11k_base *ab) { int ret;\n'+ahb[start:end]+'\nreturn -EINVAL;\n}\n'
    return wrapped

records=[]
variants=[('candidate',args.prepared,True)]+([('baseline',args.baseline,False)] if args.baseline else [])
if args.mutations:
    variants += [(name,args.prepared,False) for name in ('mutant-ce-free','mutant-napi-del','mutant-pci-caller','mutant-ahb-caller','mutant-affinity-order')]
for label,root,expected in variants:
    prepared=extract.Prepared(root); directory='drivers/net/wireless/ath/ath11k/'
    pcic=prepared.read(directory+'pcic.c'); hw=prepared.read(directory+'hw.c')
    core=prepared.read(directory+'core.h'); ph=prepared.read(directory+'pcic.h')
    declarations=''
    for text in (core,ph,prepared.read(directory+'hw.h')):
        declarations+='\n'.join(re.findall(r'^#define\s+ATH11K_(?:IRQ_NUM_MAX|EXT_IRQ_NUM_MAX|EXT_IRQ_GRP_NUM_MAX|PCI_IRQ_CE0_OFFSET|PCI_IRQ_DP_OFFSET)\s+[^\n]+',text,re.M))+'\n'
    declarations+=prepared.structure(directory+'core.h','ath11k_hw_rev','enum')
    for name in ('ath11k_msi_user','ath11k_msi_config'):
        declarations+=prepared.structure(directory+'core.h',name)
    declarations+=prepared.structure(directory+'hw.h','ath11k_hw_ring_mask')
    declarations+='\n'.join(re.findall(r'^#define ATH11K_\w+RING_MASK_\d+[^\n]*',hw,re.M))+'\n'
    for name in ('qca6390','qcn9074','wcn6750','qcn6122'):
        declarations+=variable(hw,'ath11k_hw_ring_mask_'+name)
    declarations+=variable(pcic,'irq_name')+variable(pcic,'ath11k_msi_config')
    declarations+=variable(prepared.read(directory+'pci.c'),'msi_config_one_msi')
    # Assignment failures are API fault injection, not substitute config logic.
    functions='#define ath11k_pcic_get_user_msi_assignment host_real_assignment\n'
    functions+=prepared.function(directory+'pcic.c','ath11k_pcic_get_user_msi_assignment')
    functions+='#undef ath11k_pcic_get_user_msi_assignment\n'
    functions+='''static int ath11k_pcic_get_user_msi_assignment(struct ath11k_base *ab, char *name, void *count, u32 *data, u32 *vector) {
        if ((!strcmp(name,"CE") && assignment_ce_error) || (!strcmp(name,"DP") && assignment_dp_error)) return -EINVAL;
        return host_real_assignment(ab,name,count,data,vector);
    }\n'''
    for name in ('ath11k_pcic_free_ext_irq','ath11k_pcic_free_irq','ath11k_pcic_ce_irq_disable',
                 'ath11k_pcic_ext_grp_disable','ath11k_pcic_ext_irq_config','ath11k_pcic_config_irq'):
        functions+=prepared.function(directory+'pcic.c',name)
    core_c=prepared.read(directory+'core.c'); counts=[]
    for name in ('qca6390 hw2.0','qcn9074 hw1.0','wcn6750 hw1.0','qcn6122 hw1.0'):
        start=core_c.index('.name = "'+name+'"')
        value=re.search(r'\.ce_count\s*=\s*(\w+)',core_c[start:]).group(1)
        if not value.isdigit(): value=re.search(r'^#define\s+'+value+r'\s+(\d+)',core,re.M).group(1)
        counts.append(value)
    program=assets[HERE/'ath11k-pcic-irq/host-fixture.c'].decode().replace('HOST_DECLARATIONS',declarations)
    program=program.replace('HOST_FUNCTIONS',functions).replace('HOST_CALL_SITES',callers(prepared,directory)).replace('HOST_CE_COUNTS',', '.join(counts))
    if 'The caller frees partial ownership' in pcic: program='#define HOST_FIXED 1\n'+program
    mutations={
        'mutant-ce-free': ('free_irq(ab->irq_num[irq_idx], &ab->ce.ce_pipe[i]);',';'),
        'mutant-napi-del': ('netif_napi_del(&irq_grp->napi);',';'),
        'mutant-pci-caller': ('ath11k_pci_set_irq_affinity_hint(ab_pci, NULL);\n\tath11k_pcic_free_irq(ab);',
                              'ath11k_pci_set_irq_affinity_hint(ab_pci, NULL);'),
        'mutant-ahb-caller': ('if (ret)\n\t\t\tath11k_pcic_free_irq(ab);','if (ret)\n\t\t\t(void)ab;'),
        'mutant-affinity-order': ('ath11k_pci_set_irq_affinity_hint(ab_pci, NULL);\n\tath11k_pcic_free_irq(ab);',
                                  'ath11k_pcic_free_irq(ab);\n\tath11k_pci_set_irq_affinity_hint(ab_pci, NULL);'),
    }
    if label in mutations:
        old,new=mutations[label]
        if program.count(old)!=1: raise SystemExit('ambiguous mutation '+label)
        program=program.replace(old,new,1)
    target=args.output/(label+'.c'); target.write_text(program)
    command=[cc,'-std=gnu11','-Wall','-Wextra','-Werror','-Wno-sign-compare','-Wno-unused-parameter',
             '-Wno-unused-variable','-Wno-unused-function',str(target),'-o',str(target.with_suffix('.host'))]
    if args.sanitize: command[1:1]=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
    result=subprocess.run(command,capture_output=True,timeout=40)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode: raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(target.with_suffix('.host'))],capture_output=True,timeout=40)
    (args.output/(label+'.stdout')).write_bytes(result.stdout); (args.output/(label+'.stderr')).write_bytes(result.stderr)
    if args.sanitize and re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:',result.stderr):
        raise SystemExit(label+' sanitizer error: '+result.stderr.decode())
    if (result.returncode==0)!=expected: raise SystemExit(label+' unexpected test result: '+result.stderr.decode())
    summary=json.loads(result.stdout)
    if result.returncode != (0 if expected else 1) or bool(summary['failures'])==expected:
        raise SystemExit(label+' did not return the expected assertion result')
    records.append(dict(label=label,expected_pass=expected,returncode=result.returncode,compile_command=command,
        **summary,generated_c_sha256=hashlib.sha256(program.encode()).hexdigest(),**prepared.manifest()))
for record in records[1:]:
    if records[0]['success_signatures']!=record['success_signatures']:
        raise SystemExit(record['label']+': successful IRQ/owner/flags/disable signatures changed')
for path,data in assets.items():
    if path.read_bytes()!=data: raise SystemExit('test asset changed while running: '+str(path))
report=dict(results=records,sanitizer_enabled=args.sanitize,successful_profiles_match_baseline=bool(args.baseline),
    scope='actual prepared PCIC functions, four ring masks and MSI tables; byte-preserved PCI/AHB caller snippets only, not full probes or hardware',
    test_assets=[dict(path=str(x),sha256=hashlib.sha256(data).hexdigest()) for x,data in assets.items()])
(args.output/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([dict(label=r['label'],checks=r['checks'],failures=r['failures']) for r in records]))
