#!/usr/bin/env python3
"""Host-side suite for the probe-gated AX6 U-Boot environment geometry (S1-01).

The merged-layout AX6 boots a custom U-Boot that *may* use a 256 KiB
(0x40000) environment while the stock Xiaomi geometry is 64 KiB (0x10000).
Shipping the larger geometry unprobed is unsafe: on a device whose U-Boot
environment is still 64 KiB, a wrong /etc/fw_env.config makes every Linux
fw_setenv rewrite a CRC-invalid image and forces U-Boot into the
bad-CRC/default/512-KiB-erase cycle (GAPFILL S1-02).

The only safe contract is therefore:

  * the default geometry is the stock 0x10000;
  * the 0x40000 candidate is selected only when a runtime read of
    /dev/mtdN (through fw_printenv with a temporary candidate config)
    proves a CRC-valid 256 KiB U-Boot environment on this boot;
  * fw_printenv falls back to its compiled-in default environment after a
    bad CRC and still exits 0, so "rc=0 and a non-empty value" is NOT
    proof: the bad-CRC warning must be rejected and the merged-layout
    boot command (bootcmd=bootipq) must be observed;
  * when the probe cannot prove the size, the geometry stays 0x10000 and
    S1-01 is reported OPEN;
  * this uci-defaults arm never calls fw_setenv and never writes MTD.

The suite runs the real case arm extracted from
package/boot/uboot-tools/uboot-envtools/files/qualcommax_ipq807x against
stub find_mtd_index/fw_printenv/fw_setenv/ubootenv_add_* implementations and
covers probe-ok, bad-CRC fallback, empty value, tool failure and the stock
dual-slot layout. Its static checks also prove that the arm contains no
statically selected 0x40000 geometry (negative control included).

An optional --fixture replay parses a raw/gzipped mtd6 APPSBLENV dump and
proves that, for the 2026-11-17 device state, only the 64 KiB view carries a
valid U-Boot environment CRC: the probe MUST therefore keep 0x10000 (OPEN)
instead of accepting the 0x40000 candidate.

Usage:
  python3 tests/test-ax6-uboot-env-geometry.py
  python3 tests/test-ax6-uboot-env-geometry.py --shell /bin/dash
  python3 tests/test-ax6-uboot-env-geometry.py \
      --fixture /Volumes/FX-MD87/Review-AX6/audits/20261117/device-backup/\
20261117T2120/partitions/mtd6_0:appsblenv.gz
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(
    "package/boot/uboot-tools/uboot-envtools/files/qualcommax_ipq807x")
AX6_LABELS = ("redmi,ax6", "redmi,ax6-stock")
XIAOMI_LABELS = ("xiaomi,ax3600", "xiaomi,ax3600-stock",
                 "xiaomi,ax9000", "xiaomi,ax9000-stock")

HARNESS = r"""\
set -u
calls="$1"
layout="$2"
probe="$3"
PROBE_MODE="$probe"
board="redmi,ax6-stock"
# Faithful copy of base-files /lib/functions.sh find_mtd_index against the
# per-layout /proc/mtd fixture written next to this harness.  The AX6
# partition names carry the Qualcomm numeric prefix ("0:appsblenv"), so a
# probe that greps for a bare "appsblenv" must not resolve an index.
find_mtd_index() {
	local part index
	part=$(grep "\"$1\"" mtd.txt | awk -F: '{print $1}')
	index=${part##mtd}
	printf '%s\n' "$index"
}
fw_printenv() {
	printf 'fw_printenv %s\n' "$*" >> "$calls"
	cfg=
	while [ "$#" -gt 0 ]; do
		case "$1" in
			-c) cfg="$2"; shift 2 ;;
			*) shift ;;
		esac
	done
	if [ -n "$cfg" ] && [ -f "$cfg" ]; then
		printf 'probe-config %s\n' "$(cat "$cfg")" >> "$calls"
	fi
	case "$PROBE_MODE" in
		ok) printf 'bootipq\n'; return 0 ;;
		badcrc) printf 'run distro_bootcmd\n'
			printf 'Warning: Bad CRC, using default environment\n' >&2
			return 0 ;;
		empty) printf '\n'; return 0 ;;
		*) return 1 ;;
	esac
}
fw_setenv() { printf 'fw_setenv %s\n' "$*" >> "$calls"; return 0; }
ubootenv_add_mtd() { printf 'add_mtd %s\n' "$*" >> "$calls"; }
ubootenv_add_sys_mtd() { printf 'add_sys_mtd %s\n' "$*" >> "$calls"; }
ubootenv_add_mmc() { printf 'add_mmc %s\n' "$*" >> "$calls"; }
ubootenv_add_uci_config() { printf 'add_uci %s\n' "$*" >> "$calls"; }
ubootenv_mtdinfo() { printf 'mtdinfo\n'; }
__AX6_ARM__
printf 'arm rc=%s\n' "$?" >> "$calls"
"""


class Suite:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []

    def ok(self, label: str) -> None:
        self.passed += 1
        print(f"PASS: {label}")

    def bad(self, label: str, detail: str = "") -> None:
        self.failed += 1
        text = f"FAIL: {label}" + (f" ({detail})" if detail else "")
        print(text)
        self.failures.append(text)


def parse_case_arms(text: str) -> list[dict]:
    """Split the outer `case "$board" in ... esac` into arms."""
    match = re.search(
        r'(?ms)^case\s+"?\$\{?board\}?"?\s+in\s*$\n(.*?)^esac\s*$', text)
    if not match:
        raise ValueError('no top-level case "$board" block found')
    arms = []
    for chunk in re.split(r'(?m)^[ \t]*;;[ \t]*$', match.group(1)):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        head = None
        for index, line in enumerate(lines):
            if line.strip().endswith(")"):
                head = index
                break
        if head is None:
            continue
        label_text = " ".join(lines[:head + 1]).replace(")", " ")
        labels = [item.replace("\\", "").strip()
                  for item in label_text.split("|") if item.strip()]
        arms.append({"labels": labels, "body": "\n".join(lines[head + 1:])})
    if not arms:
        raise ValueError("case block has no parseable arms")
    return arms


def ax6_arm(arms: list[dict]) -> dict:
    for arm in arms:
        if any(label in AX6_LABELS for label in arm["labels"]):
            return arm
    raise ValueError("no redmi,ax6 arm found")


def arm_labels_contain(arm: dict, wanted: tuple) -> bool:
    return all(label in arm["labels"] for label in wanted)


def static_findings(text: str) -> list[str]:
    """Static contract violations in the AX6 uboot-envtools arm."""
    findings = []
    try:
        arms = parse_case_arms(text)
        arm = ax6_arm(arms)
    except ValueError as exc:
        return [f"case parsing failed: {exc}"]
    body = arm["body"]
    if not arm_labels_contain(arm, AX6_LABELS):
        findings.append("AX6 arm does not carry both redmi,ax6 and redmi,ax6-stock")
    for other in arms:
        if other is arm:
            continue
        if any(label in AX6_LABELS for label in other["labels"]):
            findings.append("AX6 labels remain in a shared Xiaomi arm")
    if re.search(r'ubootenv_add_mtd\s+"0:appsblenv"\s+"0x0"\s+"0x40000"', body):
        findings.append("AX6 arm statically selects 0x40000")
    if re.search(r'ubootenv_add_mtd\s+"0:appsblenv"\s+"0x0"\s+"0x10000"', body):
        findings.append("AX6 arm hardcodes the default instead of "
                        "forwarding the probed envsize")
    if not re.search(r'ubootenv_add_mtd\s+"0:appsblenv"\s+"0x0"\s+"\$ax6_envsize"',
                     body):
        findings.append("AX6 arm does not pass the probed envsize to "
                        "ubootenv_add_mtd")
    if "fw_printenv" not in body:
        findings.append("AX6 arm has no runtime fw_printenv probe")
    if not re.search(r'find_mtd_index\s+"?0:appsblenv"?', body):
        findings.append("runtime probe does not resolve the 0:appsblenv "
                        "partition")
    if not re.search(r"printf\s+'/dev/mtd%s 0x0 0x40000 0x20000", body):
        findings.append("runtime probe does not read the 0x40000 candidate "
                        "geometry")
    if "Bad CRC" not in body:
        findings.append("runtime probe does not reject the fw_printenv "
                        "bad-CRC fallback")
    if "bootipq" not in body:
        findings.append("runtime probe does not require the merged-layout "
                        "boot command")
    if "ax6_envsize=0x10000" not in body:
        findings.append("default envsize is not 0x10000")
    else:
        default_at = body.index("ax6_envsize=0x10000")
        if "fw_printenv" in body and body.index("fw_printenv") < default_at:
            findings.append("runtime probe runs before the 0x10000 default")
        if "ax6_envsize=0x40000" in body and \
                body.index("ax6_envsize=0x40000") < body.index("fw_printenv"):
            findings.append("0x40000 geometry is assigned before the probe")
    if "OPEN" not in body:
        findings.append("probe failure does not report S1-01 OPEN")
    code = "\n".join(line for line in body.splitlines()
                     if not line.strip().startswith("#"))
    for forbidden in ("fw_setenv", "mtd write", "flash_erase", "nand write",
                      "ubiupdatevol", "ubi write", "/etc/fw_env.config"):
        if forbidden in code:
            findings.append(f"AX6 arm performs a forbidden write: {forbidden}")
    return findings


MTD_MERGED = (
    'mtd6: 00080000 00020000 "0:appsblenv"\n'
    'mtd12: 06640000 00020000 "rootfs"\n'
)
MTD_DUAL = MTD_MERGED + 'mtd13: 06640000 00020000 "rootfs_1"\n'


def run_arm(shell: str, body: str, layout: str, probe: str) -> dict:
    work = Path(tempfile.mkdtemp(prefix="ax6-env-geometry-"))
    try:
        calls = work / "calls.txt"
        (work / "mtd.txt").write_text(
            MTD_DUAL if layout == "dual" else MTD_MERGED)
        (work / "harness.sh").write_text(HARNESS.replace("__AX6_ARM__", body))
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LC_ALL": "C",
            "HOME": str(work),
        }
        proc = subprocess.run(
            [shell, "harness.sh", str(calls), layout, probe],
            cwd=work, capture_output=True, text=True, timeout=60, env=env)
        call_lines = []
        if calls.is_file():
            call_lines = [line for line in calls.read_text().splitlines()
                          if line]
        return {
            "rc": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "calls": call_lines,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def add_mtd_calls(result: dict) -> list[str]:
    return [c for c in result["calls"]
            if c.startswith("add_mtd ") and "appsblenv" in c]


def call_entries(result: dict, prefix: str) -> list[str]:
    return [c for c in result["calls"] if c.startswith(prefix)]


def check(suite: Suite, label: str, condition: bool, detail: str = "") -> None:
    if condition:
        suite.ok(label)
    else:
        suite.bad(label, detail)


def replay_fixture(path: Path) -> dict:
    """Analyse an mtd6 APPSBLENV dump for the candidate env geometry CRCs."""
    raw = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
    if len(raw) < 0x10000:
        raise ValueError(f"env dump too small for a 64 KiB environment: {len(raw)}")
    stored = int.from_bytes(raw[0:4], "little")

    def crc_valid(size: int) -> bool:
        if len(raw) < size:
            return False
        return zlib.crc32(raw[4:size]) & 0xFFFFFFFF == stored

    result = {
        "path": str(path),
        "bytes": len(raw),
        "stored_env_crc": f"0x{stored:08x}",
        "crc_valid_0x10000": crc_valid(0x10000),
        "crc_valid_0x20000": crc_valid(0x20000),
        "crc_valid_0x40000": crc_valid(0x40000),
    }
    if len(raw) >= 0x80000:
        result["region_0x10000_0x3ffff_is_zero"] = (
            raw[0x10000:0x40000] == b"\x00" * 0x30000)
        result["region_0x40000_0x7ffff_is_ff"] = (
            raw[0x40000:0x80000] == b"\xff" * 0x40000)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / DEFAULT_SOURCE,
                        help="qualcommax_ipq807x source file to test")
    parser.add_argument("--shell", default=os.environ.get("AX6_TEST_SHELL",
                                                          "/bin/sh"),
                        help="POSIX shell used for the arm harness")
    parser.add_argument("--json-output", type=Path,
                        help="optional path for a machine-readable summary")
    parser.add_argument("--fixture", type=Path,
                        help="optional mtd6 APPSBLENV raw/.gz dump replay "
                             "(2026-11-17 device state: proves only the "
                             "64 KiB view is CRC-valid, so the probe must "
                             "keep 0x10000/OPEN)")
    args = parser.parse_args()

    shell = args.shell
    if shutil.which(shell) is None:
        raise SystemExit(f"requested shell is unavailable: {shell}")
    shell = shutil.which(shell)
    text = args.source.read_text()
    suite = Suite()

    # ---------------------------------------------------------------- static
    try:
        arms = parse_case_arms(text)
        arm = ax6_arm(arms)
        suite.ok("case arm parsing finds the AX6 arm")
    except ValueError as exc:
        suite.bad("case arm parsing", str(exc))
        return 1

    findings = static_findings(text)
    if findings:
        for finding in findings:
            suite.bad("static: " + finding)
    else:
        suite.ok("static: probe-gated contract has no static 0x40000 selection")

    # A negative control proves the static checker is not vacuous: the
    # previously withdrawn layout-gated static change must be rejected.
    negative = text.replace(arm["body"], """
	ubootenv_add_mtd "0:appsblenv" "0x0" "0x40000" "0x20000"
	ubootenv_add_sys_mtd "bdata" "0x0" "0x10000" "0x20000"
