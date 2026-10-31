#!/usr/bin/env python3
"""Fresh PORT24 native host model; not a target/root/whole-PHY qualification."""
import argparse
import copy
import errno
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
SUPPORT = Path(__file__).resolve().parent / 'ssdk-phy-port-admission'
sys.path.insert(0, str(SUPPORT))
import source
from mutations import once, variants

AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-phy-port-admission')
OLD = AUDIT.parents[1] / '20261030/ssdk-dp-retirement'
PROFILES = {'base': [], 'i2c': ['-DIN_PHY_I2C_MODE'], 'sfp': ['-DIN_SFP_PHY'],
            'i2c-sfp': ['-DIN_PHY_I2C_MODE', '-DIN_SFP_PHY']}


def save(path, data):
    raw = (json.dumps(data, indent=2) + '\n').encode()
    path.write_bytes(raw)
    return raw


def record(path, data, generated):
    generated[str(path)] = source.digest(save(path, data))


def expected_tail(root, expected):
    source.require(not any(p.is_symlink() for p in root.rglob('*')), 'output-symlink')
    source.require({str(p) for p in root.rglob('*.expected') if p.is_file()} == set(expected), 'expected-inventory')
    for n, sha in expected.items():
        source.require(source.identity(n) == sha, 'expected-memory-hash')


def generated_tail(root, generated):
    actual = {str(p) for p in root.rglob('*') if p.is_file() and p != root / 'RESULTS.json' and
              not p.is_relative_to(root / 'fresh24')}
    source.require(actual == set(generated), 'generated-inventory')
    for n, sha in generated.items():
        source.require(source.identity(n) == sha, 'generated-memory-hash')


def tail_controls(out):
    folder = out / 'tail-controls'
    folder.mkdir()
    path = folder / 'valid.expected'
    raw = b'ALPHA\nBETA\n'
    path.write_bytes(raw)
    expected = {str(path): source.digest(raw)}
    valid, rejected = 0, []

    def check():
        nonlocal valid
        expected_tail(folder, expected)
        generated_tail(folder, expected)
        valid += 1

    def reject(name, action, restore, marker, gate=expected_tail):
        action()
        try:
            gate(folder, expected)
        except RuntimeError as e:
            source.require(str(e) == marker, 'tail-control-specific-gate')
        else:
            raise RuntimeError('tail-control-accepted:' + name)
        rejected.append(name)
        restore()
        check()

    check()
    reject('modified', lambda: path.write_bytes(b'changed'), lambda: path.write_bytes(raw), 'expected-memory-hash')
    reject('truncated', lambda: path.write_bytes(raw[:-1]), lambda: path.write_bytes(raw), 'expected-memory-hash')
    reject('deleted', path.unlink, lambda: path.write_bytes(raw), 'expected-inventory')
    renamed = folder / 'renamed.data'
    reject('renamed', lambda: path.rename(renamed), lambda: renamed.rename(path), 'expected-inventory')
    extra = folder / 'extra.expected'
    reject('extra-expected', lambda: extra.write_bytes(raw), extra.unlink, 'expected-inventory')
    extra = folder / 'foreign.c'
    reject('extra-generated', lambda: extra.write_bytes(raw), extra.unlink, 'generated-inventory', generated_tail)
    nested = folder / 'rogue'
    nested.mkdir()
    extra = nested / 'RESULTS.json'
    reject('nested-results', lambda: extra.write_bytes(raw), extra.unlink, 'generated-inventory', generated_tail)
    nested.rmdir()
    allowed = folder / 'RESULTS.json'
    allowed.write_bytes(b'root-only-result-exception')
    check()
    allowed.unlink()
    path.unlink()
    folder.rmdir()
    return {'valid': valid, 'rejects': rejected, 'truth': 'in-memory oracle digest and exact paths'}


def port(**changes):
    p = dict(enabled=1, id_len=4, id_error=0, dac_len=-1, dac_error=0, id=0, dac0=257, dac1=65538,
             i2c=0, i2c_error=0, force=0, c45=0, combo=0, sfp=0, mac=0, external=0, external_fail=0,
             mdio=0, address=5, i2c_address=83, speed=2500, duplex=258, rx=19, tx=-1, present=23, medium=0)
    p.update(changes)
    return p


