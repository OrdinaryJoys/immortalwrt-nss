#!/usr/bin/env python3
"""Complete prepared MAC allocation/dump functions with explicit host contracts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--driver-prepared', type=Path, required=True)
parser.add_argument('--linux-list-header', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cc', default='cc')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-mesh-dump-ownership/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py', args.linux_list_header)}
linux = assets[args.linux_list_header].decode()


def macro(name):
    lines = linux.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if re.match(r'^#define\s+' + name + r'\b', line)]
    assert len(starts) == 1, name
    i, found = starts[0], []
    while True:
        found.append(lines[i])
        if not lines[i].rstrip().endswith('\\'):
            return ''.join(found)
        i += 1


list_functions = ''.join(extract.function(linux, name) for name in ('INIT_LIST_HEAD', '__list_add',
    'list_add_tail', '__list_del', '__list_del_entry', 'list_del', 'list_is_head', 'list_empty',
    '__list_splice', 'list_splice_tail', 'list_splice_tail_init'))
list_macros = ''.join(macro(name) for name in ('LIST_HEAD_INIT', 'LIST_HEAD', 'list_entry',
    'list_first_entry', 'list_next_entry', 'list_entry_is_head', 'list_for_each_entry_safe'))
driver = extract.Prepared(args.driver_prepared)
mesh_header = driver.read('exports/nss_wifi_mesh.h')
structures = ''.join(extract.structure(mesh_header, name) for name in
    ('nss_wifi_mesh_path_dump_entry', 'nss_wifi_mesh_proxy_path_dump_entry', 'nss_wifi_mesh_path_table_dump'))
variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants += [('baseline', args.baseline, False)]
if args.mutations:
    variants += [(name, args.prepared, False) for name in
        ('missing-lock-init', 'first-radio-only', 'retained-source-head', 'forgot-stale-free',
         'erase-fresh-after-unlock', 'reset-lock-on-recovery')]
records = []
for variant, root, expected in variants:
    tree = extract.Prepared(root)
    header = tree.read('drivers/net/wireless/ath/ath11k/nss.h')
    driver_structures = structures + ''.join(extract.structure(header, name) for name in
        ('ath11k_nss_mpath_entry', 'ath11k_nss_mpp_entry'))
    mac = ''.join(tree.function('drivers/net/wireless/ath/ath11k/mac.c', name)
                  for name in ('ath11k_mac_allocate', 'ath11k_mac_destroy'))
    nss = ''.join(tree.function('drivers/net/wireless/ath/ath11k/nss.c', name) for name in
        ('ath11k_nss_mesh_process_path_table_dump_msg', 'ath11k_nss_dump_mpath_request',
         'ath11k_nss_dump_mpp_request'))
    if variant in ('missing-lock-init', 'first-radio-only'):
        before = '\t\tspin_lock_init(&ar->nss.dump_lock);'
        assert mac.count(before) == 1
        mac = mac.replace(before, '' if variant == 'missing-lock-init' else '\t\tif (!i)\n' + before, 1)
    elif variant == 'reset-lock-on-recovery':
        before = '\tif (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags))'
        assert mac.count(before) == 1
        mac = mac.replace(before, '#ifdef CPTCFG_ATH11K_NSS_SUPPORT\n'
            '\tif (test_bit(ATH11K_FLAG_REGISTERED, &ab->dev_flags))\n'
            '\t\tspin_lock_init(&ab->pdevs[0].ar->nss.dump_lock);\n#endif\n' + before, 1)
    elif variant == 'retained-source-head':
        before = 'list_splice_tail_init(&nss->mpath_dump, &local_entry);'
        assert nss.count(before) == 1
        nss = nss.replace(before, 'list_splice_tail(&nss->mpath_dump, &local_entry);', 1)
    elif variant == 'forgot-stale-free':
        before = 'list_for_each_entry_safe(entry, tmp, &local_entry, list)\n\t\tkfree(entry);'
        assert nss.count(before) == 1
        nss = nss.replace(before, before.replace('kfree(entry)', 'host_forget_free(entry)'), 1)
    elif variant == 'erase-fresh-after-unlock':
        before = '\tarvif->nss.mpath_dump_num_entries = 0;\n\tspin_unlock_bh(&ar->nss.dump_lock);'
        assert nss.count(before) == 1
        nss = nss.replace(before, before + '\n\tINIT_LIST_HEAD(&nss->mpath_dump);', 1)
    code = assets[HERE / 'ath11k-mesh-dump-ownership/host-fixture.c'].decode()
    code = code.replace('HOST_LIST_FUNCTIONS', list_functions + list_macros)
    code = code.replace('HOST_STRUCTURES', driver_structures)
    code = code.replace('HOST_MAC_FUNCTIONS', mac).replace('HOST_NSS_FUNCTIONS', nss)
    source = args.output / (variant + '.c')
    source.write_text(code)
    for nss_on, mesh_on in ((0, 0), (1, 0), (1, 1)):
        for debug_on in (0, 1):
            mode = f'nss{nss_on}-mesh{mesh_on}-debug{debug_on}'
            binary = args.output / (variant + '-' + mode + '.host')
            command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-DHOST_NSS=' + str(nss_on), '-DHOST_MESH=' + str(mesh_on), '-DHOST_DEBUG=' + str(debug_on),
                str(source), '-o', str(binary)]
            if args.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            compiled = subprocess.run(command, capture_output=True, timeout=60)
            binary.with_suffix('.compile.stderr').write_bytes(compiled.stderr)
            assert compiled.returncode == 0, (variant, mode, compiled.stderr.decode())
            ran = subprocess.run([str(binary)], capture_output=True, timeout=60)
            binary.with_suffix('.stdout').write_bytes(ran.stdout)
            binary.with_suffix('.stderr').write_bytes(ran.stderr)
            assert not ran.stderr, (variant, mode, ran.stderr.decode())
            result = json.loads(ran.stdout)
            if expected:
                assert ran.returncode == 0 and result['failures'] == 0, (variant, mode, result)
            else:
                assert ran.returncode in (0, 1)
            records.append(dict(variant=variant, mode=mode, command=command,
                generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **result, **tree.manifest()))
for variant, _, expected in variants:
    rows = [r for r in records if r['variant'] == variant]
    if not expected:
        assert sum(r['failures'] for r in rows) > 0, variant
for mode in {r['mode'] for r in records}:
    assert len({r['normal_signature'] for r in records if r['mode'] == mode}) == 1, mode
assert all(p.read_bytes() == data for p, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records,
    driver=driver.manifest(), assets={str(p):hashlib.sha256(b).hexdigest() for p,b in assets.items()},
    scope='Five complete driver functions; eleven exact Linux list helpers and seven macros. Allocation, locks, firmware, structures other than dump payloads are host contracts. Controlled reply interleavings, not kernel concurrency or mesh runtime qualification.',
    hardware_accessed=False, target_compiled=False), indent=2) + '\n')
print(json.dumps([{ 'variant':v, 'scenarios':sum(r['scenarios'] for r in records if r['variant']==v),
    'checks':sum(r['checks'] for r in records if r['variant']==v),
    'failures':sum(r['failures'] for r in records if r['variant']==v)} for v,_,_ in variants]))
