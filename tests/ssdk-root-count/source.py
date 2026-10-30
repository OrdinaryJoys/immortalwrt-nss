"""COUNT21 derivation; reuse only current A1 extraction, never its prepare gate."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[2]
PACKAGE = SOURCE / 'package/qca-nss/qca-ssdk'
EXTRACTOR = SOURCE / 'tests/ssdk-root-lifecycle/source.py'
PIN = 'd9a196497ecee2530722d906e0efe1b7408b6ef6'
BASE_SHA = '04d4e1017874d8354d2a6f77d1ff963efa6d102926a6a77da27813dacbde59e0'
PATCH = '033-ssdk-bound-root-count-before-phy-allocation.patch'
PATCH_SHA = 'af7dcabe60503bc81f128b97fcc926d071a973a9863e88f3f61ffcb24682ea83'
OWNED = ['README.md', 'fixture.c', 'mutations.py', 'source.py']
DTS = 'src/init/ssdk_dts.c'


def require(ok, marker):
    if not ok:
        raise RuntimeError(marker)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    return digest(Path(path).read_bytes())


def inventory(root):
    require(root.is_dir(), 'missing-tree')
    result = {}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'tree-symlink')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = identity(p)
    return result


def owned():
    root = SOURCE / 'tests/ssdk-root-count'
    require(sorted(p.name for p in root.iterdir()) == OWNED, 'owned-inventory')
    return [SOURCE / 'tests/test-ssdk-root-count-admission.py', *(root / name for name in OWNED)]


def patches():
    return sorted(p.name for p in (PACKAGE / 'patches').glob('*.patch'))


def extractor():
    spec = importlib.util.spec_from_file_location('count_current_a1_extraction', EXTRACTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract(tree):
    # Only this pure operation is reused. No A1 assets(), receipt(), prepare(),
    # runner, generated program or old PASS is invoked or borrowed.
    bodies, enum, macro, records = extractor().extract(tree)
    config = (tree / 'include/common/sw_config.h').read_text()
    found = re.findall(r'^\s*#define\s+SW_MAX_NR_DEV[ \t]+(\d+)[ \t]*$', config, re.M)
    require(found == ['3'], 'actual-capacity3-profile')
    declaration = re.search(r'^\s*#define\s+SW_MAX_NR_DEV[ \t]+3[ \t]*$', config, re.M).group().strip()
    error_header = (tree / 'include/common/sw_error.h').read_text()
    errors = re.findall(r'typedef enum\s*\{[^}]*\}\s*sw_error_t;', error_header)
    require(len(errors) == 1, 'actual-sw-error-enum')
    return bodies, enum, macro, records, declaration, errors[0], int(found[0])


def render(tree, template):
    bodies, enum, macro, records, capacity, errors, number = extract(tree)
    text = template.replace('/* @ACTUAL_ENUM@ */', enum)
    text = text.replace('/* @ACTUAL_ERROR_MACRO@ */', macro)
    text = text.replace('/* @ACTUAL_FUNCTIONS@ */', '\n'.join(bodies.values()))
    text = text.replace('/* @ACTUAL_SW_ERRORS@ */', errors)
    text = text.replace('/* @ACTUAL_CAPACITY@ */', capacity)
    require('@ACTUAL_' not in text, 'fixture-placeholder')
    return text, records, number


def receipt(root, sha, layers, historical=False):
    require(identity(root / 'RESULTS.json') == sha, 'receipt-identity')
    data = json.loads((root / 'RESULTS.json').read_text())
    require(data['status'] == 'PASS_TEXT_ONLY' and data['pin'] == PIN and
            len(data['patches']) == layers, 'receipt-status-pin-layers')
    raw = (root / 'upstream.tar').read_bytes()
    require(digest(raw) == data['archive_sha256'], 'archive-identity')
    derived = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        require(tar.pax_headers.get('comment') == PIN, 'archive-pin')
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and '.git' not in name.parts and
                    (member.isfile() or member.isdir()), 'archive-member')
            if member.isfile():
                require(str(name) not in derived, 'archive-duplicate')
                derived[str(name)] = digest(tar.extractfile(member).read())
    require(derived == data['upstream_files'], 'archive-derived-manifest')
    names = [entry['name'] for entry in data['patches']]
    require(sorted(p.name for p in (root / 'patches').iterdir()) == names, 'saved-inventory')
    for entry in data['patches']:
        path = PACKAGE / 'patches' / entry['name']
        require(identity(path) == identity(root / 'patches' / entry['name']) == entry['sha256'] ==
                data['inputs'][str(path)], 'saved-live-patch-identity')
        require(entry['status'] == 'PASS_DECLARED_CONTEXT_AND_OUTPUT' and entry['returncode'] == 0,
                'patch-status')
        for name, context in entry['declared_context'].items():
            require(derived.get(name) == context['before_sha256'] and context['hunks'] and
                    all(h['offset'] == 0 and h['full_context'] for h in context['hunks']), 'derived-preimage')
            derived[name] = context['after_sha256']
    require(derived == data['prepared_files'] and len(derived) == 692 and
            inventory(root / 'prepared') == derived, 'whole-derived-tree')
    delta = None
    for name, expected in data['inputs'].items():
        raw = Path(name).read_bytes()
        if historical and Path(name) == PACKAGE / 'Makefile':
            require(raw.count(b'PKG_RELEASE:=11\n') == 1 and
                    digest(raw.replace(b'PKG_RELEASE:=11\n', b'PKG_RELEASE:=10\n', 1)) == expected,
                    'historical-only-release10-to11')
            delta = {'path': name, 'baseline_release': 10, 'actual_release': 11,
                     'baseline_sha256': expected, 'actual_sha256': digest(raw),
                     'only_delta': 'unique exact PKG_RELEASE:=10 newline -> :=11 newline'}
        else:
            require(digest(raw) == expected, 'receipt-live-input:' + name)
    return data, delta


def prepare(base, candidate, candidate_sha, output):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from edma_patch_context import inspect_patch
    before, delta = receipt(base, BASE_SHA, 20, historical=True)
    after, _ = receipt(candidate, candidate_sha, 21)
    require(after['patches'][:-1] == before['patches'], 'exact20-prefix')
    names = [p['name'] for p in after['patches']]
    require(names == patches() and names[-1] == PATCH and
            after['patches'][-1]['sha256'] == PATCH_SHA, 'current21-inventory-and033')
    expected, context = inspect_patch(base / 'prepared', (PACKAGE / 'patches' / PATCH).read_bytes())
    require(set(expected) == {DTS} and context == after['patches'][-1]['declared_context'], '033-exact-context')
    derived = dict(before['prepared_files'])
    derived.update({name: digest(raw) for name, raw in expected.items()})
    require(derived == after['prepared_files'] and
            (candidate / 'prepared' / DTS).read_bytes() == expected[DTS], '033-full-output-derivation')
    old = extract(base / 'prepared')
    new = extract(candidate / 'prepared')
    name = 'ssdk_switch_device_num_init'
    original = (base / 'prepared' / DTS).read_text()
    require(original.count(old[0][name]) == 1 and
            original.replace(old[0][name], new[0][name], 1).encode() == expected[DTS],
            'only-complete-dt-init-changed')
    require(all(body == new[0][key] for key, body in old[0].items() if key != name) and
            old[1:3] == new[1:3] and old[4:] == new[4:], 'other-five-functions-types-capacity-preserved')
    bound = set(owned()) | {EXTRACTOR, SOURCE / 'tests/SSDK_ROOT_COUNT_PLAN_2026-10-30.md'}
    bound.update(Path(path) for path in after['inputs'])
    for root in (base, candidate):
        bound.update([root / 'RESULTS.json', root / 'upstream.tar'])
        bound.update((root / 'patches').iterdir())
    result = {'pin': PIN, 'patch_name': PATCH, 'patch_sha256': PATCH_SHA,
              'baseline_receipt_sha256': BASE_SHA, 'candidate_receipt_sha256': candidate_sha,
              'base': str(base), 'candidate': str(candidate), 'base_manifest': before['prepared_files'],
              'derived_candidate': derived, 'patch_inventory': names, 'actual_capacity': new[-1],
              'capacity_header': 'include/common/sw_config.h', '033_context': context,
              'historical_recipe_delta': delta, 'only_complete_dt_init_changed': True,
              'current_A1_reused_operations': ['extract'], 'current_A1_asset_sha256': identity(EXTRACTOR),
              'old_qualification_or_prepare_gate_reused': False,
              'inputs': {str(p): identity(p) for p in sorted(bound)}}
    (output / 'INPUTS.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def stable(inputs):
    owned()
    require(patches() == inputs['patch_inventory'], 'end-patch-inventory')
    for name, expected in inputs['inputs'].items():
        require(identity(name) == expected, 'end-input-drift:' + name)
    require(inventory(Path(inputs['base']) / 'prepared') == inputs['base_manifest'], 'end-baseline-tree')
    require(inventory(Path(inputs['candidate']) / 'prepared') == inputs['derived_candidate'], 'end-candidate-tree')
    return 'PASS_ALL_BOUND_HASHES_INVENTORIES_AND_FULL_DERIVED_TREES_NOT_ATOMIC_LOCK'
