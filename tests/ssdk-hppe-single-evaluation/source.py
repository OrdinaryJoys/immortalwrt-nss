"""HPPE26 fixed-input text derivation and complete-function extraction."""
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
PATCH = '038-ssdk-evaluate-hppe-fallible-calls-once.patch'
PATCH_SHA = '80c3faded9b81cd422a47a237d2927e243938d5240058aa47cf2c343d696ead4'
PLAN = REPO / 'tests/SSDK_HPPE_SINGLE_EVALUATION_PLAN_2026-10-31.md'
PLAN_SHA = 'de64960880e8a90533718464a33e942742facdd4951b4dd53459549ca30cb372'
BASE_SHA = 'c3956ae5392752b59504f3bdeef1a2e2af07eaf5b51858c59b459a005690fe88'
CANDIDATE_SHA = '9f47f173e049f37542836b45d50f1642a4e5fa7812553958ccb24950f63b4687'
IDENTITY = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-hppe-single-eval/SOURCE-IDENTITY-r1.json')
IDENTITY_SHA = '7405dbc82c102347482b89c95f66cd8e8693ccf8146f0bafbc25ee998845a622'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
HPPE = 'src/hsl/hppe/hppe_init.c'


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
    return [REPO / 'tests/test-ssdk-hppe-single-evaluation.py', *(SUPPORT / n for n in OWNED)]


def names():
    return sorted(p.name for p in (PACKAGE / 'patches').iterdir())


def recipe_gate(raw, expected, historical):
    if historical:
        require(raw.count(b'PKG_RELEASE:=16\n') == 1 and
                digest(raw.replace(b'PKG_RELEASE:=16\n', b'PKG_RELEASE:=15\n', 1)) == expected,
                'unique-whole-recipe16-to15')
    else:
        require(digest(raw) == expected, 'current26-strict-recipe')


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
    before, _ = receipt(base, BASE_SHA, 25, True)
    after, raw = receipt(candidate, CANDIDATE_SHA, 26, False)
    require(after['patches'][:-1] == before['patches'] and names() == [p['name'] for p in after['patches']] and
            after['patches'][-1]['name'] == PATCH and after['patches'][-1]['sha256'] == PATCH_SHA, 'exact25-plus038')
    tree = output / 'fresh26'
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
    require(set(changed) == {HPPE} and ctx == after['patches'][-1]['declared_context'], 'only-hppe-init')
    derived = dict(before['prepared_files'])
    derived.update({n: digest(v) for n, v in changed.items()})
    require(derived == after['prepared_files'], 'all692-26-equals25-plus038')
    bound = set(assets()) | {PLAN, IDENTITY, REPO / 'tests/edma_patch_context.py'}
    bound.update(Path(n) for n in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    data = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
            'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
            'patches': names(), 'fresh_contexts': contexts, '038_context': ctx,
            'recipe': {'historical15': before['inputs'][str(PACKAGE / 'Makefile')],
                       'current16': identity(PACKAGE / 'Makefile'), 'unique_whole_reverse16_to15': True},
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
    records,bodies=[],{}
    def record(path,name,text,start):
        records.append({'path':path,'symbol':name,'start_line':start,'end_line':start+text.count('\n'),'sha256':digest(text.encode())})
        return text
    def match(path,name,pattern):
        t=(tree/path).read_text();ms=list(re.finditer(pattern,t,re.M));require(len(ms)==1,'one-declaration:'+name)
        m=ms[0];return record(path,name,m.group(),t[:m.start()].count('\n')+1)
    def decl(path,name,kind):return match(path,name,r'typedef\s+'+kind+r'\s*\{[^}]*\}\s*'+name+r'\s*;')
    types=[]
    for bits in (8,16,32,64):
        name='a_uint%d_t'%bits
        types.append(match('include/sal/os/aos_types.h',name,r'^typedef\s+__'+name+r'\s+'+name+r';'))
    for path,name,kind in [('include/sal/os/aos_types.h','a_bool_t','enum'),('include/common/sw_error.h','sw_error_t','enum'),
                         ('include/init/ssdk_init.h','hsl_init_mode','enum'),('include/hsl/hsl_dev.h','hsl_dev_t','struct'),
                         ('include/hsl/hsl_port_prop.h','hsl_port_prop_t','enum'),('include/init/ssdk_init.h','ssdk_port_cfg','struct')]:
        types.append(decl(path,name,kind))
    for name in ('SW_MAX_NR_DEV','SW_MAX_NR_PORT'):
        types.append(match('include/common/sw_config.h',name,r'^#define\s+'+name+r'\s+[^\n]*'))
    types.append(match('include/fal/fal_type.h','fal_pbmp_t conditional',r'^#if \(SW_MAX_NR_PORT <= 32\)[\s\S]*?^#endif'))
    types.append(match('include/fal/fal_type.h','fal_port_t',r'typedef\s+a_uint32_t\s+fal_port_t;'))
    types.append(decl('src/hsl/hsl_port_prop.c','port_info_t','struct'))
    macros=[]
    for path,name in [('include/common/shared_func.h','SW_RTN_ON_ERROR'),('include/common/shared_func.h','SW_RTN_ON_NULL'),
                      ('include/hsl/hsl_dev.h','HSL_DEV_ID_CHECK'),('include/common/shared_func.h','SW_IS_PBMP_MEMBER'),
                      ('include/common/shared_func.h','SW_PBMP_ADD_PORT')]:
        macros.append(match(path,name,r'^#define '+name+r'\([^\n]*\)[^\n]*\n(?:[^\n]*\\\n)*[^\n]*' if name in ('SW_RTN_ON_ERROR','SW_RTN_ON_NULL','HSL_DEV_ID_CHECK') else r'^#define '+name+r'\([^\n]*'))
    symbols=[(HPPE,n) for n in ('hppe_init','hppe_cleanup','hppe_portproperty_init','hppe_dev_init')]
    symbols += [('src/hsl/hsl_port_prop.c',n) for n in ('hsl_port_validity_check','hsl_port_prop_set','hsl_port_prop_portmap_set',
                'hsl_port_prop_init','hsl_port_prop_init_by_dev','hsl_port_prop_cleanup_by_dev')]
    symbols += [('src/hsl/hsl_dev.c','hsl_dev_ptr_get'),('src/hsl/hsl_api.c','hsl_api_ptr_get')]
    for path,name in symbols:
        t=(tree/path).read_text();ms=list(re.finditer(r'^[ \t]*(?:(?:static|sw_error_t|a_bool_t|hsl_dev_t|hsl_api_t)\s*\*?\s*)+'+name+r'\s*\([^;{]*\)\s*\{',t,re.M))
        require(len(ms)==1,'one-complete-body:'+name);m=ms[0]
        masked=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda x:' '*len(x.group()),t)
        end,depth=t.index('{',m.start())+1,1
        while depth:depth+=(masked[end]=='{')-(masked[end]=='}');end+=1
        bodies[name]=record(path,name,t[m.start():end],t[:m.start()].count('\n')+1)
    globals_=[]
    for path,name,pattern in [(HPPE,'hppe_cfg',r'^static ssdk_init_cfg[^\n]*hppe_cfg[^\n]*'),
                ('src/hsl/hsl_port_prop.c','p_port_info',r'^static port_info_t[^\n]*p_port_info[^\n]*'),
                ('src/hsl/hsl_dev.c','dev_table',r'^static hsl_dev_t[^\n]*dev_table[^\n]*'),
                ('src/hsl/hsl_api.c','hsl_api_table',r'^static hsl_api_t[^\n]*hsl_api_table[^\n]*')]:
        globals_.append(match(path,name,pattern))
    return {'records':records,'types':'\n'.join(types),'macros':'\n'.join(macros),'globals':'\n'.join(globals_),'bodies':bodies}