def switch(index=0, **changes):
    s = dict(enabled=1, container=1, container_enabled=1, nports=1, mode=0, id=index,
             ports=[port(), port(id=15), port(id=1), port(id=2)])
    s.update(changes)
    return s


def case(name, flow='reader', **changes):
    c = dict(name=name, flow=flow, count=1, repeats=1, fault=0, foreign=0,
             switches=[switch(i) for i in range(3)])
    c.update(changes)
    return c


def cases():
    rows = []
    def one(name, **p):
        for flow in ('reader', 'validate', 'parse', 'topology'):
            s = switch(ports=[port(**p), port(id=15), port(id=1), port(id=2)])
            rows.append(case(name + '-' + flow, flow, switches=[s, switch(1), switch(2)]))
    for length in (-1, 0, 1, 2, 3, 4, 5, 8, 12):
        one('id-len-' + str(length), id_len=length)
    for value in (0, 15, 16, 4294967295):
        one('id-value-' + str(value), id=value)
    one('id-typed-error', id_error=-errno.EIO)
    for length in (-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 12):
        one('dac-len-' + str(length), dac_len=length)
    one('dac-typed-error', dac_len=8, dac_error=-errno.EILSEQ)
    for a, b in [(0, 255), (255, 256), (511, 65535), (4294967295, 4294967294)]:
        one('dac-values-%d-%d' % (a, b), dac_len=12, dac0=a, dac1=b)
    for flow in ('validate', 'prepare', 'topology', 'parse'):
        for label, s in [
            ('absent', switch(container=0)), ('empty', switch(nports=0)),
            ('disabled-parent', switch(container_enabled=0)),
            ('disabled-child', switch(nports=2, ports=[port(enabled=0, id=4294967295, dac_len=1), port(id=15), port(), port()])),
            ('all-disabled', switch(nports=2, ports=[port(enabled=0, id_len=0), port(enabled=0, id=16), port(), port()])),
            ('duplicate', switch(nports=3, ports=[port(id=15, dac_len=8, dac0=7), port(id=15, dac_len=12, dac0=9), port(id=0), port()])),
            ('later-bad', switch(nports=3, ports=[port(id=0, dac_len=8), port(id=16), port(id=15), port()])),
            ('later-dac-bad', switch(nports=3, ports=[port(id=0), port(id=15, dac_len=7), port(), port()]))]:
            rows.append(case(label + '-' + flow, flow, switches=[s, switch(1), switch(2)], repeats=2))
    for count in (0, 1, 2, 3):
        for flow in ('prepare', 'topology'):
            rows.append(case('multi-%d-%s' % (count, flow), flow, count=count, repeats=2,
                             switches=[switch(2 if count==3 else 0), switch(0 if count==3 else 1, mode=1), switch(1, mode=2)]))
        for fault in range(1, count + 2):
            rows.append(case('alloc-%d-fault-%d' % (count, fault), 'topology', count=count, fault=fault))
    rows += [case('multi-later-invalid', 'topology', count=3,
                  switches=[switch(0), switch(1), switch(2, ports=[port(id=16), port(), port(), port()])]),
             case('multi-disabled-switch', 'topology', count=3,
                  switches=[switch(0), switch(1, enabled=0, ports=[port(id=4294967295), port(), port(), port()]), switch(2)]),
             case('topology-foreign', 'topology', foreign=1)]
    rows += [case('same-disabled-two', 'topology', count=2,
                  switches=[switch(0,enabled=0),switch(1,enabled=0),switch(2)]),
             case('dev2-parse', 'parse', count=3, switches=[switch(2),switch(0),switch(1)]),
             case('carry-miibus-parse', 'parse', switches=[switch(nports=3,ports=[port(id=15,mdio=1,dac_len=8),
                     port(id=0,force=1,sfp=1),port(id=15,c45=1,combo=1),port()]),switch(1),switch(2)]),
             case('old-id-boundary', 'oldparse', switches=[switch(ports=[port(id=16),port(),port(),port()]),switch(1),switch(2)]),
             case('old-dac-boundary', 'oldparse', switches=[switch(ports=[port(dac_len=4),port(),port(),port()]),switch(1),switch(2)])]
    for name,changes in [('later-i2c-error',dict(i2c=1,i2c_error=-errno.EIO)),
                         ('later-external-error',dict(external=1,external_fail=1))]:
        rows.append(case(name,'parse',switches=[switch(nports=3,ports=[port(id=15,dac_len=8),
                         port(id=0,**changes),port(id=1),port()]),switch(1),switch(2)]))
    for name, changes in [('i2c-error', dict(i2c=1, i2c_error=-errno.EIO)),
                          ('i2c-ok', dict(i2c=1)), ('external-error', dict(external=1, external_fail=1)),
                          ('external-ok', dict(external=1)),
                          ('rich', dict(id=15, dac_len=12, force=1, mdio=1, c45=1, combo=1, sfp=2, mac=2, i2c=1)),
                          ('sfp-rx-defer', dict(sfp=1, rx=-517, tx=21, present=0, medium=27))]:
        rows.append(case(name+'-parse', 'parse', repeats=2,
                         switches=[switch(ports=[port(**changes), port(), port(), port()]), switch(1), switch(2)]))
    source.require(len({c['name'] for c in rows}) == len(rows), 'case-name-unique')
    return rows


