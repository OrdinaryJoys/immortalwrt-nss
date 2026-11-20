"""42-layer (r3 SSDK + 054) root-init extraction, static gates and freeze witness.

Text preparation only: this module never invokes make, a compiler or the
network.  It reapplies the live reviewed patch inventory to the pinned
d9a19649 upstream archive (git archive from a local clone) and derives both the
41-layer base tree (no 054) and the 42-layer candidate tree (with 054) so that
every claimed layer fact is a function of repository bytes.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True

SOURCE = Path(__file__).resolve().parents[2]
PACKAGE = SOURCE / 'package/qca-nss/qca-ssdk'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
PATCH = '054-ssdk-root-init-retention.patch'
SUPPORT = SOURCE / 'tests/ssdk-root-init-retention'
ASSET_NAMES = ['README.md', 'fixture.c', 'source.py']
TOUCHED_FILES = {'src/init/ssdk_init.c'}
LAYERS = 42

# (name, definition preimage regex, emission role)
FUNCTIONS = [
    ('regi_init', r'static int __init regi_init\('),
    ('regi_exit', r'static void __exit\s+regi_exit\('),
    ('ssdk_init', r'sw_error_t\s+ssdk_init\('),
    ('ssdk_driver_register', r'static int ssdk_driver_register\('),
    ('ssdk_driver_unregister_owned', r'static void ssdk_driver_unregister_owned\('),
    ('ssdk_driver_unregister', r'static void ssdk_driver_unregister\('),
    ('ssdk_root_abort_unpublished', r'static void ssdk_root_abort_unpublished\('),
    ('qm_err_check_work_init', r'void qm_err_check_work_init\('),
    ('qm_err_check_work_start', r'void qm_err_check_work_start\('),
    ('qm_err_check_work_stop', r'void qm_err_check_work_stop\('),
    ('_qm_err_work_chip_check', r'static sw_error_t\s+_qm_err_work_chip_check\('),
    ('qca_mac_sw_sync_work_init', r'int\s+qca_mac_sw_sync_work_init\('),
    ('ssdk_mac_sw_sync_work_stop', r'sw_error_t\s+ssdk_mac_sw_sync_work_stop\('),
    ('_ssdk_mac_sw_sync_chip_check',
     r'static sw_error_t\s+_ssdk_mac_sw_sync_chip_check\('),
    ('ssdk_netdev_notifier_register',
     r'static void ssdk_netdev_notifier_register\('),
]
# Emitted into the host translation unit in this order (file line order used).
COMPILED = [name for name, _ in FUNCTIONS]

ROOT_BLOCK_START = '/* Root module-init context.'
ROOT_BLOCK_END = 'extern void qca_ar8327_sw_mac_polling_task'

# Functions modelled by the existing SSDK/DP suites; 054 may only change the
# first group, and only regi_init among them.
SUITE_MODELS = {
    'test-ssdk-root-exit-order.py': ['regi_exit'],
    'test-ssdk-root-lifecycle.py': ['ssdk_free_priv', 'ssdk_alloc_priv',
                                    'regi_init'],
    'test-ssdk-root-cleanup-errors.py': ['ssdk_cleanup'],
    'test-ssdk-dt-admission.py': ['ssdk_switch_device_num_init',
                                  'ssdk_switch_device_num_exit',
                                  'ssdk_switch_device_num_get', 'ssdk_dt_parse'],
    'test-ssdk-phy-prealloc.py': ['ssdk_alloc_priv', 'qca_ssdk_phy_info_prepare',
                                  'qca_ssdk_phy_info_publish'],
    'test-ssdk-netdev-cache.py': ['ssdk_netdev_cache_start',
                                  'ssdk_netdev_cache_commit',
                                  'ssdk_netdev_cache_stop',
                                  'ssdk_netdev_cache_ready'],
    'test-ssdk-retirement-admission.py': ['ssdk_cleanup',
                                          'ssdk_fdb_retire_controls'],
    'test-dp-init-retirement.py': [],
}
WITNESS_EXTRA_FILES = {
    'ssdk_free_priv': 'src/init/ssdk_init.c',
    'ssdk_alloc_priv': 'src/init/ssdk_init.c',
    'ssdk_cleanup': 'src/init/ssdk_init.c',
    'ssdk_fdb_retire_controls': 'src/init/ssdk_init.c',
    'ssdk_netdev_notifier_unregister': 'src/init/ssdk_init.c',
    'ssdk_switch_device_num_init': 'src/init/ssdk_dts.c',
    'ssdk_switch_device_num_exit': 'src/init/ssdk_dts.c',
    'ssdk_switch_device_num_get': 'src/init/ssdk_dts.c',
    'ssdk_dt_parse': 'src/init/ssdk_dts.c',
    'ssdk_netdev_cache_start': 'src/init/ssdk_plat.c',
    'ssdk_netdev_cache_commit': 'src/init/ssdk_plat.c',
    'ssdk_netdev_cache_stop': 'src/init/ssdk_plat.c',
    'ssdk_netdev_cache_ready': 'src/init/ssdk_plat.c',
    'ssdk_phy_driver_cleanup': 'src/hsl/phy/hsl_phy.c',
    'qca_ssdk_phy_info_prepare': 'src/hsl/phy/hsl_phy.c',
    'qca_ssdk_phy_info_publish': 'src/hsl/phy/hsl_phy.c',
}


def require(ok, marker):
    if not ok:
        raise AssertionError(marker)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def inventory(root):
    result = {}
    for path in sorted(Path(root).rglob('*')):
        require(not path.is_symlink(), 'SYMLINK')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def patch_inventory():
    return sorted((PACKAGE / 'patches').glob('*.patch'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def masked(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()),
                  text)


def block_end(text, start):
    mask = masked(text)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (mask[end] == '{') - (mask[end] == '}')
        end += 1
    return end


def function_body(text, name):
    pattern = r'(?m)^(?:static\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\s+)+(?:__init\s+|__exit\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, masked(text)))
    require(len(matches) == 1, 'FUNCTION_DEFINITION:' + name)
    start = matches[0].start()
    end = block_end(text, start)
    return text[start:end] + '\n', text.count('\n', 0, start) + 1


def function_anchored(text, name, prefix):
    matches = list(re.finditer(r'(?m)^' + prefix, masked(text)))
    require(len(matches) == 1, 'FUNCTION_PREFIX:' + name)
    start = matches[0].start()
    require(text[start:start + 400].count('(') >= 1, 'FUNCTION_SIGNATURE:' + name)
    end = block_end(text, start)
    return text[start:end] + '\n', text.count('\n', 0, start) + 1


def extract(tree, optional=False):
    tree = Path(tree)
    path = tree / 'src/init/ssdk_init.c'
    text = path.read_text()
    if ROOT_BLOCK_START in text:
        start = text.index(ROOT_BLOCK_START)
        end = text.index(ROOT_BLOCK_END)
        require(start < end, 'ROOT_BLOCK_ORDER')
        root_block = text[start:end].rstrip('\n') + '\n'
    else:
        root_block = ''
    bodies = {}
    for name, prefix in FUNCTIONS:
        try:
            body, line = function_anchored(text, name, prefix)
        except AssertionError:
            if optional:
                continue
            raise
        bodies[name] = {'body': body, 'line': line, 'sha256': digest(body.encode())}
    extras = {}
    for name, rel in WITNESS_EXTRA_FILES.items():
        other = (tree / rel).read_text()
        prefix = (r'(?:static\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\s+)+'
                  + re.escape(name) + r'\s*\(')
        try:
            body, line = function_anchored(other, name, prefix)
        except AssertionError:
            if optional:
                continue
            raise
        extras[name] = {'body': body, 'line': line,
                        'sha256': digest(body.encode()), 'path': rel}
    headers = {}
    for name in ['include/sal/os/aos_types.h', 'include/common/sw_error.h',
                 'include/common/sw_config.h', 'include/init/ssdk_init.h']:
        headers[name] = sha(tree / name)
    return {
        'tree': str(tree),
        'path': str(path),
        'text': text,
        'text_sha256': digest(text.encode()),
        'root_block': root_block,
        'root_block_sha256': digest(root_block.encode()),
        'functions': bodies,
        'extras': extras,
        'headers': headers,
        'regi_exit_sha256': bodies['regi_exit']['sha256'],
    }


def sdk_prelude(tree):
    """Real SDK scalar/error/capacity/register-mode declarations from the layer."""
    tree = Path(tree)
    aos = (tree / 'include/sal/os/aos_types.h').read_text()
    err = (tree / 'include/common/sw_error.h').read_text()
    cfg = (tree / 'include/common/sw_config.h').read_text()
    init = (tree / 'include/init/ssdk_init.h').read_text()

    def one(pattern, text, marker):
        found = re.findall(pattern, text, re.M)
        require(len(found) == 1, marker)
        return found[0]

    uint32 = one(r'^(typedef\s+__a_uint32_t\s+a_uint32_t;)', aos, 'A_UINT32')
    bool_t = one(r'(typedef enum\s*\{\s*A_FALSE,\s*A_TRUE\s*\}\s*a_bool_t;)', aos,
                 'A_BOOL')
    err_enum = one(r'(typedef enum\s*\{[^}]*\}\s*sw_error_t;)', err, 'SW_ERROR')
    max_dev = one(r'^(#define\s+SW_MAX_NR_DEV\s+\d+)', cfg, 'SW_MAX_NR_DEV')
    reg_mode = one(r'(typedef enum\s*\{[^}]*\}\s*hsl_reg_mode;)', init, 'HSL_REG_MODE')
    shared = (tree / 'include/common/shared_func.h').read_text()
    rtn_error = one(r'(#define SW_RTN_ON_ERROR\(rtn\) [\s\S]*?while\(0\);\n)',
                    shared, 'SW_RTN_ON_ERROR')
    rtn_null = one(r'(#define SW_RTN_ON_NULL\(op\) [\s\S]*?while\(0\);\n)',
                   shared, 'SW_RTN_ON_NULL')
    plat = (tree / 'include/init/ssdk_plat.h').read_text()
    qca_ver = one(r'(enum \{\s*QCA_VER_AR8216[\s\S]*?\};)', plat, 'QCA_VER')
    chip_type = one(r'(typedef enum\s*\{\s*CHIP_UNSPECIFIED[\s\S]*?\}\s*ssdk_chip_type;)',
                    init, 'SSDK_CHIP_TYPE')
    sdk_text = (tree / 'src/init/ssdk_init.c').read_text()
    work_delays = ''.join(one(r'^(#define %s\s+\d+)' % name, sdk_text, name) + '\n'
                          for name in ('QCA_QM_WORK_DELAY', 'QCA_MAC_SW_SYNC_WORK_DELAY'))
    return ('#include <stdint.h>\n'
            'typedef uint32_t __a_uint32_t;\n'
            + uint32 + '\n' + bool_t + '\n' + err_enum + '\n' + max_dev + '\n'
            + reg_mode + '\n' + rtn_error + rtn_null + qca_ver + '\n'
            + chip_type + '\n' + work_delays)


def _apply_patch(tree, path, derived):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from edma_patch_context import inspect_patch, verify_applied
    data = path.read_bytes()
    require(data.endswith(b'\n'), 'PATCH_FINAL_NEWLINE:' + path.name)
    expected, contexts = inspect_patch(tree, data)
    for name, context in contexts.items():
        require(context['before_sha256'] == derived.get(name),
                'PATCH_PREIMAGE:' + path.name + ':' + name)
        require(context['after_sha256'] is not None, 'PATCH_POSTIMAGE:' + name)
        require(all(h['offset'] == 0 and h['full_context']
                    for h in context['hunks']), 'PATCH_CONTEXT:' + name)
    process = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-V', 'none'],
                             input=data, cwd=tree, capture_output=True, timeout=120)
    require(process.returncode == 0 and not process.stderr, 'PATCH_TOOL:' + path.name)
    require(not re.search(rb'fuzz|offset|FAILED|reject|malformed|Reversed|previously applied',
                          process.stdout, re.I), 'PATCH_SHIFT:' + path.name)
    verify_applied(tree, expected)
    derived.update({name: digest(raw) for name, raw in expected.items()})
    return digest(data)


def _prepare_layer(archive, output, patches):
    tree = output / 'prepared'
    tree.mkdir()
    derived = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and
                    '.git' not in name.parts, 'ARCHIVE_MEMBER:' + member.name)
            require(member.isfile() or member.isdir(), 'ARCHIVE_TYPE:' + member.name)
            destination = tree / str(name)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(member).read()
                require(str(name) not in derived, 'ARCHIVE_DUPLICATE:' + member.name)
                derived[str(name)] = digest(data)
                destination.write_bytes(data)
    require(inventory(tree) == derived, 'ARCHIVE_INVENTORY')
    entries = []
    for path in patches:
        entry = {'name': path.name, 'sha256': _apply_patch(tree, path, derived),
                 'status': 'PASS_DECLARED_CONTEXT_AND_OUTPUT'}
        entries.append(entry)
    require(not list(tree.rglob('*.orig')) and not list(tree.rglob('*.rej')),
            'REPLAY_BACKUPS')
    require(inventory(tree) == derived, 'PREPARED_INVENTORY')
    write_json(output / 'RESULTS.json', {
        'status': 'PASS_TEXT_ONLY', 'pin': PIN,
        'archive_sha256': digest(archive), 'patches': entries,
        'prepared_files': derived,
        'qualification': 'TEXT_ONLY_NO_BUILD_NO_TARGET_COMPILE',
        'live_patch_inventory': [p.name for p in patch_inventory()],
    })
    return tree, {'patches': entries, 'prepared_files': derived,
                  'archive_sha256': digest(archive)}


def prepare(upstream_cache, output):
    """Build 41-layer base and 42-layer candidate trees under a fresh output."""
    output = Path(output).resolve()
    require(output.is_relative_to(Path('/tmp')) or not output.exists(),
            'FRESH_OUTPUT')
    require(not output.exists(), 'FRESH_OUTPUT')
    output.mkdir(parents=True)
    patches = patch_inventory()
    require(len(patches) == LAYERS, 'PATCH_LAYER_COUNT')
    require(all(re.fullmatch(r'\d{3}-.+\.patch', p.name) for p in patches),
            'PATCH_NAMES')
    require([p.name for p in patches] == [p.name for p in sorted(patches)],
            'PATCH_ORDER')
    require(patches[-1].name == PATCH, 'PATCH_054_LAST')
    require(re.search(r'^PKG_SOURCE_VERSION:=' + PIN + r'\s*$',
                      (PACKAGE / 'Makefile').read_text(), re.M), 'SSDK_PIN')
    process = subprocess.run(['git', '-C', str(upstream_cache), 'archive',
                              '--format=tar', PIN], capture_output=True,
                             timeout=180)
    require(process.returncode == 0 and not process.stderr, 'UPSTREAM_ARCHIVE')
    archive = process.stdout
    (output / 'upstream.tar').write_bytes(archive)
    base = output / 'base41'
    candidate = output / 'candidate42'
    base.mkdir()
    candidate.mkdir()
    base_tree, base_data = _prepare_layer(archive, base, patches[:-1])
    cand_tree, cand_data = _prepare_layer(archive, candidate, patches)
    require(set(cand_data['prepared_files']) == set(base_data['prepared_files']),
            'LAYER_FILE_SET')
    changed = {name for name in cand_data['prepared_files']
               if cand_data['prepared_files'][name] != base_data['prepared_files'][name]}
    require(changed == TOUCHED_FILES, 'TOUCHED_FILES:' + repr(sorted(changed)))
    require(len(cand_data['patches']) == LAYERS, 'CANDIDATE_LAYER_COUNT')
    require(len(base_data['patches']) == LAYERS - 1, 'BASE_LAYER_COUNT')
    result = {
        'pin': PIN,
        'layers': {'base41': base_data, 'candidate42': cand_data},
        'changed_files': sorted(changed),
        'base_tree': str(base_tree),
        'candidate_tree': str(cand_tree),
        'candidate_extract': extract(cand_tree)['functions'],
        'base_regi_exit_sha256': extract(base_tree, optional=True)['regi_exit_sha256'],
    }
    write_json(output / 'PREPARE.json', {
        'pin': PIN, 'changed_files': sorted(changed),
        'candidate_patches': [p['name'] for p in cand_data['patches']],
        'candidate_patch_sha256': [p['sha256'] for p in cand_data['patches']],
        'base_patch_count': len(base_data['patches']),
        'candidate_patch_count': len(cand_data['patches']),
        'prepared_files': len(cand_data['prepared_files']),
        'base_tree': str(base_tree), 'candidate_tree': str(cand_tree),
    })
    return base_tree, cand_tree, result


# ---------------------------------------------------------------------------
# Static gates: the retention contract must be visible in the source itself.
# ---------------------------------------------------------------------------

def _between(text, start, end):
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def gates(tree, base_tree):
    """Return {gate: {'status': 'PASS'|'FAIL', 'detail': ...}} for 054."""
    candidate = extract(tree)
    base = extract(base_tree, optional=True)
    text = candidate['text']
    regi = candidate['functions']['regi_init']['body']
    root = candidate['root_block']
    abort = candidate['functions']['ssdk_root_abort_unpublished']['body']
    errno_fn = _between(root, 'static int ssdk_root_errno(', '\n}\n')
    notifier = candidate['functions']['ssdk_netdev_notifier_register']['body']
    driver_reg = candidate['functions']['ssdk_driver_register']['body']
    driver_unreg = candidate['functions']['ssdk_driver_unregister']['body'] + \
        candidate['functions']['ssdk_driver_unregister_owned']['body']
    work_stop_mac = candidate['functions']['ssdk_mac_sw_sync_work_stop']['body']
    work_stop_qm = candidate['functions']['qm_err_check_work_stop']['body']
    work_init_mac = candidate['functions']['qca_mac_sw_sync_work_init']['body']
    work_init_qm = candidate['functions']['qm_err_check_work_init']['body']
    ssdk_init_fn = candidate['functions']['ssdk_init']['body']
    out_block = _between(regi, 'out:\n', 'abort:\n')
    retain_block = _between(regi, 'retain:\n', 'out:\n')
    post_pub = _between(regi, 'ssdk_root.published = A_TRUE;', 'switch (cfg.chip_type)')

    def check(ok, detail):
        return {'status': 'PASS' if ok else 'FAIL', 'detail': detail}

    result = {}
    result['touched_files'] = check(
        set(json.loads((Path(tree).parent / 'PREPARE.json').read_text())['changed_files']) == TOUCHED_FILES
        if (Path(tree).parent / 'PREPARE.json').exists() else True,
        'only src/init/ssdk_init.c changes')
    result['regi_exit_unchanged'] = check(
        candidate['regi_exit_sha256'] == base['regi_exit_sha256'],
        'regi_exit body identical to 41-layer')
    masked_regi = masked(regi)
    result['enodev_single'] = check(
        len(re.findall(r'-ENODEV', masked_regi)) == 1 and
        re.search(r'rv = chip_ver_get\(dev_id, &cfg\);\n\t\tif \(rv == -ENODEV\)',
                  masked_regi),
        'only chip_ver_get interprets -ENODEV')
    result['enodev_stage_errors'] = check(
        not re.search(r'SV_CNTU_ON_ERROR|SW_CNTU_ON_ERROR', regi) and
        not re.search(r'if \(rv == -ENODEV\)\s*\n\s*continue;', regi.replace(
            'rv = chip_ver_get(dev_id, &cfg);\n\t\tif (rv == -ENODEV)', 'CHIP_SENTINEL')),
        'no stage error is turned into a no-device continue')
    result['postpub_no_free'] = check(
        'ssdk_free_priv' not in post_pub and 'ssdk_free_priv' not in retain_block and
        'return rv' not in post_pub,
        'post-publication path neither frees priv nor returns rv')
    result['retention_return_zero'] = check(
        re.search(r'if \(ssdk_root\.first_err != SW_OK\) \{[\s\S]*?return 0;', out_block) and
        'module stays resident' in retain_block,
        'retained init returns 0 with a retained banner')
    result['cache_gate'] = check(
        re.search(r'if \(ssdk_root\.first_err == SW_OK &&[ \t\n]*'
                  r'ssdk_root\.dev_initialized > 0\)\n?\s*'
                  r'ssdk_netdev_notifier_register\(\);', out_block) and
        masked(out_block).count('ssdk_netdev_notifier_register()') == 1,
        'cache commits only for first_err clear and >0 initialized devices')
    result['cache_degraded_log'] = check(
        'no admitted switch device; netdev cache not started; qca-nss-dp will refuse'
        in out_block or 'netdev cache withheld; qca-nss-dp will refuse' in retain_block,
        'zero-device/degraded cache refusal is explicit')
    result['errno_map'] = check(
        all(needle in errno_fn for needle in [
            'case SW_NOT_SUPPORTED:\n\t\t\treturn -EOPNOTSUPP;',
            'case SW_OUT_OF_MEM:\n\t\t\treturn -ENOMEM;',
            'case SW_ALREADY_EXIST:\n\t\t\treturn -EEXIST;',
            'case SW_BUSY:\n\t\t\treturn -EBUSY;',
            'case SW_BAD_VALUE:', 'default:\n\t\t\treturn -EIO;']) and
        'return rv == -ENODEV ? -EIO : rv;' in errno_fn and
        'return -ENODEV;' not in errno_fn,
        'explicit SSDK->errno map; -ENODEV stays the chip sentinel only')
    result['plat_domain'] = check(
        'err == SW_FAIL ? SSDK_ROOT_DOMAIN_SW : SSDK_ROOT_DOMAIN_LINUX' in root and
        'ssdk_root_plat_domain(rv)' in regi,
        'ssdk_plat_init SW_FAIL maps to an SSDK-domain honest errno')
    result['abort_order'] = check(
        abort.index('ssdk_driver_unregister_owned()') <
        abort.index('ssdk_phy_driver_cleanup(dev_id)') <
        abort.index('ssdk_plat_exit(dev_id)') <
        abort.index('ssdk_free_priv()'),
        'driver -> phy metadata -> platform -> private/topology')
    result['abort_scoped_by_stage'] = check(
        re.search(r'if \(ssdk_root\.dev_stage\[dev_id\] >= SSDK_ROOT_STAGE_PLAT\)\n\s*ssdk_plat_exit\(dev_id\);',
                  abort) and
        regi.count('ssdk_root_stage_set(') >= 6,
        'dev_stage[] scopes platform unwinding and the stage context is recorded')
    result['stage_read'] = check(
        candidate['text'].count('ssdk_root_stage_name(ssdk_root.stage)') == 2 and
        'ssdk_root_stage_name' in root,
        'stage name is read back in both retained/aborted banners')
    result['abort_honest_errno'] = check(
        'return ssdk_root_errno(ssdk_root.first_err, ssdk_root.first_domain);' in regi,
        'abort return is a mapped errno, not raw rv')
    result['driver_module_wide'] = check(
        text.count('platform_driver_register(&ssdk_driver)') == 1 and
        text.count('platform_driver_unregister(&ssdk_driver)') == 1 and
        'if (ssdk_driver_owned)\n\t\treturn 0;' in driver_reg and
        'ssdk_driver_unregister_owned()' in driver_unreg,
        'platform driver publication is module-wide and owned once')
    result['fal_first_error'] = check(
        re.search(r'rv = fal_init\(dev_id, cfg\);\n\tif \(rv != SW_OK\) \{\n\t\tSSDK_ERROR\("ssdk fal init failed: %d\. \\r\\n", rv\);\n\t\treturn rv;\n\t\}',
                  ssdk_init_fn) is not None and
        'ssdk_phy_driver_init(dev_id)' in ssdk_init_fn,
        'FAL first error is preserved and PHY is not attempted after it')
    result['hppe_capture'] = check(
        'rv = qca_hppe_hw_init(dev_id);' in regi and
        not re.search(r'(?<!rv = )\bqca_hppe_hw_init\(dev_id\);', regi),
        'HPPE return is a required stage result')
    result['hppe_gate'] = check(
        re.search(r'rv = qca_hppe_hw_init\(dev_id\);\n\t+if \(rv != SW_OK\) \{[\s\S]*?goto retain;',
                  regi) is not None,
        'HPPE failure is latched and retained before switch registration')
    result['sysfs_nonfatal'] = check(
        'sysfs diagnostic plane degraded' in out_block and
        not re.search(r'if \(rv\)\s*\n\s*(?:return|goto)', out_block),
        'sysfs failure is logged and never fatal')
    result['genl_nonfatal'] = check(
        'genl diagnostic plane degraded' in out_block and
        not re.search(r'ssdk_genl_deinit', out_block),
        'genl failure is logged, not fatal, and not double-deinitialized here')
    result['notifier_contract'] = check(
        'netdev cache contract violation' in notifier and
        'qca-nss-dp will refuse' in notifier and
        'optional netdev notifier' not in notifier and
        'netdev cache not live' in out_block,
        'notifier failure names the qca-nss-dp cache contract and the '
        'final module-init status reports the degraded cache')
    result['work_guard_mac'] = check(
        'ssdk_mac_sw_sync_work_initialized[priv->device_id]' in work_stop_mac and
        'ssdk_mac_sw_sync_work_initialized[priv->device_id] = true;' in work_init_mac,
        'MAC sw-sync stop skips a work item whose init never ran')
    result['work_guard_qm'] = check(
        'ssdk_qm_err_check_work_initialized[priv->device_id]' in work_stop_qm and
        'ssdk_qm_err_check_work_initialized[priv->device_id] = true;' in work_init_qm,
        'QM error-check stop skips a work item whose init never ran')
    result['retained_state_unload_contract'] = check(
        'module_exit()' in root and 'retention' in root.lower() and
        'fdb_work_initialized' in (Path(tree) / 'src/init/ssdk_init.c').read_text() and
        'mib_work_initialized' in (Path(tree) / 'src/init/ssdk_init.c').read_text() and
        'intr_work_initialized' in (Path(tree) / 'src/init/ssdk_interrupt.c').read_text(),
        'retained-state exit contract documented; producer stop guards present')
    result['failed_gates'] = check(
        all(value['status'] == 'PASS' for key, value in result.items()
            if isinstance(value, dict)),
        'no static gate failed')
    return result


# Text mutations used only to prove every static gate can fail (non-vacuous).
def gate_controls(tree, base_tree):
    text = extract(tree)['text']
    controls = []

    import shutil

    def control(name, gate, mutate):
        mutated = mutate(text)
        if mutated is None or mutated == text:
            return
        scratch = Path('/tmp') / ('gate-control-' + name)
        if scratch.exists():
            shutil.rmtree(scratch)
        shutil.copytree(Path(tree), scratch)
        (scratch / 'src/init/ssdk_init.c').write_text(mutated)
        controls.append({'control': name, 'gate': gate,
                         'status': 'PASS' if _gate_fails(gate, scratch, tree) else 'FAIL'})

    def replace_once(old, new):
        def mutate(text):
            return text.replace(old, new, 1) if old in text else None
        return mutate

    control('notifier-final-status', 'notifier_contract', replace_once(
        'netdev cache not live', 'netdev cache nominal'))
    control('notifier-reverted', 'notifier_contract', replace_once(
        'qca-ssdk netdev cache contract violation: netdev notifier registration failed',
        'optional netdev notifier registration failed'))
    control('cache-gate-relaxed', 'cache_gate', replace_once(
        'ssdk_root.first_err == SW_OK && ssdk_root.dev_initialized > 0',
        'ssdk_root.dev_initialized > 0'))
    control('cache-first-error-dropped', 'cache_gate', replace_once(
        'ssdk_root.first_err == SW_OK && ssdk_root.dev_initialized > 0',
        'ssdk_root.dev_initialized > 0 || ssdk_root.first_err == SW_OK'))
    control('hppe-ignored', 'hppe_capture', replace_once(
        'rv = qca_hppe_hw_init(dev_id);', 'qca_hppe_hw_init(dev_id);'))
    control('stage-unread', 'abort_scoped_by_stage', replace_once(
        'if (ssdk_root.dev_stage[dev_id] >= SSDK_ROOT_STAGE_PLAT)',
        'if (dev_id < dev_num)'))
    control('postpub-frees', 'postpub_no_free', replace_once(
        'ssdk_root.published = A_TRUE;',
        'ssdk_root.published = A_TRUE;\n\t\tssdk_free_priv();'))
    control('macro-reintroduced', 'enodev_stage_errors', replace_once(
        'rv = ssdk_plat_init(&cfg, dev_id);',
        'rv = ssdk_plat_init(&cfg, dev_id);\n\t\tSW_CNTU_ON_ERROR_AND_COND1_OR_GOTO_OUT(rv, -ENODEV);'))
    control('errno-guard-removed', 'errno_map', replace_once(
        'return rv == -ENODEV ? -EIO : rv;', 'return rv;'))
    control('errno-enodev', 'errno_map', replace_once(
        'case SW_NOT_SUPPORTED:\n\t\t\treturn -EOPNOTSUPP;',
        'case SW_NOT_SUPPORTED:\n\t\t\treturn -ENODEV;'))
    control('abort-unowned', 'abort_order', replace_once(
        '\tssdk_driver_unregister_owned();\n\tfor (dev_id',
        '\tssdk_driver_unregister(0);\n\tfor (dev_id'))
    control('mac-guard-removed', 'work_guard_mac', replace_once(
        '!ssdk_mac_sw_sync_work_initialized[priv->device_id])',
        '!ssdk_mac_sw_sync_work_initialized[SW_MAX_NR_DEV - 1])'))
    control('qm-guard-removed', 'work_guard_qm', replace_once(
        '!ssdk_qm_err_check_work_initialized[priv->device_id])',
        '!ssdk_qm_err_check_work_initialized[SW_MAX_NR_DEV - 1])'))
    control('plat-domain-raw', 'plat_domain', replace_once(
        'return err == SW_FAIL ? SSDK_ROOT_DOMAIN_SW : SSDK_ROOT_DOMAIN_LINUX;',
        'return SSDK_ROOT_DOMAIN_LINUX;'))
    control('sysfs-fatal', 'sysfs_nonfatal', replace_once(
        'SSDK_ERROR("qca-%s sysfs diagnostic plane degraded (code: %d); control plane continues\\n",\n\t\t\t\t   SSDK_STR, rv);',
        'if (rv)\n\t\t\t\treturn rv;'))
    control('fal-continues', 'fal_first_error', replace_once(
        '\t\treturn rv;\n\t}',
        '\trv = SW_OK;\n\t}'))
    control('driver-double-register', 'driver_module_wide', replace_once(
        '\tif (ssdk_driver_owned)\n\t\treturn 0;\n\trv = platform_driver_register',
        '\trv = platform_driver_register'))
    require(all(c['status'] == 'PASS' for c in controls), 'GATE_CONTROL')
    return controls


def _gate_fails(gate, scratch, layer42):
    try:
        result = gates(scratch, layer42)
    except Exception:
        return True
    if gate == 'touched_files':
        return True
    if gate == 'regi_exit_unchanged':
        return True
    return result.get(gate, {'status': 'FAIL'})['status'] == 'FAIL'


# ---------------------------------------------------------------------------
# Freeze witness for the existing SSDK/DP suites (re-freeze is out of this
# patch's write scope; the witness supplies every value the re-freeze needs).
# ---------------------------------------------------------------------------

def witness(base_tree, cand_tree, prepared):
    base = extract(base_tree, optional=True)
    cand = extract(cand_tree)
    changed = sorted(name for name in cand['functions']
                     if cand['functions'][name]['sha256'] !=
                     base['functions'].get(name, {}).get('sha256'))
    changed_extra = sorted(name for name in cand['extras']
                           if cand['extras'][name]['sha256'] !=
                           base['extras'].get(name, {}).get('sha256'))
    impact = {}
    for suite, functions in SUITE_MODELS.items():
        hit = [name for name in functions if name in changed or name in changed_extra]
        impact[suite] = {
            'modeled_functions': functions,
            'changed': hit,
            'impact': 'CHANGED' if hit else 'UNCHANGED_BY_054',
        }
    sources = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')
    return {
        'status': 'REFREEZE_REQUIRED',
        'reason': 'existing suites pin historical prepared layers (31/19/20 '
                  'patches) and cannot accept the 42-layer tree without pin '
                  'updates; their pin files are outside this patch write scope',
        'new_layer': {
            'patch_count': len(prepared['layers']['candidate42']['patches']),
            'patch_names': [p['name'] for p in prepared['layers']['candidate42']['patches']],
            'prepared_files': len(prepared['layers']['candidate42']['prepared_files']),
            'src/init/ssdk_init.c': cand['text_sha256'],
            'patch_054_sha256': prepared['layers']['candidate42']['patches'][-1]['sha256'],
            'registry_pin': PIN,
        },
        'impact': impact,
        'changed_functions': changed,
        'changed_witness_functions': changed_extra,
        'regi_exit_unchanged': cand['regi_exit_sha256'] == base['regi_exit_sha256'],
        'historical_evidence_root': str(sources),
        'note': 're-run each suite against a fresh candidate42 prepared tree after '
                'updating its SOURCE_SHA/RECEIPT_SHA/patch-count pins; only '
                'test-ssdk-root-lifecycle.py and any suite modelling '
                'ssdk_netdev_notifier_register change body hashes',
    }


# ---------------------------------------------------------------------------
# Host model cases. One source of truth for fixture.c's cases.h and the driver.
# ---------------------------------------------------------------------------

OUTCOMES = {
    'OUT_OK': 0, 'OUT_ABORT': 1, 'OUT_RETAIN': 2, 'OUT_NODEVICE': 3,
    'OUT_ZERODEV': 4, 'OUT_DEG_SYSFS': 5, 'OUT_DEG_GENL': 6,
    'OUT_DEG_NOTIFIER': 7, 'OUT_EARLY_TOPO': 8, 'OUT_EARLY_PRIV': 9,
    'OUT_STOP': 10, 'OUT_LATCH': 11, 'OUT_UNLOAD': 12, 'OUT_ERRNO': 13,
}
OUTCOME_NAMES = {value: key for key, value in OUTCOMES.items()}
# Exact stdout marker every positive case must contain (free-form text is not
# the contract; the fixture also asserts call counters and order invariants).
OUTCOME_MARKERS = {
    'OUT_OK': 'module init succeeded!',
    'OUT_ABORT': 'module init aborted in stage',
    'OUT_RETAIN': 'module init retained in stage',
    'OUT_NODEVICE': 'module init, no device found!',
    'OUT_ZERODEV': 'no admitted switch device',
    'OUT_DEG_SYSFS': 'sysfs diagnostic plane degraded',
    'OUT_DEG_GENL': 'genl diagnostic plane degraded',
    'OUT_DEG_NOTIFIER': 'netdev cache contract violation',
}
SW_FAIL = -1
SW_READ_ERROR = -8
SW_BUSY = -22
SW_OUT_OF_MEM = -28
SW_NOT_SUPPORTED = -19
ERRNO = {'EIO': 5, 'ENOMEM': 12, 'EINVAL': 22, 'EBUSY': 16, 'EEXIST': 17,
         'EOPNOTSUPP': 95, 'ENODEV': 19}


def _case(name, outcome, ret, **kwargs):
    row = {
        'name': name, 'kind': 0, 'ndev': 1, 'dt_disabled': 0, 'local_bus': 1,
        'topology_rv': 0, 'alloc_rv': 0, 'plat_rv': [0, 0, 0, 0],
        'driver_rv': 0, 'chip_none': 0, 'chip_rv': [0, 0, 0, 0],
        'sd_rv': 0, 'fal_rv': 0, 'phy_rv': 0, 'hppe_rv': 0, 'switch_rv': 0,
        'sysfs_rv': 0, 'genl_rv': 0, 'notifier_rv': 0,
        'expect_outcome': outcome, 'expect_ret': ret, 'variant': 0,
        'artificial': 0,
    }
    row.update(kwargs)
    return row


CASES = [
    _case('healthy-1dev', 'OUT_OK', '0'),
    _case('healthy-2dev', 'OUT_OK', '0', ndev=2, local_bus=0b11),
    _case('healthy-mdio-2dev', 'OUT_OK', '0', ndev=2, local_bus=0b00),
    _case('abort-topology', 'OUT_EARLY_TOPO', '-ENOMEM', topology_rv=-12),
    _case('abort-priv', 'OUT_EARLY_PRIV', '-ENOMEM', alloc_rv=-12),
    _case('abort-plat-swfail', 'OUT_ABORT', '-EIO', plat_rv=[SW_FAIL, 0, 0, 0]),
    _case('abort-plat-einval', 'OUT_ABORT', '-EINVAL',
          plat_rv=[ERRNO['EINVAL'] * -1, 0, 0, 0]),
    _case('abort-plat-enodev', 'OUT_ABORT', '-EIO',
          plat_rv=[-ERRNO['ENODEV'], 0, 0, 0]),
    _case('abort-driver', 'OUT_ABORT', '-ENOMEM', driver_rv=-12),
    _case('abort-chip-busy', 'OUT_ABORT', '-EBUSY',
          chip_rv=[SW_BUSY, 0, 0, 0]),
    _case('no-device-then-device', 'OUT_OK', '0', ndev=2, local_bus=0b11,
          chip_none=0b01),
    _case('abort-second-dev', 'OUT_ABORT', '-EIO', ndev=2, local_bus=0b11,
          dt_disabled=0b01, plat_rv=[0, SW_FAIL, 0, 0]),
    _case('retain-fal', 'OUT_RETAIN', '0', fal_rv=SW_READ_ERROR),
    _case('retain-phy-artificial', 'OUT_RETAIN', '0', phy_rv=-12, artificial=1),
    _case('retain-hppe', 'OUT_RETAIN', '0', hppe_rv=SW_FAIL),
    _case('retain-switch', 'OUT_RETAIN', '0', switch_rv=SW_OUT_OF_MEM),
    _case('no-device', 'OUT_NODEVICE', '0', chip_none=0b1),
    _case('all-disabled', 'OUT_ZERODEV', '0', ndev=2, dt_disabled=0b11),
    _case('degraded-sysfs', 'OUT_DEG_SYSFS', '0', sysfs_rv=SW_FAIL),
    _case('degraded-genl', 'OUT_DEG_GENL', '0', genl_rv=-12),
    _case('notifier-fail', 'OUT_DEG_NOTIFIER', '0',
          notifier_rv=-ERRNO['EEXIST']),
    _case('retain-after-publish', 'OUT_RETAIN', '0', ndev=2, local_bus=0b11,
          plat_rv=[0, SW_FAIL, 0, 0]),
    _case('driver-once-2dev', 'OUT_OK', '0', ndev=2, local_bus=0b11),
    _case('stop-idempotence', 'OUT_STOP', '0', kind=1, variant=0),
    _case('stop-retained-state', 'OUT_UNLOAD', '0', kind=1, variant=1),
    _case('latch-first-error', 'OUT_LATCH', '0', kind=2),
    _case('errno-map-unit', 'OUT_ERRNO', '0', kind=3),
    _case('unload-retained-clean', 'OUT_UNLOAD', '0', kind=4, ndev=2,
          variant=0),
    _case('unload-retained-fal-partial', 'OUT_UNLOAD', '0', kind=4, ndev=2,
          variant=1),
]
CASE_NAMES = [row['name'] for row in CASES]


def _c_int(value):
    return str(int(value))


def _c_ret(token):
    require(token == '0' or re.fullmatch(r'-E[A-Z]+', token), 'CASE_ERRNO:' + token)
    if token == '0':
        return '0'
    require(token[1:] in ERRNO, 'CASE_ERRNO:' + token)
    return token


def render_cases(max_dev):
    lines = ['/* Generated from tests/ssdk-root-init-retention/source.py CASES. */',
             'struct input {',
             '\tunsigned kind, ndev, dt_disabled, local_bus, variant, artificial;',
             '\tint topology_rv, alloc_rv, driver_rv;',
             '\tint plat_rv[%d];' % max_dev,
             '\tunsigned chip_none;',
             '\tint chip_rv[%d];' % max_dev,
             '\tint sd_rv, fal_rv, phy_rv, hppe_rv, switch_rv;',
             '\tint sysfs_rv, genl_rv, notifier_rv;',
             '\tunsigned expect_outcome;',
             '\tint expect_ret;',
             '\tconst char *name;',
             '};',
             'enum outcome {']
    lines += ['\t%s = %d,' % (name, value) for name, value in OUTCOMES.items()]
    lines += ['};', 'static const struct input inputs[] = {']
    for row in CASES:
        lines.append('\t{%d, %d, 0x%x, 0x%x, %d, %d, %d, %d, %d, '
                     '{%s}, 0x%x, {%s}, %d, %d, %d, %d, %d, %d, %d, %d, '
                     '%s, %s, "%s"},' % (
                         row['kind'], row['ndev'], row['dt_disabled'],
                         row['local_bus'], row['variant'], row['artificial'],
                         row['topology_rv'], row['alloc_rv'], row['driver_rv'],
                         ', '.join(_c_int(v) for v in row['plat_rv'][:max_dev]),
                         row['chip_none'],
                         ', '.join(_c_int(v) for v in row['chip_rv'][:max_dev]),
                         row['sd_rv'], row['fal_rv'], row['phy_rv'],
                         row['hppe_rv'], row['switch_rv'], row['sysfs_rv'],
                         row['genl_rv'], row['notifier_rv'],
                         row['expect_outcome'], _c_ret(row['expect_ret']),
                         row['name']))
    lines += ['};', '#define CASE_COUNT (sizeof(inputs) / sizeof(inputs[0]))', '']
    return '\n'.join(lines)


def host_sources(tree):
    """Emit the host translation-unit inputs derived from the 42-layer tree."""
    layer = extract(tree)
    order = sorted(layer['functions'],
                   key=lambda name: layer['functions'][name]['line'])
    actual = ['/* Generated from the 42-layer prepared src/init/ssdk_init.c. Do not edit. */']
    actual.append(layer['root_block'])
    file_scope = ['static bool ssdk_driver_owned;']
    for declaration in file_scope:
        require(declaration in layer['text'], 'FILE_SCOPE_DECL:' + declaration)
        actual.append(declaration)
    for name in order:
        entry = layer['functions'][name]
        actual.append('/* %s (prepared line %d) */' % (name, entry['line']))
        actual.append(entry['body'])
    max_dev = int(re.search(r'^#define\s+SW_MAX_NR_DEV\s+(\d+)',
                           (Path(tree) / 'include/common/sw_config.h').read_text(),
                           re.M).group(1))
    return {'sdk.h': sdk_prelude(tree), 'actual.c': '\n'.join(actual) + '\n',
            'cases.h': render_cases(max_dev), 'max_dev': max_dev,
            'extracted': {name: {'line': entry['line'],
                                 'sha256': entry['sha256']}
                          for name, entry in layer['functions'].items()}}
