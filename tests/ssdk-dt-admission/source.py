"""DT23 exact source identity and extraction. Never execute saved audit code."""
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
PATCH = '035-ssdk-admit-dt-nodes-before-root-allocation.patch'
PATCH_SHA = '90a192cb25d0518a92dcfcfe6812843192a247135e715208fe36c57e504bfd93'
PLAN = REPO / 'tests/SSDK_DT_ADMISSION_PLAN_2026-10-31.md'
PLAN_SHA = 'c27b3e0e5a28f3e90ffe502b571aa07277001b3553ce8fa46bf202c2aec838b5'
BASE_SHA = '669ef0065f55d329ce8f293d72a432139db828ae665ac25d95957542e11a5a7f'
CANDIDATE_SHA = 'd681a1b6e47bddbd20eef1393768ba20716e2efc84bb0d1f52dc81c0e7a1d19a'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
DTS = 'src/init/ssdk_dts.c'


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


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
    return [REPO / 'tests/test-ssdk-dt-admission.py', *(SUPPORT / p for p in OWNED)]


def names():
    return sorted(p.name for p in (PACKAGE / 'patches').glob('*.patch'))


def recipe_gate(raw, expected, historical):
    if historical:
        require(raw.count(b'PKG_RELEASE:=13\n') == 1 and
                digest(raw.replace(b'PKG_RELEASE:=13\n', b'PKG_RELEASE:=12\n', 1)) == expected,
                'only-complete-recipe12-to13')
    else:
        require(digest(raw) == expected, 'current23-strict-recipe')


