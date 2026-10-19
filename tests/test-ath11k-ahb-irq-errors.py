#!/usr/bin/env python3
"""Run actual prepared AHB functions/ring masks with host API substitutes only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('extract_c',HERE/'nss-dp-containment/extract_prepared_c.py')
extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared',type=Path);p.add_argument('--baseline',type=Path)
p.add_argument('--output',type=Path,required=True);p.add_argument('--cc',default='cc')
p.add_argument('--sanitize',action='store_true',help='enable host ASan/UBSan; not kernel instrumentation')
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
cc=shutil.which(args.cc)
if not cc:raise SystemExit('host C compiler required')
assets={path:path.read_bytes() for path in (Path(__file__).resolve(),HERE/'ath11k-ahb-irq/host-fixture.c',
                                           HERE/'nss-dp-containment/extract_prepared_c.py')}

def variable(text,name):
    matches=list(re.finditer(r'^(?:static\s+)?const[^;=]+\b'+re.escape(name)+r'\b[^;=]*=\s*\{',extract.code_mask(text),re.M))
    if len(matches)!=1:raise ValueError('ambiguous/missing variable '+name)
    m=matches[0];return text[m.start():extract.block_end(text,m.end()-1)]+';\n'

records=[]
for label,root,expected in [('candidate',args.prepared,True)]+([('baseline',args.baseline,False)] if args.baseline else []):
    prepared=extract.Prepared(root)
    ahb='drivers/net/wireless/ath/ath11k/ahb.c';hw='drivers/net/wireless/ath/ath11k/hw.c'
    hwh='drivers/net/wireless/ath/ath11k/hw.h';core='drivers/net/wireless/ath/ath11k/core.h'
    text=prepared.read(ahb);hardware=prepared.read(hw)
    fixed='ath11k_ahb_free_ext_irq_grp' in text
    declarations=''
    for header in (core,hwh,ahb):
        for match in re.finditer(r'^#define\s+ATH11K_(?:IRQ_NUM_MAX|EXT_IRQ_NUM_MAX|EXT_IRQ_GRP_NUM_MAX|IRQ_CE0_OFFSET|INVALID_HW_MAC_ID)\s+[^\n]+',prepared.read(header),re.M):
            declarations+=match.group()+'\n'
    declarations+=prepared.structure(hwh,'ath11k_hw_ring_mask')
    declarations+='\n'.join(re.findall(r'^#define ATH11K_\w+RING_MASK_\d+[^\n]*',hardware,re.M))+'\n'
    declarations+=variable(hardware,'ath11k_hw_ring_mask_ipq8074')
    declarations+=variable(text,'irq_name')+prepared.structure(ahb,'ext_irq_num','enum')
    declarations+=prepared.function(hw,'ath11k_hw_ipq8074_mac_from_pdev_id')
    names=['ath11k_ahb_free_ext_irq_grp','ath11k_ahb_free_ext_irq','ath11k_ahb_free_ce_irqs',
           'ath11k_ahb_free_irq','ath11k_ahb_config_ext_irq','ath11k_ahb_config_irq'] if fixed else [
           'ath11k_ahb_free_ext_irq','ath11k_ahb_free_irq','ath11k_ahb_config_ext_irq','ath11k_ahb_config_irq']
    functions=''.join(prepared.function(ahb,name) for name in names)
    if 'static void ath11k_ahb_core_free(' in text:
        functions+=prepared.function(ahb,'ath11k_ahb_core_free')
    functions+='#define ath11k_ahb_fw_resources_init host_fw_resources\n#define ath11k_ahb_fw_resource_deinit host_fw_deinit\n'
    functions+=prepared.function(ahb,'ath11k_ahb_probe')
    functions+='#undef ath11k_ahb_fw_resources_init\n#undef ath11k_ahb_fw_resource_deinit\n'
    functions+=prepared.function(ahb,'ath11k_ahb_fw_resources_init')+prepared.function(ahb,'ath11k_ahb_fw_resource_deinit')
    fixture=assets[HERE/'ath11k-ahb-irq/host-fixture.c'].decode()
    program=fixture.replace('HOST_SOURCE_DECLARATIONS',declarations).replace('HOST_DRIVER_FUNCTIONS',functions)
    if fixed:program='#define HOST_FIXED_IRQ_OWNERSHIP 1\n'+program
    path=args.output/(label+'.c');path.write_text(program)
    command=[cc,'-std=gnu11','-Wall','-Wextra','-Werror','-Wno-sign-compare','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-function',
             str(path),'-o',str(path.with_suffix('.host'))]
    if args.sanitize:command[1:1]=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
    result=subprocess.run(command,capture_output=True,timeout=30)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(path.with_suffix('.host'))],capture_output=True,timeout=30)
    (args.output/(label+'.stdout')).write_bytes(result.stdout);(args.output/(label+'.stderr')).write_bytes(result.stderr)
    if args.sanitize and re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:',result.stderr):
        raise SystemExit(label+' sanitizer failure: '+result.stderr.decode())
    if (result.returncode==0)!=expected:raise SystemExit(label+' unexpected assertions: '+result.stderr.decode())
    records.append(dict(label=label,expected_pass=expected,returncode=result.returncode,compile_command=command,**json.loads(result.stdout),
        generated_c_sha256=hashlib.sha256(program.encode()).hexdigest(),**prepared.manifest()))
if args.baseline and records[0]['native_success_signatures']!=records[1]['native_success_signatures']:
    raise SystemExit('native IRQ selection/ownership changed in a successful profile')
for path,data in assets.items():
    if path.read_bytes()!=data:raise SystemExit('test asset changed during run: '+str(path))
report=dict(results=records,scope='actual prepared AHB functions and IPQ8074 ring masks; API/IRQ/NAPI/resource effects modeled, not kernel or target qualification',
            successful_native_profiles_match_baseline=bool(args.baseline),
            sanitizer_enabled=args.sanitize,
            test_assets=[dict(path=str(path),sha256=hashlib.sha256(data).hexdigest()) for path,data in assets.items()])
(args.output/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([dict(label=r['label'],checks=r['checks'],failures=r['failures'],expected_pass=r['expected_pass']) for r in records]))
