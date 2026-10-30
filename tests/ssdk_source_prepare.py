#!/usr/bin/env python3
"""Fresh pinned SSDK text preparation only; never invoke make or a compiler."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from edma_patch_context import inspect_patch, verify_applied

SOURCE = Path(__file__).resolve().parents[1]
PACKAGE = SOURCE / 'package/qca-nss/qca-ssdk'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
AUDIT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'symlink in prepared tree')
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path.read_bytes())
    return result


def patch_inventory():
    return sorted((PACKAGE / 'patches').glob('*.patch'))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare(cache, output):
    output = Path(output).resolve()
    require(output.is_relative_to(AUDIT) and output != AUDIT, 'output outside phase3 evidence')
    require(not output.exists(), 'fresh output required')
    recipe = PACKAGE / 'Makefile'
    require(re.search(r'^PKG_SOURCE_VERSION:=' + PIN + r'\s*$', recipe.read_text(), re.M),
            'unexpected SSDK source train')
    patches = patch_inventory()
    require(patches and all(re.fullmatch(r'\d{3}-.+\.patch', p.name) for p in patches),
            'invalid patch inventory')
    bound = [Path(__file__).resolve(), SOURCE / 'tests/edma_patch_context.py', recipe, *patches]
    identities = {str(p): digest(p.read_bytes()) for p in bound}
    output.mkdir(parents=True)
    result = {'status': 'INCOMPLETE', 'pin': PIN, 'qualification': 'TEXT_ONLY_NO_BUILD',
              'source': str(SOURCE), 'inputs': identities, 'patches': []}
    report = output / 'RESULTS.json'
    try:
        process = subprocess.run(['git', '-C', str(cache), 'archive', '--format=tar', PIN],
                                 capture_output=True, timeout=90)
        require(process.returncode == 0 and not process.stderr, 'exact upstream Git archive failed')
        archive = process.stdout
        (output / 'upstream.tar').write_bytes(archive)
        result['archive_sha256'] = digest(archive)
        tree = output / 'prepared'
        tree.mkdir()
        derived = {}
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                name = PurePosixPath(member.name)
                require(not name.is_absolute() and '..' not in name.parts and
                        '.git' not in name.parts and (member.isfile() or member.isdir()),
                        'unsupported archive member: ' + member.name)
                destination = tree / str(name)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    data = tar.extractfile(member).read()
                    require(str(name) not in derived, 'duplicate archive file')
                    derived[str(name)] = digest(data)
                    destination.write_bytes(data)
        require(inventory(tree) == derived, 'archive extraction differs from derived bytes')
        result['upstream_files'] = dict(derived)
        (output / 'patches').mkdir()
        for path in patches:
            data = path.read_bytes()
            require(digest(data) == identities[str(path)], 'patch changed before replay')
            (output / 'patches' / path.name).write_bytes(data)
            entry = {'name': path.name, 'sha256': digest(data), 'status': 'INCOMPLETE'}
            result['patches'].append(entry)
            write_json(report, result)
            expected, contexts = inspect_patch(tree, data)
            for name, context in contexts.items():
                require(context['before_sha256'] == derived.get(name),
                        'patch preimage differs from derived bytes: ' + name)
            entry['declared_context'] = contexts
            process = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-V', 'none'],
                                     input=data, cwd=tree, capture_output=True, timeout=90)
            (output / (path.name + '.stdout')).write_bytes(process.stdout)
            (output / (path.name + '.stderr')).write_bytes(process.stderr)
            entry['returncode'] = process.returncode
            require(process.returncode == 0 and not process.stderr and not re.search(
                rb'fuzz|offset|FAILED|reject|malformed|Reversed|previously applied',
                process.stdout, re.I), 'patch tool rejection/shift: ' + path.name)
            verify_applied(tree, expected)
            derived.update({name: digest(data) for name, data in expected.items()})
            entry['status'] = 'PASS_DECLARED_CONTEXT_AND_OUTPUT'
            write_json(report, result)
        require(not list(tree.rglob('*.orig')) and not list(tree.rglob('*.rej')),
                'unexpected replay backups/rejects')
        require(inventory(tree) == derived, 'final source differs from derived bytes')
        result['prepared_files'] = derived
        result['input_stability'] = check_stable_inputs(output, result)
        result['status'] = 'PASS_TEXT_ONLY'
        write_json(report, result)
        return tree, result
    except Exception as error:
        result['error'] = str(error)
        write_json(report, result)
        raise


def check_stable_inputs(output, result):
    expected_names = [p['name'] for p in result['patches']]
    require([p.name for p in patch_inventory()] == expected_names, 'patch inventory drift')
    for name, expected in result['inputs'].items():
        require(digest(Path(name).read_bytes()) == expected, 'live input drift: ' + name)
    saved = output / 'patches'
    require(sorted(p.name for p in saved.iterdir()) == expected_names, 'saved inventory drift')
    for patch in result['patches']:
        require(digest((saved / patch['name']).read_bytes()) == patch['sha256'], 'saved patch drift')
    require(digest((output / 'upstream.tar').read_bytes()) == result['archive_sha256'], 'archive drift')
    require(inventory(output / 'prepared') == result['prepared_files'], 'prepared tree drift')
    return 'PASS_FIXED_INPUTS_INVENTORIES_AND_PREPARED_BYTES_NOT_ATOMIC_LOCK'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    tree, result = prepare(args.upstream_cache, args.output)
    print(json.dumps({'status': result['status'], 'prepared': str(tree),
                      'patches': len(result['patches']), 'files': len(result['prepared_files'])}))


if __name__ == '__main__':
    main()
