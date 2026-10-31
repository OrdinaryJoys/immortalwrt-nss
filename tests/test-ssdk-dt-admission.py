#!/usr/bin/env python3
"""DT23 fresh native model. No target build or historical program execution."""
import argparse
import copy
import errno
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-dt-admission'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import variants, once

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-dt-admission')
OLD = AUDIT.parents[1] / '20261030/ssdk-dp-retirement'
PROFILES = {'modern': ['-DCONFIG_OF=1'], 'oldof': ['-DCONFIG_OF=1', '-DTEST_OLD_VERSION=1'], 'noof': []}


def save(path, value):
    raw=(json.dumps(value, indent=2)+'\n').encode()
    path.write_bytes(raw)
    return raw


def record_json(path,value,generated):
    generated[str(path)]=source.digest(save(path,value))


def expected_tail(root,expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')),'output-symlink')
    actual={str(p) for p in root.rglob('*.expected') if p.is_file()}
    source.require(actual==set(expected),'expected-inventory')
    for name,sha in expected.items():
        source.require(source.identity(name)==sha,'expected-memory-hash')


def generated_tail(root,generated):
    actual={str(p) for p in root.rglob('*') if p.is_file() and
            p!=root/'RESULTS.json' and not p.is_relative_to(root/'fresh23')}
    source.require(actual==set(generated),'generated-inventory')
    for name,sha in generated.items():source.require(source.identity(name)==sha,'generated-memory-hash')


def expectation_controls(out):
    folder=out/'oracle-controls';folder.mkdir()
    p=folder/'valid.expected';raw=b'ALPHA\nBETA\n';p.write_bytes(raw)
    expected={str(p):source.digest(raw)};generated=dict(expected)
    valid=0;rejected=[]
    def valid_state():
        nonlocal valid
        expected_tail(folder,expected);generated_tail(folder,generated);valid+=1
    def reject(name,action,restore,marker,gate=expected_tail):
        action()
        try:gate(folder,expected)
        except RuntimeError as error:source.require(str(error)==marker,'pollution-wrong-gate')
        else:raise RuntimeError('pollution-accepted:'+name)
        rejected.append(name);restore();valid_state()
    valid_state()
    reject('modified',lambda:p.write_bytes(b'ALPHA\nCHANGED\n'),lambda:p.write_bytes(raw),'expected-memory-hash')
    reject('truncated',lambda:p.write_bytes(raw[:-1]),lambda:p.write_bytes(raw),'expected-memory-hash')
    reject('deleted',lambda:p.unlink(),lambda:p.write_bytes(raw),'expected-inventory')
    renamed=folder/'renamed.data'
    reject('renamed',lambda:p.rename(renamed),lambda:renamed.rename(p),'expected-inventory')
    extra=folder/'extra.expected'
    reject('extra-expected',lambda:extra.write_bytes(raw),lambda:extra.unlink(),'expected-inventory')
    extra=folder/'unlisted.c'
    reject('extra-generated',lambda:extra.write_bytes(b'foreign'),lambda:extra.unlink(),'generated-inventory',generated_tail)
    nested=folder/'rogue';nested.mkdir();extra=nested/'RESULTS.json'
    reject('nested-rogue-results',lambda:extra.write_bytes(b'foreign'),lambda:extra.unlink(),'generated-inventory',generated_tail)
    nested.rmdir()
    allowed=folder/'RESULTS.json';allowed.write_bytes(b'explicitly excluded root report');valid_state();allowed.unlink()
    p.unlink();folder.rmdir()
    return {'valid':valid,'rejects':len(rejected),'names':rejected,
            'root_results_only_exception_verified':True,'truth':'digest of in-memory oracle, not read-back file'}


def node(index, **changes):
    n = dict(present=1, enabled=1, id_len=4, id=index, id_error=0, mode='local bus',
             mode_error=0, reg_len=8, reg_error=0, emulation=0, compatible='qcom,ess-switch-ipq807x')
    n.update(changes)
    return n


def case(name, flow='topology', count=1, **changes):
    c = dict(name=name, flow=flow, instance=1, count_len=4, declared=count, count_error=0,
             fault=0, foreign=0, mutate=0, arg=0, private_error=0,
             nodes=[node(i) for i in range(3)], profiles=['modern'])
    c.update(changes)
    return c


def cases():
    rows = []
    for n in range(4):
        for flow in ('topology', 'root'):
            rows.append(case(f'{flow}-{n}-ok', flow, n, profiles=['modern'] if flow == 'root' else ['modern', 'oldof']))
            for f in range(1, n + 2):
                rows.append(case(f'{flow}-{n}-fault-{f}', flow, n, fault=f, profiles=['modern', 'oldof'], private_error=-errno.ENOMEM if flow == 'root' else 0))
        rows += [case(f'root-{n}-private-failure', 'root', n, private_error=-errno.ENOMEM, profiles=['modern', 'oldof']),
                 case(f'parse-{n}', 'parse', n)]
        disabled = [node(i, enabled=0, id_len=1, id=4294967295, mode=None, reg_len=0) for i in range(3)]
        rows.append(case(f'disabled-{n}', count=n, nodes=disabled, profiles=['modern', 'oldof']))
    rows += [case('default-no-instance', instance=0, count=4294967295),
             case('default-no-count', count_len=-1, count=4294967295),
             case('count-extra', count_len=8, profiles=['modern', 'oldof']),
             case('count-over-four', count=4, profiles=['modern', 'oldof']),
             case('count-max', count=4294967295, profiles=['modern', 'oldof']),
             case('count-error', count_error=-errno.EIO, profiles=['modern', 'oldof'])]
    for length in (0, 1, 2, 3):
        rows.append(case(f'count-short-{length}', count_len=length, profiles=['modern', 'oldof']))
    for foreign in (1, 2, 3):
        for flow in ('topology', 'root'):
            rows.append(case(f'{flow}-foreign-{foreign}', flow, count_len=0, foreign=foreign,
                             profiles=['modern', 'oldof', 'noof']))
    for length in (-1, 0, 1, 2, 3, 4, 8):
        rows.append(case(f'id-length-{length}', nodes=[node(0, id_len=length), node(1), node(2)]))
        rows.append(case(f'direct-id-length-{length}', 'id', nodes=[node(0, id_len=length), node(1), node(2)]))
    for value, count, label in [(1, 1, 'dynamic'), (3, 3, 'both'), (3, 4, 'fixed-only'), (4294967295, 3, 'max'), (0, 0, 'zero')]:
        rows.append(case('direct-id-' + label, 'id', count, nodes=[node(0, id=value), node(1), node(2)]))
        if count <= 3 and count:
            rows.append(case('id-' + label, count=count, nodes=[node(0, id=value), node(1), node(2)]))
    rows += [case('id-read-error', nodes=[node(0, id_error=-errno.EIO), node(1), node(2)]),
             case('duplicate', count=2, nodes=[node(0), node(1, id=0), node(2)]),
             case('duplicate-default', count=2, nodes=[node(0, id_len=-1), node(1, id_len=-1), node(2)]),
             case('permutation-2', 'parse', 2, nodes=[node(0, id=1), node(1, id=0), node(2)]),
             case('permutation-3', 'parse', 3, nodes=[node(0, id=2), node(1, id=0), node(2, id=1)]),
             case('missing-first', nodes=[node(0, present=0), node(1), node(2)]),
             case('missing-later', count=3, nodes=[node(0), node(1, present=0), node(2)]),
             case('disabled-malformed', 'parse', 3, nodes=[node(0), node(1, enabled=0, id_len=1, id=4294967295, mode=None), node(2)])]
    for mode, need in [('local bus', 8), ('pcie bus', 4)]:
        label = mode.split()[0]
        for length in (-1, 0, 1, 3, 4, 7, 8, 12):
            rows.append(case(f'{label}-reg-{length}', 'parse', nodes=[node(0, mode=mode, reg_len=length), node(1), node(2)]))
        rows.append(case(label + '-reg-error', nodes=[node(0, mode=mode, reg_len=need, reg_error=-errno.EIO), node(1), node(2)]))
    for mode, label in [('mdio', 'mdio'), ('unknown', 'unknown'), ('', 'empty')]:
        rows.append(case('mode-' + label, 'parse', nodes=[node(0, mode=mode, reg_len=-1), node(1), node(2)]))
    rows += [case('mode-missing', nodes=[node(0, mode=None), node(1), node(2)]),
             case('mode-string-error', nodes=[node(0, mode_error=-errno.EILSEQ), node(1), node(2)]),
             case('later-mode-error', count=2, nodes=[node(0), node(1, mode_error=-errno.EILSEQ), node(2)]),
             case('mutation-cache', 'parse', 3, mutate=1,
                  nodes=[node(0, id=2), node(1, id=0, mode='pcie bus', reg_len=4), node(2, id=1, mode='unknown')]),
             case('parse-emulation', 'parse', nodes=[node(0, emulation=1), node(1), node(2)])]
    for compatible, label in [('qcom,ess-switch', 'dess-unselected'), ('qcom,ess-switch-ipq50xx', 'mp-unselected'),
                               ('qcom,ess-switch-qca83xx', 'qca83'), ('unsupported', 'unknown')]:
        rows.append(case('compatible-' + label, 'parse', nodes=[node(0, compatible=compatible), node(1), node(2)]))
    for arg, label in [(1, 'null-cfg'), (2, 'null-id'), (3, 'outside')]:
        rows.append(case('parse-bad-' + label, 'parsebad', arg=arg))
    rows.append(case('parse-bad-zero', 'parsebad', 0, arg=3))
    for label, patch in [('ok', {}), ('disabled', {'enabled': 0}), ('missing', {'present': 0})]:
        rows.append(case('lookup-' + label, 'lookup', 0, nodes=[node(0, **patch), node(1), node(2)]))
    rows += [case('lookup-null-out', 'lookup', 0, arg=1), case('lookup-outside', 'lookup', 3),
             case('access-valid', 'access'), case('access-pcie', 'access', nodes=[node(0, mode='pcie bus', reg_len=4), node(1), node(2)]),
             case('access-missing', 'access', nodes=[node(0, mode=None), node(1), node(2)]),
             case('access-short', 'access', nodes=[node(0, reg_len=4), node(1), node(2)])]
    for n in (0, 1, 2, 3, 4294967295):
        rows.append(case(f'noof-default-{n}', count=n, profiles=['noof']))
    for fault in (1, 2):
        rows.append(case(f'noof-fault-{fault}', count=0, fault=fault, profiles=['noof']))
        rows.append(case(f'noof-root-fault-{fault}', 'root', 0, fault=fault, private_error=-errno.ENOMEM, profiles=['noof']))
    rows.append(case('noof-root-private-failure', 'root', 0, private_error=-errno.ENOMEM, profiles=['noof']))
    rows.append(case('oldraw-guard', 'oldraw', nodes=[node(0, id=4294967295), node(1), node(2)]))
    source.require(len({c['name'] for c in rows}) == len(rows), 'unique-case-names')
    return rows


def typed_error(length, need, error=0):
    return error or (-errno.EINVAL if length < 0 else -errno.ENODATA if length == 0 else
                     -errno.EOVERFLOW if length < need * 4 else 0)


def id_result(n, count):
    if n['id_len'] >= 0:
        if n['id_len'] != 4: return -errno.EINVAL
        if n['id_error']: return n['id_error']
    value = n['id'] if n['id_len'] >= 0 else 0
    return -errno.EINVAL if value >= count or value >= 3 else 0


def access_result(n):
    if n['mode_error']: return n['mode_error']
    if n['mode'] is None: return -errno.EINVAL
    need = 2 if n['mode'] == 'local bus' else 1 if n['mode'] == 'pcie bus' else 0
    return typed_error(n['reg_len'], need, n['reg_error']) if need else 0


def admission(c, profile):
    if c['foreign']: return -errno.EBUSY, 1
    if profile == 'noof': return 0, 1
    count = c['declared'] if c['instance'] and c['count_len'] >= 0 else 1
    if c['instance'] and c['count_len'] >= 0:
        ret = typed_error(c['count_len'], 1, c['count_error'])
        if ret: return ret, count
    if count > 3: return -errno.EINVAL, count
    if profile != 'modern': return 0, count
    seen = set()
    for n in c['nodes'][:count]:
        if not n['present']: return -errno.EINVAL, count
        if not n['enabled']: continue
        ret = id_result(n, count)
        if ret: return ret, count
        value = n['id'] if n['id_len'] >= 0 else 0
        if value in seen: return -errno.EINVAL, count
        seen.add(value)
        ret = access_result(n)
        if ret: return ret, count
    return 0, count


def oracle(c, profile, sdk):
    events = []; live = []; owned = []; modern = profile == 'modern'
    add = events.append

    def lookup(num):
        if c['instance']: add('FIND I 1\n')
        else: add('FIND I 0\n')
        present = num < 3 and c['nodes'][num]['present']
        add(f'FIND N {num} {int(bool(present))}\n')
        if c['instance']: add('PUT I\n')
        if not present: add('WARN MISSING\n'); return sdk['SW_BAD_PARAM']
        enabled = c['nodes'][num]['enabled']; add(f'AVAILABLE {num} {int(bool(enabled))}\n')
        if not enabled:
            add('WARN DISABLED\n'); add(f'PUT N {num}\n'); return sdk['SW_DISABLE']
        return 0

    def read_id(num, count):
        n = c['nodes'][num]; add(f'PROP N {num} {n["id_len"]}\n')
        if n['id_len'] == 4:
            ret = typed_error(4, 1, n['id_error']); add(f'READ N {num} {ret} {0 if ret else n["id"]}\n')
        return id_result(n, count)

    def access(num):
        n = c['nodes'][num]; ret = n['mode_error'] or (-errno.EINVAL if n['mode'] is None else 0)
        add(f'STRING {num} {ret}\n')
        if ret: return ret
        need = 2 if n['mode'] == 'local bus' else 1 if n['mode'] == 'pcie bus' else 0
        if need:
            ret = typed_error(n['reg_len'], need, n['reg_error']); add(f'ARRAY {num} {need} {ret}\n')
        return ret

    def free(ids):
        for ident in ids:
            source.require(ident in live, 'oracle-owned-release'); live.remove(ident); add(f'FREE {ident}\n')

    def put_owned():
        for num in owned: add(f'PUT N {num}\n')
        owned.clear()

    def retire(count, mapping):
        add('MODEL_RETIRE\n')
        for d in range(count):
            if d in mapping:
                num = mapping[d]; add(f'PUT N {num}\n'); owned.remove(num)
            free([d + 2])
        free([1]); add('EXIT AGAIN\n')

    f = c['flow']; pure, count = admission(c, profile)
    if f == 'lookup':
        ret = sdk['SW_BAD_PARAM'] if c['arg'] else lookup(c['declared'])
        add(f'LOOKUP {ret}\n')
        if not ret: add(f'PUT N {c["declared"]}\n')
    elif f == 'id':
        ret = read_id(0, c['declared'])
        add(f'ID {ret} {1234 if ret else c["nodes"][0]["id"] if c["nodes"][0]["id_len"] >= 0 else 0}\n')
    elif f == 'access':
        ret = access(0)
        if not ret: add('REFERENCE 0 OK\n')
        add(f'ACCESS {ret}\n')
    elif f == 'oldraw':
        return 0, pure, b''
    else:
        ret = 0
        if c['foreign']: ret = -errno.EBUSY
        else:
            if profile == 'noof': add('OF_STUB NULL\n')
            else:
                add(f'FIND I {c["instance"]}\n')
                if c['instance']:
                    add(f'PROP I {c["count_len"]}\n')
                    if c['count_len'] >= 0:
                        ret = typed_error(c['count_len'], 1, c['count_error'])
                        add(f'READ I {ret} {0 if ret else c["declared"]}\n')
                    add('PUT I\n')
            if not ret and count > 3: ret = -errno.EINVAL
            seen = set()
            if modern and not ret:
                for num in range(count):
                    r = lookup(num)
                    if r == sdk['SW_DISABLE']: continue
                    if r: ret = -errno.EINVAL; break
                    owned.append(num)
                    ret = read_id(num, count)
                    if ret: break
                    n = c['nodes'][num]; ident = n['id'] if n['id_len'] >= 0 else 0
                    if ident in seen: ret = -errno.EINVAL; break
                    seen.add(ident); ret = access(num)
                    if ret: break
            if ret:
                put_owned()
            else:
                for index in range(count + 1):
                    ident = index + 1; ok = ident != c['fault']
                    add(f'ALLOC {ident} {"V" if index == 0 else "C"} {int(ok)}\n')
                    if not ok:
                        ret = -errno.ENOMEM; free(list(reversed(live))); put_owned(); break
                    live.append(ident)
        mapping = {}
        if not ret and modern:
            mapping = {(n['id'] if n['id_len'] >= 0 else 0): i for i, n in enumerate(c['nodes'][:count]) if n['enabled']}
        if f == 'root' and not ret:
            add(f'PRIVATE {count} {c["private_error"]}\n')
            if c['private_error']:
                for d in range(count):
                    if d in mapping: num=mapping[d]; add(f'PUT N {num}\n'); owned.remove(num)
                    free([d+2])
                free([1]); ret=c['private_error']
            elif count:
                source.require(modern, 'fallback-root-success-not-selected'); add('CFG LEAF\n'); add('STOP DT\n')
            else: add('STOP ZERO_SYSFS\n')
        add(f'INIT {ret}\n')
        if not ret:
            for d in range(count):
                num = mapping.get(d, -1); mode, base, size, pcie = 'mdio', 0, 0, 0
                if num >= 0:
                    n=c['nodes'][num]
                    if n['mode']=='local bus': mode,base,size='local',0xa100+num*0x100,0x1000+num*17
                    elif n['mode']=='pcie bus': mode,pcie='pcie',0xa100+num*0x100
                add(f'CFG {d} {num} {mode} {base} {size} {pcie}\n')
            if modern:
                for num in range(3):
                    enabled=num<count and c['nodes'][num]['enabled']; n=c['nodes'][num]
                    ident=(n['id'] if n['id_len']>=0 else 0) if enabled else 0
                    add(f'MAP {num} {int(bool(enabled))} {ident}\n')
            if f=='parse':
                for num,n in enumerate(c['nodes'][:count]):
                    if n['enabled']: add(f'REFERENCE {num} OK\n')
                if c['mutate']: add('PROPERTIES REPLACED\n')
                for num,n in enumerate(c['nodes'][:count]):
                    ident=n['id'] if n['id_len']>=0 else 0
                    if n['enabled']:
                        emulation=bool(c['mutate'] or n['emulation']);add(f'BOOL {num} {int(emulation)}\n')
                        if emulation:add('LOG EMULATION\n')
                        if n['mode']=='pcie bus':add('LOG PCIE\n')
                        for label in ['MAC','MDIO','BMP','IRQ','LED']:add(f'LEAF {label} {num} {ident}\n')
                        if n['compatible'] in ['qcom,ess-switch-ipq807x','qcom,ess-switch-ipq95xx','qcom,ess-switch-ipq60xx','qcom,ess-switch-ipq53xx','qcom,ess-switch-ipq54xx']:
                            for label in ['UNIPHY','SCHED']:add(f'LEAF {label} {num} {ident}\n')
                            add(f'LEAF INTF {num}\n');add(f'CLOCK {num}\n')
                            add(f'TICK {num} tm_tick_mode {31+num}\n');add(f'TICK {num} bm_tick_mode {41+num}\n')
                        elif n['compatible']=='qcom,ess-switch-qca83xx':add('LOG QCA83\n')
                        elif n['compatible'] not in ['qcom,ess-switch','qcom,ess-switch-ipq50xx','qcom,ess-switch-qca8386']:add('WARN COMPAT\n')
                        hppe=n['compatible'] in ['qcom,ess-switch-ipq807x','qcom,ess-switch-ipq95xx','qcom,ess-switch-ipq60xx','qcom,ess-switch-ipq53xx','qcom,ess-switch-ipq54xx']
                        add(f'STATE {num} {int(emulation)} {31+num if hppe else 0} {41+num if hppe else 0} {"clock-token" if hppe else "clock-error"} 0\n')
                        add(f'PARSE {num} 0 {ident}\n')
                    else:add(f'PARSE {num} {sdk["SW_DISABLE"]} 1234\n')
            if f=='parsebad':add(f'PARSE_BAD {sdk["SW_BAD_PARAM"]}\n')
            add('REENTRY BUSY\n');retire(count,mapping)
    source.require(not live and not owned, 'oracle-final-ledger')
    add('END CLEAN\n')
    return ret, pure, ''.join(events).encode()


def header(rows):
    fields=['name','flow','instance','count_len','declared','count_error','fault','foreign','mutate','arg','private_error']
    nfields=['present','enabled','id_len','id','id_error','mode','mode_error','reg_len','reg_error','emulation','compatible']
    def value(v):return 'NULL' if v is None else json.dumps(v) if isinstance(v,str) else str(v)+'u' if v>2147483647 else str(v)
    lines=['static const struct input inputs[]={']
    for c in rows:
        text='{'+','.join('.'+k+'='+value(c[k]) for k in fields)+',.nodes={'
        text+=','.join('{'+','.join('.'+k+'='+value(n[k]) for k in nfields)+'}' for n in c['nodes'])+'}},'
        lines.append(text)
    return '\n'.join(lines+['};\n'])


def positive(code,out,err,expected):source.require(code==0 and out==expected and err==b'','positive-exact-trace')
def negative(code,out,err,marker):source.require(code==86 and out==b'' and err==f'SSDK_DT {marker}\n'.encode(),'negative-exact-marker')


def gate_controls():
    positive(0,b'x\n',b'',b'x\n');negative(86,b'',b'SSDK_DT X\n','X')
    rejected=0
    rows=[(1,b'x\n',b'',b'x\n'),(0,b'x\nnoise',b'',b'x\n'),(0,b'x\n',b'diagnostic',b'x\n')]
    for row in rows:
        try:positive(*row)
        except RuntimeError:rejected+=1
        else:raise RuntimeError('positive-gate-pollution')
    for code,out,err in [(1,b'',b'SSDK_DT X\n'),(-6,b'',b'SSDK_DT X\n'),(None,b'',b'SSDK_DT X\n'),
                         (86,b'noise',b'SSDK_DT X\n'),(86,b'',b'SSDK_DT Y\n'),
                         (86,b'',b'SSDK_DT X\nSSDK_DT X\n'),(86,b'',b'SSDK_DT X\nERROR: AddressSanitizer\n')]:
        try:negative(code,out,err,'X')
        except RuntimeError:rejected+=1
        else:raise RuntimeError('negative-gate-pollution')
    return {'valid':2,'rejects':rejected}


def invoke(argv,prefix,env,generated):
    command=prefix.with_suffix('.command.json');record_json(command,{'argv':argv,'environment':{k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}},generated)
    try:p=subprocess.run(argv,capture_output=True,env=env,timeout=60)
    except subprocess.TimeoutExpired as e:
        prefix.with_suffix('.stdout').write_bytes(e.stdout or b'');prefix.with_suffix('.stderr').write_bytes(e.stderr or b'');
        save(prefix.with_suffix('.exit.json'),{'returncode':None,'timeout':True});raise RuntimeError('timeout-not-negative-credit') from e
    prefix.with_suffix('.stdout').write_bytes(p.stdout);generated[str(prefix.with_suffix('.stdout'))]=source.digest(p.stdout)
    prefix.with_suffix('.stderr').write_bytes(p.stderr);generated[str(prefix.with_suffix('.stderr'))]=source.digest(p.stderr)
    record_json(prefix.with_suffix('.exit.json'),{'returncode':p.returncode,'timeout':False},generated)
    return p


def compile_c(cc,flags,text,prefix,env,generated):
    path=prefix.with_suffix('.c');binary=prefix.with_suffix('.bin');path.write_text(text);generated[str(path)]=source.digest(text.encode())
    p=invoke([cc,*flags,str(path),'-o',str(binary)],prefix.with_name(prefix.name+'-compile'),env,generated)
    source.require(p.returncode==0 and p.stdout==p.stderr==b'','clean-compile:'+str(prefix));generated[str(binary)]=source.identity(binary)
    bundle=Path(str(binary)+'.dSYM')
    if bundle.exists():
        required={bundle/'Contents/Info.plist',bundle/'Contents/Resources/DWARF'/binary.name}
        arch={'arm64':'aarch64','aarch64':'aarch64','x86_64':'x86_64'}.get(platform.machine())
        source.require(arch is not None,'compiler-debug-host-architecture')
        relocation=bundle/'Contents/Resources/Relocations'/arch/(binary.name+'.yml')
        allowed=required|{relocation}
        members=list(bundle.rglob('*'))
        source.require(bundle.is_dir() and not any(q.is_symlink() for q in members),'compiler-debug-directory')
        files={q for q in members if q.is_file()}
        source.require(required<=files<=allowed,'compiler-debug-shape')
        for q in sorted(files):generated[str(q)]=source.identity(q)
    return binary


def san_env(env,code):
    env=dict(env);env['ASAN_OPTIONS']=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    env['UBSAN_OPTIONS']=f'halt_on_error=1:print_stacktrace=1:exitcode={code}';return env


def canaries(cc,flags,out,env,generated):
    result=[]
    for name,code,text,diagnostic in [
        ('asan',97,'#include <stdlib.h>\nint main(int n,char**v){(void)v;volatile int i=n;char*p=malloc(1);p[i]=1;volatile char x=p[i];free(p);return x;}\n',b'ERROR: AddressSanitizer: heap-buffer-overflow'),
        ('ubsan',98,'#include <limits.h>\nint main(int n,char**v){(void)v;volatile int x=INT_MAX;return x+n;}\n',b'runtime error: signed integer overflow')]:
        binary=compile_c(cc,flags,text,out/('canary-'+name),env,generated);used=san_env(env,code)
        p=invoke([str(binary)],out/('canary-'+name+'-run'),used,generated)
        source.require(p.returncode==code and p.stdout==b'' and diagnostic in p.stderr,'canary-activation:'+name)
        result.append({'name':name,'exit':code,'environment':{k:used[k] for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'PHY-PREALLOC-CANDIDATE-20261030-r2')
    p.add_argument('--candidate',type=Path,default=OLD/'DT-ADMISSION-CANDIDATE-20261031-r1')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true');args=p.parse_args()
    out=args.output.resolve();source.require(out.parent==AUDIT and out.name.startswith('DT-TEST-') and not out.exists(),'fresh-output');out.mkdir(parents=True)
    result={'status':'INCOMPLETE','qualification':'HOST_MODEL_ONLY_DT_ADMISSION','positives':[],'negatives':[],
            'open':['Linux OF/target ABI/concurrent property writers','actual23 PHY combination/private allocator','MDIO/SFP/FAL/clock resource or post-DT rollback','LSan']}
    inputs=None;generated={}
    try:
        tree,inputs=source.prepare(args.base.resolve(),args.candidate.resolve(),out);record_json(out/'INPUTS.json',inputs,generated)
        result['gate_controls']=gate_controls()
        result['expectation_controls']=expectation_controls(out)
        errors=(tree/'include/common/sw_error.h').read_text();sdk={k:int(v) for k,v in re.findall(r'\b(SW_\w+)\s*=\s*(-?\d+)',errors)}
        source.require(all(k in sdk for k in ['SW_BAD_PARAM','SW_DISABLE','SW_OK']),'actual-sdk-errors')
        matrix=cases();case_path=out/'cases.h';case_text=header(matrix);case_path.write_text(case_text);generated[str(case_path)]=source.digest(case_text.encode());record_json(out/'MATRIX.json',matrix,generated)
        text,new,old=source.render(tree,args.base/'prepared',(SUPPORT/'fixture.c').read_text().replace('@CASES_PATH@',str(case_path)))
        record_json(out/'EXTRACTED.json',{'candidate':new['records'],'baseline':old['records'],
             'reference_transform':'complete old access body; only function name changed and strcmp scoped to void-pointer primitive wrapper; not old header ABI',
             'root':'complete body compiled; private allocator/cfg/topology-later services explicit leaves; DT call macro aliases stop boundary',
             'trace':'complete MODEL action/argument/field/owner trace, not raw driver formatted logs'},generated)
        cc=shutil.which(args.cc);source.require(cc is not None,'compiler-path');cc=str(Path(cc).resolve());result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function']
        env=dict(os.environ);env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        result['compiler_debug_policy']='optional exact binary.dSYM bundle; required Info.plist and DWARF/binary; optional host-architecture Relocations/arch/binary.yml only, opaque compiler outputs; unknown members rejected'
        version=invoke([cc,'--version'],out/'compiler-version',env,generated);source.require(version.returncode==0 and version.stderr==b'','compiler-version')
        if args.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        byname={c['name']:(i,c) for i,c in enumerate(matrix)};expected_files={}
        for profile,pf in PROFILES.items():
            folder=out/profile;folder.mkdir();binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for i,c in enumerate(matrix):
                if profile not in c['profiles'] or c['flow']=='oldraw':continue
                ret,admit,expected=oracle(c,profile,sdk);ep=folder/(c['name']+'.expected');ep.write_bytes(expected)
                expected_files[str(ep)]=source.digest(expected);generated[str(ep)]=source.digest(expected)
                run=invoke([str(binary),str(i),str(ret),str(admit)],folder/c['name'],env,generated)
                positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append({'profile':profile,'case':c['name'],'stdout_sha256':source.digest(run.stdout)})
            if not args.positives_only:
                if profile=='modern':
                    i,c=byname['disabled-2'];ret,admit,expected=oracle(c,profile,sdk)
                    polluted=once(text,'/* MODEL_OWNER_SHAPE_INJECTION */','blocks[1].bytes++;')
                    binary_bad=compile_c(cc,flags+pf,polluted,folder/'model-owner-shape',env,generated)
                    run=invoke([str(binary_bad),str(i),str(ret),str(admit)],folder/'model-owner-shape-run',env,generated)
                    negative(run.returncode,run.stdout,run.stderr,'SLOT_IDENTITY_SHAPE')
                    bypass=once(polluted,' && owner->bytes==sizeof(ssdk_dt_cfg)','')
                    binary_bypass=compile_c(cc,flags+pf,bypass,folder/'model-owner-shape-gate-removed',env,generated)
                    run=invoke([str(binary_bypass),str(i),str(ret),str(admit)],folder/'model-owner-shape-gate-removed-run',env,generated)
                    positive(run.returncode,run.stdout,run.stderr,expected)
                    result['model_quality_controls']={'ledger_shape_rejected':1,'same_payload_trace_accepted_after_removing_only_shape_gate':1,
                        'classification':'harness allocation-ledger byte-size record pollution, NOT production mutation or actual allocation-size failure; no claim slot swaps would evade the full trace'}
                for v in variants(new,old,profile):
                    mutated=once(text,v['before'],v['after']);mb=compile_c(cc,flags+pf,mutated,folder/v['name'],env,generated)
                    i,c=byname[v['case']];ret,admit,_=oracle(c,profile,sdk)
                    run=invoke([str(mb),str(i),str(ret),str(admit)],folder/(v['name']+'-run'),env,generated)
                    negative(run.returncode,run.stdout,run.stderr,v['marker']);result['negatives'].append({k:v[k] for k in ['name','symbol','case','marker','classification']}|{'profile':profile,'source_sha256':source.digest(mutated.encode())})
                if profile=='modern':
                    i,c=byname['oldraw-guard'];run=invoke([str(binary),str(i),'0','0'],folder/'oldraw-boundary-run',env,generated)
                    negative(run.returncode,run.stdout,run.stderr,'OLD_RAW_ID_GUARD')
                    result['negatives'].append({'profile':profile,'name':'oldraw-instrumented-boundary','classification':'complete old parser with fail-fast raw-ID boundary, NOT actual OOB reproduction','marker':'OLD_RAW_ID_GUARD'})
            save(out/'RESULTS.json',result)
        result['end_input_stability']=source.stable(inputs)
        expected_tail(out,expected_files);generated_tail(out,generated)
        result['expected_tail']='EXACT_PATH_INVENTORY_AND_MEMORY_ORACLE_DIGEST'
        result['generated_tail']='EXACT_FILE_INVENTORY_AND_BOUND_BYTES_EXCLUDING_ONLY_RESULTS_AND_SEPARATELY_VERIFIED_FRESH692'
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler')
        result['generated_files_including_expected']=generated
        result['positive_count']=len(result['positives']);result['negative_count']=len(result['negatives'])
        result['status']='DEV_CHECKPOINT_POSITIVES_ONLY' if args.positives_only else 'HOST_MODEL_ONLY'
        result['outcome']='NOT_FINAL_QUALIFICATION' if args.positives_only else 'PASSED_WITHIN_DT_ADMISSION_MODEL'
    except Exception as e:result['status']='FAILED';result['error']=str(e);raise
    finally:save(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ['status','positive_count','negative_count']}))


if __name__=='__main__':main()
