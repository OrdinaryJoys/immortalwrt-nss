#!/usr/bin/env python3
"""Fault-test actual AHB provider owners with APIs modeled, not a kernel build."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prepared', type=Path)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
cc = shutil.which('cc')
if not cc:
    raise SystemExit('host C compiler required')
assets = {p: p.read_bytes() for p in (Path(__file__), HERE / 'ath11k-ahb-irq/host-fixture.c',
    HERE / 'ath11k-ahb-irq/provider-stubs.c', HERE / 'ath11k-ahb-irq/provider-cases.c',
    HERE / 'nss-dp-containment/extract_prepared_c.py')}


def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after, 1)


def variable(text, name):
    matches = list(re.finditer(r'^(?:static\s+)?const[^;=]+\b' + re.escape(name) + r'\b[^;=]*=\s*\{', extract.code_mask(text), re.M))
    assert len(matches) == 1, name
    match = matches[0]
    return text[match.start():extract.block_end(text, match.end() - 1)] + ';\n'


def generate(root):
    prepared = extract.Prepared(root)
    directory = 'drivers/net/wireless/ath/ath11k/'
    ahb = directory + 'ahb.c'
    hwh = directory + 'hw.h'
    hw = directory + 'hw.c'
    core = directory + 'core.h'
    text, hardware = prepared.read(ahb), prepared.read(hw)
    fixture = assets[HERE / 'ath11k-ahb-irq/host-fixture.c'].decode()
    fixture = replace_once(fixture, 'typedef uint32_t u32;', 'typedef uint32_t u32;\ntypedef uint16_t u16;\ntypedef uint64_t phys_addr_t;\n#define __iomem')
    fixture = replace_once(fixture, extract.structure(fixture, 'ath11k_ahb'),
                           prepared.structure(directory + 'ahb.h', 'ath11k_ahb'))
    fixture = replace_once(fixture, extract.structure(fixture, 'ath11k_hw_rev', 'enum'),
                           prepared.structure(core, 'ath11k_hw_rev', 'enum'))
    fixture = replace_once(fixture, 'struct ath11k_ahb ahb;', '''unsigned long dev_flags;
    void *mem; uint64_t mem_pa; size_t mem_len;
    struct { struct { const struct ath11k_msi_config *config; u32 addr_lo, addr_hi, ep_base_data; int irqs[64]; } msi; } pci;
    struct ath11k_ahb ahb;''')
    fixture = replace_once(fixture, 'DOMAIN_ALLOC, DOMAIN_ATTACH, MAP_MSA, MAP_CE };',
                           'DOMAIN_ALLOC, DOMAIN_ATTACH, MAP_MSA, MAP_CE, MSI_CONFIG, MSI_RESOURCE, MSI_MAP, MSI_PROPERTY };')
    fixture = replace_once(fixture, 'static void reset(bool nss, unsigned skip) {',
                           'static void provider_reset(void);\nstatic void reset(bool nss, unsigned skip) {\n    provider_reset();')
    fixture = replace_once(fixture, extract.function(fixture, 'ath11k_core_get_rproc'), '')
    fixture = replace_once(fixture, extract.function(fixture, 'ath11k_ahb_setup_resources'), '')
    fixture = replace_once(fixture, extract.function(fixture, 'ath11k_core_free'), '')
    fixture = replace_once(fixture, extract.function(fixture, 'rproc_put'), '')
    fixture = replace_once(fixture, extract.function(fixture, 'dma_unmap_resource'), '')
    fixture = replace_once(fixture, 'HOST_DRIVER_FUNCTIONS', assets[HERE / 'ath11k-ahb-irq/provider-stubs.c'].decode() +
                           '\n#define ath11k_core_free provider_core_free\nHOST_DRIVER_FUNCTIONS')
    fixture = replace_once(fixture, extract.function(fixture, 'main'), assets[HERE / 'ath11k-ahb-irq/provider-cases.c'].decode())
    declarations = '#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))\n'
    for header in (core, hwh, ahb):
        declarations += '\n'.join(re.findall(r'^#define\s+ATH11K_(?:IRQ_NUM_MAX|EXT_IRQ_NUM_MAX|EXT_IRQ_GRP_NUM_MAX|IRQ_CE0_OFFSET|INVALID_HW_MAC_ID)\s+[^\n]+', prepared.read(header), re.M)) + '\n'
    declarations += prepared.structure(hwh, 'ath11k_hw_ring_mask')
    declarations += '\n'.join(re.findall(r'^#define ATH11K_\w+RING_MASK_\d+[^\n]*', hardware, re.M)) + '\n'
    declarations += variable(hardware, 'ath11k_hw_ring_mask_ipq8074')
    for name in ('ath11k_msi_user', 'ath11k_msi_config'):
        declarations += prepared.structure(core, name)
    declarations += variable(text, 'irq_name') + prepared.structure(ahb, 'ext_irq_num', 'enum')
    declarations += prepared.function(hw, 'ath11k_hw_ipq8074_mac_from_pdev_id')
    fixture = replace_once(fixture, 'static struct ath11k_base base;',
                           variable(prepared.read(directory + 'pcic.c'), 'ath11k_msi_config') +
                           '\n#define ath11k_pcic_init_msi_config host_real_msi_config\n' +
                           prepared.function(directory + 'pcic.c', 'ath11k_pcic_init_msi_config') +
                           '\n#undef ath11k_pcic_init_msi_config\nstatic struct ath11k_base base;')
    names = ['ath11k_ahb_free_ext_irq_grp', 'ath11k_ahb_free_ext_irq', 'ath11k_ahb_free_ce_irqs',
             'ath11k_ahb_free_irq', 'ath11k_ahb_config_ext_irq', 'ath11k_ahb_config_irq',
             'ath11k_core_get_rproc']
    if 'static void ath11k_ahb_core_free(' in text:
        names.append('ath11k_ahb_core_free')
    names += ['ath11k_ahb_setup_msi_resources', 'ath11k_ahb_setup_resources',
              'ath11k_ahb_probe', 'ath11k_ahb_free_resources']
    functions = '#define ath11k_ahb_fw_resources_init host_fw_resources\n#define ath11k_ahb_fw_resource_deinit host_fw_deinit\n'
    functions += ''.join(prepared.function(ahb, name) for name in names)
    return fixture.replace('HOST_SOURCE_DECLARATIONS', declarations).replace('HOST_DRIVER_FUNCTIONS', functions), prepared


records = []
variants = [('candidate', args.prepared, True)]
if args.baseline:
    variants.append(('baseline', args.baseline, False))
if args.mutations:
    variants += [(name, args.prepared, False) for name in ('mutant-no-put', 'mutant-early-put', 'mutant-early-unmap',
        'mutant-zero-address', 'mutant-early-map-publish', 'mutant-probe-finalizer', 'mutant-remove-finalizer')]
for label, root, expected in variants:
    program, prepared = generate(root)
    if label == 'mutant-no-put':
        program = replace_once(program, '\t\trproc_put(rproc);', '\t\t(void)rproc;')
    elif label == 'mutant-early-put':
        program = replace_once(program, '\tath11k_core_free(ab);\n\tif (msi_addr_mapped)',
                               '\tif (rproc) rproc_put(rproc);\n\trproc = NULL;\n\tath11k_core_free(ab);\n\tif (msi_addr_mapped)')
    elif label == 'mutant-zero-address':
        program = replace_once(program, '\tif (msi_addr_mapped)\n', '\tif (msi_addr_mapped && msi_addr)\n')
    elif label == 'mutant-early-unmap':
        program = replace_once(program, '\tath11k_core_free(ab);\n\tif (msi_addr_mapped)',
                               '\tif (msi_addr_mapped) dma_unmap_resource(dev, msi_addr, PAGE_SIZE, DMA_FROM_DEVICE, 0);\n\tmsi_addr_mapped = false;\n\tath11k_core_free(ab);\n\tif (msi_addr_mapped)')
    elif label == 'mutant-early-map-publish':
        program = replace_once(program, '\tif (dma_mapping_error(ab->dev, msi_addr_iova))',
                               '\tab_ahb->msi_addr = msi_addr_iova;\n\tab_ahb->msi_addr_mapped = true;\n\tif (dma_mapping_error(ab->dev, msi_addr_iova))')
    elif label == 'mutant-probe-finalizer':
        program = replace_once(program, 'err_core_free:\n\tath11k_ahb_core_free(ab);', 'err_core_free:\n\tath11k_core_free(ab);')
    elif label == 'mutant-remove-finalizer':
        function = extract.function(program, 'ath11k_ahb_free_resources')
        program = replace_once(program, function, function.replace('ath11k_ahb_core_free(ab);', 'ath11k_core_free(ab);'))
    path = args.output / (label + '.c')
    path.write_text(program)
    command = [cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare', '-Wno-unused-parameter',
               '-Wno-unused-variable', '-Wno-unused-function', str(path), '-o', str(path.with_suffix('.host'))]
    if args.sanitize:
        command[1:1] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    result = subprocess.run(command, capture_output=True, timeout=45)
    (args.output / (label + '-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:
        raise SystemExit(result.stderr.decode())
    result = subprocess.run([str(path.with_suffix('.host'))], capture_output=True, timeout=45)
    (args.output / (label + '.stdout')).write_bytes(result.stdout)
    (args.output / (label + '.stderr')).write_bytes(result.stderr)
    if re.search(rb'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', result.stderr):
        raise SystemExit('sanitizer failure: ' + label)
    summary = json.loads(result.stdout)
    if (result.returncode == 0) != expected or (summary['failures'] == 0) != expected:
        raise SystemExit('unexpected assertions: ' + label + ' ' + result.stderr.decode())
    records.append(dict(label=label, expected_pass=expected, returncode=result.returncode, **summary,
        compile_command=command, generated_sha256=hashlib.sha256(program.encode()).hexdigest(), **prepared.manifest()))
for path, data in assets.items():
    assert path.read_bytes() == data
(args.output / 'RESULT.json').write_text(json.dumps(dict(results=records, sanitizer=args.sanitize,
    target_compiled=False, hardware_tested=False, full_qmi_teardown_tested=False,
    test_assets=[dict(path=str(path), sha256=hashlib.sha256(data).hexdigest()) for path, data in assets.items()]), indent=2) + '\n')
print(json.dumps([dict(label=x['label'], checks=x['checks'], failures=x['failures']) for x in records]))
