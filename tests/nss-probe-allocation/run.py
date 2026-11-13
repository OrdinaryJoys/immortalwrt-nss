#!/usr/bin/env python3
"""Compile actual prepared NSS HAL functions against a bounded host owner model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
HAL = Path("nss_hal/nss_hal.c")
FUNCTIONS = ("nss_hal_firmware_load", "nss_hal_clean_up_irq",
             "nss_hal_register_irq", "__nss_hal_probe", "nss_hal_probe")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def mask_c(text):
    """Keep offsets/newlines; ignore braces and signatures in comments/literals."""
    tokens = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(tokens, lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def extract(text, name):
    masked = mask_c(text)
    pattern = rf"^(?:static\s+)?(?:int|void)\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{"
    matches = list(re.finditer(pattern, masked, re.M))
    require(len(matches) == 1, f"expected one definition of {name}, got {len(matches)}")
    match = matches[0]
    depth, end = 1, match.end()
    while depth and end < len(masked):
        depth += (masked[end] == "{") - (masked[end] == "}")
        end += 1
    require(depth == 0, f"unclosed function {name}")
    return text[match.start():end], text.count("\n", 0, match.start()) + 1


def bounds(header):
    # Match the IPQ807x branch, not the different limits for other backends.
    branch = re.search(r"^#if defined\(NSS_HAL_IPQ807x_SUPPORT\)[^\n]*\n(.*?)^#elif",
                       header, re.M | re.S)
    require(branch is not None, "missing IPQ807x IRQ bounds branch")
    result = {}
    for name, text, expected in (("NSS_MAX_IRQ_PER_CORE", branch[1], 10),
                                 ("NSS_MAX_CLIENTS", header, 12),
                                 ("NSS_N2H_DESC_RING_NUM", header, 15)):
        values = re.findall(rf"^#define\s+{name}\s+(\d+)\b", text, re.M)
        require(values == [str(expected)], f"review fixture bounds for {name}: {values}")
        result[name] = expected
    return result


def file_inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"symlink needs explicit review: {path}")
        if path.is_file():
            data = path.read_bytes()
            result[str(path.relative_to(root))] = {"bytes": len(data), "sha256": sha256(data)}
    return result


def inventory(root):
    result = file_inventory(root)
    require(str(HAL) in result and "nss_core.h" in result, f"not a prepared driver source directory: {root}")
    return result


def fingerprints(paths):
    result = {}
    for path in paths:
        require(path.is_file() and not path.is_symlink(), f"missing or substituted artifact: {path}")
        data = path.read_bytes()
        result[str(path)] = {"bytes": len(data), "sha256": sha256(data)}
    return result


def unchanged(before, after, label):
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    require(not changed, f"{label} changed during the run: {changed}")


def replace_once(text, old, new):
    require(text.count(old) == 1, f"mutation anchor must occur exactly once: {old!r}")
    return text.replace(old, new, 1)


def mutations(functions):
    """Every mutant has one selected scenario and one exact expected assertion."""
    inner = functions["__nss_hal_probe"]
    specs = [
        ("oom-zero-errno", "dummy-oom", "return-errno", (0, 1),
         "if (!napi_ndev)\n\t\treturn -ENOMEM;", "if (!napi_ndev)\n\t\treturn 0;"),
        ("provider-before-alloc", "dummy-oom-cold", "oom-no-provider", (0, 1),
         "\tnapi_ndev = alloc_netdev_dummy(0);",
         "\tnss_top->hal_ops->common_reset(nss_dev);\n\tnapi_ndev = alloc_netdev_dummy(0);"),
        ("omit-local-free", "firmware-error", "local-owner-released", (0, 1),
         "\t\tfree_netdev(napi_ndev);", "\t\t(void)napi_ndev;"),
        ("retain-local-alias", "irq9-fail", "dummy-live-on-free", (0, 1),
         "\tnapi_ndev = NULL;", "\t(void)napi_ndev;"),
        ("publish-before-firmware", "firmware-error", "foreign-owner-preserved", (0, 1),
         "\terr = nss_top->hal_ops->firmware_load(nss_ctx, nss_dev, npd);",
         "\tnss_ctx->napi_ndev = napi_ndev;\n\terr = nss_top->hal_ops->firmware_load(nss_ctx, nss_dev, npd);"),
        ("free-foreign-context", "firmware-error", "free-only-owned-dummy", (0, 1),
         "\t\tfree_netdev(napi_ndev);", "\t\tfree_netdev(nss_ctx->napi_ndev);"),
        ("common-exit-leak", "common-fail", "local-owner-released", (0, 1),
         "\t\t\terr = -EFAULT;\n\t\t\tgoto err_free_napi;",
         "\t\t\terr = -EFAULT;\n\t\t\tnapi_ndev = NULL;\n\t\t\tgoto err_free_napi;"),
        ("node-exit-leak", "no-node", "local-owner-released", (1,),
         "\t\terr = -ENODEV;\n\t\tgoto err_free_napi;",
         "\t\terr = -ENODEV;\n\t\tnapi_ndev = NULL;\n\t\tgoto err_free_napi;"),
        ("pdata-exit-leak", "pdata-fail", "local-owner-released", (1,),
         "\tif (!npd) {\n\t\terr = -EFAULT;\n\t\tgoto err_free_napi;",
         "\tif (!npd) {\n\t\terr = -EFAULT;\n\t\tnapi_ndev = NULL;\n\t\tgoto err_free_napi;"),
        ("omit-irq-owner-free", "irq9-fail", "irq-owner-released", (0, 1),
         "\tfree_netdev(nss_ctx->napi_ndev);", "\t(void)nss_ctx->napi_ndev;"),
    ]
    for name, case, assertion, modes, old, new in specs:
        changed = dict(functions)
        changed["__nss_hal_probe"] = replace_once(inner, old, new)
        yield name, case, assertion, modes, changed


def expected_rejection(result, assertion, case, core, dt):
    expected = f"NSS_ASSERT {assertion} case={case} core={core} dt={dt}\n"
    return result.returncode == 86 and result.stderr == expected and result.stdout == ""


def observations(stdout):
    result = {}
    for line in stdout.splitlines():
        row = json.loads(line)
        key = (row["dt"], row["core"], row["case"], row["phase"])
        require(row["dt"] in (0, 1) and row["core"] in (0, 1), "invalid observation configuration")
        require(row["phase"] in ("probe", "host-failure-boundary"), "invalid observation phase")
        require(key not in result, f"duplicate observation: {key}")
        result[key] = row
    require(result, "no observations")
    for dt, core, case, _ in result:
        require(all((dt, core, case, phase) in result for phase in ("probe", "host-failure-boundary")),
                f"missing observation phase: {(dt, core, case)}")
    return result


def normalized(row):
    # The only allowed behavioral differences outside OOM are the moved alloc
    # and release of an unpublished dummy on prefix failures.
    result = {k: v for k, v in row.items() if k not in ("allocs", "local_frees", "checks")}
    result["trace"] = [e for e in row["trace"].split(",") if e and e not in ("alloc", "free-local")]
    return result


def compare(baseline, candidate):
    require(baseline.keys() == candidate.keys(), "baseline/candidate scenario sets differ")
    compared = []
    for key, left in baseline.items():
        if left["oom"]:
            continue
        right = candidate[key]
        require(normalized(left) == normalized(right), f"non-OOM behavior changed: {key}")
        compared.append(list(key))
    require(compared, "no non-OOM differential checks")
    return compared


class Runner:
    def __init__(self, args):
        self.args = args
        self.out = args.output.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / "tmp").mkdir()
        self.env = dict(os.environ, LC_ALL="C", TMPDIR=str(self.out / "tmp"),
                        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                        UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        self.commands = []
        self.results = {"status": "RUNNING", "executions": [], "comparisons": [],
                        "scope": "Host substitutes; real FW/DMA/providers and target execution unverified."}
        self.assets = file_inventory(HERE)
        self.fixture = (HERE / "fixture.c").read_bytes()
        require(sha256(self.fixture) == self.assets["fixture.c"]["sha256"], "fixture changed during initial capture")
        self.bound_artifacts = []
        self.cc = shutil.which(args.cc)
        require(self.cc, f"compiler not found: {args.cc}")
        self.cc = str(Path(self.cc).resolve())
        self.compiler = fingerprints([Path(self.cc)])
        self.flags = ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                      "-Wno-unused-parameter", "-fno-omit-frame-pointer"]
        # Only unused parameters are exempt: actual HAL has a reserved netdev
        # parameter and logging-only uses removed by the host logging macros.
        if args.sanitizers == "address,undefined":
            self.flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]

    def check_assets(self):
        unchanged(self.assets, file_inventory(HERE), "test asset set/content")
        unchanged(self.compiler, fingerprints([Path(self.cc)]), "compiler executable")

    def command(self, argv, directory, label):
        record = {"argv": argv, "shell_display": shlex.join(argv), "cwd": str(directory),
                  "environment": {k: self.env[k] for k in ("LC_ALL", "TMPDIR", "ASAN_OPTIONS", "UBSAN_OPTIONS")}}
        self.commands.append(record)
        try:
            proc = subprocess.run(argv, cwd=directory, env=self.env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            raise RuntimeError(f"timeout is a harness failure, never a killed control: {label}")
        finally:
            write_json(self.out / "commands.json", self.commands)
        record["returncode"] = proc.returncode
        for stream in ("stdout", "stderr"):
            path = directory / f"{label}.{stream}.txt"
            path.write_text(getattr(proc, stream))
            record[stream] = str(path.relative_to(self.out))
        write_json(self.out / "commands.json", self.commands)
        return proc

    def build_run(self, label, source, dt, early, selected=None, assertion=None):
        self.check_assets()
        directory = self.out / label
        directory.mkdir()
        (directory / "fixture.c").write_bytes(self.fixture)
        (directory / "bounds.inc").write_text("".join(f"#define {k} {v}\n" for k, v in source["bounds"].items()))
        parts = [source["license"]]
        for name in FUNCTIONS:
            # Original bodies stay verbatim; mutant variants are explicitly named.
            parts.append(f'#line {source["lines"][name]} {json.dumps(str(source["path"]))}\n{source["functions"][name]}\n')
        (directory / "actual-functions.inc").write_text("\n".join(parts))
        generated = [directory / name for name in ("fixture.c", "bounds.inc", "actual-functions.inc")]
        executable = directory / "probe-test"
        require(not executable.exists(), "refusing to execute or overwrite an existing binary")
        binding = {"source_before_compile": fingerprints(generated),
                   "compiler_before_compile": fingerprints([Path(self.cc)])}
        write_json(directory / "bindings.json", binding)
        command = [self.cc, *self.flags, f"-DNSS_DT_SUPPORT={dt}", f"-DEXPECT_EARLY={early}",
                   str(directory / "fixture.c"), "-o", str(executable)]
        compiled = self.command(command, directory, "compile")
        binding["source_after_compile"] = fingerprints(generated)
        binding["compiler_after_compile"] = fingerprints([Path(self.cc)])
        write_json(directory / "bindings.json", binding)
        unchanged(binding["source_before_compile"], binding["source_after_compile"], "generated compiler inputs")
        unchanged(self.compiler, binding["compiler_after_compile"], "compiler executable")
        require(compiled.returncode == 0, f"compile failed (not a valid negative): {label}; see {directory}")
        require(not compiled.stderr.strip(), f"compiler diagnostic requires review: {label}: {compiled.stderr}")
        binding["binary_after_compile"] = fingerprints([executable])
        binding["before_execute"] = fingerprints([*generated, executable])
        unchanged({**binding["source_after_compile"], **binding["binary_after_compile"]},
                  binding["before_execute"], "generated source/binary before execution")
        self.check_assets()
        write_json(directory / "bindings.json", binding)
        proc = self.command([str(executable), *(selected or [])], directory, "run")
        binding["after_execute"] = fingerprints([*generated, executable])
        binding["compiler_after_execute"] = fingerprints([Path(self.cc)])
        write_json(directory / "bindings.json", binding)
        unchanged(binding["before_execute"], binding["after_execute"], "generated source/binary during execution")
        unchanged(self.compiler, binding["compiler_after_execute"], "compiler executable")
        self.check_assets()
        self.bound_artifacts.append(binding["after_execute"])
        if assertion:
            require(expected_rejection(proc, assertion, selected[0], int(selected[1]), dt),
                    f"wrong runtime rejection for {label}: rc={proc.returncode}, stderr={proc.stderr!r}")
            rows = {}
        else:
            require(proc.returncode == 0 and not proc.stderr, f"positive execution failed: {label}: {proc.stderr}")
            rows = observations(proc.stdout)
            # Fail closed if the fixture silently stops running a core or case.
            for core in (0, 1):
                names = {k[2] for k in rows if k[0] == dt and k[1] == core and k[3] == "probe"}
                require(len(names) == (41 if dt else 35), f"incomplete scenario matrix: {label}, core {core}")
                require(all(f"irq{i}-fail" in names for i in range(10)), "missing IRQ failure position")
            write_json(directory / "observations.json", list(rows.values()))
        self.results["executions"].append({"label": label, "dt": dt, "early_contract": early,
                                           "cases": len(rows) // 2, "expected_assertion": assertion,
                                           "selected": selected, "returncode": proc.returncode,
                                           "passed": True})
        write_json(self.out / "results.json", self.results)
        return rows

    def run(self):
        self.check_assets()
        version = self.command([self.cc, "--version"], self.out, "compiler")
        require(version.returncode == 0, "compiler version failed")
        self.check_assets()
        sources = {}
        provenance = {"started_utc": datetime.now(timezone.utc).isoformat(),
                      "invocation": [sys.executable, *sys.argv], "invocation_cwd": os.getcwd(),
                      "python_version": sys.version, "compiler": self.cc,
                      "compiler_sha256": self.compiler[self.cc]["sha256"],
                      "compiler_version": version.stdout, "flags": self.flags,
                      "test_files": self.assets,
                      "inputs": {}}
        for label, path in (("baseline", self.args.baseline), ("candidate", self.args.candidate)):
            root = path.resolve()
            entries = inventory(root)
            write_json(self.out / f"{label}-inputs.json", entries)
            hal_bytes = (root / HAL).read_bytes()
            header_bytes = (root / "nss_core.h").read_bytes()
            require(sha256(hal_bytes) == entries[str(HAL)]["sha256"] and
                    sha256(header_bytes) == entries["nss_core.h"]["sha256"],
                    f"prepared {label} changed during extraction")
            text = hal_bytes.decode()
            funcs = {name: extract(text, name) for name in FUNCTIONS}
            sources[label] = {"path": root / HAL, "functions": {k: v[0] for k, v in funcs.items()},
                              "lines": {k: v[1] for k, v in funcs.items()},
                              "license": text[:text.index("*/") + 2],
                              "bounds": bounds(header_bytes.decode())}
            provenance["inputs"][label] = {"root": str(root), "files": len(entries),
                                           "manifest_sha256": sha256((self.out / f"{label}-inputs.json").read_bytes()),
                                           "hal_sha256": entries[str(HAL)]["sha256"],
                                           "functions": {k: {"line": v[1], "sha256": sha256(v[0].encode())} for k, v in funcs.items()}}
        write_json(self.out / "provenance.json", provenance)
        for dt in (0, 1):
            baseline = self.build_run(f"baseline-dt{dt}", sources["baseline"], dt, 0)
            candidate = self.build_run(f"candidate-dt{dt}", sources["candidate"], dt, 1)
            self.results["comparisons"] += compare(baseline, candidate)
            self.build_run(f"baseline-new-contract-dt{dt}", sources["baseline"], dt, 1,
                           ["dummy-oom-cold", "0"], "oom-no-provider")
        for name, case, assertion, modes, funcs in mutations(sources["candidate"]["functions"]):
            mutant = dict(sources["candidate"], functions=funcs)
            for dt in modes:
                self.build_run(f"negative-{name}-dt{dt}", mutant, dt, 1, [case, "0"], assertion)
        for label, path in (("baseline", self.args.baseline), ("candidate", self.args.candidate)):
            unchanged(json.loads((self.out / f"{label}-inputs.json").read_text()),
                      inventory(path.resolve()), f"prepared {label}")
        self.check_assets()
        for bound in self.bound_artifacts:
            unchanged(bound, fingerprints([Path(p) for p in bound]), "previously executed source/binary")
        self.results.update(status="PASS", inputs_unchanged=True,
                            test_assets_unchanged=True, compiler_unchanged=True, executed_artifacts_unchanged=True,
                            candidate_cases=sum(r["cases"] for r in self.results["executions"] if r["label"].startswith("candidate-")),
                            runtime_negatives=sum(bool(r["expected_assertion"]) for r in self.results["executions"]),
                            differential_phases=len(self.results["comparisons"]))
        write_json(self.out / "results.json", self.results)
        artifacts = {str(p.relative_to(self.out)): sha256(p.read_bytes())
                     for p in sorted(self.out.rglob("*")) if p.is_file()}
        write_json(self.out / "artifacts.json", artifacts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path, help="prepared driver directory before 030")
    parser.add_argument("--candidate", required=True, type=Path, help="actual prepared driver directory with 030")
    parser.add_argument("--output", required=True, type=Path, help="new, nonexistent evidence directory outside inputs")
    parser.add_argument("--cc", default="cc", help="one compiler executable, not a shell command")
    parser.add_argument("--sanitizers", choices=("address,undefined", "none"), default="address,undefined",
                        help="no automatic fallback; select none explicitly if compiler lacks runtimes")
    args = parser.parse_args()
    output = args.output.resolve()
    for root in (args.baseline.resolve(), args.candidate.resolve(), HERE):
        require(output != root and root not in output.parents and output not in root.parents,
                f"output must not overlap inputs or test sources: {output}")
    runner = Runner(args)
    try:
        runner.run()
    except Exception as exc:
        runner.results.update(status="FAIL", error=str(exc))
        write_json(output / "results.json", runner.results)
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {runner.results['candidate_cases']} candidate cases; "
          f"{runner.results['differential_phases']} non-OOM phase comparisons; "
          f"{runner.results['runtime_negatives']} exact runtime negatives. Evidence: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
