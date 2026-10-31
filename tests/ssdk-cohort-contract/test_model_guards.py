"""Design-model regression controls, not mutations of actual SDK C."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CASES = (
    ('commit-replacement', 'test_publication_replacement_before_commit',
     '        need(self.publication == self.baseline, "publication-replaced")\n', ''),
    ('abort-replacement', 'test_publication_replacement_before_unpublished_abort',
     '        need(self.publication == (self.staged if self.published else self.baseline),\n'
     '             "publication-replaced")\n', ''),
    ('reader-replacement', 'test_publication_replacement_before_reader',
     '            need(internal or self.publication == self.staged, "publication-replaced")\n', ''),
    ('sfp-phy', 'test_sfp_before_phy_for_all_unresolved_states',
     'need(stage not in ("hsl", "phy") or cell.status.get("sfp")',
     'need(stage != "hsl" or cell.status.get("sfp")'),
    ('iterator', 'test_one_shot_selected_keeps_required_hsl',
     '        selected = frozenset(selected)\n'
     '        need("hsl" in selected and selected <= set(STAGES) - {"platform"}, "selected-stage")',
     '        need("hsl" in selected and set(selected) <= set(STAGES) - {"platform"}, "selected-stage")'),
    ('internal-hsl', 'test_internal_operation_cannot_revive_retired_hsl',
     '        if kind in ("fal", "uk"):\n'
     '            need(cell.status.get("hsl") in ("owned", "borrowed"), "hsl-not-ready")\n', ''),
)


def need(ok, why):
    if not ok:
        raise ValueError(why)


def run(body, case):
    contract = types.ModuleType('contract')
    sys.modules['contract'] = contract
    exec(compile(body, '<current-design-model-variant>', 'exec'), contract.__dict__)
    spec = importlib.util.spec_from_file_location('contract_tests', HERE / 'test_contract.py')
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(tests.Contracts(case))
    return result, output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    need(sys.flags.optimize > 0 and not a.output.exists(), 'FRESH_OPTIMIZED')
    a.output.mkdir(parents=True)
    assets = (Path(__file__), HERE / 'contract.py', HERE / 'test_contract.py')
    inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in assets}
    original = (HERE / 'contract.py').read_text()
    result = dict(status='INCOMPLETE', qualification='DESIGN_MODEL_GUARDS_NOT_SDK_SOURCE_TEST',
                  inputs=inputs, controls=[])
    try:
        need(len(CASES) == 6 and len({c[0] for c in CASES}) == 6, 'FIXED_CONTROLS')
        for name, test, before, after in CASES:
            need(original.count(before) == 1, 'EXACT_MUTATION_ANCHOR')
            positive, raw = run(original, test)
            (a.output / (name + '.positive.txt')).write_text(raw)
            need(positive.testsRun == 1 and positive.wasSuccessful(), 'POSITIVE_CONTROL')
            variant = original.replace(before, after)
            if name == 'iterator':
                # Restore the old store-time conversion as well as old multi-read validation.
                anchor = 'Cell(owner, selected, phy_type=phy_type)'
                need(variant.count(anchor) == 1, 'ITERATOR_STORE_ANCHOR')
                variant = variant.replace(anchor, 'Cell(owner, frozenset(selected), phy_type=phy_type)')
            negative, raw = run(variant, test)
            (a.output / (name + '.negative.txt')).write_text(raw)
            need(negative.testsRun == 1 and not negative.errors and negative.failures,
                 'SEMANTIC_TEST_FAILURE_NOT_INFRASTRUCTURE')
            marker = ("AssertionError: Items in the second set but not the first:\n'hsl'" if name == 'iterator'
                      else 'Rejected not raised')
            need(marker in raw, 'EXACT_REGRESSION_MARKER')
            result['controls'].append(dict(name=name, test=test, failures=len(negative.failures),
                                          variant_sha256=hashlib.sha256(variant.encode()).hexdigest()))
        need(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == v for p, v in inputs.items()),
             'ASSET_DRIFT')
        result['status'] = 'PASS_SIX_MODEL_GUARDS'
    except Exception as e:
        result['error'] = str(e)
    (a.output / 'RESULTS.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'error') if k in result}))
    return 0 if result['status'] == 'PASS_SIX_MODEL_GUARDS' else 1


if __name__ == '__main__':
    sys.exit(main())