def typed(length, count, error=0):
    return error or (-errno.EINVAL if length < 0 else -errno.ENODATA if length == 0 else
                     -errno.EOVERFLOW if length < count * 4 else 0)


def port_error(p):
    ret = typed(p['id_len'], 1, p['id_error'])
    if ret:
        return ret
    if p['id'] >= 16:
        return -errno.EINVAL
    return typed(p['dac_len'], 2, p['dac_error']) if p['dac_len'] >= 0 else 0


def admission(c):
    seen = set()
    for s in c['switches'][:c['count']]:
        if not s['enabled']:
            continue
        if s['id'] >= c['count'] or s['id'] >= 3 or s['id'] in seen:
            return -errno.EINVAL
        seen.add(s['id'])
        if s['container']:
            for p in s['ports'][:s['nports']]:
                if p['enabled'] and port_error(p):
                    return port_error(p)
    return 0


def oracle(c, profile, sdk):
    events = []
    add = events.append
    i2c, sfp = 'i2c' in profile, 'sfp' in profile
    meta = [[dict(address=0xa5a5a5a5, reset=0xa5a5a5a5, speed=0xa5a5a5a5, fake=0xa5a5a5a5,
                  access=0xa5a5a5a5, duplex=165, mdac=165, edac=165, c45=-1515870811,
                  combo=-1515870811, features=0xa5a5, rx=0xa5a5a5a5, tx=0xa5a5a5a5,
                  present=0xa5a5a5a5, medium=0xa5a5a5a5) for _ in range(16)] for _ in range(3)]
    wan, lan, held_mdio = 0, 0, 0
    held_external = [[0]*4 for _ in range(3)]
    ext_state = [0, 0, 0, 0]
    def get(n): add(f'GET {n}\n')
    def put(n): add(f'PUT {n}\n')
    def read(n, prop, count, ret): add(f'READ {n} {prop} {count} {ret}\n')
    def values(s, p):
        n = 300+s*4+p
        data = c['switches'][s]['ports'][p]
        ret = typed(data['id_len'], 1, data['id_error'])
        read(n, 'port_id', 1, ret)
        if ret: return ret
        if data['id'] >= 16: return -errno.EINVAL
        if data['dac_len'] >= 0:
            ret = typed(data['dac_len'], 2, data['dac_error'])
            read(n, 'phy_dac', 2, ret)
        return ret
    def validate(s):
        switch_ = c['switches'][s]
        if not switch_['container']: return 0
        get(200+s)
        ret = 0
        prev = None
        for p, data in enumerate(switch_['ports'][:switch_['nports']]):
            if not data['enabled']: continue
            get(300+s*4+p)
            if prev is not None:put(prev)
            ret = values(s, p)
            prev = 300+s*4+p
            if ret:break
        if prev is not None:put(prev)
        put(200+s)
        return ret
    def prepare():
        owned=[]
        seen=set()
        ret=0
        for s, n in enumerate(c['switches'][:c['count']]):
            get(1);get(100+s);put(1)
            if not n['enabled']:
                put(100+s);continue
            owned.append(s)
            read(100+s,'device_id',1,0)
            if n['id'] >= c['count'] or n['id']>=3 or n['id'] in seen:
                ret=-errno.EINVAL;break
            seen.add(n['id']);add(f'ACCESS {100+s} {n["mode"]}\n')
            if n['mode'] in (0,1):read(100+s,'reg',2 if n['mode']==0 else 1,0)
            ret=validate(s)
            if ret:break
        return ret,owned
    def setter(label,d,p,v):
        names={'ADDRESS':'address','RESET':'reset','SPEED':'speed','DUPLEX':'duplex',
               'ACCESS':'access','FAKE':'fake','C45':'c45','COMBO':'combo','FEATURE':'features'}
        if label=='FEATURE':meta[d][p]['features'] |= v
        else:meta[d][p][names[label]]=v
        bits={'C45':'CLAUSE45','COMBO':'COMBO','ACCESS':'I2C'}
        if label in bits:
            bit=sdk['PHY_F_'+bits[label]]
            meta[d][p]['features']=(meta[d][p]['features']|bit) if v else (meta[d][p]['features']&~bit)
        add(f'SET {label} {d} {p} {v}\n')
    def parse():
        nonlocal wan,lan,held_mdio,ext_state
        s=c['switches'][0];d=s['id']
        if not s['container']:return sdk['SW_NOT_FOUND']
        get(200)
        ret=0
        miibus=0
        prev=None
        for p,data in enumerate(s['ports'][:s['nports']]):
            if not data['enabled']:continue
            n=300+p;get(n)
            if prev is not None:put(prev)
            prev=n
            ret=values(0,p)
            if ret:
                ret=sdk['SW_BAD_VALUE'];break
            ident=data['id']
            if not wan:wan=1<<ident
            else:lan |= 1<<ident
            if data['mdio']:
                get(999);held_mdio+=1
                miibus=2;add(f'BUS {d} 2\n');setter('RESET',d,ident,17)
            read(n,'phy_address',1,0)
            address=data['address'] | (miibus<<8)
            if i2c and data['i2c']:
                setter('ACCESS',d,ident,1);read(n,'phy_i2c_address',1,data['i2c_error'])
                if data['i2c_error']:
                    ret=sdk['SW_BAD_VALUE'];break
                setter('ADDRESS',d,ident,(1<<24)|data['i2c_address']);setter('FAKE',d,ident,data['address'])
            else:setter('ADDRESS',d,ident,address)
            read(n,'forced-speed',1,0 if data['force'] else -errno.EINVAL)
            if data['force']:
                read(n,'forced-duplex',1,0);setter('SPEED',d,ident,data['speed'])
                setter('DUPLEX',d,ident,data['duplex']&255);setter('ADDRESS',d,ident,address)
            if data['dac_len']>=0:
                a,b=data['dac0']&255,data['dac1']&255
                meta[d][ident]['mdac']=a;meta[d][ident]['edac']=b
                add(f'SET DAC {d} {ident} {a} {b}\n')
            setter('C45',d,ident,data['c45']);setter('COMBO',d,ident,data['combo'])
            # Values below are independently evaluated from the actual enum domain.
            features=(sdk['PHY_F_QGMAC'] if data['mac']==1 else sdk['PHY_F_XGMAC'] if data['mac']==2 else 0)
            if data['sfp']:features|=sdk['PHY_F_SFP']
            if data['sfp']==2:features|=sdk['PHY_F_SFP_SGMII']
            setter('FEATURE',d,ident,features|sdk['PHY_F_INIT'])
            if data['sfp'] or data['combo']:
                for field in ('rx','tx','present','medium'):
                    value=data[field]
                    meta[d][ident][field]=value if value>0 else 65535 if field=='rx' and value==-517 else 65536
                if sfp:add(f'SFP {d} {ident} {miibus}\n')
            if data['external']:
                get(400+p);add(f'EXTERNAL {n} {data["external_fail"]}\n')
                held_external[0][p]+=1
                if data['external_fail']:
                    ret=sdk['SW_NO_RESOURCE'];break
                read(400+p,'switch_cpu_port',1,0);ext_state=[ident,1,0,3]
        if prev is not None:put(prev)
        put(200)
        return ret
    ret=0
    for repeat in range(c['repeats']):
        add(f'BEGIN {c["flow"]} {repeat}\n')
        flow=c['flow']
        if flow=='reader':
            ret=values(0,0);p=c['switches'][0]['ports'][0]
            fields=(0x6b6b6b6b,0x6b6b6b6b,107,107) if ret else (p['id'],int(p['dac_len']>=0),p['dac0']&255 if p['dac_len']>=0 else 0,p['dac1']&255 if p['dac_len']>=0 else 0)
            add('OUTPUT %d %u %d %u %u\n' % ((ret,)+fields))
        elif flow=='validate':ret=validate(0)
        elif flow=='prepare':
            ret,owned=prepare()
            for s in owned:put(100+s)
        elif flow=='topology':
            if c['foreign']:ret=-errno.EBUSY
            else:
                get(1);read(1,'num_devices',1,0);put(1)
                ret,owned=prepare()
                live=[]
                if not ret:
                    for index in range(c['count']+1):
                        ok=index+1!=c['fault'];add(f'ALLOC {index+1} {int(index>0)} {1 if index else c["count"]} {int(ok)}\n')
                        if not ok:
                            ret=-errno.ENOMEM
                            for b in reversed(live):add(f'FREE {b}\n')
                            break
                        live.append(index+1)
                if ret:
                    for s in owned:put(100+s)
                else:
                    for d in range(c['count']):
                        s=next((i for i,n in enumerate(c['switches'][:c['count']]) if n['enabled'] and n['id']==d),-1)
                        n=c['switches'][s] if s>=0 else None
                        base=0xa100+s*256 if n and n['mode']==0 else 0
                        size=4096+s if n and n['mode']==0 else 0
                        pcie=0xa100+s*256 if n and n['mode']==1 else 0
                        add(f'CFG {d} {s} {d if n else 0} {base} {size} {pcie}\n')
                    for d in range(c['count']):
                        s=next((i for i,n in enumerate(c['switches'][:c['count']]) if n['enabled'] and n['id']==d),-1)
                        if s>=0:put(100+s)
                        add(f'FREE {d+2}\n')
                    add('FREE 1\n')
        elif flow=='parse':ret=parse()
        else:raise RuntimeError('oracle-flow')
        add(f'RETURN {ret}\n')
    add(f'OPEN_MDIO_HELD {held_mdio}\n')
    for s in range(3):
        for p in range(4):add(f'OPEN_EXTERNAL_HELD {400+s*4+p} {held_external[s][p]}\n')
    add('EXTERNAL_STATE %d %d %d %d\n' % tuple(ext_state))
    add(f'BITMAP {wan} {lan}\n')
    for d in range(3):
        for p in range(16):
            m=meta[d][p]
            fields=['address','reset','speed','fake','access','duplex','mdac','edac','c45','combo','features','rx','tx','present','medium']
            add('STATE %d %d %s\n' % (d,p,' '.join(str(m[k]) for k in fields)))
    add('END CLEAN\n')
    return ret, admission(c), ''.join(events).encode()


