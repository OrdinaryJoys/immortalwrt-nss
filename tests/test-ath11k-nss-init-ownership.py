#!/usr/bin/env python3
"""Prepared NSS init plus pinned registry APIs; DMA/firmware/locks are modeled."""
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
parser.add_argument('--driver-prepared', type=Path, required=True)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cc', default='cc')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-nss-init-ownership/host-fixture.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}
driver = extract.Prepared(args.driver_prepared)
driver_header = driver.read('exports/nss_wifili_if.h')
driver_functions = ''.join(driver.function(path, symbol) for path, symbol in (
    ('nss_wifili.c', 'nss_wifili_release_external_if'),
    ('nss_wifili.c', 'nss_get_available_wifili_external_if'),
    ('nss_core.c', 'nss_core_register_subsys_dp'),
    ('nss_core.c', 'nss_core_unregister_subsys_dp'),
    ('nss_wifili.c', 'nss_wifili_get_context'),
    ('nss_wifili.c', 'nss_register_wifili_if'),
    ('nss_wifili.c', 'nss_unregister_wifili_if'),
    ('nss_cmn.c', 'nss_cmn_get_state')))
structures = ''.join(extract.structure(driver_header, symbol) for symbol in
    ('nss_wifili_tx_desc_init_msg', 'nss_wifili_tx_desc_addtnl_mem_msg'))
message_enum = extract.structure(driver_header, 'nss_wifili_msg_types', 'enum')
names = ['ATH11K_WIFIILI_MAX_TX_PROCESSQ', 'ATH11K_WIFILI_MAX_TX_DESC', 'ATH11K_WIFILI_DBDC_NUM_TX_DESC',
    'ATH11K_WIFILI_DBTC_NUM_TX_DESC', 'WIFILI_NSS_TX_DESC_SIZE', 'WIFILI_NSS_TX_EXT_DESC_SIZE',
    'WIFILI_NSS_TX_DESC_PAGE_LIMIT', 'WIFILI_NSS_MAX_MEM_PAGE_SIZE', 'WIFILI_NSS_MAX_EXT_MEM_PAGE_SIZE',
    'ATH11K_NSS_MAX_NUMBER_OF_PAGE', 'WIFILI_ADDTL_MEM_SEG_SET', 'WIFILI_MULTISOC_THREAD_MAP_ENABLE', 'ATH11K_WIFILI_TARGET_TYPE_UNKNOWN',
    'ATH11K_WIFILI_TARGET_TYPE_QCA8074V2', 'ATH11K_WIFILI_TARGET_TYPE_QCA6018',
    'ATH11K_WIFILI_TARGET_TYPE_QCN9074', 'ATH11K_WIFILI_TARGET_TYPE_QCA5018', 'ATH11K_WIFILI_TARGET_TYPE_QCN6122']
variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(v, args.prepared, False) for v in
        ('eager-readiness-reject', 'skip-post-reject-unregister', 'zero-dma-skipped', 'retain-metadata', 'forget-dma-free')]
