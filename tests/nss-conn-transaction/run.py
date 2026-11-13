#!/usr/bin/env python3
"""Run the NSS connection-table transaction and its RX/TX entry points on the host."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

from source import UNIT, paths, management_abi, strip_includes, entrypoints, require


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def invoke(argv, cwd, env):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=30)


def compile_fixture(cc, flags, work, env, variant, production, fixture, abi, source,
                    integration=None):
    subject = work / variant
    subject.mkdir()
    (subject / "wire_abi.h").write_bytes(abi)
    # The copied unit's line numbers and warnings still refer to the actual input.
    (subject / "production.inc").write_text(f"#line 1 {json.dumps(str(source))}\n{production}")
    unit = subject / "fixture.c"
    unit.write_bytes(fixture)
    if integration is not None:
        integration_source, entries = integration
        (subject / "integration.c").write_bytes(integration_source)
        (subject / "entrypoints.inc").write_text(entries)
        flags = [*flags, "-DHOST_INTEGRATION"]
    binary = subject / "fixture"
    result = invoke([cc, *flags, str(unit), "-o", str(binary)], work, env)
    require(result.returncode == 0 and not result.stderr and not result.stdout,
            f"{variant}: compile failed or noisy (status {result.returncode})\n"
            f"{result.stdout}{result.stderr}")
    return binary


def run_case(binary, case, work, env, expected_failure=None):
    result = invoke([str(binary), case], work, env)
    if expected_failure is None:
        expected = (0, f"PASS {case}\n", "")
    else:
        expected = (1, "", f"FAIL {case}:{expected_failure}\n")
    observed = (result.returncode, result.stdout, result.stderr)
    require(observed == expected,
            f"{binary.parent.name}/{case}: expected {expected!r}, observed {observed!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="prepared candidate NSS driver directory containing " + UNIT)
    parser.add_argument("--cc", default="clang", help="host C compiler executable")
    parser.add_argument("--optimization", choices=("O0", "O1", "O2"), default="O2")
    parser.add_argument("--sanitize", action="store_true", help="enable ASan and UBSan")
    args = parser.parse_args()

    from matrix import INTEGRATION, profiles, mutants, integration_mutants

    cc = shutil.which(args.cc)
    require(cc is not None, f"compiler not found: {args.cc}")
    cc = os.path.abspath(cc)
    input_paths = paths(args.source)
    source = input_paths[UNIT]
    captured = {name: path.read_bytes() for name, path in input_paths.items()}
    inputs = {name: data.decode() for name, data in captured.items()}
    abi = management_abi(inputs)
    production = strip_includes(inputs[UNIT])
    entries = entrypoints(inputs, input_paths)
    fixture, integration = [(HERE / name).read_bytes() for name in ("fixture.c", "integration.c")]
    flags = ["-std=gnu11", "-" + args.optimization, "-g", "-Wall", "-Wextra", "-Werror",
             "-Wno-sign-compare", "-pthread"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                  "-fno-sanitize-recover=all"]

    with tempfile.TemporaryDirectory(prefix=".host-", dir=HERE) as temp:
        work = Path(temp)
        env = dict(os.environ, LC_ALL="C", TMPDIR=temp,
                   ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        version = invoke([cc, "--version"], work, env)
        require(version.returncode == 0 and version.stdout.strip() and not version.stderr,
                f"could not identify compiler {cc}: {version.stderr}")
        for name, data in captured.items():
            print(f"input: {input_paths[name]} sha256={sha256(data)}", flush=True)
        print(f"fixture: sha256={sha256(fixture)}; extracted ABI: sha256={sha256(abi)}",
              flush=True)
        print(f"integration: sha256={sha256(integration)}; extracted entries: "
              f"sha256={sha256(entries.encode())}", flush=True)
        print(f"compiler: {cc}: {version.stdout.splitlines()[0]}; flags={' '.join(flags)}",
              flush=True)
        total = 0
        for profile, defines, cases in profiles():
            positive = compile_fixture(cc, flags + defines, work, env, profile, production,
                                       fixture, abi, source)
            for case in cases:
                run_case(positive, case, work, env)
            total += len(cases)
            print(f"{profile}: {len(cases)} cases passed", flush=True)
        count = 0
        _, defines, cases = next(profiles())
        integrated = compile_fixture(cc, flags + defines, work, env, "integration",
                                     production, fixture, abi, source, (integration, entries))
        for case in INTEGRATION:
            run_case(integrated, case, work, env)
        print(f"integration: {len(INTEGRATION)} cases passed", flush=True)
        for name, mutated, case, assertion in mutants(production):
            require(case in cases, f"{name}: control must use a passing candidate case")
            binary = compile_fixture(cc, flags + defines, work, env, name, mutated, fixture,
                                     abi, source)
            run_case(binary, case, work, env, expected_failure=assertion)
            count += 1
            print(f"{name}: exact failure {case}:{assertion}", flush=True)
        integration_count = 0
        for name, mutated, case, assertion in integration_mutants(entries):
            require(case in INTEGRATION, f"{name}: control must use a passing integration case")
            binary = compile_fixture(cc, flags + defines, work, env, name, production,
                                     fixture, abi, source, (integration, mutated))
            run_case(binary, case, work, env, expected_failure=assertion)
            integration_count += 1
            print(f"{name}: exact failure {case}:{assertion}", flush=True)
        for name, data in captured.items():
            require(input_paths[name].read_bytes() == data, f"input changed during the run: {name}")
        require((HERE / "fixture.c").read_bytes() == fixture, "fixture changed during the run")
        require((HERE / "integration.c").read_bytes() == integration,
                "integration fixture changed during the run")
        print(f"PASS transaction_cases={total} transaction_controls={count} "
              f"integration_cases={len(INTEGRATION)} integration_controls={integration_count}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
