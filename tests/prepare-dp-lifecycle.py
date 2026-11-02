#!/usr/bin/env python3
"""Fresh pinned DP text replay; no make, target compiler, network or device access."""
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

PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
PACKAGE = Path(__file__).resolve().parents[1] / 'package/qca-nss/qca-nss-dp'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'symlink in prepared tree')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    recipe = (PACKAGE / 'Makefile').read_bytes()
    require(re.search(rb'^PKG_SOURCE_VERSION:=' + PIN.encode() + rb'$', recipe, re.M), 'DP pin')
    require(re.search(rb'^PKG_RELEASE:=10$', recipe, re.M), 'DP release')
    paths = sorted((PACKAGE / 'patches').iterdir())
    require(len(paths) == 19 and paths[-1].name ==
            '019-limit-stp-restore-to-departing-bridge-master.patch', 'DP patch inventory')
    patches = {}
    for index, path in enumerate(paths, 1):
        require(path.is_file() and not path.is_symlink() and
                path.name.startswith(f'{index:03}-') and path.suffix == '.patch',
                'nonconsecutive or unsafe patch')
        patches[path.name] = path.read_bytes()
    args.output.mkdir(parents=True, exist_ok=False)
    tree = args.output / 'prepared'
    tree.mkdir()
    process = subprocess.run(['git', '-C', str(args.upstream_cache), 'archive',
                              '--format=tar', PIN], capture_output=True, timeout=90)
    require(process.returncode == 0 and not process.stderr, 'exact Git archive')
    archive = process.stdout
    (args.output / 'upstream.tar').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'Git archive commit')
        for entry in tar.getmembers():
            name = PurePosixPath(entry.name)
            require(not name.is_absolute() and '..' not in name.parts and '.git' not in name.parts
                    and (entry.isfile() or entry.isdir()), 'unsafe archive entry')
            path = tree / str(name)
            if entry.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                require(not path.exists(), 'duplicate archive entry')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(entry).read())
    before = inventory(tree)
    derived = dict(before)
    saved = args.output / 'patches'
    saved.mkdir()
    report = {'status': 'INCOMPLETE', 'qualification': 'TEXT_ONLY_NO_TARGET_BUILD',
              'pin': PIN, 'recipe_sha256': digest(recipe), 'archive_sha256': digest(archive),
              'upstream_files': before, 'patches': []}
    for name, data in patches.items():
        (saved / name).write_bytes(data)
        expected, context = inspect_patch(tree, data)
        for relative, record in context.items():
            require(derived[relative] == record['before_sha256'], 'preimage drift')
        process = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-V', 'none'],
                                 cwd=tree, input=data, capture_output=True, timeout=60)
        (args.output / (name + '.stdout')).write_bytes(process.stdout)
        (args.output / (name + '.stderr')).write_bytes(process.stderr)
        require(process.returncode == 0 and not process.stderr and not re.search(
            rb'fuzz|offset|FAILED|reject|malformed|Reversed', process.stdout, re.I), 'patch: ' + name)
        verify_applied(tree, expected)
        derived.update({relative: digest(data) for relative, data in expected.items()})
        report['patches'].append({'name': name, 'sha256': digest(data), 'context': context})
    require(inventory(tree) == derived, 'complete derived output mismatch')
    require((PACKAGE / 'Makefile').read_bytes() == recipe and
            sorted(p.name for p in (PACKAGE / 'patches').iterdir()) == list(patches) and
            all((PACKAGE / 'patches' / n).read_bytes() == b for n, b in patches.items()),
            'live input drift')
    report.update(status='PASS_TEXT_ONLY', prepared_files=derived)
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'layers': len(patches), 'prepared': str(tree)}))


if __name__ == '__main__':
    main()
