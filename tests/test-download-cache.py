#!/usr/bin/env python3
"""Exercise the real downloader with local fixtures and no network access."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/download.pl'
PAYLOAD = b'verified archive fixture\n'


class DownloadCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='download-cache-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / 'cache'
        self.mirror = self.root / 'mirror'
        self.cache.mkdir()
        self.mirror.mkdir()
        self.name = 'test-source.tar.gz'
        self.target = self.cache / self.name
        (self.root / '.config').write_text('')
        (self.mirror / self.name).write_bytes(PAYLOAD)
        mkhash = self.root / 'mkhash.py'
        mkhash.write_text('import hashlib, sys\nprint(hashlib.new(sys.argv[1], sys.stdin.buffer.read()).hexdigest())\n')
        deny = self.root / 'deny-network.py'
        deny.write_text('import sys\nsys.exit("network downloader must not run in this fixture")\n')
        self.env = dict(os.environ, TOPDIR=str(self.root), DOWNLOAD_MIRROR='',
                        DOWNLOAD_CHECK_CERTIFICATE='y',
                        DOWNLOAD_TOOL_CUSTOM=sys.executable + ' ' + str(deny),
                        MKHASH=sys.executable + ' ' + str(mkhash))

    def download(self, digest, env=None):
        return subprocess.run(['perl', str(SCRIPT), str(self.cache), self.name,
                               digest, self.name, self.mirror.as_uri()],
                              env=env or self.env, text=True, capture_output=True,
                              timeout=15)

    def test_mismatch_is_removed_and_next_attempt_uses_local_mirror(self):
        for algorithm in ('sha256', 'md5'):
            with self.subTest(algorithm=algorithm):
                self.target.write_bytes(b'corrupted cached download\n')
                digest = hashlib.new(algorithm, PAYLOAD).hexdigest()
                result = self.download(digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('does not match', result.stderr)
                self.assertFalse(self.target.exists(), result.stderr)
                self.assertFalse(Path(str(self.target) + '.hash').exists())
                result = self.download(digest)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(self.target.read_bytes(), PAYLOAD)

    def test_matching_cache_is_not_replaced(self):
        self.target.write_bytes(PAYLOAD)
        stamp = self.target.stat().st_mtime_ns
        result = self.download(hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), PAYLOAD)
        self.assertEqual(self.target.stat().st_mtime_ns, stamp)

    def test_hash_tool_failure_does_not_delete_cache(self):
        self.target.write_bytes(PAYLOAD)
        result = self.download(hashlib.sha256(PAYLOAD).hexdigest(),
                               dict(self.env, MKHASH='/usr/bin/false'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Failed to generate hash', result.stderr)
        self.assertEqual(self.target.read_bytes(), PAYLOAD)

    def test_explicit_skip_keeps_existing_cache(self):
        self.target.write_bytes(PAYLOAD)
        result = self.download('skip')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), PAYLOAD)


if __name__ == '__main__':
    unittest.main(verbosity=2)
