"""Exact 37-layer baseline plus reviewed 050; no expected hashes learned at run time."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT/'package/qca-nss/qca-ssdk/patches/050-i2c-transfer-results-and-reference-balance.patch'
PATCH_SHA = '7bbd1074fade9de5f07235ecf3d893539b4c3e27ee81b0e35934b1d51a357af9'
BASE_TREE = '26226bb536fb64e108b320559bb6ffbf7063e4a1c4b2c76bc5ba815acf3b5ed2'
C = 'src/init/ssdk_phy_i2c.c'
HEADER = 'include/init/ssdk_phy_i2c.h'
ERRORS = 'include/common/sw_error.h'
CONSTANTS = 'include/hsl/phy/hsl_phy.h'
OLD_C = 'dbfbd5b7805c8b32d92cb2c13d716377f81a9b5abb027cec3843032c9cb1bbd9'
NEW_C = '9536ba0a0bc3414e44bcf947384060e958addaaecca74abb4c8b7944e79dc2d3'

def module(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value

context=module('i2c_exact_patch','tests/edma_patch_context.py')
lex=module('i2c_c_reader','tests/nss-dp-containment/extract_prepared_c.py')

def need(ok,why):
    if not ok: raise ValueError(why)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def inventory(root):
    rows={}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(),'source symlink')
        need(path.is_dir() or path.is_file(),'nonregular source entry')
        if path.is_file(): rows[path.relative_to(root).as_posix()]=sha(path.read_bytes())
    allowed={parent.as_posix() for name in rows for parent in Path(name).parents if parent.as_posix()!='.'}
    need(all(path.relative_to(root).as_posix() in allowed for path in root.rglob('*') if path.is_dir()),
         'unclassified empty source directory')
    return rows

def tree_hash(rows): return sha((json.dumps(rows,sort_keys=True,separators=(',',':'))+'\n').encode())

def prepare(base,actual,out,patch_tool,invoke):
    before=inventory(base)
    need(len(before)==692 and tree_hash(before)==BASE_TREE and before[C]==OLD_C,'frozen complete37 required')
    raw=PATCH.read_bytes(); need(sha(raw)==PATCH_SHA,'reviewed050 patch identity')
    expected,declared=context.inspect_patch(base,raw)
    need(set(expected)=={C} and sha(expected[C])==NEW_C,'only reviewed I2C translation unit')
    after=dict(before); after[C]=NEW_C
    need(inventory(actual)==after,'actual complete38 must equal frozen37 plus050')
    view=out/'roundtrip38'; shutil.copytree(actual,view)
    reverse=invoke('reverse050',[patch_tool,'--batch','--fuzz=0','-p1','-R','-i',str(PATCH)],cwd=view)
    need(reverse['returncode']==0 and not reverse['stderr'] and
         not re.search(r'offset|fuzz|FAILED|reject|malformed',reverse['stdout'],re.I) and inventory(view)==before,
         'exact reverse050 full692')
    forward=invoke('forward050',[patch_tool,'--batch','--fuzz=0','-p1','-i',str(PATCH)],cwd=view)
    need(forward['returncode']==0 and not forward['stderr'] and
         not re.search(r'offset|fuzz|FAILED|reject|malformed',forward['stdout'],re.I) and inventory(view)==after,
         'exact forward050 full692')
    return before,after,declared

def constants(root):
    text=(root/CONSTANTS).read_text(); lines=[]
    for name in ('TO_PHY_I2C_ADDR_VAL','I2C_ADAPTER_DEFAULT_ID'):
        found=re.findall(r'^#define '+name+r'[^\n]*$',text,re.M)
        need(len(found)==1,'unique actual macro '+name); lines+=found
    return '\n'.join(lines)+'\n'

def replace_function(text,name,before,after):
    body=lex.function(text,name)
    need(body.count(before)==1,'exact mutation anchor '+name)
    need(text.count(body.rstrip('\n'))==1,'unique complete function '+name)
    return text.replace(body.rstrip('\n'),body.replace(before,after,1).rstrip('\n'),1)

# Completion obligations are fixed independently of observed return codes.
MUTANTS=(
 ('get-put','qca_i2c_data_get','\ti2c_put_adapter(adapt);\n','','data-reference','REFERENCE_BALANCE',False),
 ('set-put','qca_i2c_data_set','\ti2c_put_adapter(adapt);\n','','data-reference','REFERENCE_BALANCE',False),
 ('read-put','qca_phy_i2c_read','\ti2c_put_adapter(adapt);\n','','phy-reference','REFERENCE_BALANCE',True),
 ('write-put','qca_phy_i2c_write','\ti2c_put_adapter(adapt);\n','','phy-reference','REFERENCE_BALANCE',True),
 ('get-total-width','__qca_i2c_data_get','a_uint32_t ret = 0, cnt = count;','a_int16_t ret = 0; a_uint32_t cnt = count;','data-width','LENGTH_WIDTH',False),
 ('set-total-width','__qca_i2c_data_set','a_uint32_t ret = 0, cnt = count;','a_int16_t ret = 0; a_uint32_t cnt = count;','data-width','LENGTH_WIDTH',False),
 ('get-remaining-width','__qca_i2c_data_get','a_uint32_t ret = 0, cnt = count;','a_uint32_t ret = 0; a_uint16_t cnt = count;','data-width','LENGTH_WIDTH',False),
 ('set-remaining-width','__qca_i2c_data_set','a_uint32_t ret = 0, cnt = count;','a_uint32_t ret = 0; a_uint16_t cnt = count;','data-width','LENGTH_WIDTH',False),
 ('short-read-as-bytes','__qca_i2c_read','return ret < 0 ? ret : -EIO;','return ret;','short-read','READ_FAILURE',False),
 ('wrong-read-recipient','__qca_i2c_read','msg[1].buf = buf;',
  'msg[1].buf = count == 1 ? (a_uint8_t[8]){0} : buf;','data-chunks','DATA_RESULT',False),
 ('mmd-read-unsigned','__qca_phy_i2c_mmd_read','a_int32_t ret;','a_uint8_t ret;','mmd-result','MMD_SIGNED_RESULT',True),
 ('mmd-write-unsigned','__qca_phy_i2c_mmd_write','a_int32_t ret;','a_uint8_t ret;','mmd-result','MMD_SIGNED_RESULT',True),
 ('mmd-early-output','__qca_phy_i2c_mmd_read',
  '\tif (ret != ARRAY_SIZE(msg)) {\n\t\treturn SW_FAIL;\n\t}\n\n\t*reg_data = (rx[0] << 8) | rx[1];',
  '\t*reg_data = (rx[0] << 8) | rx[1];\n\tif (ret != ARRAY_SIZE(msg)) {\n\t\treturn SW_FAIL;\n\t}',
  'mmd-publication','MMD_FAILURE_OUTPUT',True),
 ('discard-read-error','__qca_phy_i2c_read',
  '\t\treturn __qca_phy_i2c_mmd_read(dev_id, phy_addr, mmd_num, reg_addr, reg_data);\n\n\t} else {\n\t\treturn __qca_phy_i2c_mii_read(dev_id, phy_addr, reg_addr, reg_data);\n\t}',
  '\t\t__qca_phy_i2c_mmd_read(dev_id, phy_addr, mmd_num, reg_addr, reg_data);\n\n\t} else {\n\t\t__qca_phy_i2c_mii_read(dev_id, phy_addr, reg_addr, reg_data);\n\t}\n\treturn SW_OK;',
  'phy-errors','PHY_FAILURE_PROPAGATION',True),
 ('discard-write-error','__qca_phy_i2c_write',
  '\t\treturn __qca_phy_i2c_mmd_write(dev_id, phy_addr, mmd_num, reg_addr, reg_data);\n\n\t} else {\n\t\treturn __qca_phy_i2c_mii_write(dev_id, phy_addr, reg_addr, reg_data);\n\t}',
  '\t\t__qca_phy_i2c_mmd_write(dev_id, phy_addr, mmd_num, reg_addr, reg_data);\n\n\t} else {\n\t\t__qca_phy_i2c_mii_write(dev_id, phy_addr, reg_addr, reg_data);\n\t}\n\treturn SW_OK;',
  'phy-errors','PHY_FAILURE_PROPAGATION',True),
)