def header(matrix):
    def value(v):
        return json.dumps(v) if isinstance(v,str) else str(v)+'u' if v>2147483647 else str(v)
    def item(d):
        parts=[]
        for k,v in d.items():
            if k in ('name','flow') or not isinstance(v,list):parts.append('.'+k+'='+value(v))
            else:parts.append('.'+k+'={'+','.join(item(n) for n in v)+'}')
        return '{'+','.join(parts)+'}'
    return 'static const struct input inputs[]={\n'+',\n'.join(item(c) for c in matrix)+'\n};\n'


def positive(code,out,err,expected):
    source.require(code==0 and out==expected and err==b'', 'positive-exact-trace')


def negative(code,out,err,marker):
    source.require(code==86 and out==b'' and err==('SSDK_PORT '+marker+'\n').encode(), 'negative-exact-marker')


def gate_controls():
    positive(0,b'x',b'',b'x');negative(86,b'',b'SSDK_PORT X\n','X')
    rejected=0
    for row in [(1,b'x',b'',b'x'),(0,b'xnoise',b'',b'x'),(0,b'x',b'diagnostic',b'x')]:
        try:positive(*row)
        except RuntimeError:rejected+=1
        else:raise RuntimeError('positive-control-accepted')
    for row in [(1,b'',b'SSDK_PORT X\n'),(-6,b'',b'SSDK_PORT X\n'),(None,b'',b'SSDK_PORT X\n'),
                (86,b'noise',b'SSDK_PORT X\n'),(86,b'',b'SSDK_PORT Y\n'),
                (86,b'',b'SSDK_PORT X\nSSDK_PORT X\n'),(86,b'',b'SSDK_PORT X\nAddressSanitizer')]:
        try:negative(*row,'X')
        except RuntimeError:rejected+=1
        else:raise RuntimeError('negative-control-accepted')
    return {'valid':2,'rejects':rejected}


