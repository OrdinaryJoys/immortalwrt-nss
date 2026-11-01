#!/usr/bin/env python3
"""Profile and result checks imported by the existing CI extractor test entry."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dp_retirement_runner', HERE / 'test-nss-dp-detach-quarantine.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Inputs:
    def __init__(self, arch='', edma='', attach=''):
        self.files = {runner.ARCH: arch, runner.EDMA: edma, 'nss_dp_attach.c': attach,
                      runner.EDMA_HEADER: '#include <excluded.h>\n#define EDMA_RING_SIZE 128\n',
                      runner.EDMA_REGS: '#define EDMA_MASK_INT_CLEAR 0\n'}

    def read(self, path):
        return self.files[path]


class RetirementContract(unittest.TestCase):
    def test_result_pollution_controls(self):
        self.assertEqual(runner.check_result_oracles(), {'valid': 2, 'rejected_pollution': 16})

    def test_combined_sanitizers_share_an_unambiguous_exit_policy(self):
        for code in (97, 98):
            environment = runner.sanitizer_environment(code)
            self.assertTrue(environment['ASAN_OPTIONS'].endswith('exitcode=' + str(code)))
            self.assertTrue(environment['UBSAN_OPTIONS'].endswith('exitcode=' + str(code)))

    def test_pre015_and_comment_decoys_do_not_enable_profile(self):
        self.assertFalse(runner.has_retirement(Inputs()))
        self.assertFalse(runner.has_retirement(Inputs(arch='/* edma_retire_port */',
            edma='const char *s="edma_retire_port";', attach='// edma_retire_port\n')))

    def test_removing_call_cannot_silently_disable_existing_provider_tests(self):
        for inputs in (Inputs(arch='bool edma_retire_port(void);'),
                       Inputs(edma='bool edma_retire_port(void) { return false; }'),
                       Inputs(attach='void q(void) { edma_retire_port(0, 1); }')):
            self.assertTrue(runner.has_retirement(inputs))

    def test_actual_prototype_is_retained_and_includes_are_explicitly_substituted(self):
        prototype = 'bool edma_retire_port(struct net_device *netdev, uint32_t macid);'
        text = runner.retirement_header(Inputs(arch='#define NSS_DP_HAL_START_IFNUM 1\n' + prototype + '\n'))
        self.assertIn(prototype, text)
        self.assertIn('HOST_EDMA_RETIREMENT 1', text)
        self.assertNotIn('#include', text)

    def test_missing_duplicate_or_changed_abi_is_rejected(self):
        prototype = 'bool edma_retire_port(struct net_device *netdev, uint32_t macid);\n'
        prefix = '#define NSS_DP_HAL_START_IFNUM 1\n'
        for arch in (prefix, prefix + prototype * 2,
                     prefix + prototype.replace('bool ', 'int ', 1),
                     prefix + prototype.replace('uint32_t', 'uint16_t'),
                     prefix.replace('IFNUM 1', 'IFNUM 0') + prototype):
            with self.assertRaises(ValueError):
                runner.retirement_header(Inputs(arch=arch))

    def test_negative_gate_rejects_partial_pass_line_and_accepts_whole_prefix(self):
        positive = 'PASS one\nPASS two\n'
        self.assertFalse(runner.semantic_rejection(86, 'PASS one', 'DP_RETIRE reason\n', 'reason', positive))
        self.assertTrue(runner.semantic_rejection(86, 'PASS one\n', 'DP_RETIRE reason\n', 'reason', positive))

    def test_same_count_wrong_inventory_is_not_positive_acceptance(self):
        self.assertFalse(runner.positive_result(0, 'PASS unrelated\n', '', 1, ('required',)))
        self.assertTrue(runner.positive_result(0, 'PASS required\n', '', 1, ('required',)))


if __name__ == '__main__':
    unittest.main()
