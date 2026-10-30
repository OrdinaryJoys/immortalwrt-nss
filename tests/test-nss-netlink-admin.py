#!/usr/bin/env python3
"""Host-only actual NSS op tables and Linux 6.18.38 permission control flow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / 'test-nss-netlink-admin-ops.json').read_text())
TARGET_FILES = {'nss_nlqrfs.c', 'nss_nlgre_redir_cmd.c', 'nss_nludp_st.c'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def mask_c(text):
    """Keep offsets and braces while hiding C comments and string contents."""
    out = list(text)
    token = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    for match in token.finditer(text):
        for index in range(match.start(), match.end()):
            if out[index] != '\n':
                out[index] = ' '
    return ''.join(out)


def closing(mask, start):
    depth = 0
    for index in range(start, len(mask)):
        if mask[index] == '{':
            depth += 1
        elif mask[index] == '}':
            depth -= 1
            if not depth:
                return index + 1
    raise ValueError('unclosed C brace')


def function(text, name):
    masked = mask_c(text)
    pattern = re.compile(r'^(?:static\s+)?(?:inline\s+)?(?:int|bool|void)\s+' +
                         re.escape(name) + r'\s*\(', re.M)
    candidates = []
    for match in pattern.finditer(masked):
        end = masked.find(')', match.end())
        if end < 0:
            continue
        brace = end + 1
        while brace < len(masked) and masked[brace].isspace():
            brace += 1
        if brace < len(masked) and masked[brace] == '{':
            candidates.append((match.start(), closing(masked, brace)))
    if len(candidates) != 1:
        raise ValueError('expected one complete function: ' + name)
    begin, end = candidates[0]
    return text[begin:end], begin, end


def declaration(text, pattern):
    masked = mask_c(text)
    hits = list(re.finditer(pattern, masked, re.M))
    if len(hits) != 1:
        raise ValueError('expected one declaration: ' + pattern)
    match = hits[0]
    end = closing(masked, masked.index('{', match.start()))
    semicolon = masked.find(';', end)
    if semicolon < 0 or masked[end:semicolon].strip():
        raise ValueError('expected declaration terminator')
    return text[match.start():semicolon + 1], match.start(), semicolon + 1


def table(text):
    return declaration(text, r'^(?:static\s+)?(?:const\s+)?struct\s+genl_ops\s+\w+\[\]\s*=\s*\{')


def entries(block):
    masked = mask_c(block)
    outer = masked.index('{')
    index = outer + 1
    result = []
    while index < len(masked):
        if masked[index].isspace() or masked[index] == ',':
            index += 1
            continue
        if masked[index] == '}':
            break
        if masked[index] != '{':
            raise ValueError('unexpected op initializer')
        end = closing(masked, index)
        item = masked[index:end]
        fields = {}
        for key in ('cmd', 'doit', 'flags'):
            match = re.search(r'\.' + key + r'\s*=\s*([A-Za-z_]\w*|0)\s*[,}]', item)
            if match:
                fields[key] = match[1]
        if not {'cmd', 'doit'} <= fields.keys():
            raise ValueError('op missing cmd/doit')
        fields.setdefault('flags', '0')
        fields['span'] = (index, end)
        result.append(fields)
        index = end
    return result


class Inputs:
    def __init__(self):
        self.records = {}
        self.extracts = []

    def read(self, path):
        path = Path(path).absolute()
        if any(parent.is_symlink() for parent in (path,) + tuple(path.parents)):
            raise ValueError('symlink input: ' + str(path))
        data = path.read_bytes()
        self.records[str(path)] = digest(data)
        return data.decode('utf-8')

    def take(self, path, text, value, begin, end, kind):
        self.extracts.append({'path': str(path), 'kind': kind,
                              'first_line': text[:begin].count('\n') + 1,
                              'last_line': text[:end].count('\n') + 1,
                              'sha256': digest(value.encode())})
        return value


def source_tables(root, inputs):
    result = []
    for family in POLICY['families']:
        path = root / 'netlink' / family['file']
        text = inputs.read(path)
        block, begin, end = table(text)
        rows = entries(block)
        expected = family['ops']
        if [(x['cmd'], x['doit']) for x in rows] != [(x['cmd'], x['handler']) for x in expected]:
            raise ValueError('actual table differs from complete policy inventory: ' + str(path))
        if not re.search(r'\b' + re.escape(family['table']) + r'\[\]', mask_c(block)):
            raise ValueError('unexpected table name')
        netns = re.findall(r'\.netnsok\s*=\s*(true|false)', mask_c(text))
        if netns != [str(family['netnsok']).lower()]:
            raise ValueError('actual family namespace setting changed')
        inputs.take(path, text, block, begin, end, 'complete genl_ops table')
        result.append((family, path, text, block, rows))
    return result


def verify_scope(candidate, baseline):
    if len(candidate) != 23 or sum(len(x[4]) for x in candidate) != 58:
        raise ValueError('expected 23 actual tables and 58 ops')
    for new, old in zip(candidate, baseline):
        family, path, text, block, rows = new
        restored = text
        for row, policy, before in zip(rows, family['ops'], old[4]):
            required = policy['policy'] in ('new_admin', 'existing_admin')
            if row['flags'] != ('GENL_ADMIN_PERM' if required else '0'):
                raise ValueError('wrong candidate privilege: ' + row['cmd'])
            old_flag = 'GENL_ADMIN_PERM' if policy['policy'] == 'existing_admin' else '0'
            if before['flags'] != old_flag:
                raise ValueError('baseline already changed: ' + before['cmd'])
        if family['file'] in TARGET_FILES:
            restored = text.replace(', .flags = GENL_ADMIN_PERM', '')
        if restored != old[2]:
            raise ValueError('non-authorized source change: ' + str(path))
    return {'new_admin': 18, 'existing_admin': 4, 'stats_noop': 15,
            'unchanged_dormant': 21, 'files_changed': sorted(TARGET_FILES)}


def command_enums(clients, driver, inputs):
    wanted = {op['cmd'] for family in POLICY['families'] for op in family['ops']}
    paths = [clients / 'netlink/include' / ('nss_nl' + name + '_if.h')
             for name in ('gre_redir', 'capwap', 'dtls', 'ipsec', 'oam')]
    paths += [driver / 'exports' / ('nss_' + name + '.h')
              for name in ('ipv4', 'ipv6', 'qrfs', 'udp_st', 'stats_public')]
    blocks, found = [], set()
    for path in paths:
        text = inputs.read(path)
        masked = mask_c(text)
        for match in re.finditer(r'\benum(?:\s+\w+)?\s*\{', masked):
            end = closing(masked, masked.index('{', match.start()))
            block = text[match.start():end] + ';'
            names = {name for name in wanted if re.search(r'\b' + name + r'\b', mask_c(block))}
            if names:
                if names & found:
                    raise ValueError('duplicate command enum')
                found |= names
                blocks.append(inputs.take(path, text, block, match.start(), end, 'actual command enum'))
    if found != wanted:
        raise ValueError('unresolved actual command ids: ' + str(sorted(wanted - found)))
    return '\n\n'.join(blocks)


def kernel_inputs(root, inputs):
    texts = {}
    for relative, expected in POLICY['linux_sha256'].items():
        path = root / relative
        text = inputs.read(path)
        if digest(text.encode()) != expected:
            raise ValueError('wrong exact Linux 6.18.38 input: ' + str(path))
        texts[relative] = text
    uapi = texts['include/uapi/linux/genetlink.h']
    constants = []
    for name in ('GENL_HDRLEN', 'GENL_ADMIN_PERM', 'GENL_UNS_ADMIN_PERM',
                 'GENL_CMD_CAP_DO', 'GENL_CMD_CAP_DUMP'):
        match = re.search(r'^#define\s+' + name + r'\s+[^\n]+', uapi, re.M)
        if not match:
            raise ValueError('missing official constant')
        constants.append(match[0])
    block = declaration(uapi, r'^struct genlmsghdr\s*\{')
    constants.append(inputs.take(root / 'include/uapi/linux/genetlink.h',
                                 uapi, *block, 'actual generic header'))
    header_flags = texts['include/linux/netlink.h']
    block = declaration(header_flags, r'^enum netlink_skb_flags\s*\{')
    constants.append(inputs.take(root / 'include/linux/netlink.h',
                                 header_flags, *block, 'actual netlink skb flags'))
    cap = re.search(r'^#define\s+CAP_NET_ADMIN\s+[^\n]+',
                    texts['include/uapi/linux/capability.h'], re.M)
    if not cap:
        raise ValueError('missing official CAP_NET_ADMIN')
    constants.append(cap[0])
    types = []
    header = texts['include/net/genetlink.h']
    for pattern in (r'^struct genl_ops\s*\{', r'^struct genl_split_ops\s*\{',
                    r'^enum genl_validate_flags\s*\{'):
        block = declaration(header, pattern)
        types.append(inputs.take(root / 'include/net/genetlink.h', header, *block, 'actual op type'))
    bodies = []
    for relative, names in [
        ('net/netlink/af_netlink.c',
         ('__netlink_ns_capable', 'netlink_ns_capable', 'netlink_capable')),
        ('net/netlink/genetlink.c',
         ('genl_op_from_full', 'genl_get_cmd_full', 'genl_cmd_full_to_split', 'genl_family_rcv_msg'))
    ]:
        for name in names:
            text = texts[relative]
            block = function(text, name)
            bodies.append(inputs.take(root / relative, text, *block, 'complete official ' + name))
    return '\n'.join(constants), '\n\n'.join(types), '\n\n'.join(bodies)


def fixture_tables(tables, inputs):
    handlers, blocks, families, rows = [], [], [], []
    index = 0
    for family_index, (family, path, text, block, parsed) in enumerate(tables):
        blocks.append(block)
        families.append('{"%s", %s, sizeof(%s)/sizeof(%s[0]), %s}' %
                        (family['file'], family['table'], family['table'], family['table'],
                         str(family['netnsok']).lower()))
        for row, policy in zip(parsed, family['ops']):
            name = row['doit']
            if policy['policy'] == 'stats':
                body = function(text, name)
                if re.sub(r'\s+', '', mask_c(body[0]).split('{', 1)[1][:-1]) != 'return0;':
                    raise ValueError('stats handler is no longer a noop: ' + name)
                handlers.append(inputs.take(path, text, *body, 'complete actual stats noop'))
            else:
                handlers.append('static int %s(struct sk_buff *s, struct genl_info *i) '
                                '{ (void)s; (void)i; host_effects++; return 0; }' % name)
            policy_id = 1 if policy['policy'] in ('new_admin', 'existing_admin') else (
                2 if policy['policy'] == 'stats' else 0)
            rows.append('{"%s/%s", %u, %s, %s, %u}' %
                        (family['file'], row['cmd'], family_index, row['cmd'], name, policy_id))
            index += 1
    if index != 58:
        raise ValueError('incomplete host rows')
    asserts = ['_Static_assert(%s == %u, "actual cmd id");' % pair
               for pair in POLICY['target_ids'].items()]
    return ('\n'.join(handlers), '\n\n'.join(blocks),
            'static struct host_family families[] = {\n' + ',\n'.join(families) + '\n};\n' +
            'static struct host_row rows[] = {\n' + ',\n'.join(rows) + '\n};\n' + '\n'.join(asserts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clients', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--kernel-inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    out = args.output.absolute()
    repo = HERE.parent
    for parent in (out,) + tuple(out.parents):
        if parent.is_symlink():
            raise ValueError('output symlink')
    roots = [repo, args.clients.resolve(), args.baseline.resolve(),
             args.driver.resolve(), args.kernel_inputs.resolve()]
    if any(out == root or root in out.parents for root in roots):
        raise ValueError('generated output must be outside repository and input trees')
    inputs = Inputs()
    candidate = source_tables(args.clients, inputs)
    baseline = source_tables(args.baseline, inputs)
    scope = verify_scope(candidate, baseline)
    enums = command_enums(args.clients, args.driver, inputs)
    uapi, types, bodies = kernel_inputs(args.kernel_inputs, inputs)
    template = inputs.read(HERE / 'test-nss-netlink-admin.c')
    out.mkdir(parents=True, exist_ok=False)
    commands, runs = [], []

    def save(path, data):
        path.write_bytes(data.encode() if isinstance(data, str) else data)

    def run(label, phase, argv):
        result = subprocess.run(argv, capture_output=True, timeout=120,
                                env=dict(os.environ, LC_ALL='C'))
        stem = out / (label + '-' + phase)
        save(stem.with_suffix('.stdout'), result.stdout)
        save(stem.with_suffix('.stderr'), result.stderr)
        record = {'variant': label, 'phase': phase, 'argv': argv,
                  'returncode': result.returncode, 'stdout_sha256': digest(result.stdout),
                  'stderr_sha256': digest(result.stderr)}
        commands.append(record)
        save(stem.with_suffix('.json'), json.dumps(record, indent=2) + '\n')
        if result.returncode < 0:
            raise ValueError('unexpected signal: ' + label + '/' + phase)
        return result

    flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-parameter', '-Wno-sign-compare']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    version = run('compiler', 'version', [args.cc, '--version'])
    if version.returncode:
        raise ValueError('compiler unavailable')

    def build(label, tables, kernel_bodies):
        directory = out / label
        directory.mkdir()
        handlers, actual_tables, host_rows = fixture_tables(tables, inputs)
        for filename, data in [('host.c', template), ('nss-enums.inc', enums),
                               ('kernel-uapi.inc', uapi), ('kernel-types.inc', types),
                               ('kernel-bodies.inc', kernel_bodies), ('handlers.inc', handlers),
                               ('actual-tables.inc', actual_tables), ('rows.inc', host_rows)]:
            save(directory / filename, data)
        comp = run(label, 'compile', [args.cc] + flags + ['-I', str(directory), '-c',
                   str(directory / 'host.c'), '-o', str(directory / 'host.o')])
        if comp.returncode:
            raise ValueError('unexpected compile failure: ' + label)
        link = run(label, 'link', [args.cc] + flags + [str(directory / 'host.o'),
                   '-o', str(directory / 'host')])
        if link.returncode:
            raise ValueError('unexpected link failure: ' + label)
        return directory / 'host'

    flat = [(family, op) for family in POLICY['families'] for op in family['ops']]
    protected = [i for i, (_, op) in enumerate(flat)
                 if op['policy'] in ('new_admin', 'existing_admin')]

    def check_run(label, binary, expected, mode='none', index=0):
        result = run(label, 'run', [str(binary), mode, str(index)])
        if result.stderr or result.returncode not in (0, 1):
            raise ValueError('unexpected runtime/sanitizer diagnostic: ' + label)
        observed = json.loads(result.stdout)
        if observed['failed_ops'] != expected or bool(observed['failures']) != bool(expected):
            raise ValueError('wrong differential result: ' + label + ': ' + result.stdout.decode())
        if bool(observed['flow_failures']) != bool(expected):
            raise ValueError('control flow was not independently discriminated: ' + label)
        if result.returncode != bool(expected):
            raise ValueError('wrong runtime exit: ' + label)
        runs.append({'variant': label, 'expected_failed_ops': expected, 'observed': observed})

    binary = build('candidate', candidate, bodies)
    check_run('candidate', binary, [])
    original = build('baseline', baseline, bodies)
    new_rows = [i for i, (_, op) in enumerate(flat) if op['policy'] == 'new_admin']
    check_run('baseline', original, new_rows)
    if args.mutations:
        for index, (_, op) in enumerate(flat):
            if op['policy'] in ('new_admin', 'existing_admin'):
                prefix = 'omit-new' if op['policy'] == 'new_admin' else 'omit-existing'
                check_run(prefix + '-' + str(index), binary, [index], 'omit', index)
            elif op['policy'] == 'stats':
                check_run('restrict-stats-' + str(index), binary, [index], 'restrict', index)
        check_run('wrong-userns', binary, [new_rows[0]], 'uns', new_rows[0])
        old = 'if ((op.flags & GENL_ADMIN_PERM)'
        if bodies.count(old) != 1:
            raise ValueError('official permission branch changed')
        bypass = build('bypass-permission', candidate, bodies.replace(
            old, 'if ((0 & GENL_ADMIN_PERM)'))
        check_run('bypass-permission', bypass, protected)
        old = 'op->flags\t\t= full->flags;'
        if bodies.count(old) != 1:
            raise ValueError('official full-to-split flag transfer changed')
        lost = build('lose-op-flags', candidate, bodies.replace(
            old, 'op->flags = 0;'))
        check_run('lose-op-flags', lost, protected)

    summary = {'scope': scope, 'tables': 23, 'ops': 58,
               'sanitizers': args.sanitize, 'compiler': args.cc,
               'commands': commands, 'runtime_results': runs,
               'inputs_sha256': inputs.records, 'extractions': inputs.extracts,
               'compile_count': sum(x['phase'] == 'compile' for x in commands),
               'link_count': sum(x['phase'] == 'link' for x in commands),
               'runtime_count': len(runs), 'all_expected_results_observed': True,
               'boundary': 'Actual NSS tables/enums/stats noops and complete selected official '
                           'Linux functions run as host C. Credentials, headers/attrs, family '
                           'layout and NSS handlers are substitutes; no actual kernel, sockets, '
                           'device, target build or firmware execution.'}
    save(out / 'results.json', json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('scope', 'compile_count', 'link_count',
                                             'runtime_count', 'all_expected_results_observed')}))


if __name__ == '__main__':
    main()
