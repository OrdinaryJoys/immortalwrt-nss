#!/usr/bin/env python3
"""TESTONLY: qualify 014 TX against a freshly replayed, frozen 001-015 tree."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from edma_patch_context import inspect_patch, verify_applied

SOURCE = Path(__file__).resolve().parents[1]
EVIDENCE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2')
PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
ACCEPTED_TX_REF = '914fa57048d6e543d7aef46c1b0de5d4eb4669dd'
REL = Path('hal/dp_ops/edma_dp/edma_v1')
PATCHES = SOURCE / 'package/qca-nss/qca-nss-dp/patches'
PATCH14 = '014-edma-v1-pair-tx-slot-ownership.patch'
PATCH15 = '015-edma-v1-retire-probe-and-host-napi-owners.patch'
TX_RUNNER = SOURCE / 'tests/test-edma-tx-slot-ownership.py'
TX_FIXTURE = SOURCE / 'tests/edma-tx-slot-ownership/fixture.c'
README = SOURCE / 'tests/edma-phase2-integration/README.md'
CPU_FIELDS = (
    'struct net_device *napi_dev;',
    'bool napi_enabled;',
    'bool host_open[EDMA_MAX_GMACS];',
    'bool override_accounted[EDMA_MAX_GMACS];',
    'uint32_t tx_irqs_owned;',
    'uint32_t rxfill_irqs_owned;',
    'uint32_t rxdesc_irqs_owned;',
    'bool misc_irq_owned;',
)
EXPECTED_FUNCTIONS = {
    'edma_tx_slot_take', 'edma_clean_tx', 'edma_ring_xmit', 'edma_if_xmit',
    'edma_setup_txdesc_ring_res', 'edma_setup_txcmpl_ring_res',
    'edma_configure_rings', 'edma_cleanup_txdesc_ring_res',
    'edma_cleanup_txcmpl_ring_res',
}
EXPECTED_MUTANTS = {
    'producer-per-ring-only', 'take-without-common-lock', 'no-clear',
    'wrong-length', 'wrong-ring-owner', 'omit-owner-check',
    'teardown-no-owner', 'reload-shared-dma', 'skip-zero-unmap',
    'skip-txcmpl-clean', 'omit-lock-init', 'bad-map-error-unlock',
    'bad-padding-unlock', 'wrong-unmap-device', 'wrong-txdesc-length',
    'truncate-stored-dma',
}
FLAGS = [
    '-std=gnu11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
    '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable',
    '-Wno-sign-compare',
]
SANITIZER_FLAGS = [
    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
    '-fno-omit-frame-pointer',
]
SUITE = re.compile(
    r'cases=(\d+) checks=(\d+) maps=(\d+) unmaps=(\d+) '
    r'zero_unmaps=(\d+) frees=(\d+)\n'
)


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def clean_command(command):
    result = subprocess.run(command, capture_output=True, timeout=90)
    require(result.returncode == 0 and not result.stderr,
            'read command failed: ' + shlex.join(map(str, command)))
    return result.stdout


def identities(paths):
    return {str(path): sha(path.read_bytes()) for path in paths}


def unchanged_inputs(paths, initial, patches):
    require(selected_patches() == patches,
            'patch directory inventory changed after freeze capture')
    require(identities(paths) == initial, 'bound repository inputs changed')


def selected_patches():
    return [p for p in sorted(PATCHES.glob('*.patch'))
            if re.match(r'^\d{3}-',p.name) and int(p.name[:3]) <= 15]


def file_hashes(root):
    return {str(p.relative_to(root)): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def load_tx():
    spec = importlib.util.spec_from_file_location('edma_repo_tx_integration', TX_RUNNER)
    require(spec is not None and spec.loader is not None, 'TX helper import spec')
    tx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tx)
    require(tx.PIN == PIN and tx.SOURCE == SOURCE and tx.TEMPLATE == TX_FIXTURE,
            'only current repository TX helper/fixture may be reused')
    require({name for names in tx.NAMES.values() for name in names}
            == EXPECTED_FUNCTIONS, 'TX extraction scope drift; review required')
    return tx


def prepare(cache, output, patches, expected):
    require(clean_command(['git', '-C', str(cache), 'rev-parse', PIN + '^{commit}'])
            .decode().strip() == PIN, 'upstream pin identity')
    archive = clean_command(['git', '-C', str(cache), 'archive', PIN])
    (output / 'upstream.tar').write_bytes(archive)
    manifest = {'pin': PIN, 'git_archive_sha256': sha(archive), 'patches': [],
                'method': 'full fresh package replay, --fuzz=0; offsets forbidden'}
    roots = {name: output / name for name in ('before15', 'after15')}
    for root in roots.values():
        root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            members = tar.getmembers()
            require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute()
                        and '..' not in Path(m.name).parts for m in members),
                    'archive links or unsafe member path')
            require(len({m.name.casefold() for m in members}) == len(members),
                    'duplicate/case-colliding archive member')
            tar.extractall(root)
    manifest['raw_files'] = file_hashes(roots['before15'])
    saved_dir = output / 'patches'
    saved_dir.mkdir()
    for patch in patches:
        data = patch.read_bytes()
        require(sha(data) == expected[str(patch)],
                'patch changed after identity capture: ' + patch.name)
        saved = saved_dir / patch.name
        saved.write_bytes(data)
        entry = {'path': str(patch), 'saved': str(saved), 'sha256': sha(data),
                 'replays': {}}
        manifest['patches'].append(entry)
        # Persist partial preparation evidence even if a later patch fails.
        write_json(output / 'INPUTS.json', manifest)
        targets = ('after15',) if patch.name == PATCH15 else ('before15', 'after15')
        for name in targets:
            expected_bytes, context = inspect_patch(roots[name],data)
            entry.setdefault('declared_context',{})[name] = context
            command = ['/usr/bin/patch', '-p1', '--fuzz=0', '--batch',
                       '-V', 'none', '-i', str(saved)]
            stem = name + '-' + patch.name
            try:
                p = subprocess.run(command, cwd=roots[name], capture_output=True,
                                   text=True, timeout=90)
                rc, stdout, stderr = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as exc:
                rc = 'timeout'
                stdout = exc.stdout or ''
                stderr = exc.stderr or ''
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors='replace')
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors='replace')
            (output / (stem + '.stdout')).write_text(stdout)
            (output / (stem + '.stderr')).write_text(stderr)
            entry['replays'][name] = {'command': shlex.join(command),
                                      'returncode': rc,
                                      'stdout_sha256': sha(stdout.encode()),
                                      'stderr_sha256': sha(stderr.encode())}
            write_json(output / 'INPUTS.json', manifest)
            require(rc == 0 and not stderr and
                    not re.search(r'fuzz|offset|FAILED|Reversed|previously applied|'
                                  r'reject|malformed|saving rejects|skipping',
                                  stdout + stderr, re.I),
                    'nonexact full-package replay: ' + name + '/' + patch.name)
            verify_applied(roots[name],expected_bytes)
    manifest['prepared_files'] = {name: file_hashes(root)
                                  for name, root in roots.items()}
    require(all(not list(root.rglob('*.rej')) and not list(root.rglob('*.orig'))
                for root in roots.values()), 'patch rejection/backup artifacts')
    before, after = (manifest['prepared_files'][name] for name in roots)
    manifest['changed_by_015'] = [p for p in sorted(set(before) | set(after))
                                  if before.get(p) != after.get(p)]
    write_json(output / 'INPUTS.json', manifest)
    return roots, manifest


def canonical(tx, text):
    return re.sub(r'\s+', '', tx.mask(text))


def calls_to(tx, text, target):
    clean = tx.mask(text)
    found = []
    for match in re.finditer(r'\b' + re.escape(target) + r'\s*\(', clean):
        depth, end = 1, match.end()
        while depth and end < len(clean):
            depth += (clean[end] == '(') - (clean[end] == ')')
            end += 1
        require(depth == 0, 'unterminated call to ' + target)
        found.append(text[match.start():end])
    return found


def structure(tx, text, name):
    clean = tx.mask(text)
    matches = list(re.finditer(r'\bstruct\s+' + re.escape(name) + r'\s*\{', clean))
    require(len(matches) == 1, 'ambiguous struct ' + name)
    start, end, depth = matches[0].start(), matches[0].end(), 1
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    require(depth == 0, 'unterminated struct ' + name)
    return clean[start:end]


def header_contract(tx, roots):
    before, after = (roots[name] for name in ('before15', 'after15'))
    hw = [(root / REL / 'edma_data_plane.h').read_text() for root in (before, after)]
    reduced = tx.mask(hw[1])
    owner = structure(tx, hw[1], 'edma_hw')
    for field in CPU_FIELDS:
        pattern = re.escape(field).replace(r'\ ', r'\s+')
        require(len(re.findall(pattern, owner)) == 1 and
                not re.search(pattern, tx.mask(hw[0])),
                'unreviewed/missing CPU lifecycle header field: ' + field)
        reduced, count = re.subn(pattern, '', reduced)
        require(count == 1, 'CPU field outside edma_hw or duplicated: ' + field)
    annotation = r'struct\s+net_device\s+__rcu\s*\*netdev_arr\[EDMA_MAX_GMACS\];'
    require(len(re.findall(annotation, owner)) == 1, 'netdev_arr RCU annotation')
    reduced, count = re.subn(annotation,
                            'struct net_device *netdev_arr[EDMA_MAX_GMACS];', reduced)
    require(count == 1 and canonical(tx, reduced) == canonical(tx, hw[0]),
            '015 changed TX/wire declarations or unapproved header content')
    require(structure(tx, hw[0], 'edma_tx_slot') ==
            structure(tx, hw[1], 'edma_tx_slot'), '014 tuple declaration changed')
    arch_rel = Path('hal/soc_ops/ipq807x/nss_ipq807x.h')
    arch = [(root / arch_rel).read_text() for root in (before, after)]
    declarations = ('struct net_device;',
                    'bool edma_retire_port(struct net_device *netdev, uint32_t macid);')
    reduced = tx.mask(arch[1])
    for declaration in declarations:
        pattern = re.escape(declaration).replace(r'\ ', r'\s+')
        reduced, count = re.subn(pattern, '', reduced)
        require(count == 1 and not re.search(pattern, tx.mask(arch[0])),
                'unexpected arch header lifecycle declaration')
    require(canonical(tx, reduced) == canonical(tx, arch[0]),
            'architecture parameters/declarations changed beyond retire prototype')
    regs = [root / REL / 'edma_regs.h' for root in (before, after)]
    require(regs[0].read_bytes() == regs[1].read_bytes(), 'descriptor register header drift')
    return {'allowed_added_CPU_fields': list(CPU_FIELDS),
            'allowed_arch_declarations': list(declarations),
            'host_annotation_model': '#define __rcu; annotation erasure ONLY, not RCU validation',
            'tuple_and_register_declarations_unchanged': True}


def extract_contract(tx, roots, output):
    extracted, fragments, bodies, calls = {}, {}, {}, {}
    for stage, root in roots.items():
        headers, functions, records = tx.extract(root, True)
        extracted[stage] = (headers, functions)
        fragments[stage] = records
        dest = output / (stage + '-functions')
        dest.mkdir()
        bodies[stage] = dict(functions)
        cfg = (root / REL / 'edma_cfg.c').read_text()
        names = re.findall(r'^(?:static )?(?:int|void|bool|uint32_t) '
                           r'(edma_\w+)\([^;{}]*\)\s*\{', tx.mask(cfg), re.M)
        require(names and len(names) == len(set(names)), 'complete config function inventory')
        for name in names:
            code, line = tx.definition(cfg, name)
            bodies[stage][name] = code
            records.append({'path': str(root / REL / 'edma_cfg.c'),
                            'function': name, 'line': line, 'sha256': sha(code.encode()),
                            'kind': 'complete config/setup/ring-teardown body; identity only unless in TX fixture'})
        for name, code in bodies[stage].items():
            (dest / (name + '.c.txt')).write_text(code + '\n')
        napi, line = tx.definition((root / REL / 'edma_tx_rx.c').read_text(), 'edma_napi')
        (dest / 'edma_napi.c.txt').write_text(napi + '\n')
        records.append({'path': str(root / REL / 'edma_tx_rx.c'), 'function': 'edma_napi',
                        'line': line, 'sha256': sha(napi.encode()),
                        'kind': 'complete changed poll body saved; TX call identity only, not executed'})
        plane = (root / REL / 'edma_data_plane.c').read_text()
        for name in (('edma_cleanup',) if stage == 'before15' else
                     ('edma_cleanup', 'edma_cleanup_locked')):
            code, line = tx.definition(plane, name)
            (dest / (name + '.c.txt')).write_text(code + '\n')
            records.append({'path': str(root / REL / 'edma_data_plane.c'),
                            'function': name, 'line': line, 'sha256': sha(code.encode()),
                            'kind': 'complete lifecycle caller saved, NOT hash-equal or runtime-qualified'})
        binding = re.findall(r'\.xmit\s*=\s*edma_if_xmit\b', tx.mask(plane))
        require(len(binding) == 1, 'actual dataplane .xmit registration missing/duplicated')
        calls[stage] = {'xmit_registration': binding,
                        'edma_napi_to_clean_tx': calls_to(tx, napi, 'edma_clean_tx')}
        require(len(calls[stage]['edma_napi_to_clean_tx']) == 1, 'poll -> TX cleanup call')
        edges = {
            'edma_if_xmit': ['edma_ring_xmit'],
            'edma_clean_tx': ['edma_tx_slot_take'],
            'edma_cleanup_txdesc_ring_res': ['edma_tx_slot_take'],
            'edma_cleanup_txcmpl_ring_res': ['edma_clean_tx'],
            'edma_cleanup_rings': ['edma_cleanup_txdesc_ring_res', 'edma_cleanup_txcmpl_ring_res'],
            'edma_setup_ring_resources': ['edma_setup_txdesc_ring_res', 'edma_setup_txcmpl_ring_res'],
        }
        for caller, targets in edges.items():
            for target in targets:
                hits = calls_to(tx, bodies[stage][caller], target)
                require(hits, 'missing TX call edge: ' + caller + ' -> ' + target)
                calls[stage][caller + ' -> ' + target] = hits
        write_json(output / (stage + '-FRAGMENTS.json'), records)
    before, after = (roots[name] for name in ('before15', 'after15'))
    require((before / REL / 'edma_cfg.c').read_bytes() ==
            (after / REL / 'edma_cfg.c').read_bytes(), '015 changed complete config/setup/teardown file')
    require(bodies['before15'] == bodies['after15'], '014 TX/config function body hash drift under 015')
    normalized = {stage: {name: [canonical(tx, text) for text in value]
                           for name, value in edges.items()}
                  for stage, edges in calls.items()}
    require(normalized['before15'] == normalized['after15'], '014 TX call contract changed')
    comparisons = {name: {'before15': sha(code.encode()),
                          'after15': sha(bodies['after15'][name].encode()), 'equal': True}
                   for name, code in bodies['before15'].items()}
    write_json(output / 'FUNCTION-COMPARISON.json', comparisons)
    write_json(output / 'CALL-CONTRACT.json', calls)
    write_json(output / 'HEADER-CONTRACT.json', header_contract(tx, roots))
    return extracted


def suite_summary(result):
    require(result['returncode'] == 0 and not result['stderr'], 'positive suite exit/stderr gate')
    match = SUITE.fullmatch(result['stdout'])
    require(match is not None, 'complete TX suite summary missing')
    values = dict(zip(('cases', 'checks', 'maps', 'unmaps', 'zero_unmaps', 'frees'),
                      map(int, match.groups())))
    require(values['cases'] >= 74 and values['checks'] > 0 and
            values['maps'] == values['unmaps'] > 0 and
            values['zero_unmaps'] > 0 and values['frees'] >= values['maps'],
            'TX suite coverage/ledger summary')
    return values


def compiler_suite(tx, compiler, sanitize, output, extracted):
    output.mkdir()
    version = clean_command([compiler, '--version']).decode()
    require(('clang' in version.lower()) if sanitize else
            ('gcc' in version.lower() and 'clang' not in version.lower()),
            'requested GCC/Clang compiler family does not match executable')
    flags = FLAGS + (SANITIZER_FLAGS if sanitize else [])
    env = dict(os.environ,
               ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=97',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1:abort_on_error=0:exitcode=97')
    result = {'compiler': compiler, 'version': version, 'flags': flags,
              'compiler_realpath': str(Path(compiler).resolve()),
              'compiler_sha256': sha(Path(compiler).resolve().read_bytes()),
              'annotation_model': '#define __rcu (empty); no RCU behavior tested',
              'env': {k: env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS')},
              'runs': {}, 'mutants': {}, 'sanitizer_canaries': {}}

    def save():
        write_json(output / 'RESULTS.json', result)

    def build(name, text):
        src, binary = output / (name + '.c'), output / name
        src.write_text(text)
        p = tx.run([compiler, *flags, '-DCANDIDATE=1', src, '-o', binary],
                   output, name + '.compile')
        result.setdefault('compiles', {})[name] = {
            'source_sha256': sha(src.read_bytes()), **p}
        save()
        require(p['returncode'] == 0 and not p['stdout'] and not p['stderr'],
                'compile must succeed diagnostic-free: ' + name)
        result['compiles'][name]['binary_sha256'] = sha(binary.read_bytes())
        save()
        return binary

    def run(name, binary, mode):
        p = tx.run([binary, *mode], output, name, env)
        result['runs'][name] = p
        save()
        return p

    try:
        traces = {}
        for stage, (headers, funcs) in extracted.items():
            text = '#define __rcu\n' + tx.fixture(headers, funcs, True)
            binary = build(stage + '-fixture', text)
            p = run(stage + '.trace', binary, ['trace'])
            require(p['returncode'] == 0 and not p['stderr'] and p['stdout'],
                    'positive successful trace gate: ' + stage)
            traces[stage] = p['stdout']
            if stage == 'after15':
                result['suite'] = suite_summary(run(stage + '.suite', binary, ['suite']))
        require(traces['before15'] == traces['after15'], 'before15/after15 successful trace drift')
        result['successful_trace_sha256'] = sha(traces['after15'].encode())
        headers, funcs = extracted['after15']
        variants = tx.mutants(funcs)
        require(set(variants) == EXPECTED_MUTANTS, 'exact existing 16 TX mutants required')
        for name, (changed, marker) in variants.items():
            binary = build('mutant-' + name,
                           '#define __rcu\n' + tx.fixture(headers, changed, True))
            p = run('mutant-' + name, binary, ['suite'])
            # A signal, sanitizer, timeout, compile error or unrelated assertion is NOT a kill.
            require(p['returncode'] == 86 and not p['stdout'] and
                    p['stderr'] == 'EDMA_TX_CONTRACT ' + marker + '\n',
                    'mutant requires exact intended semantic rejection: ' + name)
            result['mutants'][name] = {'marker': marker, 'rejection': p}
            save()
        if sanitize:
            canaries = (
                ('asan', '#include <stdlib.h>\nint main(void){volatile int i=2;'
                 'volatile int *p=malloc(sizeof(int));p[i]=1;free((void *)p);return 0;}\n',
                 'AddressSanitizer', 97),
                ('ubsan', 'int main(void){volatile int i=32;return 1<<i;}\n',
                 'runtime error:', 97),
            )
            for name, code, marker, exitcode in canaries:
                binary = build('canary-' + name, code)
                p = run('canary-' + name, binary, [])
                require(p['returncode'] == exitcode and marker in p['stderr'] and
                        not p['stdout'], 'sanitizer activation canary failed: ' + name)
                result['sanitizer_canaries'][name] = p
        result['status'] = 'PASS_TX_ONLY'
        return result
    except Exception as exc:
        result['status'] = 'FAIL'
        result['error'] = str(exc)
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gcc', required=True)
    parser.add_argument('--clang', required=True)
    parser.add_argument('--frozen-015-sha256', required=True,
                        help='Only supply the SHA explicitly released by the parent after freeze')
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f]{64}', args.frozen_015_sha256) is not None,
            'a parent-confirmed frozen 015 SHA256 is mandatory; do not run WIP')
    patches = selected_patches()
    require(len(patches) == 15 and
            [int(p.name[:3]) if re.match(r'^\d{3}-', p.name) else -1 for p in patches]
            == list(range(1, 16)) and patches[-2].name == PATCH14 and
            patches[-1].name == PATCH15, 'exact ordered package patches 001-015 required')
    require(sha(patches[-1].read_bytes()) == args.frozen_015_sha256,
            '015 does not match parent-confirmed freeze; do not run WIP')
    recipe = SOURCE / 'package/qca-nss/qca-nss-dp/Makefile'
    require(re.search(r'^PKG_SOURCE_VERSION:=' + PIN + r'\s*$',
                      recipe.read_text(), re.M), 'current recipe is not exact d8f train')
    output = args.output.resolve()
    require(output.parent == EVIDENCE.resolve() and
            output.name.startswith('EDMA-INTEGRATION-'), 'evidence output scope')
    bound = [Path(__file__).resolve(), README, TX_RUNNER, TX_FIXTURE, recipe,
             SOURCE/'tests/edma_patch_context.py', *patches]
    initial = identities(bound)
    require(initial[str(patches[-1])] == args.frozen_015_sha256,
            '015 changed during input capture; do not run WIP')
    output.mkdir(exist_ok=False)
    result = {'status': 'INCOMPLETE', 'output': str(output), 'pin': PIN,
              'parent_confirmed_015_sha256': args.frozen_015_sha256,
              'initial_source_HEAD': clean_command(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip(),
              'source_branch': clean_command(['git', '-C', str(SOURCE), 'branch', '--show-current']).decode().strip(),
              'input_identities': initial, 'compilers': {},
              'excluded_patch_names': [p.name for p in sorted(PATCHES.glob('*.patch'))
                                       if p not in patches],
              'accepted_TX_reference': ACCEPTED_TX_REF,
              'qualification': '014 TX host tuple behavior under actual 001-015 headers/source only; '
                               'NOT 015 CPU lifecycle/RCU, FW/DMA idle, target build or device acceptance'}
    try:
        for path in (TX_RUNNER, TX_FIXTURE, PATCHES / PATCH14):
            data = clean_command(['git', '-C', str(SOURCE), 'show',
                                  ACCEPTED_TX_REF + ':' + str(path.relative_to(SOURCE))])
            require(sha(data) == initial[str(path)],
                    'accepted 014/runner/fixture identity changed: ' + str(path))
        snapshots = output / 'repo-inputs'
        for path in bound:
            dest = snapshots / path.relative_to(SOURCE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
            require(sha(dest.read_bytes()) == initial[str(path)], 'snapshot changed while reading')
        tx = load_tx()
        unchanged_inputs(bound, initial, patches)
        roots, inputs = prepare(args.upstream_cache.resolve(), output, patches, initial)
        unchanged_inputs(bound, initial, patches)
        extracted = extract_contract(tx, roots, output)
        result['inputs_sha256'] = sha((output / 'INPUTS.json').read_bytes())
        write_json(output / 'RESULTS.json', result)
        for name, compiler, sanitize in (('gcc', args.gcc, False), ('clang-asan-ubsan', args.clang, True)):
            result['compilers'][name] = compiler_suite(tx, compiler, sanitize, output / name, extracted)
            write_json(output / 'RESULTS.json', result)
        require(result['compilers']['gcc']['successful_trace_sha256'] ==
                result['compilers']['clang-asan-ubsan']['successful_trace_sha256'],
                'successful trace differs between GCC and Clang')
        unchanged_inputs(bound, initial, patches)
        require({name: file_hashes(root) for name, root in roots.items()}
                == inputs['prepared_files'], 'prepared source/header drift during host execution')
        require(sha((output / 'upstream.tar').read_bytes()) == inputs['git_archive_sha256'],
                'raw upstream archive drift')
        require(all(sha(Path(item['saved']).read_bytes()) == item['sha256']
                    for item in inputs['patches']), 'saved patch data drift')
        result['final_source_HEAD'] = clean_command(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip()
        result['final_input_identities_match'] = True
        result['final_selected_patch_inventory_matches'] = True
        result['final_prepared_and_raw_input_hashes_match'] = True
        result['status'] = 'PASS_TX_ONLY'
    except Exception as exc:
        result['status'] = 'FAIL'
        result['error'] = str(exc)
        raise
    finally:
        result['evidence_files'] = file_hashes(output)
        result['evidence_files'].pop('RESULTS.json', None)
        write_json(output / 'RESULTS.json', result)
    print(json.dumps({'status': result['status'], 'output': str(output),
                      'compilers': {k: {'suite': v['suite'], 'mutants': len(v['mutants'])}
                                    for k, v in result['compilers'].items()}}))


if __name__ == '__main__':
    main()