def invoke(argv,prefix,env,generated):
    record(prefix.with_suffix('.command.json'),{'argv':argv,'environment':{k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}},generated)
    try:
        p=subprocess.run(argv,capture_output=True,env=env,timeout=60)
    except subprocess.TimeoutExpired as e:
        for suffix,raw in [('.stdout',e.stdout or b''),('.stderr',e.stderr or b'')]:prefix.with_suffix(suffix).write_bytes(raw)
        save(prefix.with_suffix('.exit.json'),{'returncode':None,'timeout':True})
        raise RuntimeError('timeout-not-negative-credit') from e
    for suffix,raw in [('.stdout',p.stdout),('.stderr',p.stderr)]:
        path=prefix.with_suffix(suffix);path.write_bytes(raw);generated[str(path)]=source.digest(raw)
    record(prefix.with_suffix('.exit.json'),{'returncode':p.returncode,'timeout':False},generated)
    return p


def compile_c(cc,flags,text,prefix,env,generated):
    path=prefix.with_suffix('.c');binary=prefix.with_suffix('.bin')
    path.write_text(text);generated[str(path)]=source.digest(text.encode())
    p=invoke([cc,*flags,str(path),'-o',str(binary)],prefix.with_name(prefix.name+'-compile'),env,generated)
    source.require(p.returncode==0 and p.stdout==p.stderr==b'','clean-compile:'+str(prefix))
    generated[str(binary)]=source.identity(binary)
    bundle=Path(str(binary)+'.dSYM')
    if bundle.exists():
        required={bundle/'Contents/Info.plist',bundle/'Contents/Resources/DWARF'/binary.name}
        arch={'arm64':'aarch64','aarch64':'aarch64','x86_64':'x86_64'}.get(platform.machine())
        source.require(arch is not None,'debug-host-arch')
        allowed=required|{bundle/'Contents/Resources/Relocations'/arch/(binary.name+'.yml')}
        members=list(bundle.rglob('*'));files={p for p in members if p.is_file()}
        source.require(bundle.is_dir() and not any(p.is_symlink() for p in members) and required<=files<=allowed,'debug-bundle-shape')
        for path in sorted(files):generated[str(path)]=source.identity(path)
    return binary