records = []
for variant, root, expected in variants:
    tree = extract.Prepared(root)
    header = tree.read('drivers/net/wireless/ath/ath11k/nss.h')
    macros = []
    for name in names:
        matches = re.findall(r'^#define\s+' + re.escape(name) + r'\s+[^\n]+', header, re.M)
        assert len(matches) == 1, name
        macros += matches
    for name in ('NSS_WIFILI_MAX_NUMBER_OF_PAGE_MSG', 'NSS_WIFILI_MAX_NUMBER_OF_ADDTNL_SEG'):
        matches = re.findall(r'^#define\s+' + re.escape(name) + r'\s+[^\n]+', driver_header, re.M)
        assert len(matches) == 1, name
        macros += matches
    functions = ''.join(tree.function('drivers/net/wireless/ath/ath11k/nss.c', symbol) for symbol in
        ('ath11k_nss_tx_desc_mem_free', 'ath11k_nss_tx_desc_mem_alloc', 'ath11k_nss_get_tx_desc_limit',
         'ath11k_nss_fill_tx_desc_info', 'ath11k_nss_get_target_type', 'ath11k_nss_get_interface_type', 'ath11k_nss_init'))
    edits = {
        'eager-readiness-reject': ('\twlmsg = kzalloc(sizeof(struct nss_wifili_msg), GFP_ATOMIC);',
            '\tnss_contex = nss_wifili_get_context();\n\tif (nss_cmn_get_state(nss_contex) != NSS_STATE_INITIALIZED)\n'
            '\t\treturn -EINVAL;\n\twlmsg = kzalloc(sizeof(struct nss_wifili_msg), GFP_ATOMIC);'),
        'skip-post-reject-unregister': ('"nss state in default init state\\n");\n\t\tgoto unregister;',
            '"nss state in default init state\\n");\n\t\tgoto free;'),
        'zero-dma-skipped': ('if (ab->nss.tx_desc_vaddr[i])', 'if (ab->nss.tx_desc_vaddr[i] && ab->nss.tx_desc_paddr[i])'),
        'retain-metadata': ('\t\tab->nss.tx_desc_paddr[i] = 0;\n\t\tab->nss.tx_desc_size[i] = 0;\n', ''),
        'forget-dma-free': ('dma_free_coherent(ab->dev,', 'host_forget_dma_free(ab->dev,'),
    }
    if variant in edits:
        before, after = edits[variant]
        assert functions.count(before) == 1, variant
        functions = functions.replace(before, after, 1)
    prefix = ''
    fixture = assets[HERE / 'ath11k-nss-init-ownership/host-fixture.c'].decode()
    if variant == 'forget-dma-free':
        prefix = ('\nstatic void host_forget_dma_free(struct device *dev, size_t bytes, void *cpu, dma_addr_t dma)'
            ' { (void)dev; (void)bytes; (void)cpu; (void)dma; (void)dma_free_coherent; }\n')
    code = fixture.replace('HOST_CONSTANTS', '\n'.join(macros)).replace('HOST_TX_STRUCTURES', structures)
    code = code.replace('HOST_MESSAGE_ENUM', message_enum).replace('DRIVER_FUNCTIONS', driver_functions)
    code = code.replace('HOST_FUNCTIONS', prefix + functions)
    source = args.output / (variant + '.c')
    source.write_text(code)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror',
        '-Wno-error=sign-compare', '-Wno-error=pointer-sign', str(source), '-o', str(source.with_suffix('.host'))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / (variant + '-compile.stderr')).write_bytes(compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr.decode()
    ran = subprocess.run([str(source.with_suffix('.host'))], capture_output=True, timeout=120)
    (args.output / (variant + '.stdout')).write_bytes(ran.stdout)
    (args.output / (variant + '.stderr')).write_bytes(ran.stderr)
    assert not re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', ran.stderr)
    result = json.loads(ran.stdout)
    assert (ran.returncode == 0) == expected and (result['failures'] == 0) == expected, (variant, result)
    if variant == 'baseline':
        assert result['n01_failures'] and result['n02_failures']
    if variant in ('eager-readiness-reject', 'skip-post-reject-unregister'):
        assert result['n02_failures'] and not result['n01_failures']
    records.append(dict(variant=variant, expected_pass=expected, command=command,
        generated_sha256=hashlib.sha256(code.encode()).hexdigest(), **result, **tree.manifest()))
assert len({r['normal_signature'] for r in records}) == 1
assert all(p.read_bytes() == data for p, data in assets.items())
(args.output / 'RESULT.json').write_text(json.dumps(dict(records=records, driver=driver.manifest(),
    assets={str(p): hashlib.sha256(b).hexdigest() for p,b in assets.items()},
    scope='Seven full NSS functions, eight pinned driver ownership/state APIs. Non-descriptor struct layout, hardware IDs, DMA, locking and firmware are host contracts, not target ABI. Does not establish post-timeout DMA quiescence or callback draining.',
    hardware_accessed=False, target_compiled=False), indent=2) + '\n')
print(json.dumps([{k:r[k] for k in ('variant','scenarios','checks','failures','n01_failures','n02_failures')} for r in records]))
