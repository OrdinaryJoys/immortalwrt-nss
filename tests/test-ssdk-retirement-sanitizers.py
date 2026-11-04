#!/usr/bin/env python3
"""Typed sanitizer oracles and instrumentation separation, not SDK qualification."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('retire_runner', Path(__file__).with_name('test-ssdk-retirement-admission.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Oracles(unittest.TestCase):
    def test_gcc11_commuted_operands_and_exact_overflow_identity(self):
        for operands in (b'2147483647 + 1', b'1 + 2147483647'):
            raw = (b'probe.c:2:77: runtime error: signed integer overflow: ' + operands +
                   b" cannot be represented in type 'int'\n    #0 in main\n")
            self.assertTrue(m.canary_result(98, b'', raw, 'ubsan'))
        for expression in (b'21474836470 + 1', b'2147483647 + 10', b'1 + 21474836470',
                           b'2147483647 - 1', b'1 * 2147483647'):
            raw = (b'runtime error: signed integer overflow: ' + expression +
                   b" cannot be represented in type 'int'\n")
            self.assertFalse(m.canary_result(98, b'', raw, 'ubsan'))
        prefix = b'runtime error: signed integer overflow: 2147483647 + 1'
        for suffix in (b'\n', b" cannot be represented in type 'long'\n",
                       b" cannot be represented in type 'int' trailing-noise\n"):
            self.assertFalse(m.canary_result(98, b'', prefix + suffix, 'ubsan'))

    def test_historical_witness_admission_is_not_current_qualification(self):
        spec = importlib.util.spec_from_file_location('historical_witness', Path(__file__).with_name('witness-ssdk-shared-ownership.py'))
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        old.admit_hashes(dict(old.HISTORICAL_FUNCTIONS))
        for name in old.HISTORICAL_FUNCTIONS:
            changed = dict(old.HISTORICAL_FUNCTIONS); changed[name] = '0' * 64
            with self.assertRaisesRegex(RuntimeError, 'historical SSDK36'): old.admit_hashes(changed)
        with self.assertRaises(RuntimeError): old.admit_hashes({})

    def test_directed_positive(self):
        self.assertTrue(m.canary_result(97, b'', b'ERROR: AddressSanitizer: heap-buffer-overflow\nWRITE of size 1\n', 'asan'))
        self.assertTrue(m.canary_result(98, b'', b"runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'\n", 'ubsan'))

    def test_actual_cloud_object_size_diagnostic_rejected(self):
        self.assertFalse(m.canary_result(97, b'', b'runtime error: store to address with insufficient space for char', 'asan'))

    def test_wrong_detector_and_mixed_reports(self):
        asan = b'ERROR: AddressSanitizer: heap-buffer-overflow\nWRITE of size 1\n'
        ubsan = b"runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'\n"
        for kind, code in (('asan', 97), ('ubsan', 98)):
            for err in (asan + ubsan, b'AddressSanitizer: DEADLYSIGNAL', b''):
                self.assertFalse(m.canary_result(code, b'', err, kind))
        self.assertFalse(m.canary_result(98, b'', asan, 'ubsan'))
        self.assertFalse(m.canary_result(97, b'', ubsan, 'asan'))

    def test_exit_and_output_pollution(self):
        raw = b'ERROR: AddressSanitizer: heap-buffer-overflow\nWRITE of size 1\n'
        for code in (True, False, '97', 0, 1, -6, 86, None, 'timeout'):
            self.assertFalse(m.canary_result(code, b'', raw, 'asan'))
        self.assertFalse(m.canary_result(97, b'noise', raw, 'asan'))

    def test_formal_profiles_still_use_both_detectors(self):
        for hppe in (False, True):
            flags = m.host_flags(hppe, True)
            self.assertIn('-fsanitize=address,undefined', flags)
            self.assertNotIn('-fsanitize=address,undefined', m.host_flags(hppe))
            self.assertEqual('-DHPPE=1' in flags, hppe)
            self.assertIn('-Werror', flags)


if __name__ == '__main__':
    unittest.main()