def san_env(env,code):
    env=dict(env)
    env['ASAN_OPTIONS']=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={code}'
    env['UBSAN_OPTIONS']=f'halt_on_error=1:print_stacktrace=1:exitcode={code}'
    return env


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


def sdk_domain(tree):
    errors=(tree/'include/common/sw_error.h').read_text()
    sdk={k:int(v) for k,v in re.findall(r'\b(SW_\w+)\s*=\s*(-?\d+)',errors)}
    feature=(tree/'include/init/ssdk_init.h').read_text()
    enum=re.search(r'enum\s*\{\s*(QCA_PHY_F_CLAUSE45_BIT,[\s\S]*?)\};',feature).group(1)
    names=[v.strip() for v in enum.split(',') if v.strip()]
    source.require(all(re.fullmatch(r'QCA_PHY_\w+',v) for v in names),'actual-feature-domain')
    for label in ('QGMAC','XGMAC','INIT','SFP','SFP_SGMII','CLAUSE45','COMBO','I2C'):
        sdk['PHY_F_'+label]=1<<names.index('QCA_PHY_F_'+label+'_BIT')
    return sdk


def model_controls(text,profile,byname,sdk,cc,flags,folder,env,generated):
    """Model-contract pollution, not production mutations or kernel execution."""
    rows=[]
    reordered=once(text,'    of_node_put(prev);\n    return next;', '    return next;')
    reordered=once(reordered,'    for(int p=start;p<input->switches[parent->s].nports;p++)',
                   '    of_node_put(prev);\n    for(int p=start;p<input->switches[parent->s].nports;p++)')
    borrowed=once(text,'return pi(n)->mdio ? get(&foreign_node) : NULL;',
                  'return pi(n)->mdio ? &foreign_node : NULL;')
    lookup=once(text,'    of_node_put(from);\n    return next;', '    return next;')
    lookup=once(lookup,'    struct device_node *next=NULL;\n    if(!strcmp(name,"ess-instance"))',
                '    of_node_put(from);\n    struct device_node *next=NULL;\n    if(!strcmp(name,"ess-instance"))')
    for name,case_name,changed in [('model-iterator-order','duplicate-validate',reordered),
                                    ('model-mdio-borrow','rich-parse',borrowed),
                                    ('model-lookup-order','duplicate-prepare',lookup)]:
        binary=compile_c(cc,flags,changed,folder/name,env,generated)
        i,c=byname[case_name];ret,pure,_=oracle(c,profile,sdk)
        ep=folder/(case_name+'.expected')
        run=invoke([str(binary),str(i),str(ret),str(pure),str(ep)],folder/(name+'-run'),env,generated)
        negative(run.returncode,run.stdout,run.stderr,'EXACT_MODEL_TRACE')
        rows.append({'profile':profile,'name':name,'case':case_name,'marker':'EXACT_MODEL_TRACE',
                     'classification':'harness API-model pollution only, NOT actual source mutant or Linux runtime proof',
                     'source_sha256':source.digest(changed.encode())})
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',required=True);p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--positives-only',action='store_true')
    p.add_argument('--base',type=Path,default=OLD/'DT-ADMISSION-CANDIDATE-20261031-r1')
    p.add_argument('--candidate',type=Path,default=OLD/'PHY-PORT-ADMISSION-CANDIDATE-20261031-r1')
    args=p.parse_args();out=args.output.resolve()
    source.require(out.parent==AUDIT and out.name.startswith('PORT-TEST-') and not out.exists(),'fresh-output')
    out.mkdir(parents=True)
    result={'status':'INCOMPLETE','qualification':'HOST_MODEL_ONLY_PHY_PORT_ADMISSION','positives':[],'negatives':[],
            'python_optimize':sys.flags.optimize,
            'open':['target/kernel OF/concurrent writer/ABI','full24 root+private+PHY integration',
                    'MDIO/SFP/provider/bus/external node ownership','CONFIG_MDIO_I2C unknown QCOM API','LSan']}
    generated={}
    try:
        tree,inputs=source.prepare(args.base.resolve(),args.candidate.resolve(),out)
        record(out/'INPUTS.json',inputs,generated)
        result['gate_controls']=gate_controls();result['tail_controls']=tail_controls(out)
        matrix=cases();sdk=sdk_domain(tree)
        record(out/'MATRIX.json',matrix,generated);record(out/'SDK-DOMAIN.json',sdk,generated)
        template=(SUPPORT/'fixture.c').read_text().replace('/* @CASES@ */',header(matrix))
        text,new,old=source.render(tree,args.base/'prepared',template)
        record(out/'EXTRACTED.json',{'candidate':new['records'],'baseline':old['records'],
               'complete_bodies':list(new['bodies']),
               'leaves':'OF/allocator/MDIO/I2C/SFP/setters/large structs explicit models; actual topology before-allocation caller; no full root',
               'transform':'candidate bodies unchanged; complete baseline parser name-only rename with guarded raw-DAC primitive; Linux unsigned base modeled uintN_t',
               'witness':'old parser safe sink/raw-prefix guards are instrumented boundary witnesses, NOT OOB reproduction'},generated)
        cc=shutil.which(args.cc);source.require(cc is not None,'compiler-path');cc=str(Path(cc).resolve())
        result['compiler']={'path':cc,'sha256':source.identity(cc)}
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wformat=2','-Wno-unused-function']
        env=dict(os.environ);env.pop('ASAN_OPTIONS',None);env.pop('UBSAN_OPTIONS',None)
        if args.sanitize:
            flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all'];env=san_env(env,97)
        result['flags']=flags;result['environment']={k:env.get(k) for k in ('ASAN_OPTIONS','UBSAN_OPTIONS')}
        v=invoke([cc,'--version'],out/'compiler-version',env,generated)
        source.require(v.returncode==0 and v.stderr==b'','compiler-version')
        if args.sanitize:result['canaries']=canaries(cc,flags,out,env,generated)
        expected_files={};byname={c['name']:(i,c) for i,c in enumerate(matrix)}
        for profile,pf in PROFILES.items():
            folder=out/profile;folder.mkdir();binary=compile_c(cc,flags+pf,text,folder/'positive',env,generated)
            for i,c in enumerate(matrix):
                if c['flow']=='oldparse':continue
                ret,pure,expected=oracle(c,profile,sdk)
                ep=folder/(c['name']+'.expected');ep.write_bytes(expected)
                expected_files[str(ep)]=source.digest(expected);generated[str(ep)]=source.digest(expected)
                run=invoke([str(binary),str(i),str(ret),str(pure),str(ep)],folder/c['name'],env,generated)
                positive(run.returncode,run.stdout,run.stderr,expected)
                result['positives'].append({'profile':profile,'case':c['name'],'stdout_sha256':source.digest(run.stdout)})
            if not args.positives_only:
                result.setdefault('model_controls',[]).extend(model_controls(text,profile,byname,sdk,cc,flags+pf,folder,env,generated))
                for variant in variants(new,old,profile):
                    mutated=once(text,variant['before'],variant['after'])
                    mb=compile_c(cc,flags+pf,mutated,folder/variant['name'],env,generated)
                    i,c=byname[variant['case']];ret,pure,expected=oracle(c,profile,sdk)
                    ep=folder/(c['name']+'.expected')
                    run=invoke([str(mb),str(i),str(ret),str(pure),str(ep)],folder/(variant['name']+'-run'),env,generated)
                    negative(run.returncode,run.stdout,run.stderr,variant['marker'])
                    result['negatives'].append({k:variant[k] for k in ('name','symbol','case','marker','classification')}|
                                              {'profile':profile,'source_sha256':source.digest(mutated.encode())})
                for name,marker in [('old-id-boundary','PORT_BOUNDS_SAFE'),('old-dac-boundary','OLD_RAW_DAC_BOUNDARY')]:
                    i,c=byname[name]
                    ep=folder/(name+'.expected');ep.write_bytes(b'')
                    expected_files[str(ep)]=source.digest(b'');generated[str(ep)]=source.digest(b'')
                    run=invoke([str(binary),str(i),'0','0',str(ep)],folder/(name+'-run'),env,generated)
                    negative(run.returncode,run.stdout,run.stderr,marker)
                    result['negatives'].append({'profile':profile,'name':name,'symbol':'complete23 baseline parser',
                         'case':name,'marker':marker,'classification':'instrumented safe boundary witness, NOT actual old OOB or target failure'})
            save(out/'RESULTS.json',result)
        result['end_input_stability']=source.stable(inputs)
        expected_tail(out,expected_files);generated_tail(out,generated)
        source.require(source.identity(cc)==result['compiler']['sha256'],'end-compiler')
        result['expected_tail']='EXACT_PATHS_AND_MEMORY_ORACLE_DIGESTS'
        result['generated_tail']='EXACT_FILES_EXCLUDING_ONLY_ROOT_RESULTS_AND_SEPARATELY_VERIFIED_FRESH692'
        result['generated_files']=generated
        result['positive_count']=len(result['positives']);result['negative_count']=len(result['negatives'])
        result['status']='DEV_CHECKPOINT_POSITIVES_ONLY' if args.positives_only else 'HOST_MODEL_ONLY'
        result['outcome']='NOT_FINAL_QUALIFICATION' if args.positives_only else 'PASSED_WITHIN_PORT_ADMISSION_MODEL'
    except Exception as e:
        result['status']='FAILED';result['error']=str(e);raise
    finally:
        save(out/'RESULTS.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_count','negative_count')}))


if __name__=='__main__':main()
