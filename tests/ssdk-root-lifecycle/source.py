"""A1 extraction and receipt-derived source eligibility; never run old tools."""
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
PATCH = '031-ssdk-root-topology-ownership.patch'
BASE_RECEIPT_SHA = 'c6a4077173600152571736f3a851e4976e1f21538330b24b073a0c1cdb6e2794'
FUNCTIONS = {
    'src/init/ssdk_dts.c': ['ssdk_switch_device_num_init',
                            'ssdk_switch_device_num_exit', 'ssdk_switch_device_num_get'],
    'src/init/ssdk_init.c': ['ssdk_free_priv', 'ssdk_alloc_priv', 'regi_init'],
}
ASSET_NAMES = ['README.md', 'fixture.c', 'mutations.py', 'source.py']


def require(ok, marker):
    if not ok:
        raise RuntimeError(marker)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(Path(path).read_bytes())


def inventory(root):
    require(root.is_dir(), 'missing-tree')
    result = {}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'tree-symlink')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = file_hash(p)
    return result


def assets():
    directory = SOURCE / 'tests/ssdk-root-lifecycle'
    require(sorted(p.name for p in directory.iterdir()) == ASSET_NAMES,
            'owned-inventory')
    return [SOURCE / 'tests/test-ssdk-root-lifecycle.py',
            *(directory / name for name in ASSET_NAMES)]


def patch_inventory():
    return sorted(p.name for p in (PACKAGE / 'patches').glob('*.patch'))


def masked(text):
    pattern = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27'
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' '
                                            for c in m.group()), text)


def function(text, name):
    clean = masked(text)
    pattern = r'(?m)^[ \t]*(?:static\s+)?(?:int|void|a_uint32_t)\s+(?:__init\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, clean))
    require(len(matches) == 1, 'function-definition:' + name)
    match = matches[0]
    start, end, depth = match.start(), match.end(), 1
    while depth and end < len(clean):
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    require(depth == 0, 'function-unclosed:' + name)
    return text[start:end] + '\n', text.count('\n', 0, start) + 1


def extract(tree):
    bodies, records = {}, []
    for path, names in FUNCTIONS.items():
        text = (tree / path).read_text()
        for name in names:
            body, line = function(text, name)
            bodies[name] = body
            records.append({'path': path, 'function': name, 'line': line,
                            'sha256': digest(body.encode()), 'complete_body': True})
    header = (tree / 'include/init/ssdk_init.h').read_text()
    enums = re.findall(r'typedef enum\s*\{[^}]*\}\s*hsl_reg_mode;', header)
    require(len(enums) == 1, 'actual-hsl-reg-enum')
    shared = (tree / 'include/common/shared_func.h').read_text().splitlines(True)
    macro = []
    for i, line in enumerate(shared):
        if line.startswith('#define SW_CNTU_ON_ERROR_AND_COND1_OR_GOTO_OUT('):
            while True:
                macro.append(shared[i])
                if not shared[i].rstrip().endswith('\\'):
                    break
                i += 1
    require(macro, 'actual-root-error-macro')
    return bodies, enums[0], ''.join(macro), records


def render(tree, template):
    bodies, enum, macro, records = extract(tree)
    text = template.replace('/* @ACTUAL_ENUM@ */', enum)
    text = text.replace('/* @ACTUAL_ERROR_MACRO@ */', macro)
    text = text.replace('/* @ACTUAL_FUNCTIONS@ */', '\n'.join(bodies.values()))
    require('@ACTUAL_' not in text, 'fixture-placeholder')
    return text, records


def archive_manifest(path, expected_sha):
    raw = path.read_bytes()
    require(digest(raw) == expected_sha, 'archive-hash')
    derived = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'archive-pin')
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and
                    '.git' not in name.parts and (member.isfile() or member.isdir()),
                    'archive-member')
            if member.isfile():
                require(str(name) not in derived, 'archive-duplicate')
                derived[str(name)] = digest(tar.extractfile(member).read())
    return derived


