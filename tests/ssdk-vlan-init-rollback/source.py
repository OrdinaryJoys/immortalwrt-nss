"""VLAN25 fixed-input text derivation and complete-function extraction."""
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
PATCH = '037-ssdk-construct-vlan-cache-before-publication.patch'
PATCH_SHA = '46702234a63d9e28aedcdc14309756aac0c2a6816203b479170f7f94154d5ad9'
PLAN = REPO / 'tests/SSDK_VLAN_INIT_ROLLBACK_PLAN_2026-10-31.md'
PLAN_SHA = '2a8ffcc4c67dd564ed7aebb039643dbe41952912498c2d49dec7715f860d9a5d'
BASE_SHA = '8714f974183d4e68424d93f70fc0f85e61512cb770b033745c63ec5f402fadcd'
CANDIDATE_SHA = 'c3956ae5392752b59504f3bdeef1a2e2af07eaf5b51858c59b459a005690fe88'
IDENTITY = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-vlan-init-rollback/SOURCE-IDENTITY-r1.json')
IDENTITY_SHA = '938857c48f404f6731d3678a0a11f4e55d3b6f24e0e2be16f17458c549a4c5b1'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
VLAN = 'src/fal/fal_vlan.c'


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
    return [REPO / 'tests/test-ssdk-vlan-init-rollback.py', *(SUPPORT / n for n in OWNED)]


def names():
    return sorted(p.name for p in (PACKAGE / 'patches').iterdir())


