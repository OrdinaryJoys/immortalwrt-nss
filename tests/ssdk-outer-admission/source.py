"""Outer28 fixed-input text derivation and complete-function extraction."""
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
PATCH = '040-ssdk-guard-fal-hsl-lifecycle-before-mutation.patch'
PATCH_SHA = 'd172c18b316e315b685e4f500b88d8b8b48a159cb1a64b2a4c0134aec32f05ce'
BASE_SHA = '2f58e0d2203846be5f0de99a03515baa18df91d67ffac88bbb9d97f3b9635e2f'
CANDIDATE_SHA = '645358b757642d6db932defd9100a0448f7c3c602fd9e923e29f606c6f7680a8'
PLAN = REPO / 'tests/SSDK_FAL_HSL_ADMISSION_PLAN_2026-10-31.md'
PLAN_SHA = 'a003f9ee76396c49ca859f25ed0fb108937def333b87135d9c2ac744f9fd46df'
PHASE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261031/ssdk-outer-admission')
CONTRACTS = {PHASE/'TEST-ADMISSION-REVIEW-r1.json':'90e189f7c4aa2bb51111cc74faefaa287befef63bd6da2ba6066a32c6b01b22a',
             PHASE/'EPOCH-TEST-OBLIGATIONS-r1.json':'04e4443f091b893d227b27f75e6223c7cd293abee4dcf069b518d043c8dd79d7',
             PHASE/'SOURCE-COMPATIBILITY-REVIEW-r2.json':'6daacf2827b796141a3931da561df9c167ceaf50726b1ae325207aeca290eee9'}
CONTRACTS.update({PHASE/'PARENT-R4-SOURCE-DATA-BRIDGE-r1.json':'6df6ef18f4c1027817c9d3d08ef01fa92384cb5658ca27b88a5b0ef8a8aebdf2',
                  PHASE/'SOURCE-R4-DECLARED-UNUSED-REVIEW-r1.json':'f669f7b013248f2506876a9d92e239c4391d86536ad589e790252f03b4b849f4'})
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
HPPE = 'src/hsl/hppe/hppe_init.c'
CHANGED = ('include/hsl/hppe/hppe_init.h', HPPE, 'include/hsl/hsl_dev.h', 'src/hsl/hsl_dev.c',
           'src/hsl/hsl_api.c', 'src/fal/fal_init.c', 'include/fal/fal_vlan.h', 'src/fal/fal_vlan.c')


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
    return [REPO / 'tests/test-ssdk-outer-admission.py', *(SUPPORT / n for n in OWNED)]


def names():
    return sorted(p.name for p in (PACKAGE / 'patches').iterdir())


