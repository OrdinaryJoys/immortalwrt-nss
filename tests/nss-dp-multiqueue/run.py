#!/usr/bin/env python3
"""Compile and run byte-extracted DP C; never prepare a tree or touch a device."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "nss-dp-containment/extract_prepared_c.py"
spec = importlib.util.spec_from_file_location("multiqueue_extract", HELPER)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
API = "exports/nss_dp_api_if.h"
PRIVATE = "include/nss_dp_dev.h"
HAL = "hal/include/nss_dp_hal_if.h"
ARCH = "hal/soc_ops/ipq807x/nss_ipq807x.h"
ATTACH = "nss_dp_attach.c"
MAIN = "nss_dp_main.c"
FILES = (API, PRIVATE, HAL, ARCH, ATTACH, MAIN, "Makefile")
ATTACH_FUNCTIONS = (
    "nss_dp_reset_netdev_features", "nss_dp_quarantine_init",
    "nss_dp_quarantine_open", "nss_dp_quarantine_noop", "nss_dp_quarantine_value",
    "nss_dp_quarantine_mac", "nss_dp_quarantine_xmit", "nss_dp_quarantine_features",
)
PLANE_FUNCTIONS = (
    "nss_dp_plane_init", "nss_dp_plane_get", "nss_dp_plane_put",
    "nss_dp_plane_is_quarantined", "nss_dp_plane_stop_phy",
    "nss_dp_plane_quiesce", "nss_dp_plane_quarantine", "nss_dp_plane_resume",
)
MAIN_FUNCTIONS = (
    "nss_dp_close_data_plane", "nss_dp_open_data_plane", "nss_dp_activate_data_plane",
    "nss_dp_xmit", "nss_dp_close", "nss_dp_open",
)
CONTROL_FUNCTIONS = (
    "nss_dp_override_data_plane", "nss_dp_start_data_plane", "nss_dp_restore_data_plane",
)
CORE_CASES = (
    "api-semantics", "down-phy", "down-no-phy", "down-uninitialized",
    "up-phy", "up-no-phy", "reopen-phy", "reopen-no-phy", "quarantine",
    "pending-open", "wrong-readiness",
)
OPEN_STAGES = ("vsi", "mac", "mtu", "open", "gmac", "link-up")
CASES = (CORE_CASES + ("open-error-init",) +
         tuple("open-error-" + s for s in OPEN_STAGES) +
         tuple("readiness-error-" + s for s in OPEN_STAGES) +
         tuple("takeover-error-" + s for s in ("init", "deinit", "close", "link-down")) +
         tuple("close-error-" + s for s in ("link-down", "unassign", "stop", "close")))
ACTIVATE = "nss_dp_activate_data_plane"
SINGLE = "netif_start_queue(dp->netdev);"
ALL = "netif_tx_start_all_queues(dp->netdev);"
# (source function, exact mutation, witness case, exact runtime rejection)
MUTATIONS = {
    "single-queue-regression": (ACTIVATE, ALL, SINGLE, "down-phy", "queues-ready"),
    "omit-queue-start": (ACTIVATE, ALL, "(void)0;", "down-phy", "queues-ready"),
    "skip-last-queue": (ACTIVATE, ALL,
        "for (unsigned q=0; q<3; q++) netif_tx_start_queue(netdev_get_tx_queue(dp->netdev,q));",
        "down-no-phy", "queues-ready"),
    "start-other-instance": (ACTIVATE, ALL,
        "netif_tx_start_all_queues(host_other_device(dp->netdev));", "down-phy", "peer-state"),
    "wake-instead-of-start": (ACTIVATE, ALL,
        "netif_tx_wake_all_queues(dp->netdev);", "down-phy", "activation-no-schedule"),
    "activate-failed-open": ("nss_dp_open", "if (!ret)", "if (true)",
        "open-error-mac", "error-no-start"),
    "resume-wakes-down-device": ("nss_dp_plane_resume", "netif_device_attach(dp->netdev);",
        "netif_device_attach(dp->netdev);\n\tnetif_tx_wake_all_queues(dp->netdev);",
        "down-phy", "down-admin-queues"),
    "wake-quarantined-device": ("nss_dp_plane_quarantine",
        "dp->plane_quarantined = true;",
        "dp->plane_quarantined = true;\n\tnetif_tx_start_all_queues(dp->netdev);",
        "quarantine", "quarantine-queues"),
    "failed-open-not-quarantined": ("nss_dp_open",
        "if (ret)\n\t\tnss_dp_plane_quarantine(dp_priv);", "(void)0;",
        "open-error-mac", "quarantine-state"),
    "pending-reader-admitted": ("nss_dp_plane_get",
        "!dp->plane_blocked && !dp->plane_quarantined", "!dp->plane_quarantined",
        "pending-open", "pending-open-denied"),
    "readiness-skips-open": ("nss_dp_start_data_plane",
        "if (was_open && nss_dp_open_data_plane(dp_dev, &ref))",
        "if (false && was_open && nss_dp_open_data_plane(dp_dev, &ref))",
        "readiness-error-open", "error-no-start"),
    "failed-gmac-start-ignored": ("nss_dp_open_data_plane",
        "if (dp->gmac_hal_ops->start &&", "if (false && dp->gmac_hal_ops->start &&",
        "open-error-gmac", "error-no-start"),
    "vsi-error-treated-as-success": ("nss_dp_open_data_plane",
        "ref->ops->vsi_assign(ref->dpc, dp->vsi))\n\t\treturn -EAGAIN;",
        "ref->ops->vsi_assign(ref->dpc, dp->vsi))\n\t\treturn 0;",
        "open-error-vsi", "error-no-start"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    require(text.count(old) == 1, "missing/ambiguous mutation anchor: " + old)
    return text.replace(old, new, 1)


def definitions(prepared):
    queue_define = re.findall(r"^#define\s+NSS_DP_QUEUE_NUM\s+4\s*$",
                              prepared.read(ARCH), re.M)
    require(len(queue_define) == 1, "prepared IPQ807x must define four queues")
    declarations = [queue_define[0] + "\n_Static_assert(NSS_DP_QUEUE_NUM == 4, \"four queues\");\n"]
    for path, names in (
        (API, ("nss_dp_data_plane_ctx", "nss_dp_gmac_stats",
               "nss_dp_vlan_append_info", "nss_dp_data_plane_ops")),
        (HAL, ("nss_gmac_hal_dev", "nss_gmac_hal_ops")),
        (PRIVATE, ("nss_dp_dev", "nss_dp_plane_ref")),
    ):
        declarations.extend(prepared.structure(path, name) for name in names)
    for name in ("nss_dp_link_state", "nss_dp_state", "nss_dp_priv_flags"):
        declarations.append(prepared.structure(PRIVATE, name, "enum"))
    functions = {}
    for path, names in ((ATTACH, ATTACH_FUNCTIONS + PLANE_FUNCTIONS),
                        (MAIN, MAIN_FUNCTIONS), (ATTACH, CONTROL_FUNCTIONS)):
        for name in names:
            functions[name] = prepared.function(path, name)
    return declarations, functions, prepared.variable(ATTACH, "nss_dp_quarantine_ops")


def program(prepared, defs, assets, mutation=None):
    declarations, original, quarantine = defs
    functions = original.copy()
    if mutation:
        name, old, new, _, _ = MUTATIONS[mutation]
        functions[name] = replace_once(functions[name], old, new)
    ordered = [functions[n] for n in ATTACH_FUNCTIONS] + [quarantine]
    ordered += [functions[n] for n in PLANE_FUNCTIONS + MAIN_FUNCTIONS + CONTROL_FUNCTIONS]
    # Only forward declarations are generated; every production body is intact.
    prototypes = []
    for name in MAIN_FUNCTIONS:
        prototypes.append(original[name].split("{", 1)[0].rstrip() + ";\n")
    licenses = [row["text"].split("*/", 1)[0] + "*/\n"
                for row in prepared.files.values() if row["text"].startswith("/*")]
    return ("".join(licenses) + assets["host_api.h"].decode() + "\n" +
            "".join(declarations + prototypes) +
            assets["cases.c"].decode().replace("HOST_FUNCTIONS", "\n".join(ordered)))


def environment():
    return dict(os.environ,
                ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=98",
                UBSAN_OPTIONS="halt_on_error=1:abort_on_error=0:print_stacktrace=1:exitcode=98")


def command(argv, folder, label, env=None):
    row = {"argv": argv, "cwd": str(folder)}
    try:
        p = subprocess.run(argv, cwd=folder, text=True, capture_output=True,
                           timeout=45, env=env)
        row.update(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired as e:
        row.update(returncode="timeout", stdout=(e.stdout or b"").decode(),
                   stderr=(e.stderr or b"").decode())
    (folder / (label + ".stdout")).write_text(row["stdout"])
    (folder / (label + ".stderr")).write_text(row["stderr"])
    (folder / (label + ".json")).write_text(json.dumps(row, indent=2) + "\n")
    return row


def compile_c(cc, text, output, label, sanitize):
    source, binary = output / (label + ".c"), output / (label + ".host")
    source.write_text(text)
    argv = [cc, "-std=gnu11", "-O0", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter"]
    if sanitize:
        argv += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                 "-fno-omit-frame-pointer"]
    argv += [str(source), "-o", str(binary)]
    row = command(argv, output, label + ".compile")
    require(row["returncode"] == 0 and not row["stderr"] and not row["stdout"],
            "compilation failure is NOT semantic rejection: " + label)
    return binary


def expected_result(row, case, marker=None):
    if type(row["returncode"]) is not int:
        return False
    if marker:
        if row["returncode"] != 86 or row["stderr"] != f"MQ_FAIL {case} {marker}\n":
            return False
    elif row["returncode"] != 0 or row["stderr"]:
        return False
    try:
        records = [json.loads(line) for line in row["stdout"].splitlines()]
    except (ValueError, TypeError):
        return False
    if not records:
        return False
    if not marker:
        if records[-1] != {"pass": case}:
            return False
        records = records[:-1]
    for rec in records:
        if (rec.get("case") != case or not isinstance(rec.get("phase"), str) or
                len(rec.get("queues", [])) != 4 or
                any(type(q) is not int or q < 0 for q in rec["queues"]) or "pass" in rec):
            return False
    return bool(records)


def oracle_controls():
    trace = '{"case":"c","phase":"p","queues":[0,1,1,1]}\n'
    fail = {"returncode": 86, "stdout": trace, "stderr": "MQ_FAIL c m\n"}
    good = {"returncode": 0, "stdout": trace + '{"pass":"c"}\n', "stderr": ""}
    require(expected_result(fail, "c", "m") and expected_result(good, "c"), "oracle positive")
    pollution = [
        dict(fail, returncode=1), dict(fail, returncode=-6), dict(fail, returncode=98),
        dict(fail, returncode="timeout"), dict(fail, stderr="MQ_FAIL c other\n"),
        dict(fail, stderr=fail["stderr"] + "noise\n"),
        dict(fail, stdout=fail["stdout"] + '{"pass":"c"}\n'),
        dict(fail, stdout=""), dict(fail, stdout="compiler error\n"),
    ]
    require(not any(expected_result(r, "c", "m") for r in pollution), "oracle pollution")
    return {"positive": 2, "rejected_pollution": len(pollution)}


def sanitizer_canaries(cc, output):
    samples = {
        "clean": ("int main(void) { return 0; }\n", 0, ""),
        "asan": ("#include <stdlib.h>\nint main(void) { volatile int n=3; "
                 "volatile int *p=malloc(sizeof(int)); p[n]=1; free((void *)p); return 0; }\n",
                 98, "AddressSanitizer"),
        "ubsan": ("int main(void) { volatile unsigned n=32; return (int)(1U << n); }\n",
                  98, "runtime error:"),
    }
    result = {}
    for name, (text, code, diagnostic) in samples.items():
        label = "canary-" + name
        binary = compile_c(cc, text, output, label, True)
        row = command([str(binary)], output, label + ".run", environment())
        require(row["returncode"] == code and not row["stdout"] and
                (diagnostic in row["stderr"] if diagnostic else not row["stderr"]),
                "sanitizer canary failure: " + name)
        result[name] = {"returncode": code, "diagnostic": diagnostic}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--output", type=Path, required=True,
                        help="new directory; existing results are never overwritten")
    parser.add_argument("--sanitize", action="store_true",
                        help="also run the whole matrix with ASan+UBSan after canaries")
    args = parser.parse_args()
    cc = shutil.which(args.cc)
    require(cc is not None, "compiler not found")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be a new directory")
    output.mkdir(parents=True)
    report = {"status": "INCOMPLETE", "scope": "ACTUAL_PREPARED_C_WITH_HOST_API_SUBSTITUTES",
              "kernel_target_or_runtime_acceptance": False, "compiler": cc,
              "host_platform": platform.platform(), "python": sys.version,
              "boundary": "no prepare, no target build, no network, no device, no archived fixture execution",
              "runs": [], "mutations": []}
    try:
        report["result_oracle_controls"] = oracle_controls()
        report["compiler_version"] = command([cc, "--version"], output, "compiler-version")
        assets = {name: (HERE / name).read_bytes() for name in ("host_api.h", "cases.c", "run.py")}
        assets["extract_prepared_c.py"] = HELPER.read_bytes()
        report["assets"] = {name: digest(data) for name, data in assets.items()}
        for name, data in assets.items():
            (output / ("asset-" + name)).write_bytes(data)
        baseline, candidate = extract.Prepared(args.baseline), extract.Prepared(args.candidate)
        for prepared, role in ((baseline, "baseline"), (candidate, "candidate")):
            for name in FILES:
                prepared.read(name)
            snapshot = output / (role + "-input")
            snapshot.mkdir()
            for row in prepared.files.values():
                (snapshot / row["path"].replace("/", "__")).write_text(row["text"])
        base_defs, cand_defs = definitions(baseline), definitions(candidate)
        old_activate = base_defs[1][ACTIVATE]
        new_activate = replace_once(old_activate, SINGLE, ALL)
        require(cand_defs[1][ACTIVATE] == new_activate, "candidate activation not the single-call fix")
        for name in FILES:
            expected = baseline.read(name)
            if name == MAIN:
                expected = replace_once(expected, old_activate, new_activate)
            require(candidate.read(name) == expected, "unexpected candidate delta: " + name)
        report["pair_check"] = "seven input files identical except the one activation call"
        if args.sanitize:
            report["sanitizer_canaries"] = sanitizer_canaries(cc, output)
        for sanitized in ((False, True) if args.sanitize else (False,)):
            suffix = "asan-ubsan" if sanitized else "plain"
            for role, prepared, defs in (("baseline", baseline, base_defs),
                                         ("candidate", candidate, cand_defs)):
                label = role + "-" + suffix
                binary = compile_c(cc, program(prepared, defs, assets), output, label, sanitized)
                for case in CASES:
                    marker = "queues-ready" if role == "baseline" and case.startswith("down-") else None
                    row = command([str(binary), case], output, label + "." + case, environment())
                    report["runs"].append({"label": label, "case": case, "expected_failure": marker,
                                           "returncode": row["returncode"]})
                    require(expected_result(row, case, marker), "unexpected run outcome: " + label + "/" + case)
            for mutation, (_, _, _, case, marker) in MUTATIONS.items():
                label = "mutation-" + mutation + "-" + suffix
                binary = compile_c(cc, program(candidate, cand_defs, assets, mutation),
                                   output, label, sanitized)
                row = command([str(binary), case], output, label + ".run", environment())
                report["mutations"].append({"label": label, "case": case, "marker": marker,
                                            "returncode": row["returncode"]})
                require(expected_result(row, case, marker), "not the precise runtime rejection: " + label)
        report["inputs"] = {"baseline": baseline.manifest(), "candidate": candidate.manifest()}
        for name, data in assets.items():
            path = HELPER if name == "extract_prepared_c.py" else HERE / name
            require(path.read_bytes() == data, "test asset changed during execution: " + name)
        report["status"] = "PASS_BASELINE_RUNTIME_WITNESSES_CANDIDATE_AND_MUTATIONS"
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        report["artifacts"] = [
            {"path": str(p.relative_to(output)), "bytes": p.stat().st_size,
             "sha256": digest(p.read_bytes())}
            for p in sorted(output.rglob("*")) if p.is_file()
        ]
        (output / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "output": str(output),
                      "runs": len(report["runs"]), "mutations": len(report["mutations"])}))


if __name__ == "__main__":
    main()
