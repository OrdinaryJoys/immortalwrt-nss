#!/usr/bin/env python3
"""Offline full-package declared-line replay and independent gate controls."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from edma_patch_context import inspect_patch, verify_applied

SOURCE = Path(__file__).resolve().parents[1]
PINS = {'qca-nss-dp':'d8f802f08fd8ff31057ba58edb20bbe448e7b505',
        'qca-mcs':'da120b15e7fe1168f4b42fca09642a542d3a1e76'}


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def controls():
    results = {}
    with tempfile.TemporaryDirectory(prefix='edma-context-') as temp:
        root = Path(temp)
        (root / 'a.c').write_text('prefix\none\ntwo\nthree\n')
        header = '--- a/a.c\n+++ b/a.c\n'
        valid = header + '@@ -2,2 +2,2 @@\n one\n-two\n+TWO\n'
        expected, _ = inspect_patch(root, valid.encode())
        require(expected['a.c'] == b'prefix\none\nTWO\nthree\n', 'valid replacement')
        results['valid-replacement'] = 'PASS'
        for name,body,wanted in [
            ('insert', '@@ -0,0 +1 @@\n+top\n', b'top\nprefix\none\ntwo\nthree\n'),
            ('delete', '@@ -1 +0,0 @@\n-prefix\n', b'one\ntwo\nthree\n'),
            ('two-hunks', '@@ -1 +1,2 @@\n prefix\n+added\n@@ -4 +5 @@\n-three\n+THREE\n',
             b'prefix\nadded\none\ntwo\nTHREE\n'),
        ]:
            actual, _ = inspect_patch(root,(header+body).encode())
            require(actual['a.c'] == wanted, 'valid '+name)
            results['valid-'+name] = 'PASS'
        (root / 'blank.c').write_text('\none\n')
        blank = '--- a/blank.c\n+++ b/blank.c\n@@ -1,2 +1,2 @@\n\n-one\n+ONE\n'
        blank_expected, _ = inspect_patch(root, blank.encode())
        require(blank_expected['blank.c'] == b'\nONE\n', 'unprefixed empty context')
        results['valid-empty-context'] = 'PASS'
        (root / 'blank.c').write_text('not-empty\none\n')
        try:
            inspect_patch(root, blank.encode())
        except ValueError:
            results['changed-empty-context'] = 'REJECTED'
        else:
            raise RuntimeError('empty context dropped')
        for name, text in {
            'silent-offset': valid.replace('-2,2 +2,2', '-3,2 +3,2'),
            'wrong-new-coordinate': valid.replace('+2,2', '+3,2'),
            'fuzzy-context': valid.replace(' one\n', ' nope\n'),
            'missing-body': valid.rsplit('+TWO\n', 1)[0],
            'wrong-count': valid.replace('-2,2', '-2,3'),
            'extra-body': valid + '+extra\n',
            'external-path': valid.replace('a/a.c', 'a/../a.c').replace('b/a.c', 'b/../a.c'),
            'no-newline': valid[:-1],
            'repeated-file': valid + valid,
            'overlap': valid + '@@ -2 +2 @@\n-one\n+ONE\n',
            'past-eof-insertion': header + '@@ -1000,0 +5 @@\n+extra\n',
            'past-eof-deletion': header + '@@ -4,2 +4 @@\n three\n-missing\n',
        }.items():
            try:
                inspect_patch(root, text.encode())
            except ValueError:
                results[name] = 'REJECTED'
            else:
                raise RuntimeError('context pollution accepted: ' + name)
        (root / 'a.c').write_bytes(expected['a.c'])
        verify_applied(root, expected)
        results['valid-output'] = 'PASS'
        (root / 'a.c').write_text('wrong\n')
        try:
            verify_applied(root, expected)
        except ValueError:
            results['wrong-output'] = 'REJECTED'
        else:
            raise RuntimeError('wrong output accepted')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--through', type=int, choices=(15, 16), default=15)
    parser.add_argument('--compare-to', type=Path)
    parser.add_argument('--package', choices=tuple(PINS), default='qca-nss-dp')
    parser.add_argument('--allowed-comparison-backup', action='append', default=[])
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pin = PINS[args.package]
    result = {'status':'INCOMPLETE','package':args.package,'pin':pin,
              'controls':controls(),'patches':[]}
    try:
        archive = subprocess.run(['git','-C',str(args.upstream_cache),'archive',pin],
                                 check=True,capture_output=True).stdout
        (out / 'upstream.tar').write_bytes(archive)
        result['archive_sha256'] = sha(archive)
        root = out / 'prepared'
        root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute()
                        and '..' not in Path(m.name).parts for m in tar.getmembers()),
                    'unsafe archive')
            tar.extractall(root)
        paths = sorted((SOURCE / 'package/qca-nss' / args.package / 'patches').glob('*.patch'))
        if args.package == 'qca-nss-dp':
            paths = [p for p in paths if int(p.name[:3]) <= args.through]
            numbers = list(range(1,args.through+1))
        else:
            numbers = [1,2,3,4,5,6,7,9,20,21]
        require([int(p.name[:3]) for p in paths] == numbers,
                'patch inventory')
        result['test_inputs'] = {str(p):sha(p.read_bytes()) for p in
                                 [Path(__file__),SOURCE/'tests/edma_patch_context.py']}
        for p in paths:
            data = p.read_bytes()
            entry = {'path':str(p),'sha256':sha(data)}
            result['patches'].append(entry)
            saved = out / p.name
            saved.write_bytes(data)
            expected, entry['declared_context'] = inspect_patch(root,data)
            applied = subprocess.run(['/usr/bin/patch','-p1','--fuzz=0','--batch',
                                      '-V','none','-i',str(saved)],cwd=root,
                                     capture_output=True,text=True)
            (out / (p.name+'.stdout')).write_text(applied.stdout)
            (out / (p.name+'.stderr')).write_text(applied.stderr)
            require(applied.returncode == 0 and not applied.stderr, 'patch failed')
            verify_applied(root,expected)
        result['files'] = {str(p.relative_to(root)):sha(p.read_bytes())
                           for p in sorted(root.rglob('*')) if p.is_file()}
        if args.compare_to:
            other = args.compare_to.resolve()
            compared = {str(p.relative_to(other)):sha(p.read_bytes())
                        for p in sorted(other.rglob('*')) if p.is_file()}
            extras = sorted(set(compared)-set(result['files']))
            require(extras == sorted(args.allowed_comparison_backup),
                    'unexpected comparison extra files')
            backup_records = {}
            for extra in extras:
                base = extra[:-5] if extra.endswith('.orig') else ''
                known = [entry['declared_context'][base]['before_sha256']
                         for entry in result['patches'] if base in entry['declared_context']]
                require(base in result['files'] and compared[extra] in known,
                        'comparison backup is not a known prepatch source')
                backup_records[extra] = {'sha256':compared.pop(extra),
                                          'matches_known_prepatch_data':True}
            require(compared == result['files'],'comparison source bytes differ')
            result['comparison'] = {'path':str(other),'all_file_bytes_match':True,
                                    'files':len(compared),'data_only':True,
                                    'explicit_backups':backup_records}
        result['status'] = 'PASS_DECLARED_CONTEXT'
    except Exception as exc:
        result['status']='FAIL';result['error']=str(exc)
        raise
    finally:
        (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'patches':len(result['patches']),
                      'controls':len(result['controls'])}))


if __name__ == '__main__':
    main()
