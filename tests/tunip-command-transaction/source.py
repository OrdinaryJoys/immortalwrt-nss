"""Fixed clients26 -> clients27 source admission and complete-body extraction."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACKAGE = REPO / 'package/qca-nss/qca-nss-clients'
OLD_PROFILE = REPO / 'tests/nss-command-inputs/profile.json'
OLD_PROFILE_SHA = '8c371cd531866c8c9268021a54798b1327f818254ca573611913366755349e3b'
RELATIVE = 'tunipip6/nss_connmgr_tunipip6_sysctl.c'
PATCH = '027-tunipip6-command-errors-and-netdev-ownership.patch'
PIN = '51be82d43ef85079f78aa163d014223b05baa6a2'
NAMES = ('nss_tunipip6_data_parser', 'nss_tunipip6_cmd_procfs_add_maprule',
         'nss_tunipip6_cmd_procfs_del_maprule', 'nss_tunipip6_cmd_procfs_flush_fmr_rule',
         'nss_tunipip6_cmd_procfs_enable_frag_id')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        need(not p.is_symlink(), 'SYMLINK_INPUT')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return result


def invhash(items):
    return sha(json.dumps(items, sort_keys=True, separators=(',', ':')).encode())


def partition(root):
    code, metadata = inventory(root), {}
    for name in list(code):
        if name == 'version.date':
            need(re.fullmatch(rb'[0-9]{1,19}\n', (root/name).read_bytes()), 'VERSION_DATE')
        elif re.fullmatch(r'\.prepared_[0-9a-f]{32}_[0-9a-f]{32}', name):
            need(not (root/name).read_bytes() and not any(n.startswith('.prepared_') for n in metadata), 'PREPARED_STAMP')
        else:
            continue
        metadata[name] = code.pop(name)
    return code, metadata


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def profile():
    need(sha(OLD_PROFILE.read_bytes()) == OLD_PROFILE_SHA, 'FROZEN26_PROFILE')
    result = json.loads((HERE/'profile.json').read_text())
    need(result['pin'] == PIN and result['baseline_inventory_sha256'] ==
         'eca9bd5f9f893e6d817a456e54a054ddb774e1d30d1bec55347e7912c55c61d1', 'FIXED_BASELINE')
    return result


def check_inputs():
    p = profile()
    old = json.loads(OLD_PROFILE.read_text())
    expected = dict(old['clients']['patches'], **{PATCH: p['patch_sha256']})
    actual = {f.name: sha(f.read_bytes()) for f in sorted((PACKAGE/'patches').glob('*.patch'))}
    need(actual == expected and len(actual) == 27, 'EXACT_27_PATCH_INVENTORY')
    for name, digest in p['helper_inputs'].items():
        need(sha((REPO/name).read_bytes()) == digest, 'FIXED_HELPER_INPUT')
    recipe = (PACKAGE/'Makefile').read_text()
    version = re.search(r'^PKG_SOURCE_VERSION:=(\S+)$', recipe, re.M).group(1)
    release = re.search(r'^PKG_RELEASE:=(\S+)$', recipe, re.M).group(1)
    normalized = re.sub(r'^PKG_RELEASE:=\S+$', 'PKG_RELEASE:=REVIEWED_RELEASE_ONLY', recipe, flags=re.M)
    need(PIN.startswith(version) and release in p['allowed_releases'] and
         sha(normalized.encode()) == p['recipe_without_release_sha256'], 'FIXED_RECIPE')
    return p, actual


def check_tree(tree, baseline=False):
    p, _ = check_inputs()
    code, metadata = partition(tree)
    key = 'baseline_inventory_sha256' if baseline else 'candidate_inventory_sha256'
    need(len(code) == 298 and invhash(code) == p[key], 'FIXED_' + ('BASELINE' if baseline else 'CANDIDATE') + '_TREE')
    return metadata


def render(tree, baseline=False):
    check_tree(tree, baseline)
    extract = module('tunip_exact_extract', REPO/'tests/nss-dp-containment/extract_prepared_c.py')
    raw = (tree/RELATIVE).read_text()
    names = NAMES if baseline else ('nss_tunipip6_sysctl_errno',) + NAMES
    bodies, provenance = {}, {}
    for name in names:
        body = extract.function(raw, name)
        bodies[name] = body
        provenance[name] = {'path': RELATIVE, 'line': raw[:raw.index(body)].count('\n')+1,
                            'sha256': sha(body.encode()), 'coverage': 'COMPLETE_ACTUAL_BODY'}
    public = (tree/'exports/nss_connmgr_tunipip6.h').read_text()
    def one(pattern, text):
        found = re.findall(pattern, text, re.M | re.S)
        need(len(found) == 1, 'UNIQUE_TYPE: ' + pattern)
        return found[0]
    definitions = [one(r'^#define '+name+r'[^\n]*', raw) for name in
                   ('MAX_PROC_SIZE', 'MAX_IPV4_PREFIX_LEN', 'MAX_IPV6_PREFIX_LEN',
                    'MAX_PSID_OFFSET_LEN', 'NETDEV_STR_LEN', 'PREFIX_STR_LEN')]
    definitions += [one(r'enum nss_tunipip6_sysctl_mode\s*\{[^{}]*\};', raw),
                    one(r'enum nss_connmgr_tunipip6_err_codes\s*\{[^{}]*\};', public),
                    one(r'typedef enum nss_connmgr_tunipip6_maprule_type\s*\{[^{}]*\}[^;]*;', public),
                    one(r'struct nss_connmgr_tunipip6_maprule_cfg\s*\{[^{}]*\};', public)]
    for name in ('add_maprule', 'del_maprule', 'flush_fmr_rule'):
        definitions.append(one(r'enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_'+name+r'\([^;]*\);', public))
    return bodies, '\n\n'.join(definitions)+'\n', provenance


def prepare(output):
    need(not output.exists(), 'FRESH_OUTPUT')
    output.mkdir(parents=True)
    p, patches = check_inputs()
    report = {'status': 'INCOMPLETE', 'qualification': 'TEXT_ONLY_NO_BUILD', 'patches': []}
    inputs = {str(f): sha(f.read_bytes()) for f in
              [Path(__file__), HERE/'profile.json', OLD_PROFILE, PACKAGE/'Makefile',
               *sorted((PACKAGE/'patches').glob('*.patch')),
               *(REPO/n for n in p['helper_inputs'])]}
    try:
        cache = Path('/Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-nss-clients-source')
        pin = subprocess.check_output(['git', '-C', str(cache), 'rev-parse', PIN+'^{commit}'], text=True).strip()
        need(pin == PIN, 'VENDOR_PIN')
        archive = subprocess.check_output(['git', '-C', str(cache), 'archive', '--format=tar', pin])
        need(sha(archive) == p['archive_sha256'], 'VENDOR_ARCHIVE')
        baseline = output/'baseline'; baseline.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                name = Path(member.name)
                need(not name.is_absolute() and '..' not in name.parts and
                     (member.isfile() or member.isdir()), 'ARCHIVE_MEMBER')
                dst = baseline/name
                if member.isdir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(tar.extractfile(member).read())
        context = module('tunip_patch_context', REPO/'tests/edma_patch_context.py')
        saved = output/'patches'; saved.mkdir()
        def apply(name, tree):
            raw = (PACKAGE/'patches'/name).read_bytes(); (saved/name).write_bytes(raw)
            exception = None
            try:
                expected, detail = context.inspect_patch(tree, raw)
            except ValueError as e:
                need(name in ('005-qdisc-and-traffic-control.patch', '023-igs-ifb-find-reference.patch'), 'UNWAIVED_CONTEXT: '+name)
                expected, detail, exception = None, None, str(e)
            command = [shutil.which('gpatch') or 'patch', '--batch', '--forward', '--fuzz=0', '-p1']
            run = subprocess.run(command, cwd=tree, input=raw, capture_output=True, timeout=60)
            (output/(name+'.stdout')).write_bytes(run.stdout)
            (output/(name+'.stderr')).write_bytes(run.stderr)
            need(run.returncode == 0 and not run.stderr and
                 not re.search(rb'offset|fuzz|FAILED|reject|malformed', run.stdout, re.I), 'EXACT_PATCH: '+name)
            if expected is not None:
                context.verify_applied(tree, expected)
            report['patches'].append({'name': name, 'sha256': sha(raw), 'command': command,
                                      'context': detail, 'historical_context_exception': exception,
                                      'returncode': run.returncode})
        for name in patches:
            if name != PATCH:
                apply(name, baseline)
        check_tree(baseline, True)
        candidate = output/'clients'; shutil.copytree(baseline, candidate)
        apply(PATCH, candidate)
        check_tree(candidate)
        check_inputs()
        need({f.name: sha(f.read_bytes()) for f in saved.glob('*.patch')} == patches, 'SAVED_PATCH_INVENTORY')
        need(all(sha(Path(n).read_bytes()) == h for n, h in inputs.items()), 'PREPARE_INPUT_DRIFT')
        report.update(status='PASS_EXACT_NEW027_TEXT_ONLY', pin=pin, archive_sha256=sha(archive),
                      baseline=inventory(baseline), candidate=inventory(candidate),
                      inputs=inputs, saved_patches=patches)
    except Exception as e:
        report['error'] = str(e)
    (output/'RESULTS.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'error') if k in report}))
    return 0 if report['status'] == 'PASS_EXACT_NEW027_TEXT_ONLY' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-output', required=True, type=Path)
    sys.exit(prepare(parser.parse_args().prepare_output))
