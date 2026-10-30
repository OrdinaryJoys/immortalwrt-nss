#!/usr/bin/env python3
"""Fresh, host-only WIFILI context contract checks; no target or firmware build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


PIN = "6aa14c78e097b29c493ff2fef87e4d35906b2b5a"
BACKPORTS_SHA = "2ad578c6cae22f192fefd44e1449725228d4109ee781998b41dcbae872554968"
MAC_DIRS = ("build subsys ath ath5k ath9k ath10k ath11k ath12k rt2x00 "
            "mt7601u mwl brcm rtl nss/subsys nss/ath10k nss/ath11k").split()
NSS_FILES = ["nss_core.c", "nss_core.h", "nss_wifili.c", "nss_cmn.c",
             "nss_phys_if.h", "exports/nss_wifili_if.h", "exports/nss_cmn.h",
             "exports/nss_def.h", "exports/nss_api_if.h",
             "exports/nss_dynamic_interface.h", "exports/arch/nss_ipq807x_64.h",
             "nss_if.c", "nss_wifi_vdev.c", "nss_wifi_ext_vdev.c",
             "nss_data_plane/nss_data_plane.c", "nss_gre_redir_stats.c",
             "nss_gre_redir_mark.c", "nss_gre_redir.c"]
MAC_FILES = ["drivers/net/wireless/ath/ath11k/nss.c",
             "drivers/net/wireless/ath/ath11k/nss.h"]


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=90, **kwargs).stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_file(repo, ref, path):
    return run(["git", "-C", str(repo), "show", ref + ":" + path]).decode()


def replay(text, patch, target):
    lines = text.splitlines(keepends=True)
    src = patch.splitlines(keepends=True)
    name, delta, i = None, 0, 0
    offsets, count = [], 0
    while i < len(src):
        if src[i].startswith("+++ b/"):
            name, delta = src[i][6:].strip(), 0
            i += 1
            continue
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", src[i])
        if not m or name != target:
            i += 1
            continue
        old_n, new_n = int(m[2] or 1), int(m[4] or 1)
        old, new = [], []
        i += 1
        while len(old) < old_n or len(new) < new_n:
            line = src[i]
            if line.startswith(" "):
                old.append(line[1:])
                new.append(line[1:])
            elif line.startswith("-"):
                old.append(line[1:])
            elif line.startswith("+"):
                new.append(line[1:])
            elif not line.startswith("\\"):
                raise AssertionError("invalid selected hunk for " + target)
            i += 1
        if len(old) != old_n or len(new) != new_n:
            raise AssertionError("hunk count mismatch")
        start = int(m[1]) - (1 if old_n else 0)
        at = start + delta
        if lines[at:at + old_n] != old:
            hits = [n for n in range(len(lines) - old_n + 1)
                    if lines[n:n + old_n] == old]
            if len(hits) != 1:
                raise AssertionError("missing/nonunique full context: " + target)
            offsets.append({"line": int(m[1]), "offset": hits[0] - at})
            at = hits[0]
        lines[at:at + old_n] = new
        delta = at - start + new_n - old_n
        count += 1
    return "".join(lines), count, offsets


def patches(source, root, ref=None, ordered_dirs=None):
    if ref:
        names = run(["git", "-C", str(source), "ls-tree", "-r", "--name-only",
                     ref, root]).decode().splitlines()
        names = [n for n in names if n.endswith(".patch")]
    else:
        names = [p.relative_to(source).as_posix()
                 for p in (source / root).rglob("*.patch")]
    if ordered_dirs:
        order = {d: i for i, d in enumerate(ordered_dirs)}
        def key(name):
            relative = name[len(root) + 1:]
            directory = relative.rsplit("/", 1)[0]
            return order[directory], relative
        names.sort(key=key)
    else:
        names.sort()
    return [(n, git_file(source, ref, n) if ref else (source / n).read_text())
            for n in names]


def prepare(source, nss_repo, archive, output, ref=None):
    output.mkdir(parents=True, exist_ok=False)
    nss_recipe = (git_file(source, ref, "package/qca-nss/qca-nss-drv/Makefile")
                  if ref else (source / "package/qca-nss/qca-nss-drv/Makefile").read_text())
    if "PKG_SOURCE_VERSION:=6aa14c7\n" not in nss_recipe:
        raise AssertionError("driver recipe pin changed")
    if run(["git", "-C", str(nss_repo), "rev-parse", "6aa14c7^{commit}"]).decode().strip() != PIN:
        raise AssertionError("driver pin ambiguous")
    if sha(archive.read_bytes()) != BACKPORTS_SHA:
        raise AssertionError("backports archive SHA mismatch")
    mac_recipe = (git_file(source, ref, "package/kernel/mac80211/Makefile")
                  if ref else (source / "package/kernel/mac80211/Makefile").read_text())
    if BACKPORTS_SHA not in mac_recipe or "PKG_VERSION:=6.18.26\n" not in mac_recipe:
        raise AssertionError("backports recipe changed")
    nss_patches = patches(source, "package/qca-nss/qca-nss-drv/patches", ref)
    mac_patches = patches(source, "package/kernel/mac80211/patches", ref, MAC_DIRS)
    names = run(["tar", "-tf", str(archive)]).decode().splitlines()
    result = {"source_ref": ref or "current_worktree", "nss_pin": PIN,
              "backports_sha256": BACKPORTS_SHA, "files": [],
              "patches": [{"path": p, "sha256": sha(t.encode())}
                          for p, t in nss_patches + mac_patches]}
    for component, files, series in (("nss", NSS_FILES, nss_patches),
                                      ("mac80211", MAC_FILES, mac_patches)):
        for filename in files:
            if component == "nss":
                raw = git_file(nss_repo, PIN, filename)
            else:
                hits = [n for n in names if n.endswith("/" + filename)]
                if hits:
                    if len(hits) != 1:
                        raise AssertionError("nonunique archive entry")
                    raw = run(["tar", "-xOf", str(archive), hits[0]]).decode()
                else:
                    raw = ""
            text, used = raw, []
            for patch, body in series:
                text, count, offsets = replay(text, body, filename)
                if count:
                    used.append({"patch": patch, "hunks": count, "offsets": offsets})
            dest = output / component / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            result["files"].append({"path": component + "/" + filename,
                                    "raw_sha256": sha(raw.encode()),
                                    "sha256": sha(text.encode()), "hunks": used})
    (output / "PREPARED.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def balanced(text, start, opening, closing):
    depth, i = 0, start
    while i < len(text):
        if text.startswith("/*", i):
            i = text.index("*/", i + 2) + 2
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                raise AssertionError("unterminated source block")
            continue
        if text[i] in ('"', "'"):
            quote = text[i]
            i += 1
            while text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise AssertionError("unbalanced source")


def function(text, name):
    for match in re.finditer(r"\b" + name + r"\s*\(", text):
        paren = text.index("(", match.start())
        end_args = balanced(text, paren, "(", ")")
        body = end_args
        while text[body].isspace():
            body += 1
        if text[body] != "{":
            continue
        start = text.rfind("\n", 0, match.start()) + 1
        previous = text.rfind("\n", 0, start - 1) + 1
        if text[previous:start].strip() in ("static void", "static inline void"):
            start = previous
        return text[start:balanced(text, body, "{", "}")]
    raise AssertionError("missing actual function: " + name)


def fixture_source(prepared, template, opaque):
    core = (prepared / "nss/nss_core.c").read_text()
    registry_header = (prepared / "nss/nss_core.h").read_text()
    wifili = (prepared / "nss/nss_wifili.c").read_text()
    cmn_source = (prepared / "nss/nss_cmn.c").read_text()
    ath = (prepared / "mac80211/drivers/net/wireless/ath/ath11k/nss.c").read_text()
    fragments = {}
    core_names = ["nss_core_set_subsys_dp_type", "nss_core_register_subsys_dp",
                  "nss_core_unregister_subsys_dp", "nss_core_skb_needs_linearize"]
    if opaque:
        core_names.append("nss_core_register_wifili_ctx")
    core_names += ["nss_core_handle_ext_buffer_pkt", "nss_core_handle_buffer_pkt",
                   "nss_core_handle_virt_if_pkt"]
    wifili_names = ["nss_wifili_handler", "nss_register_wifili_if",
                    "nss_unregister_wifili_if", "nss_register_wifili_radio_if",
                    "nss_unregister_wifili_radio_if"]
    if opaque:
        wifili_names += ["nss_register_wifili_if_ctx", "nss_register_wifili_radio_if_ctx"]
    ath_names = ["ath11k_nss_wifili_event_receive", "ath11k_nss_wifili_ext_callback_fn",
                 "ath11k_nss_wifili_ext_callback_wrapper"]
    for marker, text, names in (("CORE", core, core_names),
                                ("LOOKUP", cmn_source, ["nss_cmn_get_interface_dev",
                                                       "nss_cmn_get_interface_number"]),
                                ("WIFILI", wifili, wifili_names),
                                ("ATH", ath, ath_names)):
        bodies = [function(text, name) for name in names]
        fragments.update({name: sha(body.encode()) for name, body in zip(names, bodies)})
        template = template.replace("/* SOURCE_" + marker + " */", "\n\n".join(bodies))
    start = registry_header.index("struct nss_subsystem_dataplane_register {")
    end = balanced(registry_header, registry_header.index("{", start), "{", "}")
    registry = registry_header[start:end + 1]
    template = template.replace("/* SOURCE_REGISTRY */", registry)
    phys = (prepared / "nss/nss_phys_if.h").read_text()
    cmn = (prepared / "nss/exports/nss_cmn.h").read_text()
    types = []
    for name, text in (("nss_phys_if_xmit_callback_t", phys),
                       ("nss_phys_if_rx_callback_t", phys),
                       ("nss_phys_if_rx_ext_data_callback_t", phys)):
        matches = re.findall(r"typedef\s+void\s*\(\*" + name + r"\)[\s\S]*?;", text)
        if len(matches) != 1:
            raise AssertionError("callback typedef identity: " + name)
        types.append(matches[0])
    template = template.replace("/* SOURCE_LEGACY_TYPES */", "\n".join(types))
    definitions = {}
    for filename in ("exports/nss_api_if.h", "exports/nss_dynamic_interface.h",
                     "exports/arch/nss_ipq807x_64.h"):
        for name, value in re.findall(r"^#define\s+(NSS_\w+)[ \t]+([^\n]+)",
                                     (prepared / "nss" / filename).read_text(), re.M):
            definitions[name] = value.split("/*")[0].strip()
    required = ["NSS_MAX_NUM_PRI", "NSS_MAX_NET_INTERFACES", "NSS_DYNAMIC_IF_START",
                "NSS_SPECIAL_IF_START", "NSS_WIFILI_INTERNAL_INTERFACE",
                "NSS_WIFILI_EXTERNAL_INTERFACE0", "NSS_WIFILI_EXTERNAL_INTERFACE1"]
    constants = {}
    def add(name):
        if name in constants:
            return
        value = definitions[name]
        for dependency in re.findall(r"\bNSS_\w+\b", value):
            add(dependency)
        constants[name] = value
    for name in required:
        add(name)
    template = template.replace("/* SOURCE_CONSTANTS */", "\n".join(
        "#define " + name + " " + value for name, value in constants.items()))
    for marker, pattern in (("SOC_CALL", r"nss_contex = nss_register_wifili_if(?:_ctx)?\([\s\S]*?;"),
                            ("RADIO_CALL", r"ar->nss.ctx = nss_register_wifili_radio_if(?:_ctx)?\([\s\S]*?;")):
        match = re.search(pattern, ath)
        if not match:
            raise AssertionError("missing actual ath11k registration statement")
        template = template.replace("/* SOURCE_" + marker + " */", match[0])
        fragments[marker] = sha(match[0].encode())
    if "/* SOURCE_" in template:
        raise AssertionError("unresolved fixture source marker")
    return "#define HAS_OPAQUE " + str(int(opaque)) + "\n" + template, fragments


def compile_run(code, prepared, directory, compiler):
    directory.mkdir(parents=True)
    src, binary = directory / "fixture.c", directory / "fixture"
    src.write_text(code)
    env = dict(os.environ, TMPDIR=str(directory),
               ASAN_OPTIONS="detect_leaks=0:abort_on_error=1",
               UBSAN_OPTIONS="halt_on_error=1")
    command = [compiler, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
               "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
               "-I" + str(prepared / "nss"), str(src), "-o", str(binary)]
    compiled = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=90, env=env)
    (directory / "compile.log").write_bytes(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise AssertionError("fixture compilation failed: " + str(directory / "compile.log"))
    if compiled.stdout or compiled.stderr:
        raise AssertionError("compiler emitted diagnostics: " + str(directory / "compile.log"))
    checked = subprocess.run([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             timeout=90, env=env)
    (directory / "run.log").write_bytes(checked.stdout + checked.stderr)
    return {"returncode": checked.returncode,
            "stdout": checked.stdout.decode(errors="replace"),
            "stderr": checked.stderr.decode(errors="replace"), "command": command}


def replace_in_function(code, name, old, new):
    original = function(code, name)
    if original.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + name + " / " + old)
    return code.replace(original, original.replace(old, new), 1)


def negative_controls(candidate, baseline):
    return [
        ("wrapper-private-offset", replace_in_function(candidate,
         "ath11k_nss_wifili_ext_callback_wrapper", "struct ath11k_base *ab = context;",
         "struct ath11k_base *ab = netdev_priv((struct net_device *)context);")),
        ("opaque-reads-fake-netdev-features", replace_in_function(candidate,
         "nss_core_handle_ext_buffer_pkt", "READ_ONCE(subsys_dp_reg->features)",
         "((struct net_device *)context)->features")),
        ("legacy-loses-dynamic-features", replace_in_function(candidate,
         "nss_core_handle_ext_buffer_pkt", "ndev->features", "subsys_dp_reg->features")),
        ("linearize-failure-still-calls-owner", replace_in_function(candidate,
         "nss_core_handle_ext_buffer_pkt", "__skb_linearize(nbuf))\n\t\t\tgoto drop;",
         "__skb_linearize(nbuf))\n\t\t\t(void)0;")),
        ("opaque-message-uses-ndev", replace_in_function(candidate,
         "nss_wifili_handler", "ctx = smp_load_acquire(&reg->wifili_ctx);", "ctx = NULL;")),
        ("notify-uses-global-fallback", replace_in_function(candidate,
         "nss_wifili_handler", "ctx ? READ_ONCE(reg->wifili_msg_cb) :",
         "false ? READ_ONCE(reg->wifili_msg_cb) :")),
        ("register-guard-missing-set-type-only", replace_in_function(candidate,
         "nss_core_register_subsys_dp", "BUG_ON(reg->wifili_ctx || (reg->ndev && reg->ndev != ndev));",
         "BUG_ON(reg->ndev && reg->ndev != ndev);")),
        ("unregister-retains-opaque-context", replace_in_function(candidate,
         "nss_core_unregister_subsys_dp", "smp_store_release(&reg->wifili_ctx, NULL);",
         "(void)reg->wifili_ctx;")),
        ("radio-still-registers-fake-netdev", candidate.replace(function(candidate, "client_radio"),
         function(baseline, "client_radio"), 1)),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--nss-source", type=Path, required=True)
    parser.add_argument("--backports-archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--compiler", action="append", default=[])
    args = parser.parse_args()
    source, output = args.source_tree.resolve(), args.output_dir.resolve()
    if source == output or source in output.parents:
        raise AssertionError("fixture output must be outside the source tree")
    output.mkdir(parents=True, exist_ok=False)
    result = prepare(source, args.nss_source.resolve(),
                     args.backports_archive.resolve(), output / "prepared")
    if not args.prepare_only:
        baseline = output / "baseline"
        baseline_meta = prepare(source, args.nss_source.resolve(),
                                args.backports_archive.resolve(), baseline,
                                "cfde3310d6fe3b007775a91c81e35309a29886a2")
        template = Path(__file__).with_name("test-ath11k-nss-context-fixture.c").read_text()
        candidate_code, fragments = fixture_source(output / "prepared", template, True)
        baseline_code, baseline_fragments = fixture_source(baseline, template, False)
        compilers = args.compiler or [shutil.which("clang") or "cc"]
        reports = []
        for index, compiler in enumerate(compilers):
            c = compile_run(candidate_code, output / "prepared", output / ("compiler-" + str(index)) / "candidate", compiler)
            if c["returncode"] or c["stderr"]:
                raise AssertionError("candidate failed: " + c["stderr"][:3000])
            b = compile_run(baseline_code, baseline, output / ("compiler-" + str(index)) / "baseline", compiler)
            if not b["returncode"]:
                raise AssertionError("old baseline unexpectedly passed")
            wire = r"wire_msg_size=(\d+) cmn_size=(\d+)"
            if re.search(wire, c["stdout"]).groups() != re.search(wire, b["stdout"]).groups():
                raise AssertionError("public wire struct sizes changed")
            cast_only = replace_in_function(baseline_code,
                "ath11k_nss_wifili_ext_callback_wrapper",
                "(struct ath11k_base *)netdev_priv(netdev)",
                "(struct ath11k_base *)(void *)netdev")
            cast_result = compile_run(cast_only, baseline,
                output / ("compiler-" + str(index)) / "cast-only", compiler)
            if not cast_result["returncode"] or "callback skb linearity" not in cast_result["stderr"]:
                raise AssertionError("cast-only control failed to expose nonlinear contract")
            mutations = []
            for label, code in negative_controls(candidate_code, baseline_code):
                mutated = compile_run(code, output / "prepared",
                    output / ("compiler-" + str(index)) / "mutations" / label, compiler)
                if not mutated["returncode"] or "FAIL:" not in mutated["stderr"]:
                    raise AssertionError("mutation escaped or was not a semantic failure: " + label)
                if label == "register-guard-missing-set-type-only" and "core register must reject opaque slot" not in mutated["stderr"]:
                    raise AssertionError("register overwrite negative control missed its target")
                mutations.append({"id": label, "source_sha256": sha(code.encode()), "result": mutated})
            reports.append({"compiler": compiler, "candidate": c, "baseline_rejected": b,
                            "cast_only_rejected": cast_result, "mutations_rejected": mutations})
        report = {"scope": "host context contract only; not lifetime/FW validation",
                  "candidate_inputs": result, "baseline_inputs": baseline_meta,
                  "fragments": fragments, "baseline_fragments": baseline_fragments,
                  "runs": reports}
        (output / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"candidate": "pass", "baseline": "rejected", "cast_only": "rejected",
                          "mutations_rejected_per_compiler": 9, "compilers": compilers}))
        return
    print(json.dumps({"prepared": str(output / "prepared"),
                      "files": len(result["files"]),
                      "qualification": "text only; no fixture executed"}))


if __name__ == "__main__":
    main()
