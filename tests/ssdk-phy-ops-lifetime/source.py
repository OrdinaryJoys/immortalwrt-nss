"""Frozen 36-layer input, exact local patch application and whole C extraction."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent
PATCH = REPO / 'package/qca-nss/qca-ssdk/patches/049-module-lifetime-shared-phy-ops.patch'
PATCH_SHA = '4f127a68d7e69fe10b3459f950ce6e87f138e565920ea96f1d589c51c1eb41d8'
EXTRACTOR = REPO / 'tests/nss-dp-containment/extract_prepared_c.py'
CONTEXT = REPO / 'tests/edma_patch_context.py'
spec = importlib.util.spec_from_file_location('phy_ops_lexical_reader', EXTRACTOR)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
context_spec = importlib.util.spec_from_file_location('phy_ops_declared_context', CONTEXT)
context = importlib.util.module_from_spec(context_spec)
context_spec.loader.exec_module(context)
PHY = 'src/hsl/phy/hsl_phy.c'
AQUA = 'src/hsl/phy/aquantia_phy.c'
HEADER = 'include/hsl/phy/hsl_phy.h'
BASE_INVENTORY = '016cdc5ad5f84bf76f52d2910bf88e14b3d617c25e56cdc7aaf6a1aac50cfb13'
FUNCTIONS = ('hsl_phy_api_ops_register', 'hsl_phy_api_ops_unregister',
             'hsl_phy_api_ops_get', 'phy_api_ops_init', 'ssdk_phy_driver_cleanup')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'input symlink')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return result


def inventory_hash(rows):
    return sha((json.dumps(rows, sort_keys=True, separators=(',', ':')) + '\n').encode())


def check_prepared(root, expected):
    """Only two recipe metadata forms are excluded from the fixed code inventory."""
    files = inventory(root)
    directories = {str(parent) for name in expected for parent in Path(name).parents
                   if str(parent) != '.'}
    require(all(path.relative_to(root).as_posix() in directories
                for path in root.rglob('*') if path.is_dir()), 'unexpected prepared directory')
    metadata = {}
    for name in list(files):
        if name == 'version.date' or ('/' not in name and name.startswith('.prepared_')):
            raw = (root / name).read_bytes()
            require(sha(raw) == files[name], 'recipe metadata changed during read')
            if name == 'version.date':
                require(re.fullmatch(rb'[0-9]+\n', raw) is not None, 'dirty version.date')
                kind = 'ROOT_DECIMAL_NEWLINE_VERSION_DATE'
            else:
                require(raw == b'', 'dirty .prepared marker')
                kind = 'ROOT_EMPTY_PREPARED_MARKER'
            metadata[name] = {'kind': kind, 'bytes': len(raw), 'sha256': files.pop(name)}
    require(files == expected, 'actual prepared37 must equal frozen36 plus049, every file')
    return files, metadata


def prepare(baseline, out, patch_tool):
    require(sha(PATCH.read_bytes()) == PATCH_SHA, 'frozen 049 identity')
    before = inventory(baseline)
    require(len(before) == 692 and inventory_hash(before) == BASE_INVENTORY,
            'exact frozen baseline36 inventory required; do not refresh automatically')
    expected, declared = context.inspect_patch(baseline, PATCH.read_bytes())
    try:
        context.inspect_patch(baseline, PATCH.read_bytes()[:-2])
    except ValueError as error:
        require(str(error) == 'truncated hunk', 'exact truncated-hunk negative gate')
    else:
        raise RuntimeError('truncated patch accepted')
    candidate = out / 'candidate37'
    candidate.mkdir()
    for rel in before:
        target = candidate / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((baseline / rel).read_bytes())
    applied = subprocess.run([patch_tool, '-p1', '--fuzz=0', '--batch',
                              '-i', str(PATCH)], cwd=candidate,
                             capture_output=True, text=True, timeout=30)
    (out / 'patch.stdout').write_text(applied.stdout)
    (out / 'patch.stderr').write_text(applied.stderr)
    require(applied.returncode == 0 and not applied.stderr and
            not re.search(r'offset|fuzz|FAILED|Reversed', applied.stdout, re.I),
            '049 exact coordinates/context required')
    context.verify_applied(candidate, expected)
    after = inventory(candidate)
    require(set(after) == set(before) and
            {name for name in before if before[name] != after[name]} == {PHY, AQUA},
            'full692 candidate, 049 only two source files')
    return candidate, before, declared


def typedef(text, name):
    masked = extract.code_mask(text)
    end = re.search(r'\}\s*' + re.escape(name) + r'\s*;', masked)
    require(end is not None, 'typedef end ' + name)
    starts = list(re.finditer(r'\btypedef\s+(?:enum|struct)\b[^;{}]*\{', masked[:end.end()]))
    require(bool(starts), 'typedef start ' + name)
    start = starts[-1].start()
    return text[start:end.end()] + '\n'


def mapping(text, old):
    pairs, mini = [], False
    for line in text.splitlines():
        if line.strip() == '#ifndef IN_PORTCONTROL_MINI':
            require(not mini, 'nested MINI mapping')
            mini = True
        elif line.strip() == '#endif':
            mini = False
        else:
            pattern = (r'aquantia_phy_api_ops->(\w+)\s*=\s*(\w+)\s*;' if old else
                       r'\.(\w+)\s*=\s*(\w+)\s*,')
            match = re.fullmatch(r'\s*' + pattern + r'\s*', line)
            if match:
                pairs.append((*match.groups(), mini))
    require(pairs and len({p[0] for p in pairs}) == len(pairs), 'mapping fields unique')
    return pairs


def fragments(baseline, candidate):
    phy = (candidate / PHY).read_text()
    aqua = (candidate / AQUA).read_text()
    old_aqua = (baseline / AQUA).read_text()
    start = re.search(r'^static hsl_phy_ops_t aquantia_phy_api_ops = \{', aqua, re.M)
    require(start is not None, 'static complete Aquantia table')
    table = aqua[start.start():extract.block_end(aqua, aqua.index('{', start.start()))] + ';\n'
    pairs = mapping(extract.function(old_aqua, 'aquantia_phy_api_ops_init'), True)
    require(mapping(table, False) == pairs, 'all original Aquantia mappings and MINI guards')
    old_directives = re.findall(r'^#(?:if\w*|else|endif).*$',
                               extract.function(old_aqua, 'aquantia_phy_api_ops_init'), re.M)
    require(re.findall(r'^#(?:if\w*|else|endif).*$', table, re.M) == old_directives,
            'complete original MINI directive sequence')
    require('phy_ops_flag' not in extract.function(aqua, 'aquantia_phy_init') and
            not re.search(r'\b(?:kzalloc|kfree|phy_api_ops_init)\s*\(',
                          extract.function(aqua, 'aquantia_phy_api_ops_init')),
            'static Aquantia no heap/reset/latch')
    funcs = {name: extract.function(phy, name) for name in FUNCTIONS}
    funcs.update({name: extract.function(aqua, name) for name in
                  ('aquantia_phy_api_ops_init', 'aquantia_phy_init')})
    header = (baseline / HEADER).read_text()
    start = header.index('\ttypedef enum {')
    finish = header.index('} hsl_phy_ops_t;') + len('} hsl_phy_ops_t;')
    types = header[start:finish] + '\n'
    for name in ('phy_driver_instance_t', 'phy_type_t', 'phy_dac_t', 'phy_info_t'):
        types += typedef(header, name)
    errors = typedef((baseline / 'include/common/sw_error.h').read_text(), 'sw_error_t')
    config = (baseline / 'include/common/sw_config.h').read_text()
    limits = '\n'.join(re.findall(r'^#define SW_MAX_NR_(?:DEV|PORT)\s+\d+\s*$', config, re.M))
    require(len(limits.splitlines()) == 2, 'actual fixed capacities')
    aliases = ''.join('typedef unsigned ' + name + ';\n' for name in sorted(set(
        re.findall(r'\b(?:fal_\w+|led_ctrl_pattern_t)\b', types))))
    structs = ''.join('struct ' + name + ';\n' for name in sorted(set(
        re.findall(r'\bstruct\s+(\w+)\s*\*', types))))
    callback_defs = []
    common = (baseline / 'src/hsl/phy/qcaphy_c45_common.c').read_text()
    for name in sorted({p[1] for p in pairs}):
        actual = extract.function(common if name.startswith('qcaphy_') else old_aqua, name)
        prototype = actual[:actual.index('{')].rstrip()
        callback_defs.append(prototype + '\n{ host_callback_unlocked(); return SW_OK; }\n')
    expected = ['static void check_mapping(void) {', 'hsl_phy_ops_t expected;',
                'memset(&expected, 0, sizeof(expected));']
    for field, callback, mini in pairs:
        if mini:
            expected.append('#ifndef IN_PORTCONTROL_MINI')
        expected.append('expected.' + field + ' = ' + callback + ';')
        if mini:
            expected.append('#endif')
    expected += ['check(!memcmp(&expected, &aquantia_phy_api_ops, sizeof(expected)), "mapping");', '}']
    lock = re.search(r'^static DEFINE_SPINLOCK\(ssdk_phy_ops_lock\);$', phy, re.M)
    require(lock is not None and '#include <linux/spinlock.h>' in phy, 'actual spinlock definition/include')
    # The table has an incomplete [] declarator, handled without rewriting its body.
    begin = phy.index('phy_driver_instance_t ssdk_phy_driver[]')
    opening = phy.index('{', begin)
    globals_c = ('phy_info_t *phy_info[SW_MAX_NR_DEV];\na_uint32_t port_bmp[SW_MAX_NR_DEV];\n' +
                 lock.group() + '\n' + phy[begin:extract.block_end(phy, opening)] + ';\n')
    return dict(funcs=funcs, table=table, pairs=pairs, globals=globals_c,
                types=errors + '\n' + limits + '\n' + aliases + structs + types,
                callbacks='\n'.join(callback_defs), expected='\n'.join(expected),
                old={name: extract.function((baseline / PHY).read_text(), name)
                     for name in ('hsl_phy_api_ops_get', 'ssdk_phy_driver_cleanup')})


def program(data, funcs=None, table=None):
    funcs = data['funcs'] if funcs is None else funcs
    text = (SUPPORT / 'fixture.c').read_text()
    parts = {'TYPES': data['types'], 'GLOBALS': data['globals'],
             'CALLBACKS': data['callbacks'], 'TABLE': data['table'] if table is None else table,
             'REGISTRY': '\n'.join(funcs[n] for n in FUNCTIONS),
             'AQUA': '\n'.join(funcs[n] for n in ('aquantia_phy_api_ops_init', 'aquantia_phy_init')),
             'MAPPING': data['expected']}
    for name, value in parts.items():
        marker = '/* ' + name + ' */'
        require(text.count(marker) == 1, 'fixture marker ' + name)
        text = text.replace(marker, value)
    return text
