#!/usr/bin/env python3
"""SSDK41 cold-resource ledger host tests, not root/reader/HW qualification."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT/'tests/ssdk-platform-resources'
PATCH = ROOT/'package/qca-nss/qca-ssdk/patches/053-ssdk-track-platform-resource-acquisition.patch'
BASE_INVENTORY = 'de800e3ae4900eb832161581c753098dd232a36a980d09c2a66a375c044e0129'
BASE_PLAT = 'd4575ba235184edb072761cf5e5d02bc3b61f0944b315d8bdd73d991a19bb8f1'
CANDIDATE_PLAT = 'aff83ac50ba65685ab44d1c6ad8c96d8c6f040045a532e52b6cc7af2f1d0474f'
PREFIX_PATCHES = '0b7fde825cdba39ced7920e0785a67a30c10196fcb16df83c09b9dcf9dd27bff'
RECIPE31 = 'a4f44c2ea43aaf4a35e93472cef0c81f96b0104fb913a93d17b0b4197ecc9757'
PATCH53 = '9863d5e960f8582100cf61fc22373490c6cfc5db8236a4da20cb1d8ecc159938'
PROFILES = {name: flags for name, flags in [
    ('plain', []), ('uniphy', ['IN_UNIPHY']), ('dess', ['DESS']), ('dess-uniphy', ['DESS', 'IN_UNIPHY']),
    ('hppe', ['HPPE']), ('hppe-uniphy', ['HPPE', 'IN_UNIPHY']), ('hppe-dess', ['HPPE', 'DESS']),
    ('hppe-dess-uniphy-synthetic', ['HPPE', 'DESS', 'IN_UNIPHY']), ('mp-uniphy', ['MP', 'IN_UNIPHY'])]}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


lex = load_module('platform_lexer', ROOT/'tests/nss-dp-containment/extract_prepared_c.py')
patcher = load_module('platform_patch', ROOT/'tests/edma_patch_context.py')


def inventory(root):
    need(root.is_dir() and not root.is_symlink(), 'regular prepared directory')
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink() and (path.is_dir() or path.is_file()), 'regular prepared files')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return result


def typedef(text, name):
    rows = re.findall(r'\btypedef\s+(?:enum|struct)\s*\{[^{}]*\}\s*'+name+r'\s*;', text)
    need(len(rows) == 1, 'one actual typedef: '+name)
    return rows[0]


def admit_source(patches, recipe):
    need(type(patches) is dict and len(patches) == 41 and
         patches.get(PATCH.name) == PATCH53, 'complete41 patch inventory')
    prefix = {name: value for name, value in patches.items() if name != PATCH.name}
    need(sha(json.dumps(prefix, sort_keys=True, separators=(',', ':')).encode()) == PREFIX_PATCHES,
         'unchanged frozen40 patch names and bytes')
    need(sha(recipe) == RECIPE31, 'exact vendor pin and reviewed release31 recipe')


def sdk_view(text):
    kept, result = False, []
    for line in text.splitlines(True):
        if '/*qca808x_start*/' in line:
            need(not kept, 'nested export marker'); kept = True
        elif '/*qca808x_end*/' in line:
            need(kept, 'unpaired export marker'); kept = False
        elif kept:
            result.append(line)
    need(not kept, 'unclosed export marker')
    return ''.join(result)


def outcome(code, out, err, marker=None):
    if type(code) is not int or type(out) is not bytes or type(err) is not bytes:
        return False
    if marker is not None:
        return code == 86 and out == b'' and err == ('PLATFORM:'+marker+'\n').encode()
    if code != 0 or err:
        return False
    try:
        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('duplicate outcome key')
                result[key] = value
            return result
        value = json.loads(out, object_pairs_hook=unique)
    except (ValueError, TypeError):
        return False
    keys = {'maps', 'unmaps', 'claims', 'releases', 'enables', 'disables', 'gcc_starts', 'gcc_stops'}
    return (type(value) is dict and set(value) == keys | {'status'} and value['status'] == 'PLATFORM_CASE' and
            all(type(value[k]) is int and value[k] >= 0 for k in keys))


def expected_simple(flags, mask, fault, clock):
    kinds = ([0] if 'IN_UNIPHY' in flags and mask & 1 else []) + ([1] if mask & 2 else []) + ([2] if 'DESS' in flags and mask & 4 else [])
    successful, region, reached_clock = 0, 0, False
    for index, kind in enumerate(kinds, 1):
        if kind == 2:
            if fault == 10:
                break
            region = 1
        if index == fault:
            break
        successful += 1
        if kind == 1:
            reached_clock = True
    reached_clock = successful == len(kinds) and bool(mask & 2)
    enables = int(reached_clock and clock in (0, 3, 4, 6))
    disables = int(reached_clock and clock in (0, 3, 6))
    gcc = int(reached_clock and clock in (1, 5) and bool({'HPPE', 'MP'} & set(flags)))
    return dict(status='PLATFORM_CASE', maps=successful, unmaps=successful, claims=region, releases=region,
                enables=enables, disables=disables, gcc_starts=gcc, gcc_stops=gcc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline40', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    report = {'status': 'INCOMPLETE', 'runtime_approved': False,
              'profile': 'SERIAL_COLD_RESOURCE_MODELS_NOT_ROOT_SHARED_READERS_OR_TARGET_ABI',
              'commands': [], 'positive': [], 'negative': [], 'old_witnesses': []}
    package = ROOT/'package/qca-nss/qca-ssdk'
    source_patches = inventory(package/'patches')
    admit_source(source_patches, (package/'Makefile').read_bytes())
    owned = [Path(__file__), SUPPORT/'fixture.c', SUPPORT/'README.md', ROOT/'tests/test-ssdk-platform-oracles.py',
             ROOT/'tests/test-ssdk-retirement-admission.py', *(package/'patches'/name for name in source_patches), package/'Makefile',
             ROOT/'tests/edma_patch_context.py', ROOT/'tests/nss-dp-containment/extract_prepared_c.py']
    identities = {str(path): sha(path.read_bytes()) for path in owned}
    report.update(inputs=identities, source_patches=source_patches)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
               UBSAN_OPTIONS='halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode=98')

    def invoke(label, argv, raw=None):
        process = subprocess.run(list(map(str, argv)), input=raw, capture_output=True, timeout=90, env=env)
        prefix = out/label; prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix('.stdout').write_bytes(process.stdout); prefix.with_suffix('.stderr').write_bytes(process.stderr)
        row = {'argv': list(map(str, argv)), 'returncode': process.returncode,
               'ASAN_OPTIONS': env['ASAN_OPTIONS'], 'UBSAN_OPTIONS': env['UBSAN_OPTIONS']}
        prefix.with_suffix('.json').write_text(json.dumps(row, indent=2)+'\n')
        report['commands'].append({'label': label, **row})
        return process

    try:
        base, actual = inventory(args.baseline40), inventory(args.prepared)
        need(len(base) == 692 and sha(json.dumps(base, sort_keys=True, separators=(',', ':')).encode()) == BASE_INVENTORY,
             'immutable complete SSDK40 baseline')
        relative = 'src/init/ssdk_plat.c'
        need(base[relative] == BASE_PLAT and actual == dict(base, **{relative: CANDIDATE_PLAT}), 'only reviewed platform file changes')
        data = PATCH.read_bytes()
        outputs, context = patcher.inspect_patch(args.baseline40, data)
        need(set(outputs) == {relative} and sha(outputs[relative]) == CANDIDATE_PLAT, 'exact declared patch output')
        replay = out/'replayed'; shutil.copytree(args.baseline40, replay)
        process = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-V', 'none'], input=data,
                                 cwd=replay, capture_output=True, timeout=60)
        (out/'patch.stdout').write_bytes(process.stdout); (out/'patch.stderr').write_bytes(process.stderr)
        need(process.returncode == 0 and not process.stderr and
             not re.search(rb'offset|fuzz|FAILED|reject|Reversed', process.stdout, re.I) and inventory(replay) == actual,
             'exact real patch replay and full692')
        report.update(prepared_files=actual, patch_context=context)
        header = (replay/'include/init/ssdk_init.h').read_text()
        start = header.index('    typedef enum {\n        HSL_MDIO')
        end = header.index('} hsl_reg_func;', start)+len('} hsl_reg_func;')
        types = typedef((replay/'include/common/sw_error.h').read_text(), 'sw_error_t')+'\n'+header[start:end]
        types += '\n'+ '\n'.join(typedef(header, name) for name in ('ssdk_chip_type', 'ssdk_port_cfg', 'ssdk_init_cfg'))
        types += '\n'+typedef((replay/'include/init/ssdk_dts.h').read_text(), 'ssdk_reg_map_info')
        maximum = re.findall(r'^#define SW_MAX_NR_DEV\s+3\s*$', (replay/'include/common/sw_config.h').read_text(), re.M)
        need(len(maximum) == 1, 'actual three-device limit')
        fixture = (SUPPORT/'fixture.c').read_text().replace('@ACTUAL_TYPES@', types).replace('@ACTUAL_MAX_DEV@', maximum[0])
        text = (replay/relative).read_text()
        begin = text.index('/* Cold root init/exit only;')
        last = lex.function(text, 'ssdk_plat_exit')
        finish = text.index(last.rstrip(), begin)+len(last.rstrip())
        candidate = text[begin:finish]
        baseline_text = (args.baseline40/relative).read_text()
        baseline = lex.function(baseline_text, 'ssdk_plat_init')+lex.function(baseline_text, 'ssdk_plat_exit')
        sdk_view(text); sdk_view(baseline_text)
        cc = shutil.which(args.cc); need(cc is not None, 'host compiler')
        cc = str(Path(cc).resolve())
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        report['compiler'] = {'path': cc, 'sha256': sha(Path(cc).read_bytes()), 'flags': flags}
        if args.sanitize:
            detector = ROOT/'tests/test-ssdk-retirement-admission.py'
            need(sha(detector.read_bytes()) == '3d7a2b175c617aea12b45fe37e3a63b4e5b595d8b671fb46763784b6443ef2e3',
                 'fixed independent detector activation runner')
            process = invoke('detector-controls', [sys.executable, '-B', detector, '--canaries-only', '--sanitize',
                             '--cc', cc, '--output', out/'detector-controls'])
            need(process.returncode == 0 and not process.stderr and
                 json.loads(process.stdout) == {'status': 'PASS_SANITIZER_CONTROLS_ONLY'}, 'actual detector activation campaign')
            control = json.loads((out/'detector-controls/RESULTS.json').read_bytes())
            need(control['sanitizer_controls']['activation'] == [
                 {'name': 'asan', 'instrumentation': 'address', 'exit': 97},
                 {'name': 'ubsan', 'instrumentation': 'undefined', 'exit': 98}], 'distinct active detectors')
            for kind, expected_code in [('asan', 97), ('ubsan', 98)]:
                prefix = out/'detector-controls'/('canary-'+kind+'-run')
                row = json.loads(prefix.with_suffix('.exit.json').read_bytes())
                diagnostic = prefix.with_suffix('.stderr').read_bytes()
                need(type(row['returncode']) is int and row['returncode'] == expected_code and
                     prefix.with_suffix('.stdout').read_bytes() == b'', 'strict activation process identity')
                if kind == 'asan':
                    need(b'ERROR: AddressSanitizer: heap-buffer-overflow' in diagnostic and
                         b'WRITE of size 1' in diagnostic and b'runtime error:' not in diagnostic and
                         b'DEADLYSIGNAL' not in diagnostic, 'ASan write identity')
                else:
                    need(re.search(rb"runtime error: signed integer overflow: (?:2147483647 \+ 1|1 \+ 2147483647) "
                                   rb"cannot be represented in type 'int'(?:\r?\n|$)", diagnostic) is not None and
                         b'AddressSanitizer' not in diagnostic, 'UBSan overflow identity')
            report['sanitizer_controls'] = control['sanitizer_controls']

        def compile_code(label, body, definitions, current=True):
            path = out/(label+'.c'); path.parent.mkdir(parents=True, exist_ok=True)
            raw = fixture.replace('@ACTUAL_CODE@', body)
            need('@ACTUAL_' not in raw, 'all actual input placeholders bound')
            path.write_text(raw)
            binary = path.with_suffix('.host')
            process = invoke(label+'-compile', [cc, *flags, *(['-DCANDIDATE=1'] if current else []),
                             *('-D'+name+'=1' for name in definitions), path, '-o', binary])
            need(process.returncode == 0 and process.stdout == process.stderr == b'', 'clean native compile: '+label)
            return binary

        def execute(label, binary, case, marker=None):
            process = invoke(label, [binary, *map(str, case)])
            need(outcome(process.returncode, process.stdout, process.stderr, marker), 'exact runtime result: '+label)
            return json.loads(process.stdout) if marker is None else None

        for name, definitions in PROFILES.items():
            binary = compile_code('profiles/'+name, candidate, definitions)
            cases = []
            for mask in range(8):
                count = int(bool(mask & 2))+int('IN_UNIPHY' in definitions and bool(mask & 1))+int('DESS' in definitions and bool(mask & 4))
                for clock in range(7):
                    cases += [(mask, fault, clock, 0) for fault in [0, *range(1, count+1), *([10] if 'DESS' in definitions and mask & 4 else [])]]
            cases += [(7, 0, clock, scenario) for clock in range(7) for scenario in (1, 2, 4, 6, 7, 9, 10)]
            count = 1+int('IN_UNIPHY' in definitions)+int('DESS' in definitions)
            cases += [(7, fault, clock, 8) for clock in range(7) for fault in range(1, count+1)]
            cases += [(7, 0, 0, 3), (0, 0, 0, 5)]
            need(len(cases) == len(set(cases)), 'no duplicate positive cases')
            for index, case in enumerate(cases):
                value = execute('positive/'+name+'/'+str(index), binary, case)
                if case[3] == 0:
                    need(value == expected_simple(definitions, *case[:3]), 'independent exact resource counts')
            report['positive'].append({'profile': name, 'defines': definitions, 'cases': len(cases)})

        def edit(before, after):
            need(candidate.count(before) == 1, 'unique source mutation anchor')
            return candidate.replace(before, after, 1)

        mutants = [
            ('uniphy-leak', '\tif (resources->uniphy)\n\t\tiounmap(resources->uniphy);', '(void)resources->uniphy;', (3, 2, 1, 0), 'MAP_LEAK'),
            ('region-leak', '\tif (resources->psgmii_region)\n\t\trelease_mem_region(resources->psgmii_map.base_addr,\n\t\t\tresources->psgmii_map.size);', '(void)resources->psgmii_region;', (7, 3, 0, 0), 'REGION_LEAK'),
            ('clock-leak', '\tif (resources->ess_enabled)\n\t\tclk_disable_unprepare(resources->ess_clk);', '(void)resources->ess_enabled;', (2, 0, 0, 0), 'CLOCK_LEAK'),
            ('failed-clock-retired', '\t\t\tif (clock_rv) {', '\t\t\tif (clock_rv) { pending.ess_clk = ess_clk; pending.ess_enabled = true;', (2, 0, 4, 0), 'UNOWNED_CLOCK'),
            ('gcc-repeated-init', '\t\t\tif (!ssdk_plat_gcc_users)\n\t\t\t\tssdk_gcc_clock_init();', '\t\t\tssdk_gcc_clock_init();', (2, 0, 1, 2), 'GCC_DOUBLE_START'),
            ('gcc-premature-stop', 'resources->gcc && --ssdk_plat_gcc_users == 0', 'resources->gcc && --ssdk_plat_gcc_users < SW_MAX_NR_DEV', (2, 0, 1, 2), 'GCC_PEER_RETIRE'),
            ('gcc-missing-right', '\t\t\t++ssdk_plat_gcc_users;', '\t\t\t(void)ssdk_plat_gcc_users;', (2, 0, 1, 0), 'GCC_LEAK'),
            ('region-missing-right', 'pending.psgmii_region = true;', 'pending.psgmii_region = false;', (7, 3, 0, 0), 'REGION_LEAK'),
            ('ledger-not-retired', '\tmemset(resources, 0, sizeof(*resources));', '\t(void)resources;', (2, 0, 0, 0), 'LEDGER_LEAK'),
            ('early-cfg', '\tpending.owner = priv;', '\tpending.owner = priv; cfg->reg_func.uniphy_reg_set = qca_uniphy_reg_write;', (7, 0, 0, 0), 'EARLY_CFG'),
            ('early-map', '#ifdef DESS\n\treg_mode = ssdk_psgmii_reg_access_mode_get(dev_id);',
             '\tpriv->hw_addr = pending.switch_base;\n#ifdef DESS\n\treg_mode = ssdk_psgmii_reg_access_mode_get(dev_id);', (7, 0, 0, 0), 'EARLY_PUBLICATION'),
            ('region-wrong-identity', 'release_mem_region(resources->psgmii_map.base_addr,', 'release_mem_region(resources->psgmii_map.base_addr + 4,', (7, 0, 0, 0), 'REGION_PAIR'),
            ('invalid-accepted', '\t\trv = -EINVAL;', '\t\trv = 0;', (0, 0, 0, 5), 'INVALID_RESULT'),
            ('wrong-mdio', '\t\taccess_mode = HSL_MDIO;', '\t\taccess_mode = HSL_HEADER;', (0, 0, 0, 0), 'CFG_MODE'),
            ('empty-owner-admission', 'ssdk_plat_resources[dev_id].owner || ', '', (0, 0, 0, 1), 'ADMISSION_RESULT'),
            ('borrowed-map-admission', ' || priv->hw_addr ||', ' ||', (0, 0, 0, 3), 'ADMISSION_RESULT'),
            ('foreign-instance-exit', '\tif (!qca_phy_priv_global || dev_id >= ssdk_switch_device_num_get() ||\n\t    qca_phy_priv_global[dev_id] != resources->owner)\n\t\tgoto foreign;',
             '\t(void)qca_phy_priv_global;', (2, 0, 6, 4), 'FOREIGN_RETIRE'),
            ('foreign-mapping-exit', '\tif (priv->hw_addr != resources->switch_base ||\n\t    priv->uniphy_hw_addr != resources->uniphy ||\n\t    priv->psgmii_hw_addr != resources->psgmii)\n\t\tgoto foreign;',
             '\t(void)priv;', (2, 0, 6, 4), 'FOREIGN_RETIRE'),
            ('missing-cold-lock', '\trv = -1;\n\tmutex_lock(&ssdk_plat_resource_lock);',
             '\trv = -1;', (2, 0, 0, 0), 'LOCK_MISSING'),
            ('gcc-before-mapping-complete', '#ifdef DESS\n\treg_mode = ssdk_psgmii_reg_access_mode_get(dev_id);',
             '\tssdk_gcc_clock_init(); ++ssdk_plat_gcc_users; pending.gcc = true;\n#ifdef DESS\n\treg_mode = ssdk_psgmii_reg_access_mode_get(dev_id);',
             (7, 3, 1, 0), 'CLOCK_BEFORE_MAP_COMPLETE'),
        ]
        all_features = ['HPPE', 'DESS', 'IN_UNIPHY']
        for name, before, after, case, marker in mutants:
            binary = compile_code('negative/'+name, edit(before, after), all_features)
            execute('negative/'+name+'-run', binary, case, marker)
            report['negative'].append({'name': name, 'case': case, 'marker': marker})
        old = compile_code('old/current40', baseline, all_features, current=False)
        for index, (case, marker) in enumerate([((3, 2, 1, 0), 'ERROR_PUBLICATION'),
                                               ((7, 3, 0, 0), 'ERROR_PUBLICATION'),
                                               ((2, 0, 6, 10), 'EXIT_PUBLICATION'),
                                               ((2, 0, 1, 2), 'GCC_DOUBLE_START')]):
            execute('old/witness-'+str(index), old, case, marker)
            report['old_witnesses'].append({'case': case, 'marker': marker})
        exported = sdk_view(text)
        sdk_functions = lex.function(exported, 'ssdk_plat_init')+lex.function(exported, 'ssdk_plat_exit')
        exported_header = sdk_view(header)
        first = exported_header.index('    typedef enum {\n        HSL_MDIO')
        last = exported_header.index('} hsl_reg_func;', first)+len('} hsl_reg_func;')
        sdk_types = typedef((replay/'include/common/sw_error.h').read_text(), 'sw_error_t')+'\n'+exported_header[first:last]
        sdk_types += '\n'+typedef(exported_header, 'ssdk_chip_type')+'\n'+typedef(exported_header, 'ssdk_init_cfg')
        fields = sorted(re.findall(r'\b\w+\s+(\w+)\s*;', typedef(exported_header, 'hsl_reg_func')))
        need(fields == ['i2c_get', 'i2c_set', 'mdio_get', 'mdio_set'], 'actual SDK-only four callback fields')
        sdk_source = '#include <stdio.h>\ntypedef unsigned a_uint32_t; typedef unsigned short a_uint16_t;\n'+sdk_types+'\n#define SSDK_INFO(...) ((void)0)\n'+sdk_functions
        sdk_source += '\nint main(void) { ssdk_plat_exit(0); return ssdk_plat_init(NULL, 0); }\n'
        path = out/'sdk-view.c'; path.write_text(sdk_source)
        process = invoke('sdk-view-compile', [cc, *flags, '-Wno-unused-parameter', path, '-o', out/'sdk-view.host'])
        need(process.returncode == 0 and process.stdout == process.stderr == b'', 'SDK export does not include Linux resource code')
        process = invoke('sdk-view-run', [out/'sdk-view.host'])
        need(process.returncode == 0 and process.stdout == process.stderr == b'', 'unchanged SDK-only no-platform behavior')
        report['sdk_reg_func_fields'] = fields
        need(inventory(args.baseline40) == base and inventory(args.prepared) == actual and inventory(replay) == actual and
             all(sha(Path(name).read_bytes()) == value for name, value in identities.items()), 'all input and full tree stability')
        need(inventory(package/'patches') == source_patches, 'end complete patch directory stability')
        admit_source(inventory(package/'patches'), (package/'Makefile').read_bytes())
        report.update(status='PASS_SSDK41_PLATFORM_HOST_ONLY_NOT_ROOT_SHARED_LIFECYCLE',
                      positive_count=sum(row['cases'] for row in report['positive']), negative_count=len(mutants), old_witness_count=4,
                      open=['root late-failure transaction and module exit failure', 'UK/SD/PHY providers/readers/ABA',
                            'clock-enable failure propagation and nested void GCC hardware success',
                            'real target ABI/RCU/MMIO/clocks and performance'])
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        (out/'RESULTS.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'positive_count', 'negative_count', 'old_witness_count')}))


if __name__ == '__main__':
    main()
