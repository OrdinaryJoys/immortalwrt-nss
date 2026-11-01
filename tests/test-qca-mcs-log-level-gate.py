#!/usr/bin/env python3
"""Isolated regression of the actual shell gate, never a driver/build test."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tests/test-qca-mcs-log-level.sh'
PATCH = ROOT / 'package/qca-nss/qca-mcs/patches/009-quiet-unconfigured-wifi-leave-events.patch'


class Gate(unittest.TestCase):
    def run_gate(self, release='PKG_RELEASE:=4\n', expected=None, edit=None, missing=False):
        with tempfile.TemporaryDirectory(prefix='ax6-mcs-gate-') as tmp:
            root = Path(tmp)
            script = root / 'tests' / SCRIPT.name
            script.parent.mkdir()
            shutil.copy2(SCRIPT, script)
            patch = root / PATCH.relative_to(ROOT)
            patch.parent.mkdir(parents=True)
            content = PATCH.read_text()
            patch.write_text(edit(content) if edit else content)
            if missing:
                patch.unlink()
            (patch.parent.parent / 'Makefile').write_text(release)
            env = dict(os.environ)
            env.pop('SOURCE_QCA_MCS_PKG_RELEASE', None)
            if expected is not None:
                env['SOURCE_QCA_MCS_PKG_RELEASE'] = expected
            proc = subprocess.run(['sh', str(script)], capture_output=True, text=True,
                                  timeout=10, env=env)
            return proc.returncode, proc.stdout, proc.stderr

    def reject(self, marker, **kwargs):
        code, out, err = self.run_gate(**kwargs)
        self.assertEqual(code, 1, (out, err))
        self.assertEqual(err, '')
        self.assertIn('FAIL: ' + marker + '\n', out)

    def test_floor_and_later_releases(self):
        for release in ('3', '4', '5', '27'):
            with self.subTest(release=release):
                code, out, err = self.run_gate('PKG_RELEASE:=' + release + '\n')
                self.assertEqual((code, err), (0, ''))
                self.assertIn('PASS: qca-mcs release retains quiet-patch floor r3\n', out)
                self.assertIn('=== summary: PASS=6 FAIL=0 ===\n', out)

    def test_exact_build_identity(self):
        for release in ('3', '4', '5'):
            code, out, err = self.run_gate('PKG_RELEASE:=' + release + '\n', expected=release)
            self.assertEqual((code, err), (0, ''))
            self.assertIn('PASS: qca-mcs release matches the build lock\n', out)
            self.assertIn('=== summary: PASS=7 FAIL=0 ===\n', out)

    def test_release_drift_is_not_accepted(self):
        self.reject('qca-mcs release differs from the build lock', expected='3')
        self.reject('qca-mcs release differs from the build lock', release='PKG_RELEASE:=5\n', expected='4')

    def test_missing_duplicate_or_invalid_release(self):
        for content in ('', 'PKG_RELEASE:=3\nPKG_RELEASE:=4\n', 'PKG_RELEASE:=4\nPKG_RELEASE:=4\n',
                        'PKG_RELEASE:=\n', 'PKG_RELEASE:=no\n', 'PKG_RELEASE:=4.0\n',
                        'PKG_RELEASE:=0\n', 'PKG_RELEASE:=2\n', 'PKG_RELEASE:=-4\n'):
            with self.subTest(content=content):
                self.reject('qca-mcs release must be one numeric value at least r3', release=content)

    def test_invalid_expected_identity(self):
        for expected in ('', '0', '-4', 'four', '4\n4'):
            with self.subTest(expected=expected):
                self.reject('qca-mcs release differs from the build lock', expected=expected)

    def test_missing_patch(self):
        # Missing-input denial emits grep diagnostics, unlike valid-source mutations.
        code, out, err = self.run_gate(missing=True)
        self.assertEqual(code, 1)
        self.assertIn('FAIL: qca-mcs quiet leave-event patch exists\n', out)
        self.assertIn('No such file or directory', err)

    def test_origin_still_required(self):
        self.reject('patch records reviewed VIKING origin',
                    edit=lambda s: s.replace('Origin: VIKINGYFY/', 'Origin: wrong/'))

    def test_debug_addition_still_counted(self):
        self.reject('expected four pr_debug additions, got 3',
                    edit=lambda s: s.replace('+\t\tpr_debug(', '+\t\tpr_info(', 1))

    def test_printk_removal_still_counted(self):
        self.reject('expected four printk removals, got 3',
                    edit=lambda s: s.replace('-\t\tprintk(KERN_DEBUG', '-\t\tother(KERN_DEBUG', 1))

    def test_new_ring_buffer_log_still_rejected(self):
        self.reject('patch adds no KERN_DEBUG printk', edit=lambda s: s + '+printk(KERN_DEBUG "bad");\n')


if __name__ == '__main__':
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SCRIPT, PATCH, Path(__file__))}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gate))
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SCRIPT, PATCH, Path(__file__))}
    if before != after:
        raise RuntimeError('test inputs changed')
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 10 else 1)
