#!/usr/bin/env python3
"""Fresh pinned patch replay and extracted EDMA TX ownership host tests."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile

PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
REL = Path('hal/dp_ops/edma_dp/edma_v1')
PATCH = '014-edma-v1-pair-tx-slot-ownership.patch'
SOURCE = Path(__file__).resolve().parents[1]
PATCHES = SOURCE / 'package/qca-nss/qca-nss-dp/patches'
TEMPLATE = SOURCE / 'tests/edma-tx-slot-ownership/fixture.c'
NAMES = {
    'edma_tx_rx.c': ['edma_tx_slot_take', 'edma_clean_tx', 'edma_ring_xmit'],
    'edma_cfg.c': ['edma_setup_txdesc_ring_res', 'edma_setup_txcmpl_ring_res',
                   'edma_configure_rings', 'edma_cleanup_txdesc_ring_res',
                   'edma_cleanup_txcmpl_ring_res'],
    'edma_data_plane.c': ['edma_if_xmit'],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def mask(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def definition(text, name):
    clean = mask(text)
    pattern = r'^(?:static )?(?:enum edma_tx|netdev_tx_t|uint32_t|bool|void|int) ' + re.escape(name) + r'\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, clean, re.M))
    require(len(matches) == 1, 'ambiguous definition ' + name)
    m = matches[0]
    depth, end = 1, m.end()
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    require(depth == 0, 'unterminated ' + name)
    return text[m.start():end], text[:m.start()].count('\n') + 1


def once(text, before, after):
    require(text.count(before) == 1, 'mutation/instrumentation anchor: ' + before)
    return text.replace(before, after, 1)


def outside_functions(text, names):
    for name in names:
        try:
            body, _ = definition(text, name)
        except RuntimeError:
            require(name == 'edma_tx_slot_take', 'missing unchanged function ' + name)
            continue
        text = once(text, body, '')
    return re.sub(r'\s+', '', mask(text))


def run(command, output, stem, env=None, timeout=90):
    command = [str(c) for c in command]
    try:
        p = subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)
        result = {'command': shlex.join(command), 'returncode': p.returncode,
                  'stdout': p.stdout, 'stderr': p.stderr}
    except subprocess.TimeoutExpired as exc:
        result = {'command': shlex.join(command), 'returncode': 'timeout',
                  'stdout': str(exc.stdout or ''), 'stderr': str(exc.stderr or '')}
    (output / (stem + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    (output / (stem + '.stdout')).write_text(result['stdout'])
    (output / (stem + '.stderr')).write_text(result['stderr'])
    return result


def prepare(cache, output):
    archive = subprocess.run(['git', '-C', str(cache), 'archive', PIN], check=True, capture_output=True).stdout
    manifest = {'pin': PIN, 'git_archive_sha256': sha(archive), 'patches': []}
    base, candidate = output / 'baseline', output / 'candidate'
    for root in (base, candidate):
        root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(all(m.isfile() or m.isdir() for m in tar.getmembers()), 'archive contains links')
            require(all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tar.getmembers()), 'unsafe archive path')
            tar.extractall(root)
    names = sorted(p.name for p in PATCHES.glob('*.patch') if p.name[:3].isdigit() and int(p.name[:3]) <= 14)
    require(len(names) == 14 and names[-1] == PATCH, 'expected exactly patches 001-014')
    for name in names:
        data = (PATCHES / name).read_bytes()
        saved = output / name
        saved.write_bytes(data)
        targets = (candidate,) if name == PATCH else (base, candidate)
        for root in targets:
            p = subprocess.run(['/usr/bin/patch', '-p1', '--fuzz=0', '--batch', '-i', str(saved)],
                               cwd=root, capture_output=True, text=True)
            (output / (root.name + '-' + name + '.log')).write_text(p.stdout + p.stderr)
            require(p.returncode == 0 and not re.search(r'fuzz|offset|FAILED|Reversed', p.stdout + p.stderr, re.I), 'nonexact patch replay ' + name)
        manifest['patches'].append({'path': str(PATCHES / name), 'sha256': sha(data)})
    changed = []
    for f in base.rglob('*'):
        if f.is_file() and f.read_bytes() != (candidate / f.relative_to(base)).read_bytes():
            changed.append(str(f.relative_to(base)))
    require(set(changed) == {str(REL / n) for n in ['edma_cfg.c', 'edma_data_plane.h', 'edma_tx_rx.c']}, '014 target scope')
    manifest['changed_files'] = changed
    for fn, allowed in {'edma_cfg.c': ['edma_configure_rings', 'edma_cleanup_txdesc_ring_res'],
                        'edma_tx_rx.c': NAMES['edma_tx_rx.c']}.items():
        require(outside_functions((base / REL / fn).read_text(), allowed) ==
                outside_functions((candidate / REL / fn).read_text(), allowed), 'out-of-scope C code changed: ' + fn)
    hb, hc = [(root / REL / 'edma_data_plane.h').read_text() for root in (base, candidate)]
    for m in re.finditer(r'struct (\w+) \{[^{}]*\};', hb):
        if m[1] != 'edma_hw':
            require(m[0] in hc, 'existing wire/ring declaration changed: ' + m[1])
    require(re.findall(r'^#define[^\n]*', hb, re.M) == re.findall(r'^#define[^\n]*', hc, re.M), 'header macro/parameter changed')
    for fn, names in NAMES.items():
        if fn == 'edma_data_plane.c':
            require((base / REL / fn).read_bytes() == (candidate / REL / fn).read_bytes(), 'lifecycle file changed')
    manifest['prepared_hashes'] = {root.name: {str(f.relative_to(root)): sha(f.read_bytes()) for f in root.rglob('*') if f.is_file()} for root in (base, candidate)}
    (output / 'INPUTS.json').write_text(json.dumps(manifest, indent=2) + '\n')
    sites = {root.name: [{'path': str(f), 'line': i+1, 'text': line}
                        for f in (root / REL).glob('*.[ch]')
                        for i, line in enumerate(f.read_text().splitlines())
                        if re.search(r'tx_skb_store|tx_dma_store|tx_slots|tx_slot_lock|edma_tx_slot_take', line)]
             for root in (base, candidate)}
    require(not any(re.search(r'tx_skb_store|tx_dma_store', row['text']) for row in sites['candidate']), 'old split TX stores remain')
    (output / 'SOURCE-SITES.json').write_text(json.dumps(sites, indent=2) + '\n')
    return base, candidate, manifest


def extract(root, candidate):
    headers = []
    fragments = []
    for rel in [Path('hal/soc_ops/ipq807x/nss_ipq807x.h'), REL / 'edma_regs.h', REL / 'edma_data_plane.h']:
        data = (root / rel).read_text()
        headers.append(re.sub(r'^#include[^\n]*\n', '', data, flags=re.M))
        fragments.append({'path': str(root / rel), 'sha256': sha(data.encode()), 'kind': 'complete header except include directives'})
    functions = {}
    for fn, names in NAMES.items():
        text = (root / REL / fn).read_text()
        for name in names:
            if name == 'edma_tx_slot_take' and not candidate:
                continue
            code, line = definition(text, name)
            fragments.append({'path': str(root / REL / fn), 'function': name, 'line': line, 'sha256': sha(code.encode())})
            functions[name] = code
    return '\n'.join(headers), functions, fragments


def fixture(headers, funcs, candidate):
    funcs = dict(funcs)
    if candidate:
        funcs['edma_tx_slot_take'] = once(funcs['edma_tx_slot_take'], '*slot = ehw->tx_slots[index];', '*slot = ehw->tx_slots[index];\n\t\tpoint(3);')
    else:
        code = funcs['edma_clean_tx']
        code = once(code, 'ehw->tx_skb_store[store_index] = NULL;', 'ehw->tx_skb_store[store_index] = NULL;\n\t\tpoint(1);')
        code = once(code, 'daddr = ehw->tx_dma_store[store_index];', 'daddr = ehw->tx_dma_store[store_index];\n\t\tpoint(2);')
        funcs['edma_clean_tx'] = code
    text = TEMPLATE.read_text()
    text = once(text, '/* DP_HEADERS */', headers)
    text = once(text, '/* DP_FUNCTIONS */', '\n\n'.join(funcs.values()))
    return text


def mutants(functions):
    variants = {}
    def add(name, func, old, new, marker):
        f = dict(functions); f[func] = once(f[func], old, new); variants[name] = (f, marker)
    f = dict(functions)
    f['edma_ring_xmit'] = f['edma_ring_xmit'].replace('&ehw->tx_slot_lock', '&txdesc_ring->tx_lock')
    variants['producer-per-ring-only'] = (f, 'producer-slot-lock')
    f = dict(functions)
    f['edma_tx_slot_take'] = f['edma_tx_slot_take'].replace('spin_lock_bh(&ehw->tx_slot_lock);', '').replace('spin_unlock_bh(&ehw->tx_slot_lock);', '')
    variants['take-without-common-lock'] = (f, 'take-slot-lock')
    add('no-clear', 'edma_tx_slot_take', 'memset(&ehw->tx_slots[index], 0, sizeof(ehw->tx_slots[index]));', '(void)0;', 'empty-tuple-all-fields')
    add('wrong-length', 'edma_ring_xmit', '.len = buf_len + EDMA_TX_PREHDR_SIZE;', '.len = buf_len;', 'map-unmap-identity')
    add('wrong-ring-owner', 'edma_ring_xmit', '.txdesc_id = txdesc_ring->id;', '.txdesc_id = 0;', 'published-ring-owner')
    add('omit-owner-check', 'edma_tx_slot_take', '(!owner || ehw->tx_slots[index].txdesc_id == owner->id)', '(!owner || true)', 'foreign-ring-not-claimed')
    add('teardown-no-owner', 'edma_cleanup_txdesc_ring_res', 'store_idx, txdesc_ring, &slot', 'store_idx, NULL, &slot', 'foreign-ring-not-claimed')
    add('reload-shared-dma', 'edma_clean_tx', 'slot.dma,', 'ehw->tx_slots[store_index].dma,', 'map-unmap-identity')
    add('skip-zero-unmap', 'edma_clean_tx', 'dma_unmap_single(&pdev->dev, slot.dma,', 'if (slot.dma) dma_unmap_single(&pdev->dev, slot.dma,', 'free-before-unmap')
    add('skip-txcmpl-clean', 'edma_cleanup_txcmpl_ring_res', 'edma_clean_tx(ehw, txcmpl_ring);', '(void)0;', 'txcmpl-teardown-indirect-take')
    add('omit-lock-init', 'edma_configure_rings', 'spin_lock_init(&ehw->tx_slot_lock);', '(void)0;', 'lock-initialized-balanced')
    add('bad-map-error-unlock', 'edma_ring_xmit', 'dev_kfree_skb_any(skb);\n\t\tspin_unlock_bh(&ehw->tx_slot_lock);', 'dev_kfree_skb_any(skb);', 'producer-return-lock-balance')
    add('bad-padding-unlock', 'edma_ring_xmit', 'netdev->stats.tx_dropped++;\n\t\t\tspin_unlock_bh(&ehw->tx_slot_lock);', 'netdev->stats.tx_dropped++;', 'producer-return-lock-balance')
    add('wrong-unmap-device', 'edma_clean_tx', 'dma_unmap_single(&pdev->dev,', 'dma_unmap_single(NULL,', 'map-unmap-identity')
    add('wrong-txdesc-length', 'edma_cleanup_txdesc_ring_res', 'slot.len, DMA_TO_DEVICE', 'slot.len - 1, DMA_TO_DEVICE', 'map-unmap-identity')
    add('truncate-stored-dma', 'edma_ring_xmit', '.dma = dma_addr;', '.dma = (uint32_t)dma_addr;', 'map-unmap-identity')
    return variants


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.name.startswith('EDMA-TX-'), 'evidence directory must use EDMA-TX- prefix')
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    results = {'status': 'INCOMPLETE', 'output': str(output), 'compiler': args.compiler, 'sanitize': args.sanitize,
               'env': {k: env[k] for k in ['ASAN_OPTIONS', 'UBSAN_OPTIONS']}, 'runs': {}, 'mutants': {}}
    try:
        results['compiler_version'] = subprocess.run([args.compiler, '--version'], check=True, capture_output=True, text=True).stdout
        base, candidate, inputs = prepare(args.upstream_cache.resolve(), output)
        results['inputs_sha256'] = sha((output / 'INPUTS.json').read_bytes())
        results['test_inputs'] = {str(p): sha(p.read_bytes()) for p in [Path(__file__), TEMPLATE]}
        flags = ['-std=gnu11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-sign-compare']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        def build(name, text, is_candidate):
            src, binary = output / (name + '.c'), output / name
            src.write_text(text)
            p = run([args.compiler, *flags, '-DCANDIDATE=' + str(int(is_candidate)), src, '-o', binary], output, name + '.compile')
            require(p['returncode'] == 0 and not p['stdout'] and not p['stderr'], 'clean compile gate: ' + name)
            return binary
        extracted = {}
        for root, is_candidate in [(base, False), (candidate, True)]:
            headers, functions, fragments = extract(root, is_candidate)
            extracted[root.name] = (headers, functions)
            (output / (root.name + '.fragments.json')).write_text(json.dumps(fragments, indent=2) + '\n')
            binary = build(root.name + '-fixture', fixture(headers, functions, is_candidate), is_candidate)
            p = run([binary, 'trace'], output, root.name + '.trace', env)
            require(p['returncode'] == 0 and not p['stderr'], 'positive trace stderr/exit gate: ' + root.name)
            results['runs'][root.name + '.trace'] = p
            if is_candidate:
                p = run([binary, 'suite'], output, 'candidate.suite', env)
                require(p['returncode'] == 0 and not p['stderr'] and re.fullmatch(r'cases=\d+ checks=\d+ maps=\d+ unmaps=\d+ zero_unmaps=\d+ frees=\d+\n', p['stdout']), 'positive suite gate')
                results['runs']['candidate.suite'] = p
            else:
                for mode in ['race-a', 'race-b']:
                    p = run([binary, mode], output, 'baseline.' + mode, env)
                    require(p['returncode'] == 86 and 'EDMA_TX_CONTRACT map-unmap-identity' in p['stderr'], 'old race must fail exact ledger gate: ' + mode)
                    results['runs']['baseline.' + mode] = p
        require(results['runs']['baseline.trace']['stdout'] == results['runs']['candidate.trace']['stdout'], 'baseline/candidate successful wire trace mismatch')
        headers, functions = extracted['candidate']
        for name, (changed, marker) in mutants(functions).items():
            binary = build('mutant-' + name, fixture(headers, changed, True), True)
            p = run([binary, 'suite'], output, 'mutant-' + name, env)
            require(p['returncode'] == 86 and 'EDMA_TX_CONTRACT ' + marker in p['stderr'], 'mutant not rejected by intended semantic gate: ' + name)
            results['mutants'][name] = p
        if args.sanitize:
            results['sanitizer_canaries'] = {}
            for name, code, marker in [('asan', '#include <stdlib.h>\nint main(void){volatile int i=2;volatile int *p=malloc(sizeof(int));p[i]=1;free((void *)p);return 0;}\n', 'AddressSanitizer'), ('ubsan', 'int main(void){volatile int i=32;return 1<<i;}\n', 'runtime error:')]:
                binary = build('canary-' + name, code, True)
                p = run([binary], output, 'canary-' + name, env)
                require(isinstance(p['returncode'], int) and p['returncode'] != 0 and marker in p['stderr'], 'sanitizer positive stderr gate: ' + name)
                results['sanitizer_canaries'][name] = p
        results['status'] = 'PASS'
    except Exception as exc:
        results['error'] = str(exc)
        raise
    finally:
        (output / 'RESULTS.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({'status': results['status'], 'output': str(output), 'suite': results['runs']['candidate.suite']['stdout'].strip(), 'mutants': len(results['mutants'])}))


if __name__ == '__main__':
    main()
