#!/usr/bin/env python3
"""B12/r34 host regression. Supply a NEW evidence directory; never modifies prepared.
Serial GMAC-style read-clear model, not MMIO, XGMAC, MP, DP or lifetime proof.
Without --candidate, B12's empty-port failures remain red. With --candidate,
they must reproduce precisely on B12 and disappear on the exact 056 postimage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

B12 = "8e73e59a440e80f5475d1147aca909f9459ba77f"
PIN = "d9a196497ecee2530722d906e0efe1b7408b6ef6"
PKG = "package/qca-nss/qca-ssdk"
REF, FAL, MIB, PORT, PLAT = FILES = (
    "src/ref/ref_mib.c", "src/fal/fal_mib.c", "include/fal/fal_mib.h",
    "include/fal/fal_type.h", "include/init/ssdk_plat.h")
HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "ssdk-mib-physical-ports/model.c"
CASES = ("cycles", "resets", "rx-error", "tx-error", "reset-between-ticks", "empty-0", "empty-1")
PATCH = HERE.parent / PKG / "patches/056-ssdk-mib-refuse-empty-physical-port-range.patch"
WORKER = b"\nqca_ar8327_sw_mib_task(struct qca_phy_priv *priv)\n{\n\tint ret;\n\n"
GUARD = b"\tif (priv->ports <= SSDK_PHYSICAL_PORT1)\n\t\treturn;\n\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique(text, pattern):
    hits = re.findall(pattern, text, re.M)
    if len(hits) != 1:
        raise ValueError(f"expected one {pattern!r}, got {len(hits)}")
    return hits[0]


def definition(text, name):
    # These selected definitions have a column-zero closing brace.
    return unique(text, r"^(?:static )?(?:int|void|sw_error_t)\s+" + name +
                  r"\([^;{}]*\)\s*\{[\s\S]*?^\}") + "\n"


def unit(files, ref):
    fal = files[FAL]
    types = [unique(files[PORT], r"^#define FAL_PORT_ID_VALUE\([^\n]+"),
             unique(files[PLAT], r"^#define SSDK_PHYSICAL_PORT1\s+\d+"),
             "#define BUF_SIZE " + unique(files[PLAT], r"a_uint8_t\s+buf\[(\d+)\]")]
    for name in ("fal_mib_info_t", "fal_mib_counter_t"):
        types.append(unique(files[MIB], r"typedef\s+struct\s*\{[^}]+\}\s*" + name + ";"))
    functions = unique(fal, r"^static a_bool_t g_mibcounter_invalid\[[^;]+;") + "\n"
    for name in ("_fal_mib_counter_invalidate", "_fal_rx_mib_update", "_fal_tx_mib_update",
                 "__fal_mib_counter_get_locked", "fal_mib_counter_get",
                 "fal_get_rx_mib_info", "fal_get_tx_mib_info", "fal_mib_port_flush_counters"):
        functions += definition(fal, name)
    callbacks = "".join(definition(ref, name) for name in (
        "_qca_ar8327_sw_capture_port_rx_counter", "_qca_ar8327_sw_capture_port_tx_counter",
        "qca_ar8327_sw_mib_task", "qca_ar8327_sw_set_reset_mibs",
        "qca_ar8327_sw_set_port_reset_mib", "qca_ar8327_sw_get_port_mib"))
    return (FIXTURE.read_text().replace("/* @types */", "\n".join(types))
            .replace("/* @fal */", functions).replace("/* @ref */", callbacks))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prepared", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, nargs="?", const=PATCH, metavar="PATCH_OR_TREE",
                    help="apply the worktree 056 patch to verified B12; optionally also check a supplied tree")
    ap.add_argument("--upstream", type=Path, help="local git object store for the SSDK pin; defaults to prepared")
    ap.add_argument("--cc", default="clang")
    ap.add_argument("--minimum-only", action="store_true",
                    help="only build and run the r34 ports=2 case; requires --candidate")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.minimum_only and not args.candidate:
        ap.error("--minimum-only requires --candidate")
    out = args.output.resolve()
    prepared = args.prepared.resolve()
    if out == prepared or prepared in out.parents:
        ap.error("output cannot be inside prepared")
    if HERE == out or HERE in out.parents:
        ap.error("write host evidence outside tests")
    candidate_tree = None
    if args.candidate:
        supplied = args.candidate.resolve(strict=True)
        if supplied.is_dir():
            candidate_tree = supplied
            if out == supplied or supplied in out.parents:
                ap.error("output cannot be inside supplied candidate")
        elif supplied != PATCH.resolve():
            ap.error("candidate patch must be the worktree's 056")
    out.mkdir(parents=True, exist_ok=False)
    cases = []

    def run(argv, cwd, *, data=None, required=True):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=cwd, input=data, capture_output=True,
                              env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"})
        with (out / "commands.jsonl").open("a") as f:
            print(json.dumps(dict(argv=argv, cwd=str(cwd), rc=proc.returncode,
                                  stdin_sha256=sha(data) if data is not None else None,
                                  stdout=proc.stdout.decode(errors="replace"),
                                  stderr=proc.stderr.decode(errors="replace"))), file=f)
        if required and proc.returncode:
            raise RuntimeError(f"{argv}: {proc.stderr.decode(errors='replace')}")
        return proc

    def git(cwd, *argv):
        return run(["git", *argv], cwd).stdout

    # Only replay relevant blobs to scratch for identity, never prepare a package.
    # Read the patch bytes from B12 objects (not worktree edits or a directory label).
    recipe = git(HERE, "show", f"{B12}:{PKG}/Makefile")
    if f"PKG_SOURCE_VERSION:={PIN}\n".encode() not in recipe or b"PKG_RELEASE:=33\n" not in recipe:
        raise ValueError("unexpected B12 SSDK recipe")
    paths = git(HERE.parent, "ls-tree", "-r", "--name-only", B12, f"{PKG}/patches").decode().splitlines()
    if not paths or not paths[-1].endswith("/055-ssdk-mib-start-physical-port.patch"):
        raise ValueError("missing B12 patch list or unexpected last layer")
    inputs = {p: (prepared / p).read_bytes() for p in FILES}
    manifest = dict(b12=B12, ssdk_pin=PIN, release=33, prepared=str(prepared),
                    recipe_sha256=sha(recipe), patches=[], prepared_sha256={p:sha(v) for p,v in inputs.items()},
                    model_sha256=sha(FIXTURE.read_bytes()), runner_sha256=sha(Path(__file__).read_bytes()))
    baseline = None
    candidate = None
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        scratch = Path(tmp)
        git(scratch, "init", "-q")
        for p in FILES:
            dest = scratch / p
            dest.parent.mkdir(exist_ok=True, parents=True)
            dest.write_bytes(git(args.upstream or prepared, "show", f"{PIN}:{p}"))
        for path in paths:
            if not path.endswith(".patch"):
                continue
            patch = git(HERE, "show", f"{B12}:{path}")
            touched = [p for p in FILES if b"+++ b/"+p.encode()+b"\n" in patch]
            if not touched:
                continue
            if Path(path).name.startswith("055-"):
                baseline = (scratch / REF).read_bytes()
                (out / "pre055-ref_mib.c").write_bytes(baseline)
            run(["git", "apply", "--whitespace=nowarn", *["--include="+p for p in touched], "-"],
                scratch, data=patch)
            manifest["patches"].append(dict(path=path, sha256=sha(patch), touched=touched))
        for p in FILES:
            if (scratch / p).read_bytes() != inputs[p]:
                raise ValueError(f"prepared differs from B12 postimage: {p}")
            saved = out / "verified-inputs" / p
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(inputs[p])
        if args.candidate:
            # Verify the input stack, rather than trusting a 'candidate' label.
            locked_paths = {HERE.parent / p for p in paths if p.endswith(".patch")}
            if set(PATCH.parent.glob("*.patch")) != locked_paths | {PATCH}:
                raise ValueError("expected B12 patch set plus exactly 056")
            for p in sorted(locked_paths):
                if p.read_bytes() != git(HERE, "show", f"{B12}:{p.relative_to(HERE.parent)}"):
                    raise ValueError(f"B12 layer changed: {p.name}")
            new_recipe = (PATCH.parent.parent / "Makefile").read_bytes()
            if new_recipe != recipe.replace(b"PKG_RELEASE:=33\n", b"PKG_RELEASE:=34\n"):
                raise ValueError("r34 recipe is not a release-only change")
            patch = PATCH.read_bytes()
            numstat = run(["git", "apply", "--numstat", "-"], scratch, data=patch).stdout
            if numstat != b"3\t0\tsrc/ref/ref_mib.c\n":
                raise ValueError("unexpected 056 numstat")
            run(["git", "apply", "--check", "--whitespace=error-all", "-"], scratch, data=patch)
            run(["git", "apply", "--whitespace=error-all", "-"], scratch, data=patch)
            candidate = {p:(scratch / p).read_bytes() for p in FILES}
            anchor = WORKER + b"\tmutex_lock(&priv->reg_mutex);"
            if inputs[REF].count(anchor) != 1 or GUARD in inputs[REF]:
                raise ValueError("missing unique B12 worker entry")
            expected = dict(inputs)
            expected[REF] = inputs[REF].replace(anchor, WORKER + GUARD + anchor[len(WORKER):])
            if candidate != expected:
                raise ValueError("056 changed more than the expected pre-mutex guard")
            for p, data in candidate.items():
                if candidate_tree and (candidate_tree / p).read_bytes() != data:
                    raise ValueError(f"supplied candidate differs from B12 + 056: {p}")
                saved = out / "r34-inputs" / p
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(data)
            (out / PATCH.name).write_bytes(patch)
            (out / "r34-Makefile").write_bytes(new_recipe)
            manifest["candidate"] = dict(release=34, patch=str(PATCH), patch_sha256=sha(patch),
                                         recipe_sha256=sha(new_recipe), supplied_tree=str(candidate_tree)
                                         if candidate_tree else None, files={p:sha(v) for p,v in candidate.items()})
    if baseline is None:
        raise ValueError("no 055 preimage")
    manifest["pre055_sha256"] = sha(baseline)
    manifest["argv"] = sys.argv
    manifest["scope"] = ("Serial host ref/FAL functions, modeled read-clear and mutex/spinlock. "
                         "Generic and HPPE GMAC swconfig dispatch only. No hardware, XGMAC, "
                         "MP backend, concurrent reset epoch, DP admission or reader retirement.")
    (out / "identity.json").write_text(json.dumps(manifest, indent=2)+"\n")
    for p in (FIXTURE, Path(__file__)):
        (out / p.name).write_bytes(p.read_bytes())
    run([args.cc, "--version"], out)
    sources = {p:v.decode() for p,v in inputs.items()}

    def build(label, files, ref):
        c = out / (label+".c")
        c.write_text(unit(files, ref))
        binary = out / label
        run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", c, "-o", binary], out)
        return binary

    def case(binary, name, defect=None):
        proc = run([binary, name], out, required=False)
        log = proc.stdout.decode()+proc.stderr.decode()
        (out / f"{binary.name}-{name}.log").write_text(log)
        expected = f"FAIL {name} {defect}" if defect else f"PASS {name}"
        match = proc.returncode == int(bool(defect)) and log.splitlines()[-1:] == [expected]
        if defect == "empty-worker-issued-io":
            match = match and log.splitlines() == [
                "IO dev=0 port=1 op=RX rx=0 tx=0 status=-3",
                "qca-ssdk: MIB sample failed dev=0 port=1 direction=rx error=-3", expected]
        row = dict(variant=binary.name, case=name, expected=expected, rc=proc.returncode,
                   observed=log.splitlines()[-1:], matched=match)
        cases.append(row)
        with (out / "cases.jsonl").open("a") as f:
            print(json.dumps(row), file=f)
        print(f"CASE {binary.name}/{name}: {row['observed']} (rc={proc.returncode})")
        return match

    def finish():
        hashes = (f"{sha(p.read_bytes())}  {p.relative_to(out)}\n"
                  for p in sorted(out.rglob("*")) if p.is_file())
        (out / "SHA256SUMS").write_text("".join(hashes))
        return int(not all(row["matched"] for row in cases))

    if args.minimum_only:
        sources = {p:v.decode() for p,v in candidate.items()}
        case(build("r34", sources, sources[REF]), "ports-2")
        return finish()

    base = build("pre055", sources, baseline.decode())
    if not case(base, "cycles", "event-port") or "IO dev=0 port=0 op=RX" not in (
            out / "pre055-cycles.log").read_text():
        raise ValueError("pre-055 must demonstrably poll CPU port first")
    fixed = build("b12", sources, sources[REF])
    for name in CASES:
        case(fixed, name, "empty-worker-issued-io" if candidate and name.startswith("empty-") else None)
    if candidate:
        sources = {p:v.decode() for p,v in candidate.items()}
        fixed = build("r34", sources, sources[REF])
        for name in (*CASES, "ports-2"):
            case(fixed, name)
        # Independent removal from actual candidate C, not a rerun of the B12 binary.
        if candidate[REF].count(GUARD) != 1:
            raise ValueError("ambiguous guard mutation")
        stripped = candidate[REF].replace(GUARD, b"")
        if stripped != inputs[REF]:
            raise ValueError("removing guard must restore B12 byte-for-byte")
        binary = build("r34-no-empty-guard", sources, stripped.decode())
        for name in ("empty-0", "empty-1"):
            case(binary, name, "empty-worker-issued-io")

    # Compile production-source changes only. A build error, crash or unrelated
    # assertion must never count as detection of the intended mutation.
    mutants = (
        ("wrap-zero", REF, "priv->mib_loop_cnt = 2 * SSDK_PHYSICAL_PORT1;\n\t}",
         "priv->mib_loop_cnt = 0;\n\t}", "cycles", "cursor"),
        ("swap-rx", REF, "ret = _qca_ar8327_sw_capture_port_rx_counter(priv->device_id",
         "ret = _qca_ar8327_sw_capture_port_tx_counter(priv->device_id", "cycles", "event-direction"),
        ("reset-skip-last", REF, "i < dev->ports; i++", "i+1 < dev->ports; i++", "resets", "reset-all-count"),
        ("reset-permit-cpu", REF, "val->port_vlan < SSDK_PHYSICAL_PORT1", "val->port_vlan < 0",
         "resets", "single-result"),
        ("drop-tx-value", FAL, ".TxBroad += mib_Info->TxBroad;", ".TxBroad += 0;", "cycles", "publish-tx"),
        ("false-recovery", FAL, "if (g_mibcounter_invalid[dev_id][port_index])",
         "if (0 && g_mibcounter_invalid[dev_id][port_index])", "rx-error", "invalid-fal"),
        ("hide-flush-error", REF, "ret = -EIO;", "ret = 0;", "resets", "reset-all-status"),
    )
    for label, path, before, after, name, defect in mutants:
        changed = sources.copy()
        if changed[path].count(before) != 1:
            raise ValueError(f"ambiguous mutation {label}")
        # Swap both directions so neither static capture function becomes dead.
        if label == "swap-rx":
            opposite = after
            if changed[path].count(opposite) != 1:
                raise ValueError("ambiguous TX site")
            changed[path] = changed[path].replace(opposite, "MUTANT_SWAP")
        changed[path] = changed[path].replace(before, after)
        if label == "swap-rx":
            changed[path] = changed[path].replace("MUTANT_SWAP", before)
        case(build(label, changed, changed[REF]), name, defect)
    return finish()


if __name__ == "__main__":
    sys.exit(main())
