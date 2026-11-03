#!/usr/bin/env python3
"""Compile the complete prepared I2C C file with observable native leaf models."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
SUPPORT=Path(__file__).resolve().parent/'ssdk-i2c-io'
sys.path.insert(0,str(SUPPORT))
import source

DATA=('data-chunks','data-width','short-read','short-write','negative-read','negative-write',
      'midstream','data-reference','adapter-missing','data-null','data-zero','unlocked-data')
PHY=('phy-valid','phy-errors','unlocked-phy','phy-reference','mmd-result','mmd-publication',
     'phy-invalid','phy-null')

def exact_positive(row,case):
    return (type(row['returncode']) is int and row['returncode']==0 and
            row['stdout']=='PASS '+case+'\n' and row['stderr']=='')

def exact_negative(row,marker):
    return (type(row['returncode']) is int and row['returncode']==86 and
            row['stdout']=='' and row['stderr']=='I2C_IO '+marker+'\n')

def oracle_controls():
    good={'returncode':86,'stdout':'','stderr':'I2C_IO expected\n'}
    source.need(exact_negative(good,'expected'),'valid semantic oracle')
    rejected=0
    for field,value in [('returncode',1),('returncode',-11),('returncode',97),('returncode',98),
                        ('returncode',None),('returncode',True),('stdout','PASS fake\n'),
                        ('stderr','I2C_IO wrong\n'),('stderr','I2C_IO expected\nextra\n')]:
        changed=dict(good); changed[field]=value
        source.need(not exact_negative(changed,'expected'),'negative oracle pollution'); rejected+=1
    good={'returncode':0,'stdout':'PASS expected\n','stderr':''}
    source.need(exact_positive(good,'expected'),'valid positive oracle')
    for field,value in [('returncode',False),('returncode',86),('stdout','PASS wrong\n'),
                        ('stdout','PASS expected\nextra\n'),('stderr','warning\n')]:
        changed=dict(good); changed[field]=value
        source.need(not exact_positive(changed,'expected'),'positive oracle pollution'); rejected+=1
    return {'classification':'PYTHON_RESULT_ORACLE_NOT_NATIVE_SOURCE_CONTROLS','valid':2,'rejected':rejected}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--cc',required=True)
    parser.add_argument('--patch-tool',default='patch')
    parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args(); a.output=a.output.resolve(); a.output.mkdir(parents=True,exist_ok=False)
    a.baseline=a.baseline.resolve(); a.prepared=a.prepared.resolve()
    report={'status':'INCOMPLETE','scope':'WHOLE_I2C_TRANSLATION_UNIT_HOST_MODEL_NOT_KERNEL_OR_HW',
            'positive':[],'negative':[],'baseline_witnesses':[],'commands':[],
            'sanitize':a.sanitize,'LSan':'NOT_VERIFIED','oracle_controls':oracle_controls(),
            'remaining':['HSL cross-operation bus lease and lock admission',
                         'adapter provider removal/registration and MDIO devres ownership',
                         'shared UK/SD/PHY readers and root rollback','target ABI and actual I2C/HW/FW']}
    inputs=[Path(__file__),*sorted(SUPPORT.glob('*')),source.PATCH,
            source.ROOT/'tests/edma_patch_context.py',source.ROOT/'tests/nss-dp-containment/extract_prepared_c.py',
            source.ROOT/'package/qca-nss/qca-ssdk/Makefile']
    source.need(all(p.is_file() and not p.is_symlink() for p in inputs),'exact regular support files')
    input_hash={str(p):source.sha(p.read_bytes()) for p in inputs}
    report['inputs']=input_hash
    generated={}
    def emit(target,raw):
        relative=target.relative_to(a.output).as_posix()
        source.need(relative not in generated and not target.exists(),'unique output '+relative)
        target.parent.mkdir(parents=True,exist_ok=True)
        generated[relative]=source.sha(raw); target.write_bytes(raw)
        source.need(source.sha(target.read_bytes())==generated[relative],'output write bytes '+relative)
    def check_generated(root,expected):
        source.need(source.inventory(root)==expected,'generated exact inventory and bytes')
    def generated_controls():
        expected={'payload.c':source.sha(b'known C\n'),'program.bin':source.sha(b'known binary\n')}
        records=[]
        samples={'valid':{'payload.c':b'known C\n','program.bin':b'known binary\n'},
                 'missing':{'payload.c':b'known C\n'},
                 'changed':{'payload.c':b'changed C\n','program.bin':b'known binary\n'},
                 'extra':{'payload.c':b'known C\n','program.bin':b'known binary\n','extra.txt':b'not admitted\n'}}
        for label,files in samples.items():
            root=a.output/'generated-controls'/label
            for name,raw in files.items(): emit(root/name,raw)
            try: check_generated(root,expected)
            except ValueError as error:
                source.need(label!='valid' and str(error)=='generated exact inventory and bytes','precise inventory rejection')
                records.append([label,'REJECTED'])
            else:
                source.need(label=='valid','polluted output inventory accepted'); records.append([label,'ACCEPTED'])
        return {'classification':'ACTUAL_FILE_INVENTORY_CONTROLS_NOT_SOURCE_MUTANTS','records':records}
    def save(): (a.output/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    def invoke(label,command,cwd=None,code=97):
        env=dict(os.environ,ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}',
                 UBSAN_OPTIONS=f'halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode={code}')
        row={'label':label,'command':[str(x) for x in command],
             'ASAN_OPTIONS':env['ASAN_OPTIONS'],'UBSAN_OPTIONS':env['UBSAN_OPTIONS']}
        try:
            p=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
            row.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
        except subprocess.TimeoutExpired as e:
            row.update(returncode=None,timeout=True,stdout=str(e.stdout or ''),stderr=str(e.stderr or ''))
        report['commands'].append(row)
        dest=a.output/'logs'/label; dest.parent.mkdir(parents=True,exist_ok=True)
        for stream in ('stdout','stderr'): emit(dest.with_suffix('.'+stream),row[stream].encode())
        emit(dest.with_suffix('.json'),(json.dumps(row,indent=2)+'\n').encode()); save(); return row
    def compile_program(label,text,phy):
        path=a.output/'native'/label; path.mkdir(parents=True)
        files={'actual.c':text,'fixture.c':(SUPPORT/'fixture.c').read_text(),
               'model.h':(SUPPORT/'model.h').read_text(),
               'vendor-errors.h':(a.prepared/source.ERRORS).read_text(),
               'vendor-constants.h':source.constants(a.prepared),
               'ssdk_phy_i2c.h':(a.prepared/source.HEADER).read_text()}
        for name in ('sw.h','ssdk_init.h','ssdk_plat.h','hsl_phy.h','linux/i2c.h'):
            files[name]='#include "model.h"\n'
        for name,raw in files.items():
            emit(path/name,raw.encode())
        flags=['-std=c11','-O1','-g','-Wall','-Werror','-fno-omit-frame-pointer']
        if phy: flags+=['-DIN_PHY_I2C_MODE']
        if a.sanitize: flags+=['-fsanitize=address,undefined']
        binary=path/'program.host'
        row=invoke(label+'/compile',[a.cc,*flags,'-I',str(path),str(path/'fixture.c'),'-o',str(binary)])
        source.need(row['returncode']==0 and not row['stdout'] and not row['stderr'],'clean compile '+label)
        observed=source.inventory(path)
        compiled=set(observed)-set(files)
        symbols={'program.host.dSYM/Contents/Info.plist','program.host.dSYM/Contents/Resources/DWARF/program.host',
                 'program.host.dSYM/Contents/Resources/Relocations/aarch64/program.host.yml'}
        source.need('program.host' in compiled and compiled <= {'program.host'}|symbols,'exact compiler output paths')
        for name in compiled:
            relative=(path/name).relative_to(a.output).as_posix()
            source.need(relative not in generated,'compiler output overwrites known file')
            generated[relative]=observed[name]
        source.need(observed=={name:generated[(path/name).relative_to(a.output).as_posix()] for name in observed},
                    'compiler changed emitted source or header')
        return binary
    save()
    try:
        before,after,declared=source.prepare(a.baseline,a.prepared,a.output,a.patch_tool,invoke)
        generated.update({'roundtrip38/'+name:digest for name,digest in after.items()})
        report.update(baseline=before,prepared=after,declared_context=declared)
        report['generated_controls']=generated_controls()
        code=(a.prepared/source.C).read_text(); old=(a.baseline/source.C).read_text()
        source.need(len(source.MUTANTS)==15 and len({r[0] for r in source.MUTANTS})==15,'fixed15 mutation definitions')
        for phy,profile in ((False,'data'),(True,'phy')):
            cases=DATA+(PHY if phy else ())
            controls=[r for r in source.MUTANTS if phy or not r[-1]]
            source.need(len(cases)==(20 if phy else 12) and len(controls)==(15 if phy else 8),'fixed profile obligations')
            binary=compile_program(profile+'/fixed',code,phy)
            for case in cases:
                row=invoke(profile+'/fixed/'+case,[str(binary),case])
                source.need(exact_positive(row,case),
                            'exact positive '+profile+'/'+case)
                report['positive'].append([profile,case])
            for name,fn,anchor,replacement,case,marker,_ in controls:
                mutated=source.replace_function(code,fn,anchor,replacement)
                program=compile_program(profile+'/mutant-'+name,mutated,phy)
                row=invoke(profile+'/mutant-'+name+'/run',[str(program),case])
                source.need(exact_negative(row,marker),
                            'precise semantic negative '+profile+'/'+name)
                report['negative'].append([profile,name,case,marker])
            old_program=compile_program(profile+'/old37',old,phy)
            witnesses=[('data-reference','REFERENCE_BALANCE'),('short-read','READ_FAILURE')]
            if phy: witnesses += [('phy-errors','PHY_FAILURE_PROPAGATION'),('mmd-result','MMD_SIGNED_RESULT')]
            for case,marker in witnesses:
                row=invoke(profile+'/old37/'+case,[str(old_program),case])
                source.need(exact_negative(row,marker),
                            'precise old source witness '+profile+'/'+case)
                report['baseline_witnesses'].append([profile,case,marker])
            if a.sanitize:
                for name,exitcode,diagnostic in (('asan-canary',97,'ERROR: AddressSanitizer: heap-buffer-overflow'),
                                                 ('ubsan-canary',98,'runtime error: signed integer overflow:')):
                    row=invoke(profile+'/'+name,[str(binary),name],code=exitcode)
                    source.need(row['returncode']==exitcode and diagnostic in row['stderr'],'sanitizer activation '+profile+'/'+name)
        source.need(len(report['positive'])==32 and len(report['negative'])==23 and
                    len(report['baseline_witnesses'])==6,'complete fixed obligations')
        source.need(all(source.sha(Path(p).read_bytes())==h for p,h in input_hash.items()),'end input stability')
        source.need(source.inventory(a.baseline)==before and source.inventory(a.prepared)==after,'end tree stability')
        observed=source.inventory(a.output); observed.pop('RESULTS.json',None)
        source.need(observed==generated,'generated exact inventory and bytes')
        report.update(status='PASS_HOST_I2C_IO_ONLY',end_input_stability=True,
                      generated=generated,generated_excludes=['RESULTS.json'])
    except Exception as error: report['error']=str(error)
    save()
    print(json.dumps({'status':report['status'],'error':report.get('error'),
                      'positive':len(report['positive']),'negative':len(report['negative']),
                      'old_witnesses':len(report['baseline_witnesses'])}))
    return 0 if report['status']=='PASS_HOST_I2C_IO_ONLY' else 1

if __name__=='__main__': sys.exit(main())
