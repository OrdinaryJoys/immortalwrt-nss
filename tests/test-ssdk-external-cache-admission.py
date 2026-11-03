#!/usr/bin/env python3
"""Run actual current cache functions with the existing model and two new cases."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("external_cache", HERE / "test-ssdk-netdev-cache.py")
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)

CASES = r'''
    } else if (!strcmp(which, "external-disconnected")) {
        ssdk_dt_global.netdev_switch[0].switch_connected = false;
        ssdk_netdev_switch_t saved = ssdk_dt_global.netdev_switch[0];
        live();
        CHECK(ssdk_netdev_switch_init(&a) == SW_NOT_FOUND, "DISCONNECTED_STATUS");
        CHECK(a.refs == 2 && cells(&a) == 1, "DISCONNECTED_NO_EXT_REF");
        CHECK(!memcmp(&saved, &ssdk_dt_global.netdev_switch[0], sizeof(saved)), "DISCONNECTED_SLOT_UNCHANGED");
        name_is(1, "ethA");
        ssdk_switch_name_copy(0, name); CHECK(!name[0], "DISCONNECTED_NAME_UNCHANGED");
        event(NETDEV_REGISTER, &a);
        CHECK(a.refs == 2 && cells(&a) == 1, "DISCONNECTED_DUPLICATE");
        event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 1 && !cells(&a), "DISCONNECTED_RETIRE_PRIMARY");
    } else if (!strcmp(which, "external-skip-stale-first")) {
        ssdk_dt_global.netdev_switch[0].switch_connected = false;
        ssdk_dt_global.netdev_switch[1].switch_netdev_port = 1;
        ssdk_netdev_switch_t saved = ssdk_dt_global.netdev_switch[0];
        live();
        CHECK(ssdk_netdev_switch_init(&a) == SW_OK, "CONNECTED_LATER_STATUS");
        CHECK(a.refs == 3 && cells(&a) == 2, "CONNECTED_LATER_REF");
        CHECK(!memcmp(&saved, &ssdk_dt_global.netdev_switch[0], sizeof(saved)), "CONNECTED_LATER_PRESERVE_STALE");
        CHECK(ssdk_dt_global.netdev_switch[1].dev == &a, "CONNECTED_LATER_SLOT");
        ssdk_switch_name_copy(0, name); CHECK(!name[0], "CONNECTED_LATER_FIRST_NAME");
        ssdk_switch_name_copy(1, name); CHECK(!strcmp(name, "ethA"), "CONNECTED_LATER_SECOND_NAME");
        event(NETDEV_UNREGISTER, &a);
        CHECK(a.refs == 1 && !cells(&a), "CONNECTED_LATER_RETIRE");
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    inputs = {str(p): digest(p) for p in [Path(__file__), cache.HERE,
              cache.FIX / "host-fixture.c", HERE / "ssdk_source_prepare.py"]}
    for tree in (args.prepared, args.baseline):
        for path in sorted(tree.rglob("*")):
            if path.is_file():
                inputs[str(path)] = digest(path)
    report = {"status": "INCOMPLETE", "scope": "ACTUAL_CURRENT_CACHE_C_HOST_MODEL_NOT_REAL_KERNEL",
              "inputs": inputs, "compiles": [], "positives": [], "negatives": []}
    try:
        report["source_gate"] = cache.source_gate(args.prepared)
        bodies, render = cache.extract(args.prepared, out / "actual")
        original, _ = cache.function((args.baseline / "src/init/ssdk_plat.c").read_text(), "ssdk_netdev_switch_init")
        anchor = '    } else if (!strcmp(which, "primary-only")) {'

        def extended(selected):
            code = render(selected)
            cache.require(code.count(anchor) == 1, "one fixture extension anchor")
            return code.replace(anchor, CASES + anchor, 1)

        flags = ["-std=gnu11", "-O1", "-g", "-pthread", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-parameter"]
        env = dict(os.environ)
        if args.sanitize:
            flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
            env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1:abort_on_error=1"
            env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"

        def compile_case(label, selected, defines):
            path = out / (label + ".c")
            path.write_text(extended(selected))
            record = cache.run([args.cc, *flags, *defines, str(path), "-o", str(path.with_suffix(".host"))],
                               out, label + ".compile", env)
            cache.require(record["returncode"] == 0 and not record["stdout"] and not record["stderr"],
                          "clean compile " + label)
            report["compiles"].append({"label": label, "c_sha256": digest(path), **cache.public(record)})
            return path.with_suffix(".host")

        added = ["external-disconnected", "external-skip-stale-first"]
        for profile, defines in cache.PROFILES.items():
            binary = compile_case("candidate-" + profile, bodies, defines)
            for case in cache.CASES + added:
                record = cache.run([str(binary), case], out, profile + "-" + case, env)
                cache.require(cache.positive_ok(record, case), "positive " + profile + "/" + case)
                report["positives"].append({"profile": profile, "case": case, **cache.public(record)})
        variants = [("old-publisher", "ssdk_netdev_switch_init", original,
                     "external-disconnected", "DISCONNECTED_STATUS")]
        for name, function, old, new, case, marker in cache.MUTANTS:
            variants.append((name, function, cache.once(bodies[function], old, new), case, marker))
        changed = cache.once(bodies["ssdk_netdev_switch_init"],
            "!sw->switch_connected ||", "sw->switch_connected ||")
        variants.append(("invert-connected-publisher", "ssdk_netdev_switch_init", changed,
                         "external-disconnected", "DISCONNECTED_STATUS"))
        for label, function, body, case, marker in variants:
            selected = dict(bodies)
            selected[function] = body
            binary = compile_case("mutant-" + label, selected, cache.PROFILES["hppe-dsa"])
            record = cache.run([str(binary), case], out, label + ".run", env)
            cache.require(cache.negative_ok(record, marker), "exact negative " + label)
            report["negatives"].append({"label": label, "case": case, "marker": marker, **cache.public(record)})
        cache.require(all(digest(Path(p)) == d for p, d in inputs.items()), "input drift")
        report["status"] = "PASS_HOST_CURRENT_CACHE_AND_EXTERNAL_ADMISSION_NOT_RUNTIME"
    finally:
        (out / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "profiles": len(cache.PROFILES),
                      "positive_runs": len(report["positives"]), "negative_runs": len(report["negatives"])}))


if __name__ == "__main__":
    main()
