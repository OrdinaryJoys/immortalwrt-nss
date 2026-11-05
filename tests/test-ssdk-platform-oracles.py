#!/usr/bin/env python3
"""Reader/oracle controls only, not a driver or clock campaign."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('platform_test', Path(__file__).with_name('test-ssdk-platform-resources.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def sample(self):
        return dict(status='PLATFORM_CASE', maps=1, unmaps=1, claims=0, releases=0,
                    enables=1, disables=1, gcc_starts=0, gcc_stops=0)

    def test_positive(self):
        self.assertTrue(m.outcome(0, json.dumps(self.sample()).encode(), b''))

    def test_precise_negative(self):
        self.assertTrue(m.outcome(86, b'', b'PLATFORM:MAP_LEAK\n', 'MAP_LEAK'))
        for code in (True, False, '86', 0, 1, -6, 97, 98, None):
            self.assertFalse(m.outcome(code, b'', b'PLATFORM:MAP_LEAK\n', 'MAP_LEAK'))

    def test_negative_noise_not_credit(self):
        for out, err in [(b'noise', b'PLATFORM:MAP_LEAK\n'), (b'', b'PLATFORM:WRONG\n'),
                         (b'', b'PLATFORM:MAP_LEAK\nnoise'), (b'', b'AddressSanitizer: DEADLYSIGNAL')]:
            self.assertFalse(m.outcome(86, out, err, 'MAP_LEAK'))

    def test_positive_strict_process(self):
        raw = json.dumps(self.sample()).encode()
        for code in (True, False, '0', 1, -11, None):
            self.assertFalse(m.outcome(code, raw, b''))
        self.assertFalse(m.outcome(0, raw, b'warning'))

    def test_duplicate_key_rejected(self):
        raw = json.dumps(self.sample()).replace('"maps": 1', '"maps": 0, "maps": 1').encode()
        self.assertFalse(m.outcome(0, raw, b''))

    def test_typed_counts(self):
        for value in (True, False, '1', -1, 1.0, None):
            row = self.sample(); row['maps'] = value
            self.assertFalse(m.outcome(0, json.dumps(row).encode(), b''))

    def test_extra_missing_and_status(self):
        for row in (dict(self.sample(), extra=1), dict(self.sample(), status='PASS'),
                    {k:v for k,v in self.sample().items() if k != 'unmaps'}):
            self.assertFalse(m.outcome(0, json.dumps(row).encode(), b''))
        for raw in (b'[]', b'null', b'{}', b'"PLATFORM_CASE"', b'invalid'):
            self.assertFalse(m.outcome(0, raw, b''))

    def test_fixed_failure_prefix_counts(self):
        self.assertEqual(m.expected_simple(['HPPE', 'DESS', 'IN_UNIPHY'], 7, 3, 0),
                         dict(status='PLATFORM_CASE', maps=2, unmaps=2, claims=1, releases=1,
                              enables=0, disables=0, gcc_starts=0, gcc_stops=0))
        self.assertEqual(m.expected_simple(['HPPE', 'DESS', 'IN_UNIPHY'], 3, 2, 1),
                         dict(status='PLATFORM_CASE', maps=1, unmaps=1, claims=0, releases=0,
                              enables=0, disables=0, gcc_starts=0, gcc_stops=0))

    def test_fixed_null_and_failed_clock_counts(self):
        row = self.sample()
        self.assertEqual(m.expected_simple(['HPPE'], 2, 0, 3), row)
        row['disables'] = 0
        self.assertEqual(m.expected_simple(['HPPE'], 2, 0, 4), row)
        self.assertEqual(m.expected_simple(['HPPE'], 2, 0, 5),
                         dict(status='PLATFORM_CASE', maps=1, unmaps=1, claims=0, releases=0,
                              enables=0, disables=0, gcc_starts=1, gcc_stops=1))

    def test_export_balanced_and_strict(self):
        self.assertEqual(m.sdk_view('hidden\n/*qca808x_start*/\nkept\n/*qca808x_end*/\nhidden'), 'kept\n')
        for raw in ('/*qca808x_start*/', '/*qca808x_end*/',
                    '/*qca808x_start*/\n/*qca808x_start*/\n/*qca808x_end*/'):
            with self.assertRaises(ValueError): m.sdk_view(raw)

    def test_actual_complete_source_admission(self):
        package = m.ROOT/'package/qca-nss/qca-ssdk'
        inventory = m.inventory(package/'patches')
        recipe = (package/'Makefile').read_bytes()
        m.admit_source(inventory, recipe)
        for change in ('extra', 'missing', 'prefix-drift', 'last-drift'):
            mutated = dict(inventory)
            if change == 'extra': mutated['series'] = '0'*64
            elif change == 'missing': mutated.pop(next(iter(mutated)))
            elif change == 'prefix-drift': mutated[next(k for k in mutated if k != m.PATCH.name)] = '0'*64
            else: mutated[m.PATCH.name] = '0'*64
            with self.subTest(change=change), self.assertRaises(ValueError): m.admit_source(mutated, recipe)
        with self.assertRaises(ValueError): m.admit_source(inventory, recipe+b'\n')


if __name__ == '__main__':
    unittest.main()
