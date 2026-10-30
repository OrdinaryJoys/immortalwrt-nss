#!/usr/bin/env python3
"""Actual SSDK030 C definitions in a bounded native allocation/value fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import ssdk_source_prepare as source

HERE = Path(__file__).resolve()
FIX = HERE.parent / 'ssdk-netdev-cache'
PATCH = source.PACKAGE / 'patches/030-ssdk-netdev-cache-retirement.patch'
FROZEN_029 = 'a0e19f941d404525dd21bc4c374e577ac3ca8d6663425e2a5a437d36adcf8cd5'
FROZEN_030 = 'd99c275b58d73910108e1cd92c07ac07dd27dcc6b0530f5fac6b18ce933b066f'
CASES = '''readiness normal primary-only duplicate replacement rename all-slots identity-hw reader
stop replay-success replay-api-error replay-fail-0 replay-fail-1 replay-fail-2
admission bounds copy-bounds legacy tombstone g3-missing g3-no-phy g3-success dsa sysfs
fdb-new fdb-expire fdb-missing property-domain mark-states mark-reject mark-failed-register
mark-reregister'''.split()
PROFILES = {
    'hppe': ['-DHPPE=1', '-DCONFIG_NET_DSA=0'],
    'hppe-dsa': ['-DHPPE=1', '-DCONFIG_NET_DSA=1'],
    'appe-dsa': ['-DHPPE=1', '-DAPPE=1', '-DCONFIG_NET_DSA=1'],
    'mp': ['-DMP=1', '-DCONFIG_NET_DSA=0'],
    'mp-dsa': ['-DMP=1', '-DCONFIG_NET_DSA=1'],
}
GROUPS = {
    'src/init/ssdk_plat.c': '''ssdk_netdev_to_portid ssdk_netdev_cache_ready ssdk_netdev_cache_mark_native_port
ssdk_netdev_cache_start ssdk_netdev_cache_commit ssdk_netdev_cache_remove
ssdk_netdev_cache_stop ssdk_netdev_cache_unregister ssdk_netdev_cache_rename
ssdk_netdev_cache_name ssdk_netdev_cache_index ssdk_switch_netdev_get
ssdk_switch_name_copy ssdk_netdev_switch_init ssdk_switch_set_standby_status
ssdk_switch_enable_dsa ssdk_eth_switch_get'''.split(),
    'src/init/ssdk_init.c': '''ssdk_ifname_to_port ssdk_port_to_ifname_copy
ssdk_nss_dp_netdev_check ssdk_netdev_switch_init_required ssdk_dev_event
ssdk_netdev_notifier_register ssdk_netdev_notifier_unregister'''.split(),
    'src/init/ssdk_dts.c': '''ssdk_dts_netdev_switch_get ssdk_dts_netdev_switch_find
ssdk_dts_netdev_switch_find_by_netdev ssdk_dts_netdev_switch_find_by_devid'''.split(),
    'src/ref/ref_fdb.c': ['_ref_fdb_notify_mac'],
    'src/hsl/phy/hsl_phy.c': ['hsl_phy_info_get'],
    'src/hsl/hsl_port_prop.c': ['hsl_port_prop_check'],
    'src/hsl/hsl_dev.c': ['hsl_dev_ptr_get', 'hsl_get_current_chip_type'],
    'src/hsl/hppe/hppe_init.c': ['hppe_dev_init'],
    'src/adpt/adpt.c': ['adpt_ppe_type_get'],
}
DSA_ONLY = {'ssdk_switch_netdev_get', 'ssdk_switch_enable_dsa'}


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def masked(text):
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def close_brace(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if not depth:
                return i + 1
    raise RuntimeError('unclosed C definition')


def function(text, name):
    clean = masked(text)
    result = list(re.finditer(
        r'(?m)^(?:static\s+)?(?:void|int|bool|ssize_t|a_bool_t|a_uint32_t|sw_error_t|'
        r'phy_info_t|ssdk_netdev_switch_t|hsl_dev_t|ssdk_chip_type|adpt_ppe_type_t|struct\s+net_device)\s*\**\s*(?:(?:__init|__exit)\s+)?' +
        re.escape(name) + r'\s*\([^;{}]*\)\s*\{', clean))
    require(len(result) == 1, 'definition cardinality: ' + name)
    match = result[0]
    end = close_brace(clean, clean.index('{', match.start()))
    return text[match.start():end], text.count('\n', 0, match.start()) + 1


def typedef(text, name):
    end = list(re.finditer(r'}\s*' + re.escape(name) + r'\s*;', masked(text)))
    require(len(end) == 1, 'typedef cardinality: ' + name)
    start = max(text.rfind('typedef struct', 0, end[0].start()),
                text.rfind('typedef enum', 0, end[0].start()))
    require(start >= 0, 'typedef start: ' + name)
    return text[start:end[0].end()]


def once(text, old, new):
    require(text.count(old) == 1, 'mutation anchor cardinality: ' + old[:100])
    return text.replace(old, new, 1)


def source_gate(tree):
    init = (tree / 'src/init/ssdk_init.c').read_text()
    plat = (tree / 'src/init/ssdk_plat.c').read_text()
    decl = (tree / 'include/init/ssdk_init.h').read_text()
    require(decl.count('bool ssdk_netdev_cache_ready(void);') == 1, 'ready prototype')
    require('ssdk_netdev_cache_ready' not in (tree / 'include/init/ssdk_plat.h').read_text(),
            'no private ready declaration')
    recipe = (source.PACKAGE / 'Makefile').read_text()
    require('$(INSTALL_DATA) $(PKG_BUILD_DIR)/include/init/ssdk_init.h $(1)/usr/include/qca-ssdk/init/;' in recipe,
            'ready public header InstallDev wiring')
    require(plat.count('EXPORT_SYMBOL(ssdk_netdev_cache_ready);') == 1, 'ready export')
    require(decl.count('bool ssdk_netdev_cache_mark_native_port(a_uint32_t dev_id, a_uint32_t port_id);') == 1,
            'mark prototype')
    require(plat.count('EXPORT_SYMBOL(ssdk_netdev_cache_mark_native_port);') == 1, 'mark export')
    mark, _ = function(plat, 'ssdk_netdev_cache_mark_native_port')
    calls = set(re.findall(r'\b(\w+)\s*\(', masked(mark)))
    require(calls <= {'ssdk_netdev_cache_mark_native_port', 'if', 'spin_lock_bh', 'spin_unlock_bh',
                     'hsl_get_current_chip_type', 'hsl_dev_ptr_get', 'adpt_ppe_type_get'},
            'producer mark metadata-only calls')
    ready, _ = function(plat, 'ssdk_netdev_cache_ready')
    require(ready.count('spin_lock_bh(') == ready.count('spin_unlock_bh(') == 1 and
            'ready = ssdk_netdev_cache_live;' in ready, 'ready short lock snapshot')
    root, _ = function(init, 'regi_init')
    require(root.count('ssdk_netdev_notifier_register();') == 1 and
            not re.search(r'\brv\s*=\s*ssdk_netdev_notifier_register', root), 'optional notifier policy')
    for name in ['ssdk_cleanup', 'ssdk_free_priv']:
        body, _ = function(init, name)
        require(body.index('ssdk_netdev_cache_stop();') < body.index('ssdk_fdb_retire_controls();'),
                'cache stop before managed owner cleanup: ' + name)
    exit_, _ = function(init, 'regi_exit')
    require(exit_.index('ssdk_netdev_notifier_unregister();') < exit_.index('ssdk_driver_unregister('),
            'notifier/cache before hardware teardown')
    require('ssdk_port_to_ifname(' not in init and
            'ssdk_port_to_ifname(' not in (tree / 'src/ref/ref_fdb.c').read_text(), 'borrowed helper removed')
    # Exhaustive textual census for these exact field names, not a whole-tree review.
    accesses = []
    helpers = ['ssdk_netdev_cache_remove', 'ssdk_netdev_cache_rename', 'ssdk_netdev_cache_name',
               'ssdk_netdev_cache_index', 'ssdk_switch_netdev_get', 'ssdk_netdev_switch_init']
    ranges = []
    for name in helpers:
        body, line = function(plat, name)
        ranges.append((line, line + body.count('\n'), name))
    for p in sorted((tree / 'src').rglob('*.c')):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if re.search(r'->netdev\[|netdev_switch\[[^]]+\]\.dev|\b(?:sw|netdev_switch)->dev\b', line):
                owner = next((name for start, end, name in ranges if start <= n <= end), None)
                accesses.append({'path': str(p.relative_to(tree)), 'line': n,
                                 'function': owner, 'text': line.strip()})
    require(accesses and all(a['path'] == 'src/init/ssdk_plat.c' and a['function'] for a in accesses),
            'direct cache access outside helper layer')
    return {'status': 'PASS_BOUNDED_TEXT_GATES_NOT_KERNEL_COMPILE', 'direct_accesses': accesses,
            'root_init': 'definition inspected, not compiled/invoked',
            'cleanup': 'stop ordering inspected, full root drain not certified'}


def extract(tree, dest):
    dest.mkdir()
    bodies, records = {}, []
    for path, names in GROUPS.items():
        text = (tree / path).read_text()
        for name in names:
            body, line = function(text, name)
            bodies[name] = body
            (dest / (name + '.c.txt')).write_text(body + '\n')
            records.append({'function': name, 'path': path, 'line': line,
                            'sha256': sha(body.encode()), 'complete_definition': True})
    types = []
    for path, names in {
        'include/init/ssdk_init.h': ['ssdk_chip_type', 'ssdk_port_cfg'],
        'include/hsl/hsl_dev.h': ['hsl_dev_t'],
        'include/hsl/hsl_port_prop.h': ['hsl_port_prop_t'],
        'include/adpt/adpt.h': ['adpt_chip_ver_t', 'adpt_ppe_type_t'],
        'include/init/ssdk_dts.h': ['ssdk_netdev_switch_t'],
        'include/hsl/phy/hsl_phy.h': ['phy_dac_t', 'phy_info_t'],
        'include/ref/ref_fdb.h': ['ref_fdb_info_t'],
        'src/hsl/hsl_port_prop.c': ['port_info_t'],
    }.items():
        for name in names:
            full = typedef((tree / path).read_text(), name)
            types.append(full)
            (dest / (name + '.h.txt')).write_text(full + '\n')
    constants = []
    for path, names in {
        'include/common/sw_config.h': ['SW_MAX_NR_DEV', 'SW_MAX_NR_PORT'],
        'include/init/ssdk_init.h': ['SSDK_MAX_PORT_NUM', 'phy_features_t'],
        'include/init/ssdk_plat.h': ['SSDK_PHYSICAL_PORT1', 'SSDK_PHYSICAL_PORT6'],
        'include/adpt/hppe/adpt_hppe.h': ['CPPE_REVISION', 'MPPE_REVISION'],
        'include/init/ssdk_dts.h': ['SSDK_NETDEV_SWITCH_NUM'],
        'include/ref/ref_fdb.h': ['REF_FDB_MAC_NEW', 'REF_FDB_MAC_OLD', 'REF_FDB_MAC_EXPIRE'],
        'include/hsl/hppe/hppe_portctrl_reg.h': ['MAC_ENABLE_INC'],
        'include/hsl/hppe/hppe_xgportctrl_reg.h': ['MAC_TX_CONFIGURATION_INC'],
        'include/hsl/mp/mp_portctrl_reg.h': ['MAC_CONFIGURATION_INC'],
    }.items():
        text = (tree / path).read_text()
        for name in names:
            hit = re.findall(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M)
            require(len(hit) == 1, 'actual constant cardinality: ' + name)
            constants.append(hit[0])
    reg = (tree / 'include/hsl/hppe/hppe_reg_access.h').read_text()
    constants.append(reg[reg.index('#if defined(APPE)'):reg.index('#define TUNNEL_PARSER_BASE_ADDR')])
    # Keep the exact conditional definition block, excluding unrelated registers.
    constants[-1] = '#if defined(APPE)\n' + re.findall(r'^#define NSS_XGMAC_CSR_BASE_ADDR[^\n]*', reg, re.M)[0] + '\n#else\n' + re.findall(r'^#define NSS_XGMAC_CSR_BASE_ADDR[^\n]*', reg, re.M)[1] + '\n#endif'
    constants.append(re.findall(r'^#define NSS_MAC_CSR_BASE_ADDR[^\n]*', reg, re.M)[0])
    constants.append('#ifdef MP\n#define MP_GMAC_BASE_ADDR 0xc00000\n#endif')
    original_mp = (tree / 'src/init/ssdk_plat.c').read_text()
    require('#define MP_GMAC_BASE_ADDR 0xc00000' in original_mp, 'actual MP base')
    net = (tree / 'include/init/ssdk_netlink.h').read_text()
    enums = re.findall(r'enum(?:\s+\w+)?\s*\{[^{}]*\};', net)
    cmd = [e for e in enums if 'SSDK_COMMAND_NEW_MAC' in e]
    require(len(cmd) == 1, 'actual command enum')
    plat = (tree / 'src/init/ssdk_plat.c').read_text()
    globals_ = plat[plat.index('static DEFINE_SPINLOCK(ssdk_netdev_cache_lock)'):
                    plat.index('/* Snapshot only:')]
    globals_ += '\nEXPORT_SYMBOL(ssdk_netdev_cache_ready);\n'
    globals_ += 'EXPORT_SYMBOL(ssdk_netdev_cache_mark_native_port);\n'
    for path, prefix in [('src/hsl/hsl_dev.c', 'static hsl_dev_t dev_table'),
                         ('src/hsl/hsl_dev.c', 'ssdk_chip_type SSDK_CURRENT_CHIP_TYPE'),
                         ('src/adpt/adpt.c', 'adpt_chip_ver_t g_chip_ver')]:
        hits = [line for line in (tree / path).read_text().splitlines() if line.startswith(prefix)]
        require(len(hits) == 1, 'actual metadata global: ' + prefix)
        globals_ += hits[0] + '\n'
    public_header = (tree / 'include/init/ssdk_init.h').read_text()
    declarations = re.findall(r'^bool ssdk_netdev_cache_ready\(void\);$', public_header, re.M)
    require(len(declarations) == 1, 'actual public ready declaration')
    public_ready = declarations[0]
    marks = re.findall(r'^bool ssdk_netdev_cache_mark_native_port\(a_uint32_t dev_id, a_uint32_t port_id\);$', public_header, re.M)
    require(len(marks) == 1, 'actual public mark declaration')
    public_mark = marks[0]
    (dest / 'ssdk_init.full.h.txt').write_text(public_header)
    (dest / 'public-ready-declaration.h.txt').write_text(public_ready + '\n')
    (dest / 'public-mark-declaration.h.txt').write_text(public_mark + '\n')
    template = (FIX / 'host-fixture.c').read_text()
    actual_types = '\n'.join(constants + types + cmd)
    def render(selected):
        definitions, prototypes = [], []
        for name, body in selected.items():
            proto = body[:masked(body).index('{')].rstrip() + ';'
            if name == 'ssdk_netdev_cache_ready':
                proto = public_ready
            if name == 'ssdk_netdev_cache_mark_native_port':
                proto = public_mark
            if name in DSA_ONLY:
                body = '#if CONFIG_NET_DSA\n' + body + '\n#endif'
                proto = '#if CONFIG_NET_DSA\n' + proto + '\n#endif'
            if name == 'hppe_dev_init':
                body = '#ifdef HPPE\n' + body + '\n#endif'
                proto = '#ifdef HPPE\n' + proto + '\n#endif'
            definitions.append(body)
            prototypes.append(proto)
        result = template
        for key, value in {'ACTUAL_TYPES': actual_types, 'ACTUAL_PROTOTYPES': '\n'.join(prototypes),
                           'ACTUAL_GLOBALS': globals_, 'ACTUAL_FUNCTIONS': '\n\n'.join(definitions)}.items():
            require(result.count('@@' + key + '@@') == 1, 'template marker: ' + key)
            result = result.replace('@@' + key + '@@', value)
        require('@@' not in result, 'unresolved fixture marker')
        return result
    property_path = 'include/hsl/hsl_port_prop.h'
    property_enum = typedef((tree / property_path).read_text(), 'hsl_port_prop_t')
    save(dest / 'MANIFEST.json', {'functions': records, 'actual_types': types, 'constants': constants,
        'property_enum': {'path': property_path, 'sha256': sha(property_enum.encode()),
                          'declaration': property_enum, 'consumer': 'before actual port_info_t and checker; no handwritten property aliases'},
        'public_ready': {'path': 'include/init/ssdk_init.h', 'declaration': public_ready,
                         'sha256': sha(public_ready.encode()),
                         'consumer': 'native function-pointer initializer and type static assertion; not full kernel header/module link'},
        'public_mark': {'path': 'include/init/ssdk_init.h', 'declaration': public_mark,
                        'sha256': sha(public_mark.encode())},
        'limits': 'Native types; modeled net_device/PHY/DSA/private leaves, not kernel or target ABI. Full root init/exit not invoked.'})
    return bodies, render


# Each semantic negative is one exact source edit and a separately named scenario.
MUTANTS = [
    ('property-wrong-row', 'hsl_port_prop_check', 'property[p_type]', 'property[HSL_PP_INCL_CPU]', 'property-domain', 'PROPERTY_ROW_ISOLATION'),
    ('unregister-missing', 'ssdk_dev_event', '\t\tssdk_netdev_cache_unregister(dev);', '\t\t(void)dev;', 'normal', 'UNREGISTER_REFS'),
    ('one-cell-put', 'ssdk_netdev_cache_remove', '\twhile (n)\n\t\tdev_put(old[--n]);', '\tif (n)\n\t\tdev_put(old[--n]);', 'normal', 'UNREGISTER_REFS'),
    ('put-locked', 'ssdk_netdev_cache_remove', '\tspin_unlock_bh(&ssdk_netdev_cache_lock);\n\twhile (n)', '\twhile (n) dev_put(old[--n]);\n\tspin_unlock_bh(&ssdk_netdev_cache_lock);\n\twhile (n)', 'normal', 'PUT_UNDER_CACHE_LOCK'),
    ('duplicate-hold', 'ssdk_netdev_switch_init', '\tif (phyinfo->netdev[port_id] != dev) {', '\tif (true) {', 'duplicate', 'DUP_REGISTER_REF'),
    ('stale-primary', 'ssdk_netdev_cache_remove', '(stop || phyinfo->netdev[p] == dev)', '(stop || true)', 'replacement', 'STALE_EVENT_REPLACEMENT'),
    ('first-slot-only', 'ssdk_netdev_cache_remove', '\t\t\t\tssdk_netdev_names[d][p][0] = \'\\0\';', '\t\t\t\tssdk_netdev_names[d][p][0] = \'\\0\';\n\t\t\t\tbreak;', 'all-slots', 'MATCH_ALL_CELLS'),
    ('chip-before-retire', 'ssdk_dev_event', '\tif (event == NETDEV_UNREGISTER) {', '\tif (event == NETDEV_UNREGISTER) {\n\t\tchip_ver_get(0, &cfg);', 'identity-hw', 'HARDWARE_ON_RETIRE'),
    ('tombstone-fallback', 'ssdk_port_to_ifname_copy', '\tif (cached)', '\tif (cached > 0)', 'tombstone', 'LEGACY_AFTER_RETIRE'),
    ('forget-managed', 'ssdk_netdev_switch_init', 'ssdk_netdev_managed[dev_id][port_id] = true;', 'ssdk_netdev_managed[dev_id][port_id] = false;', 'tombstone', 'LEGACY_AFTER_RETIRE'),
    ('pin-unlocked', 'ssdk_switch_netdev_get', '\t\t\tdev_hold(dev);', '\t\t\tspin_unlock_bh(&ssdk_netdev_cache_lock);\n\t\t\tdev_hold(dev);\n\t\t\tspin_lock_bh(&ssdk_netdev_cache_lock);', 'reader', 'READ_PIN_AFTER_UNLOCK'),
    ('stop-accepting', 'ssdk_netdev_cache_remove', '\t\tssdk_netdev_cache_accepting = false;', '\t\tssdk_netdev_cache_accepting = true;', 'stop', 'STOP_NO_PUBLISH'),
    ('failed-replay-no-sweep', 'ssdk_netdev_notifier_register', '\t\tssdk_netdev_cache_stop();', '\t\t(void)0;', 'replay-fail-1', 'FAILED_REPLAY_CURRENT_LEAK'),
    ('unowned-unregister', 'ssdk_netdev_notifier_unregister', '\tif (ssdk_dev_notifier_owned) {', '\tif (true) {', 'replay-api-error', 'NOTIFIER_ACQUISITION_LEDGER'),
    ('g3-no-put', 'ssdk_ifname_to_port', '\tdev_put(eth_dev);', '\tif (eth_dev->phydev) dev_put(eth_dev);', 'g3-no-phy', 'G3_NO_PHY_PUT'),
    ('g3-postput', 'ssdk_ifname_to_port', '\tdev_put(eth_dev);\n\treturn port_id;', '\tdev_put(eth_dev);\n\tif (eth_dev->phydev) port_id = qca_ssdk_phydev_to_port(dev_id, eth_dev->phydev);\n\treturn port_id;', 'g3-success', 'PHY_MAP_AFTER_PUT'),
    ('dsa-no-put', 'ssdk_switch_enable_dsa', '\t\tdev_put(netdev);', '\t\t(void)netdev;', 'dsa', 'DSA_READER_BALANCE'),
    ('rename-switch-missing', 'ssdk_netdev_cache_rename', '\t\tif (sw->dev == dev)', '\t\tif (false && sw->dev == dev)', 'rename', 'SWITCH_RENAME'),
    ('ready-always', 'ssdk_netdev_cache_ready', '\tready = ssdk_netdev_cache_live;', '\tready = true;', 'normal', 'COLD_READY'),
    ('ready-never', 'ssdk_netdev_cache_ready', '\tready = ssdk_netdev_cache_live;', '\tready = false;', 'normal', 'LIVE_READY'),
    ('unknown-legacy-denied', 'ssdk_netdev_cache_name', '\tif (!ssdk_netdev_managed[dev_id][port_id]) {', '\tif (false) {', 'legacy', 'NAME_AVAILABLE'),
    ('duplicate-notifier', 'ssdk_netdev_notifier_register', '\tif (ssdk_dev_notifier_owned)\n\t\treturn;', '\t(void)0;', 'replay-success', 'NOTIFIER_DUPLICATE_OWNER'),
    ('sysfs-old-cast', 'ssdk_eth_switch_get', '&member_bmp);', '(fal_pbmp_t *)&netdev_switch->switch_port_bmp);', 'sysfs', 'FAL_OUTPUT_ALIGNMENT'),
    ('mark-no-bit', 'ssdk_netdev_cache_mark_native_port', 'ssdk_netdev_managed[dev_id][port_id] = true;', 'ssdk_netdev_managed[dev_id][port_id] = false;', 'mark-failed-register', 'LEGACY_AFTER_RETIRE'),
    ('mark-ignore-live', 'ssdk_netdev_cache_mark_native_port', 'if (ssdk_netdev_cache_live &&', 'if (true &&', 'mark-states', 'MARK_COLD'),
    ('mark-ignore-device', 'ssdk_netdev_cache_mark_native_port', 'if (dev_id != 0 ||', 'if (dev_id >= SW_MAX_NR_DEV ||', 'mark-reject', 'MARK_REJECT_DEVICE'),
    ('mark-ignore-chip', 'ssdk_netdev_cache_mark_native_port', 'hsl_get_current_chip_type(dev_id) == CHIP_HPPE', 'true', 'mark-reject', 'MARK_REJECT_CHIP'),
    ('mark-ignore-variant', 'ssdk_netdev_cache_mark_native_port', 'adpt_ppe_type_get(dev_id) == HPPE_TYPE', 'true', 'mark-reject', 'MARK_REJECT_VARIANT'),
    ('mark-ignore-init', 'ssdk_netdev_cache_mark_native_port', 'pdev && pdev->nr_ports &&', 'pdev &&', 'mark-reject', 'MARK_REJECT_UNINITIALIZED'),
    ('mark-ignore-cpu', 'ssdk_netdev_cache_mark_native_port', 'port_id != pdev->cpu_port_nr', 'true', 'mark-reject', 'MARK_REJECT_CPU'),
    ('mark-ignore-port-cap', 'ssdk_netdev_cache_mark_native_port', 'port_id > SSDK_PHYSICAL_PORT6', 'port_id >= SW_MAX_NR_PORT', 'mark-reject', 'MARK_REJECT_PORT'),
    ('mark-forget-stop', 'ssdk_netdev_cache_remove', '\tif (stop) {', '\tif (stop) {\n\t\tmemset(ssdk_netdev_managed, 0, sizeof(ssdk_netdev_managed));', 'mark-failed-register', 'LEGACY_AFTER_RETIRE'),
]


def positive_ok(record, case):
    return (not record['timeout'] and record['returncode'] == 0 and not record['stderr'] and
            record['stdout'] == ('PASS ' + case + '\n').encode())


def negative_ok(record, marker):
    return (not record['timeout'] and record['returncode'] == 86 and not record['stdout'] and
            record['stderr'] == ('SSDK_CACHE ' + marker + '\n').encode())


def oracle_controls():
    good = {'returncode': 86, 'stdout': b'', 'stderr': b'SSDK_CACHE marker\n', 'timeout': False}
    require(negative_ok(good, 'marker'), 'valid negative oracle')
    bad = [dict(good, returncode=x) for x in [0, 1, -11, 97, 98]]
    bad += [dict(good, stderr=x) for x in [b'', b'SSDK_CACHE wrong\n', good['stderr'] * 2,
            good['stderr'] + b'extra\n', good['stderr'] + b'AddressSanitizer: fault\n',
            good['stderr'] + b'runtime error: fault\n']]
    bad += [dict(good, stdout=b'noise'), dict(good, timeout=True)]
    require(all(not negative_ok(x, 'marker') for x in bad), 'negative oracle pollution')
    good_pos = {'returncode': 0, 'stdout': b'PASS normal\n', 'stderr': b'', 'timeout': False}
    require(positive_ok(good_pos, 'normal'), 'valid positive oracle')
    pos_bad = [dict(good_pos, stdout=x) for x in [b'', b'PASS other\n', b'PASS normal\nextra\n']]
    pos_bad += [dict(good_pos, stderr=b'noise'), dict(good_pos, timeout=True), dict(good_pos, returncode=86)]
    require(all(not positive_ok(x, 'normal') for x in pos_bad), 'positive oracle pollution')
    return {'valid_controls': 2, 'negative_pollution_rejected': len(bad), 'positive_pollution_rejected': len(pos_bad)}


def run(command, directory, label, env=None):
    timeout = False
    try:
        p = subprocess.run(command, capture_output=True, timeout=40, env=env)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as ex:
        timeout = True
        rc, out, err = None, ex.stdout or b'', ex.stderr or b''
    (directory / (label + '.stdout')).write_bytes(out)
    (directory / (label + '.stderr')).write_bytes(err)
    record = {'command': list(map(str, command)), 'returncode': rc, 'timeout': timeout,
              'stdout_sha256': sha(out), 'stderr_sha256': sha(err),
              'stdout_file': label + '.stdout', 'stderr_file': label + '.stderr'}
    actual_env = env if env is not None else os.environ
    record['runtime_environment'] = {key: actual_env[key] for key in ['ASAN_OPTIONS', 'UBSAN_OPTIONS'] if key in actual_env}
    save(directory / (label + '.json'), record)
    return dict(record, stdout=out, stderr=err)


def public(record):
    return {k: v for k, v in record.items() if k not in ['stdout', 'stderr']}


def source_gate_controls(tree, out):
    controls = [
        ('ready-prototype', 'include/init/ssdk_init.h', 'bool ssdk_netdev_cache_ready(void);',
         '/* removed */', 'ready prototype'),
        ('ready-export', 'src/init/ssdk_plat.c', 'EXPORT_SYMBOL(ssdk_netdev_cache_ready);',
         '/* removed */', 'ready export'),
        ('mark-prototype', 'include/init/ssdk_init.h',
         'bool ssdk_netdev_cache_mark_native_port(a_uint32_t dev_id, a_uint32_t port_id);', '/* removed */', 'mark prototype'),
        ('mark-export', 'src/init/ssdk_plat.c', 'EXPORT_SYMBOL(ssdk_netdev_cache_mark_native_port);',
         '/* removed */', 'mark export'),
        ('mark-hw-call', 'src/init/ssdk_plat.c', '\tbool marked = false;',
         '\tbool marked = false; hsl_port_prop_check(0, 1, HSL_PP_EXCL_CPU);', 'producer mark metadata-only calls'),
        ('fatal-policy', 'src/init/ssdk_init.c', '\t\tssdk_netdev_notifier_register();',
         '\t\trv = ssdk_netdev_notifier_register();', 'optional notifier policy'),
        ('raw-reader', 'src/init/ssdk_dts.c', '', '', 'direct cache access outside helper layer')
    ]
    # Minimal text-gate trees, NOT prepared source or executable candidates.
    required = ['src/init/ssdk_plat.c', 'src/init/ssdk_init.c', 'src/init/ssdk_dts.c',
                'src/ref/ref_fdb.c', 'include/init/ssdk_plat.h', 'include/init/ssdk_init.h']
    records = []
    for name, path, old, new, expected in controls:
        scope = out / ('gate-' + name)
        for relative in required:
            dest = scope / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / relative, dest)
        target = scope / path
        if name == 'raw-reader':
            target.write_text(target.read_text() + '\nvoid raw_reader(void) { netdev_switch->dev = NULL; }\n')
        else:
            target.write_text(once(target.read_text(), old, new))
        reason = None
        try:
            source_gate(scope)
        except RuntimeError as error:
            reason = str(error)
        require(reason == expected, 'text gate control: ' + name + ': ' + str(reason))
        records.append({'name': name, 'expected_reason': expected, 'actual_reason': reason})
    return records


def sanitizer_canaries(cc, flags, out, env):
    cases = [
        ('asan-uaf', '#include <stdlib.h>\nint main(void) { volatile int *p = malloc(sizeof(int)); *p = 3; free((void *)p); return *p; }\n', b'AddressSanitizer: heap-use-after-free', 97),
        ('ubsan-overflow', '#include <limits.h>\nint main(void) { volatile int x = INT_MAX; return x + 1; }\n', b'runtime error: signed integer overflow', 98),
    ]
    records = []
    for name, text, diagnostic, expected_exit in cases:
        src = out / (name + '.c')
        src.write_text(text)
        binary = out / name
        comp = run([cc, *flags, str(src), '-o', str(binary)], out, 'compile-canary-' + name)
        require(comp['returncode'] == 0 and not comp['stdout'] and not comp['stderr'], 'canary compile: ' + name)
        canary_env = dict(env)
        canary_env['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=' + str(expected_exit)
        canary_env['UBSAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode=' + str(expected_exit)
        rec = run([str(binary)], out, 'run-canary-' + name, canary_env)
        require(not rec['timeout'] and rec['returncode'] == expected_exit and
                not rec['stdout'] and diagnostic in rec['stderr'], 'expected sanitizer activation: ' + name)
        require(not negative_ok(rec, 'EXAMPLE'), 'sanitizer cannot be semantic negative')
        records.append({'name': name, 'compile': public(comp), 'run': public(rec),
                        'expected_diagnostic': diagnostic.decode(), 'expected_exitcode': expected_exit, 'semantic_pass': False})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(source.AUDIT) and out.name.startswith('SSDK-CACHE-ADOPT-') and
            not out.exists(), 'fresh owned-prefix output required')
    require(sha(PATCH.read_bytes()) == FROZEN_030, '030 freeze drift')
    require(sha((PATCH.parent / '029-ssdk-fdb-retirement.patch').read_bytes()) == FROZEN_029, '029 freeze drift')
    out.mkdir()
    assets = [HERE, FIX / 'host-fixture.c', FIX / 'README.md']
    bound = {str(p): sha(p.read_bytes()) for p in assets}
    result = {'status': 'INCOMPLETE', 'role': 'AUTHOR_NOT_INDEPENDENT_REVIEW',
              'qualification': 'BOUNDED_NATIVE_ALLOCATION_VALUE_MODEL_ONLY',
              'source030_sha256': FROZEN_030, 'baseline029_sha256': FROZEN_029,
              'assets': bound, 'sanitize': args.sanitize, 'compiles': [], 'positive_runs': [], 'mutants': []}
    report = out / 'RESULT.json'
    save(report, result)
    try:
        tree, prepared = source.prepare(args.upstream_cache, out / 'source')
        require(len(prepared['patches']) == 18 and len(prepared['prepared_files']) == 692, '18-layer inventory')
        result['source_gate'] = source_gate(tree)
        result['text_gate_controls'] = source_gate_controls(tree, out)
        result['oracle_controls'] = oracle_controls()
        bodies, render = extract(tree, out / 'actual')
        candidate = render(bodies)
        generated = out / 'candidate.c'
        generated.write_text(candidate)
        result['generated_sha256'] = sha(candidate.encode())
        identity = run([args.cc, '--version'], out, 'compiler-identity')
        require(identity['returncode'] == 0 and not identity['stderr'], 'compiler identity failed')
        result['compiler'] = public(identity)
        flags = ['-std=gnu11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
                 '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter']
        env = dict(os.environ)
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            env['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
            env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        result['runtime_environment'] = {k: env[k] for k in ['ASAN_OPTIONS', 'UBSAN_OPTIONS'] if k in env}
        for profile, defines in PROFILES.items():
            binary = out / profile
            compiled = run([args.cc, *flags, *defines, str(generated), '-o', str(binary)], out, 'compile-' + profile)
            result['compiles'].append(public(compiled))
            require(compiled['returncode'] == 0 and not compiled['stdout'] and not compiled['stderr'],
                    'candidate compile: ' + profile)
            for case in CASES:
                rec = run([str(binary), case], out, profile + '-' + case, env)
                result['positive_runs'].append({'profile': profile, 'case': case, **public(rec)})
                save(report, result)
                require(positive_ok(rec, case), 'positive runtime: ' + profile + '/' + case)
        for name, function_name, old, new, case, marker in MUTANTS:
            modified = dict(bodies)
            modified[function_name] = once(modified[function_name], old, new)
            mutated = out / ('mutant-' + name + '.c')
            text = render(modified)
            mutated.write_text(text)
            binary = out / ('mutant-' + name)
            compiled = run([args.cc, *flags, *PROFILES['hppe-dsa'], str(mutated), '-o', str(binary)], out, 'compile-mutant-' + name)
            result['compiles'].append(public(compiled))
            save(report, result)
            require(compiled['returncode'] == 0 and not compiled['stdout'] and not compiled['stderr'], 'mutant compile: ' + name)
            rec = run([str(binary), case], out, 'run-mutant-' + name, env)
            result['mutants'].append({'name': name, 'function': function_name, 'case': case,
                'marker': marker, 'source_sha256': sha(text.encode()), **public(rec)})
            save(report, result)
            require(negative_ok(rec, marker), 'semantic mutant: ' + name)
        # Recreate the old enum/layout projection as a separately labeled model control.
        property_enum = typedef((tree / 'include/hsl/hsl_port_prop.h').read_text(), 'hsl_port_prop_t')
        projected = once(candidate, property_enum,
                         property_enum + '\n#define HSL_PP_EXCL_CPU 1\n#define HSL_PP_BUTT 2\n')
        projection_src = out / 'old-property-projection.c'
        projection_src.write_text(projected)
        projection_bin = out / 'old-property-projection'
        compiled = run([args.cc, *flags, *PROFILES['hppe-dsa'], str(projection_src), '-o',
                        str(projection_bin)], out, 'compile-old-property-projection')
        require(compiled['returncode'] == 0 and not compiled['stdout'] and not compiled['stderr'],
                'old property projection must compile cleanly')
        rec = run([str(projection_bin), 'property-domain'], out, 'run-old-property-projection', env)
        require(negative_ok(rec, 'PROPERTY_ENUM_DOMAIN'), 'old property projection must fail exact domain')
        result['property_projection_control'] = {'classification': 'TEST_MODEL_NEGATIVE_NOT_PRODUCTION_MUTANT',
            'compile': public(compiled), 'run': public(rec), 'marker': 'PROPERTY_ENUM_DOMAIN',
            'source_sha256': sha(projected.encode())}
        result['expected_sanitizer_failures'] = sanitizer_canaries(args.cc, flags, out, env) if args.sanitize else []
        result['input_stability'] = source.check_stable_inputs(out / 'source', prepared)
        require(all(sha(Path(p).read_bytes()) == h for p, h in bound.items()), 'owned asset drift')
        result['evidence_files'] = {str(p.relative_to(out)): sha(p.read_bytes()) for p in sorted(out.rglob('*'))
                                    if p.is_file() and p != report and 'source/prepared/' not in str(p.relative_to(out))}
        result['status'] = 'PASS_G1_G3_NATIVE_MODEL_ONLY'
        result['totals'] = {'candidate_compiles': len(PROFILES), 'positive_runs': len(PROFILES) * len(CASES),
                            'semantic_mutants': len(MUTANTS), 'actual_definitions': sum(map(len, GROUPS.values()))}
        save(report, result)
        print(json.dumps({'status': result['status'], **result['totals']}))
    except BaseException as error:
        result['status'] = 'FAIL'
        result['error'] = str(error)
        save(report, result)
        raise


if __name__ == '__main__':
    main()
