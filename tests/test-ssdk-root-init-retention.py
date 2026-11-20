#!/usr/bin/env python3
"""42-layer SSDK root-init retention host model: positives, mutants, gates.

The model compiles the complete actual patched regi_init(), ssdk_init(), the
root context helpers, the module-wide driver publication, the abort helper and
the two work-stop guards from the prepared d9a19649 + 54-patch tree inside
explicit serial stubs. Positives assert outcome, return code, call counters,
cleanup order, cache admission and log markers; named source mutants must be
newly compiled clean and reject with exit 86 and one fixed ROOT_ASSERT line.
Static gates prove the contract is in the source and are themselves proven
non-vacuous by text-mutation controls. No target compile, build, hardware,
thread, RCU or module-unload claim is made.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve()
SUPPORT = HERE.parent / 'ssdk-root-init-retention'
spec = importlib.util.spec_from_file_location('root_init_source', SUPPORT / 'source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)

# Compiled source mutants: (name, case, marker, [(old, new), ...]).
MUTANTS = [
    ('fal-continue', 'retain-fal', 'FAL_PHY_AFTER_FAILURE', [(
        '\t\tSSDK_ERROR("ssdk fal init failed: %d. \\r\\n", rv);\n\t\treturn rv;\n\t}',
        '\t\tSSDK_ERROR("ssdk fal init failed: %d. \\r\\n", rv);\n\t}')]),
    ('fal-overwrite-first-error', 'retain-fal', 'FAL_SILENT_ACCEPT', [(
        '\t\tSSDK_ERROR("ssdk fal init failed: %d. \\r\\n", rv);\n\t\treturn rv;',
        '\t\tSSDK_ERROR("ssdk fal init failed: %d. \\r\\n", rv);\n\t\treturn 0;')]),
    ('overwrite-first-error', 'latch-first-error', 'FIRST_ERROR_OVERWRITE', [(
        '\tif (err == 0 || ssdk_root.first_err)\n\t\treturn;',
        '\tif (err == 0)\n\t\treturn;')]),
    ('hppe-ignore', 'retain-hppe', 'HPPE_SWITCH_AFTER_FAILURE', [(
        '\t\t\t\trv = qca_hppe_hw_init(dev_id);',
        '\t\t\t\tqca_hppe_hw_init(dev_id);')]),
    ('cache-on-zero-devices', 'all-disabled', 'CACHE_ZERO_DEVICES', [(
        'if (ssdk_root.first_err == SW_OK && ssdk_root.dev_initialized > 0)',
        'if (ssdk_root.first_err == SW_OK)')]),
    ('cache-on-degraded', 'retain-fal', 'CACHE_DEGRADED', [(
        'if (ssdk_root.first_err == SW_OK && ssdk_root.dev_initialized > 0)',
        'if (1)')]),
    ('sysfs-fatal', 'degraded-sysfs', 'SYSFS_FATAL', [(
        '\t\tif (rv)\n\t\t\tSSDK_ERROR("qca-%s sysfs diagnostic plane degraded (code: %d); control plane continues\\n",\n\t\t\t\t   SSDK_STR, rv);',
        '\t\tif (rv)\n\t\t\treturn rv;')]),
    ('sysfs-silent', 'degraded-sysfs', 'SYSFS_SILENT', [(
        '\t\tif (rv)\n\t\t\tSSDK_ERROR("qca-%s sysfs diagnostic plane degraded (code: %d); control plane continues\\n",\n\t\t\t\t   SSDK_STR, rv);',
        '\t\tif (rv)\n\t\t\t(void)rv;')]),
    ('genl-double-deinit', 'healthy-1dev', 'GENL_DOUBLE_DEINIT', [(
        '\t\tif (rv)\n\t\t\tSSDK_ERROR("qca-%s genl diagnostic plane degraded (code: %d); control plane continues\\n",\n\t\t\t\t   SSDK_STR, rv);',
        '\t\tif (rv)\n\t\t\tSSDK_ERROR("qca-%s genl diagnostic plane degraded (code: %d); control plane continues\\n",\n\t\t\t\t   SSDK_STR, rv);\n\t\tssdk_genl_deinit();')]),
    ('abort-phy-after-plat', 'abort-plat-swfail', 'ABORT_ORDER_PHY_AFTER_PLAT', [(
        '\tssdk_driver_unregister_owned();\n\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {\n\t\tphy_rv = ssdk_phy_driver_cleanup(dev_id);',
        '\tssdk_driver_unregister_owned();\n\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {\n\t\tif (ssdk_root.dev_stage[dev_id] >= SSDK_ROOT_STAGE_PLAT)\n\t\t\tssdk_plat_exit(dev_id);\n\t}\n\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {\n\t\tphy_rv = ssdk_phy_driver_cleanup(dev_id);')]),
    ('abort-plat-skip', 'abort-plat-swfail', 'ABORT_PLAT_LEAKED', [(
        '\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {\n\t\tif (ssdk_root.dev_stage[dev_id] >= SSDK_ROOT_STAGE_PLAT)\n\t\t\tssdk_plat_exit(dev_id);\n\t}\n\tssdk_free_priv();',
        '\tssdk_free_priv();')]),
    ('abort-no-free', 'abort-plat-swfail', 'ABORT_NO_FREE', [(
        '\tssdk_free_priv();\n}\n\n/* regi_init',
        '}\n\n/* regi_init')]),
    ('abort-unregister-unowned', 'abort-driver', 'DRIVER_UNREG_UNOWNED', [(
        '\tif (!ssdk_driver_owned)\n\t\treturn;\n\tplatform_driver_unregister(&ssdk_driver);',
        '\tplatform_driver_unregister(&ssdk_driver);')]),
    ('retain-frees-priv', 'retain-fal', 'RETAIN_FREED', [(
        '\t\t\t  SSDK_STR, ssdk_root.dev_initialized);\n\t\treturn 0;',
        '\t\t\t  SSDK_STR, ssdk_root.dev_initialized);\n\t\tssdk_free_priv();\n\t\treturn 0;')]),
    ('retain-return-error', 'retain-fal', 'RETAIN_RETURN_ERROR', [(
        '\t\t\t  SSDK_STR, ssdk_root.dev_initialized);\n\t\treturn 0;',
        '\t\t\t  SSDK_STR, ssdk_root.dev_initialized);\n\t\treturn -ENOMEM;')]),
    ('errno-enodev', 'errno-map-unit', 'ERRNO_SW_ENODEV', [(
        '\t\tcase SW_NOT_SUPPORTED:\n\t\t\treturn -EOPNOTSUPP;',
        '\t\tcase SW_NOT_SUPPORTED:\n\t\t\treturn -ENODEV;')]),
    ('errno-guard-removed', 'abort-plat-enodev', 'ERRNO_ENODEV', [(
        '\treturn rv == -ENODEV ? -EIO : rv;', '\treturn rv;')]),
    ('errno-raw-minus1', 'abort-plat-swfail', 'ERRNO_RAW_MINUS1', [(
        '\treturn err == SW_FAIL ? SSDK_ROOT_DOMAIN_SW : SSDK_ROOT_DOMAIN_LINUX;',
        '\treturn SSDK_ROOT_DOMAIN_LINUX;')]),
    ('chip-enodev-fatal', 'no-device', 'CHIP_ENODEV_FATAL', [(
        '\t\tif (rv == -ENODEV) {', '\t\tif (0) {')]),
    ('plat-enodev-swallowed', 'abort-plat-enodev', 'ABORT_SWALLOWED', [(
        '\t\t\tssdk_root_latch(SSDK_ROOT_STAGE_PLAT, dev_id, rv,\n\t\t\t\t\tssdk_root_plat_domain(rv));',
        '\t\t\tif (rv == -ENODEV)\n\t\t\t\tcontinue;\n\t\t\tssdk_root_latch(SSDK_ROOT_STAGE_PLAT, dev_id, rv,\n\t\t\t\t\tssdk_root_plat_domain(rv));')]),
    ('mac-stop-guard-removed', 'stop-idempotence', 'MAC_STOP_UNSTARTED', [(
        '\t/* A retained partial init may be unloaded before this work was set up. */\n\tif (priv->device_id >= SW_MAX_NR_DEV ||\n\t    !ssdk_mac_sw_sync_work_initialized[priv->device_id])\n\t\treturn SW_NOT_SUPPORTED;\n',
        '')]),
    ('qm-stop-guard-removed', 'stop-idempotence', 'QM_STOP_UNSTARTED', [(
        '\t/* A retained partial init may be unloaded before this work was set up. */\n\tif (priv->device_id >= SW_MAX_NR_DEV ||\n\t    !ssdk_qm_err_check_work_initialized[priv->device_id])\n\t\treturn;\n',
        '')]),
    ('driver-double-register', 'driver-once-2dev', 'DRIVER_DOUBLE_REG', [(
        '\tif (ssdk_driver_owned)\n\t\treturn 0;\n\trv = platform_driver_register(&ssdk_driver);',
        '\trv = platform_driver_register(&ssdk_driver);')]),
]
SANITIZED_CASES = ['healthy-1dev', 'abort-plat-swfail', 'retain-fal',
                   'retain-after-publish']


def require(ok, marker):
    if not ok:
        raise AssertionError(marker)


def sha(path):
    return source.sha(path)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def env(code=97):
    return dict(os.environ,
                ASAN_OPTIONS=('detect_leaks=0:halt_on_error=1:abort_on_error=0:'
                              'exitcode=%d' % code),
                UBSAN_OPTIONS=('halt_on_error=1:print_stacktrace=1:exitcode=%d'
                               % code))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='gcc-16')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    source.require(sys.flags.optimize > 0, 'PYTHON_O')
    output = args.output.resolve()
    source.require(not output.exists(), 'FRESH_OUTPUT')
    output.mkdir(parents=True)
    result = {
        'status': 'FAILED',
        'qualification': 'HOST_MODEL_ONLY_NO_TARGET_COMPILE_NO_HARDWARE',
        'suite': 'ssdk-root-init-retention',
        'scope': ('42-layer patched actual regi_init/ssdk_init/root helpers/'
                  'driver publication/abort/work guards in serial stubs'),
        'positives': [],
        'negatives': [],
        'static_gates': {},
        'gate_controls': [],
        'commands': [],
    }
    try:
        base_tree, cand_tree, prepared = source.prepare(
            args.upstream_cache.resolve(), output / 'prepare')
        result['layers'] = {
            'base_patches': len(prepared['layers']['base41']['patches']),
            'candidate_patches': len(prepared['layers']['candidate42']['patches']),
            'changed_files': prepared['changed_files'],
            'candidate_patch_sha256':
                prepared['layers']['candidate42']['patches'][-1]['sha256'],
            'src_sha256': sha(Path(cand_tree) / 'src/init/ssdk_init.c'),
        }
        require(prepared['changed_files'] == ['src/init/ssdk_init.c'],
                'TOUCHED_FILES')
        host = source.host_sources(cand_tree)
        build = output / 'build'
        build.mkdir()
        for name in ('sdk.h', 'actual.c', 'cases.h'):
            (build / name).write_text(host[name])
        fixture = build / 'fixture.c'
        shutil.copyfile(SUPPORT / 'fixture.c', fixture)
        write_json(output / 'EXTRACTED.json', host['extracted'])

        result['static_gates'] = source.gates(cand_tree, base_tree)
        result['gate_controls'] = source.gate_controls(cand_tree, base_tree)
        source.require(all(g['status'] == 'PASS'
                           for g in result['static_gates'].values()
                           if isinstance(g, dict)), 'STATIC_GATE')
        source.require(all(c['status'] == 'PASS'
                           for c in result['gate_controls']), 'GATE_CONTROL')

        cc = shutil.which(args.cc)
        source.require(cc is not None, 'COMPILER')
        cc = str(Path(cc).resolve())
        compiler = {'path': cc, 'sha256': sha(cc)}
        version = subprocess.run([cc, '--version'], capture_output=True,
                                 timeout=30)
        source.require(version.returncode == 0 and version.stderr == b'',
                       'COMPILER_VERSION')
        compiler['version'] = version.stdout.splitlines()[0].decode()
        flags = ['-std=gnu11', '-O1', '-Wall', '-Wextra', '-Werror',
                 '-Wno-unused-function', '-Wno-unused-parameter',
                 '-DHPPE', '-DIN_NETLINK', '-I' + str(build)]
        result['compiler'] = compiler
        result['flags'] = flags
        case_index = {row['name']: index
                      for index, row in enumerate(source.CASES)}

        def compile_actual(stem, actual_text, extra_flags=()):
            unit = build / stem
            unit.mkdir()
            shutil.copyfile(fixture, unit / 'fixture.c')
            for name in ('sdk.h', 'cases.h'):
                shutil.copyfile(build / name, unit / name)
            (unit / 'actual.c').write_text(actual_text)
            binary = unit / 'fixture.bin'
            argv = [cc, *flags, *extra_flags, str(unit / 'fixture.c'),
                    '-o', str(binary)]
            proc = subprocess.run(argv, capture_output=True, timeout=120)
            result['commands'].append({'argv': argv, 'returncode': proc.returncode})
            (output / (stem + '.compile.stdout')).write_bytes(proc.stdout)
            (output / (stem + '.compile.stderr')).write_bytes(proc.stderr)
            source.require(proc.returncode == 0,
                           'COMPILE:' + stem + ':' + proc.stderr.decode()[-400:])
            source.require(proc.stdout == b'' and proc.stderr == b'',
                           'WARNINGS:' + stem)
            return binary

        def run_binary(binary, index, stem, used_env=None):
            argv = [str(binary), str(index)]
            proc = subprocess.run(argv, capture_output=True, timeout=60,
                                  env=used_env or os.environ.copy())
            (output / (stem + '.stdout')).write_bytes(proc.stdout)
            (output / (stem + '.stderr')).write_bytes(proc.stderr)
            return proc

        pristine_binary = compile_actual('actual', host['actual.c'])
        for row in source.CASES:
            index = case_index[row['name']]
            stem = 'positive-' + row['name']
            proc = run_binary(pristine_binary, index, stem)
            source.require(proc.returncode == 0,
                           'POSITIVE:' + row['name'] + ':'
                           + proc.stderr.decode()[-300:])
            marker = source.OUTCOME_MARKERS.get(row['expect_outcome'])
            if marker:
                source.require(marker.encode() in proc.stdout,
                               'POSITIVE_MARKER:' + row['name'])
            result['positives'].append({
                'case': row['name'],
                'outcome': row['expect_outcome'],
                'artificial': bool(row['artificial']),
                'returncode': proc.returncode,
                'stdout_sha256': source.digest(proc.stdout),
            })

        actual_text = host['actual.c']
        for name, case, marker, replacements in MUTANTS:
            mutated = actual_text
            for old, new in replacements:
                source.require(mutated.count(old) == 1,
                               'MUTANT_ANCHOR:%s:%s' % (name, old[:40]))
                mutated = mutated.replace(old, new, 1)
            binary = compile_actual('mutant-' + name, mutated)
            proc = run_binary(binary, case_index[case], 'negative-' + name)
            expected = ('ROOT_ASSERT:' + marker + '\n').encode()
            source.require(proc.returncode == 86,
                           'MUTANT_EXIT:%s:%d' % (name, proc.returncode))
            source.require(proc.stdout == b'', 'MUTANT_STDOUT:' + name)
            source.require(proc.stderr == expected,
                           'MUTANT_MARKER:%s:%r' % (name, proc.stderr))
            result['negatives'].append({
                'name': name, 'case': case, 'marker': marker,
                'compile_clean': True, 'exit': 86, 'exact_stderr': True,
                'empty_stdout': True,
            })

        if args.sanitize:
            sanitized = list(flags) + ['-fsanitize=address,undefined',
                                       '-fno-sanitize-recover=all',
                                       '-fno-omit-frame-pointer']
            canaries = []
            # ASan honours abort_on_error=0 + exitcode on this host. GCC UBSan
            # on Darwin aborts under halt_on_error=1 and does not honour
            # exitcode; activation is proven by the diagnostic instead and the
            # deviation is recorded, not hidden.
            for name, flags, text, diagnostic, exit_ok in [
                ('asan', ['-fsanitize=address', '-fno-omit-frame-pointer'],
                 '#include <stdlib.h>\nint main(int c, char **v){(void)v;'
                 'volatile char *p = malloc(1); p[c] = 1; free((void *)p);'
                 'return 0;}\n', b'AddressSanitizer',
                 lambda code: code == 97),
                ('ubsan', ['-fsanitize=undefined', '-fno-sanitize-recover=all',
                           '-fno-omit-frame-pointer'],
                 '#include <limits.h>\nint main(void){volatile int x = INT_MAX;'
                 'return x + 1;}\n',
                 b'runtime error: signed integer overflow',
                 lambda code: code in (98, 134, -6)),
            ]:
                unit = build / ('canary-' + name + '.c')
                unit.write_text(text)
                binary = build / ('canary-' + name + '.bin')
                argv = [cc, *flags, str(unit), '-o', str(binary)]
                proc = subprocess.run(argv, capture_output=True, timeout=120)
                source.require(proc.returncode == 0 and proc.stderr == b'',
                               'CANARY_COMPILE:' + name)
                proc = subprocess.run([str(binary)], capture_output=True,
                                      timeout=30, env=env(97 if name == 'asan' else 98))
                source.require(exit_ok(proc.returncode) and
                               diagnostic in proc.stderr,
                               'CANARY_ACTIVATION:' + name)
                canaries.append({'name': name, 'exit': proc.returncode,
                                 'exitcode_honoured':
                                     proc.returncode in (97, 98),
                                 'accepted_halt': exit_ok(proc.returncode),
                                 'diagnostic': diagnostic.decode(),
                                 'note': 'GCC UBSan on Darwin aborts under '
                                         'halt_on_error and does not honour '
                                         'exitcode; activation is proven by '
                                         'the diagnostic'})
            sanitized_binary = compile_actual(
                'actual-sanitized', host['actual.c'], sanitized)
            sanitized_runs = []
            for case in SANITIZED_CASES:
                proc = run_binary(sanitized_binary,
                                  case_index[case], 'sanitized-' + case, env())
                source.require(proc.returncode == 0 and
                               b'ERROR: AddressSanitizer' not in proc.stderr and
                               b'runtime error' not in proc.stderr,
                               'SANITIZED_RUN:' + case)
                sanitized_runs.append({'case': case, 'returncode': 0})
            result['sanitizers'] = {'canaries': canaries,
                                    'runs': sanitized_runs,
                                    'LSan': 'NOT_VERIFIED'}

        witness = source.witness(base_tree, cand_tree, prepared)
        write_json(output / 'REFREEZE.json', witness)
        write_json(output / 'ASSET-FREEZE.json', {
            'status': 'FROZEN_INPUT_ASSETS_HOST_MODEL_ONLY',
            'suite_assets': {
                name: sha(SUPPORT / name) for name in source.ASSET_NAMES},
            'driver_sha256': sha(HERE),
            'case_names': source.CASE_NAMES,
            'input_sha256': {
                'prepared/candidate42/RESULTS.json':
                    sha(Path(cand_tree).parent / 'RESULTS.json'),
                'prepared/base41/RESULTS.json':
                    sha(Path(base_tree).parent / 'RESULTS.json'),
                '054-patch': prepared['layers']['candidate42']['patches'][-1]['sha256'],
                'src/init/ssdk_init.c': sha(Path(cand_tree) / 'src/init/ssdk_init.c'),
            },
            'pending': 'independent parent GCC/Clang review; target build; '
                       'hardware healthy-boot regression',
        })
        result.update(
            status='HOST_MODEL_ONLY',
            positive_count=len(result['positives']),
            negative_count=len(result['negatives']),
            gate_count=len([g for g in result['static_gates'].values()
                            if isinstance(g, dict)]) - 1,
            gate_control_count=len(result['gate_controls']),
            regi_exit_unchanged=witness['regi_exit_unchanged'],
            refreeze=witness['status'],
            host_compile='actual patched function bodies compiled clean '
                         '(no target build)',
            artificial_cases=[row['name'] for row in source.CASES
                              if row['artificial']],
        )
    except Exception as error:  # noqa: BLE001 - report exact failure
        result['error'] = '%s: %s' % (type(error).__name__, error)
        import traceback
        result['traceback'] = traceback.format_exc()[-4000:]
    write_json(output / 'RESULTS.json', result)
    print(json.dumps({key: result.get(key) for key in
                      ('status', 'positive_count', 'negative_count',
                       'gate_count', 'gate_control_count', 'error')}))
    return 0 if result['status'] == 'HOST_MODEL_ONLY' else 1


if __name__ == '__main__':
    sys.exit(main())
