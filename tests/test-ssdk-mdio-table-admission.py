#!/usr/bin/env python3
"""Real getter/table functions; sequential admission, not reader/provider lifetime."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load('extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
types = load('types', HERE / 'ssdk-phy-port-admission/source.py')


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.prepared / 'src/init/ssdk_plat.c'
    init = args.prepared / 'src/init/ssdk_init.c'
    header = args.prepared / 'include/init/ssdk_plat.h'
    dts = args.prepared / 'src/init/ssdk_dts.c'
    inputs = {str(p): sha(p.read_bytes()) for p in (source, init, dts, header, Path(__file__),
              HERE / 'nss-dp-containment/extract_prepared_c.py', HERE / 'ssdk-phy-port-admission/source.py')}
    names = ['ssdk_miibus_get', 'ssdk_miibus_add', 'ssdk_miibus_index_get']
    bodies = {n: extract.function(source.read_text(), n) for n in names}
    getter = extract.function(init.read_text(), 'ssdk_phy_priv_data_get')
    count_getter = extract.function(dts.read_text(), 'ssdk_switch_device_num_get')
    defines = '\n'.join(line for line in header.read_text().splitlines()
                        if line.startswith(('#define SSDK_MII_BUS_MAX ', '#define SSDK_MII_INVALID_BUS_ID ')))
    need(len(defines.splitlines()) == 2, 'actual bus limits')
    prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
'''
    fixture = r'''
struct mii_bus { unsigned identity, untouched; };
struct qca_phy_priv { uint64_t before; struct mii_bus *miibus[SSDK_MII_BUS_MAX]; uint64_t after; };
static struct qca_phy_priv **qca_phy_priv_global;
static struct { unsigned num_devices; } ssdk_dt_global;
static struct qca_phy_priv storage[SW_MAX_NR_DEV];
static struct qca_phy_priv *slots[SW_MAX_NR_DEV];
static struct mii_bus buses[5];
static unsigned cases;
static const char *label;
static void demand(bool ok, const char *why)
{ if (!ok) { fprintf(stderr,"MDIO_TABLE:%s:%s\n",label,why); exit(86); } }
/* @FUNCTIONS@ */
static void scenario(unsigned layout, unsigned mask, unsigned dev, bool root, unsigned query, bool extreme, unsigned count)
{
    ssdk_dt_global.num_devices = count;
    memset(storage, 0, sizeof(storage));
    for (unsigned d=0; d<SW_MAX_NR_DEV; d++) {
        slots[d] = mask & (1u<<d) ? &storage[d] : NULL;
        storage[d].before = 0x1234567812345678ULL + d;
        storage[d].after = 0x8765432187654321ULL + d;
        unsigned value = layout;
        for (unsigned i=0; i<SSDK_MII_BUS_MAX; i++, value/=5)
            storage[d].miibus[i] = value%5 ? &buses[value%5-1] : NULL;
    }
    qca_phy_priv_global = root ? slots : NULL;
    struct qca_phy_priv saved[SW_MAX_NR_DEV];
    memcpy(saved, storage, sizeof(saved));
    struct qca_phy_priv *saved_slots[SW_MAX_NR_DEV];
    memcpy(saved_slots, slots, sizeof(slots));
    struct mii_bus saved_buses[5]; memcpy(saved_buses, buses, sizeof(buses));
    bool valid = root && dev<SW_MAX_NR_DEV && dev<count && (mask & (1u<<dev));
    unsigned index = extreme ? UINT32_MAX : query;
    struct mii_bus *bus = query ? &buses[query-1] : NULL;
    demand(ssdk_miibus_get(dev,index) == (valid && index<SSDK_MII_BUS_MAX ? saved[dev].miibus[index] : NULL), "get-result");
    unsigned expected_index = SSDK_MII_INVALID_BUS_ID;
    if (valid && bus) for (unsigned i=0; i<SSDK_MII_BUS_MAX; i++) if (saved[dev].miibus[i]==bus) { expected_index=i; break; }
    demand(ssdk_miibus_index_get(dev,bus)==expected_index,"index-result");
    demand(ssdk_miibus_add(dev,bus,NULL)==SW_BAD_PTR,"null-output-result");
    demand(!memcmp(storage,saved,sizeof(saved)),"null-output-mutated-table");
    unsigned output=0xdeadbeefU, selected=SSDK_MII_INVALID_BUS_ID;
    if (valid && bus) for (unsigned i=0; i<SSDK_MII_BUS_MAX; i++) if (saved[dev].miibus[i]==bus || !saved[dev].miibus[i]) { selected=i; break; }
    sw_error_t expected = !valid || !bus ? SW_BAD_PTR : selected==SSDK_MII_INVALID_BUS_ID ? SW_OUT_OF_RANGE : SW_OK;
    demand(ssdk_miibus_add(dev,bus,&output)==expected,"add-result");
    if (expected==SW_OK) saved[dev].miibus[selected]=bus;
    demand(output==(expected==SW_OK ? selected : 0xdeadbeefU),"output-ownership");
    demand(!memcmp(storage,saved,sizeof(saved)) && !memcmp(slots,saved_slots,sizeof(slots)) &&
           !memcmp(buses,saved_buses,sizeof(buses)),"foreign-state");
    demand(qca_phy_priv_global==(root ? slots : NULL),"global-state");
    cases++;
}
int main(void)
{
    for (unsigned i=0;i<5;i++) buses[i]=(struct mii_bus){i+1,0xa5a5a5a5};
    label="matrix";
    unsigned devices[]={0,1,2,SW_MAX_NR_DEV,UINT32_MAX};
    for (unsigned layout=0;layout<625;layout++)
    for (unsigned mask=0;mask<8;mask++)
    for (unsigned d=0;d<5;d++)
    for (unsigned root=0;root<2;root++)
    for (unsigned query=0;query<6;query++)
    for (unsigned count=0;count<=SW_MAX_NR_DEV;count++) scenario(layout,mask,devices[d],root,query,false,count);
    scenario(624,7,2,true,5,true,3);
    printf("{\"scenarios\":%u,\"reader_retirement_verified\":false}\n",cases);
    return 0;
}
'''
    mutations = [
        ('metadata-count-missing', 'ssdk_phy_priv_data_get', 'dev_id >= ssdk_switch_device_num_get() ||', '', 'add-result'),
        ('get-refusal', 'ssdk_miibus_get', '\t\treturn NULL;', '\t\treturn &buses[4];', 'get-result'),
        ('get-wrong-slot', 'ssdk_miibus_get', 'return priv->miibus[index];', 'return priv->miibus[0];', 'get-result'),
        ('get-off-by-one', 'ssdk_miibus_get', 'index >= SSDK_MII_BUS_MAX', 'index >= SSDK_MII_BUS_MAX - 1', 'get-result'),
        ('add-refusal', 'ssdk_miibus_add', '\t\treturn SW_BAD_PTR;', '\t\treturn SW_OK;', 'null-output-result'),
        ('add-full', 'ssdk_miibus_add', '\treturn SW_OUT_OF_RANGE;', '\treturn SW_OK;', 'add-result'),
        ('add-output', 'ssdk_miibus_add', '*index = i;', '*index = 0;', 'output-ownership'),
        ('add-store', 'ssdk_miibus_add', 'priv->miibus[i] = miibus;', 'priv->miibus[i] = NULL;', 'foreign-state'),
        ('index-null', 'ssdk_miibus_index_get', 'if (!priv || !miibus)', 'if (!priv)', 'index-result'),
        ('index-missing', 'ssdk_miibus_index_get', '\n\treturn SSDK_MII_INVALID_BUS_ID;', '\n\treturn 0;', 'index-result'),
        ('index-wrong-slot', 'ssdk_miibus_index_get', '\t\t\treturn index;', '\t\t\treturn 0;', 'index-result'),
    ]
    records=[]
    for label, selected, before, after, reason in [('candidate',None,None,None,None)] + mutations:
        changed={'ssdk_phy_priv_data_get': getter, **bodies}
        if selected:
            need(changed[selected].count(before)==1,'ambiguous mutation '+label)
            changed[selected]=changed[selected].replace(before,after,1)
        code=prefix+types.extract(args.prepared)['types']+'\n'+defines+'\n'+fixture.replace('/* @FUNCTIONS@ */',count_getter+'\n'+'\n'.join(changed.values()))
        c=args.output/(label+'.c'); c.write_text(code)
        command=[args.cc,'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror']
        if args.sanitize:
            command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        command += [str(c),'-o',str(c.with_suffix('.host'))]
        compile_result=subprocess.run(command,capture_output=True,timeout=60)
        (args.output/(label+'.compile.stdout')).write_bytes(compile_result.stdout)
        (args.output/(label+'.compile.stderr')).write_bytes(compile_result.stderr)
        need(compile_result.returncode==0 and not compile_result.stdout and not compile_result.stderr,'clean compile '+label)
        result=subprocess.run([str(c.with_suffix('.host'))],capture_output=True,timeout=90)
        (args.output/(label+'.stdout')).write_bytes(result.stdout)
        (args.output/(label+'.stderr')).write_bytes(result.stderr)
        if reason:
            need(result.returncode==86 and not result.stdout and result.stderr==f'MDIO_TABLE:matrix:{reason}\n'.encode(),'exact runtime negative '+label)
        else:
            need(result.returncode==0 and not result.stderr and json.loads(result.stdout)=={'scenarios':1200001,'reader_retirement_verified':False},'positive matrix')
        records.append({'label':label,'command':command,'returncode':result.returncode,'reason':reason,'c_sha256':sha(c.read_bytes())})
    need(all(sha(Path(p).read_bytes())==h for p,h in inputs.items()),'source changed')
    (args.output/'RESULTS.json').write_text(json.dumps({'scope':'SEQUENTIAL_ARGUMENT_AND_ABSENT_METADATA_ADMISSION_NOT_CONCURRENT_RETIREMENT','inputs':inputs,'records':records},indent=2)+'\n')
    print(json.dumps({'scenarios':1200001,'exact_runtime_mutants':len(mutations),'output':str(args.output)}))


if __name__ == '__main__':
    main()
