"""Rehash new evidence as data; run only the new sequential design tests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[2]
AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261101/ssdk-cohort-contract')
PREP = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    paths = list(root.rglob('*'))
    need(not any(p.is_symlink() for p in paths), 'SYMLINK:' + str(root))
    return {str(p.relative_to(root)): sha(p) for p in paths if p.is_file()}


def read(path):
    return json.loads(path.read_text())


def native(directory, positives, negatives, commands):
    r = read(directory / 'RESULTS.json')
    need(r['status'] == 'HOST_MODEL_ONLY' and r['positive_count'] == positives and
         r['negative_count'] == negatives and len(r['commands']) == commands, 'NATIVE_COUNTS')
    need(r['end_inputs'] is True, 'NATIVE_END_INPUTS')
    for path, value in r['inputs'].items():
        need(sha(path) == value, 'NATIVE_INPUT:' + path)
    actual = files(directory)
    del actual['RESULTS.json']
    need(actual == r['generated'], 'NATIVE_OUTPUT_TAIL:' + str(directory))
    for p in directory.rglob('*.expected'):
        # Each expected byte stream is paired with an exact run, not a compile failure.
        stem = p.with_suffix('')
        if not stem.with_suffix('.json').exists():
            stem = Path(str(stem) + '-run')
        row = read(Path(str(stem) + '.json'))
        out = Path(str(stem) + '.stdout').read_bytes()
        err = Path(str(stem) + '.stderr').read_bytes()
        expected = p.read_bytes()
        need(not row.get('timeout'), 'RUN_TIMEOUT')
        if expected.startswith(b'OK '):
            need(row['returncode'] == 0 and out == expected and not err, 'POSITIVE_BYTES')
        else:
            need(row['returncode'] == 86 and not out and err == expected, 'NEGATIVE_BYTES')
    return dict(path=str(directory), receipt_sha256=sha(directory / 'RESULTS.json'),
                positives=positives, negatives=negatives, commands=commands,
                generated_files=len(actual), qualification='REHASH_AND_RAW_RECHECK_ONLY')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--root-tests', action='store_true')
    a = p.parse_args()
    need(sys.flags.optimize > 0 and not a.output.exists(), 'OPTIMIZED_FRESH_OUTPUT')
    a.output.mkdir(parents=True)
    bound = {str(p): sha(p) for p in (Path(__file__), SOURCE / 'tests/ssdk-cohort-contract/contract.py',
                                    SOURCE / 'tests/ssdk-cohort-contract/test_contract.py')}
    r = dict(status='INCOMPLETE', qualification='TEXT_AND_HOST_NOT_TARGET_OR_RUNTIME')
    try:
        names = ('UK-TRANSPORT-CANDIDATE-20261101-r1',
                 'SHARED-CONTRACT-CANDIDATE-20261101-r2',
                 'SHARED-CONTRACT-CANDIDATE-20261101-r3')
        receipts = [read(PREP / n / 'RESULTS.json') for n in names]
        need([len(x['patches']) for x in receipts] == [29, 30, 31], 'PATCH_COUNTS')
        for n, data in zip(names, receipts):
            need(data['status'] == 'PASS_TEXT_ONLY' and len(data['prepared_files']) == 692, 'PREP_STATUS')
            need(files(PREP / n / 'prepared') == data['prepared_files'], 'WHOLE_PREP_TREE')
        for old, new in zip(receipts, receipts[1:]):
            need(new['patches'][:len(old['patches'])] == old['patches'], 'OLD_PATCH_ENTRY_DRIFT')
        changes = []
        for old, new in zip(receipts, receipts[1:]):
            changes.append(sorted(k for k in set(old['prepared_files']) | set(new['prepared_files'])
                                  if old['prepared_files'].get(k) != new['prepared_files'].get(k)))
        need(changes == [['mk/obj.mk', 'src/hsl/hsl_lock.c'], ['src/init/ssdk_init.c']], 'UNEXPECTED_DELTA')
        for patch in receipts[-1]['patches']:
            need(sha(SOURCE / 'package/qca-nss/qca-ssdk/patches' / patch['name']) == patch['sha256'],
                 'CURRENT_PATCH_DRIFT')
        final = PREP / names[-1] / 'prepared'
        obj = (final / 'mk/obj.mk').read_text()
        clause = 'ifeq (TRUE, $(API_LOCK))\nOBJ-COMMON += src/hsl/hsl_lock.o\nendif'
        need(obj.count(clause) == 1 and obj.index(clause) < obj.index('OBJ := $(OBJ-COMMON)'),
             'OBJECT_SELECTION_BEFORE_COLLECTION')
        need('API_LOCK=FALSE' in (final / 'mk/feature.mk').read_text(), 'DEFAULT_CHANGED')
        r['object_selection'] = 'STATIC_ONLY_TRUE_APPEND_FALSE_INACTIVE_NO_MAKE'
        r['prepare'] = dict(patches=31, files=692, changes=changes,
                            receipts={n: sha(PREP / n / 'RESULTS.json') for n in names})
        r['native'] = [native(AUDIT / 'LOCK-PARENT-GCC-r1', 13, 15, 50),
                       native(AUDIT / 'LOCK-PARENT-CLANG-r1', 13, 15, 54)]
        if a.root_tests:
            r['root_host'] = []
            for name in ('ROOT-PARENT-GCC-r1', 'ROOT-PARENT-CLANG-r1'):
                root = AUDIT / name
                data = read(root / 'RESULTS.json')
                count = 40 if 'CLANG' in name else 36
                need(data['status'] == 'HOST_MODEL_ONLY' and data['positive_count'] == 312 and
                     data['negative_count'] == 6 and len(data['commands']) == count, 'ROOT_HOST_STATUS')
                for path, value in data['inputs'].items():
                    need(sha(path) == value, 'ROOT_INPUT:' + path)
                actual = files(root)
                del actual['RESULTS.json']
                need(actual == data['generated'], 'ROOT_OUTPUT_TAIL')
                streams = list(root.rglob('*.expected'))
                need(len(streams) == 18, 'ROOT_EXPECTED_INVENTORY')
                for expected in streams:
                    prefix = expected.parent / 'run'
                    row = read(Path(str(prefix) + '.json'))
                    stdout = Path(str(prefix) + '.stdout').read_bytes()
                    stderr = Path(str(prefix) + '.stderr').read_bytes()
                    need(not row['timeout'], 'ROOT_TIMEOUT')
                    if expected.name == 'stdout.expected':
                        need(row['returncode'] == 0 and stdout == expected.read_bytes() and not stderr and
                             stdout.count(b'CASE ') == stdout.count(b'END\n') == 26, 'ROOT_POSITIVE_BYTES')
                    else:
                        need(expected.name == 'stderr.expected' and row['returncode'] == 86 and
                             not stdout and stderr == expected.read_bytes(), 'ROOT_NEGATIVE_BYTES')
                compile_rows = list(root.rglob('compile.json'))
                need(len(compile_rows) == 18, 'ROOT_COMPILE_INVENTORY')
                for compile_path in compile_rows:
                    need(read(compile_path)['returncode'] == 0 and
                         not compile_path.with_suffix('.stdout').read_bytes() and
                         not compile_path.with_suffix('.stderr').read_bytes(), 'ROOT_CLEAN_COMPILE')
                r['root_host'].append(dict(name=name, positives=312, negatives=6, commands=count,
                    generated=len(actual), raw='ALL_18_RUNS_AND_COMPILES_MATCH', qualification='HOST_ONLY'))
            r['root_receipts'] = {n: sha(AUDIT / n / 'RESULTS.json')
                                  for n in ('ROOT-PARENT-GCC-r1', 'ROOT-PARENT-CLANG-r1')}
        run = subprocess.run([sys.executable, '-B', '-O', str(Path(__file__).with_name('test_contract.py'))],
                             capture_output=True, timeout=30)
        (a.output / 'model.stdout').write_bytes(run.stdout)
        (a.output / 'model.stderr').write_bytes(run.stderr)
        model = json.loads(run.stdout)
        need(run.returncode == 0 and not run.stderr and model['success'] and
             model['failures'] == model['errors'] == 0, 'NEW_MODEL_TESTS')
        r['design_model'] = model
        for path, value in bound.items():
            need(sha(path) == value, 'NEW_MODEL_DRIFT')
        r.update(status='PASS_BOUNDED_DATA_AND_DESIGN', inputs=bound)
    except Exception as e:
        r['error'] = str(e)
    (a.output / 'RESULTS.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('status', 'error') if k in r}))
    return 0 if r['status'] == 'PASS_BOUNDED_DATA_AND_DESIGN' else 1


if __name__ == '__main__':
    sys.exit(main())
