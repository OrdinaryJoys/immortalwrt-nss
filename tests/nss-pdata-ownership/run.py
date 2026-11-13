#!/usr/bin/env python3
"""Extract and test the real IPQ807x pdata constructor; never execute input code scripts."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

if not __debug__:
    raise SystemExit('ERROR: python-optimization-forbidden')

REL = Path('nss_hal/ipq807x/nss_hal_pvt.c')
SIGNATURE = 'static struct nss_platform_data *__nss_hal_of_get_pdata(struct platform_device *pdev)'
TOKENS = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
CASES = (['alloc'] + ['property%d' % i for i in range(4)] +
         ['irq-count', 'id-bound', 'id-max'] + ['resource%d' % i for i in range(3)] +
         ['map%d' % i for i in range(1, 4)] + ['irq%d' % i for i in range(10)] +
         ['success0', 'success1', 'success10', 'last-id-root-one', 'last-id-nine-irqs', 'tcm20'] +
         ['optional%d' % i for i in range(3)])


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AuditError(Exception):
    pass


def require(condition, tag):
    if not condition:
        raise AuditError(tag)


def outside_inputs(output, protected):
    for root in protected:
        require(not output.resolve().is_relative_to(root.resolve()), 'output-inside-input-tree')


def check_stable(path, expected, tag):
    actual = sha(path.read_bytes())
    require(actual == expected, 'changed-' + tag)
    return actual


def clean_command(result, tag):
    require(result.returncode == 0, tag + '-nonzero')
    require(not result.stderr, tag + '-stderr')


def check_runtime(result, case, dynamic, direct, expected=None):
    if expected:
        require(result.returncode == 86 and result.stderr == 'FAIL:%s:%s\n' % (case, expected) and result.stdout == '', 'runtime-negative-mismatch')
    else:
        require(result.returncode == 0 and result.stderr == '' and result.stdout == 'PASS:%s:dynamic=%d:direct-cache=%d\n' % (case, dynamic, direct), 'runtime-positive-mismatch')


class FrozenInputs:
    def __init__(self, output):
        self.output = output
        self.records = {}
        output.mkdir()

    def read(self, path, label):
        path = path.resolve()
        require(label not in self.records, 'duplicate-input-label')
        data = path.read_bytes()
        (self.output / label).write_bytes(data)
        self.records[label] = {'path': str(path), 'before_sha256': sha(data)}
        return data

    def verify(self):
        for label, record in self.records.items():
            record['after_sha256'] = check_stable(Path(record['path']), record['before_sha256'], label)
            check_stable(self.output / label, record['before_sha256'], 'snapshot-' + label)


def extract(data):
    assert data.count(SIGNATURE) == 1, 'Function definition must be unique'
    start = data.index(SIGNATURE)
    depth = 0
    for token in TOKENS.finditer(data, start + len(SIGNATURE)):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return data[start:token.end()] + '\n', data[:start].count('\n') + 1
    raise ValueError('Unterminated function')


def replace_once(text, old, new):
    assert text.count(old) == 1, 'Mutation anchor not unique: ' + old
    return text.replace(old, new, 1)


def mutants(function):
    guard = ('\tif (npd->id >= NSS_MAX_CORES) {\n'
             '\t\tpr_err("%s: invalid NSS core id %u\\n", np->name, npd->id);\n'
             '\t\tgoto out;\n\t}\n\n')
    tcm = ('\t/*\n\t * Clear TCM only after all fallible pdata validation has completed.\n\t */\n'
           '\tfor (i = 0; i < resource_size(&res_vphys) ; i += 4)\n'
           '\t\tnss_write_32(npd->vmap, i, 0);\n\n\tNSS_CORE_DSB();\n\n')
    yield 'missing-node-put', replace_once(function, '\tif (!npd) {\n\t\tof_node_put(np);', '\tif (!npd) {'), 'alloc', 'node_ref_balanced', 0
    for member, case in [('nmap', 'map2'), ('vmap', 'map3'), ('qgic_map', 'irq0')]:
        block = '\tif (npd->%s) {\n\t\tiounmap(npd->%s);\n\t}\n\n' % (member, member)
        tag = 'qgic_rollback' if member == 'qgic_map' else member + '_rollback'
        yield 'missing-' + member + '-rollback', replace_once(function, block, ''), case, tag, 0
    yield 'foreign-qgic-unmap', replace_once(function, 'iounmap(npd->qgic_map);', 'iounmap(nss_ctx->qgic_map);'), 'irq0', 'unmap_local_not_foreign', 0
    yield 'success-unmap', replace_once(function, '\treturn npd;', '\tiounmap(npd->qgic_map);\n\treturn npd;'), 'success10', 'success_retains_maps', 0
    yield 'off-by-one-id', replace_once(function, 'npd->id >= NSS_MAX_CORES', 'npd->id > NSS_MAX_CORES'), 'id-bound', 'invalid_id_no_context_write', 1
    yield 'overstrict-root-count', replace_once(function, 'npd->id >= NSS_MAX_CORES', 'npd->id >= nss_top->num_nss'), 'last-id-root-one', 'return_contract', 0
    late = replace_once(function, guard, '')
    late = replace_once(late, '\tif (npd->num_irq > NSS_MAX_IRQ_PER_CORE)', guard + '\tif (npd->num_irq > NSS_MAX_IRQ_PER_CORE)')
    yield 'late-id-guard', late, 'id-bound', 'invalid_id_frequency_untouched', 0
    early = replace_once(function, tcm, '')
    early = replace_once(early, '\t/*\n\t * Get IRQ numbers\n', tcm + '\t/*\n\t * Get IRQ numbers\n')
    yield 'early-tcm', early, 'irq9', 'tcm_after_all_irqs', 0
    yield 'missing-barrier', replace_once(function, '\tNSS_CORE_DSB();\n', ''), 'success10', 'features_after_barrier', 0
    yield 'dispose-borrowed-irq', replace_once(function, 'out:\n', 'out:\n\tif (npd->irq[0])\n\t\tirq_dispose_mapping(npd->irq[0]);\n'), 'irq1', 'no_irq_disposal_without_ownership', 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Prepared candidate source tree')
    parser.add_argument('--baseline', type=Path, help='Optional fresh pre-032 prepared source tree')
    parser.add_argument('--vendor-file', type=Path, help='Optional git-show/archive file at locked 6aa vendor pin')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; must not exist')
    parser.add_argument('--cc', required=True)
    parser.add_argument('--optimization', choices=['O0', 'O2'], default='O2')
    parser.add_argument('--sanitize', action='store_true', help='Address/UB sanitizers (no leak-sanitizer claim)')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    tests = Path(__file__).resolve().parent
    protected = [source, tests]
    if args.baseline:
        protected.append(args.baseline.resolve())
    outside_inputs(output, protected)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'tmp').mkdir()
    environment = dict(os.environ, TMPDIR=str(output / 'tmp'), ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
    requested_cc = shutil.which(args.cc)
    require(requested_cc is not None, 'compiler-unavailable')
    cc = Path(requested_cc).resolve()
    resolution = None
    if sys.platform == 'darwin' and str(cc) in ('/usr/bin/clang', '/usr/bin/cc'):
        resolution = subprocess.run(['/usr/bin/xcrun', '--find', 'clang'], capture_output=True, text=True, timeout=30)
        clean_command(resolution, 'compiler-resolution')
        cc = Path(resolution.stdout.strip()).resolve()
    compiler_hash = sha(cc.read_bytes())
    frozen = FrozenInputs(output / 'inputs')
    api = frozen.read(source / 'exports/nss_api_if.h', 'nss_api_if.h').decode()
    core = frozen.read(source / 'nss_core.h', 'nss_core.h').decode()
    assert re.search(r'^#define NSS_MAX_CORES\s+2\b', api, re.M)
    assert re.search(r'^#define NSS_MAX_IRQ_PER_CORE\s+10\b', core, re.M)
    assert 'struct nss_ctx_instance nss[NSS_MAX_CORES];' in core
    full_source = frozen.read(source / REL, 'candidate-nss_hal_pvt.c')
    function, line = extract(full_source.decode())
    harness_bytes = frozen.read(tests / 'harness.c', 'harness.c')
    harness = harness_bytes.decode()
    runner_bytes = frozen.read(Path(__file__), 'run.py')
    before, before_line, baseline_file = None, None, None
    vendor = None
    if args.baseline:
        baseline_file = args.baseline.resolve() / REL
        before, before_line = extract(frozen.read(baseline_file, 'baseline-nss_hal_pvt.c').decode())
    if args.vendor_file:
        vendor, _ = extract(frozen.read(args.vendor_file, 'vendor-nss_hal_pvt.c').decode())
    assert harness.count('/* @FUNCTION@ */') == 1
    report = {
        'source_file': str(source / REL), 'source_sha256': sha(full_source),
        'function_line': line, 'function_sha256': sha(function.encode()),
        'harness_sha256': sha(harness_bytes), 'runner_sha256': sha(runner_bytes),
        'compiler': str(cc), 'requested_compiler': requested_cc, 'compiler_before_sha256': compiler_hash,
        'compiler_resolution': resolution.stdout.strip() if resolution else None,
        'optimization': args.optimization, 'sanitizers': args.sanitize, 'frozen_inputs': frozen.records,
        'source_contracts': {'NSS_MAX_CORES': 2, 'NSS_MAX_IRQ_PER_CORE': 10, 'production_array_is_fixed': True},
        'commands': [], 'runtime_results': [],
    }

    def command(argv):
        result = subprocess.run(argv, cwd=output, env=environment, capture_output=True, text=True, timeout=60)
        record = {'argv': [str(arg) for arg in argv], 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        report['commands'].append(record)
        (output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
        return result

    version = command([str(cc), '--version'])
    clean_command(version, 'compiler-version')
    report['compiler_version'] = version.stdout
    cc1_result = command([str(cc), '-print-prog-name=cc1'])
    clean_command(cc1_result, 'compiler-cc1')
    cc1 = Path(cc1_result.stdout.strip())
    cc1_hash = sha(cc1.read_bytes()) if cc1.is_file() else None
    report['cc1'] = {'path': str(cc1), 'before_sha256': cc1_hash}

    def build(name, body, origin, origin_line, pad=0):
        path = output / (name + '.c')
        inserted = '#line %d %s\n%s\n#line 1 "harness-after-extraction"\n' % (origin_line, json.dumps(str(origin)), body)
        path.write_text(harness.replace('/* @FUNCTION@ */', inserted))
        binary = output / name
        flags = ['-std=c11', '-' + args.optimization, '-g', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                 '-DNSS_MAX_CORES=2', '-DNSS_MAX_IRQ_PER_CORE=10', '-DHOST_PAD_CONTEXT=%d' % pad]
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        generated_hash = sha(path.read_bytes())
        check_stable(cc, compiler_hash, 'compiler-before-compile')
        result = command([str(cc)] + flags + [str(path), '-o', str(binary)])
        clean_command(result, 'compile-' + name)
        check_stable(cc, compiler_hash, 'compiler-after-compile')
        generated_after = check_stable(path, generated_hash, 'generated-c-after-compile')
        report.setdefault('binaries', {})[name] = {
            'generated_c_before_sha256': generated_hash, 'generated_c_after_compile_sha256': generated_after,
            'binary_after_compile_sha256': sha(binary.read_bytes()), 'context_padding': pad}
        return binary

    def run(binary, case, dynamic=1, direct=0, expected=None):
        artifact = report['binaries'][binary.name]
        c_before = check_stable(binary.with_suffix('.c'), artifact['generated_c_before_sha256'], 'generated-c-before-run')
        binary_before = check_stable(binary, artifact['binary_after_compile_sha256'], 'binary-before-run')
        result = command([str(binary), case, str(dynamic), str(direct)])
        c_after = check_stable(binary.with_suffix('.c'), artifact['generated_c_before_sha256'], 'generated-c-after-run')
        binary_after = check_stable(binary, artifact['binary_after_compile_sha256'], 'binary-after-run')
        check_runtime(result, case, dynamic, direct, expected)
        report['runtime_results'].append({'binary': binary.name, 'case': case, 'dynamic': dynamic, 'direct_cache': direct,
            'expected_failure': expected, 'verified': True, 'c_before_sha256': c_before, 'c_after_sha256': c_after,
            'binary_before_sha256': binary_before, 'binary_after_sha256': binary_after})

    positive = build('positive', function, source / REL, line)
    for dynamic in (0, 1):
        for direct in (0, 1):
            for case in CASES:
                run(positive, case, dynamic, direct)
    for name, body, case, expected, padding in mutants(function):
        binary = build('negative-' + name, body, source / REL, line, padding)
        run(binary, case, expected=expected)
    if args.baseline:
        report['baseline_function_sha256'] = sha(before.encode())
        if vendor:
            report['vendor_function_sha256'] = sha(vendor.encode())
            delta = ''.join(difflib.unified_diff(vendor.splitlines(True), before.splitlines(True), fromfile='vendor6aa-function', tofile='prepared-baseline-function'))
            (output / 'vendor-to-baseline.diff').write_text(delta)
            # Patch 003 already changes these APIs; it is not part of 032.
            require(vendor.count('ioremap_nocache(') == 2, 'vendor-ioremap-anchors')
            compatible = vendor.replace('ioremap_nocache(', 'nss_ioremap(')
            compatible = replace_once(compatible,
                '\tfor (i = 0; i < resource_size(&res_vphys) ; i += 4) {\n\t\tnss_write_32(npd->vmap, i, 0);\n\t\tNSS_CORE_DMA_CACHE_MAINT((npd->vmap + i), 4, DMA_TO_DEVICE);\n\t}\n',
                '\tfor (i = 0; i < resource_size(&res_vphys) ; i += 4)\n\t\tnss_write_32(npd->vmap, i, 0);\n\n')
            require(compatible == before, 'unexpected-vendor-baseline-delta')
            report['vendor_baseline_delta_is_existing_003_compatibility'] = True
        baseline = build('baseline-witness', before, baseline_file, before_line, 1)
        run(baseline, 'alloc', expected='node_ref_balanced')
        run(baseline, 'id-bound', expected='invalid_id_no_context_write')
        for i in range(10):
            run(baseline, 'irq%d' % i, expected='tcm_after_all_irqs')
    frozen.verify()
    report['compiler_after_sha256'] = check_stable(cc, compiler_hash, 'compiler-final')
    if cc1_hash:
        report['cc1']['after_sha256'] = check_stable(cc1, cc1_hash, 'cc1-final')
    for name, artifact in report['binaries'].items():
        artifact['generated_c_final_sha256'] = check_stable(output / (name + '.c'), artifact['generated_c_before_sha256'], 'generated-c-final')
        artifact['binary_final_sha256'] = check_stable(output / name, artifact['binary_after_compile_sha256'], 'binary-final')
    report['status'] = 'PASS'
    report['positive_count'] = sum(r['expected_failure'] is None for r in report['runtime_results'])
    report['precise_negative_count'] = sum(r['expected_failure'] is not None for r in report['runtime_results'])
    (output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'positive_count', 'precise_negative_count', 'function_sha256', 'compiler')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except AuditError as error:
        raise SystemExit('ERROR: ' + str(error))
