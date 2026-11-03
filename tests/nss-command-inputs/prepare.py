#!/usr/bin/env python3
"""Offline Git-archive/full-patch text replay for command-input fixtures only."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))
from edma_patch_context import inspect_patch, verify_applied

PINS = {"driver": "6aa14c78e097b29c493ff2fef87e4d35906b2b5a",
        "clients": "51be82d43ef85079f78aa163d014223b05baa6a2"}
NEW = {"driver": "027-checked-command-and-sequence-inputs.patch",
       "clients": "026-parse-sysctl-kernel-buffers.patch"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("SYMLINK: " + str(p))
        if p.is_file():
            result[p.relative_to(root).as_posix()] = digest(p.read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--driver-repo", type=Path, default=Path("/Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-nss-drv-source"))
    parser.add_argument("--clients-repo", type=Path, default=Path("/Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-nss-clients-source"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "INCOMPLETE", "qualification": "SOURCE_TEXT_ONLY_NO_TARGET_BUILD", "packages": {}}
    inputs = {str(Path(__file__).resolve()): digest(Path(__file__).read_bytes())}
    helper = REPO / "tests/edma_patch_context.py"
    inputs[str(helper)] = digest(helper.read_bytes())
    try:
        for label, package, cache in (("driver", "qca-nss-drv", args.driver_repo),
                                      ("clients", "qca-nss-clients", args.clients_repo)):
            pkg = REPO / "package/qca-nss" / package
            recipe = pkg / "Makefile"
            inputs[str(recipe)] = digest(recipe.read_bytes())
            pin = re.search(r"^PKG_SOURCE_VERSION:=(\S+)$", recipe.read_text(), re.M).group(1)
            resolved = subprocess.check_output(["git", "-C", str(cache), "rev-parse", pin + "^{commit}"], text=True).strip()
            if resolved != PINS[label]:
                raise ValueError("VENDOR_PIN: " + label)
            archive = subprocess.check_output(["git", "-C", str(cache), "archive", "--format=tar", resolved])
            tree = args.output / label
            tree.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                for member in tar.getmembers():
                    relative = Path(member.name)
                    if relative.is_absolute() or ".." in relative.parts or not (member.isfile() or member.isdir()):
                        raise ValueError("ARCHIVE_MEMBER: " + member.name)
                    dest = tree / relative
                    if member.isdir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(tar.extractfile(member).read())
            all_patches = sorted((pkg / "patches").glob("*.patch"))
            patches = [p for p in all_patches if not (args.baseline and p.name == NEW[label])]
            entry = {"pin": resolved, "archive_sha256": digest(archive), "patches": []}
            report["packages"][label] = entry
            for index, patch in enumerate(patches):
                raw = patch.read_bytes()
                inputs[str(patch)] = digest(raw)
                inspected = raw
                historical_offset = None
                if label == "driver" and patch.name == "022-lower-sysctl-read-log-level.patch":
                    if digest(raw) != "3455b7338980f2464407859e7510fd5ae456ccaae3970559e4cbdae751bd1b7a":
                        raise ValueError("HISTORICAL_022_IDENTITY")
                    # Old022 predates the +18-line frequency fix. Keep its bytes immutable;
                    # verify the full context/output at the actual coordinates explicitly.
                    inspected = re.sub(rb"@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@",
                        lambda m: b"@@ -" + str(int(m[1])+18).encode() + (m[2] or b"") +
                        b" +" + str(int(m[3])+18).encode() + (m[4] or b"") + b" @@", raw)
                    historical_offset = 18
                context_exception = None
                try:
                    expected, context = inspect_patch(tree, inspected)
                except ValueError as e:
                    if patch.name == NEW[label]:
                        raise
                    # The shared checker rejects pre-existing EOF-without-newline and
                    # some old coordinates. Retain that gap; never waive new hunks.
                    expected, context = None, None
                    context_exception = str(e)
                command = [shutil.which("gpatch") or "patch", "--batch", "--forward", "--fuzz=0", "-p1"]
                p = subprocess.run(command, cwd=tree, input=raw, capture_output=True, timeout=60)
                stem = label + "-" + str(index + 1).zfill(2)
                (args.output / (stem + ".stdout")).write_bytes(p.stdout)
                (args.output / (stem + ".stderr")).write_bytes(p.stderr)
                if p.returncode or p.stderr or re.search(rb"offset|fuzz|FAILED|reject|malformed", p.stdout, re.I):
                    raise ValueError("EXACT_PATCH: " + patch.name)
                if expected is not None:
                    verify_applied(tree, expected)
                entry["patches"].append({"name": patch.name, "sha256": digest(raw), "context": context,
                                          "historical_coordinate_offset": historical_offset,
                                          "old_declared_context_exception": context_exception,
                                          "command": command, "returncode": p.returncode})
            entry["files"] = inventory(tree)
            entry["patch_count"] = len(patches)
        if any(digest(Path(p).read_bytes()) != h for p, h in inputs.items()):
            raise ValueError("INPUT_DRIFT")
        report.update(status="PASS_TEXT_REPLAY_NEW_PATCHES_EXACT", inputs=inputs)
    except Exception as e:
        report["error"] = str(e)
    (args.output / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "error") if k in report}))
    return 0 if report["status"] == "PASS_TEXT_REPLAY_NEW_PATCHES_EXACT" else 1


if __name__ == "__main__":
    sys.exit(main())
