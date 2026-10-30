#!/usr/bin/env python3
"""Fresh declared-context EDMA 001-016 and actual global OF ownership tests."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
REL = Path('hal/dp_ops/edma_dp/edma_v1')
PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
PATCH = '016-edma-v1-balance-global-of-references.patch'
TEMPLATE = SOURCE / 'tests/edma-of-references/fixture.c'
README = SOURCE / 'tests/edma-of-references/README'
HELPER = SOURCE / 'tests/edma_patch_context.py'
LEXER = SOURCE / 'tests/test-edma-tx-slot-ownership.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    data = path.read_bytes()
    exec(compile(data, str(path), 'exec'), module.__dict__)
    module.of016_loaded_sha256 = hashlib.sha256(data).hexdigest()
    return module


tx = load('edma_of016_tx_lexer', LEXER)
context = load('edma_of016_declared_context', HELPER)
require, sha, once, run = tx.require, tx.sha, tx.once, tx.run
NAMES = [
    'edma_disable_interrupts', 'edma_enable_interrupts', 'edma_disable_port',
    'edma_of_get_pdata', 'edma_release_of_refs', 'edma_init', 'edma_free_irqs',
    'edma_stop_napi', 'edma_release_mmio', 'edma_cleanup_locked', 'edma_cleanup',
    'edma_close_member', 'edma_retire_port', 'edma_if_open', 'edma_if_close',
    'edma_irq_init', 'edma_register_netdevice', 'edma_if_init',
]
SUMMARY = r'cases=\d+ checks=\d+ node=(\d+)/(\d+) device=(\d+)/(\d+) dma_uses=\d+ irq_uses=\d+\n'


def fail_oracle(result, marker):
    return (result['returncode'] == 86 and result['stdout'] == '' and
            result['stderr'] == 'EDMA_OF016 ' + marker + '\n')


def prepare(cache, output):
    archive = subprocess.run(['git', '-C', str(cache), 'archive', PIN], check=True, capture_output=True).stdout
    manifest = {'pin': PIN, 'archive_sha256': sha(archive),
                'context_helper': {'path': str(HELPER), 'sha256': sha(HELPER.read_bytes())},
                'declared_context_status': 'PASS_DECLARED_CONTEXT', 'patches': []}
    roots = [output / 'baseline', output / 'candidate']
    for root in roots:
        root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                        '..' not in Path(m.name).parts for m in tar.getmembers()), 'archive paths')
            tar.extractall(root)
    patches = sorted(p for p in (SOURCE / 'package/qca-nss/qca-nss-dp/patches').glob('*.patch')
                     if p.name[:3].isdigit() and int(p.name[:3]) <= 16)
    require([int(p.name[:3]) for p in patches] == list(range(1, 17)) and
            patches[-1].name == PATCH, 'exact 001-016 required')
    for patch in patches:
        data = patch.read_bytes(); saved = output / patch.name; saved.write_bytes(data)
        reports = {}
        for root in roots[1:] if patch.name == PATCH else roots:
            expected, report = context.inspect_patch(root, data)
            reports[root.name] = report
            p = subprocess.run(['/usr/bin/patch', '-p1', '--fuzz=0', '--batch', '-i', str(saved)],
                               cwd=root, capture_output=True, text=True)
            (output / (root.name + '-' + patch.name + '.log')).write_text(p.stdout + p.stderr)
            require(p.returncode == 0 and not re.search(r'fuzz|offset|FAILED|Reversed', p.stdout + p.stderr, re.I), 'patch replay ' + patch.name)
            context.verify_applied(root, expected)
        manifest['patches'].append({'path': str(patch), 'saved_path': str(saved),
                                    'sha256': sha(data), 'declared_context': reports})
    base, candidate = roots
    changed = [str(f.relative_to(base)) for f in base.rglob('*') if f.is_file() and
               f.read_bytes() != (candidate / f.relative_to(base)).read_bytes()]
    require(changed == [str(REL / 'edma_data_plane.c')], '016 single-file scope')
    allowed = ['edma_release_of_refs', 'edma_init', 'edma_release_mmio', 'edma_cleanup_locked']
    normalized = []
    for root in roots:
        text = (root / REL / 'edma_data_plane.c').read_text()
        for name in allowed:
            if root == base and name == 'edma_release_of_refs':
                require(not re.search(r'\b' + name + r'\(', tx.mask(text)), 'baseline already has helper')
                continue
            body, _ = tx.definition(text, name)
            text = once(text, body, '')
        normalized.append(re.sub(r'\s+', '', tx.mask(text)))
    require(normalized[0] == normalized[1], '016 touched other C tokens')
    manifest['changed_by_016'] = changed
    manifest['prepared_hashes'] = {root.name: {str(f.relative_to(root)): sha(f.read_bytes())
                                             for f in root.rglob('*') if f.is_file()} for root in roots}
    (output / 'INPUTS.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return roots, manifest


def extract(root, candidate, output):
    headers = []; funcs = {}; fragments = []
    for rel in ['hal/soc_ops/ipq807x/nss_ipq807x.h', str(REL / 'edma_regs.h'), str(REL / 'edma_data_plane.h')]:
        text = (root / rel).read_text()
        headers.append(re.sub(r'^#include[^\n]*\n', '', text, flags=re.M))
        fragments.append({'path': str(root / rel), 'sha256': sha(text.encode()), 'kind': 'complete header minus include directives'})
    for rel, names in [(str(REL / 'edma_data_plane.c'), NAMES),
                       ('nss_dp_main.c', ['nss_dp_clear_host_ctx', 'nss_dp_abort_host_probe'])]:
        text = (root / rel).read_text()
        for name in names:
            if not candidate and name == 'edma_release_of_refs':
                continue
            body, line = tx.definition(text, name)
            funcs[name] = body
            fragments.append({'path': str(root / rel), 'function': name, 'line': line, 'sha256': sha(body.encode())})
    (output / (root.name + '.fragments.json')).write_text(json.dumps(fragments, indent=2) + '\n')
    return '\n'.join(headers), funcs


def fixture(headers, functions):
    text = once(TEMPLATE.read_text(), '/* HEADERS */', headers)
    prototypes = '\n'.join(body[:body.index('{')].strip() + ';' for body in functions.values())
    text = once(text, '/* PROTOTYPES */', prototypes)
    return once(text, '/* FUNCTIONS */', '\n\n'.join(functions.values()))


def mutants(functions):
    variants = {}
    def add(name, fn, old, new, marker, mode='suite'):
        f = dict(functions); f[fn] = once(f[fn], old, new); variants[name] = (f, marker, mode)
    add('missing-node-put', 'edma_release_of_refs', 'of_node_put(node);', '(void)0;', 'node-get-put-balance')
    add('missing-device-put', 'edma_release_of_refs', 'put_device(&pdev->dev);', '(void)0;', 'device-get-put-balance')
    add('wrong-device-put', 'edma_release_of_refs', 'put_device(&pdev->dev);', 'put_device(&foreign_pdev.dev);', 'put-device-owned')
    add('stale-node-pointer', 'edma_release_of_refs', 'edma_hw.device_node = NULL;', '(void)0;', 'detach-before-put')
    add('double-node-put', 'edma_release_of_refs', 'of_node_put(node);', '{ of_node_put(node); of_node_put(node); }', 'put-node-owned')
    add('double-device-put', 'edma_release_of_refs', 'put_device(&pdev->dev);', '{ put_device(&pdev->dev); put_device(&pdev->dev); }', 'put-device-owned')
    add('put-before-last-use', 'edma_cleanup_locked', 'ASSERT_RTNL();', 'ASSERT_RTNL();\n\tedma_release_of_refs();', 'device-put-after-last-use', 'target-override')
    add('override-puts-refs', 'edma_cleanup_locked', 'if (!is_dp_override)\n\t\tedma_release_of_refs();', 'edma_release_of_refs();', 'device-put-after-last-use', 'target-override')
    add('abort-puts-global', 'nss_dp_abort_host_probe', 'edma_retire_port(dp->netdev, dp->macid);', 'edma_retire_port(dp->netdev, dp->macid);\n\t\tedma_release_of_refs();', 'device-put-after-last-use', 'target-peer')
    add('busy-region-release', 'edma_init', 'pr_warn("Unable to request EDMA register memory.\\n");', 'pr_warn("Unable to request EDMA register memory.\\n");\n\t\trelease_mem_region(res_edma.start, resource_size(&res_edma));', 'foreign-region-not-released', 'target-region')
    add('live-reject-unwinds', 'edma_init', 'return -EBUSY;', '{ ret = -EBUSY; goto edma_init_of_refs_fail; }', 'live-init-no-gets-or-puts', 'target-partial')
    add('foreign-drvdata-clear', 'edma_release_mmio', 'if (edma_hw.pdev && platform_get_drvdata(edma_hw.pdev) == &edma_hw)', 'if (edma_hw.pdev)', 'foreign-drvdata-preserved', 'target-foreign')
    add('skip-partial-puts', 'edma_cleanup_locked', '\t\t\tedma_release_of_refs();', '\t\t\tif (edma_hw.reg_base) edma_release_of_refs();', 'node-get-put-balance', 'target-partial')
    add('ignore-preowned-refs', 'edma_init', 'edma_hw.napi_dev || edma_hw.device_node || edma_hw.pdev', 'edma_hw.napi_dev', 'node-get-not-overwritten', 'target-partial')
    return variants


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--sanitize', action='store_true')
    a = parser.parse_args(); out = a.output.resolve()
    require(out.name.startswith('EDMA-OF016-'), 'evidence prefix'); out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'INCOMPLETE', 'compiler': a.compiler, 'sanitize': a.sanitize,
              'runs': {}, 'mutants': {}, 'oracle_poison_rejected': {}}
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    try:
        frozen_paths = [Path(__file__), TEMPLATE, README, LEXER, HELPER]
        result['test_inputs'] = {str(p): sha(p.read_bytes()) for p in frozen_paths}
        require(result['test_inputs'][str(LEXER)] == tx.of016_loaded_sha256 and
                result['test_inputs'][str(HELPER)] == context.of016_loaded_sha256,
                'loaded helper/lexer input changed')
        result['compiler_version'] = subprocess.run([a.compiler, '--version'], check=True, capture_output=True, text=True).stdout
        roots, inputs = prepare(a.upstream_cache.resolve(), out)
        result['inputs_sha256'] = sha((out / 'INPUTS.json').read_bytes())
        result['declared_context'] = inputs['declared_context_status']
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter', '-Wno-sign-compare']
        if a.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        result['compiler_flags'] = flags
        result['sanitizer_environment'] = {key: env[key] for key in ['ASAN_OPTIONS', 'UBSAN_OPTIONS']}
        def build(name, text):
            src, binary = out / (name + '.c'), out / name; src.write_text(text)
            r = run([a.compiler, *flags, src, '-o', binary], out, name + '.compile')
            require(r['returncode'] == 0 and r['stdout'] == r['stderr'] == '', 'compile gate ' + name)
            return binary
        headers, functions = extract(roots[1], True, out)
        binary = build('candidate-fixture', fixture(headers, functions))
        r = run([binary, 'suite'], out, 'candidate.suite', env)
        match = re.fullmatch(SUMMARY, r['stdout'])
        require(r['returncode'] == 0 and r['stderr'] == '' and match and
                match[1] == match[2] and match[3] == match[4], 'positive suite gate')
        require(r['stdout'] == 'cases=36 checks=4522 node=65/65 device=62/62 dma_uses=70 irq_uses=8\n',
                'positive scenario/accounting gate')
        result['runs']['candidate'] = r
        r = run([binary, 'trace'], out, 'candidate.trace', env)
        require(r['returncode'] == 0 and r['stderr'] == '' and re.search(SUMMARY + r'\Z', r['stdout']), 'trace gate')
        result['runs']['trace'] = r
        for mode in ['poison-exit', 'poison-stdout', 'poison-stderr', 'poison-sanitizer']:
            r = run([binary, mode], out, mode, env)
            require(not fail_oracle(r, 'node-get-put-balance'), 'poison accepted ' + mode)
            result['oracle_poison_rejected'][mode] = r
        for name, (changed, marker, mode) in mutants(functions).items():
            b = build('mutant-' + name, fixture(headers, changed)); r = run([b, mode], out, 'mutant-' + name, env)
            require(fail_oracle(r, marker), 'semantic oracle ' + name)
            result['mutants'][name] = {'expected_marker': marker, 'mode': mode, **r}
        bh, bf = extract(roots[0], False, out); b = build('old-fixture', fixture(bh, bf))
        for mode in ['old-missing-pdev', 'old-region', 'old-success']:
            r = run([b, mode], out, mode, env)
            require(fail_oracle(r, 'node-get-put-balance'), 'old source must fail exact reference gate ' + mode)
            result['runs'][mode] = r
        if a.sanitize:
            result['sanitizer_canaries'] = {}
            for name, code, marker in [('asan', '#include <stdlib.h>\nint main(void){volatile int i=2;volatile int *p=malloc(sizeof(int));p[i]=1;free((void *)p);return 0;}\n', 'AddressSanitizer'), ('ubsan', 'int main(void){volatile int i=32;return 1<<i;}\n', 'runtime error:')]:
                b = build('canary-' + name, code); r = run([b], out, 'canary-' + name, env)
                require(isinstance(r['returncode'], int) and r['returncode'] != 0 and marker in r['stderr'], 'positive sanitizer gate ' + name)
                result['sanitizer_canaries'][name] = r
        require(result['test_inputs'] == {str(p): sha(p.read_bytes()) for p in frozen_paths},
                'test/helper inputs changed during run')
        require(all(sha(Path(item['path']).read_bytes()) == item['sha256']
                    for item in inputs['patches']), 'patch chain changed during run')
        result['input_stability'] = 'PASS'
        result['status'] = 'PASS'
    except Exception as exc:
        result['error'] = str(exc); raise
    finally:
        (out / 'RESULTS.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'suite': result['runs']['candidate']['stdout'].strip(),
                      'mutants': len(result['mutants']), 'oracle_poison': len(result['oracle_poison_rejected']),
                      'declared_context': result['declared_context']}))


if __name__ == '__main__':
    main()