def receipt(root, sha, layers, historical):
    require(identity(root / 'RESULTS.json') == sha, 'receipt-identity')
    data = json.loads((root / 'RESULTS.json').read_text())
    require(data['status'] == 'PASS_TEXT_ONLY' and data['pin'] == PIN and
            len(data['patches']) == layers, 'receipt-status-pin-layers')
    archive = (root / 'upstream.tar').read_bytes()
    require(digest(archive) == data['archive_sha256'], 'archive-identity')
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
    require(derived == data['upstream_files'], 'archive-all-files')
    require(sorted(p.name for p in (root / 'patches').iterdir()) ==
            [p['name'] for p in data['patches']], 'saved-patch-inventory')
    for entry in data['patches']:
        p = PACKAGE / 'patches' / entry['name']
        require(identity(p) == identity(root / 'patches' / entry['name']) == entry['sha256'] ==
                data['inputs'][str(p)], 'patch-identities')
        require(entry['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and entry['returncode'] == 0,
                'patch-status')
        for n, ctx in entry['declared_context'].items():
            require(derived.get(n) == ctx['before_sha256'] and ctx['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in ctx['hunks']), 'context-chain')
            derived[n] = ctx['after_sha256']
    require(len(derived) == 692 and derived == data['prepared_files'] == inventory(root / 'prepared'),
            'whole692-receipt')
    for name, expected in data['inputs'].items():
        content = Path(name).read_bytes()
        if Path(name) == PACKAGE / 'Makefile':
            recipe_gate(content, expected, historical)
        else:
            require(digest(content) == expected, 'strict-input:' + name)
    return data, raw


def prepare(base, candidate, output):
    require(identity(PLAN) == PLAN_SHA, 'frozen-plan')
    sys.path.insert(0, str(REPO / 'tests'))
    from edma_patch_context import inspect_patch
    before, _ = receipt(base, BASE_SHA, 22, True)
    after, raw = receipt(candidate, CANDIDATE_SHA, 23, False)
    require(after['patches'][:-1] == before['patches'] and names() ==
            [p['name'] for p in after['patches']] and after['patches'][-1]['name'] == PATCH and
            after['patches'][-1]['sha256'] == PATCH_SHA, 'exact22-plus035-live23')
    tree = output / 'fresh23'; tree.mkdir()
    for name, content in raw.items():
        p = tree / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
    contexts = []
    for entry in after['patches']:
        expected, ctx = inspect_patch(tree, (PACKAGE / 'patches' / entry['name']).read_bytes())
        require(ctx == entry['declared_context'], 'fresh-exact-context')
        for name, content in expected.items():
            (tree / name).write_bytes(content)
        contexts.append({'name': entry['name'], 'context': ctx})
    require(inventory(tree) == after['prepared_files'], 'fresh692-output')
    expected, ctx = inspect_patch(base / 'prepared', (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(expected) == {DTS} and ctx == after['patches'][-1]['declared_context'], 'only-dts-change')
    derived = dict(before['prepared_files']); derived.update({n: digest(v) for n, v in expected.items()})
    require(derived == after['prepared_files'], 'all692-23-equals22-plus035')
    bound = set(assets()) | {PLAN, REPO / 'tests/edma_patch_context.py'}
    bound.update(Path(n) for n in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar']); bound.update((root / 'patches').iterdir())
    result = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
              'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
              'patches': names(), 'fresh_contexts': contexts, '035_context': ctx,
              'recipe_delta': {'before': before['inputs'][str(PACKAGE / 'Makefile')],
                               'current': identity(PACKAGE / 'Makefile'), 'unique_release12_to13': True},
              'saved_patch_members': {str(base): [p['name'] for p in before['patches']],
                                      str(candidate): [p['name'] for p in after['patches']]},
              'inputs': {str(p): identity(p) for p in sorted(bound)},
              'preparation': 'Fresh byte application by current repo inspect_patch only, exact coordinates/context/output; no sealed program or target build.'}
    return tree, result


def stable(inputs):
    assets(); require(names() == inputs['patches'], 'end-patch-inventory')
    for n, sha in inputs['inputs'].items(): require(identity(n) == sha, 'end-input:' + n)
    for root, expected in inputs['saved_patch_members'].items():
        require(sorted(p.name for p in (Path(root) / 'patches').iterdir()) == expected,
                'end-saved-patch-members:' + root)
    for key, manifest in [('base', 'base_manifest'), ('candidate', 'candidate_manifest')]:
        require(inventory(Path(inputs[key]) / 'prepared') == inputs[manifest], 'end-tree:' + key)
    require(inventory(Path(inputs['fresh'])) == inputs['candidate_manifest'], 'end-fresh-tree')
    return 'ALL_BOUND_INPUTS_ASSETS_AND_FULL692_TREES_STABLE_NOT_ATOMIC_LOCK'


def extract(tree):
    records, bodies = [], {}

    def record(path, name, text, start):
        records.append({'path': path, 'symbol': name, 'start_line': start,
                        'end_line': start + text.count('\n'), 'sha256': digest(text.encode())})
        return text

    def function(path, name):
        text = (tree / path).read_text()
        ms = list(re.finditer(r'^[ \t]*(?:(?:static|int|void|sw_error_t|a_uint32_t|__init)\s+)+' +
                              name + r'\s*\([^;{]*\)\s*\{', text, re.M))
        require(len(ms) == 1, 'one-complete-function:' + name)
        m = ms[0]; opening = text.index('{', m.start()); end, depth = opening + 1, 1
        masked = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                        lambda x: ' ' * len(x.group()), text)
        while depth:
            depth += (masked[end] == '{') - (masked[end] == '}'); end += 1
        body = record(path, name, text[m.start():end], text[:m.start()].count('\n') + 1)
        bodies[name] = body

    def decl(path, kind, name):
        t = (tree / path).read_text()
        ms = list(re.finditer(r'typedef\s+' + kind + r'\s*\{[^}]*\}\s*' + name + r'\s*;', t))
        require(len(ms) == 1, 'one-declaration:' + name)
        m = ms[0]; return record(path, name, m.group(), t[:m.start()].count('\n') + 1)

    def define(path, name):
        t = (tree / path).read_text()
        ms = list(re.finditer(r'^#define\s+' + name + r'[ \t]+[^\n]*', t, re.M))
        require(len(ms) == 1, 'one-constant:' + name)
        m = ms[0]; return record(path, name, m.group(), t[:m.start()].count('\n') + 1)

    types = [decl('include/sal/os/aos_types.h', 'enum', 'a_bool_t'),
             decl('include/common/sw_error.h', 'enum', 'sw_error_t'),
             decl('include/init/ssdk_init.h', 'enum', 'hsl_reg_mode'),
             decl('include/init/ssdk_init.h', 'enum', 'ssdk_chip_type'),
             define('include/common/sw_config.h', 'SW_MAX_NR_DEV'),
             define('include/init/ssdk_plat.h', 'SSDK_PHYSICAL_PORT7')]
    t = (tree / DTS).read_text(); private = []
    current = 'ssdk_dt_prepare_nodes(' in t
    if current:
        for name in ['ssdk_dt_access', 'ssdk_dt_prepared_node', 'ssdk_dt_admitted_node']:
            m = re.search(r'struct\s+' + name + r'\s*\{[^}]*\};', t)
            require(m is not None, 'private-struct:' + name)
            private.append(record(DTS, name, m.group(), t[:m.start()].count('\n') + 1))
    names_ = ['ssdk_dt_get_switch_node', 'ssdk_dt_parse', 'ssdk_switch_device_num_init',
              'ssdk_switch_device_num_exit', 'ssdk_switch_device_num_get']
    names_ += ['ssdk_dt_read_access_mode', 'ssdk_dt_read_device_id', 'ssdk_dt_prepare_nodes'] if current else ['ssdk_dt_parse_access_mode']
    for name in names_: function(DTS, name)
    function('src/init/ssdk_init.c', 'regi_init')
    macro = (tree / 'include/common/shared_func.h').read_text()
    start = macro.index('#define SW_CNTU_ON_ERROR_AND_COND1_OR_GOTO_OUT')
    macro = macro[start:macro.index('\n\n', start)]
    return {'records': records, 'bodies': bodies, 'types': '\n'.join(types),
            'private': '\n'.join(private), 'macro': macro}


def render(current, baseline, template):
    new, old = extract(current), extract(baseline)
    require(new['types'] == old['types'] and new['bodies']['regi_init'] == old['bodies']['regi_init'],
            'root-and-enums-unchanged')
    b = new['bodies']; parts = []
    for n in ['ssdk_dt_read_access_mode', 'ssdk_dt_get_switch_node', 'ssdk_dt_read_device_id',
              'ssdk_dt_prepare_nodes', 'ssdk_dt_parse']:
        parts.append('#if DT_NATIVE\n' + b[n] + '\n#endif')
    for n in ['ssdk_switch_device_num_init', 'ssdk_switch_device_num_exit', 'ssdk_switch_device_num_get']:
        parts.append(b[n])
    ref = old['bodies']['ssdk_dt_parse_access_mode']
    ref = re.sub(r'\bssdk_dt_parse_access_mode\b', 'reference_access', ref)
    old_lookup = old['bodies']['ssdk_dt_get_switch_node'].replace('ssdk_dt_get_switch_node', 'old_lookup')
    old_parse = old['bodies']['ssdk_dt_parse'].replace('ssdk_dt_parse_access_mode', 'reference_access').replace('ssdk_dt_get_switch_node', 'old_lookup')
    old_parse = re.sub(r'\bssdk_dt_parse\b', 'old_parse', old_parse)
    text = template.replace('/* @TYPES@ */', new['types']).replace('/* @PRIVATE@ */', new['private'])
    text = text.replace('/* @MACRO@ */', new['macro']).replace('/* @FUNCTIONS@ */', '\n\n'.join(parts))
    text = text.replace('/* @REFERENCE@ */', '#if DT_NATIVE\n#define strcmp legacy_string_compare\n' + ref +
                        '\n#undef strcmp\n' + old_lookup + '\n' + old_parse + '\n#endif')
    text = text.replace('/* @ROOT@ */', b['regi_init'])
    require('@FUNCTIONS@' not in text, 'unfilled-placeholder')
    return text, new, old
