#!/usr/bin/env python3
"""Actual external-switch lookup C; not publication or concurrent retirement."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("extract_external_lookup", HERE / "nss-dp-containment/extract_prepared_c.py")
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)
NAMES = ("ssdk_dts_netdev_switch_find", "ssdk_dts_netdev_switch_find_by_devid")


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def once(text, old, new):
    need(text.count(old) == 1, "unique mutation preimage: " + old)
    return text.replace(old, new, 1)


def declarations(tree):
    selected = []
    for relative, pattern in [
        ("include/sal/os/aos_types.h", r"typedef\s+enum\s*\{[^}]*\}\s*a_bool_t\s*;"),
        ("include/sal/os/aos_types.h", r"^typedef\s+__a_uint8_t\s+a_uint8_t;"),
        ("include/sal/os/aos_types.h", r"^typedef\s+__a_uint32_t\s+a_uint32_t;"),
        ("include/init/ssdk_init.h", r"^#define SSDK_MAX_PORT_NUM[^\n]+"),
        ("include/init/ssdk_dts.h", r"^#define SSDK_NETDEV_SWITCH_NUM[^\n]+"),
        ("include/init/ssdk_dts.h", r"typedef\s+struct\s*\{[^}]*\}\s*ssdk_netdev_switch_t\s*;"),
    ]:
        matches = re.findall(pattern, (tree / relative).read_text(), re.M)
        need(len(matches) == 1, "exact actual declaration " + pattern)
        selected.append(matches[0])
    return "\n".join(selected)


PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t __a_uint8_t;
typedef uint32_t __a_uint32_t;
struct net_device { unsigned identity; };
'''
FIXTURE = r'''
_Static_assert(SSDK_NETDEV_SWITCH_NUM == 2, "reviewed external slot count");
static struct { ssdk_netdev_switch_t netdev_switch[SSDK_NETDEV_SWITCH_NUM]; } ssdk_dt_global;
static struct net_device netdevs[SSDK_NETDEV_SWITCH_NUM];
static unsigned cases;
static void demand(bool ok, const char *reason)
{
    if (!ok) { fprintf(stderr, "EXTERNAL_LOOKUP:%s\n", reason); exit(86); }
}
/* @FUNCTIONS@ */
int main(void)
{
    const unsigned fields[] = {0, 1, 7, 255};
    const unsigned keys[] = {0, 1, 2, 7, 254, 255, 256, UINT32_MAX};
    for (unsigned layout = 0; layout < 1024; layout++) {
        memset(&ssdk_dt_global, 0, sizeof(ssdk_dt_global));
        unsigned encoding = layout;
        for (unsigned i = 0; i < SSDK_NETDEV_SWITCH_NUM; i++, encoding /= 32) {
            unsigned state = encoding % 32;
            ssdk_netdev_switch_t *slot = &ssdk_dt_global.netdev_switch[i];
            slot->dev = &netdevs[i];
            slot->switch_connected = state & 1 ? A_TRUE : A_FALSE;
            slot->switch_netdev_port = fields[(state >> 1) & 3];
            slot->switch_dev_id = fields[(state >> 3) & 3];
            slot->switch_cpu_port = 0x5a + i;
            slot->switch_port_bmp = 0xa5 + i;
            slot->switch_athtag = 0x12345678 + i;
            slot->switch_erp_standby = i ? A_TRUE : A_FALSE;
            for (unsigned p = 0; p < SSDK_MAX_PORT_NUM; p++)
                slot->switch_port_vid[p] = 0xdead0000 + i * 256 + p;
        }
        unsigned char before[sizeof(ssdk_dt_global)];
        memcpy(before, &ssdk_dt_global, sizeof(before));
        for (unsigned k = 0; k < sizeof(keys) / sizeof(keys[0]); k++) {
            ssdk_netdev_switch_t *port = NULL, *device = NULL;
            for (unsigned i = 0; i < SSDK_NETDEV_SWITCH_NUM; i++) {
                ssdk_netdev_switch_t *slot = &ssdk_dt_global.netdev_switch[i];
                if (!slot->switch_connected) continue;
                if (!port && (unsigned)slot->switch_netdev_port == keys[k]) port = slot;
                if (!device && (unsigned)slot->switch_dev_id == keys[k]) device = slot;
            }
            demand(ssdk_dts_netdev_switch_find(keys[k]) == port, "port-result");
            demand(ssdk_dts_netdev_switch_find_by_devid(keys[k]) == device, "device-result");
            demand(!memcmp(before, &ssdk_dt_global, sizeof(before)), "foreign-state");
            cases++;
        }
    }
    printf("scenarios=%u connected_first_match_only=1 runtime_retirement=0\n", cases);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [args.prepared / p for p in ("src/init/ssdk_dts.c", "include/init/ssdk_dts.h",
             "include/init/ssdk_init.h", "include/sal/os/aos_types.h")]
    paths += [Path(__file__), HERE / "nss-dp-containment/extract_prepared_c.py"]
    if args.baseline:
        paths += [args.baseline / "src/init/ssdk_dts.c"]
    inputs = {str(p): sha(p.read_bytes()) for p in paths}
    bodies = {name: extract.function(paths[0].read_text(), name) for name in NAMES}
    variants = [("candidate", bodies, None)]
    if args.baseline:
        need(declarations(args.baseline) == declarations(args.prepared), "actual baseline declarations unchanged")
        original = {name: extract.function((args.baseline / "src/init/ssdk_dts.c").read_text(), name) for name in NAMES}
        variants.append(("old-zero-slot-witness", original, "port-result"))
    guard = "ssdk_dt_global.netdev_switch[index].switch_connected &&"
    for n, field, marker in [(NAMES[0], "switch_netdev_port", "port-result"),
                             (NAMES[1], "switch_dev_id", "device-result")]:
        short = "port" if n == NAMES[0] else "device"
        changes = [
            ("omit-connected", guard, "1 &&", marker),
            ("invert-connected", guard, "!ssdk_dt_global.netdev_switch[index].switch_connected &&", marker),
            ("wrong-key", "." + field + " == " + ("port_id" if short == "port" else "dev_id"),
             "." + field + " == (" + ("port_id" if short == "port" else "dev_id") + " ^ 1U)", marker),
            ("skip-last", "index < SSDK_NETDEV_SWITCH_NUM", "index < SSDK_NETDEV_SWITCH_NUM - 1", marker),
            ("skip-first", "for(index = 0;", "for(index = 1;", marker),
            ("wrong-slot", "return &ssdk_dt_global.netdev_switch[index];", "return &ssdk_dt_global.netdev_switch[0];", marker),
            ("false-found", "return NULL;", "return &ssdk_dt_global.netdev_switch[0];", marker),
            ("writes-peer", "return &ssdk_dt_global.netdev_switch[index];", "{ ssdk_dt_global.netdev_switch[index ^ 1].switch_athtag ^= 1; return &ssdk_dt_global.netdev_switch[index]; }", "foreign-state"),
        ]
        for label, old, new, reason in changes:
            changed = dict(bodies)
            changed[n] = once(changed[n], old, new)
            variants.append((short + "-" + label, changed, reason))
    result = {"status": "INCOMPLETE", "scope": "ACTUAL_LOOKUP_C_WITH_ACTUAL_SLOT_TYPE_HOST_ONLY",
              "inputs": inputs, "concurrent_reader_retirement_verified": False, "records": []}
    try:
        for label, functions, reason in variants:
            code = PREFIX + declarations(args.prepared) + "\n" + FIXTURE.replace(
                "/* @FUNCTIONS@ */", "\n".join(functions[n] for n in NAMES))
            c = args.output / (label + ".c")
            c.write_text(code)
            command = [args.cc, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
            if args.sanitize:
                command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            command += [str(c), "-o", str(c.with_suffix(".host"))]
            compiled = subprocess.run(command, capture_output=True, timeout=60)
            (args.output / (label + ".compile.stdout")).write_bytes(compiled.stdout)
            (args.output / (label + ".compile.stderr")).write_bytes(compiled.stderr)
            need(compiled.returncode == 0 and not compiled.stdout and not compiled.stderr, "clean compile " + label)
            executed = subprocess.run([str(c.with_suffix(".host"))], capture_output=True, timeout=60)
            (args.output / (label + ".stdout")).write_bytes(executed.stdout)
            (args.output / (label + ".stderr")).write_bytes(executed.stderr)
            result["records"].append({"label": label, "compile_command": command,
                "compile_returncode": compiled.returncode, "returncode": executed.returncode,
                "expected_marker": reason, "c_sha256": sha(c.read_bytes()),
                "binary_sha256": sha(c.with_suffix(".host").read_bytes()),
                "stdout_sha256": sha(executed.stdout), "stderr_sha256": sha(executed.stderr)})
            if reason:
                need(executed.returncode == 86 and not executed.stdout and
                     executed.stderr == ("EXTERNAL_LOOKUP:" + reason + "\n").encode(), "precise runtime rejection " + label)
            else:
                need(executed.returncode == 0 and not executed.stderr and executed.stdout ==
                     b"scenarios=8192 connected_first_match_only=1 runtime_retirement=0\n", "positive matrix")
        need(all(sha(Path(p).read_bytes()) == v for p, v in inputs.items()), "input drift")
        result["status"] = "PASS_HOST_LOOKUP_ADMISSION_NOT_SHARED_LIFECYCLE"
    finally:
        (args.output / "RESULTS.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "scenarios": 8192,
                      "precise_runtime_mutants": 16, "old_witness": bool(args.baseline)}))


if __name__ == "__main__":
    main()
