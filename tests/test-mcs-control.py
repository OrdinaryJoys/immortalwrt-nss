#!/usr/bin/env python3
"""Actual MCS control functions with host transport/list/RCU substitutes only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generate(tree, template, netlink, ip_header, ipv6_header):
    prepared = extract.Prepared(tree)
    api = prepared.read('mc_api.h')
    api = re.sub(r'^#include[^\n]*$', '', api, flags=re.M)
    names = ['mc_ip', 'mc_querier_entry', 'mc_router_port', 'mc_param_pattern',
             'mc_acl_rule_table', 'mc_struct', 'mc_rt_src_list', 'mc_mdb_entry',
             'mc_port_group', 'mc_src_list', 'mc_fdb_group']
    structures = ''.join(prepared.structure('mc_private.h', name) for name in names)
    control = prepared.read('mc_netlink.c')
    boundary = 'int __init mc_netlink_init(void)'
    if control.count(boundary) != 1:
        raise ValueError('missing or ambiguous control translation boundary')
    control = control[:control.index(boundary)]
    control = re.sub(r'^#include[^\n]*$', '', control, flags=re.M)
    source_names = ['mc_stranslate_check_source']
    if re.search(r'^int mc_translate_filter_address\(', prepared.read('mc_forward.c'), re.M):
        source_names.append('mc_translate_filter_address')
    source_names.append('mc_translate_filter_source')
    source_functions = ''.join(prepared.function('mc_forward.c', name) for name in source_names)
    source_functions += ''.join(prepared.function('mc_ecm.c', name) for name in
        ('mc_bridge_if_source_filter', '__mc_bridge_get_ifs', 'mc_bridge_ipv4_get_if'))
    source_functions += '#ifdef MC_SUPPORT_MLD\n' + prepared.function('mc_ecm.c', 'mc_bridge_ipv6_get_if') + '#endif\n'
    generated = template.replace('/* ACTUAL_NETLINK_HEADER */', extract.structure(netlink, 'nlmsghdr')).replace('/* ACTUAL_API */', api).replace(
        '/* ACTUAL_PRIVATE_STRUCTURES */', structures).replace('/* ACTUAL_IP_HEADERS */',
        extract.structure(ip_header, 'iphdr') + extract.structure(ipv6_header, 'ipv6hdr')).replace('/* ACTUAL_FUNCTIONS */', control + source_functions)
    return generated, prepared.manifest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('mutation anchor not unique: ' + old)
    return text.replace(old, new, 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared', type=Path)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cc', required=True)
    p.add_argument('--linux-netlink', type=Path, required=True)
    p.add_argument('--linux-ip-header', type=Path, required=True)
    p.add_argument('--linux-ipv6-header', type=Path, required=True)
    p.add_argument('--sanitize', action='store_true')
    p.add_argument('--mutations', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture_path = HERE / 'mcs-control/host-fixture.c'
    fixture = fixture_path.read_text()
    netlink = args.linux_netlink.read_text()
    candidate, inputs = generate(args.prepared, fixture, netlink, args.linux_ip_header.read_text(), args.linux_ipv6_header.read_text())
    baseline, old_inputs = generate(args.baseline, fixture, netlink, args.linux_ip_header.read_text(), args.linux_ipv6_header.read_text())
    record = {'scope': 'Actual control functions, not complete kernel/module or real netlink/DMA',
              'status': 'RUNNING', 'inputs': inputs, 'baseline_inputs': old_inputs,
              'assets': {str(x): sha(x.read_bytes()) for x in [Path(__file__), fixture_path, args.linux_netlink,
                         args.linux_ip_header, args.linux_ipv6_header, HERE / 'nss-dp-containment/extract_prepared_c.py']},
              'commands': [], 'runs': []}
    env = os.environ.copy()
    flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-sign-compare',
             '-Wno-address-of-packed-member', '-Wno-unused-variable', '-Wno-unused-but-set-variable']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        env['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    record['sanitizer_environment'] = {k: env[k] for k in ['ASAN_OPTIONS', 'UBSAN_OPTIONS'] if k in env}

    def command(argv, label):
        r = subprocess.run([str(x) for x in argv], capture_output=True, text=True, env=env, timeout=90)
        record['commands'].append({'label': label, 'argv': [str(x) for x in argv], 'returncode': r.returncode})
        (args.output / (label + '.stdout')).write_text(r.stdout)
        (args.output / (label + '.stderr')).write_text(r.stderr)
        return r

    def compile_code(code, label, mld, expected_missing_ipv6=False, jiffy_limit=False):
        src = args.output / (label + '.c')
        src.write_text(code)
        binary = args.output / label
        r = command([args.cc] + flags + (['-DMC_SUPPORT_MLD=1'] if mld else []) +
                    (['-DHOST_JIFFY_MAX=1073741822UL'] if jiffy_limit else []) + [src, '-o', binary], label + '-compile')
        if expected_missing_ipv6:
            if not r.returncode or not re.search(r"no member named ['\u2018]ip6|has no member named.*ip6", r.stderr):
                raise ValueError('old MLD-off compile control missed expected ip6 field defect')
            record.setdefault('expected_compile_failures', []).append({'label': label, 'defect': 'old DEL_MDB unguarded IPv6 union member', 'returncode': r.returncode})
            return None
        if r.returncode or r.stderr or r.stdout:
            raise ValueError('compile failed or diagnostics: ' + label)
        return binary

    def run_case(binary, case, label, positive=True, diagnostic=None):
        r = command([binary, case], label)
        if re.search(r'AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:', r.stderr):
            raise ValueError('sanitizer diagnostic cannot count as semantic negative: ' + label)
        if positive:
            data = json.loads(r.stdout)
            if r.returncode or r.stderr or data['failures'] or data['cases'] < 250 or data['checks'] < 1000:
                raise ValueError('positive failure/incomplete suite: ' + label)
        else:
            if r.returncode not in (1, 86) or not diagnostic or diagnostic not in r.stderr:
                raise ValueError('negative missed designated defect: ' + label)
            data = json.loads(r.stdout) if r.stdout else None
        record['runs'].append({'label': label, 'case': case, 'returncode': r.returncode,
                               'positive': positive, 'summary': data, 'expected_diagnostic': diagnostic})

    try:
        compiler = command([args.cc, '--version'], 'compiler-version')
        if compiler.returncode:
            raise ValueError('compiler unavailable')
        record['compiler'] = compiler.stdout.strip()
        for mld in (False, True):
            suffix = 'mld-on' if mld else 'mld-off'
            good = compile_code(candidate, 'candidate-' + suffix, mld)
            run_case(good, 'all', 'candidate-' + suffix)
            limited = compile_code(candidate, 'candidate-jiffy-model-' + suffix, mld, jiffy_limit=True)
            run_case(limited, 'all', 'candidate-jiffy-model-' + suffix)
            old = compile_code(baseline, 'baseline-' + suffix, mld, not mld)
            if mld:
                run_case(old, 'permission', 'baseline-permission-' + suffix, False, 'unprivileged-command-refused')
                run_case(old, 'normal', 'baseline-response-' + suffix, False, 'request-data-unchanged')
                run_case(old, 'acl', 'baseline-ACL-' + suffix, False, 'full-MLD-update-matched-index')
                if not args.sanitize:
                    run_case(old, 'ecm-v4', 'baseline-ECM-' + suffix, False, 'ECM-source-address-and-filter-result')
            if not args.mutations:
                continue
            mutations = [
                ('no-admin', '!netlink_capable(__skb, CAP_NET_ADMIN)', 'false', 'permission', 'unprivileged-command-refused'),
                ('shared-reply', 'skb = skb_copy(__skb, GFP_ATOMIC);', 'skb = skb_clone(__skb, GFP_ATOMIC);', 'normal', 'request-data-unchanged'),
                ('untrusted-portid', 'pid = NETLINK_CB(__skb).portid;', 'pid = nlh->nlmsg_pid;', 'normal', 'trusted-reply-route'),
                ('short-private-header', 'nlmsg_len(nlh) < MC_MSG_HDRLEN', 'false', 'bounds', 'short-frame-rejected'),
                ('no-declared-bound', 'hdr->buf_len > available', 'false', 'bounds', 'declared-payload-bound'),
                ('no-inner-bound', 'entry->dev[j].in_nsrcs > MC_DEF_SRCS_MAX', 'false', 'nested', 'nested-include-count'),
                ('source-index', 'offset < 0 || offset >= MC_DEF_SRCS_MAX', 'offset > MC_DEF_IP6_SIZE', 'nested', 'consumer-source-index-bound'),
                ('event-uninitialized', 'memset(data, 0, MC_MSG_HDRLEN);', '(void)data;', 'output', 'event-private-header-zero'),
                ('MDB-unbounded', 'if (fg->a.nsrcs < 0 || fg->a.nsrcs > MC_DEF_SRCS_MAX ||', 'if (false ||', 'output-count', 'MDB-internal-source-bound'),
                ('overlap-delete', 'memmove(&mc->igmp_acl.patterns[i],', 'memcpy(&mc->igmp_acl.patterns[i],', 'acl', 'overlapping-memcpy'),
                ('interval-overflow', 'mc->membership_interval = (unsigned long)mi->val * HZ;', 'mc->membership_interval = (u32)(mi->val * HZ);', 'domains', 'interval-no-u32-overflow'),
                ('event-zero-set', 'return ((const struct __event_info *)data)->event_pid != 0;', 'return true;', 'event-zero', 'zero-event-destination-rejected'),
                ('event-zero-emit', '!destination || destination == MC_INVALID_PID', 'destination == MC_INVALID_PID', 'event-zero', 'zero-kernel-unicast-forbidden'),
                ('zero-ingress', '!NETLINK_CB(__skb).portid ||', 'false ||', 'zero-ingress', 'zero-ingress-before-capability'),
                ('ECM-capacity-zero', 'if (!max_dst) {', 'if (false) {', 'ecm-capacity', 'ECM-zero-capacity-no-write'),
                ('ECM-internal-source-bound', 'if (fg->a.nsrcs < 0 || fg->a.nsrcs > MC_DEF_SRCS_MAX)\n\t\t\t\tcontinue;',
                 'if (false)\n\t\t\t\tcontinue;', 'ecm-flood', 'ECM-flood-source-bound-and-match'),
            ]
            if mld:
                mutations += [('MLD-wrong-index', 'memcpy(&mc->mld_acl.patterns[i], &pattern, sizeof pattern);',
                               'memcpy(&mc->mld_acl.patterns[mc->mld_acl.pattern_count], &pattern, sizeof pattern);', 'acl', 'full-MLD-update-matched-index')]
                mutations += [('ECM-header-mismatch', 'mc_translate_filter_address(mdb->encap_dev, &mc_source->u, mdb->group.pro)',
                               'mc_translate_filter_source(mdb->encap_dev, &mc_source->u.ip4, mdb->group.pro)', 'ecm-v4', 'ECM-source-address-and-filter-result')]
            for name, before, after, case, diagnostic in mutations:
                mutated = replace_once(candidate, before, after)
                binary = compile_code(mutated, name + '-' + suffix, mld)
                run_case(binary, case, name + '-' + suffix, False, diagnostic)
            if args.sanitize:
                mutated = replace_once(candidate, 'return !memcmp((const u8 *)srcs + offset * sizeof(__be32), source, sizeof(__be32));',
                                       'return *((const __be32 *)srcs + offset) == *(const __be32 *)source;') if not mld else None
                if mutated is not None:
                    binary = compile_code(mutated, 'unaligned-source-' + suffix, mld)
                    r = command([binary, 'source-match'], 'unaligned-source-' + suffix)
                    if not r.returncode or not re.search(r'runtime error: load of misaligned address', r.stderr):
                        raise ValueError('unaligned source sanitizer control missed designated defect')
                    record.setdefault('expected_sanitizer_failures', []).append({'label': 'unaligned-source-' + suffix,
                        'returncode': r.returncode, 'diagnostic': 'runtime error: load of misaligned address',
                        'scope': 'sanitizer negative, not a semantic-negative PASS or real device fault'})
            mutated = replace_once(candidate, 'ticks <= MAX_JIFFY_OFFSET', 'true')
            binary = compile_code(mutated, 'jiffy-limit-bypass-' + suffix, mld, jiffy_limit=True)
            run_case(binary, 'domains', 'jiffy-limit-bypass-' + suffix, False, 'jiffy-limit-and-no-side-effect')
            if mld:
                mutated = replace_once(candidate, 'p = &mc->mld_acl.patterns[0];\n\tfor (i = 0;',
                                       'if (ret < 0) goto out;\n\tp = &mc->mld_acl.patterns[0];\n\tfor (i = 0;')
                mutated = replace_once(mutated, '\n#endif\n\tif (bytes_written)', '\n#endif\nout:\n\tif (bytes_written)')
                binary = compile_code(mutated, 'ACL-needed-short-circuit-' + suffix, mld)
                run_case(binary, 'compatibility', 'ACL-needed-short-circuit-' + suffix, False, 'ACL-total-needed-includes-MLD')
        record['status'] = 'PASS'
    except Exception as error:
        record['status'] = 'FAIL'
        record['error'] = str(error)
        raise
    finally:
        (args.output / 'RESULT.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'runs': len(record['runs']), 'result': str(args.output / 'RESULT.json')}))


if __name__ == '__main__':
    main()
