#!/usr/bin/env python3
"""Execute actual NSS coredump control and pinned Linux parser bodies on the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
KERNEL_SHA256 = "ac9501697708f8921734125d507661487462a6dae3205bf3c2ab92d7df94dc53"
KERNEL_URL = "https://raw.githubusercontent.com/gregkh/linux/v6.18.38/kernel/sysctl.c"
FUNCTIONS = ("proc_first_pos_non_zero_ignore", "proc_skip_spaces", "proc_get_long",
             "proc_put_long", "proc_put_char", "do_proc_dointvec_conv",
             "__do_proc_dointvec", "do_proc_dointvec", "proc_dointvec")
BASELINE_FAILURES = [
    "empty-live:sends", "empty-live:stores", "empty-live:readiness",
    "empty-cold:errno", "empty-cold:readiness",
    "empty-closed:errno", "empty-closed:stores", "empty-closed:readiness",
    "empty-debug-off:stores", "empty-interleaved:policy", "empty-interleaved:stores",
]
INVERTED_FAILURES = BASELINE_FAILURES + [
    "trigger:policy", "trigger:sends", "trigger:stores", "trigger:readiness",
    "trigger-cold:errno", "trigger-cold:readiness",
    "trigger-closed:errno", "trigger-closed:policy", "trigger-closed:stores", "trigger-closed:readiness",
    "policy:policy", "policy:stores", "debug-off:policy", "debug-off:stores",
    "offset-strict:stores", "offset-legacy:policy", "offset-legacy:stores",
]


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def mask_c(text):
    tokens = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(tokens, lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def extract(text, name):
    masked = mask_c(text)
    pattern = rf"^(?:static\s+)?(?:int|void|bool)\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{"
    matches = list(re.finditer(pattern, masked, re.M))
    require(len(matches) == 1, f"expected one definition of {name}, got {len(matches)}")
    match = matches[0]
    depth, end = 1, match.end()
    while depth and end < len(masked):
        depth += (masked[end] == "{") - (masked[end] == "}")
        end += 1
    require(depth == 0, f"unclosed function: {name}")
    return text[match.start():end], text.count("\n", 0, match.start()) + 1


def replace_once(text, old, new):
    require(text.count(old) == 1, f"expected one mutation anchor: {old!r}")
    return text.replace(old, new, 1)


def expected_output(failures):
    return "".join(f"FAIL {item}\n" for item in failures) + f"SUMMARY cases=19 failures={len(failures)}\n"


def accepted(result, failures):
    return (result.returncode == (1 if failures else 0)
            and result.stdout == expected_output(failures) and result.stderr == "")


def execute(args):
    inputs = [("baseline", args.baseline.resolve() / "nss_init.c"),
              ("candidate", args.candidate.resolve() / "nss_init.c"),
              ("kernel", args.kernel.resolve() / "kernel/sysctl.c")]
    require(args.baseline.resolve() != args.candidate.resolve(), "baseline and candidate must differ")
    out = args.output.resolve()
    for root in (args.baseline.resolve(), args.candidate.resolve(), args.kernel.resolve(), HERE):
        require(out != root and root not in out.parents and out not in root.parents,
                f"output must not overlap input: {root}")
    data = {key: file.read_bytes() for key, file in inputs}
    require(sha256(data["kernel"]) == KERNEL_SHA256, "review parser contract for this kernel/sysctl.c hash")
    require(b"proc_dointvec_single" not in data["kernel"], "unexpected single-value parser implementation")
    baseline, bl = extract(data["baseline"].decode(), "nss_coredump_handler")
    candidate, cl = extract(data["candidate"].decode(), "nss_coredump_handler")
    expected = replace_once(baseline, "if (ret || !write)", "if (ret || !write || !*lenp)")
    require(candidate == expected, "candidate handler must contain only the reviewed empty-write guard delta")
    # Exclude the CONFIG_PROC_SYSCTL-disabled ENOSYS definitions, not runtime code.
    kernel_text = data["kernel"].decode().split("#else /* CONFIG_PROC_SYSCTL */")[0]
    parser, functions = [], []
    for name in FUNCTIONS:
        body, line = extract(kernel_text, name)
        parser.append(body)
        functions.append({"name": name, "line": line, "sha256": sha256(body.encode())})
    fixture = (HERE / "fixture.c").read_text()
    require(fixture.count("/* ACTUAL_PARSER_SOURCE */") == 1, "parser fixture marker")
    require(fixture.count("/* ACTUAL_HANDLER_SOURCE */") == 1, "handler fixture marker")
    cc = shutil.which(args.cc)
    require(cc, f"compiler not found: {args.cc}")
    out.mkdir(parents=True, exist_ok=False)
    (out / "tmp").mkdir()
    env = dict(os.environ, LC_ALL="C", TMPDIR=str(out / "tmp"),
               ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
               UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    flags = ["-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", "-Wno-sign-compare", "-Wno-deprecated-declarations",
             "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
    report = {"status": "RUNNING", "scope": "Host control-only; no FW, provider, DMA or unload acceptance",
              "kernel_url": KERNEL_URL, "functions": functions, "executions": [],
              "handler_lines": {"baseline": bl, "candidate": cl},
              "inputs": [{"role": key, "path": str(file), "sha256": sha256(data[key])} for key, file in inputs],
              "fixture_sha256": sha256(fixture.encode())}
    variants = [
        ("candidate", candidate, []),
        ("baseline", baseline, BASELINE_FAILURES),
        ("inverted-empty-guard", replace_once(candidate, "|| !*lenp", "|| *lenp"), INVERTED_FAILURES),
        ("suppress-valid-trigger", replace_once(candidate, "if (nss_ctl_debug && coredump == 1) {", "if (false) {"),
         ["trigger:sends", "trigger-closed:errno"]),
    ]
    try:
        version = subprocess.run([cc, "--version"], capture_output=True, text=True, timeout=30, env=env)
        require(version.returncode == 0, "cannot identify compiler")
        report["compiler"] = version.stdout
        for name, body, failures in variants:
            unit, binary = out / f"{name}.c", out / name
            unit.write_text(fixture.replace("/* ACTUAL_PARSER_SOURCE */", "\n\n".join(parser))
                           .replace("/* ACTUAL_HANDLER_SOURCE */", body))
            command = [cc, *flags, str(unit), "-o", str(binary)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)
            row = {"name": name, "command": command, "source_sha256": sha256(unit.read_bytes()),
                   "compile": {"status": compile_result.returncode, "stdout": compile_result.stdout, "stderr": compile_result.stderr},
                   "expected_failures": failures}
            report["executions"].append(row)
            require(compile_result.returncode == 0, f"{name} failed compilation: {compile_result.stderr}")
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30, env=env)
            row["run"] = {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            require(accepted(result, failures), f"{name} unexpected runtime evidence: {row['run']}")
            print(f"{name}: {19} cases; {len(failures)} exact expected runtime failures")
        for key, file in inputs:
            require(file.read_bytes() == data[key], f"input changed during execution: {file}")
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        (out / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="prepared 001..029 driver directory")
    parser.add_argument("--candidate", type=Path, required=True, help="prepared driver including the proposed guard")
    parser.add_argument("--kernel", type=Path, required=True, help="Linux v6.18.38 source directory")
    parser.add_argument("--cc", default="clang", help="host compiler executable; requires ASan and UBSan")
    parser.add_argument("--output", type=Path, required=True, help="new, nonoverlapping output directory")
    execute(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
