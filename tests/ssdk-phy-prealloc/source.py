"""Exact22 source derivation and complete-body extraction; no sealed code imports."""
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
PATCH = '034-ssdk-stage-pre-dt-phy-metadata.patch'
PATCH_SHA = '98b5cae60f8cd63f810b5faaf72580a8fc9b29a1e079dae751c54dbca44dbef2'
BASE_SHA = '369005003b0806d4b7c44af39ca0e75d08606dc0d8001b593e8659e46ea393df'
CANDIDATE_SHA = '669ef0065f55d329ce8f293d72a432139db828ae665ac25d95957542e11a5a7f'
PLAN_SHA = '0c82c933a834b9a21d4a05c929fa1907a487aadd0ccc89996401e66006a29d39'
OWNED = ['README.md', 'fixture.c', 'linux-phy-interface.h', 'mutations.py', 'source.py']
PHY = 'src/hsl/phy/hsl_phy.c'
ROOT = 'src/init/ssdk_init.c'


def require(ok, marker):
    if not ok:
        raise RuntimeError(marker)


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
    return [REPO / 'tests/test-ssdk-phy-prealloc.py', *(SUPPORT / n for n in OWNED)]


def patch_names():
    return sorted(p.name for p in (PACKAGE / 'patches').glob('*.patch'))


