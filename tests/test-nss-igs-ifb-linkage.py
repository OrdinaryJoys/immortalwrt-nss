#!/usr/bin/env python3
"""Compile the real IFB header/helper in separate host translation units."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
HELPER = HERE / 'nss-dp-containment/extract_prepared_c.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    with path.open('xb') as stream:
        stream.write(data.encode() if isinstance(data, str) else data)


def load(root, extract):
    prepared = extract.Prepared(root)
    header = prepared.read('nss_qdisc/igs/nss_ifb.h')
    function = prepared.function('nss_qdisc/igs/nss_ifb.c', 'nss_ifb_info_put')
    declarations = re.findall(r'^extern void nss_ifb_info_put\([^;]+;', header, re.M)
    if len(declarations) != 1:
        raise ValueError('expected exact public IFB put declaration')
    recipe = prepared.read('nss_qdisc/igs/Makefile')
    for name in ('nss_ifb.o', 'nss_mirred.o'):
        if name not in extract.code_mask(recipe):
            raise ValueError('expected both IFB users in the composite module')
    return prepared, header, function, declarations[0]


TYPES = '''#include <stdint.h>
#include <stdbool.h>
struct net_device;
struct sk_buff;
struct nf_hook_state;
struct list_head { struct list_head *next, *prev; };
'''
REFCOUNT = '''#ifndef HOST_REFCOUNT_H
#define HOST_REFCOUNT_H
typedef struct { unsigned int refs; } refcount_t;
static inline int refcount_dec_and_test(refcount_t *r) { return --r->refs == 0; }
#endif
'''
SUPPORT = '''#include <stdlib.h>
#include "host-types.h"
#include "nss_ifb.h"
unsigned int host_frees;
void kfree(void *pointer) { host_frees++; free(pointer); }
'''
CALLER = r'''#include <stdio.h>
#include <stdlib.h>
#include "host-types.h"
#include "nss_ifb.h"
extern unsigned int host_frees;
int main(void) {
    struct nss_ifb_info *binding = calloc(1, sizeof(*binding));
    if (!binding) return 70;
    binding->refs.refs = 2;
    nss_ifb_info_put(binding);
    unsigned int first = binding->refs.refs;
    nss_ifb_info_put(binding);
    unsigned int freed = host_frees;
    if (!freed) free(binding);
    printf("{\"after_first\":%u,\"frees\":%u}\n", first, freed);
    return first == 1 && freed == 1 ? 0 : 1;
}
'''


def changed(text, old, new):
    if text.count(old) != 1:
        raise ValueError('mutation must have exactly one code context: ' + old)
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    for path in (output,) + tuple(output.parents):
        if path.is_symlink():
            raise ValueError('output path must not contain symlinks')
    inputs = [args.prepared] + ([args.baseline] if args.baseline else [])
    for root in inputs:
        if root.is_symlink():
            raise ValueError('prepared root must not be a symlink')
        if output == root.resolve() or root.resolve() in output.parents:
            raise ValueError('output must be outside prepared input')
    spec = importlib.util.spec_from_file_location('ifb_extract', HELPER)
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)
    candidate, header, function, declaration = load(args.prepared, extract)
    if not function.startswith('void nss_ifb_info_put('):
        raise ValueError('candidate put helper must have external linkage')
    variants = [('candidate', header, function, 'pass')]
    prepared_inputs = [candidate]
    if args.baseline:
        baseline, old_header, old_function, _ = load(args.baseline, extract)
        if not old_function.startswith('static void nss_ifb_info_put('):
            raise ValueError('baseline must reproduce the pre-fix linkage conflict')
        variants.append(('baseline-static', old_header, old_function, 'static-conflict'))
        prepared_inputs.append(baseline)
    if args.mutations:
        variants.extend([
            ('static-definition', header, 'static ' + function, 'static-conflict'),
            ('missing-declaration', changed(header, declaration, ''), function, 'missing-declaration'),
            ('missing-definition', header, '', 'missing-definition'),
            ('wrong-signature', header, changed(function, 'void nss_ifb_info_put(', 'int nss_ifb_info_put('), 'wrong-signature'),
            ('omit-free', header, changed(function, 'kfree(ifb_info);', '(void)ifb_info;'), 'omit-free'),
            ('omit-decrement', header, changed(function, 'refcount_dec_and_test(&ifb_info->refs)', 'ifb_info == NULL'), 'omit-decrement'),
        ])
    output.mkdir(parents=True, exist_ok=False)
    flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    records = []
    commands = []

    def run(label, phase, argv):
        result = subprocess.run(argv, capture_output=True, timeout=60,
                                env=dict(os.environ, LC_ALL='C'))
        stem = output / (label + '-' + phase)
        save(stem.with_suffix('.stdout'), result.stdout)
        save(stem.with_suffix('.stderr'), result.stderr)
        row = {'variant': label, 'phase': phase, 'argv': argv, 'returncode': result.returncode,
               'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr)}
        commands.append(row)
        save(stem.with_suffix('.json'), json.dumps(row, indent=2) + '\n')
        if result.returncode < 0:
            raise ValueError('command terminated by signal: ' + label + '/' + phase)
        return result

    for label, variant_header, body, expected in variants:
        directory = output / label
        (directory / 'linux').mkdir(parents=True)
        for path, data in [('host-types.h', TYPES), ('linux/refcount.h', REFCOUNT),
                           ('nss_ifb.h', variant_header), ('definition.c', SUPPORT + body),
                           ('caller.c', CALLER)]:
            save(directory / path, data)
        failed_phase = None
        diagnostic = ''
        for phase, filename in [('compile-definition', 'definition.c'), ('compile-caller', 'caller.c')]:
            result = run(label, phase, [args.cc] + flags + ['-I', str(directory), '-c',
                         str(directory / filename), '-o', str(directory / (filename + '.o'))])
            if result.returncode:
                failed_phase = phase
                diagnostic = result.stderr.decode(errors='replace')
                break
        if failed_phase is None:
            result = run(label, 'link', [args.cc] + flags + [str(directory / 'definition.c.o'),
                         str(directory / 'caller.c.o'), '-o', str(directory / 'linked')])
            if result.returncode:
                failed_phase = 'link'
                diagnostic = result.stderr.decode(errors='replace')
        observed = None
        if failed_phase is None:
            result = run(label, 'run', [str(directory / 'linked')])
            if result.returncode not in (0, 1) or result.stderr:
                raise ValueError('unexpected runtime/sanitizer failure: ' + label)
            observed = json.loads(result.stdout)
            expected_observed = {'after_first': 2 if expected == 'omit-decrement' else 1,
                                 'frees': 0 if expected in ('omit-free', 'omit-decrement') else 1}
            if observed != expected_observed or result.returncode != (0 if expected == 'pass' else 1):
                raise ValueError('unexpected complete runtime result: ' + label)
        else:
            patterns = {
                'static-conflict': ('compile-definition', r'static declaration.*follows non-static'),
                'missing-declaration': ('compile-caller', r'(?:implicit declaration|undeclared function)'),
                'missing-definition': ('link', r'(?:[Uu]ndefined|unresolved)'),
                'wrong-signature': ('compile-definition', r'conflicting types'),
            }
            if expected not in patterns:
                raise ValueError('unexpected compiler/link failure: ' + label + '\n' + diagnostic)
            phase, pattern = patterns[expected]
            if failed_phase != phase or 'nss_ifb_info_put' not in diagnostic or not re.search(pattern, diagnostic):
                raise ValueError('wrong rejection diagnostic: ' + label + '\n' + diagnostic)
        if failed_phase is None and expected in ('static-conflict', 'missing-declaration', 'missing-definition', 'wrong-signature'):
            raise ValueError('negative control escaped: ' + label)
        records.append({'variant': label, 'expected': expected, 'rejected_phase': failed_phase,
                        'runtime': observed,
                        'inputs': [{'path': str(path), 'sha256': sha(path.read_bytes())}
                                   for path in sorted(directory.rglob('*')) if path.is_file()
                                   and path.suffix in ('.c', '.h')]})
    result = {'status': 'PASS_HOST_IFB_LINKAGE_ONLY', 'compiler': args.cc, 'sanitize': args.sanitize,
              'variants': records, 'commands': commands,
              'prepared': [item.manifest() for item in prepared_inputs],
              'runner_sha256': sha(Path(__file__).read_bytes()), 'extractor_sha256': sha(HELPER.read_bytes()),
              'scope': 'Real full IFB header and complete put function in separate host TUs. Kernel types/refcount/kfree are explicit substitutes. Compilation/linkage controls are not runtime failures. No kernel ABI, saturation, concurrency, callback, FW, target or performance acceptance.'}
    save(output / 'RESULT.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'variants': len(records), 'commands': len(commands)}))


if __name__ == '__main__':
    main()
