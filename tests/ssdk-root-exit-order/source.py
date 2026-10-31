"""Exact31 root function extraction and six source-only ordering edits."""
import hashlib
import json
from pathlib import Path
import re

SOURCE_SHA = 'b8041a729d8d113853726edc71b2041fd110db30d90ef95bf535be63d0e29951'
RECEIPT_SHA = '099b63b20ea199eb6f63cc52cb3d9a4c3f683217a6548dfbfb559a26a0e90cf3'
MEMBERS = ['README.md', 'fixture.c', 'source.py']


def require(ok, marker):
    if not ok:
        raise ValueError(marker)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    paths = list(root.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'SYMLINK')
    return {str(p.relative_to(root)): sha(p) for p in paths if p.is_file()}


def masked(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                  lambda m: ' ' * len(m.group()), text)


def block_end(text, start):
    mask = masked(text); end = text.index('{', start) + 1; depth = 1
    while depth:
        depth += (mask[end] == '{') - (mask[end] == '}'); end += 1
    return end


def prepare(path, assets):
    require(sha(path) == SOURCE_SHA, 'SOURCE_IDENTITY')
    require(sorted(p.name for p in assets[1].parent.iterdir()) == MEMBERS, 'ASSET_INVENTORY')
    prepared = path.parents[2]; receipt = prepared.parent / 'RESULTS.json'
    require(sha(receipt) == RECEIPT_SHA, 'RECEIPT_IDENTITY')
    data = json.loads(receipt.read_text())
    require(len(data['patches']) == 31 and len(data['prepared_files']) == 692 and
            data['prepared_files']['src/init/ssdk_init.c'] == SOURCE_SHA, 'EXACT31')
    text = path.read_text(); pattern = r'^static void __exit\s+regi_exit\(void\)\s*\{'
    matches = list(re.finditer(pattern, text, re.M)); require(len(matches) == 1, 'COMPLETE_FUNCTION')
    start = matches[0].start(); body = text[start:block_end(text, start)]
    names = ['include/sal/os/aos_types.h', 'include/common/sw_error.h', 'include/common/sw_config.h']
    headers = {}
    for name in names:
        require(sha(prepared / name) == data['prepared_files'][name], 'ACTUAL_HEADER:' + name)
        headers[name] = (prepared / name).read_text()
    def one(pattern, text):
        found = re.findall(pattern, text, re.M); require(len(found) == 1, 'SMALL_DECLARATION'); return found[0]
    sdk = '#include <stdint.h>\ntypedef uint32_t __a_uint32_t;\n'
    sdk += one(r'^(typedef\s+__a_uint32_t\s+a_uint32_t;)', headers[names[0]]) + '\n'
    sdk += one(r'(typedef enum\s*\{\s*A_FALSE,\s*A_TRUE\s*\} a_bool_t;)', headers[names[0]]) + '\n'
    sdk += headers[names[1]] + '\n' + one(r'^(#define SW_MAX_NR_DEV\s+\d+)', headers[names[2]]) + '\n'
    inputs = {str(p): sha(p) for p in [path, receipt, *(prepared / n for n in names), *assets]}
    return body, sdk, inputs, dict(path=str(path), line=text[:start].count('\n') + 1,
                                  sha256=digest(body.encode()), transformation='none: complete actual regi_exit')


def replace(text, before, after):
    require(text.count(before) == 1, 'MUTANT_ANCHOR'); return text.replace(before, after, 1)


def variants(body):
    loops = []
    for m in re.finditer(r'for \(dev_id = 0; dev_id < dev_num; dev_id\+\+\) \{', body):
        start = body.rfind('\n', 0, m.start()) + 1
        loops.append(body[start:block_end(body, m.start())])
    require(len(loops) == 4, 'ACTUAL_FOUR_LOOPS')
    producer, sfp, cleanup, platform = loops
    inside = lambda loop: loop[loop.index('{') + 1:loop.rfind('}')]
    interleaved = producer[:producer.index('{') + 1] + inside(producer)
    interleaved += '\n#ifdef IN_SFP_PHY\n' + inside(sfp) + '\n#endif\n' + inside(cleanup) + '\n\t\t}'
    old = replace(replace(body, sfp, ''), cleanup, '')
    early_sfp = replace(body, sfp, '')
    early_platform = replace(body, platform, '')
    first = r'if \(rv == SW_OK\)\s*rv = cleanup_rv;'
    require(len(re.findall(first, body)) == 1, 'FIRST_ERROR_ANCHOR')
    return {
        'old-interleaved': replace(old, producer, interleaved),
        'early-sfp-retire': replace(early_sfp, producer, '#ifdef IN_SFP_PHY\n' + sfp + '\n#endif\n' + producer),
        'missing-cleanup': replace(body, 'cleanup_rv = ssdk_cleanup(dev_id);', 'cleanup_rv = SW_OK;'),
        'overwrite-first-error': re.sub(first, 'rv = cleanup_rv;', body, count=1),
        'early-platform': replace(early_platform, cleanup, platform + '\n' + cleanup),
        'ignore-registered': replace(body, 'if (qca_phy_priv_global[dev_id]->qca_ssdk_sw_dev_registered == A_TRUE)', 'if (1)')}


def stable(inputs, assets):
    require(sorted(p.name for p in assets[1].parent.iterdir()) == MEMBERS, 'END_ASSET_INVENTORY')
    for path, expected in inputs.items():
        require(sha(path) == expected, 'END_INPUT:' + path)
