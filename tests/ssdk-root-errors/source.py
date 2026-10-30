"""A2-only whole-tree and receipt binding. No old audit program is imported."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[2]
PACKAGE = SOURCE / 'package/qca-nss/qca-ssdk'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
BASE_SHA = '6116c3dc33695a70d8a28757349400e2220b75b13dcc8431fd36c8fdd8958def'
PATCH_NAME = '032-ssdk-cleanup-first-error-reporting.patch'
PATCH_SHA = '8a7e71bc84dd94ccad890801cfc8f1d8aaf11c24846d18b0c1ac749143286f93'
INIT = 'src/init/ssdk_init.c'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']


def require(ok, marker):
    if not ok:
        raise RuntimeError(marker)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    return digest(Path(path).read_bytes())


def inventory(tree):
    require(tree.is_dir(), 'missing-tree')
    result = {}
    for path in sorted(tree.rglob('*')):
        require(not path.is_symlink(), 'tree-symlink')
        if path.is_file():
            result[path.relative_to(tree).as_posix()] = identity(path)
    return result


def owned():
    directory = SOURCE / 'tests/ssdk-root-errors'
    require(sorted(p.name for p in directory.iterdir()) == OWNED, 'owned-inventory')
    return [SOURCE / 'tests/test-ssdk-root-cleanup-errors.py',
            *(directory / name for name in OWNED)]


def patch_names():
    return sorted(p.name for p in (PACKAGE / 'patches').glob('*.patch'))


def function(text, name):
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27'
    clean = re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text)
    matches = list(re.finditer(r'(?m)^[ \t]*(?:static\s+)?(?:void|sw_error_t)\s+(?:__exit\s+)?' + name + r'\s*\([^;{}]*\)\s*\{', clean))
    require(len(matches) == 1, 'complete-definition:' + name)
    start, end, depth = matches[0].start(), matches[0].end(), 1
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    require(depth == 0, 'unclosed-definition:' + name)
    return text[start:end], text.count('\n', 0, start) + 1


def extract(tree):
    text = (tree / INIT).read_text()
    bodies, records = {}, []
    for name in ('ssdk_cleanup', 'regi_exit'):
        body, line = function(text, name)
        bodies[name] = body
        records.append({'function': name, 'line': line, 'path': INIT,
                        'sha256': digest(body.encode()), 'complete_body': True})
    header = (tree / 'include/common/sw_error.h').read_text()
    matches = re.findall(r'typedef enum\s*\{[^}]*\}\s*sw_error_t;', header)
    require(len(matches) == 1, 'actual-sw-error-type')
    enum = matches[0]
    clean_enum = re.sub(r'/\*[\s\S]*?\*/', '', enum)
    errors = {name: int(value) for name, value in re.findall(r'\b(SW_\w+)\s*=\s*(-?\d+)', clean_enum)}
    require(len(errors) == 30 and set(errors.values()) == set(range(-29, 1)), 'actual-error-domain')
    return bodies, enum, records, errors


def render(tree, template):
    bodies, enum, records, errors = extract(tree)
    result = template.replace('/* @ACTUAL_ERROR_ENUM@ */', enum)
    result = result.replace('/* @ACTUAL_FUNCTIONS@ */', '\n\n'.join(bodies.values()))
    require('@ACTUAL_' not in result, 'unfilled-fixture')
    return result, records, errors


def receipt(directory, expected_sha, layers, historical=False):
    path = directory / 'RESULTS.json'
    require(identity(path) == expected_sha, 'receipt-sha')
    data = json.loads(path.read_text())
    require(data['status'] == 'PASS_TEXT_ONLY' and data['pin'] == PIN and
            len(data['patches']) == layers, 'receipt-status-pin-layers')
    raw = (directory / 'upstream.tar').read_bytes()
    require(digest(raw) == data['archive_sha256'], 'archive-sha')
    derived = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'archive-pin')
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and
                    '.git' not in name.parts and (member.isfile() or member.isdir()), 'archive-member')
            if member.isfile():
                require(str(name) not in derived, 'archive-duplicate')
                derived[str(name)] = digest(tar.extractfile(member).read())
    require(derived == data['upstream_files'], 'upstream-derived-manifest')
    names = [entry['name'] for entry in data['patches']]
    require(sorted(p.name for p in (directory / 'patches').iterdir()) == names,
            'saved-patch-inventory')
    for entry in data['patches']:
        live = PACKAGE / 'patches' / entry['name']
        require(identity(live) == identity(directory / 'patches' / entry['name']) ==
                entry['sha256'] == data['inputs'][str(live)], 'saved-live-patch')
        require(entry['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and entry['returncode'] == 0,
                'patch-receipt-status')
        for name, context in entry['declared_context'].items():
            require(derived.get(name) == context['before_sha256'] and context['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in context['hunks']), 'patch-derived-preimage')
            derived[name] = context['after_sha256']
    require(derived == data['prepared_files'] and len(derived) == 692 and
            inventory(directory / 'prepared') == derived, 'whole-derived-tree')
    recipe_delta = None
    for name, expected in data['inputs'].items():
        actual = Path(name).read_bytes()
        if historical and Path(name) == PACKAGE / 'Makefile':
            require(actual.count(b'PKG_RELEASE:=10\n') == 1 and
                    digest(actual.replace(b'PKG_RELEASE:=10\n', b'PKG_RELEASE:=9\n', 1)) == expected,
                    'historical-recipe-exact-9-to-10')
            recipe_delta = {'path': name, 'baseline_release': 9, 'actual_release': 10,
                            'baseline_sha256': expected, 'actual_sha256': digest(actual),
                            'only_delta': 'unique exact PKG_RELEASE:=9 newline -> :=10 newline'}
        else:
            require(digest(actual) == expected, 'receipt-live-input:' + name)
    return data, recipe_delta


def prepare(base, candidate, candidate_sha, output):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from edma_patch_context import inspect_patch
    before, delta = receipt(base, BASE_SHA, 19, historical=True)
    after, _ = receipt(candidate, candidate_sha, 20)
    require(after['patches'][:-1] == before['patches'], 'exact-19-prefix')
    names = [p['name'] for p in after['patches']]
    require(names == patch_names(), 'complete-live-inventory')
    require(names[-1] == PATCH_NAME and after['patches'][-1]['sha256'] == PATCH_SHA,
            'frozen-032-name-and-sha')
    patch = PACKAGE / 'patches' / names[-1]
    expected, contexts = inspect_patch(base / 'prepared', patch.read_bytes())
    require(set(expected) == {INIT} and contexts == after['patches'][-1]['declared_context'],
            '032-actual-declared-context')
    derived = dict(before['prepared_files'])
    derived.update({name: digest(raw) for name, raw in expected.items()})
    require(derived == after['prepared_files'] and
            (candidate / 'prepared' / INIT).read_bytes() == expected[INIT], '032-whole-output-derivation')
    old_bodies = extract(base / 'prepared')[0]
    new_bodies = extract(candidate / 'prepared')[0]
    rebuilt = (base / 'prepared' / INIT).read_text()
    for name in old_bodies:
        require(rebuilt.count(old_bodies[name]) == 1, 'function-replacement-anchor')
        rebuilt = rebuilt.replace(old_bodies[name], new_bodies[name], 1)
    require(rebuilt.encode() == expected[INIT], 'two-complete-functions-only-diff')
    bound = set(owned())
    bound.add(SOURCE / 'tests/SSDK_ROOT_ROLLBACK_PLAN_2026-10-30.md')
    bound.update(Path(path) for path in after['inputs'])
    for directory in (base, candidate):
        bound.update([directory / 'RESULTS.json', directory / 'upstream.tar'])
        bound.update((directory / 'patches').iterdir())
    inputs = {'pin': PIN, 'patch_sha256': PATCH_SHA, 'patch_name': names[-1],
              'base': str(base), 'candidate': str(candidate), 'baseline_receipt_sha256': BASE_SHA,
              'candidate_receipt_sha256': candidate_sha,
              'base_manifest': before['prepared_files'], 'derived_candidate': derived,
              'recipe_delta_from_historical_A1': delta, 'patch_inventory': names,
              '032_context': contexts, 'two_complete_functions_only_diff': True,
              'inputs': {str(path): identity(path) for path in sorted(bound)},
              'A1_test_assets_bound_or_imported': False,
              'old_program_executed': False}
    (output / 'INPUTS.json').write_text(json.dumps(inputs, indent=2) + '\n')
    return inputs


def stable(inputs):
    owned()
    require(patch_names() == inputs['patch_inventory'], 'end-patch-inventory')
    for path, expected in inputs['inputs'].items():
        require(identity(path) == expected, 'end-input-drift:' + path)
    require(inventory(Path(inputs['base']) / 'prepared') == inputs['base_manifest'], 'end-base-tree')
    require(inventory(Path(inputs['candidate']) / 'prepared') == inputs['derived_candidate'], 'end-candidate-tree')
    return 'PASS_FIXED_INPUTS_INVENTORIES_AND_FULL_DERIVED_TREES_NOT_ATOMIC_LOCK'
