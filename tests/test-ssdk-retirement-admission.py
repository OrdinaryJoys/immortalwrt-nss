#!/usr/bin/env python3
"""Replay actual pinned SSDK; test SD admission and root dependent retirement.

No firmware/target build or device access. Native callbacks and allocation/
endpoint services are serial stateful models, not provider lifetime proofs.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / 'package/qca-nss/qca-ssdk'
BASE = '3f6df667e1dcfc1b7412cffca54e454d1d68922c'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
PATCH = '051-ssdk-sd-publication-and-phy-retirement-admission.patch'
BASE_INVENTORY = '469a2fabfc6cf7ce8a81f0a948a809987fcc771d1f287bc59ad3da7c28cc0fc0'
FIELDS = [('mdio_set', 'ssdk_mdio_set'), ('mdio_get', 'ssdk_mdio_get'),
          ('i2c_set', 'ssdk_i2c_set'), ('i2c_get', 'ssdk_i2c_get'),
          ('header_reg_set', 'ssdk_hdr_reg_set'), ('header_reg_get', 'ssdk_hdr_reg_get'),
          ('psgmii_reg_set', 'ssdk_psgmii_reg_set'), ('psgmii_reg_get', 'ssdk_psgmii_reg_get'),
          ('uniphy_reg_set', 'ssdk_uniphy_reg_set'), ('uniphy_reg_get', 'ssdk_uniphy_reg_get'),
          ('mii_reg_set', 'ssdk_mii_reg_set'), ('mii_reg_get', 'ssdk_mii_reg_get')]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


reader = module('retire_lexical', REPO / 'tests/nss-dp-containment/extract_prepared_c.py')
context = module('retire_patch', REPO / 'tests/edma_patch_context.py')


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    need(root.is_dir() and not root.is_symlink(), 'regular input root')
    files = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink() and (path.is_file() or path.is_dir()), 'nonregular input')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return files


def run(argv, prefix, env=None):
    prefix.with_suffix('.argv.json').write_text(json.dumps({'argv': argv,
        'ASAN_OPTIONS': (env or {}).get('ASAN_OPTIONS'),
        'UBSAN_OPTIONS': (env or {}).get('UBSAN_OPTIONS')}) + '\n')
    process = subprocess.run(argv, capture_output=True, timeout=90, env=env)
    prefix.with_suffix('.stdout').write_bytes(process.stdout)
    prefix.with_suffix('.stderr').write_bytes(process.stderr)
    prefix.with_suffix('.exit.json').write_text(json.dumps({'returncode': process.returncode}) + '\n')
    return process


def git_blob(name):
    p = subprocess.run(['git', '-C', str(REPO), 'show', BASE + ':' + name],
                       capture_output=True, timeout=30)
    need(p.returncode == 0 and not p.stderr, 'frozen base blob')
    return p.stdout


def prepare(cache, output):
    paths = sorted((PACKAGE / 'patches').glob('*.patch'))
    old = subprocess.run(['git', '-C', str(REPO), 'ls-tree', '-r', '--name-only', BASE,
                          'package/qca-nss/qca-ssdk/patches'], capture_output=True, timeout=30)
    need(old.returncode == 0 and not old.stderr, 'old patch names')
    names = old.stdout.decode().splitlines()
    need(len(names) == 38 and [str(p.relative_to(REPO)) for p in paths[:-1]] == names and
         paths[-1].name == PATCH, '38 fixed layers plus051 only')
    for path in paths[:-1]:
        need(path.read_bytes() == git_blob(path.relative_to(REPO).as_posix()), 'historical patch drift')
    need(re.search(r'^PKG_SOURCE_VERSION:=' + PIN + '$', (PACKAGE / 'Makefile').read_text(), re.M),
         'fixed vendor pin')
    arc = subprocess.run(['git', '-C', str(cache), 'archive', '--format=tar', PIN],
                         capture_output=True, timeout=60)
    need(arc.returncode == 0 and not arc.stderr, 'vendor git archive')
    (output / 'upstream.tar').write_bytes(arc.stdout)
    tree = output / 'prepared'; tree.mkdir()
    with tarfile.open(fileobj=io.BytesIO(arc.stdout)) as tar:
        seen = set()
        for member in tar:
            name = PurePosixPath(member.name)
            need(not name.is_absolute() and '..' not in name.parts and '.git' not in name.parts and
                 (member.isfile() or member.isdir()) and str(name) not in seen, 'archive member')
            seen.add(str(name)); dest = tree / str(name)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(tar.extractfile(member).read())
    derived = inventory(tree)
    records = []
    baseline = None
    for number, path in enumerate(paths):
        if path.name == PATCH:
            baseline = {rel: (tree / rel).read_bytes() for rel in derived}
        data = path.read_bytes()
        expected, declared = context.inspect_patch(tree, data)
        # Set cwd explicitly; never search/reapply shifted hunks.
        p = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-V', 'none', '-i', str(path)],
                           cwd=tree, capture_output=True, timeout=30)
        (output / (path.name + '.stdout')).write_bytes(p.stdout)
        (output / (path.name + '.stderr')).write_bytes(p.stderr)
        need(p.returncode == 0 and not p.stderr and not re.search(
             rb'offset|fuzz|FAILED|Reversed|reject', p.stdout, re.I), 'exact replay:' + path.name)
        context.verify_applied(tree, expected)
        derived.update({rel: sha(raw) for rel, raw in expected.items()})
        need(inventory(tree) == derived, 'whole tree replay drift')
        records.append({'name': path.name, 'sha256': sha(data), 'declared': declared})
    need(len(derived) == 692 and baseline is not None and
         {rel for rel, raw in baseline.items() if sha(raw) != derived[rel]} ==
         {'src/sal/sd/sd.c', 'src/init/ssdk_init.c', 'src/hsl/hsl_dev.c', 'include/sal/sd/sd.h'},
         '051 exact four-file delta')
    return tree, baseline, records, derived


def from_prepared(baseline, prepared, output):
    before = inventory(baseline)
    need(len(before) == 692 and sha(json.dumps(before, sort_keys=True, separators=(',', ':')).encode()) ==
         BASE_INVENTORY, 'frozen accepted38 baseline692')
    data = (PACKAGE / 'patches' / PATCH).read_bytes()
    delta, declared = context.inspect_patch(baseline, data)
    expected = dict(before, **{name: sha(raw) for name, raw in delta.items()})
    actual = inventory(prepared)
    need(actual == expected, 'actual full candidate39 differs from accepted38 plus051')
    tree = output / 'prepared'; tree.mkdir()
    old = {}
    for name in before:
        old[name] = (baseline / name).read_bytes()
        target = tree / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((prepared / name).read_bytes())
    need(inventory(tree) == expected, 'actual39 snapshot')
    return tree, old, [{'name': PATCH, 'sha256': sha(data), 'declared': declared}], expected


def typedef(text, name):
    pattern = r'\btypedef\s+(?:struct|enum)\s*\{[^{}]*\}\s*' + name + r'\s*;'
    found = re.findall(pattern, text)
    need(len(found) == 1, 'actual typedef ' + name)
    return found[0]


def render(tree, sd=None, root=None, sd_init=None, root_init=None, hsl_admit=None):
    header = (tree / 'include/init/ssdk_init.h').read_text()
    typedefs = header[header.index('    typedef sw_error_t\n    (*mdio_reg_set)'):
                      header.index('/*qca808x_start*/\nenum ssdk_port_wrapper_cfg')]
    types = typedef((tree / 'include/common/sw_error.h').read_text(), 'sw_error_t')
    types += '\n' + typedef((tree / 'include/sal/os/aos_types.h').read_text(), 'a_bool_t')
    types += '\n' + typedef((tree / 'include/hsl/phy/hsl_phy.h').read_text(), 'phy_type_t')
    types += '\n' + typedefs + '\n' + typedef(header, 'hsl_reg_func')
    types += '\n' + typedef(header, 'ssdk_chip_type')
    config = (tree / 'include/common/sw_config.h').read_text()
    cap = re.findall(r'^#define SW_MAX_NR_DEV\s+\d+\s*$', config, re.M)
    need(len(cap) == 1, 'actual device capacity'); types += '\n' + cap[0]
    sd_text = (tree / 'src/sal/sd/sd.c').read_text()
    globals_c = sd_text[sd_text.index('mdio_reg_set ssdk_mdio_set'):sd_text.index('/*qca808x_start*/\nsw_error_t')]
    callbacks, install, checks, resets = [], [], [], []
    for index, (field, global_name) in enumerate(FIELDS):
        typematch = re.findall(r'\b(\w+)\s+' + field + r'\s*;', typedef(header, 'hsl_reg_func'))
        need(len(typematch) == 1, 'actual field type'); kind = typematch[0]
        match = re.search(r'typedef\s+(sw_error_t|void|a_uint32_t)\s+\(\*' + kind +
                          r'\)\s*\(([^;]+)\);', typedefs)
        need(match is not None, 'actual callback prototype')
        ret, params = match.groups()
        args = re.findall(r'\b(\w+)\s*(?:,|$)', params)
        for suffix in ('a', 'b'):
            body = 'check(false, "unexpected-provider-dispatch");' + ''.join('(void)' + arg + ';' for arg in args)
            body += '' if ret == 'void' else 'return 0;'
            callbacks.append(f'static {ret} cb_{index}_{suffix}({params}) {{{body}}}')
        install.append(f'case {index}: c->reg_func.{field} = other ? cb_{index}_b : cb_{index}_a; break;')
        checks.append(f'check({global_name} == c->reg_func.{field}, "publication-snapshot");')
        resets.append(f'{global_name} = NULL;')
    helpers = ('static void install_field(ssdk_init_cfg *c, unsigned field, bool other) { switch(field) {' +
               ''.join(install) + 'default: check(false, "field");}}\n' +
               'static void install_full(ssdk_init_cfg *c, bool other) { for(unsigned i=0;i<12;i++) install_field(c,i,other);}\n' +
               'static void check_sd(const ssdk_init_cfg *c) {' + ''.join(checks) + '}\n' +
               'static void reset_sd(void) {' + ''.join(resets) + '}\n')
    text = (REPO / 'tests/ssdk-retirement-admission/fixture.c').read_text()
    values = {'SDK_TYPES': types, 'SD_CALLBACKS': '\n'.join(callbacks), 'SD_GLOBALS': globals_c,
              'SD_CHECK': sd if sd is not None else reader.function(sd_text, 'sd_init_check'),
              'SD_INIT': sd_init if sd_init is not None else reader.function(sd_text, 'sd_init'),
              'SD_HELPERS': helpers,
              'HSL_CLEANUP': reader.function((tree / 'src/hsl/hsl_dev.c').read_text(), 'hsl_dev_cleanup_core'),
              'PHY_CLEANUP': reader.function((tree / 'src/hsl/phy/hsl_phy.c').read_text(), 'ssdk_phy_driver_cleanup'),
              'ROOT_CLEANUP': root if root is not None else reader.function((tree / 'src/init/ssdk_init.c').read_text(), 'ssdk_cleanup'),
              'ROOT_INIT': root_init if root_init is not None else reader.function((tree / 'src/init/ssdk_init.c').read_text(), 'ssdk_init'),
              'HSL_INIT_AVAILABLE': hsl_admit if hsl_admit is not None else reader.function((tree / 'src/hsl/hsl_dev.c').read_text(), 'hsl_dev_init_available'),
              'HSL_HPPE_REQUEST': '#ifdef HPPE\n' + reader.function((tree / 'src/hsl/hsl_dev.c').read_text(), 'hsl_dev_hppe_request') + '#endif\n'}
    for key, value in values.items():
        need(text.count('/* @' + key + '@ */') == 1, 'fixture slot')
        text = text.replace('/* @' + key + '@ */', value)
    need('/* @' not in text, 'unfilled fixture')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path)
    parser.add_argument('--baseline38', type=Path)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--hppe', action='store_true')
    args = parser.parse_args()
    need(not args.output.exists(), 'fresh output required'); args.output.mkdir(parents=True)
    report = {'status': 'INCOMPLETE', 'qualification': 'SERIAL_NATIVE_HOST_NOT_TARGET_OR_RUNTIME'}
    inputs = [Path(__file__).resolve(), REPO / 'tests/ssdk-retirement-admission/fixture.c',
              REPO / 'tests/nss-dp-containment/extract_prepared_c.py',
              REPO / 'tests/edma_patch_context.py', PACKAGE / 'Makefile',
              *sorted((PACKAGE / 'patches').glob('*.patch'))]
    identities = {str(path): sha(path.read_bytes()) for path in inputs}
    report.update(inputs=identities, profile='HPPE_UK' if args.hppe else 'NON_HPPE_UK')
    result = args.output / 'RESULTS.json'
    def save():
        result.write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        need(bool(args.upstream_cache) != bool(args.baseline38 and args.prepared), 'exclusive archive or actual mode')
        need(bool(args.baseline38) == bool(args.prepared), 'actual mode requires frozen baseline')
        actual_before = inventory(args.prepared) if args.prepared else None
        base_before = inventory(args.baseline38) if args.baseline38 else None
        tree, old, patches, expected = (from_prepared(args.baseline38, args.prepared, args.output)
            if args.prepared else prepare(args.upstream_cache, args.output))
        report.update(patches=patches, prepared_inventory=expected)
        # The old SDK sd_init has an unused dev_id; keep its body unchanged.
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-O1', '-g']
        if args.hppe:
            flags += ['-DHPPE=1']
        import os
        env = dict(os.environ)
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            env.update(ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1:exitcode=98')
            report['sanitizer_canaries'] = []
            for label, body, expected_code, diagnostic in [
                ('asan', '#include <stdlib.h>\nint main(int argc,char **argv) {(void)argv; volatile int i=argc; char *p=malloc(1); p[i]=1; volatile char x=p[i]; free(p); return x;}\n',
                 97, b'ERROR: AddressSanitizer: heap-buffer-overflow'),
                ('ubsan', '#include <limits.h>\nint main(int argc,char **argv) {(void)argv; volatile int i=INT_MAX; return i+argc;}\n',
                 98, b'runtime error: signed integer overflow'),
            ]:
                path = args.output / ('canary-' + label + '.c'); path.write_text(body)
                binary = path.with_suffix('.host')
                compiled = run([args.cc, *flags, str(path), '-o', str(binary)],
                               args.output / ('canary-' + label + '-compile'), env)
                need(compiled.returncode == 0 and not compiled.stdout and not compiled.stderr, 'canary compile')
                # Darwin's combined runtime may honor the other sanitizer's exitcode.
                # Both controls must specify this canary's fixed expected exit.
                probe_env = dict(env)
                probe_env.update(ASAN_OPTIONS=f'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode={expected_code}',
                                 UBSAN_OPTIONS=f'halt_on_error=1:print_stacktrace=1:exitcode={expected_code}')
                executed = run([str(binary)], args.output / ('canary-' + label + '-run'), probe_env)
                need(executed.returncode == expected_code and not executed.stdout and
                     diagnostic in executed.stderr, 'active sanitizer canary')
                report['sanitizer_canaries'].append({'name': label, 'exit': expected_code,
                                                     'diagnostic': diagnostic.decode()})
            save()
        sd = reader.function((tree / 'src/sal/sd/sd.c').read_text(), 'sd_init_check')
        root = reader.function((tree / 'src/init/ssdk_init.c').read_text(), 'ssdk_cleanup')
        variants = [('positive', render(tree), None)]
        for field, global_name in FIELDS:
            clause = f'    if (cfg->reg_func.{field} && {global_name} &&\n        cfg->reg_func.{field} != {global_name})\n        return SW_BUSY;\n'
            need(sd.count(clause) == 1, 'unique typed guard')
            variants.append(('omit-' + field, render(tree, sd=sd.replace(clause, '', 1)), 'conflict-error'))
        variants.append(('late-failure', render(tree, root=root.replace('\t\treturn rv;\n', '', 1)),
                         'fal-failure-retains-phy'))
        early = '    if (!ssdk_mdio_set) ssdk_mdio_set = cfg->reg_func.mdio_set;\n'
        # Place a real publication after argument admission but before conflict checks.
        site = '        return SW_BAD_PTR;\n'
        need(sd.count(site) == 1, 'unique argument admission')
        variants.append(('early-publication', render(tree, sd=sd.replace(site, site + early, 1)),
                         'publication-snapshot'))
        for label, pattern, replacement, marker in [
            ('clear-nulls', '    return SW_OK;', '    ssdk_mdio_set = cfg->reg_func.mdio_set;\n    return SW_OK;', 'publication-snapshot'),
            ('invalid-id', '    if (dev_id >= SW_MAX_NR_DEV)\n        return SW_BAD_PARAM;\n', '', 'invalid-device'),
        ]:
            need(sd.count(pattern) == 1, 'unique mutant site')
            variants.append((label, render(tree, sd=sd.replace(pattern, replacement, 1)), marker))
        for label, key, text, clause, marker in [
            ('omit-sd-admission', 'sd_init', reader.function((tree / 'src/sal/sd/sd.c').read_text(), 'sd_init'),
             '    SW_RTN_ON_ERROR(rv);', 'invalid-device'),
            ('omit-hsl-admission', 'hsl_admit', reader.function((tree / 'src/hsl/hsl_dev.c').read_text(), 'hsl_dev_init_available'),
             '        SW_RTN_ON_ERROR(rv);', 'hsl-conflict-before-api-reset'),
            ('omit-root-admission', 'root_init', reader.function((tree / 'src/init/ssdk_init.c').read_text(), 'ssdk_init'),
             '\tSW_RTN_ON_ERROR(rv);', 'root-conflict-before-fal-and-phy'),
            ('omit-root-device', 'root', root,
             '\tif (dev_id >= SW_MAX_NR_DEV)\n\t\treturn SW_BAD_PARAM;\n', 'invalid-cleanup-no-global-retirement'),
        ]:
            need(text.count(clause) >= 1, 'admission mutant site')
            # Preserve evaluating the real check, but reject ignoring its result.
            replacement = '(void)rv;' if 'SW_RTN' in clause else ''
            variants.append((label, render(tree, **{key: text.replace(clause, replacement, 1)}), marker))
        variants.append(('old-sd', render(tree, sd_init=reader.function(old['src/sal/sd/sd.c'].decode(), 'sd_init')), 'conflict-error'))
        variants.append(('old-root', render(tree, root=reader.function(old['src/init/ssdk_init.c'].decode(), 'ssdk_cleanup')), 'emulation-device'))
        report['native'] = []
        for label, code, marker in variants:
            path = args.output / (label + '.c'); path.write_text(code)
            binary = path.with_suffix('.host')
            compiled = run([args.cc, *flags, str(path), '-o', str(binary)], args.output / (label + '-compile'), env)
            need(compiled.returncode == 0 and not compiled.stdout and not compiled.stderr,
                 'clean compile required:' + label)
            executed = run([str(binary), *(['conflict'] if label == 'old-sd' else [])],
                           args.output / (label + '-run'), env)
            if marker is None:
                need(executed.returncode == 0 and not executed.stderr and
                     json.loads(executed.stdout) == {'status': 'PASS', 'cases': 266, 'shared_uk_order': 'OPEN'},
                     'positive fixed cases')
            else:
                need(executed.returncode == 86 and not executed.stdout and
                     executed.stderr == ('RETIRE:' + marker + '\n').encode(), 'exact runtime negative:' + label)
            report['native'].append({'name': label, 'marker': marker, 'code_sha256': sha(path.read_bytes()),
                                     'returncode': executed.returncode})
            save()
        need(inventory(tree) == expected, 'prepared end stability')
        if args.prepared:
            need(inventory(args.prepared) == actual_before and inventory(args.baseline38) == base_before,
                 'actual/baseline end stability')
        need(all(sha(Path(name).read_bytes()) == digest for name, digest in identities.items()),
             'test/source input changed during execution')
        report['status'] = 'PASS_LOCAL_ONLY'
        save()
        print(json.dumps({'status': report['status'], 'variants': len(variants), 'report': str(result)}))
    except Exception as error:
        report['error'] = str(error); save(); raise


if __name__ == '__main__':
    main()