""")
    negative_findings = static_findings(negative)
    check(suite, "static negative control rejects the unprobed 0x40000 arm",
          any("statically selects 0x40000" in finding
              for finding in negative_findings),
          "; ".join(negative_findings))

    # The stock Xiaomi arms must keep the 64 KiB geometry and stay separate.
    for arm_row in arms:
        if any(label in XIAOMI_LABELS for label in arm_row["labels"]):
            check(suite, "xiaomi stock arm keeps 0x10000",
                  re.search(r'ubootenv_add_mtd\s+"0:appsblenv"\s+"0x0"\s+"0x10000"',
                            arm_row["body"]) is not None)

    # A shell syntax check keeps the committed script valid.
    proc = subprocess.run([shell, "-n", str(args.source)],
                          capture_output=True, text=True)
    check(suite, "shell -n accepts the source script", proc.returncode == 0,
          proc.stderr.strip())

    # ------------------------------------------------------------ behaviour
    body = arm["body"]

    merged_ok = run_arm(shell, body, "merged", "ok")
    mtd = add_mtd_calls(merged_ok)
    check(suite, "merged+probe-ok selects 0x40000/0x20000",
          len(mtd) == 1 and "0x40000" in mtd[0] and "0x20000" in mtd[0],
          str(mtd))
    check(suite, "merged+probe-ok announces probe-verified",
          "probe-verified" in merged_ok["stdout"], merged_ok["stdout"])
    check(suite, "merged+probe-ok never calls fw_setenv",
          not call_entries(merged_ok, "fw_setenv"), str(merged_ok["calls"]))
    check(suite, "merged+probe-ok performs exactly one probe read",
          len(call_entries(merged_ok, "fw_printenv")) == 1,
          str(merged_ok["calls"]))
    probe_configs = [c.replace("probe-config ", "", 1)
                     for c in merged_ok["calls"]
                     if c.startswith("probe-config ")]
    check(suite, "merged+probe-ok reads the 0x40000/0x20000 candidate",
          probe_configs == ["/dev/mtd6 0x0 0x40000 0x20000"],
          str(probe_configs))
    check(suite, "merged+probe-ok returns rc=0", merged_ok["rc"] == 0,
          merged_ok["stderr"])
    rerun = run_arm(shell, body, "merged", "ok")
    check(suite, "repeated arm execution is idempotent",
          add_mtd_calls(rerun) == mtd, f"{add_mtd_calls(rerun)} != {mtd}")

    merged_badcrc = run_arm(shell, body, "merged", "badcrc")
    mtd = add_mtd_calls(merged_badcrc)
    check(suite, "merged+bad-CRC keeps the safe 0x10000 default",
          len(mtd) == 1 and "0x10000" in mtd[0] and "0x40000" not in mtd[0],
          str(mtd))
    check(suite, "merged+bad-CRC reports S1-01 OPEN",
          "OPEN" in merged_badcrc["stdout"], merged_badcrc["stdout"])
    check(suite, "merged+bad-CRC never calls fw_setenv",
          not call_entries(merged_badcrc, "fw_setenv"),
          str(merged_badcrc["calls"]))
    check(suite, "merged+bad-CRC cannot leak 0x40000 into add_mtd",
          all("0x40000" not in call for call in mtd), str(mtd))

    merged_empty = run_arm(shell, body, "merged", "empty")
    mtd = add_mtd_calls(merged_empty)
    check(suite, "merged+empty probe value keeps 0x10000",
          len(mtd) == 1 and "0x10000" in mtd[0], str(mtd))
    check(suite, "merged+empty probe value reports OPEN",
          "OPEN" in merged_empty["stdout"], merged_empty["stdout"])

    merged_error = run_arm(shell, body, "merged", "error")
    mtd = add_mtd_calls(merged_error)
    check(suite, "merged+probe failure keeps 0x10000",
          len(mtd) == 1 and "0x10000" in mtd[0], str(mtd))
    check(suite, "merged+probe failure reports OPEN",
          "OPEN" in merged_error["stdout"], merged_error["stdout"])
    check(suite, "merged+probe failure never calls fw_setenv",
          not call_entries(merged_error, "fw_setenv"),
          str(merged_error["calls"]))

    dual = run_arm(shell, body, "dual", "ok")
    mtd = add_mtd_calls(dual)
    check(suite, "dual-slot keeps the stock 0x10000 geometry",
          len(mtd) == 1 and "0x10000" in mtd[0] and "0x40000" not in mtd[0],
          str(mtd))
    check(suite, "dual-slot does not attempt the merged-layout probe",
          not call_entries(dual, "fw_printenv"), str(dual["calls"]))
    check(suite, "dual-slot never calls fw_setenv",
          not call_entries(dual, "fw_setenv"), str(dual["calls"]))

    # ------------------------------------------------- optional dump replay
    fixture = None
    if args.fixture:
        try:
            fixture = replay_fixture(args.fixture)
        except (OSError, ValueError) as exc:
            suite.bad("fixture replay", f"{args.fixture}: {exc}")
        else:
            print("fixture: " + json.dumps(fixture, sort_keys=True))
            check(suite, "fixture: 64 KiB view carries the valid env CRC",
                  fixture["crc_valid_0x10000"], json.dumps(fixture))
            check(suite, "fixture: 0x20000 view is not a valid environment",
                  not fixture["crc_valid_0x20000"], json.dumps(fixture))
            check(suite, "fixture: 0x40000 candidate is NOT proven "
                  "(probe keeps 0x10000 / OPEN)",
                  not fixture["crc_valid_0x40000"], json.dumps(fixture))
            if "region_0x10000_0x3ffff_is_zero" in fixture:
                check(suite, "fixture: 0x10000-0x3FFFF is erasure-zero tail",
                      fixture["region_0x10000_0x3ffff_is_zero"],
                      json.dumps(fixture))
                check(suite, "fixture: 0x40000-0x7FFFF is erased 0xFF",
                      fixture["region_0x40000_0x7ffff_is_ff"],
                      json.dumps(fixture))

    summary = {
        "suite": "test-ax6-uboot-env-geometry",
        "source": str(args.source),
        "shell": shell,
        "passed": suite.passed,
        "failed": suite.failed,
        "failures": suite.failures,
        "contract": "probe-gated S1-01 env geometry: default 0x10000, "
                    "0x40000 only after runtime proof, OPEN otherwise",
        "fixture": fixture,
    }
    print(f"test-ax6-uboot-env-geometry: {suite.passed} passed, "
          f"{suite.failed} failed")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2) + "\n")
    return 1 if suite.failed else 0


if __name__ == "__main__":
    sys.exit(main())
