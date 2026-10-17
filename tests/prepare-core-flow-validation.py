#!/usr/bin/env python3
"""Replay package patches in a NEW offline tree; does not build firmware."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--ssdk-repo', type=Path, required=True)
parser.add_argument('--ecm-repo', type=Path, required=True)
parser.add_argument('--backports-archive', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
records = []


def run(label, command, cwd=None, data=None):
    result = subprocess.run(command, cwd=cwd, input=data, capture_output=True, timeout=180)
    (args.output / (label + '.stdout')).write_bytes(result.stdout)
    (args.output / (label + '.stderr')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(label + ': ' + result.stderr.decode(errors='replace'))


for name, repo in [('qca-ssdk', args.ssdk_repo), ('qca-nss-ecm', args.ecm_repo)]:
    package = ROOT / 'package/qca-nss' / name
    recipe = (package / 'Makefile').read_text()
    pin = re.search(r'^PKG_SOURCE_VERSION:=(\S+)$', recipe, re.M).group(1)
    resolved = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', pin + '^{commit}'], text=True).strip()
    if not resolved.startswith(pin):
        raise RuntimeError('pin mismatch: ' + name)
    archive = subprocess.check_output(['git', '-C', str(repo), 'archive', '--format=tar', resolved])
    destination = args.output / name
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar.getmembers():
            if not (entry.isfile() or entry.isdir()) or entry.name.startswith('/') or '..' in Path(entry.name).parts:
                raise RuntimeError('unsafe archive entry')
        tar.extractall(destination)
    patches = []
    for patch in sorted((package / 'patches').glob('*.patch')):
        run(name + '-' + patch.stem, ['patch', '--batch', '--forward', '--fuzz=0', '-p1'], destination, patch.read_bytes())
        patches.append({'file': patch.name, 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()})
    records.append({'package': name, 'pin': resolved, 'patches': patches})

recipe = (ROOT / 'package/kernel/mac80211/Makefile').read_text()
expected = re.search(r'^PKG_HASH:=(\S+)$', recipe, re.M).group(1)
if hashlib.sha256(args.backports_archive.read_bytes()).hexdigest() != expected:
    raise RuntimeError('backports archive hash mismatch')
destination = args.output / 'mac80211'
destination.mkdir()
run('backports-extract', ['tar', '-xf', str(args.backports_archive), '-C', str(destination), '--strip-components=1'])
patches = []
for directory in ('build', 'subsys', 'ath', 'ath5k', 'ath9k', 'ath10k', 'ath11k', 'ath12k', 'rt2x00',
                  'mt7601u', 'mwl', 'brcm', 'rtl', 'nss/subsys', 'nss/ath10k', 'nss/ath11k'):
    for patch in sorted((ROOT / 'package/kernel/mac80211/patches' / directory).glob('*.patch')):
        # Match Build/Patch ordering; no fuzz is accepted for this candidate.
        run('mac-' + directory.replace('/', '-') + '-' + patch.stem,
            ['patch', '--batch', '--forward', '--fuzz=0', '-p1'], destination, patch.read_bytes())
        patches.append({'file': directory + '/' + patch.name, 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()})
records.append({'package': 'mac80211', 'archive_sha256': expected, 'patches': patches})
(args.output / 'PREPARED.json').write_text(json.dumps(records, indent=2) + '\n')
print('PASS: exact pins and complete package patch order, zero fuzz; no target compilation')
