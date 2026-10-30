"""Bound complete DP/SSDK definitions; no kernel/module build or source mutation."""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import shutil


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mask(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def function(text, name, occurrence=None):
    clean = mask(text)
    if name == 'nss_dp_port_attr_set':
        headers = list(re.finditer(r'(?m)^static int nss_dp_port_attr_set\(', clean))
        require(len(headers) == 2, 'versioned signature cardinality')
        start = text.rfind('#if (LINUX_VERSION_CODE < KERNEL_VERSION(6, 1, 0))', 0, headers[0].start())
        require(start >= 0, 'versioned signature guard')
        end = clean.index('{', headers[-1].end()) + 1
        depth = 1
        while depth and end < len(clean):
            depth += (clean[end] == '{') - (clean[end] == '}')
            end += 1
        require(depth == 0, 'versioned body closure')
        return text[start:end], text.count('\n', 0, start) + 1
    pattern = (r'(?m)^(?:static\s+)?(?:inline\s+)?(?:struct\s+\w+|enum\s+\w+|\w+)\s+\**\s*'
               r'(?:(?:__init|__exit)\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    hits = list(re.finditer(pattern, clean))
    require(bool(hits) and (occurrence is not None or len(hits) == 1),
            'definition cardinality: ' + name)
    hit = hits[occurrence or 0]
    end, depth = hit.end(), 1
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    require(depth == 0, 'unclosed definition: ' + name)
    return text[hit.start():end], text.count('\n', 0, hit.start()) + 1


def typedef(text, name):
    ends = list(re.finditer(r'}\s*' + re.escape(name) + r'\s*;', mask(text)))
    require(len(ends) == 1, 'typedef cardinality: ' + name)
    end = ends[0]
    start = max(text.rfind('typedef struct', 0, end.start()),
                text.rfind('typedef enum', 0, end.start()))
    require(start >= 0, 'typedef start: ' + name)
    return text[start:end.end()]


def once(text, old, new):
    require(text.count(old) == 1, 'single mutation anchor: ' + old[:100])
    return text.replace(old, new, 1)


def tree_hashes(root):
    require(not any(p.is_symlink() for p in root.rglob('*')), 'source tree symlink')
    return {str(p.relative_to(root)): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def receipt_chain(repo, audit, dp_base, ssdk_tree):
    """Rebind existing exact receipts, not rerun their preparation programs."""
    receipts = {
        audit/'DP-PHY-parent-r3/INPUTS.json': '97cddf7455026990e968c000b7ad108c169f6383a371f3991e4c07542c25fce3',
        audit/'DP-PHY-parent-r3/RESULTS.json': 'd5fc7ef958b61009805c384c501bdea01f74c96978e71044b264158bd30134d8',
        audit/'DP-PHY-parent-r3/PREPARED.json': '1ae6589b7b5bf8169e763afe18dcc471c9056207a50cfd3edd88db233ba9a563',
        ssdk_tree.parent/'RESULTS.json': '9fb53f4305239628d1da5941011fef85bcf621641ecb38012e3cbe053900a36b',
    }
    for p, h in receipts.items():
        require(sha(p.read_bytes()) == h, 'accurate receipt identity: ' + str(p))
    dp = json.loads((audit/'DP-PHY-parent-r3/INPUTS.json').read_text())
    dp_result = json.loads((audit/'DP-PHY-parent-r3/RESULTS.json').read_text())
    prepared = json.loads((audit/'DP-PHY-parent-r3/PREPARED.json').read_text())
    ssdk = json.loads((ssdk_tree.parent/'RESULTS.json').read_text())
    used, recipe_metadata = list(receipts), {}

    def archive_manifest(path, wanted):
        require(sha(path.read_bytes()) == wanted, 'receipt archive hash')
        used.append(path)
        files = {}
        with tarfile.open(path) as tar:
            for member in tar.getmembers():
                require(member.isdir() or member.isfile(), 'archive special member')
                rel = Path(member.name)
                require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe archive member')
                if member.isfile():
                    require(member.name not in files, 'archive duplicate file')
                    files[member.name] = sha(tar.extractfile(member).read())
        return files

    def update(derived, changes):
        for rel, change in changes.items():
            require(derived.get(rel) == change['before_sha256'], 'receipt preimage chain: '+rel)
            require(all(h['offset']==0 and h['full_context'] for h in change['hunks']),
                    'receipt nonexact hunk')
            derived[rel] = change['after_sha256']

    def live(path, wanted):
        require(path.is_file(), 'missing receipt input')
        data=path.read_bytes()
        if path in {repo/'package/qca-nss/qca-nss-dp/Makefile',repo/'package/qca-nss/qca-ssdk/Makefile'}:
            recipe_metadata[str(path)]=recipe_binding(data,wanted)
        else:
            require(sha(data) == wanted, 'receipt/live input mismatch: '+str(path))
        used.append(path)

    for package, pin in [('qca-nss-dp', 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'),
                         ('qca-ssdk', 'd9a196497ecee2530722d906e0efe1b7408b6ef6')]:
        recipe = repo/'package/qca-nss'/package/'Makefile'
        require(re.search(r'^PKG_SOURCE_VERSION:=' + pin + r'\s*$', recipe.read_text(), re.M), 'actual recipe pin')
    require(dp['pin']=='d8f802f08fd8ff31057ba58edb20bbe448e7b505' and
            ssdk['pin']=='d9a196497ecee2530722d906e0efe1b7408b6ef6', 'receipt pins')
    d = archive_manifest(audit/'DP-PHY-parent-r3/upstream.tar', dp['git_archive_sha256'])
    require(d == dp['raw_files'], 'DP archive/raw receipt')
    require(len(dp['patches']) == 16, 'DP receipt first16')
    for row in dp['patches']:
        live(Path(row['path']), row['sha256']);live(Path(row['saved']), row['sha256'])
        update(d, row['declared_context']['after'])
    require(d == dp['prepared_files']['after'], 'DP16 derived whole tree')
    patch17 = repo/'package/qca-nss/qca-nss-dp/patches/017-ipq807x-unregister-before-phy-retirement.patch'
    live(patch17, dp_result['inputs'][str(patch17)])
    live(audit/'DP-PHY-parent-r3/patches'/patch17.name, dp_result['inputs'][str(patch17)])
    update(d, dp_result['017_context'])
    require(d == prepared[str(dp_base)] == tree_hashes(dp_base), 'DP17 derived whole tree')
    for rel in ['package/qca-nss/qca-nss-dp/Makefile', 'tests/edma_patch_context.py',
                'tests/test-edma-phase2-integration.py', 'tests/test-edma-tx-slot-ownership.py']:
        p = repo/rel;live(p, dp_result['inputs'][str(p)])
    s = archive_manifest(ssdk_tree.parent/'upstream.tar', ssdk['archive_sha256'])
    require(s == ssdk['upstream_files'] and len(ssdk['patches'])==18, 'SSDK raw/18 receipt')
    require([p.name for p in sorted((repo/'package/qca-nss/qca-ssdk/patches').glob('*.patch'))] ==
            [r['name'] for r in ssdk['patches']], 'SSDK receipt/live complete inventory')
    for p, wanted in ssdk['inputs'].items(): live(Path(p), wanted)
    for row in ssdk['patches']:
        live(ssdk_tree.parent/'patches'/row['name'], row['sha256'])
        update(s, row['declared_context'])
    require(s == ssdk['prepared_files'] == tree_hashes(ssdk_tree), 'SSDK18 derived whole tree')
    return d, s, list(dict.fromkeys(used)), recipe_metadata


def recipe_binding(data, baseline):
    allowed={'0ef994b56fc408a44a9a4501b594d413a806ab9d2a24055eccfe3d035cad0af5',
             'c861915851567a3738b1d1edfc1af035fc94c380f735d8d3b8711b010ed30455'}
    require(baseline in allowed,'recipe baseline not explicitly allowed')
    actual=sha(data)
    if actual==baseline:
        require(data.count(b'PKG_RELEASE:=8\n')==1,'baseline recipe release8')
        release=8
    else:
        require(data.count(b'PKG_RELEASE:=9\n')==1 and data.count(b'PKG_RELEASE:=8\n')==0,
                'recipe delta must be single8-to9 release line')
        require(sha(data.replace(b'PKG_RELEASE:=9\n',b'PKG_RELEASE:=8\n',1))==baseline,
                'recipe bytes outside allowed release delta')
        release=9
    return {'baseline_sha256':baseline,'actual_sha256':actual,
            'baseline_release':8,'actual_release':release,
            'release_delta':None if release==8 else {'from':8,'to':9},
            'qualification':'This run only; never upgrades historical8 results or permits in-run drift'}


DP_NAMES = ['nss_dp_of_get_pdata', 'nss_dp_clear_host_ctx', 'nss_dp_abort_host_probe',
            'nss_dp_is_phy_dev', 'nss_dp_phy_disconnect', 'nss_dp_probe', 'nss_dp_remove',
            'nss_dp_release_stages', 'nss_dp_init', 'nss_dp_exit']
S_NAMES = ['nss_dp_is_bridge_port', 'nss_dp_netdev_event', 'nss_dp_set_slow_proto_filter',
           'nss_dp_stp_state_set', 'nss_dp_port_attr_set',
           'nss_dp_switchdev_port_attr_set_event', 'nss_dp_switchdev_event',
           'nss_dp_switchdev_fdb_del_event', 'nss_dp_switchdev_fdb_del_children',
           'nss_dp_switchdev_event_nb', 'nss_dp_bridge_attr_set',
           'nss_dp_switchdev_exit', 'nss_dp_switchdev_init']
SSDK_GROUPS = {
    'src/init/ssdk_plat.c': ['ssdk_netdev_to_portid', 'ssdk_netdev_cache_ready', 'ssdk_netdev_cache_mark_native_port',
        'ssdk_netdev_cache_start', 'ssdk_netdev_cache_commit', 'ssdk_netdev_cache_remove',
        'ssdk_netdev_cache_stop', 'ssdk_netdev_cache_unregister', 'ssdk_netdev_cache_rename',
        'ssdk_netdev_cache_name', 'ssdk_netdev_switch_init'],
    'src/init/ssdk_init.c': ['ssdk_ifname_to_port', 'ssdk_port_to_ifname_copy',
        'ssdk_nss_dp_netdev_check', 'ssdk_netdev_switch_init_required', 'ssdk_dev_event',
        'ssdk_netdev_notifier_register', 'ssdk_netdev_notifier_unregister'],
    'src/init/ssdk_dts.c': ['ssdk_dts_netdev_switch_find', 'ssdk_dts_netdev_switch_get'],
    'src/hsl/hsl_dev.c': ['hsl_dev_ptr_get', 'hsl_get_current_chip_type'],
    'src/hsl/hsl_port_prop.c': ['hsl_port_prop_check'],
    'src/hsl/phy/hsl_phy.c': ['hsl_phy_info_get', 'qca_ssdk_port_bmp_get',
                            'qca_ssdk_phy_addr_to_port', 'qca_ssdk_phydev_to_port'],
    'src/adpt/adpt.c': ['adpt_ppe_type_get'],
}


def extract(dp, ssdk, out):
    out.mkdir()
    records, bodies = [], {}

    def add(root, rel, name, occurrence=None):
        body, line = function((root / rel).read_text(), name, occurrence)
        require(name not in bodies, 'duplicate extracted name')
        bodies[name] = body
        records.append({'root': str(root), 'path': rel, 'function': name,
                        'line': line, 'sha256': sha(body.encode()),
                        'complete_definition': True, 'branch_occurrence': occurrence})
        (out / (name + '.c.txt')).write_text(body + '\n')

    for name in DP_NAMES:
        add(dp, 'nss_dp_main.c', name)
    for name in S_NAMES:
        add(dp, 'nss_dp_switchdev.c', name,
            -1 if name in {'nss_dp_bridge_attr_set', 'nss_dp_switchdev_event_nb'} else None)
    for rel, names in SSDK_GROUPS.items():
        for name in names:
            add(ssdk, rel, name)
    types = []
    for rel, names in {
        'include/init/ssdk_init.h': ['ssdk_chip_type', 'ssdk_port_cfg'],
        'include/hsl/hsl_dev.h': ['hsl_dev_t'],
        'include/adpt/adpt.h': ['adpt_chip_ver_t', 'adpt_ppe_type_t'],
        'include/init/ssdk_dts.h': ['ssdk_netdev_switch_t'],
        'include/hsl/phy/hsl_phy.h': ['phy_dac_t', 'phy_info_t'],
        'include/hsl/hsl_port_prop.h': ['hsl_port_prop_t'],
        'src/hsl/hsl_port_prop.c': ['port_info_t'],
    }.items():
        for name in names:
            body = typedef((ssdk / rel).read_text(), name)
            types.append(body)
            (out / (name + '.h.txt')).write_text(body + '\n')
    constants = []
    for root, rel, names in [
        (ssdk, 'include/common/sw_config.h', ['SW_MAX_NR_DEV', 'SW_MAX_NR_PORT']),
        (ssdk, 'include/init/ssdk_init.h', ['SSDK_MAX_PORT_NUM', 'phy_features_t']),
        (ssdk, 'include/init/ssdk_plat.h', ['SSDK_PHYSICAL_PORT1', 'SSDK_PHYSICAL_PORT6']),
        (ssdk, 'include/init/ssdk_dts.h', ['SSDK_NETDEV_SWITCH_NUM']),
        (ssdk, 'include/ref/ref_vsi.h', ['PPE_VSI_PPORT_NR']),
        (ssdk, 'include/fal/fal_vsi.h', ['FAL_VSI_INVALID']),
        (ssdk, 'include/adpt/hppe/adpt_hppe.h', ['CPPE_REVISION', 'MPPE_REVISION']),
        (ssdk, 'include/hsl/hppe/hppe_portctrl_reg.h', ['MAC_ENABLE_INC']),
        (ssdk, 'include/hsl/hppe/hppe_xgportctrl_reg.h', ['MAC_TX_CONFIGURATION_INC']),
        (dp, 'hal/soc_ops/ipq807x/nss_ipq807x.h', ['NSS_DP_HAL_MAX_PORTS']),
    ]:
        text = (root / rel).read_text()
        for name in names:
            hits = re.findall(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M)
            require(len(hits) == 1, 'constant cardinality: ' + name)
            constants.append(hits[0])
    reg = (ssdk / 'include/hsl/hppe/hppe_reg_access.h').read_text()
    constants.append(re.findall(r'^#define NSS_MAC_CSR_BASE_ADDR[^\n]*', reg, re.M)[0])
    constants.append(re.findall(r'^#define NSS_XGMAC_CSR_BASE_ADDR[^\n]*', reg, re.M)[1])
    phy_header = (ssdk / 'include/hsl/phy/hsl_phy.h').read_text()
    for name in ['TO_PHY_ADDR_E', 'TO_PHY_ADDR']:
        hits = re.findall(r'^#define ' + name + r'\([^\n]*', phy_header, re.M)
        require(len(hits) == 1, 'actual mapper address macro')
        constants.append(hits[0])
    plat = (ssdk / 'src/init/ssdk_plat.c').read_text()
    globals_ = plat[plat.index('static DEFINE_SPINLOCK(ssdk_netdev_cache_lock)'):
                    plat.index('/* Snapshot only:')]
    for name in ['ssdk_netdev_cache_ready','ssdk_netdev_cache_mark_native_port']:
        require(plat.count('EXPORT_SYMBOL('+name+');')==1,'actual provider export source: '+name)
    for rel, prefix in [('src/hsl/hsl_dev.c', 'static hsl_dev_t dev_table'),
                         ('src/hsl/hsl_dev.c', 'ssdk_chip_type SSDK_CURRENT_CHIP_TYPE'),
                         ('src/adpt/adpt.c', 'adpt_chip_ver_t g_chip_ver'),
                         ('src/hsl/phy/hsl_phy.c', 'a_uint32_t port_bmp'),
                         ('src/ref/ref_vsi.c', 'static a_uint32_t default_pport_vsi')]:
        hits = [line for line in (ssdk / rel).read_text().splitlines() if line.startswith(prefix)]
        require(len(hits) == 1, 'metadata global: ' + prefix)
        globals_ += hits[0] + '\n'
    vsi_text=(ssdk/'src/ref/ref_vsi.c').read_text()
    prestate=[]
    for name in ['ppe_vsi_init','ppe_port_vsi_set','ppe_port_vsi_get']:
        body,line=function(vsi_text,name)
        prestate.append({'function':name,'line':line,'sha256':sha(body.encode()),
                         'body':body,'compiled':False})
    (out/'PROVIDER-VSI-PRESTATE.json').write_text(json.dumps(prestate,indent=2)+'\n')
    main = (dp / 'nss_dp_main.c').read_text()
    globals_ += main[main.index('static bool nss_dp_hal_owned;'):
                     main.index('static void nss_dp_release_stages')]
    switch = (dp / 'nss_dp_switchdev.c').read_text()
    globals_ += '#ifdef CONFIG_NET_SWITCHDEV\n' + switch[
        switch.index('static bool switchdev_blocking_owned;'):
        switch.index('#else\nstatic bool switch_init_done;')] + '\n#endif\n'
    header = (ssdk / 'include/init/ssdk_init.h').read_text()
    public = []
    for name in ['ssdk_netdev_cache_ready', 'ssdk_netdev_cache_mark_native_port']:
        hits = re.findall(r'^bool ' + name + r'\([^;\n]*\);', header, re.M)
        require(len(hits) == 1, 'installed declaration: ' + name)
        public.append(hits[0])
    for rel,name in [('include/ref/ref_vsi.h','ppe_port_vsi_get'),
                     ('include/fal/fal_vsi.h','fal_port_vsi_set')]:
        hits=re.findall(r'sw_error_t\s+'+name+r'\([^;{}]*\);',(ssdk/rel).read_text())
        require(len(hits)==1,'actual VSI leaf signature: '+name)
        public.append(hits[0])
    (out / 'MANIFEST.json').write_text(json.dumps({'functions': records,
        'types': types, 'constants': constants, 'public_declarations': public}, indent=2) + '\n')
    return bodies, '\n'.join(constants + types), globals_, '\n'.join(public), records


def render(template, bodies, types, globals_, public):
    prototypes = []
    for name, body in bodies.items():
        if name not in {'ssdk_netdev_cache_ready', 'ssdk_netdev_cache_mark_native_port'}:
            proto = body[:mask(body).index('{')].rstrip() + '\n;'
            if name in S_NAMES:
                proto = '#ifdef CONFIG_NET_SWITCHDEV\n' + proto + '\n#endif'
            prototypes.append(proto)
    definitions = []
    for name, body in bodies.items():
        if name in S_NAMES:
            body = '#ifdef CONFIG_NET_SWITCHDEV\n' + body + '\n#endif'
        definitions.append(body)
    for name, value in {'TYPES': types, 'PUBLIC': public, 'GLOBALS': globals_,
                        'PROTOTYPES': '\n'.join(prototypes),
                        'FUNCTIONS': '\n\n'.join(definitions)}.items():
        require(template.count('@@' + name + '@@') == 1, 'template marker: ' + name)
        template = template.replace('@@' + name + '@@', value)
    require('@@' not in template, 'unresolved template marker')
    return template


def installed_header_consumer(dp, ssdk, out, shim):
    """Copy only the recipe's installed SDK surface; no private-header substitute."""
    public, os_headers = out/'installed', out/'os-headers'
    public.mkdir();os_headers.mkdir()
    shutil.copytree(ssdk/'include/fal', public/'fal')
    for rel in ['include/common','include/sal/os','include/sal/os/linux']:
        for p in (ssdk/rel).glob('*.h'): shutil.copyfile(p,public/p.name)
    (public/'init').mkdir()
    (public/'ref').mkdir()
    shutil.copyfile(ssdk/'include/ref/ref_vsi.h',public/'ref/ref_vsi.h')
    for name in ['ssdk_init.h','ssdk_netlink.h']:
        shutil.copyfile(ssdk/'include/init'/name,public/'init'/name)
    # OS-level headers only. Actual SDK headers, typedefs and declarations are intact.
    for rel in ['generated/autoconf.h','asm/types.h','linux/compiler.h',
                'linux/interrupt.h','linux/spinlock.h','linux/mutex.h','linux/slab.h',
                'linux/delay.h','linux/timer.h','linux/types.h','linux/string.h']:
        p=os_headers/rel;p.parent.mkdir(exist_ok=True,parents=True)
        p.write_text('/* Host OS declaration shim; see force-included header-shim.h. */\n')
    main=(dp/'nss_dp_main.c').read_text()
    start=main.index('#if defined(NSS_DP_MAC_POLL_SUPPORT) ||')
    end=main.index('#endif', start)+len('#endif')
    actual_include=main[start:end]
    private=(dp/'include/nss_dp_dev.h').read_text()
    start=private.index('#if defined(NSS_DP_IPQ807X) && defined(NSS_DP_PPE_SUPPORT)')
    end=private.index('#endif',start)+len('#endif')
    actual_profile=private[start:end]
    text=actual_include+'\n'+actual_profile+'''
#include <ref/ref_vsi.h>
#include <fal/fal_vsi.h>
#ifndef NSS_DP_NATIVE_INIT_STAGES
#error expected selected actual private profile
#endif
_Static_assert(__builtin_types_compatible_p(__typeof__(&ssdk_netdev_cache_ready),
               bool (*)(void)), "actual installed ready declaration");
_Static_assert(__builtin_types_compatible_p(__typeof__(&ssdk_netdev_cache_mark_native_port),
               bool (*)(a_uint32_t,a_uint32_t)), "actual installed mark declaration");
_Static_assert(__builtin_types_compatible_p(__typeof__(&ppe_port_vsi_get),
               sw_error_t (*)(a_uint32_t,fal_port_t,a_uint32_t *)), "actual VSI getter signature");
_Static_assert(__builtin_types_compatible_p(__typeof__(&fal_port_vsi_set),
               sw_error_t (*)(a_uint32_t,fal_port_t,a_uint32_t)), "actual VSI setter signature");
bool header_consumer(a_uint32_t port) {
    return ssdk_netdev_cache_ready() && ssdk_netdev_cache_mark_native_port(0,port);
}
'''
    path=out/'header-consumer.c';path.write_text(text)
    return public,os_headers,path


def preservation_input(root, version, defines):
    text = '#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))\n'
    text += '#define LINUX_VERSION_CODE ' + str(version) + '\n#define IS_ENABLED(x) (x)\n'
    text += ''.join('#define '+d+' 1\n' for d in defines)
    for rel in ['include/nss_dp_dev.h','nss_dp_main.c','nss_dp_switchdev.c']:
        text += re.sub(r'(?m)^\s*#include[^\n]*\n', '\n', (root/rel).read_text()) + '\n'
    return text


def preserved_tokens(text):
    # The only nonselected syntactic difference is braces around this old log.
    text = re.sub(r'if\s*\(ret\)\s*\{\s*(pr_info\("NSS DP platform drv register failed\\n"\);)\s*\}',
                  r'if (ret) \1', text)
    return re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\d+|[^\s]', text)
