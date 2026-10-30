"""Fresh source/data preparation and audited C extraction; never run sealed code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

SOURCE = Path(__file__).resolve().parents[2]
CONTRACT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2/MUEDCA-CONTRACT.inputs/text-r5/MANIFEST.json')
CONTRACT_SHA = '1538430bbfd0b48066ad95e2250e4393624fc297f6c77e69c388606bb67b9d00'
LIBNL_SHA = 'b45c72c26961fa6eafc14f73693c2fe463912c4cb0488ccea232d61b425c60d5'
UAPI = {'netlink.h': 'f2b9dec9eb74c84239d345a9bb3aceb187caeab761579b7b58e6834a5ec64070',
        'genetlink.h': '1f2469ec331c8975e3c9643be7e23f085e1b95bef12b1b5df413d46ade3fc778'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def mask(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def balanced(text, start, left='{', right='}'):
    clean = mask(text)
    require(clean[start] == left, 'balanced start')
    depth, end = 1, start + 1
    while depth and end < len(clean):
        depth += (clean[end] == left) - (clean[end] == right)
        end += 1
    require(depth == 0, 'unterminated source block')
    return end


def function(text, name):
    clean = mask(text)
    hits = []
    for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', clean):
        end = balanced(text, clean.index('(', match.start()), '(', ')')
        brace = end
        while brace < len(clean) and clean[brace].isspace():
            brace += 1
        if brace >= len(clean) or clean[brace] != '{':
            continue
        start = clean.rfind('\n', 0, match.start()) + 1
        if not clean[start:match.start()].strip():
            previous = clean.rfind('\n', 0, start - 1) + 1
            require(clean[previous:start].strip(), 'missing function return type ' + name)
            start = previous
        hits.append((start, balanced(text, brace)))
    require(len(hits) == 1, 'ambiguous definition ' + name + ': ' + str(len(hits)))
    start, end = hits[0]
    return text[start:end], text[:start].count('\n') + 1


def block(text, pattern, suffix=';'):
    hits = list(re.finditer(pattern, mask(text), re.M))
    require(len(hits) == 1, 'ambiguous declaration ' + pattern)
    match = hits[0]
    end = balanced(text, mask(text).index('{', match.start()))
    if suffix:
        end = text.index(suffix, end) + len(suffix)
    return text[match.start():end]


def struct(text, name):
    # Nested union members may be followed by a member name before the semicolon.
    return block(text, r'\bstruct\s+' + re.escape(name) + r'\s*\{')


def enum(text, name):
    return block(text, r'\benum\s+' + re.escape(name) + r'\s*\{')


def no_includes(text):
    return re.sub(r'^#include[^\n]*\n', '', text, flags=re.M)


def once(text, old, new):
    require(text.count(old) == 1, 'transformation anchor ' + old)
    return text.replace(old, new, 1)


def macro(text, name):
    hit = re.search(r'^#define\s+' + re.escape(name) + r'(?=[\s(])[^\n]*(?:\\\n[^\n]*)*', text, re.M)
    require(hit is not None, 'missing macro ' + name)
    end = hit.start()
    lines = text[end:].splitlines(True)
    result = ''
    for line in lines:
        result += line
        if not line.rstrip().endswith('\\'):
            break
    return result.rstrip()


def archive_member(path, prefix, name):
    p = subprocess.run(['tar', '-xOf', str(path), prefix + '/' + name],
                       capture_output=True, check=True)
    require(not p.stderr, 'archive read diagnostics')
    return p.stdout


def patch_sections(text, selected):
    lines, i = text.split('\n'), 0
    while i < len(lines) - 1:
        if not (lines[i].startswith('--- ') and lines[i + 1].startswith('+++ ')):
            i += 1
            continue
        target = lines[i + 1][4:].split()[0]
        target = re.sub(r'^b/', '', target)
        i += 2
        if target not in selected:
            continue
        hunks = []
        while i < len(lines) and not lines[i].startswith(('--- ', 'diff ')):
            match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[i])
            if not match:
                i += 1
                continue
            old_count = int(match[2]) if match[2] is not None else 1
            new_count = int(match[4]) if match[4] is not None else 1
            before, after = [], []
            i += 1
            while len(before) < old_count or len(after) < new_count:
                line = lines[i]
                i += 1
                if line.startswith('\\'):
                    continue
                kind = line[0] if line else ' '
                require(kind in (' ', '+', '-'), 'invalid selected hunk')
                if kind in (' ', '-'):
                    before.append(line[1:])
                if kind in (' ', '+'):
                    after.append(line[1:])
            require(len(before) == old_count and len(after) == new_count, 'hunk count')
            hunks.append((int(match[1]), before, after))
        yield target, hunks


def prepare(output, libnl_archive, uapi_dir):
    require(sha(CONTRACT.read_bytes()) == CONTRACT_SHA, 'contract data identity')
    old = json.loads(CONTRACT.read_text())
    manifest = {'method': 'fresh selected38 plus seven support headers/sources; NOT full303 replay',
                'packages': [], 'offsets': [], 'live_inputs': {str(CONTRACT): CONTRACT_SHA}}
    extras = ['src/utils/list.h', 'src/common/defs.h', 'src/utils/common.h', 'src/common/ieee802_11_common.h']
    for package in old['packages']:
        kind = package['kind']
        archive = Path(package['archive'])
        require(sha(archive.read_bytes()) == package['archive_sha256'], 'archive identity ' + kind)
        recipe = SOURCE / package['recipe']
        require(sha(recipe.read_bytes()) == package['recipe_sha256'], 'recipe drift ' + kind)
        manifest['live_inputs'][str(recipe)] = sha(recipe.read_bytes())
        manifest['live_inputs'][str(archive)] = package['archive_sha256']
        root, rawroot = output / 'current' / kind, output / 'raw' / kind
        prefix = 'backports-6.18.26' if kind == 'kernel' else 'hostapd-2026.04.02~b004de0b'
        selected = [entry['path'] for entry in package['files']]
        if kind == 'hostapd':
            selected += extras
        else:
            selected += ['net/wireless/core.c', 'net/wireless/core.h', 'net/wireless/nl80211.h']
        files = {}
        for name in selected:
            data = archive_member(archive, prefix, name)
            p = rawroot / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            files[name] = data.decode().split('\n')
        expected_paths = [SOURCE / p['path'] for p in package['patches']]
        actual_paths = []
        for directory in dict.fromkeys(p.parent for p in expected_paths):
            actual_paths += sorted(directory.glob('*.patch'))
        require(actual_paths == expected_paths, 'ordered patch inventory drift ' + kind)
        for patch in package['patches']:
            path = SOURCE / patch['path']
            data = path.read_bytes()
            require(sha(data) == patch['sha256'], 'patch input drift ' + str(path))
            manifest['live_inputs'][str(path)] = patch['sha256']
            saved = output / 'patches' / patch['path']
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(data)
            for target, hunks in patch_sections(data.decode(), files):
                delta, carry = 0, 0
                for old_line, before, after in hunks:
                    nominal = (old_line - 1 if old_line else 0) + delta
                    expected = nominal + carry
                    a = files[target]
                    def matches(pos):
                        return pos >= 0 and a[pos:pos + len(before)] == before
                    pos = expected
                    if not matches(pos):
                        hits = [j for j in range(len(a) - len(before) + 1) if matches(j)]
                        require(len(hits) == 1, 'ambiguous full-context hunk ' + str(path))
                        pos = hits[0]
                    carry = pos - nominal
                    if carry:
                        manifest['offsets'].append({'patch': patch['path'], 'file': target,
                                                    'line': old_line, 'offset': carry})
                    a[pos:pos + len(before)] = after
                    delta += len(after) - len(before)
        records = {}
        for name, lines in files.items():
            data = '\n'.join(lines).encode()
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            records[name] = sha(data)
        for item in package['files']:
            require(records[item['path']] == item['current_sha256'], 'fresh selected text differs')
        manifest['packages'].append({'kind': kind, 'archive': str(archive),
                                     'archive_sha256': package['archive_sha256'],
                                     'patch_count': len(package['patches']), 'files': records})
    selected_keys = {(p['kind'],f['path']) for p in old['packages'] for f in p['files']}
    original_offsets = [o for o in manifest['offsets'] if ('kernel',o['file']) in selected_keys or ('hostapd',o['file']) in selected_keys]
    require(len(original_offsets) == 27, 'selected38-context offset inventory changed')
    manifest['selected38_offsets'] = len(original_offsets)
    manifest['additional_support_offsets'] = len(manifest['offsets'])-len(original_offsets)
    require(sha(libnl_archive.read_bytes()) == LIBNL_SHA, 'exact libnl-tiny mirror hash')
    recipe = SOURCE / 'package/libs/libnl-tiny/Makefile'
    require('PKG_SOURCE_VERSION:=40493a655d8caa2ccf5206dde1e733abe2920432' in recipe.read_text() and
            'PKG_MIRROR_HASH:='+LIBNL_SHA in recipe.read_text(), 'libnl recipe pin')
    manifest['live_inputs'][str(recipe)] = sha(recipe.read_bytes())
    manifest['libnl_recipe'] = str(recipe)
    manifest['live_inputs'][str(libnl_archive)] = LIBNL_SHA
    nlroot = output / 'libnl'
    nlroot.mkdir()
    listing = subprocess.run(['tar', '-tf', str(libnl_archive)], capture_output=True,
                             text=True, check=True).stdout.splitlines()
    prefix = 'libnl-tiny-2025.12.02~40493a65/'
    for name in listing:
        require(name.startswith(prefix) and '..' not in Path(name).parts, 'libnl archive member')
    # The verified source archive contains only normal files/directories.
    subprocess.run(['tar', '-xf', str(libnl_archive), '-C', str(nlroot)], check=True)
    for name, digest in UAPI.items():
        source = uapi_dir / ('linux-v6.18.26-' + name)
        require(sha(source.read_bytes()) == digest, 'exact primary Linux UAPI header ' + name)
        dest = output / 'uapi' / name
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(source.read_bytes())
        manifest['live_inputs'][str(source)] = digest
    (output / 'INPUTS.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


class Extractor:
    def __init__(self, output):
        self.output, self.records, self.changes = output, [], []

    def fn(self, path, name, rename=None, compiled=True):
        text = path.read_text()
        code, line = function(text, name)
        self.records.append({'path': str(path), 'name': name, 'line': line,
                             'original_sha256': sha(code.encode()), 'kind': 'complete function', 'compiled_complete_body': compiled})
        saved = self.output / 'functions' / (name + '.txt')
        saved.parent.mkdir(exist_ok=True)
        saved.write_text(code + '\n')
        if rename:
            code = re.sub(r'\b' + name + r'\b', rename, code, count=1)
            self.changes.append({'function': name, 'change': 'symbol rename only', 'to': rename})
        return code

    def data(self, path, code, kind):
        self.records.append({'path': str(path), 'kind': kind, 'sha256': sha(code.encode())})
        return code

    def finish(self):
        (self.output / 'EXTRACTIONS.json').write_text(json.dumps(self.records, indent=2) + '\n')
        (self.output / 'TRANSFORMATIONS.json').write_text(json.dumps(self.changes, indent=2) + '\n')


def c_sources(output):
    host = output / 'current/hostapd'
    nl = output / 'libnl/libnl-tiny-2025.12.02~40493a65'
    ex = Extractor(output)
    text = lambda p: p.read_text()
    headers = [no_includes(text(output / 'uapi/netlink.h')),
               no_includes(text(output / 'uapi/genetlink.h')),
               no_includes(text(nl / 'include/netlink/errno.h')),
               no_includes(text(host / 'src/utils/list.h'))]
    nm = text(nl / 'include/netlink/msg.h')
    headers.append(ex.data(nl / 'include/netlink/msg.h', struct(nm, 'nl_msg'), 'actual unmodified nl_msg'))
    at = text(nl / 'include/netlink/attr.h')
    headers.append(block(at, r'enum\s*\{'))
    headers.append(struct(at, 'nla_policy'))
    headers += [macro(at, name) for name in ('NLA_TYPE_MAX', 'nla_for_each_attr')]
    headers.append(enum(text(nl / 'include/netlink/handlers.h'), 'nl_cb_action'))
    uapi = text(host / 'src/drivers/nl80211_copy.h')
    for name in ('nl80211_commands', 'nl80211_attrs', 'nl80211_iftype'):
        headers.append(ex.data(host / 'src/drivers/nl80211_copy.h', enum(uapi, name), 'complete enum'))
    kernel_header = output / 'current/kernel/include/uapi/linux/nl80211.h'
    for name in ('nl80211_commands', 'nl80211_attrs'):
        actual = enum(text(kernel_header), name)
        ex.data(kernel_header, actual, 'complete kernel enum, characterization only')
        headers.append(re.sub(r'\b\w*NL80211_\w*', lambda m: 'KERNEL_'+m[0], actual).replace('enum '+name, 'enum kernel_'+name))
    ex.changes.append({'declaration': 'kernel enums', 'change': 'symbol prefix only, independently characterize existing values; no wire alias'})
    driver = text(host / 'src/drivers/driver.h')
    headers += [enum(driver, 'wpa_event_type'), enum(text(host / 'src/common/defs.h'), 'chan_width')]
    headers.append('union wpa_event_data {\n' + struct(driver, 'update_muedca') + '\n' +
                   struct(driver, 'incumbt_sig_intf_event') + '\n};')
    # Preserve actual member declarations; unused driver/AP members are omitted.
    dh = text(host / 'src/drivers/driver_nl80211.h')
    headers += [struct(dh, 'nl80211_global'), struct(dh, 'i802_link'), struct(dh, 'i802_bss')]
    dw = struct(dh, 'wpa_driver_nl80211_data')
    members = ['struct nl80211_global *global;', 'struct dl_list list;', 'void *ctx;',
               'struct wpa_driver_capa capa;', 'unsigned int unique_drv_id;',
               'int scan_complete_events;', 'enum nl80211_iftype ap_scan_as_station;',
               'unsigned int scan_for_auth:1;', 'int last_scan_cmd;',
               'u32 ignore_next_local_disconnect;', 'u32 ignore_next_local_deauth;',
               'struct i802_bss *first_bss;']
    for member in members:
        require(re.sub(r'\s+', '', member) in re.sub(r'\s+', '', mask(dw)), 'driver member ' + member)
    headers.append('struct wpa_driver_nl80211_data {\n' + '\n'.join(members) + '\n' +
                   block(dw, r'enum\s+scan_states\s*\{') + '\n};')
    ex.changes.append({'structure': 'wpa_driver_nl80211_data / wpa_event_data',
                       'change': 'actual relevant-member projection, NOT whole driver ABI'})
    for name in ('WPA_DRIVER_FLAGS_SELF_MANAGED_REGULATORY',):
        headers.append(re.search(r'^#define ' + name + r'[^\n]*', driver, re.M)[0])
    defs = text(host / 'src/common/defs.h')
    headers.insert(0, re.search(r'^#define MAX_NUM_MLD_LINKS[^\n]*', defs, re.M)[0])
    headers.append(struct(text(host / 'src/common/ieee802_11_defs.h'), 'ieee80211_he_mu_edca_parameter_set'))
    headers.append(macro(dh, 'NL80211_DRV_LINK_ID_NA'))
    hedefs = text(host / 'src/common/ieee802_11_defs.h')
    headers += [macro(hedefs, n) for n in ('WLAN_EID_EXTENSION', 'WLAN_EID_EXT_HE_MU_EDCA_PARAMS')]
    headers.append(struct(text(host / 'src/common/ieee802_11_common.h'), 'hostapd_wmm_ac_params'))
    headers.append(enum(hedefs, 'wmm_ac'))
    headers.append(struct(driver, 'hostapd_wmm_rule'))
    ah, ac = host / 'src/ap/hostapd.h', host / 'src/ap/ap_config.h'
    projections = {
        'hostapd_channel_data': (host / 'src/drivers/driver.h', ['int freq;', 'int wmm_rules_valid;', 'struct hostapd_wmm_rule wmm_rules[WMM_AC_NUM];']),
        'hostapd_hw_modes': (host / 'src/drivers/driver.h', ['int num_channels;', 'struct hostapd_channel_data *channels;']),
        'hostapd_bss_config': (ac, ['int wmm_enabled;', 'bool disable_11ax;']),
        'hostapd_config': (ac, ['int ieee80211ax;', 'u8 op_class;', 'struct ieee80211_he_mu_edca_parameter_set he_mu_edca;', 'struct hostapd_wmm_ac_params wmm_ac_params[4];']),
        'hapd_interfaces': (ah, ['size_t count;', 'struct hostapd_iface **iface;']),
        'hostapd_iface': (ah, ['struct hapd_interfaces *interfaces;', 'struct hostapd_config *conf;', 'size_t num_bss;', 'struct hostapd_data **bss;', 'struct hostapd_hw_modes *current_mode;', 'int freq;', 'struct hostapd_wmm_ac_params prev_wmm[WMM_AC_NUM];']),
        'hostapd_data': (ah, ['struct hostapd_iface *iface;', 'struct hostapd_config *iconf;', 'struct hostapd_bss_config *conf;', 'int num_sta;', 'int parameter_set_count;', 'int beacon_set_done;', 'unsigned int started:1;', 'void *drv_priv;', 'int csa_in_progress;', 'bool cca_in_progress;'])}
    for name, (path, members) in projections.items():
        actual = re.sub(r'\s+', '', mask(struct(text(path), name)))
        for member in members:
            require(re.sub(r'\s+', '', member) in actual, 'AP projected member ' + name + ':' + member)
        headers.append('struct ' + name + ' {\n' + '\n'.join(members) + '\n};')
        ex.changes.append({'structure': name, 'source': str(path), 'members': members,
                           'change': 'exact relevant-member projection; NOT hostapd binary ABI'})
    dc = host / 'src/drivers/driver_nl80211.c'
    headers.append(struct(text(dc), 'nl80211_pending_event'))
    lib = []
    for name in ('nlmsg_msg_size', 'nlmsg_total_size', 'nlmsg_padlen', 'nlmsg_data',
                 'nlmsg_tail', 'nlmsg_len', 'nlmsg_attrdata', 'nlmsg_attrlen',
                 'nlmsg_valid_hdr', 'nlmsg_get_max_size', 'nlmsg_hdr', 'nlmsg_get'):
        lib.append(ex.fn(nl / 'include/netlink/msg.h', name))
    for name in ('nla_attr_size', 'nla_total_size', 'nla_padlen', 'nla_type',
                 'nla_data', 'nla_len', 'nla_get_u8', 'nla_get_u16',
                 'nla_get_u32', 'nla_get_u64', 'nla_put_u32', 'nla_put_u64', 'nla_memcpy'):
        lib.append(ex.fn(nl / 'include/netlink/attr.h', name))
    lib += [block(text(nl / 'attr.c'), r'static uint16_t nla_attr_minlen[^=]*=\s*\{')]
    for name in ('nla_ok', 'nla_next', 'validate_nla', 'nla_parse', 'nla_validate', 'nla_reserve', 'nla_put'):
        lib.append(ex.fn(nl / 'attr.c', name))
    for name in ('nlmsg_ok', 'nlmsg_next', '__nlmsg_alloc', 'nlmsg_alloc_size',
                 'nlmsg_convert', 'nlmsg_reserve', 'nlmsg_append', 'nlmsg_put', 'nlmsg_free'):
        lib.append(ex.fn(nl / 'msg.c', name))
    for name in ('genlmsg_valid_hdr', 'genlmsg_data', 'genlmsg_len', 'genlmsg_attrdata',
                 'genlmsg_attrlen', 'genlmsg_put'):
        lib.append(ex.fn(nl / 'genl.c', name))
    events = host / 'src/drivers/driver_nl80211_event.c'
    names = ['nl80211_command_to_string', 'nl80211_update_muedca_params_event',
             'nl80211_incumbt_sig_intf_event', 'do_process_drv_event',
             'nl80211_drv_in_list', 'process_global_event', 'process_bss_event']
    original = {name: ex.fn(events, name) for name in names}
    original['do_process_drv_event'] = once(original['do_process_drv_event'],
                                          '\n\tstruct wpa_driver_nl80211_data *drv = bss->drv;',
                                          '\n\tstruct wpa_driver_nl80211_data *drv = bss->drv;\n\troute_observe(bss, cmd, tb);')
    ex.changes.append({'function': 'do_process_drv_event', 'change': 'entry observer only; original complete switch retained'})
    for name in ('nl80211_remove_pending_event', 'nl80211_deliver_pending_events', 'nl80211_reply_hook'):
        original[name] = ex.fn(dc, name)
    ap = host / 'src/ap/drv_callbacks.c'
    original['baseline_update'] = ex.fn(ap, 'hostapd_event_update_muedca_params', 'baseline_update')
    original['hostapd_is_he_enabled'] = ex.fn(ah, 'hostapd_is_he_enabled')
    beacon = host / 'src/ap/beacon.c'
    for name in ('ieee802_11_update_beacons', 'ieee802_11_set_beacon'):
        original[name] = ex.fn(beacon, name)
    whole_beacon = ex.fn(beacon, '__ieee802_11_set_beacon', compiled=False)
    guards = whole_beacon[whole_beacon.index('\tif (!hapd->drv_priv)'):whole_beacon.index('\n\thapd->beacon_set_done = 1;')]
    original['beacon_gate_projection'] = 'static int beacon_gate_projection(struct hostapd_data *hapd) {\n'+guards+'\nreturn 0;\n}'
    ex.changes.append({'function': '__ieee802_11_set_beacon', 'change': 'only exact disabled/CSA/AX-CCA gates projected; remainder is a counted/failing hardware leaf',
                       'original_sha256': sha(whole_beacon.encode()), 'guard_sha256': sha(guards.encode())})
    for name in ('wmm_set_regulatory_limit', 'wmm_calc_regulatory_limit'):
        original[name] = ex.fn(host / 'src/ap/wmm.c', name)
    he = host / 'src/ap/ieee802_11_he.c'
    original['hostapd_eid_he_mu_edca_parameter_set'] = ex.fn(he, 'hostapd_eid_he_mu_edca_parameter_set')
    # Compile only the actual relevant AP switch branch; unrelated AP cases pruned.
    whole = ex.fn(ap, 'hostapd_wpa_event', compiled=False)
    match = re.search(r'\tcase EVENT_UPDATE_MUEDCA_PARAMS:[\s\S]*?\t\t break;', whole)
    require(match is not None and '#endif /* CONFIG_IEEE80211AX */' in whole[match.end():], 'AP AX case guard')
    ap_projection = ('static void ap_event_projection(void *ctx, enum wpa_event_type event, union wpa_event_data *data) {\n'
                     'struct hostapd_data *hapd=ctx; switch(event) {\n#ifdef CONFIG_IEEE80211AX\n' +
                     match[0] + '\n#endif\ndefault: break; }}')
    original['ap_event_projection'] = ap_projection
    supp = ex.fn(host / 'wpa_supplicant/events.c', 'supplicant_event', compiled=False)
    require('case EVENT_UPDATE_MUEDCA_PARAMS:' not in mask(supp), 'supplicant added MU case; rereview')
    default = re.search(r'\n\tdefault:\n\t\twpa_msg\(wpa_s, MSG_INFO, "Unknown event %d", event\);\n\t\tbreak;', supp)
    require(default is not None, 'supplicant exact default')
    original['supp_event_projection'] = ('static void supp_event_projection(enum wpa_event_type event) {\n'
        'void *wpa_s=NULL; switch(event) {' + default[0] + '\n} }')
    for path, name in ((nl / 'nl.c', 'nl_recv'), (nl / 'nl.c', 'recvmsgs')):
        # References are retained as complete data, never compiled/socket-executed.
        ex.fn(path, name, compiled=False)
    ex.fn(output / 'current/kernel/net/wireless/nl80211.c', 'cfg80211_update_muedca_params_event', compiled=False)
    for path, name in (('net/wireless/core.c','wiphy_new_nm'),
                       ('net/wireless/core.c','cfg80211_register_wdev'), ('net/wireless/nl80211.h','wdev_id')):
        code=ex.fn(output / 'current/kernel' / path, name, compiled=False)
        raw, _=function(text(output / 'raw/kernel' / path),name)
        require(code==raw, 'allocation/encoding body changed by local patches; rereview '+name)
    require('int devlist_generation, wdev_id;' in text(output / 'current/kernel/net/wireless/core.h'), 'actual wdev counter type')
    ex.changes.append({'identity_domain_reference': 'exact backports wiphy allocator starts0, rejects negative increment result before decrement; max allocated INT_MAX-1; wdev identifier0 reserved and increment assigned, high32=wiphy, low32=identifier',
        'limits': 'reference-only allocator/encoder bodies unchanged by current patch chain; not a runtime kernel allocation/wrap/registration/lifetime proof'})
    ap_global = ex.fn(ap, 'hostapd_wpa_event_global', compiled=False)
    require('case EVENT_UPDATE_MUEDCA_PARAMS:' not in mask(ap_global), 'AP global added MU case; rereview')
    registration = []
    for callback in ('process_global_event', 'process_bss_event'):
        hit = re.search(r'nl_cb_set\([^;]+\b'+callback+r'\s*,[^;]+;', text(dc))
        require(hit is not None, 'exact callback registration '+callback)
        registration.append({'path': str(dc), 'line': text(dc)[:hit.start()].count('\n')+1, 'statement': hit[0]})
    ex.changes.append({'callback_registrations_reference_only': registration})
    ex.changes.append({'receive_boundary': 'nl_recv -> recvmsgs(nlmsg_ok with actual n) -> nlmsg_convert -> callback(nl_msg*,void*)',
        'limitation': 'saved complete receive functions are reference only, not socket executed; nm_size is capacity, true received extent is not in callback API'})
    ex.changes.append({'boundary_leaf_stubs': ['wpa_printf/wpa_dbg/hostapd_logger/wpa_hexdump',
        'wpa_msg (counts actual projected unknown default)', 'os_zalloc (allocation-failure injection)',
        'eloop_register_timeout (manual queue delivery)', 'nl80211_get_wiphy_index (fixture lookup)',
        'nl80211_has_ifidx (fixture bridge equality)', 'convert2width (fixed non-MLO width)',
        'nl80211_get_link_id_by_freq (NA non-MLO)', 'is_6ghz_op_class (bounded opclass model)',
        '__ieee802_11_set_beacon (real gate projection + record/fail leaf; not full builder)'],
        'host_shims': ['fixed-width Linux integer types', 'unused ucred storage', 'wpa_driver_capa flags member only',
                       'logging levels and utility macros; no ABI/layout assertion for projected daemon structures']})
    ex.changes.append({'function': 'hostapd_wpa_event', 'change': 'MU case + real AX guard projection; other AP events not tested',
                       'original_sha256': sha(whole.encode())})
    ex.changes.append({'function': 'supplicant_event', 'change': 'MU absence and actual unknown-event default projection only; not full supplicant engine',
                       'original_sha256': sha(supp.encode())})
    stubs = sorted(set(re.findall(r'\b(?:nl80211_\w+|mlme_\w+|send_scan_event|eloop_cancel_timeout)\s*(?=\()',
                                 original['do_process_drv_event'] + original['process_bss_event'])))
    kept = set(original) | {'nl80211_reply_hook', 'nl80211_get_wiphy_index', 'nl80211_has_ifidx'}
    stubs = [name for name in stubs if name not in kept]
    stub_code = '\n'.join('#define ' + name + '(...) leaf_event("' + name + '")' for name in stubs)
    ex.changes.append({'boundary_leaf_stubs': stubs, 'effect': 'counted leaf no I/O; no real daemon/socket/device'})
    prototypes = '\n'.join(code[:code.index('{')].strip() + ';' for code in lib + list(original.values())
                            if not code.lstrip().startswith('static uint16_t'))
    actual_ac = text(ac)
    require(re.search(r'#ifdef CONFIG_IEEE80211AX\n[^#]*\bhe_mu_edca;', actual_ac) is not None,
            'AX guard on real he_mu_edca member')
    ax_headers = once('\n'.join(headers), 'struct ieee80211_he_mu_edca_parameter_set he_mu_edca;',
                      '#ifdef CONFIG_IEEE80211AX\nstruct ieee80211_he_mu_edca_parameter_set he_mu_edca;\n#endif')
    ax_probe = (ax_headers + '\nvoid hostapd_logger(void *, void *, int, int, const char *, ...);\n'
                'void wpa_printf(int, const char *, ...);\nint ieee802_11_update_beacons(struct hostapd_iface *);\n' +
                original['baseline_update']+'\n'+original['wmm_set_regulatory_limit']+'\n'+original['wmm_calc_regulatory_limit'])
    ex.changes.append({'AXoff': 'main route-branch fixture intentionally retains HE fields as a type superset; not real AXoff header compatibility',
                       'separate_probe': 'actual he_mu_edca AX guard + full baseline AP/WMM bodies, syntax characterization; compile errors are NOT runtime negatives'})
    ex.finish()
    return {'headers': '\n'.join(headers), 'prototypes': prototypes,
            'lib': '\n\n'.join(lib), 'original': '\n\n'.join(original.values()),
            'leaf_stubs': stub_code, 'ax_probe': ax_probe}
