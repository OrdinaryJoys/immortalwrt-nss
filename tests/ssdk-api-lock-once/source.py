"""Exact small-C and real SDK declaration inputs; no target preparation."""
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/UK-TRANSPORT-CANDIDATE-20261101-r1/prepared')
C_SHA = '2168c0f18aac90c995cc6f11546dfd95aff15c69fe3902808e070aae13128739'
RECEIPT_SHA = 'a7c4a14cf8d1e7a180e154c3a6d160c3c5813d64e4faedfea9802c7f47ad5997'
MEMBERS = ['README.md', 'fixture.c', 'mutations.py', 'source.py']


def require(ok, marker):
    if not ok:
        raise ValueError(marker)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def inventory(root):
    paths = list(root.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'SYMLINK')
    return {str(p.relative_to(root)): sha(p) for p in paths if p.is_file()}


def prepare(candidate, assets):
    require(sorted(p.name for p in assets[1].parent.iterdir()) == MEMBERS, 'ASSET_INVENTORY')
    require(sha(candidate) == C_SHA, 'CANDIDATE_IDENTITY')
    receipt = BASE.parent / 'RESULTS.json'
    require(sha(receipt) == RECEIPT_SHA, 'RECEIPT_IDENTITY')
    manifest = json.loads(receipt.read_text())['prepared_files']
    names = ['include/sal/os/aos_lock.h', 'include/sal/os/linux/aos_lock_pvt.h',
             'include/hsl/hsl_lock.h', 'include/hsl/hsl_api.h', 'include/common/sw_error.h']
    texts = {}
    for name in names:
        require(sha(BASE / name) == manifest[name], 'REAL_HEADER:' + name)
        texts[name] = (BASE / name).read_text()
    records = []
    def pick(name, pattern):
        text = texts[name]
        found = list(re.finditer(pattern, text, re.M))
        require(len(found) == 1, 'EXTRACT_ONE:' + pattern)
        m = found[0]
        records.append(dict(path=str(BASE / name), line=text[:m.start()].count('\n') + 1,
                            sha256=digest(m.group().encode()), text=m.group()))
        return m.group()
    pvt, pub = names[:2][::-1]
    # Pick each type separately: the spin and mutex aliases are not interchangeable.
    snippets = [pick(pvt, r'^typedef spinlock_t aos_lock_pvt_t;'),
                pick(pvt, r'^typedef struct mutex aos_mutex_lock_pvt_t;'),
                pick(pub, r'^typedef aos_lock_pvt_t aos_lock_t;'),
                pick(pub, r'^typedef aos_mutex_lock_pvt_t aos_mutex_lock_t;')]
    for suffix in ('init', '', 'unlock'):
        name = 'lock_init' if suffix == 'init' else ('unlock' if suffix else 'lock')
        snippets += [pick(pvt, r'^#define __aos_mutex_' + name + r'\(lock\)[^\n]*'),
                     pick(pub, r'^#define aos_mutex_' + name + r'\(lock\)[^\n]*')]
    snippets += [pick(names[2], r'sw_error_t hsl_api_lock_init\(void\);'),
                 pick(names[3], r'^extern aos_mutex_lock_t sw_hsl_api_lock;')]
    model = '''#ifndef LOCK_ONCE_SDK_H
#define LOCK_ONCE_SDK_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { unsigned model; } spinlock_t;
struct mutex { unsigned ready,held,inits,locks,unlocks,destroys,cookie; };
#define LOCK_COOKIE 0x5a17u
#define DEFINE_MUTEX(n) struct mutex n = {.ready=1,.cookie=LOCK_COOKIE}
void model_init(struct mutex *m);
void model_lock(struct mutex *m);
void model_unlock(struct mutex *m);
void model_destroy(struct mutex *m);
#define mutex_init(m) model_init(m)
#define mutex_lock(m) model_lock(m)
#define mutex_unlock(m) model_unlock(m)
#define mutex_destroy(m) model_destroy(m)
'''
    sdk = model + texts[names[4]] + '\n' + '\n'.join(snippets) + '\n#endif\n'
    actual = candidate.read_text()
    require(actual.count('#include "sw.h"') == 1, 'ONLY_SW_INCLUDE')
    paths = [candidate, receipt, *(BASE / n for n in names), *assets]
    return actual.replace('#include "sw.h"', '#include "sdk.h"', 1), sdk, records, {str(p): sha(p) for p in paths}


def stable(inputs, assets):
    require(sorted(p.name for p in assets[1].parent.iterdir()) == MEMBERS, 'END_ASSETS')
    for path, value in inputs.items():
        require(sha(path) == value, 'END_INPUT:' + path)
