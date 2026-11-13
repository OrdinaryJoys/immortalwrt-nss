#!/usr/bin/env python3
"""Positive and precise rejection controls for the extraction runner itself."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pdata_runner', HERE / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [args.source.resolve(), args.baseline.resolve(), HERE]
    runner.outside_inputs(output, roots)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'tmp').mkdir()
    env = dict(os.environ, TMPDIR=str(output / 'tmp'))
    results = []

    def good(name, operation):
        operation()
        results.append({'name': name, 'kind': 'positive', 'status': 'PASS'})

    def bad(name, expected, operation):
        try:
            operation()
        except runner.AuditError as error:
            runner.require(str(error) == expected, 'unit-wrong-error-' + name)
        else:
            raise runner.AuditError('unit-negative-accepted-' + name)
        results.append({'name': name, 'kind': 'precise-rejection', 'expected': expected, 'status': 'PASS'})

    good('outside-inputs', lambda: runner.outside_inputs(output / 'good', roots))
    for name, root in zip(('source', 'baseline', 'tests'), roots):
        bad('output-' + name, 'output-inside-input-tree', lambda root=root: runner.outside_inputs(root / 'forbidden-unit-output', roots))
    alias = output / 'source-symlink'
    alias.symlink_to(roots[0], target_is_directory=True)
    bad('output-resolved-symlink', 'output-inside-input-tree', lambda: runner.outside_inputs(alias / 'forbidden-unit-output', roots))
    for name, root in zip(('source', 'baseline', 'tests'), roots):
        target = root / 'forbidden-unit-output'
        proc = subprocess.run([sys.executable, str(HERE / 'run.py'), '--source', str(roots[0]), '--baseline', str(roots[1]), '--output', str(target), '--cc', args.cc], env=env, capture_output=True, text=True)
        runner.require(proc.returncode == 1 and proc.stderr == 'ERROR: output-inside-input-tree\n' and not target.exists(), 'cli-output-rejection-' + name)
        results.append({'name': 'cli-output-' + name, 'kind': 'precise-rejection', 'status': 'PASS'})
    proc = subprocess.run([sys.executable, '-O', str(HERE / 'run.py'), '--help'], env=env, capture_output=True, text=True)
    runner.require(proc.returncode == 1 and proc.stderr == 'ERROR: python-optimization-forbidden\n', 'optimization-gate')
    results.append({'name': 'python-O', 'kind': 'precise-rejection', 'status': 'PASS'})
    for label in ('source', 'harness', 'runner'):
        path = output / (label + '.fixture')
        path.write_bytes(b'original\n')
        snapshot = runner.FrozenInputs(output / ('frozen-' + label))
        original = snapshot.read(path, label)
        good('stable-' + label, snapshot.verify)
        path.write_bytes(b'changed\n')
        bad('changed-' + label, 'changed-' + label, snapshot.verify)
        path.write_bytes(original)
        (snapshot.output / label).write_bytes(b'tampered frozen copy\n')
        bad('changed-snapshot-' + label, 'changed-snapshot-' + label, snapshot.verify)
    for label in ('compiler', 'generated-c', 'binary'):
        path = output / (label + '.fixture')
        path.write_bytes(b'original artifact\n')
        expected = runner.sha(path.read_bytes())
        good('stable-' + label, lambda: runner.check_stable(path, expected, label))
        path.write_bytes(b'changed artifact\n')
        bad('changed-' + label, 'changed-' + label, lambda: runner.check_stable(path, expected, label))
    completed = subprocess.CompletedProcess
    good('runtime-positive', lambda: runner.check_runtime(completed([], 0, 'PASS:case:dynamic=1:direct-cache=0\n', ''), 'case', 1, 0))
    good('runtime-exact-negative', lambda: runner.check_runtime(completed([], 86, '', 'FAIL:case:tag\n'), 'case', 1, 0, 'tag'))
    for name, result in (
        ('wrong-exit', completed([], 1, '', 'FAIL:case:tag\n')),
        ('wrong-marker', completed([], 86, '', 'FAIL:case:other\n')),
        ('extra-output', completed([], 86, 'unexpected', 'FAIL:case:tag\n')),
        ('signal', completed([], -11, '', 'FAIL:case:tag\n')),
        ('success-as-negative', completed([], 0, '', ''))):
        bad('runtime-' + name, 'runtime-negative-mismatch', lambda result=result: runner.check_runtime(result, 'case', 1, 0, 'tag'))
    for name in ('clean', 'warning'):
        proc = subprocess.run([args.cc, '-std=c11', '-Wall', str(HERE / 'fixtures' / (name + '.c')), '-o', str(output / name)], env=env, capture_output=True, text=True)
        runner.require(proc.returncode == 0, 'unit-compile-fixture')
        if name == 'clean':
            good('compiler-clean', lambda: runner.clean_command(proc, 'compile'))
        else:
            runner.require('pdata-runner-warning-control' in proc.stderr, 'warning-marker')
            bad('compiler-warning-rc0', 'compile-stderr', lambda: runner.clean_command(proc, 'compile'))
    bad('compiler-nonzero', 'compile-nonzero', lambda: runner.clean_command(completed([], 1, '', ''), 'compile'))
    fixture = runner.SIGNATURE + '\n{ /* } */ const char *s = "}"; if (s) {} return 0; }\nstatic int unrelated;\n'
    function, line = runner.extract(fixture)
    good('extract-comment-string-braces', lambda: runner.require(line == 1 and 'unrelated' not in function and function.endswith('return 0; }\n'), 'extract-fixture'))
    report = {'status': 'PASS', 'runner_sha256': runner.sha((HERE / 'run.py').read_bytes()),
              'unit_sha256': runner.sha(Path(__file__).read_bytes()), 'compiler': args.cc,
              'positive_count': sum(r['kind'] == 'positive' for r in results),
              'precise_rejection_count': sum(r['kind'] == 'precise-rejection' for r in results), 'results': results}
    (output / 'UNIT-RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'positive_count', 'precise_rejection_count')}, indent=2))


if __name__ == '__main__':
    main()
