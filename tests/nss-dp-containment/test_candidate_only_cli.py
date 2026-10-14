#!/usr/bin/env python3
"""CLI mode checks; successful cases compile actual already-prepared DP C."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / 'test-nss-dp-detach-quarantine.py'


class CandidateOnlyModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('DP_HOST_BASELINE') or not os.environ.get('DP_HOST_CANDIDATE'):
            raise RuntimeError('set DP_HOST_BASELINE and DP_HOST_CANDIDATE to exact already-prepared inputs')
        cls.baseline = Path(os.environ['DP_HOST_BASELINE']).resolve(strict=True)
        cls.candidate = Path(os.environ['DP_HOST_CANDIDATE']).resolve(strict=True)

    def invoke(self, arguments, output):
        return subprocess.run([sys.executable, str(RUNNER), *arguments, '--output', str(output)],
                              text=True, capture_output=True, timeout=90,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def reject(self, arguments, message):
        with tempfile.TemporaryDirectory(prefix='dp-cli-mode-') as directory:
            output = Path(directory) / 'not-created'
            result = self.invoke(arguments, output)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(message, result.stderr)
            self.assertFalse(output.exists(), 'invalid arguments must be rejected before output mutation')

    def test_candidate_only_requires_candidate(self):
        self.reject(['--candidate-only'], '--candidate-only requires --candidate')

    def test_candidate_only_forbids_baseline(self):
        self.reject(['--candidate-only', '--candidate', str(self.candidate), '--baseline', str(self.baseline)],
                    '--candidate-only forbids --baseline')

    def test_candidate_without_explicit_mode_rejected(self):
        self.reject(['--candidate', str(self.candidate)], '--baseline is required unless explicit --candidate-only')

    def test_no_inputs_rejected(self):
        self.reject([], '--baseline is required unless explicit --candidate-only')

    def execute(self, arguments):
        with tempfile.TemporaryDirectory(prefix='dp-cli-actual-c-') as directory:
            output = Path(directory) / 'result'
            result = self.invoke(arguments, output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / 'RESULT.json').read_text())
            self.assertFalse(report['kernel_or_ax6_acceptance'])
            for row in report['runs']:
                root = Path(row['prepared_root'])
                for source in row['sources']:
                    self.assertEqual(source['sha256'], hashlib.sha256((root / source['path']).read_bytes()).hexdigest())
            return report

    def test_candidate_only_26_actual_input_roles_hashes(self):
        report = self.execute(['--candidate-only', '--candidate', str(self.candidate)])
        self.assertEqual(report['mode'], 'CANDIDATE_ONLY_26')
        self.assertFalse(report['original_baseline_executed'])
        self.assertIsNone(report['selected_inputs']['baseline'])
        self.assertEqual(report['total_cases'], 26)
        self.assertEqual(report['expected_cases'], 26)
        self.assertEqual([row['count'] for row in report['runs']], [21, 5])
        self.assertEqual([row['input_role'] for row in report['runs']],
                         ['ACTUAL_PREPARED_CANDIDATE_IPQ807X', 'ACTUAL_PREPARED_CANDIDATE_OTHER_SOC_CONTROL'])
        self.assertTrue(all(row['prepared_root'] == str(self.candidate) for row in report['runs']))

    def test_baseline_plus_candidate_retains_31(self):
        report = self.execute(['--baseline', str(self.baseline), '--candidate', str(self.candidate)])
        self.assertEqual(report['mode'], 'BASELINE_AND_CANDIDATE_31')
        self.assertTrue(report['original_baseline_executed'])
        self.assertEqual(report['total_cases'], 31)
        self.assertEqual([row['count'] for row in report['runs']], [5, 21, 5])
        self.assertEqual(report['runs'][0]['input_role'], 'ORIGINAL_PREPARED_BASELINE_CONTROL')
        self.assertEqual(report['runs'][0]['prepared_root'], str(self.baseline))

    def test_baseline_only_is_not_candidate_acceptance(self):
        report = self.execute(['--baseline', str(self.baseline)])
        self.assertEqual(report['mode'], 'BASELINE_ONLY_5_CANDIDATE_INCOMPLETE')
        self.assertEqual(report['candidate_status'], 'INCOMPLETE_NO_CANDIDATE_EXECUTED')
        self.assertEqual(report['total_cases'], 5)
        self.assertEqual(len(report['runs']), 1)


if __name__ == '__main__':
    unittest.main()