def render(tree,base,template):
    new,old=extract(tree),extract(base);b=new['bodies']
    require(new['types']==old['types'] and new['macros']==old['macros'] and new['globals']==old['globals'],'shared-types-macros-globals-unchanged')
    require(all(b[n]==old['bodies'][n] for n in b if n not in ('hppe_init','hppe_cleanup','hppe_portproperty_init')),'only-three-hppe-bodies-change')
    renamed={'hsl_port_prop_set':'real_set','hsl_port_prop_portmap_set':'real_map','hsl_port_prop_init':'real_reset',
             'hsl_port_prop_init_by_dev':'real_palloc','hsl_port_prop_cleanup_by_dev':'real_clean',
             'hppe_dev_init':'real_dev','hppe_portproperty_init':'real_prop'}
    parts=[]
    for n in ('hsl_dev_ptr_get','hsl_api_ptr_get','hsl_port_validity_check','hsl_port_prop_set','hsl_port_prop_portmap_set',
              'hsl_port_prop_init','hsl_port_prop_init_by_dev','hsl_port_prop_cleanup_by_dev','hppe_dev_init','hppe_portproperty_init'):
        raw=b[n]
        if n in renamed:raw=re.sub(r'\b'+n+r'\b',renamed[n],raw,count=1)
        parts.append(raw)
    old_prop=re.sub(r'\bhppe_portproperty_init\b','real_old_prop',old['bodies']['hppe_portproperty_init'],count=1)
    parts.append(old_prop)
    final=[b['hppe_cleanup'],b['hppe_init']]
    for n in ('hppe_cleanup','hppe_init'):
        raw=old['bodies'][n]
        raw=re.sub(r'\bhppe_cleanup\b','old_hppe_cleanup',raw)
        raw=re.sub(r'\bhppe_init\b','old_hppe_init',raw)
        final.append(raw)
    text=template.replace('/* @TYPES@ */',new['types']).replace('/* @MACROS@ */',new['macros']).replace('/* @GLOBALS@ */',new['globals'])
    text=text.replace('/* @HELPERS@ */','\n\n'.join(parts)).replace('/* @ENTRY@ */','\n\n'.join(final))
    require(not re.search(r'@[A-Z_]+@',text),'unfilled-template')
    return text,new,old
