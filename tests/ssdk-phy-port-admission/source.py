"""PORT24 exact text preparation/extraction; saved audit programs are never imported."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent
PACKAGE = REPO / 'package/qca-nss/qca-ssdk'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
PATCH = '036-ssdk-admit-phy-port-values-before-root-side-effects.patch'
PATCH_SHA = 'e6c4df5b0c6e090c4004eabc54216da25f436f6184796ebc9d726225941e5f3a'
PLAN = REPO / 'tests/SSDK_PHY_PORT_ADMISSION_PLAN_2026-10-31.md'
PLAN_SHA = 'b85e958238ffe70e65d4882daf06138518435a0ffbb6d0d7edf50073531cfe62'
BASE_SHA = 'd681a1b6e47bddbd20eef1393768ba20716e2efc84bb0d1f52dc81c0e7a1d19a'
CANDIDATE_SHA = '8714f974183d4e68424d93f70fc0f85e61512cb770b033745c63ec5f402fadcd'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
DTS = 'src/init/ssdk_dts.c'
LINUX_OF = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-dt-admission/linux-of-base.c')
LINUX_OF_SHA = '3574ea911f2961c66969e5bbe0f3cc13b99f28c4151f1265064680dfbf4e43b4'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    return digest(Path(path).read_bytes())


def inventory(root):
    require(root.is_dir(), 'missing-tree')
    result = {}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'tree-symlink')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = identity(p)
    return result


def assets():
    require(sorted(p.name for p in SUPPORT.iterdir()) == OWNED, 'owned-inventory')
    return [REPO / 'tests/test-ssdk-phy-port-admission.py', *(SUPPORT / n for n in OWNED)]


def names():
    return sorted(p.name for p in (PACKAGE / 'patches').iterdir())


def recipe_gate(raw, expected, historical):
    if historical:
        require(raw.count(b'PKG_RELEASE:=14\n') == 1 and
                digest(raw.replace(b'PKG_RELEASE:=14\n', b'PKG_RELEASE:=13\n', 1)) == expected,
                'unique-complete-recipe14-to13')
    else:
        require(digest(raw) == expected, 'current24-strict-recipe')


def receipt(root, sha, layers, historical):
    require(identity(root / 'RESULTS.json') == sha, 'receipt-hash')
    data = json.loads((root / 'RESULTS.json').read_text())
    require(data['status'] == 'PASS_TEXT_ONLY' and data['pin'] == PIN and
            len(data['patches']) == layers, 'receipt-status-pin-layers')
    archive = (root / 'upstream.tar').read_bytes()
    require(digest(archive) == data['archive_sha256'], 'archive-hash')
    raw = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'archive-pin')
        for member in tar.getmembers():
            n = PurePosixPath(member.name)
            require(not n.is_absolute() and '..' not in n.parts and '.git' not in n.parts and
                    (member.isfile() or member.isdir()), 'archive-domain')
            if member.isfile():
                require(str(n) not in raw, 'archive-duplicate')
                raw[str(n)] = tar.extractfile(member).read()
    derived = {n: digest(v) for n, v in raw.items()}
    require(derived == data['upstream_files'], 'archive-all692')
    require(sorted(p.name for p in (root / 'patches').iterdir()) ==
            [p['name'] for p in data['patches']], 'saved-patch-inventory')
    for p in data['patches']:
        live = PACKAGE / 'patches' / p['name']
        require(identity(live) == identity(root / 'patches' / p['name']) == p['sha256'] ==
                data['inputs'][str(live)], 'patch-bytes')
        require(p['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and p['returncode'] == 0,
                'patch-status')
        for n, ctx in p['declared_context'].items():
            require(derived[n] == ctx['before_sha256'] and ctx['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in ctx['hunks']), 'context-chain')
            derived[n] = ctx['after_sha256']
    require(len(derived) == 692 and derived == data['prepared_files'] == inventory(root / 'prepared'),
            'prepared-all692')
    for n, sha in data['inputs'].items():
        raw_input = Path(n).read_bytes()
        if Path(n) == PACKAGE / 'Makefile':
            recipe_gate(raw_input, sha, historical)
        else:
            require(digest(raw_input) == sha, 'strict-input:' + n)
    return data, raw


def prepare(base, candidate, output):
    require(identity(PLAN) == PLAN_SHA, 'frozen-plan')
    require(identity(LINUX_OF) == LINUX_OF_SHA, 'linux-of-lookup-reference')
    sys.path.insert(0, str(REPO / 'tests'))
    from edma_patch_context import inspect_patch
    before, _ = receipt(base, BASE_SHA, 23, True)
    after, raw = receipt(candidate, CANDIDATE_SHA, 24, False)
    require(after['patches'][:-1] == before['patches'] and names() ==
            [p['name'] for p in after['patches']] and after['patches'][-1]['name'] == PATCH and
            after['patches'][-1]['sha256'] == PATCH_SHA, 'exact23-plus036-live24')
    tree = output / 'fresh24'
    tree.mkdir()
    for n, content in raw.items():
        p = tree / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    contexts = []
    for p in after['patches']:
        expected, ctx = inspect_patch(tree, (PACKAGE / 'patches' / p['name']).read_bytes())
        require(ctx == p['declared_context'], 'fresh-exact-context')
        for n, content in expected.items():
            (tree / n).write_bytes(content)
        contexts.append({'name': p['name'], 'context': ctx})
    require(inventory(tree) == after['prepared_files'], 'fresh692')
    changed, ctx = inspect_patch(base / 'prepared', (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(changed) == {DTS} and ctx == after['patches'][-1]['declared_context'], 'only-dts')
    derived = dict(before['prepared_files'])
    derived.update({n: digest(v) for n, v in changed.items()})
    require(derived == after['prepared_files'], 'all692-24-equals23-plus036')
    bound = set(assets()) | {PLAN, REPO / 'tests/edma_patch_context.py', LINUX_OF}
    bound.update(Path(n) for n in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    data = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
            'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
            'patches': names(), 'fresh_contexts': contexts, '036_context': ctx,
            'recipe': {'historical13': before['inputs'][str(PACKAGE / 'Makefile')],
                       'current14': identity(PACKAGE / 'Makefile'), 'only_full_reverse14_to13': True},
            'saved_members': {str(r): [p['name'] for p in d['patches']]
                              for r, d in [(base, before), (candidate, after)]},
            'inputs': {str(p): identity(p) for p in sorted(bound)},
            'scope': 'fresh current-repo pure inspect_patch text application, not make/build; no saved program import'}
    return tree, data


def stable(inputs):
    assets()
    require(names() == inputs['patches'], 'end-current-patches')
    for n, sha in inputs['inputs'].items():
        require(identity(n) == sha, 'end-input:' + n)
    for root, members in inputs['saved_members'].items():
        require(sorted(p.name for p in (Path(root) / 'patches').iterdir()) == members,
                'end-saved-patches:' + root)
    for key in ('base', 'candidate'):
        require(inventory(Path(inputs[key]) / 'prepared') == inputs[key + '_manifest'], 'end-tree:' + key)
    require(inventory(Path(inputs['fresh'])) == inputs['candidate_manifest'], 'end-fresh692')
    return 'ALL_FIXED_INPUTS_ASSETS_INVENTORIES_FULL692_STABLE_NOT_ATOMIC_LOCK'


def extract(tree, baseline=False):
    records, bodies = [], {}

    def record(path, name, raw, start):
        records.append({'path': path, 'symbol': name, 'start_line': start,
                        'end_line': start + raw.count('\n'), 'sha256': digest(raw.encode())})
        return raw

    def match(path, name, pattern):
        text = (tree / path).read_text()
        ms = list(re.finditer(pattern, text, re.M))
        require(len(ms) == 1, 'one-declaration:' + name)
        m = ms[0]
        return record(path, name, m.group(), text[:m.start()].count('\n') + 1)

    def function(name):
        text = (tree / DTS).read_text()
        ms = list(re.finditer(r'^[ \t]*(?:(?:static|int|void|sw_error_t|a_uint32_t)\s+)+' +
                              name + r'\s*\([^;{]*\)\s*\{', text, re.M))
        require(len(ms) == 1, 'one-complete-function:' + name)
        m = ms[0]
        masked = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                        lambda x: ' ' * len(x.group()), text)
        end, depth = text.index('{', m.start()) + 1, 1
        while depth:
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        bodies[name] = record(DTS, name, text[m.start():end], text[:m.start()].count('\n') + 1)

    types = []
    for path, kind, name in [('include/sal/os/aos_types.h', 'enum', 'a_bool_t'),
                             ('include/common/sw_error.h', 'enum', 'sw_error_t'),
                             ('include/init/ssdk_init.h', 'enum', 'hsl_reg_mode')]:
        types.append(match(path, name, r'typedef\s+' + kind + r'\s*\{[^}]*\}\s*' + name + r'\s*;'))
    for bits in (8, 16, 32):
        name = 'a_uint%d_t' % bits
        # Linux unsigned primitives are explicitly modeled by uintN_t. Public alias is actual.
        types.append(match('include/sal/os/aos_types.h', name, r'^typedef\s+__' + name + r'\s+' + name + r';'))
    types.append(match('include/hsl/phy/hsl_phy.h', 'phy_dac_t',
                       r'typedef\s+struct\s*\{[^}]*\}\s*phy_dac_t\s*;'))
    for path, names_ in [('include/common/sw_config.h', ['SW_MAX_NR_DEV', 'SW_MAX_NR_PORT']),
                         ('include/init/ssdk_dts.h', ['SSDK_PHY_RESET_GPIO_INDEX', 'SSDK_NETDEV_SWITCH_NUM']),
                         ('include/init/ssdk_plat.h', ['SSDK_MAX_GPIO', 'SSDK_INVALID_GPIO']),
                         ('include/hsl/phy/hsl_phy.h', ['PHY_I2C_ACCESS', 'TO_PHY_ADDR_E', 'TO_PHY_I2C_ADDR'])]:
        for name in names_:
            types.append(match(path, name, r'^#define\s+' + name + r'(?:\([^\n]*?\))?[ \t]+[^\n]*'))
    types.append(match('include/init/ssdk_init.h', 'feature-bits-and-macros',
                       r'enum\s*\{\s*QCA_PHY_F_CLAUSE45_BIT,[\s\S]*?^#define PHY_F_ERP_LOW_POWER[^\n]*'))
    private = []
    for name in ['ssdk_dt_access', 'ssdk_dt_prepared_node', 'ssdk_dt_admitted_node'] + ([] if baseline else ['ssdk_dt_port_values']):
        private.append(match(DTS, name, r'struct\s+' + name + r'\s*\{[^}]*\};'))
    for name in ['ssdk_dt_read_access_mode', 'ssdk_dt_get_switch_node', 'ssdk_dt_read_device_id',
                 'ssdk_dt_prepare_nodes', 'ssdk_switch_device_num_init', 'ssdk_switch_device_num_exit',
                 'ssdk_dt_parse_phy_info'] + ([] if baseline else ['ssdk_dt_read_port_values', 'ssdk_dt_validate_phy_ports']):
        function(name)
    return {'records': records, 'bodies': bodies, 'types': '\n'.join(types), 'private': '\n'.join(private)}


def render(current, baseline, template):
    new, old = extract(current), extract(baseline, True)
    require(new['types'] == old['types'], 'types-unchanged')
    b = new['bodies']
    order = ['ssdk_dt_read_port_values', 'ssdk_dt_validate_phy_ports', 'ssdk_dt_read_access_mode',
             'ssdk_dt_get_switch_node', 'ssdk_dt_read_device_id', 'ssdk_dt_prepare_nodes',
             'ssdk_switch_device_num_init', 'ssdk_switch_device_num_exit', 'ssdk_dt_parse_phy_info']
    text = template.replace('/* @TYPES@ */', new['types']).replace('/* @PRIVATE@ */', new['private'])
    text = text.replace('/* @FUNCTIONS@ */', '\n\n'.join(b[n] for n in order))
    reference = re.sub(r'\bssdk_dt_parse_phy_info\b', 'baseline_parse_phy', old['bodies']['ssdk_dt_parse_phy_info'])
    text = text.replace('/* @BASELINE@ */', reference)
    require(not re.search(r'@[A-Z_]+@', text), 'unfilled-placeholder')
    return text, new, old