def receipt(root, expected_sha, layers, historical):
    require(identity(root / 'RESULTS.json') == expected_sha, 'receipt-identity')
    data = json.loads((root / 'RESULTS.json').read_text())
    require(data['pin'] == PIN and data['status'] == 'PASS_TEXT_ONLY' and
            len(data['patches']) == layers, 'receipt-pin-status-layers')
    archive = (root / 'upstream.tar').read_bytes()
    require(digest(archive) == data['archive_sha256'], 'archive-identity')
    raw = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'archive-pin')
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and '.git' not in name.parts
                    and (member.isdir() or member.isfile()), 'archive-member')
            if member.isfile():
                require(str(name) not in raw, 'archive-duplicate')
                raw[str(name)] = tar.extractfile(member).read()
    require({k: digest(v) for k, v in raw.items()} == data['upstream_files'], 'archive-manifest')
    names = [p['name'] for p in data['patches']]
    require(sorted(p.name for p in (root / 'patches').iterdir()) == names, 'saved-patch-inventory')
    derived = dict(data['upstream_files'])
    for p in data['patches']:
        path = PACKAGE / 'patches' / p['name']
        require(identity(path) == identity(root / 'patches' / p['name']) == p['sha256'] ==
                data['inputs'][str(path)], 'saved-live-patch')
        require(p['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and p['returncode'] == 0,
                'receipt-patch-status')
        for name, ctx in p['declared_context'].items():
            require(derived.get(name) == ctx['before_sha256'] and ctx['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in ctx['hunks']), 'receipt-context')
            derived[name] = ctx['after_sha256']
    require(derived == data['prepared_files'] and len(derived) == 692 and
            inventory(root / 'prepared') == derived, 'whole-receipt-tree')
    delta = None
    for name, sha in data['inputs'].items():
        content = Path(name).read_bytes()
        if historical and Path(name) == PACKAGE / 'Makefile':
            require(content.count(b'PKG_RELEASE:=12\n') == 1 and
                    digest(content.replace(b'PKG_RELEASE:=12\n', b'PKG_RELEASE:=11\n', 1)) == sha,
                    'only-unique-recipe11-to12')
            delta = {'path': name, 'baseline_sha256': sha, 'actual_sha256': digest(content),
                     'only_delta': 'unique exact PKG_RELEASE:=11 newline -> :=12 newline'}
        else:
            require(digest(content) == sha, 'strict-live-input:' + name)
    return data, raw, delta


def prepare(base, candidate, output):
    sys.path.insert(0, str(REPO / 'tests'))
    from edma_patch_context import inspect_patch
    require(identity(REPO / 'tests/SSDK_PHY_PREALLOC_PLAN_2026-10-30.md') == PLAN_SHA,
            'frozen-plan-identity')
    before, _, delta = receipt(base, BASE_SHA, 21, True)
    after, raw, _ = receipt(candidate, CANDIDATE_SHA, 22, False)
    require(after['patches'][:-1] == before['patches'] and patch_names() ==
            [p['name'] for p in after['patches']] and after['patches'][-1]['name'] == PATCH and
            after['patches'][-1]['sha256'] == PATCH_SHA, 'exact21-plus034-live22')
    tree = output / 'fresh22'
    tree.mkdir()
    for name, content in raw.items():
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    contexts = []
    for entry in after['patches']:
        expected, context = inspect_patch(tree, (PACKAGE / 'patches' / entry['name']).read_bytes())
        require(context == entry['declared_context'], 'fresh-exact-declared-context')
        for name, content in expected.items():
            (tree / name).write_bytes(content)
        contexts.append({'name': entry['name'], 'context': context})
    require(inventory(tree) == after['prepared_files'], 'fresh-all692-exact22')
    expected, context = inspect_patch(base / 'prepared', (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(expected) == {'include/hsl/phy/hsl_phy.h', PHY, ROOT} and
            context == after['patches'][-1]['declared_context'], '034-only-three-files')
    derived = dict(before['prepared_files'])
    derived.update({name: digest(content) for name, content in expected.items()})
    require(derived == after['prepared_files'], 'all692-22-equals21-plus034')
    bound = set(assets()) | {REPO / 'tests/edma_patch_context.py',
                             REPO / 'tests/SSDK_PHY_PREALLOC_PLAN_2026-10-30.md'}
    bound.update(Path(name) for name in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    result = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
              'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
              'patches': patch_names(), 'fresh_contexts': contexts, 'recipe_delta': delta,
              'receipt_sha256': {'base': BASE_SHA, 'candidate': CANDIDATE_SHA},
              'inputs': {str(p): identity(p) for p in sorted(bound)},
              'preparation': 'Current repo inspect_patch, exact-context in-memory text application, all692 files. No sealed code, shell patch, make or compiler used for preparation.'}
    return tree, result


def stable(inputs):
    assets()
    require(patch_names() == inputs['patches'], 'end-patch-inventory')
    for name, sha in inputs['inputs'].items():
        require(identity(name) == sha, 'end-input-drift:' + name)
    for key, manifest in [('base', 'base_manifest'), ('candidate', 'candidate_manifest')]:
        require(inventory(Path(inputs[key]) / 'prepared') == inputs[manifest], 'end-tree:' + key)
    require(inventory(Path(inputs['fresh'])) == inputs['candidate_manifest'], 'end-fresh-tree')
    return 'ALL_BOUND_BYTES_AND_FULL692_TREES_STABLE_NOT_ATOMIC_LOCK'


def extract(tree):
    records, bodies = [], {}

    def record(path, label, text, start):
        records.append({'path': path, 'symbol': label, 'start_line': start,
                        'end_line': start + text.count('\n'), 'sha256': digest(text.encode()),
                        'classification': 'complete body/declaration, unchanged bytes'})
        return text

    def decl(path, kind, name):
        text = (tree / path).read_text()
        matches = list(re.finditer(r'typedef\s+' + kind + r'\s*\{[^}]*\}\s*' + name + r'\s*;', text))
        require(len(matches) == 1, 'one-declaration:' + name)
        m = matches[0]
        return record(path, name, m.group(), text[:m.start()].count('\n') + 1)

    def function(path, name):
        text = (tree / path).read_text()
        pat = r'^[ \t]*(?:(?:static|int|void|sw_error_t|a_uint32_t|__init)\s+)+\b' + name + r'\s*\([^;{]*\)\s*\{'
        matches = list(re.finditer(pat, text, re.M))
        require(len(matches) == 1, 'one-function:' + name)
        m = matches[0]
        # Strip strings/comments only for balanced-brace positions, preserving length.
        masked = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                        lambda x: ' ' * len(x.group()), text)
        opening = text.index('{', m.start())
        depth = 1
        end = opening + 1
        while depth:
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        body = record(path, name, text[m.start():end], text[:m.start()].count('\n') + 1)
        bodies[name] = body
        return body

    def defines(path, names):
        text = (tree / path).read_text()
        rows = []
        for name in names:
            ms = list(re.finditer(r'^#define\s+' + re.escape(name) + r'(?:\([^\n]*?\))?[ \t]+[^\n]*', text, re.M))
            require(len(ms) == 1, 'one-define:' + name)
            m = ms[0]
            rows.append(record(path, name, m.group(), text[:m.start()].count('\n') + 1))
        return '\n'.join(rows)

    init_h = 'include/init/ssdk_init.h'
    phy_h = 'include/hsl/phy/hsl_phy.h'
    types = [decl('include/sal/os/aos_types.h', 'enum', 'a_bool_t'),
             decl('include/common/sw_error.h', 'enum', 'sw_error_t'),
             decl(init_h, 'enum', 'ssdk_chip_type')]
    feature_text = (tree / init_h).read_text()
    m = re.search(r'enum\s*\{\s*QCA_PHY_F_CLAUSE45_BIT,[^}]*\};', feature_text)
    require(m is not None, 'complete-feature-enum')
    types += [record(init_h, 'feature-bit-enum', m.group(), feature_text[:m.start()].count('\n') + 1),
              defines(init_h, ['phy_features_t', '__PHY_F_BIT', '_PHY_F', 'PHY_F_I2C', 'PORT_LINK_DOWN']),
              defines('include/common/sw_config.h', ['SW_MAX_NR_DEV', 'SW_MAX_NR_PORT']),
              defines('include/init/ssdk_plat.h', ['SSDK_PHYSICAL_PORT0', 'SSDK_PHYSICAL_PORT7']),
              defines(phy_h, ['PHY_MDIO_ACCESS', 'PHY_I2C_ACCESS', 'INVALID_PHY_ADDR']),
              decl(phy_h, 'enum', 'phy_type_t'), decl(phy_h, 'struct', 'phy_dac_t'),
              decl(phy_h, 'struct', 'phy_info_t'),
              decl('include/fal/fal_port_ctrl.h', 'enum', 'fal_port_interface_mode_t')]
    phy = (tree / PHY).read_text()
    header = (tree / phy_h).read_text()
    apis = []
    api_names = ['qca_ssdk_phy_info_init']
    if 'qca_ssdk_phy_info_prepare(' in phy:
        api_names += ['qca_ssdk_phy_info_prepare', 'qca_ssdk_phy_info_publish']
    for name in api_names:
        matches = list(re.finditer(r'\bint\s+' + name + r'\s*\([^;{}]*\);', header))
        require(len(matches) == 1, 'one-public-prototype:' + name)
        m = matches[0]
        apis.append(record(phy_h, name + ':prototype', m.group(), header[:m.start()].count('\n') + 1))
    table = re.search(r'typedef struct\s*\{[^}]*\}\s*qca808x_phy_info_t;[\s\S]*?static qca808x_phy_info_t qca808x_phy_info\[\]\s*=\s*\{[^}]*\}[^;]*;', phy)
    require(table is not None, 'qca-table')
    qca = record(PHY, 'qca808x-type-and-table', table.group(), phy[:table.start()].count('\n') + 1)
    function(PHY, 'qca_ssdk_qca808x_phy_info_prepare' if 'qca_ssdk_phy_info_prepare(' in phy else 'qca_ssdk_qca808x_phy_info_init')
    for name in ['qca_ssdk_phy_info_init', 'qca_ssdk_port_bmp_init', 'qca_ssdk_port_bmp_set',
                 'qca_ssdk_port_bmp_get', 'hsl_port_feature_set', 'hsl_port_feature_clear']:
        function(PHY, name)
    if 'qca_ssdk_phy_info_prepare(' in phy:
        for name in ['qca_ssdk_phy_info_prepare', 'qca_ssdk_phy_info_publish']:
            function(PHY, name)
    for name in ['ssdk_alloc_priv', 'ssdk_free_priv', 'regi_init', 'qca_fdb_sw_sync_work_setup']:
        function(ROOT, name)
    function('src/init/ssdk_interrupt.c', 'qca_intr_work_init')
    macro = (tree / 'include/common/shared_func.h').read_text()
    start = macro.index('#define SW_CNTU_ON_ERROR_AND_COND1_OR_GOTO_OUT')
    macro = macro[start:macro.index('\n\n', start)]
    return {'types': '\n'.join(types), 'qca': qca, 'bodies': bodies, 'macro': macro, 'apis': '\n'.join(apis),
            'records': records}


def render(current, baseline, template):
    new, old = extract(current), extract(baseline)
    require(new['types'] == old['types'] and new['qca'] == old['qca'], 'unchanged-actual-types-table')
    rename = {'phy_info': 'reference_phy_info', 'port_bmp': 'reference_port_bmp',
              'qca808x_phy_info': 'reference_qca808x_phy_info',
              'qca808x_phy_info_t': 'reference_qca808x_phy_info_t'}
    reference_names = ['qca_ssdk_qca808x_phy_info_init', 'qca_ssdk_phy_info_init',
                       'qca_ssdk_port_bmp_set', 'hsl_port_feature_set', 'hsl_port_feature_clear']
    rename.update({n: 'reference_' + n for n in reference_names})
    ref = old['qca'] + '\n' + '\n'.join(old['bodies'][n] for n in reference_names)
    ref = re.sub(r'\b(' + '|'.join(rename) + r')\b', lambda m: rename[m.group()], ref)
    ref = re.sub(r'\bkzalloc\b', 'reference_alloc', ref)
    order = ['qca_ssdk_port_bmp_set', 'hsl_port_feature_set', 'hsl_port_feature_clear',
             'qca_ssdk_qca808x_phy_info_prepare', 'qca_ssdk_phy_info_prepare',
             'qca_ssdk_phy_info_publish', 'qca_ssdk_phy_info_init', 'qca_ssdk_port_bmp_init',
             'qca_ssdk_port_bmp_get', 'qca_fdb_sw_sync_work_setup', 'qca_intr_work_init',
             'ssdk_alloc_priv', 'ssdk_free_priv', 'regi_init']
    qca_names = {'qca_ssdk_qca808x_phy_info_prepare'}
    code = []
    for name in order:
        body = new['bodies'][name]
        code.append('#ifdef QCA808X_PORTS_INFO\n' + body + '\n#endif' if name in qca_names else body)
    ref = '#ifdef QCA808X_PORTS_INFO\n' + ref[:ref.index('int reference_qca_ssdk_phy_info_init')] + '\n#endif\n' + ref[ref.index('int reference_qca_ssdk_phy_info_init'):]
    # Reference helper definitions are ordered/prototyped by the harness.
    result = template.replace('/* @TYPES@ */', new['types'])
    result = result.replace('/* @APIS@ */', new['apis'])
    result = result.replace('/* @MACRO@ */', new['macro'])
    result = result.replace('/* @QCA@ */', '#ifdef QCA808X_PORTS_INFO\n' + new['qca'] + '\n#endif')
    result = result.replace('/* @REFERENCE@ */', ref)
    result = result.replace('/* @FUNCTIONS@ */', '\n\n'.join(code))
    require('@TYPES@' not in result and '@FUNCTIONS@' not in result, 'unfilled-placeholder')
    alloc = new['bodies']['ssdk_alloc_priv']
    require(alloc.index('qca_ssdk_phy_info_publish(') < alloc.index('qca_phy_priv_global = prepared;'),
            'source-meta-before-private-publication')
    return result, {'candidate': new['records'], 'baseline': old['records'],
                    'reference_derivation': rename, 'root': 'complete body compiled HPPE/IN_NETLINK; topology/cfg leaf; success longjmp at first DT or zero-count postloop; no full-root execution',
                    'linux_interface_enum': 'linux-phy-interface.h exact complete enum from pinned primary',
                    'models': 'Linux private struct/work/locks and topology leaves explicit, not target ABI/RCU/work runtime'}, new, old
