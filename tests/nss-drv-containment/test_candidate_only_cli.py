#!/usr/bin/env python3
"""CLI mode checks; success cases compile actual already-prepared DRV C."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
RUNNER=HERE/'test-nss-drv-containment.py'


class CandidateOnlyModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('DRV_HOST_BASELINE') or not os.environ.get('DRV_HOST_CANDIDATE'):
            raise RuntimeError('set DRV_HOST_BASELINE and DRV_HOST_CANDIDATE to actual already-prepared inputs')
        cls.baseline=Path(os.environ['DRV_HOST_BASELINE']).resolve(strict=True)
        cls.candidate=Path(os.environ['DRV_HOST_CANDIDATE']).resolve(strict=True)

    def invoke(self,arguments,output):
        return subprocess.run([sys.executable,str(RUNNER),*arguments,'--output',str(output)],
                              text=True,capture_output=True,timeout=90,
                              env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

    def reject(self,arguments,message):
        with tempfile.TemporaryDirectory(prefix='drv-cli-mode-') as directory:
            output=Path(directory)/'not-created'; result=self.invoke(arguments,output)
            self.assertEqual(result.returncode,2,result.stderr); self.assertIn(message,result.stderr)
            self.assertFalse(output.exists(),'invalid arguments must fail before output mutation')

    def test_candidate_only_requires_candidate(self):
        self.reject(['--candidate-only'],'--candidate-only requires --candidate')

    def test_candidate_only_forbids_baseline(self):
        self.reject(['--candidate-only','--candidate',str(self.candidate),'--baseline',str(self.baseline)],'--candidate-only forbids --baseline')

    def test_candidate_without_explicit_mode_rejected(self):
        self.reject(['--candidate',str(self.candidate)],'--baseline is required unless explicit --candidate-only')

    def test_no_inputs_rejected(self):
        self.reject([],'--baseline is required unless explicit --candidate-only')

    def execute(self,arguments):
        with tempfile.TemporaryDirectory(prefix='drv-cli-actual-c-') as directory:
            output=Path(directory)/'result'; result=self.invoke(arguments,output)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((output/'RESULT.json').read_text())
            self.assertFalse(report['kernel_or_ax6_acceptance']); self.assertFalse(report['network_access'])
            self.assertEqual(report['host_dimensions']['irq_slots_per_mock_core'],2)
            self.assertEqual(report['host_dimensions']['ipq807x_source_irq_slots_per_core'],10)
            self.assertEqual(report['host_dimensions']['primary_port_ifnum'],1)
            for row in report['runs']:
                for source in row['sources']:
                    self.assertEqual(source['sha256'],hashlib.sha256((Path(row['prepared_root'])/source['path']).read_bytes()).hexdigest())
                emergency=[entry for entry in row['extracted_definitions'] if entry.get('function')=='nss_core_handle_napi_emergency']
                self.assertEqual(len(emergency),1,'actual emergency poll must be extracted in every variant')
                self.assertEqual(row['compiler_diagnostics'],''); self.assertEqual(row['execution_stderr'],'')
            for asset in report['test_assets']:
                self.assertEqual(asset['sha256'],hashlib.sha256((HERE/asset['path']).read_bytes()).hexdigest())
            return report

    def test_candidate_only_37_actual_roles_hashes_and_guards(self):
        report=self.execute(['--candidate-only','--candidate',str(self.candidate)])
        self.assertEqual(report['mode'],'CANDIDATE_ONLY_37'); self.assertFalse(report['original_baseline_executed'])
        self.assertIsNone(report['selected_inputs']['baseline']); self.assertEqual(report['total_cases'],37)
        self.assertEqual(report['expected_cases'],37); self.assertEqual([row['count'] for row in report['runs']],[20,7,7,3])
        self.assertEqual([row['input_role'] for row in report['runs']],['ACTUAL_IPQ807x_CANDIDATE','ACTUAL_CANDIDATE_OTHER_SOC_LEGACY_CONTROL','WRONG_SOC_MACRO_LEGACY_DEFECT_NEGATIVE_CONTROL','ACTUAL_IPQ807x_CANDIDATE_NON_GENERIC_CONTROL'])
        self.assertTrue(all(row['prepared_root']==str(self.candidate) for row in report['runs']))
        self.assertEqual([row['soc_define'] for row in report['runs']],['NSS_HAL_IPQ807x_SUPPORT',None,'NSS_HAL_IPQ807X_SUPPORT','NSS_HAL_IPQ807x_SUPPORT'])
        self.assertEqual([row['generic_support'] for row in report['runs']],[True,True,True,False])

    def test_baseline_plus_candidate_44_separate_original_controls(self):
        report=self.execute(['--baseline',str(self.baseline),'--candidate',str(self.candidate)])
        self.assertEqual(report['mode'],'BASELINE_AND_CANDIDATE_44'); self.assertTrue(report['original_baseline_executed'])
        self.assertEqual(report['total_cases'],44); self.assertEqual([row['count'] for row in report['runs']],[7,20,7,7,3])
        self.assertEqual(report['runs'][0]['input_role'],'ORIGINAL_BASELINE_DEFECT_CONTROL')
        self.assertEqual(report['runs'][0]['prepared_root'],str(self.baseline))

    def test_baseline_only_is_not_candidate_acceptance(self):
        report=self.execute(['--baseline',str(self.baseline)])
        self.assertEqual(report['mode'],'BASELINE_ONLY_7_CANDIDATE_INCOMPLETE')
        self.assertEqual(report['candidate_status'],'INCOMPLETE_NO_CANDIDATE_EXECUTED')
        self.assertEqual(report['total_cases'],7); self.assertEqual(len(report['runs']),1)


if __name__=='__main__': unittest.main()