def recipe_gate(raw, expected, historical):
    if historical:
        require(raw.count(b'PKG_RELEASE:=15\n') == 1 and
                digest(raw.replace(b'PKG_RELEASE:=15\n', b'PKG_RELEASE:=14\n', 1)) == expected,
                'unique-whole-recipe15-to14')
    else:
        require(digest(raw) == expected, 'current25-strict-recipe')


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
        require(p['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and p['returncode'] == 0, 'patch-status')
        for n, ctx in p['declared_context'].items():
            require(derived[n] == ctx['before_sha256'] and ctx['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in ctx['hunks']), 'context-chain')
            derived[n] = ctx['after_sha256']
    require(len(derived) == 692 and derived == data['prepared_files'] == inventory(root / 'prepared'), 'all692')
    for n, sha in data['inputs'].items():
        if Path(n) == PACKAGE / 'Makefile':
            recipe_gate(Path(n).read_bytes(), sha, historical)
        else:
            require(identity(n) == sha, 'strict-input:' + n)
    return data, raw


def prepare(base, candidate, output):
    require(identity(PLAN) == PLAN_SHA and identity(IDENTITY) == IDENTITY_SHA, 'fixed-plan-identity')
    sys.path.insert(0, str(REPO / 'tests'))
    from edma_patch_context import inspect_patch
    before, _ = receipt(base, BASE_SHA, 24, True)
    after, raw = receipt(candidate, CANDIDATE_SHA, 25, False)
    require(after['patches'][:-1] == before['patches'] and names() == [p['name'] for p in after['patches']] and
            after['patches'][-1]['name'] == PATCH and after['patches'][-1]['sha256'] == PATCH_SHA, 'exact24-plus037')
    tree = output / 'fresh25'
    tree.mkdir()
    contexts = []
    for n, content in raw.items():
        p = tree / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    for p in after['patches']:
        changed, ctx = inspect_patch(tree, (PACKAGE / 'patches' / p['name']).read_bytes())
        require(ctx == p['declared_context'], 'fresh-exact-context')
        for n, content in changed.items():
            (tree / n).write_bytes(content)
        contexts.append({'name': p['name'], 'context': ctx})
    require(inventory(tree) == after['prepared_files'], 'fresh692')
    changed, ctx = inspect_patch(base / 'prepared', (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(changed) == {VLAN} and ctx == after['patches'][-1]['declared_context'], 'only-fal-vlan')
    derived = dict(before['prepared_files'])
    derived.update({n: digest(v) for n, v in changed.items()})
    require(derived == after['prepared_files'], 'all692-25-equals24-plus037')
    bound = set(assets()) | {PLAN, IDENTITY, REPO / 'tests/edma_patch_context.py'}
    bound.update(Path(n) for n in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    data = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
            'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
            'patches': names(), 'fresh_contexts': contexts, '037_context': ctx,
            'recipe': {'historical14': before['inputs'][str(PACKAGE / 'Makefile')],
                       'current15': identity(PACKAGE / 'Makefile'), 'unique_whole_reverse15_to14': True},
            'saved_members': {str(r): [p['name'] for p in d['patches']] for r, d in [(base, before), (candidate, after)]},
            'inputs': {str(p): identity(p) for p in sorted(bound)},
            'scope': 'Fresh text preparation using current hash-bound repo pure inspect_patch. No saved program or target build.'}
    return tree, data


def stable(inputs):
    assets()
    require(names() == inputs['patches'], 'end-current-patches')
    for n, sha in inputs['inputs'].items():
        require(identity(n) == sha, 'end-input:' + n)
    for root, members in inputs['saved_members'].items():
        require(sorted(p.name for p in (Path(root) / 'patches').iterdir()) == members, 'end-saved-members')
    for key in ('base', 'candidate'):
        require(inventory(Path(inputs[key]) / 'prepared') == inputs[key + '_manifest'], 'end-tree:' + key)
    require(inventory(Path(inputs['fresh'])) == inputs['candidate_manifest'], 'end-fresh692')
    return 'ALL_FIXED_INPUTS_ASSETS_EXACT_INVENTORIES_FULL692_STABLE_NOT_ATOMIC_LOCK'


def extract(tree):
    records, bodies = [], {}

    def record(path, name, text, start):
        records.append({'path': path, 'symbol': name, 'start_line': start,
                        'end_line': start + text.count('\n'), 'sha256': digest(text.encode())})
        return text

    def match(path, name, pattern):
        t = (tree / path).read_text()
        ms = list(re.finditer(pattern, t, re.M))
        require(len(ms) == 1, 'one-declaration:' + name)
        m = ms[0]
        return record(path, name, m.group(), t[:m.start()].count('\n') + 1)

    def declaration(path, name, kind):
        return match(path, name, r'typedef\s+' + kind + r'(?:\s+_\w+)?\s*\{[^}]*\}\s*' + name + r'\s*;')

    types = []
    for bits in (8, 16, 32, 64):
        name = 'a_uint%d_t' % bits
        types.append(match('include/sal/os/aos_types.h', name, r'^typedef\s+__' + name + r'\s+' + name + r';'))
    types.append(match('include/sal/os/linux/aos_types_pvt.h', '__aos_size_t', r'^typedef\s+int\s+__aos_size_t;'))
    types.append(match('include/sal/os/aos_types.h', 'aos_size_t', r'typedef\s+__aos_size_t\s+aos_size_t;'))
    for path, name, kind in [('include/sal/os/aos_types.h', 'a_bool_t', 'enum'),
                             ('include/common/sw_error.h', 'sw_error_t', 'enum'),
                             ('include/init/ssdk_init.h', 'hsl_init_mode', 'enum'),
                             ('include/hsl/hsl_dev.h', 'hsl_dev_t', 'struct')]:
        types.append(declaration(path, name, kind))
    for name in ('SW_MAX_NR_DEV', 'SW_MAX_NR_PORT'):
        types.append(match('include/common/sw_config.h', name, r'^#define\s+' + name + r'\s+[^\n]*'))
    types.append(match('include/fal/fal_type.h', 'fal_pbmp_t conditional',
                       r'^#if \(SW_MAX_NR_PORT <= 32\)[\s\S]*?^#endif'))
    types.append(declaration('include/fal/fal_vlan.h', 'fal_vlan_t', 'struct'))
    types.append(declaration(VLAN, 'v_array_t', 'struct'))
    for name in ('LL_IN_ORDER', 'LL_FIX_NDNR'):
        types.append(match('include/common/util.h', name, r'^#define\s+' + name + r'\s+[^\n]*'))
    types.append(declaration('include/common/util.h', 'll_cmp_rslt_t', 'enum'))
    for name in ('ll_nd_cmp', 'll_nd_dump'):
        types.append(match('include/common/util.h', name, r'typedef\s+[^;{}]*\(\s*\*\s*' + name + r'\s*\)[^;{}]*;'))
    for name in ('sll_node_t', 'sll_head_t', 'sid_pool_t'):
        types.append(declaration('include/common/util.h', name, 'struct'))
    types.append(match('src/util/util.c', 'pool width constants', r'^#define ID_SIZE_U8[\s\S]*?^#define ID_NR_IN_U16[^\n]*'))
    for name in ('fal_vlan_init','fal_vlan_cleanup'):
        types.append(match('include/fal/fal_vlan.h', name+' prototype', r'sw_error_t\s+'+name+r'\s*\([^;]*\);'))
    macro = match('include/common/shared_func.h', 'SW_RTN_ON_NULL', r'^#define SW_RTN_ON_NULL[^\n]*\n(?:[^\n]*\\\n)*[^\n]*')
    globals_ = match(VLAN, 'three software cache arrays', r'^static v_array_t[^\n]*\nstatic sid_pool_t[^\n]*\nstatic sll_head_t[^\n]*')
    symbols = [('src/util/util.c', n) for n in ('sid_pool_creat','sid_pool_destroy','sll_creat','sll_destroy')]
    symbols += [('src/hsl/hsl_dev.c', 'hsl_dev_ptr_get')]
    symbols += [(VLAN, n) for n in ('_fal_vlan_entry_cmp','_fal_vlan_entry_dump','fal_vlan_init','fal_vlan_cleanup')]
    symbols += [('include/sal/os/linux/aos_mem_pvt.h', n) for n in ('__aos_mem_alloc','__aos_mem_free','__aos_mem_zero')]
    symbols += [('include/sal/os/aos_mem.h', n) for n in ('aos_mem_alloc','aos_mem_free','aos_mem_zero')]
    for path, name in symbols:
        t = (tree / path).read_text()
        ms = list(re.finditer(r'^[ \t]*(?:(?:static|inline|void|sw_error_t|ll_cmp_rslt_t|sid_pool_t|sll_head_t|hsl_dev_t)\s*\*?\s*)+' +
                              name + r'\s*\([^;{]*\)\s*\{', t, re.M))
        require(len(ms) == 1, 'one-complete-body:' + name)
        m = ms[0]
        masked = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', lambda x: ' '*len(x.group()), t)
        end, depth = t.index('{', m.start()) + 1, 1
        while depth:
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        bodies[name] = record(path, name, t[m.start():end], t[:m.start()].count('\n') + 1)
    return {'records': records, 'types': '\n'.join(types), 'macro': macro, 'globals': globals_, 'bodies': bodies}


def render(current, base, template):
    new, old = extract(current), extract(base)
    require(new['types'] == old['types'] and new['globals'] == old['globals'] and
            all(new['bodies'][n] == old['bodies'][n] for n in new['bodies'] if n != 'fal_vlan_init'),
            'only-init-body-changes')
    order = ['sid_pool_creat','sid_pool_destroy','sll_creat','sll_destroy','hsl_dev_ptr_get',
             '_fal_vlan_entry_cmp','_fal_vlan_entry_dump','fal_vlan_init','fal_vlan_cleanup']
    text = template.replace('/* @TYPES@ */', new['types']).replace('/* @MACRO@ */', new['macro'])
    text = text.replace('/* @GLOBALS@ */', new['globals']).replace('/* @BODIES@ */', '\n\n'.join(new['bodies'][n] for n in order))
    os_bodies = [new['bodies']['__aos_mem_alloc'], new['bodies']['__aos_mem_free'],
                 '#pragma push_macro("memset")\n#undef memset\n#define memset tracked_memset\n' +
                 new['bodies']['__aos_mem_zero'] + '\n#undef memset\n#pragma pop_macro("memset")']
    os_bodies += [new['bodies'][n] for n in ('aos_mem_alloc','aos_mem_free','aos_mem_zero')]
    text = text.replace('/* @OS@ */', '\n\n'.join(os_bodies))
    old_init = re.sub(r'\bfal_vlan_init\b', 'old_vlan_init', old['bodies']['fal_vlan_init'])
    text = text.replace('/* @OLD@ */', old_init)
    require(not re.search(r'@[A-Z_]+@', text), 'unfilled-template')
    return text, new, old
