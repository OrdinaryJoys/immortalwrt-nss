"""Bounded whole-C input preparation; no target preparation or old tools."""
import hashlib
import re
from pathlib import Path

C_PATH = "src/sal/sd/linux/uk_interface/sw_api_ks_ioctl.c"
C_SHA = "dfa07229ff945bcc063b5d3cc0803cb41dfe816237e8add7c4a27b36c1065a64"
BASE = Path("/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/OUTER-ADMISSION-CANDIDATE-20261031-r4/prepared")
BASE_RECEIPT_SHA = "645358b757642d6db932defd9100a0448f7c3c602fd9e923e29f606c6f7680a8"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


def match_one(pattern, text):
    found = re.findall(pattern, text, re.S)
    if len(found) != 1:
        raise ValueError("EXTRACTION_IDENTITY: " + pattern)
    return found[0]


def prepare(prepared, assets):
    raw = (prepared / C_PATH).read_bytes()
    if digest(raw) != C_SHA:
        raise ValueError("CANDIDATE_IDENTITY")
    receipt = BASE.parent / "RESULTS.json"
    if digest(receipt.read_bytes()) != BASE_RECEIPT_SHA:
        raise ValueError("BASE_RECEIPT_IDENTITY")
    # Only includes are removed. All other lines, bodies, guards and globals stay.
    lines = raw.decode().splitlines(keepends=True)
    removed = [(n + 1, line.rstrip()) for n, line in enumerate(lines)
               if re.match(r"^\s*#\s*include\s+", line)]
    actual = "".join("\n" if re.match(r"^\s*#\s*include\s+", line) else line
                     for line in lines)
    api = (BASE / "include/api/sw_api.h").read_text()
    types = (BASE / "include/sal/os/aos_types.h").read_text()
    shared = (BASE / "include/common/shared_func.h").read_text()
    declarations = [match_one(r"(typedef enum\s*\{\s*A_FALSE,\s*A_TRUE\s*\} a_bool_t;)", types)]
    for name in ("sw_api_func_t", "sw_api_param_t", "sw_api_t"):
        declarations.append(match_one(r"(typedef struct\s*\{[^{}]*\}\s*" + name + r";)", api))
    definitions = []
    for name in ("SW_MAX_API_BUF", "SW_MAX_API_PARAM", "SW_PARAM_IN", "SW_PARAM_OUT", "SW_PARAM_PTR"):
        found = [line for line in api.splitlines()
                 if re.match(r"^#define\s+" + name + r"\s", line)]
        if len(found) != 1:
            raise ValueError("DEFINE_IDENTITY: " + name)
        definitions.append(found[0])
    macro = match_one(r"(#define SW_OUT_ON_ERROR\(rtn\).*?while\(0\);)", shared)
    sdk = "\n".join([
        "/* Real SDK error enum, small declarations, constants and macro; scalar storage is a host model. */",
        "typedef uint8_t a_uint8_t; typedef uint16_t a_uint16_t;",
        "typedef uint32_t a_uint32_t; typedef uint64_t a_uint64_t;",
        (BASE / "include/common/sw_error.h").read_text(),
        *declarations, *definitions, macro, ""])
    paths = [prepared / C_PATH, BASE / C_PATH, receipt,
             BASE / "include/api/sw_api.h", BASE / "include/common/sw_error.h",
             BASE / "include/sal/os/aos_types.h", BASE / "include/common/shared_func.h",
             *assets]
    inputs = {str(p): digest(p.read_bytes()) for p in paths}
    return actual, sdk, inputs, removed


def stable(inputs):
    for path, expected in inputs.items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError("INPUT_DRIFT: " + path)


def generated_tail(root, expected):
    actual = inventory(root)
    actual.pop("RESULTS.json", None)
    if actual != expected:
        raise ValueError("GENERATED_INVENTORY_OR_BYTES")
