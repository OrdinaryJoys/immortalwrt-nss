#!/usr/bin/env python3
"""Host proof for the ath11k wifili peer stats payload bound and 12.5 layout.

Runs against the prepared backports tree and the prepared qca-nss-drv exports:
the two submitted ath11k functions are extracted complete from the prepared
source and compiled against the real wifili wire structures, so the compiled
record sizes are the actual 12.5 (212-byte) and legacy (196-byte) layouts. The
fixture also asserts the mac80211 wiring that selects the layout and the exact
one-shot probe line.

Two builds are exercised: the 12.5 build (-DNSS_FIRMWARE_VERSION_12_5) must
accept 4 + n*212 payloads and reject legacy 4 + n*196 payloads before any peer
data is read; the reverted build (no define) keeps the legacy layout working.
Mutations remove one bound at a time and must be detected. No target header,
module, firmware, device, network or CI operation is performed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURE = HERE / "ath11k-nss-peer-stats-bounds" / "host-fixture.c"

spec = importlib.util.spec_from_file_location(
    "extract_prepared_c", HERE / "nss-dp-containment" / "extract_prepared_c.py")
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)

PATCH_REL = ("package/kernel/mac80211/patches/nss/ath11k/"
             "999-957-ath11k-nss-validate-wifili-peer-stats-length.patch")
MAC_PATCH_FILES = ["drivers/net/wireless/ath/ath11k/nss.c",
                   "drivers/net/wireless/ath/ath11k/nss.h"]
NSS_REL = "drivers/net/wireless/ath/ath11k/nss.c"
NSS_H_REL = "drivers/net/wireless/ath/ath11k/nss.h"
PEER_STATS_MARKER = "nss wifili peer stats: len=%u npeers=%u stride=%zu"
ABI = {
    "wide": {"rx_ctrl": 96, "retry_ctrl": 24, "peer_ctrl": 212,
             "peer_stats": 216, "retry_off": 188, "message": 2096,
             "stats_notification": 1632},
    "narrow": {"rx_ctrl": 88, "retry_ctrl": 16, "peer_ctrl": 196,
               "peer_stats": 200, "retry_off": 180, "message": 2096,
               "stats_notification": 1632},
}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("prepared", type=Path,
                    help="prepared backports-6.18.26 tree (patched source)")
parser.add_argument("--driver-prepared", type=Path, required=True,
                    help="prepared qca-nss-drv tree with exports/")
parser.add_argument("--source-tree", type=Path, default=ROOT,
                    help="source tree carrying the mac80211 recipe and patch")
parser.add_argument("--cc", default="cc")
parser.add_argument("--sanitize", action="store_true")
parser.add_argument("--mutations", action="store_true")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

source = args.source_tree.resolve()
output = args.output.resolve()
if source == output or source in output.parents:
    raise SystemExit("fixture output must be outside the source tree")
output.mkdir(parents=True, exist_ok=False)


def require(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_source(relative):
    path = source / relative
    require(path.is_file(), "missing source file: " + relative)
    return path.read_text()


# --- mac80211 wiring: the 12.5 layout must be selected by the firmware symbol

makefile = read_source("package/kernel/mac80211/Makefile")
ath_mk = read_source("package/kernel/mac80211/ath.mk")
patch_text = read_source(PATCH_REL)
require("\tCONFIG_NSS_FIRMWARE_VERSION_12_5 \\\n" in makefile,
        "mac80211 PKG_CONFIG_DEPENDS lacks CONFIG_NSS_FIRMWARE_VERSION_12_5")
require(re.search(r"ifdef CONFIG_NSS_FIRMWARE_VERSION_12_5\n"
                  r"\tC_DEFINES\+= -DNSS_FIRMWARE_VERSION_12_5\n"
                  r"endif\n", makefile) is not None,
        "mac80211 C_DEFINES lacks the guarded NSS_FIRMWARE_VERSION_12_5 define")
require("-DCONFIG_NSS_FIRMWARE_VERSION_12_5" not in makefile,
        "mac80211 must pass the bare macro name, not the CONFIG_ symbol")
require("\tCONFIG_NSS_FIRMWARE_VERSION_12_5 \\\n" in ath_mk,
        "ath.mk PKG_CONFIG_DEPENDS lacks CONFIG_NSS_FIRMWARE_VERSION_12_5")
patch_files = re.findall(r"^--- a/(\S+)$", patch_text, re.M)
require(patch_files == MAC_PATCH_FILES,
        "patch must only touch the ath11k nss source and header: " + repr(patch_files))
require(PEER_STATS_MARKER in patch_text,
        "patch lacks the one-shot peer stats probe line")
require("ath11k_nss_peer_stats_len_ok" in patch_text,
        "patch lacks the peer stats length helper")
patch_dir = (source / PATCH_REL).parent
require(len(sorted(patch_dir.glob("999-957-*.patch"))) == 1,
        "expected exactly one 999-957 ath11k patch")

wiring = {
    "makefile_config_depends": True,
    "makefile_guarded_define": True,
    "ath_mk_config_depends": True,
    "patch_files": patch_files,
    "patch_sha256": sha256(patch_text.encode()),
}

# --- prepared driver exports: real wifili wire structures and arch constants

driver = extract.Prepared(args.driver_prepared)
driver_header = driver.read("exports/nss_wifili_if.h")
require(driver_header.count("#ifdef NSS_FIRMWARE_VERSION_12_5") >= 2,
        "prepared driver header is missing the 12.5 layout guards")
arch_rel = "exports/arch/nss_ipq807x_64.h"
try:
    arch_text = driver.read(arch_rel)
except ValueError:
    matches = sorted((args.driver_prepared / "exports" / "arch").glob("nss_*.h"))
    require(bool(matches), "prepared driver tree has no arch headers")
    arch_rel = matches[0].relative_to(args.driver_prepared).as_posix()
    arch_text = driver.read(arch_rel)
constant = re.search(r"^#define NSS_MAX_NUM_PRI\s+(\d+)\b", arch_text, re.M)
require(constant is not None, "arch header has no NSS_MAX_NUM_PRI")
host_constants = "#define NSS_MAX_NUM_PRI " + constant.group(1)

# --- prepared backports tree: the two submitted functions, byte preserved

tree = extract.Prepared(args.prepared)
nss_source = tree.read(NSS_REL)
nss_header = tree.read(NSS_H_REL)
require(nss_source.count("static bool ath11k_nss_peer_stats_len_ok(") == 1,
        "prepared source does not contain the submitted length helper")
require("ath11k_nss_get_peer_stats(ab, msg);" in nss_source,
        "peer stats handler does not hand the message to the parser")
require("struct nss_wifili_peer_stats *stats = &msg->msg.peer_stats.stats;" in nss_source,
        "peer stats parser does not derive the payload from the message")
peer_stats_struct = tree.structure(NSS_H_REL, "peer_stats")
require("tx_mpdu_retries" in peer_stats_struct and "last_rxdrop" in peer_stats_struct,
        "prepared peer_stats header is missing the 999-921 fields")
require("peer_stats_len_warned" in nss_header and
        "peer_stats_layout_logged" in nss_header,
        "prepared nss.h is missing the one-shot diagnostic flags")

peer_cap = re.search(r"^#define ATH11K_NSS_PEER_STATS_MAX_PEERS\s+\d+$",
                      nss_source, re.M)
require(peer_cap is not None, "prepared source has no peer stats cap macro")
functions = peer_cap.group(0) + "\n\n" + \
    tree.function(NSS_REL, "ath11k_nss_peer_stats_len_ok") + \
    tree.function(NSS_REL, "ath11k_nss_get_peer_stats")

template = FIXTURE.read_text()
require(template.count("/* HOST_CONSTANTS */") == 1 and
        template.count("/* HOST_PEER_STATS */") == 1 and
        template.count("/* HOST_FUNCTIONS */") == 1,
        "fixture template markers are incomplete")
code = template.replace("/* HOST_CONSTANTS */", host_constants) \
               .replace("/* HOST_PEER_STATS */", peer_stats_struct) \
               .replace("/* HOST_FUNCTIONS */", functions)

assets = {FIXTURE: FIXTURE.read_bytes()}
records = []

compiler_probe = subprocess.run(shlex.split(args.cc) + ["--version"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=60).stdout.decode(errors="replace")
gcc_extra = []
if "Free Software Foundation" in compiler_probe:
    gcc_extra = ["-Wno-format-truncation", "-Wno-maybe-uninitialized"]


def compile_run(candidate, directory, wide, sanitize):
    directory.mkdir(parents=True, exist_ok=True)
    source_file = directory / "fixture.c"
    binary = directory / "fixture"
    source_file.write_text(candidate)
    command = shlex.split(args.cc) + [
        "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
        "-Wno-sign-compare",
    ] + gcc_extra + [
        "-isystem", str(args.driver_prepared / "exports"),
        "-DHOST_WIDE=" + ("1" if wide else "0"),
    ]
    if wide:
        command.append("-DNSS_FIRMWARE_VERSION_12_5")
    if sanitize:
        # The wifili peer stats payload is a variable-length wire banner, not a
        # C object: the host code reads a peer count prefix out of a short
        # message exactly as the target does. ASan keeps the exact-size heap
        # redzone that proves no read crosses the declared length; disable only
        # the object-size/bounds checks that assume standalone C objects.
        command += ["-fsanitize=address,undefined", "-fno-sanitize=object-size,bounds",
                    "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    command += [str(source_file), "-o", str(binary)]
    environment = None
    if sanitize:
        environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=1",
                           UBSAN_OPTIONS="halt_on_error=1")
    compiled = subprocess.run(command, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120,
                              env=environment)
    (directory / "compile.log").write_bytes(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise SystemExit("fixture compilation failed: " +
                         (directory / "compile.log").read_text()[:4000])
    ran = subprocess.run([str(binary)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, timeout=120, env=environment)
    (directory / "run.log").write_bytes(ran.stdout + ran.stderr)
    result = None
    for line in reversed(ran.stdout.decode(errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        break
    return {"command": command, "returncode": ran.returncode,
            "stdout": ran.stdout.decode(errors="replace"),
            "stderr": ran.stderr.decode(errors="replace"), "result": result}


def detected(run):
    if run["returncode"] != 0:
        return True
    if run["result"] is not None and run["result"].get("failures"):
        return True
    return ("AddressSanitizer" in run["stderr"] or
            "runtime error:" in run["stderr"] or "FAIL:" in run["stderr"])


# --- both builds: ABI exactness and the length-bound behaviour

for name, wide in (("wide", True), ("narrow", False)):
    run = compile_run(code, output / name, wide, args.sanitize)
    expected = ABI[name]
    require(run["returncode"] == 0 and run["result"] is not None and
            run["result"].get("failures") == 0,
            name + " fixture failed: " + run["stderr"][:2000])
    for key, value in expected.items():
        require(run["result"].get(key) == value,
                name + " " + key + " = " + repr(run["result"].get(key)) +
                ", expected " + repr(value))
    require(run["result"].get("wide") == (1 if wide else 0),
            name + " fixture ran under the wrong layout macro")
    records.append({"variant": name, "wide": wide, "command": run["command"],
                    "returncode": run["returncode"], "checks": run["result"]["checks"],
                    "failures": 0, "abi": {key: run["result"][key] for key in expected}})

# --- mutation controls: every removed bound must be observed

warn_on = "\tif (!ab->nss.peer_stats_len_warned) {\n"
warn_off = "\tif (true) {\n"
log_on = "\tif (!ab->nss.peer_stats_layout_logged) {\n"
log_off = "\tif (true) {\n"
length_block = (
    "\tif (len < required) {\n"
    "\t\tif (!ab->nss.peer_stats_len_warned) {\n"
    "\t\t\tab->nss.peer_stats_len_warned = true;\n"
    "\t\t\tath11k_warn(ab, \"nss wifili peer stats: payload too short: \"\n"
    "\t\t\t\t    \"len=%u required=%zu npeers=%u stride=%zu\\n\",\n"
    "\t\t\t\t    len, required, npeers, stride);\n"
    "\t\t}\n"
    "\t\treturn false;\n"
    "\t}\n")
cap_condition = ("if (!npeers || npeers > ATH11K_NSS_PEER_STATS_MAX_PEERS) {")
short_condition = "\tif (len < sizeof(stats->npeers)) {\n"
required_line = "\trequired = sizeof(*stats) + (npeers - 1) * stride;\n"
layout_log = "ath11k_info(ab, \"nss wifili peer stats: len="

mutations = [
    ("drop-length-bind", length_block, "\t(void)required;\n"),
    ("drop-zero-peer-check", cap_condition,
     "if (npeers > ATH11K_NSS_PEER_STATS_MAX_PEERS) {"),
    ("drop-peers-cap", cap_condition, "if (!npeers) {"),
    ("always-log-layout", log_on, log_off),
    ("always-warn", warn_on, warn_off),
    ("required-plus-one", required_line,
     "\trequired = sizeof(*stats) + (npeers - 1) * stride + 1;\n"),
    ("required-counts-all-peers", required_line,
     "\trequired = sizeof(*stats) + npeers * stride;\n"),
    ("no-layout-log", layout_log, "ath11k_dbg(ab, 0, \"nss wifili peer stats: len="),
]
if args.sanitize:
    mutations.append(("drop-short-header-check", short_condition, "\tif (false) {\n"))

mutation_records = []
if args.mutations:
    for name, old, new in mutations:
        occurrences = functions.count(old)
        expected = functions.count(warn_on) if old == warn_on else 1
        require(occurrences == expected,
                "mutation " + name + " anchor found " + str(occurrences) +
                " times, expected " + str(expected))
        mutated_functions = functions.replace(old, new)
        require(mutated_functions != functions, "mutation " + name + " is a no-op")
        mutated_code = code.replace(functions, mutated_functions, 1)
        run = compile_run(mutated_code, output / "mutations" / name, True,
                          args.sanitize)
        require(detected(run),
                "mutation " + name + " escaped the host checks")
        mutation_records.append({
            "id": name, "detected": True, "returncode": run["returncode"],
            "failures": (run["result"] or {}).get("failures"),
            "sanitizer": ("AddressSanitizer" in run["stderr"] or
                          "runtime error:" in run["stderr"]),
        })

# --- evidence

prepared_manifest = tree.manifest()
driver_manifest = driver.manifest()
require(all(path.read_bytes() == data for path, data in assets.items()),
        "fixture assets changed during the host run")
result = {
    "scope": ("host contracts only: prepared ath11k functions, real prepared "
              "qca-nss-drv wire structures, mocked peers/locks/RCU; not target "
              "ABI, module, firmware or device validation"),
    "source_wiring": wiring,
    "source_tree": str(source),
    "prepared_manifest": prepared_manifest,
    "driver_manifest": driver_manifest,
    "fixture_sha256": sha256(assets[FIXTURE]),
    "generated_sha256": sha256(code.encode()),
    "abi_expected": ABI,
    "builds": records,
    "mutations": mutation_records,
    "sanitizer": args.sanitize,
    "hardware_accessed": False,
    "target_compiled": False,
}
(output / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"wiring": "pass", "wide": "pass", "narrow": "pass",
                  "mutations_detected": len(mutation_records),
                  "sanitizer": args.sanitize}))