def recipe_gate(raw, expected, historical):
    if historical:
        require(raw.count(b'PKG_RELEASE:=18\n') == 1 and
                digest(raw.replace(b'PKG_RELEASE:=18\n', b'PKG_RELEASE:=17\n', 1)) == expected,
                'unique-whole-recipe18-to17')
    else:
        require(digest(raw) == expected, 'current28-strict-recipe')


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
    require(identity(PLAN)==PLAN_SHA,'fixed-plan')
    require(all(identity(p)==s for p,s in CONTRACTS.items()),'fixed-independent-contracts')
    sys.path.insert(0, str(REPO / 'tests'))
    from edma_patch_context import inspect_patch
    before, _ = receipt(base, BASE_SHA, 27, True)
    after, raw = receipt(candidate, CANDIDATE_SHA, 28, False)
    prior=candidate.parent/'OUTER-ADMISSION-CANDIDATE-20261031-r3'
    require(identity(prior/'RESULTS.json')=='069487510627a9125b6e5250d532b554338586bee72d64808e94a94f08c7d25f','r3-semantic-receipt')
    historical=json.loads((prior/'RESULTS.json').read_text());hsl='src/hsl/hsl_dev.c'
    old=(prior/'prepared'/hsl).read_bytes();current=(candidate/'prepared'/hsl).read_bytes()
    line=b'    (void)cfg; /* Used only by HPPE or combined-mode admission below. */\n'
    require(digest(old)==historical['prepared_files'][hsl] and current.count(line)==1 and
            current.replace(line,b'',1)==old,'exact-r3-to-r4-single-line-bridge')
    require({n:s for n,s in historical['prepared_files'].items() if n!=hsl}==
            {n:s for n,s in after['prepared_files'].items() if n!=hsl},'r3-r4-only-hsl-file-delta')
    require(after['patches'][:-1] == before['patches'] and names() == [p['name'] for p in after['patches']] and
            after['patches'][-1]['name'] == PATCH and after['patches'][-1]['sha256'] == PATCH_SHA, 'exact27-plus040')
    tree = output / 'fresh28'
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
    require(set(changed) == set(CHANGED) and ctx == after['patches'][-1]['declared_context'], 'only-eight-files')
    derived = dict(before['prepared_files'])
    derived.update({n: digest(v) for n, v in changed.items()})
    require(derived == after['prepared_files'], 'all692-28-equals27-plus040')
    bound = set(assets()) | {PLAN, REPO / 'tests/edma_patch_context.py'}
    bound.update(CONTRACTS)
    bound.update((prior/'RESULTS.json',prior/'prepared'/hsl))
    bound.update(Path(n) for n in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    data = {'pin': PIN, 'base': str(base), 'candidate': str(candidate), 'fresh': str(tree),
            'r3_r4_bridge':'EXACT_SINGLE_VOID_CFG_LINE_ONLY_ALL_OTHER691_MANIFEST_ENTRIES_EQUAL',
            'base_manifest': before['prepared_files'], 'candidate_manifest': after['prepared_files'],
            'patches': names(), 'fresh_contexts': contexts, '040_context': ctx,
            'recipe': {'historical17': before['inputs'][str(PACKAGE / 'Makefile')],
                       'current18': identity(PACKAGE / 'Makefile'), 'unique_whole_reverse18_to17': True},
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

HSL = ('hsl_dev_guard_id','hsl_dev_hppe_request','hsl_dev_dispatch_check','hsl_dev_init_available',
       'hsl_dev_api_init_check','hsl_dev_init_begin','hsl_dev_cleanup_begin','hsl_dev_api_init_guarded',
       'hsl_dev_guard_end','hsl_get_current_chip_type','hsl_set_current_chip_type','hsl_dev_ptr_get',
       'hsl_dev_inner_ports_get','hsl_dev_init_core','hsl_dev_init_guarded','hsl_dev_init',
       'hsl_dev_cleanup_core','hsl_dev_cleanup_guarded','hsl_dev_cleanup')
PUBLIC = ('hsl_dev_init','hsl_dev_cleanup','hsl_dev_init_begin','hsl_dev_cleanup_begin',
          'hsl_dev_api_init_check','hsl_dev_api_init_guarded','hsl_dev_init_guarded',
          'hsl_dev_cleanup_guarded','hsl_dev_guard_end')

BUILDERS = ('hsl_port_prop_slot_available', 'hsl_port_prop_build_alloc',
            'hsl_port_prop_build_portmap_set', 'hsl_port_prop_build_set',
            'hsl_port_prop_build_publish', 'hsl_port_prop_build_abort',
            'hsl_port_prop_cleanup_owned')

def extract(tree):
    records,bodies=[],{}
    def record(path,name,text,start):
        records.append({'path':path,'symbol':name,'start_line':start,'end_line':start+text.count('\n'),'sha256':digest(text.encode())})
        return text
    def match(path,name,pattern):
        t=(tree/path).read_text();ms=list(re.finditer(pattern,t,re.M));require(len(ms)==1,'one-declaration:'+name)
        m=ms[0];return record(path,name,m.group(),t[:m.start()].count('\n')+1)
    def decl(path,name,kind):return match(path,name,r'typedef\s+'+kind+r'(?:\s+\w+)?\s*\{[^}]*\}\s*'+name+r'\s*;')
    types=[]
    for bits in (8,16,32,64):
        name='a_uint%d_t'%bits
        types.append(match('include/sal/os/aos_types.h',name,r'^typedef\s+__'+name+r'\s+'+name+r';'))
    for path,name,kind in [('include/sal/os/aos_types.h','a_bool_t','enum'),('include/common/sw_error.h','sw_error_t','enum'),
                         ('include/init/ssdk_init.h','hsl_init_mode','enum'),('include/init/ssdk_init.h','ssdk_chip_type','enum'),('include/hsl/hsl_dev.h','hsl_dev_t','struct'),
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
    if (tree/'include/hsl/hsl_port_prop.h').read_text().find('hsl_port_prop_owner_t')>=0:
        symbols += [('src/hsl/hsl_port_prop.c',n) for n in BUILDERS]
        types.append(match('include/hsl/hsl_port_prop.h','opaque owner',r'typedef struct hsl_port_prop_info hsl_port_prop_owner_t;'))
    symbols += [('src/hsl/hsl_dev.c',n) for n in HSL]
    symbols += [('src/hsl/hsl_api.c',n) for n in ('hsl_api_ptr_get','hsl_api_init')]
    symbols += [('src/fal/fal_init.c',n) for n in ('fal_init','fal_cleanup')]
    symbols += [('src/fal/fal_vlan.c','fal_vlan_init_available'),('src/adpt/adpt.c','adpt_api_ptr_get')]
    symbols += [(HPPE,n) for n in ('hppe_init_state_check','hppe_init_owned','hppe_cleanup_owned')]
    for path,name in symbols:
        t=(tree/path).read_text();ms=list(re.finditer(r'^[ \t]*(?:(?:static|inline|int|void|sw_error_t|a_bool_t|a_uint32_t|ssdk_chip_type|adpt_api_t|hsl_dev_t|hsl_api_t)\s*\*?\s*)+'+name+r'\s*\([^;{]*\)\s*\{',t,re.M))
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
    if 'hsl_port_prop_build_alloc' in bodies:
        for name in ('hppe_port_owner','hppe_initializing','hppe_owner_epoch'):
            globals_.append(match(HPPE,name,r'^static [^\n]*\b'+name+r'\b[^\n]*'))
        declarations=[]
        for name in BUILDERS:
            declarations.append(match('include/hsl/hsl_port_prop.h','declaration:'+name,r'(?:sw_error_t|void)\s+'+name+r'\s*\([^;]*\);'))
    else:declarations=[]
    guard_types = match('include/hsl/hsl_dev.h','guard-opaque',r'typedef struct hsl_dev_lifecycle_guard hsl_dev_lifecycle_guard_t;')
    guard_types += '\n'+match('src/hsl/hsl_dev.c','hsl_dev_phase',r'enum hsl_dev_phase\s*\{[^}]*\};')
    guard_types += '\n'+match('src/hsl/hsl_dev.c','guard-private',r'struct hsl_dev_lifecycle_guard\s*\{[^}]*\};')
    for path,name,pattern in [
        ('src/hsl/hsl_dev.c','dev_ssdk_cfg',r'^static ssdk_init_cfg[^\n]*dev_ssdk_cfg[^\n]*'),
        ('src/hsl/hsl_dev.c','hsl_dev_guards',r'^static hsl_dev_lifecycle_guard_t[^\n]*hsl_dev_guards[^\n]*'),
        ('src/hsl/hsl_dev.c','SSDK_CURRENT_CHIP_TYPE',r'^ssdk_chip_type SSDK_CURRENT_CHIP_TYPE[^\n]*'),
        ('src/adpt/adpt.c','g_adpt_api',r'^adpt_api_t \*g_adpt_api[^\n]*'),
        *[('src/fal/fal_vlan.c',n,r'^static [^\n]*\b'+n+r'\b[^\n]*') for n in ('vlan_pool','vlan_db','vlan_list')]]:
        globals_.append(match(path,name,pattern))
    globals_.append('#ifdef HPPE\n'+match('src/hsl/hsl_dev.c','hsl_hppe_owned',r'^static a_bool_t[^\n]*hsl_hppe_owned[^\n]*')+'\n#endif')
    globals_.append('#ifdef HPPE\n'+match('src/hsl/hsl_dev.c','hsl_hppe_owner_epoch',r'^static a_uint64_t[^\n]*hsl_hppe_owner_epoch[^\n]*')+'\n#endif')
    for path,name in [('include/hsl/hsl_dev.h',n) for n in PUBLIC] + [
            *[('include/hsl/hppe/hppe_init.h',n) for n in ('hppe_init_state_check','hppe_init_owned','hppe_cleanup_owned')],('include/fal/fal_vlan.h','fal_vlan_init_available')]:
        declarations.append(match(path,'declaration:'+name,r'sw_error_t\s+'+name+r'\s*\([^;]*\);'))
    return {'guard_types':guard_types,'declarations':'\n'.join(declarations),'records':records,'types':'\n'.join(types),'macros':'\n'.join(macros),'globals':'\n'.join(globals_),'bodies':bodies}


def baseline_api(tree):
    text=(tree/'src/hsl/hsl_api.c').read_text()
    match=re.search(r'sw_error_t\s+hsl_api_init\([^;{]*\)\s*\{',text)
    require(match is not None,'baseline-api-body')
    start=match.start();end=text.index('{',start)+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


ALIASES={'hppe_init':'actual_hppe_init','hppe_cleanup':'actual_hppe_cleanup',
         'hsl_dev_init_core':'actual_hsl_core'}


def rendered_body(name,text):
    if name in ALIASES:return re.sub(r'\b'+name+r'\b',ALIASES[name],text,count=1)
    return text


def render(extracted,old_api,template):
    b=extracted['bodies'];parts=[]
    for n in ('hsl_dev_ptr_get','hsl_api_ptr_get','adpt_api_ptr_get','hsl_get_current_chip_type',
              'hsl_set_current_chip_type','hsl_dev_inner_ports_get',
              'hsl_port_validity_check','hsl_port_prop_set','hsl_port_prop_portmap_set',
              'hsl_port_prop_init','hsl_port_prop_init_by_dev','hsl_port_prop_cleanup_by_dev',*BUILDERS):
        parts.append(b[n])
    parts.append('#ifdef HPPE\n'+'\n\n'.join(rendered_body(n,b[n]) for n in
        ('hppe_dev_init','hppe_portproperty_init','hppe_cleanup','hppe_init','hppe_init_state_check','hppe_init_owned','hppe_cleanup_owned'))+'\n#endif')
    for n in HSL:
        if n in ('hsl_dev_ptr_get','hsl_get_current_chip_type','hsl_set_current_chip_type','hsl_dev_inner_ports_get'):continue
        raw=rendered_body(n,b[n])
        if n=='hsl_dev_hppe_request':raw='#if defined(HPPE) || (defined(KERNEL_MODULE) && defined(USER_MODE))\n'+raw+'\n#endif'
        parts.append(raw)
    parts += [b['hsl_api_init'],b['fal_vlan_init_available'],b['fal_init'],b['fal_cleanup'],
              re.sub(r'\bhsl_api_init\b','old_hsl_api_init',old_api,count=1)]
    for key,val in {'TYPES':extracted['types'],'MACROS':extracted['macros'],'GUARD_TYPES':extracted['guard_types'],
                    'GLOBALS':extracted['globals'],'DECLARATIONS':extracted['declarations'],
                    'BODIES':'\n\n'.join(parts)}.items():template=template.replace('/* @'+key+'@ */',val)
    require(not re.search(r'@[A-Z_]+@',template),'unfilled-template')
    return template
