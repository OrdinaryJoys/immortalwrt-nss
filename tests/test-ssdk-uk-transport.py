#!/usr/bin/env python3
"""Fresh, bounded UK ioctl host model. Never runs any prior audit program."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
ASSET_DIR = HERE.parent / "ssdk-uk-transport"


def load(name):
    spec = importlib.util.spec_from_file_location("uk_" + name, ASSET_DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


source = load("source")
mutations = load("mutations")
ASSETS = [HERE] + [ASSET_DIR / n for n in ("README.md", "fixture.c", "source.py", "mutations.py")]
CASES = ("empty", "buffer-oom", "register-foreign-retry", "register-error-retry",
         "minor-repeat-conflict", "context-oom", "payload-native", "payload-compat",
         "dispatch-arity", "copy-errors", "old-fd", "active-command", "epoch-cap",
         "inconsistent-state", "dynamic-minor")
PROFILES = {"constant254": ["-DUK_MINOR_DEV=254"], "dynamic": []}
# Independent fixed obligation inventory. Not derived from mutations or observed failures.
CONTRACT = (
    ("premature-ready", "payload-native", "UNPUBLISHED_STATE", ("constant254", "dynamic")),
    ("register-under-api-lock", "payload-native", "MISC_LOCK_ORDER", ("constant254", "dynamic")),
    ("failed-register-deregisters-foreign", "register-foreign-retry", "FOREIGN_DEREGISTER", ("constant254", "dynamic")),
    ("ignore-file-epoch", "old-fd", "STALE_FD_REJECT", ("constant254", "dynamic")),
    ("close-keeps-context", "context-oom", "CONTEXT_CLOSE", ("constant254", "dynamic")),
    ("cleanup-resets-epoch", "payload-native", "CLEANUP_LEDGER", ("constant254", "dynamic")),
    ("commit-no-epoch-increment", "payload-native", "INIT_COMMIT", ("constant254", "dynamic")),
    ("no-epoch-cap", "epoch-cap", "EPOCH_CAP", ("constant254", "dynamic")),
    ("cleanup-blocks-on-command", "active-command", "MUTEX_SELF_LOCK", ("constant254", "dynamic")),
    ("accept-conflicting-protocol", "minor-repeat-conflict", "MINOR_CONFLICT", ("dynamic",)),
    ("wrong-context-oom", "context-oom", "CONTEXT_OOM", ("constant254", "dynamic")),
    ("compat-output-native-rounding", "payload-compat", "OUTPUT_EXTENT", ("constant254", "dynamic")),
    ("swap-dispatch-two-arguments", "dispatch-arity", "DISPATCH_ARGUMENTS", ("constant254", "dynamic")),
    ("publish-buffer-before-register", "payload-native", "UNPUBLISHED_STATE", ("constant254", "dynamic")),
)
EXPECTED_NEG = {(profile, name, case, marker) for name, case, marker, profiles in CONTRACT
                for profile in profiles}
if len(EXPECTED_NEG) != 27 or len(CONTRACT) != 14:
    raise RuntimeError("STATIC_CONTRACT_IDENTITY")


def inventory_gate(rows):
    tuples = [tuple(row) for row in rows]
    if len(tuples) != len(EXPECTED_NEG) or len(set(tuples)) != len(tuples) or set(tuples) != EXPECTED_NEG:
        raise ValueError("NEGATIVE_INVENTORY")


def control_gates():
    good = sorted(EXPECTED_NEG)
    inventory_gate(good)
    wrong_profile = list(good)
    wrong_profile[0] = ("wrong-profile",) + good[0][1:]
    wrong_marker = list(good)
    wrong_marker[0] = good[0][:3] + ("WRONG_MARKER",)
    bad = [[], good[:-1], good + [good[0]], wrong_profile, wrong_marker]
    for rows in bad:
        try:
            inventory_gate(rows)
        except ValueError as e:
            if str(e) != "NEGATIVE_INVENTORY":
                raise
        else:
            raise ValueError("INVENTORY_CONTROL_ACCEPTED")
    return {"valid": 1, "rejected": len(bad), "classification": "PYTHON_INVENTORY_CONTROL_NOT_SOURCE_MUTANT"}


class Run:
    def __init__(self, root, cc, sanitize):
        self.root, self.cc, self.sanitize = root, shlex.split(cc), sanitize
        self.generated = {}
        self.commands = []
        self.env = dict(os.environ)
        self.env.update(ASAN_OPTIONS="detect_leaks=0:abort_on_error=0:exitcode=97",
                        UBSAN_OPTIONS="halt_on_error=1:exitcode=98:print_stacktrace=1")

    def write(self, rel, data):
        if isinstance(data, str):
            data = data.encode()
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.generated[rel] = source.digest(data)
        return path

    def opaque(self, path):
        self.generated[str(path.relative_to(self.root))] = source.digest(path.read_bytes())

    def invoke(self, rel, argv, sanitizer_exit=None):
        env = dict(self.env)
        if sanitizer_exit is not None:
            # ASan and UBSan parse the same common exitcode flag in combined builds.
            env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=0:exitcode=" + str(sanitizer_exit)
            env["UBSAN_OPTIONS"] = "halt_on_error=1:exitcode=" + str(sanitizer_exit) + ":print_stacktrace=1"
        try:
            process = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=30, check=False)
        except subprocess.TimeoutExpired as e:
            self.write(rel + ".stdout", e.stdout or b"")
            self.write(rel + ".stderr", e.stderr or b"")
            self.write(rel + ".json", json.dumps({"argv": argv, "timeout": True}, indent=2))
            raise ValueError("COMMAND_TIMEOUT: " + rel)
        self.write(rel + ".stdout", process.stdout)
        self.write(rel + ".stderr", process.stderr)
        row = {"argv": argv, "returncode": process.returncode,
               "ASAN_OPTIONS": env["ASAN_OPTIONS"], "UBSAN_OPTIONS": env["UBSAN_OPTIONS"]}
        self.write(rel + ".json", json.dumps(row, indent=2) + "\n")
        self.commands.append(row)
        return process

    def compile(self, rel, text, sdk, definitions, standalone=False):
        folder = self.root / rel
        if not standalone:
            self.write(rel + "/candidate.c", text)
            self.write(rel + "/sdk.h", sdk)
            self.write(rel + "/fixture.c", (ASSET_DIR / "fixture.c").read_bytes())
        else:
            self.write(rel + "/fixture.c", text)
        binary = folder / "fixture.bin"
        # Actual callback signatures retain unused inode/cmd parameters in whole bodies.
        flags = ["-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter"]
        if self.sanitize:
            flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all"]
        p = self.invoke(rel + "/compile", self.cc + flags + definitions + [str(folder / "fixture.c"), "-o", str(binary)])
        if p.returncode or p.stdout or p.stderr:
            raise ValueError("UNCLEAN_COMPILE: " + rel)
        self.opaque(binary)
        dsym = Path(str(binary) + ".dSYM")
        if dsym.exists():
            info = "Contents/Info.plist"
            dwarf = "Contents/Resources/DWARF/fixture.bin"
            reloc = "Contents/Resources/Relocations/aarch64/fixture.bin.yml"
            shapes = [{info, dwarf}, {info, reloc}, {info, dwarf, reloc}]
            actual = {str(x.relative_to(dsym)) for x in dsym.rglob("*") if x.is_file()}
            if actual not in shapes:
                raise ValueError("DSYM_SHAPE: " + rel)
            for member in actual:
                self.opaque(dsym / member)
        return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if not sys.flags.optimize:
        parser.error("run with python3 -O (no assert-dependent checks)")
    root = args.output.resolve()
    if root.exists():
        parser.error("--output must not exist")
    root.mkdir(parents=True)
    run = Run(root, args.cc, args.sanitize)
    result = {"status": "FAILED", "qualification": "HOST_MODEL_ONLY", "positives": [], "negatives": [],
              "limits": ["Serial mutex/misc model, not kernel scheduling/lockdep or device validation",
                         "Quarantined host allocations: not real free/UAF or same-address reuse proof",
                         "Usercopy handles and reduced API provider: not native/COMPAT target ABI",
                         "No SD/cohort/root/reader-drain/target build qualification"],
              "sanitizers": {"enabled": args.sanitize, "LSan": "NOT_VERIFIED"}}
    try:
        prepared = args.prepared.resolve()
        actual, sdk, inputs, removed = source.prepare(prepared, ASSETS)
        before = source.inventory(prepared)
        base_before = source.inventory(source.BASE)
        result.update(inputs=inputs, candidate_sha256=source.C_SHA,
                      candidate_tree_count=len(before), baseline_tree_count=len(base_before),
                      include_removals=removed, inventory_controls=control_gates())
        run.write("INPUTS.json", json.dumps(inputs, indent=2, sort_keys=True) + "\n")
        run.write("TREE-INPUTS.json", json.dumps({"candidate": before, "baseline28": base_before}, indent=2, sort_keys=True) + "\n")
        variants = mutations.variants(actual)
        if set(variants) != {row[0] for row in CONTRACT}:
            raise ValueError("MUTATION_SOURCE_INVENTORY")
        inventory_gate(sorted(EXPECTED_NEG))
        run.write("OBLIGATIONS.json", json.dumps(sorted(EXPECTED_NEG), indent=2) + "\n")
        for profile, definitions in PROFILES.items():
            binary = run.compile(profile + "/positive", actual, sdk, definitions)
            expected = "".join("OK " + case + "\n" for case in CASES).encode()
            run.write(profile + "/positive/stdout.expected", expected)
            p = run.invoke(profile + "/positive/run", [str(binary)])
            if p.returncode or p.stderr or p.stdout != expected:
                raise ValueError("POSITIVE_RUNTIME: " + profile)
            result["positives"] += [{"profile": profile, "case": case} for case in CASES]
        for profile, name, case, marker in sorted(EXPECTED_NEG):
            rel = profile + "/negative/" + name
            binary = run.compile(rel, variants[name], sdk, PROFILES[profile])
            p = run.invoke(rel + "/run", [str(binary), case])
            expected = ("UK_ASSERT:" + marker + "\n").encode()
            run.write(rel + "/stderr.expected", expected)
            if p.returncode != 86 or p.stdout or p.stderr != expected:
                raise ValueError("NEGATIVE_NOT_EXACT: " + profile + "/" + name)
            result["negatives"].append({"profile": profile, "name": name, "case": case,
                                        "marker": marker, "classification": "ACTUAL_SOURCE_SEMANTIC_MUTANT"})
        inventory_gate([(r["profile"], r["name"], r["case"], r["marker"]) for r in result["negatives"]])
        if result["positives"] != [{"profile": p, "case": c} for p in PROFILES for c in CASES]:
            raise ValueError("POSITIVE_COMPLETION_INVENTORY")
        if args.sanitize:
            canaries = {
                "asan": ("#include <stdlib.h>\nint main(int c,char **v){volatile int *p=malloc(sizeof(int));(void)v;p[c]=7;free((void*)p);return 0;}\n", 97, b"AddressSanitizer"),
                "ubsan": ("#include <limits.h>\nint main(void){volatile int x=INT_MAX;return x+1;}\n", 98, b"runtime error"),
            }
            result["sanitizers"]["canaries"] = {}
            for name, (text, code, marker) in canaries.items():
                binary = run.compile("canary/" + name, text, "", [], standalone=True)
                p = run.invoke("canary/" + name + "/run", [str(binary)], sanitizer_exit=code)
                if p.returncode != code or p.stdout or marker not in p.stderr:
                    raise ValueError("SANITIZER_CANARY: " + name)
                result["sanitizers"]["canaries"][name] = code
        source.stable(inputs)
        if source.inventory(prepared) != before or source.inventory(source.BASE) != base_before:
            raise ValueError("SOURCE_TREE_DRIFT")
        source.generated_tail(root, run.generated)
        result.update(status="HOST_MODEL_ONLY", outcome="PASSED_WITHIN_SERIAL_HOST_MODEL",
                      positive_count=len(result["positives"]), source_variant_count=len(CONTRACT),
                      source_negative_executions=len(result["negatives"]), end_input_stability=True,
                      generated=run.generated, generated_tail="EXACT_PATH_INVENTORY_AND_HASH")
    except Exception as e:
        result["error"] = str(e)
    result["commands"] = run.commands
    (root / "RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "outcome", "positive_count", "source_negative_executions", "error") if k in result}))
    return 0 if result["status"] == "HOST_MODEL_ONLY" else 1


if __name__ == "__main__":
    sys.exit(main())