def receipt(directory, expected_sha, expected_layers, expected_patch_sha=None,
            previous_release=False):
    report = directory / 'RESULTS.json'
    require(file_hash(report) == expected_sha, 'receipt-hash')
    data = json.loads(report.read_text())
    require(data['status'] == 'PASS_TEXT_ONLY' and data['pin'] == PIN,
            'receipt-status-pin')
    require(len(data['patches']) == expected_layers, 'receipt-layers')
    require(sorted(p.name for p in (directory / 'patches').iterdir()) ==
            [p['name'] for p in data['patches']], 'receipt-saved-inventory')
    derived = archive_manifest(directory / 'upstream.tar', data['archive_sha256'])
    require(derived == data['upstream_files'], 'receipt-upstream-manifest')
    for entry in data['patches']:
        name = entry['name']
        live = PACKAGE / 'patches' / name
        saved = directory / 'patches' / name
        require(file_hash(saved) == file_hash(live) == entry['sha256'],
                'receipt-patch-binding:' + name)
        require(data['inputs'][str(live)] == entry['sha256'], 'receipt-patch-input')
        require(entry['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and
                entry['returncode'] == 0, 'receipt-patch-status')
        for path, context in entry['declared_context'].items():
            require(derived.get(path) == context['before_sha256'], 'receipt-preimage')
            require(context['hunks'] and all(h['offset'] == 0 and h['full_context']
                                           for h in context['hunks']), 'receipt-context')
            derived[path] = context['after_sha256']
    if expected_patch_sha:
        require(data['patches'][-1]['name'] == PATCH and
                data['patches'][-1]['sha256'] == expected_patch_sha, 'candidate-freeze')
    require(derived == data['prepared_files'] and len(derived) == 692,
            'receipt-derived-manifest')
    require(inventory(directory / 'prepared') == derived, 'receipt-prepared-bytes')
    for path, identity in data['inputs'].items():
        if previous_release and Path(path) == PACKAGE / 'Makefile':
            raw = Path(path).read_bytes()
            require(raw.count(b'PKG_RELEASE:=10\n') == 1 and
                    digest(raw.replace(b'PKG_RELEASE:=10\n', b'PKG_RELEASE:=9\n', 1)) == identity,
                    'receipt-only-release9-to10')
        else:
            require(file_hash(path) == identity, 'receipt-live-input:' + path)
    return data


def prepare(base, candidate, candidate_sha, patch_sha, output,
            integration=None, integration_sha=None):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from edma_patch_context import inspect_patch
    base_data = receipt(base, BASE_RECEIPT_SHA, 18,
                        previous_release=integration is not None)
    candidate_data = receipt(candidate, candidate_sha, 19, patch_sha,
                             previous_release=integration is not None)
    names = [p['name'] for p in candidate_data['patches']]
    require(names[:-1] == [p['name'] for p in base_data['patches']] and
            (integration is not None or patch_inventory() == names), 'live-chain-inventory')
    require(candidate_data['patches'][:-1] == base_data['patches'], 'prefix-receipts')
    expected, contexts = inspect_patch(base / 'prepared',
                                       (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(expected) == {'src/init/ssdk_init.c', 'src/init/ssdk_dts.c'},
            'a1-patch-files')
    require(contexts == candidate_data['patches'][-1]['declared_context'],
            'a1-context-receipt')
    derived = dict(base_data['prepared_files'])
    derived.update({name: digest(raw) for name, raw in expected.items()})
    require(derived == candidate_data['prepared_files'], 'a1-full-derivation')
    for path, raw in expected.items():
        require((candidate / 'prepared' / path).read_bytes() == raw, 'a1-output-bytes')
    require(extract(base / 'prepared')[0]['ssdk_switch_device_num_exit'] ==
            extract(candidate / 'prepared')[0]['ssdk_switch_device_num_exit'],
            'a1-exit-preservation')
    integrated = None
    if integration is not None:
        integrated = receipt(integration, integration_sha, 20)
        require(integrated['patches'][:-1] == candidate_data['patches'] and
                integrated['patches'][-1]['name'] ==
                '032-ssdk-cleanup-first-error-reporting.patch' and
                integrated['patches'][-1]['sha256'] ==
                '8a7e71bc84dd94ccad890801cfc8f1d8aaf11c24846d18b0c1ac749143286f93',
                'integration-exact-prefix-and032')
        names = [p['name'] for p in integrated['patches']]
        require(patch_inventory() == names, 'integration-live-inventory')
        changed, context032 = inspect_patch(candidate / 'prepared',
            (PACKAGE / 'patches' / names[-1]).read_bytes())
        require(set(changed) == {'src/init/ssdk_init.c'} and
                context032 == integrated['patches'][-1]['declared_context'],
                'integration032-only-root-context')
        integrated_derived = dict(derived)
        integrated_derived.update({name: digest(raw) for name, raw in changed.items()})
        require(integrated_derived == integrated['prepared_files'],
                'integration032-full-tree-derivation')
        require(extract(candidate / 'prepared')[:3] == extract(integration / 'prepared')[:3],
                'integration-no-a1-function-or-type-drift')
    bound = set(assets())
    bound.add(SOURCE / 'tests/SSDK_ROOT_ROLLBACK_PLAN_2026-10-30.md')
    bound.update(Path(path) for path in candidate_data['inputs'])
    if integrated is not None:
        bound.update(Path(path) for path in integrated['inputs'])
    for directory in (base, candidate, *((integration,) if integration is not None else ())):
        bound.add(directory / 'RESULTS.json')
        bound.add(directory / 'upstream.tar')
        bound.update((directory / 'patches').iterdir())
    identities = {str(path): file_hash(path) for path in sorted(bound)}
    result = {'pin': PIN, 'patch_sha256': patch_sha, 'inputs': identities,
              'patch_inventory': names, 'owned_inventory': ASSET_NAMES,
              'base': str(base), 'candidate': str(candidate),
              'base_manifest': base_data['prepared_files'], 'derived_candidate': derived,
              'a1_context': contexts,
              'derivation': 'Pinned receipt/archive chain for 18; actual current inspect_patch for 031; full 692-file equality. No old program executed.',
              'baseline_receipt_sha256': BASE_RECEIPT_SHA,
              'candidate_receipt_sha256': candidate_sha}
    if integrated is not None:
        result['integration'] = str(integration)
        result['integration_receipt_sha256'] = integration_sha
        result['integration_manifest'] = integrated['prepared_files']
        result['integration_policy'] = 'Exact032 full-tree derivation; A1 functions/types unchanged; historical recipe differs only release9->10, current20 receipt matches all live inputs.'
    (output / 'INPUTS.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def stable(inputs):
    assets()
    require(patch_inventory() == inputs['patch_inventory'], 'end-patch-inventory')
    for path, identity in inputs['inputs'].items():
        require(file_hash(path) == identity, 'end-input-drift:' + path)
    require(inventory(Path(inputs['base']) / 'prepared') == inputs['base_manifest'],
            'end-baseline-drift')
    require(inventory(Path(inputs['candidate']) / 'prepared') == inputs['derived_candidate'],
            'end-candidate-drift')
    if 'integration' in inputs:
        require(inventory(Path(inputs['integration']) / 'prepared') ==
                inputs['integration_manifest'], 'end-integration-drift')
    return 'PASS_FIXED_HASHES_INVENTORIES_AND_DERIVED_TREES_NOT_ATOMIC_LOCK'
