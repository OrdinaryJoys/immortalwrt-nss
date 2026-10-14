#!/usr/bin/env python3
"""Compile actual prepared DRV C against explicit host API substitutes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

from extract_prepared_c import Prepared, code_mask

HERE=Path(__file__).resolve().parent
PLANE='nss_data_plane/nss_data_plane.c'
COMMON='nss_data_plane/nss_data_plane_common.c'
HEADER='nss_data_plane/include/nss_data_plane.h'
HAL='nss_hal/nss_hal.c'
ASSETS=('test-nss-drv-containment.py','extract_prepared_c.py','driver_kernel_stubs.h',
        'driver_nss_scaffolding.h','driver_api_fixtures.c','driver_emergency_cases.c',
        'driver_baseline_cases.c','driver_candidate_cases.c','driver_nongeneric_cases.c')


def asset_manifest():
    return [{'path':name,'bytes':(HERE/name).stat().st_size,
             'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in ASSETS]


def no_includes(text):
    # Only include directives are substituted. Every DRV definition/global in
    # the common unit retains its actual original source bytes and directives.
    return re.sub(r'^\s*#\s*include[^\n]*$', '', text, flags=re.M)


def actual_declaration(prepared,relative,name):
    original=prepared.read(relative)
    matches=list(re.finditer(r'^static[^\n]*\b'+re.escape(name)+r'\b[^\n]*;[ \t]*$',code_mask(original),re.M))
    if len(matches)!=1: raise ValueError('missing/ambiguous actual private declaration: '+name)
    match=matches[0]; text=original[match.start():match.end()]+'\n'
    prepared.extracted.append({'source':relative,'declaration':name,'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()})
    return text


def program(prepared,*,candidate=False,cases='driver_baseline_cases.c'):
    structures=''.join([prepared.structure(HEADER,'nss_data_plane_ops'),
                        prepared.structure('nss_core.h','int_ctx_instance'),
                        prepared.structure('nss_core.h','nss_subsystem_dataplane_register'),
                        prepared.structure('nss_data_plane/hal/include/nss_data_plane_hal.h','nss_data_plane_param')])
    functions=[]; globals_text=''
    if candidate:
        globals_text='#ifdef NSS_HAL_IPQ807x_SUPPORT\n'
        for name in ('nss_data_plane_ops_prepared','nss_data_plane_hal_registered'):
            globals_text+=actual_declaration(prepared,PLANE,name)
        for name in ('nss_hal_receive_group_lock','nss_hal_receive_group_closing','nss_hal_receive_group_stopped','nss_hal_core_removed'):
            globals_text+=actual_declaration(prepared,HAL,name)
        globals_text+='#endif\n'
    for name in ('nss_core_register_subsys_dp','nss_core_unregister_subsys_dp','nss_core_handle_napi_emergency'):
        functions.append(prepared.function('nss_core.c',name))
    for name in ('nss_data_plane_register_to_nss_dp','nss_data_plane_unregister_from_nss_dp','__nss_data_plane_register','__nss_data_plane_unregister'):
        functions.append(prepared.function(PLANE,name))
    common_names=['nss_data_plane_work_function','nss_data_plane_schedule_registration','nss_data_plane_init_delay_work','nss_data_plane_destroy_delay_work']
    if candidate: common_names+=['nss_data_plane_registration_stopped','nss_data_plane_stop_registration']
    for name in common_names:
        prepared.function(COMMON,name)  # independently hash exact definitions
    functions.append(no_includes(prepared.read(COMMON)))
    if candidate: functions.append(prepared.function(PLANE,'nss_data_plane_quarantine_registered'))
    functions.append(prepared.function(HAL,'nss_hal_clean_up_irq'))
    if candidate:
        functions.append(prepared.function(HAL,'nss_hal_probe'))
        functions.append(prepared.function(HAL,'nss_hal_quiesce_receive_group'))
    functions.append(prepared.function(HAL,'nss_hal_remove'))
    declarations='bool nss_data_plane_schedule_registration(void);\nint nss_data_plane_init_delay_work(void);\nvoid nss_data_plane_destroy_delay_work(void);\n'
    if candidate: declarations+='bool nss_data_plane_registration_stopped(void);\nvoid nss_data_plane_stop_registration(void);\nvoid nss_data_plane_quarantine_registered(void);\n'
    scaffolding=(HERE/'driver_nss_scaffolding.h').read_text().replace('HOST_EXTRACTED_STRUCTURES',structures).replace('HOST_COMMON_API_DECLARATIONS',declarations)
    fixtures=(HERE/'driver_api_fixtures.c').read_text().replace('HOST_EXTRACTED_FUNCTIONS','\n'.join(functions))
    notices=[row['text'].split('*/',1)[0]+'*/\n' for row in prepared.files.values() if row['text'].startswith('/*')]
    return '\n'.join(notices)+(HERE/'driver_kernel_stubs.h').read_text()+scaffolding+globals_text+fixtures+(HERE/'driver_emergency_cases.c').read_text()+(HERE/cases).read_text()


def run(program,prepared,cc,output,label,expected,*,soc=None,generic=True,role='ORIGINAL_BASELINE_DEFECT_CONTROL'):
    source=output/(label+'.c'); binary=output/(label+'.host'); source.write_text(program)
    command=[cc,'-std=gnu11','-O0','-g','-pthread','-Wall','-Werror=implicit-function-declaration','-Wno-unused-function','-Wno-unused-variable',str(source),'-o',str(binary)]
    if generic: command.insert(1,'-DNSS_DATA_PLANE_GENERIC_SUPPORT=1')
    if soc: command.insert(1,'-D'+soc+'=1')
    compiled=subprocess.run(command,text=True,capture_output=True,timeout=30)
    if compiled.returncode: raise RuntimeError('compilation failed:\n'+compiled.stderr[:16000])
    executed=subprocess.run([str(binary)],text=True,capture_output=True,timeout=30)
    if executed.returncode: raise RuntimeError('assertions failed:\n'+executed.stdout+executed.stderr)
    cases=[line.removeprefix('PASS ') for line in executed.stdout.splitlines() if line.startswith('PASS ')]
    if len(cases)!=expected or len(set(cases))!=expected: raise ValueError('missing/duplicate actual-C cases')
    return {'status':'PASS_HOST_SUBSTITUTES_ONLY','input_role':role,'soc_define':soc,'generic_support':generic,'count':len(cases),'cases':cases,'compile_command':command,
            'compiler_diagnostics':compiled.stderr,'execution_stdout':executed.stdout,'execution_stderr':executed.stderr,
            'generated_c_sha256':hashlib.sha256(program.encode()).hexdigest(),'compiled_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),**prepared.manifest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,help='actual full prepared DRV original baseline')
    parser.add_argument('--candidate',type=Path,help='actual prepared candidate with containment patch applied')
    parser.add_argument('--candidate-only',action='store_true',help='execute actual candidate only; does not run original baseline controls')
    parser.add_argument('--cc',default='cc'); parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.candidate_only:
        if args.candidate is None: parser.error('--candidate-only requires --candidate')
        if args.baseline is not None: parser.error('--candidate-only forbids --baseline')
    elif args.baseline is None:
        parser.error('--baseline is required unless explicit --candidate-only')
    cc=shutil.which(args.cc)
    if cc is None: raise ValueError('native C compiler is required')
    selected={'baseline':str(args.baseline.resolve(strict=True)) if args.baseline else None,
              'candidate':str(args.candidate.resolve(strict=True)) if args.candidate else None}
    assets=asset_manifest(); snapshots=[]
    output=args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nss-drv-host-check-'))
    if args.output: output.mkdir(mode=0o700)
    report={'scope':'ACTUAL_PREPARED_DRV_C_HOST_API_SUBSTITUTES_ONLY','kernel_or_ax6_acceptance':False,'network_access':False,
            'host_dimensions':{'mock_core_contexts':2,'irq_slots_per_mock_core':2,'ipq807x_source_irq_slots_per_core':10,
                               'registry_interface_slots':4,'dp_interface_slots':4,'primary_port_ifnum':1,
                               'normally_active_irq_slot':0,'edge_case_extra_irq_slot':1},
            'limitations':['Reduced host dimensions, not all actual ten IPQ807x IRQ slots or all physical ports.',
                           'Two pthread-backed fixture contexts are not hardware dual-core IRQ/NAPI evidence.',
                           'Kernel workqueue, RTNL, IRQ, NAPI ownership and grace are host API substitutes, not Linux ordering/RCU/lockdep proof.',
                           'Only selected actual DRV C is compiled; ordinary poll bodies, full probe, platform-driver initializer and general module/client lifetime are not executed.',
                           'DP override/start/restore APIs are substitutes; actual DP state is covered by separate DP extracted-C tests.',
                           'Returning and blocked host coredump notifier substitutes never invoke firmware, panic, crash or hardware.',
                           'Other-SoC and wrong-macro PASS counts assert retained legacy defects, not repaired containment.',
                           'This replay is native host evidence, not a target kernel build, ABI test or AX6 runtime acceptance.'],
            'host_platform':platform.platform(),'compiler':subprocess.run([cc,'--version'],text=True,capture_output=True,timeout=10).stdout,
            'mode':'CANDIDATE_ONLY_37' if args.candidate_only else 'BASELINE_AND_CANDIDATE_44' if args.candidate else 'BASELINE_ONLY_7_CANDIDATE_INCOMPLETE',
            'original_baseline_executed':args.baseline is not None,'selected_inputs':selected,'test_assets':assets,
            'candidate_status':'INCOMPLETE_NO_CANDIDATE_EXECUTED','runs':[]}
    if args.baseline:
        prepared=Prepared(args.baseline); snapshots.append(prepared)
        report['runs'].append(run(program(prepared),prepared,cc,output,'original-baseline-controls',7,soc='NSS_HAL_IPQ807x_SUPPORT'))
    if args.candidate:
        prepared=Prepared(args.candidate); snapshots.append(prepared)
        report['runs'].append(run(program(prepared,candidate=True,cases='driver_candidate_cases.c'),prepared,cc,output,'candidate-ipq807x',20,soc='NSS_HAL_IPQ807x_SUPPORT',role='ACTUAL_IPQ807x_CANDIDATE'))
        for label,soc,role in [('candidate-other-soc-controls',None,'ACTUAL_CANDIDATE_OTHER_SOC_LEGACY_CONTROL'),
                               ('wrong-uppercase-soc-negative','NSS_HAL_IPQ807X_SUPPORT','WRONG_SOC_MACRO_LEGACY_DEFECT_NEGATIVE_CONTROL')]:
            prepared=Prepared(args.candidate); snapshots.append(prepared)
            report['runs'].append(run(program(prepared),prepared,cc,output,label,7,soc=soc,role=role))
        prepared=Prepared(args.candidate); snapshots.append(prepared)
        report['runs'].append(run(program(prepared,candidate=True,cases='driver_nongeneric_cases.c'),prepared,cc,output,'candidate-ipq807x-nongeneric',3,soc='NSS_HAL_IPQ807x_SUPPORT',generic=False,role='ACTUAL_IPQ807x_CANDIDATE_NON_GENERIC_CONTROL'))
        report['candidate_status']='PASS_EXTRACTED_C_HOST_SUBSTITUTES_ONLY'
    # Recheck every snapshot at the end, not just after its own compilation.
    # A source mutation between macro variants must not get a mixed PASS.
    for prepared in snapshots: prepared.manifest()
    by_root={}
    for row in report['runs']:
        sources={entry['path']:entry['sha256'] for entry in row['sources']}
        root=row['prepared_root']
        if root in by_root and by_root[root]!=sources: raise ValueError('prepared input differs between macro variants')
        by_root[root]=sources
    if asset_manifest()!=assets: raise ValueError('test assets changed during host run')
    report['total_cases']=sum(row['count'] for row in report['runs'])
    report['expected_cases']=37 if args.candidate_only else 44 if args.candidate else 7
    if report['total_cases']!=report['expected_cases']: raise ValueError('unexpected case total for selected mode')
    (output/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))


if __name__=='__main__': main()
