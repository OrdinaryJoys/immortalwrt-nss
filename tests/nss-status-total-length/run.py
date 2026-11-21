#!/usr/bin/env python3
"""Local defensive transport-length regression; no target or device operations."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]
BASE = '8e73e59a440e80f5475d1147aca909f9459ba77f'
PIN = '6aa14c78e097b29c493ff2fef87e4d35906b2b5a'
PACKAGE = 'package/qca-nss/qca-nss-drv'
PATCH = PACKAGE + '/patches/056-nss-status-include-header-in-packet-length-check.patch'
FILES = ('nss_core.c', 'exports/nss_cmn.h', 'exports/nss_def.h', 'exports/nss_api_if.h',
         'exports/nss_dynamic_interface.h', 'exports/nss_ipv4.h', 'exports/nss_ipv6.h',
         'nss_tx_rx_common.h')
SPEC = importlib.util.spec_from_file_location('extract', HERE.parent / 'nss-dp-containment/extract_prepared_c.py')
EXTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACT)
CASES = ('exact-linear', 'padded-linear', 'short-one', 'payload-only', 'zero-payload', 'header-short',
         'head-short', 'invalid-version', 'invalid-interface', 'unaligned', 'no-handler',
         'page-exact', 'page-short', 'page-offset-invalid', 'page-boundary-short',
         'max-exact', 'max-short', 'ordinary-cross-core', 'table-local', 'table-cross-core',
         'table-short-contiguous', 'sg-residual')
WITNESSES = ('short-one', 'payload-only', 'page-short', 'max-short')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def macro(text, name):
    matches = re.findall(r'^#define ' + re.escape(name) + r'\s+[^\n]+$', text, re.M)
    require(len(matches) == 1, 'missing/ambiguous macro ' + name)
    return matches[0] + '\n'


def translation(files):
    common = files['exports/nss_cmn.h'].decode()
    api = files['exports/nss_api_if.h'].decode()
    dynamic = files['exports/nss_dynamic_interface.h'].decode()
    declarations = 'typedef uint64_t nss_ptr_t;\n'
    # This unit is explicitly LP64. The complete wire struct retains its guards.
    require('typedef uint64_t nss_ptr_t;' in files['exports/nss_def.h'].decode(), 'LP64 pointer typedef drift')
    for kind, name in (('enum', 'nss_cmn_response'), ('struct', 'nss_cmn_msg')):
        declarations += EXTRACT.structure(common, name, kind)
    declarations += EXTRACT.function(common, 'nss_cmn_get_msg_len')
    names = ('NSS_MAX_DEVICE_INTERFACES', 'NSS_MAX_NET_INTERFACES', 'NSS_MAX_PHYSICAL_INTERFACES',
             'NSS_MAX_VIRTUAL_INTERFACES', 'NSS_MAX_TUNNEL_INTERFACES', 'NSS_MAX_SPECIAL_INTERFACES',
             'NSS_PHYSICAL_IF_START', 'NSS_VIRTUAL_IF_START', 'NSS_TUNNEL_IF_START',
             'NSS_DYNAMIC_IF_START', 'NSS_SPECIAL_IF_START', 'NSS_IPV4_RX_INTERFACE', 'NSS_IPV6_RX_INTERFACE')
    declarations += ''.join(macro(api, name) for name in names)
    declarations += macro(dynamic, 'NSS_MAX_DYNAMIC_INTERFACES')
    declarations += macro(files['nss_tx_rx_common.h'].decode(), 'NSS_HLOS_MESSAGE_VERSION')
    for version in ('4', '6'):
        declarations += EXTRACT.structure(files[f'exports/nss_ipv{version}.h'].decode(),
                                          f'nss_ipv{version}_message_types', 'enum')
    table = files['nss_conn_table.c'].decode()
    classifier = EXTRACT.structure(table, 'nss_conn_family')
    classifier += EXTRACT.function(table, 'nss_conn_family')
    classifier += EXTRACT.function(table, 'nss_conn_table_message')
    status = EXTRACT.function(files['nss_core.c'].decode(), 'nss_core_handle_nss_status_pkt')
    template = (HERE / 'fixture.c').read_text()
    for marker, text in (('/* @wire */', declarations), ('/* @classifier */', classifier), ('/* @status */', status)):
        require(template.count(marker) == 1, 'fixture insertion marker')
        template = template.replace(marker, text)
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cc', default='clang')
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.is_relative_to(HERE), 'generated evidence must be outside tests')
    output.mkdir(parents=True, exist_ok=False)
    records = []

    def run(command, cwd, data=None):
        command = list(map(str, command))
        process = subprocess.run(command, cwd=cwd, input=data, capture_output=True, timeout=90,
                                 env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'})
        row = {'argv': command, 'cwd': str(cwd), 'rc': process.returncode,
               'stdout': process.stdout.decode(errors='replace'), 'stderr': process.stderr.decode(errors='replace')}
        records.append(row)
        with (output / 'commands.jsonl').open('a') as handle:
            handle.write(json.dumps(row) + '\n')
        return process

    def git(cwd, *command):
        process = run(['git', *command], cwd)
        require(process.returncode == 0, 'git failure: ' + str(command))
        return process.stdout

    require(git(args.upstream, 'rev-parse', PIN + '^{commit}').decode().strip() == PIN, 'vendor pin unavailable')
    recipe = git(SOURCE, 'show', BASE + ':' + PACKAGE + '/Makefile')
    versions = re.findall(rb'^PKG_SOURCE_VERSION:=([0-9a-f]{7,40})$', recipe, re.M)
    require(len(versions) == 1 and
            git(args.upstream, 'rev-parse', versions[0].decode() + '^{commit}').decode().strip() == PIN,
            'source recipe abbreviated vendor pin must resolve exactly')
    require((SOURCE / PACKAGE / 'Makefile').read_bytes() == recipe.replace(b'PKG_RELEASE:=30\n', b'PKG_RELEASE:=31\n'),
            'only expected package release change allowed')
    scratch = output / 'replay-work'
    scratch.mkdir()
    git(scratch, 'init', '-q')
    for name in FILES:
        target = scratch / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(args.upstream, 'show', PIN + ':' + name))
    paths = git(SOURCE, 'ls-tree', '-r', '--name-only', BASE, PACKAGE + '/patches').decode().splitlines()
    require(set((SOURCE / PACKAGE / 'patches').glob('*.patch')) == {SOURCE / path for path in paths} | {SOURCE / PATCH},
            'expected B12 patch set plus 056 only')
    replay = []
    for path in paths:
        data = git(SOURCE, 'show', BASE + ':' + path)
        require((SOURCE / path).read_bytes() == data, 'old patch changed: ' + path)
        wanted = tuple(name for name in ('nss_core.c', 'nss_conn_table.c')
                       if ('+++ b/' + name + '\n').encode() in data)
        if not wanted:
            continue
        for mode in ('check', 'apply'):
            process = run(['git', 'apply', '--verbose', *(['--check'] if mode == 'check' else []),
                           *['--include=' + name for name in wanted], '-'], scratch, data)
            require(process.returncode == 0, 'patch replay failed: ' + path)
            for name in wanted:
                require((name + '...').encode() in process.stderr or
                        ('to ' + name + ' cleanly').encode() in process.stderr,
                        'target not named in apply evidence: ' + name)
        replay.append({'path': path, 'sha256': sha(data), 'selected_paths': wanted})
    baseline = {name: (scratch / name).read_bytes() for name in (*FILES, 'nss_conn_table.c')}
    require(sha(baseline['nss_core.c']) == '2ffd9f7c12cf21a77b5413b85ffccb0669dab35bd9122c07c5580b0c011f2680',
            'B12 core differs from independent review')
    data = (SOURCE / PATCH).read_bytes()
    for mode in ('check', 'apply'):
        process = run(['git', 'apply', '--verbose', *(['--check'] if mode == 'check' else []), '-'], scratch, data)
        require(process.returncode == 0, 'new patch replay failed')
    candidate = {name: (scratch / name).read_bytes() for name in (*FILES, 'nss_conn_table.c')}
    old = b'if (header.len > nbuf->len) {'
    new = b'if (nss_cmn_get_msg_len(&header) > nbuf->len) {'
    require(baseline['nss_core.c'].count(old) == 1, 'unique length condition required')
    expected = dict(baseline)
    expected['nss_core.c'] = baseline['nss_core.c'].replace(old, new)
    require(candidate == expected, 'only total-length condition may change')
    # Keep the B12 postimage separate from the candidate scratch directory.
    for label, files in (('baseline', baseline), ('candidate', candidate)):
        for name, content in files.items():
            target = output / label / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    identity = {'source': BASE, 'vendor': PIN, 'replay': replay, 'patch': PATCH, 'patch_sha256': sha(data),
                'baseline': {name: sha(content) for name, content in baseline.items()},
                'candidate': {name: sha(content) for name, content in candidate.items()},
                'test_assets': {name: sha((HERE / name).read_bytes()) for name in ('run.py', 'fixture.c')},
                'extractor_sha256': sha(Path(EXTRACT.__file__).read_bytes())}
    (output / 'INPUTS.json').write_text(json.dumps(identity, indent=2) + '\n')
    run([args.cc, '--version'], output)
    outcomes = []

    def execute(label, files, cases, expected_fail=()):
        unit = output / (label + '.c')
        unit.write_text(translation(files))
        binary = output / (label + '.host')
        process = run([args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', unit, '-o', binary], output)
        require(process.returncode == 0 and not process.stderr, 'clean C compile required: ' + label)
        for case in cases:
            process = run([binary, case], output)
            failed = case in expected_fail
            expected_line = ('RX_FAIL ' + case + ' dispatch-count') if failed else ('RX_PASS ' + case)
            matched = (process.returncode == (86 if failed else 0) and
                       process.stdout.decode().splitlines() == [expected_line] and not process.stderr)
            outcomes.append({'variant': label, 'case': case, 'rc': process.returncode,
                             'expected_line': expected_line, 'matched': matched})
            require(matched, 'runtime result mismatch: ' + label + '/' + case)

    execute('baseline', baseline, CASES, WITNESSES)
    execute('candidate', candidate, CASES)
    for label, before, after, witness in (
        ('payload-only', new, old, 'short-one'),
        ('reject-equal', b'nss_cmn_get_msg_len(&header) > nbuf->len',
         b'nss_cmn_get_msg_len(&header) >= nbuf->len', 'exact-linear'),
        ('subtract-header', b'nss_cmn_get_msg_len(&header) > nbuf->len',
         b'nss_cmn_get_msg_len(&header) > nbuf->len + sizeof(header)', 'payload-only'),
        ('require-equal', b'nss_cmn_get_msg_len(&header) > nbuf->len',
         b'nss_cmn_get_msg_len(&header) != nbuf->len', 'padded-linear'),
        ('require-linear-header', b'\tunsigned int contiguous;\n\tuint32_t nss_if;\n',
         b'\tunsigned int contiguous;\n\tuint32_t nss_if;\n\n\tif (skb_headlen(nbuf) < sizeof(header))\n\t\treturn;\n',
         'page-exact'),
    ):
        mutated = dict(candidate)
        require(mutated['nss_core.c'].count(before) == 1, 'unique source mutation required')
        mutated['nss_core.c'] = mutated['nss_core.c'].replace(before, after)
        execute('mutation-' + label, mutated, (witness,), (witness,))
    report = {'status': 'PASS_HOST_TRANSPORT_LENGTH_ONLY', 'cases_per_input': len(CASES),
              'baseline_exact_failures': list(WITNESSES), 'candidate_cases': len(CASES),
              'exact_runtime_mutations': 5, 'outcomes': outcomes,
              'limits': ['No target compile or real skb/kernel API execution',
                         'SG residual forwards to header-only sink; not a safe payload parser proof',
                         'No handler per-type minima/count, firmware owner or DMA retirement proof',
                         'No sanitizer, concurrency, device or performance acceptance']}
    (output / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('outcomes',)}, indent=2))


if __name__ == '__main__':
    main()
