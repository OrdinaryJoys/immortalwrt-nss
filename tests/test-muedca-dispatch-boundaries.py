#!/usr/bin/env python3
"""Offline MU boundary/dispatch characterization; no usable MU wire protocol."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SUPPORT = HERE / 'muedca-dispatch-boundaries'
spec = importlib.util.spec_from_file_location('muedca_source', SUPPORT / 'source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
ROOT = Path('/Volumes/FX-MD87/Review-AX6/audits/20261030/core-risk-phase2')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def execute(cmd, prefix, env):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, env=env, timeout=90)
    prefix.with_suffix('.stdout').write_bytes(p.stdout)
    prefix.with_suffix('.stderr').write_bytes(p.stderr)
    prefix.with_suffix('.json').write_text(json.dumps({'argv': [str(x) for x in cmd],
        'returncode': p.returncode, 'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(),
        'stderr_sha256': hashlib.sha256(p.stderr).hexdigest()}, indent=2)+'\n')
    return p


def mutate(text, old, new):
    require(text.count(old) == 1, 'mutant anchor not unique: ' + old)
    return text.replace(old, new, 1)


MUTANTS = [
    ('capacity-for-extent', 'memcpy(&h, bytes, sizeof(h));',
     'memcpy(&h, bytes, sizeof(h)); received=h.nlmsg_len;', 'MD01-received-not-capacity', None),
    ('accept-short-IE', 'if (len != 16) return false;',
     'if (len != 15 && len != 16) return false;', 'MD02-IE-exact-length', None),
    ('ignore-IE-prefix', 'if (ie[0] != WLAN_EID_EXTENSION || ie[1] != 14 ||\n        ie[2] != WLAN_EID_EXT_HE_MU_EDCA_PARAMS) return false;',
     'if (false) return false;', 'MD02-IE-prefix', None),
    ('duplicate-last-wins', 'if (seen[type]) return false;',
     'if (false) return false;', 'MD02-duplicate-IE', None),
    ('oversize-id', 'if (n != sizeof(value)) return false;',
     '', 'MD02-identity-width', 'identity-u32'),
    ('nested-flag', 'a.nla_type != type || type == 0',
     'type == 0', 'MD02-nested-flag', None),
    ('ambiguous-identity', 'identities <= 1', 'identities <= 2', 'MD02-conflicting-identity', None),
    ('zero-IFINDEX', 'if (type == NL80211_ATTR_IFINDEX && (!value || value > INT_MAX)) return false;',
     'if (type == NL80211_ATTR_IFINDEX && value > INT_MAX) return false;', 'MD02-zero-identity', None),
    ('AC-offset', 'memcpy(out->params.he_mu_ac_be_param, ie+4, 3);',
     'memcpy(out->params.he_mu_ac_be_param, ie+3, 3);', 'MD02-AC-mapping', None),
    ('canonical-first-eligible', 'struct hostapd_data *canonical = iface->bss[0];',
     'struct hostapd_data *canonical = iface->bss[0]; for(size_t z=0;z<iface->num_bss;z++) if(eligible(iface->bss[z])) { canonical=iface->bss[z]; break; }',
     'MD05-actual-bss0-canonical', None),
    ('primary-only-eligibility', 'for (size_t i=0; i<iface->num_bss; i++) if (eligible(iface->bss[i])) {',
     'for (size_t i=0; i<1; i++) if (eligible(iface->bss[i])) {', 'MD05-actual-bss0-canonical', None),
    ('ignore-HE', 'h->started && h->beacon_set_done && hostapd_is_he_enabled(h)',
     'h->started && h->beacon_set_done', 'MD05-all-BSS-eligibility', None),
    ('double-shared-count', '((mu->he_qos_info+1)&0xf)',
     '((mu->he_qos_info+2)&0xf)', 'MD06-secondary-eligible-count', None),
    ('clobber-high-count-bits', '(mu->he_qos_info & 0xf0)',
     '0', 'MD06-secondary-eligible-count', None),
    ('WMM-primary-only', 'iface->bss[i]->parameter_set_count++;',
     'iface->bss[0]->parameter_set_count++;', 'MD06-secondary-eligible-count', None),
    ('no-iface-dedup', 'if (found) continue;',
     'if (false) continue;', 'MD05-offwire-one-owner-per-iface', None),
    ('baseline-broadcast-beacon-break', 'if (iface->bss[i]->beacon_set_done && iface->bss[i]->started &&',
     'if (iface->bss[i]->beacon_set_done &&', 'MD07-real-started-beacon-filter', None),
    ('drop-supp-default', 'unknown_events++;', '(void)0;', 'MD09-real-supp-default-projection', None),
    ('radio-missing-WIPHY', 'if (ok) *out=temporary;',
     'if (!tb[NL80211_ATTR_WIPHY] && !tb[NL80211_ATTR_IFINDEX] && !tb[NL80211_ATTR_WDEV]) ok=true;\n    if (ok) *out=temporary;',
     'MD02-radio-needs-WIPHY', None),
    ('radio-foreign-WIPHY', 'nla_get_u32(tb[NL80211_ATTR_WIPHY])==expected_wiphy;',
     'true;', 'MD02-radio-foreign', None),
    ('suppress-real-regulatory-count', 'hapd->parameter_set_count++;\n\t\t /* Incrementing MU-EDCA',
     '/* lost WMM count */\n\t\t /* Incrementing MU-EDCA', 'MD07-reg-change-extra-original-count', None),
    ('bypass-real-CSA-gate', 'if (hapd->csa_in_progress) {',
     'if (false) {', 'MD07-real-gates-no-rollback', None),
    ('old-candidate-rejects-WIPHY0', 'if (type == NL80211_ATTR_WIPHY && value >= INT_MAX) return false;',
     'if (type == NL80211_ATTR_WIPHY && (!value || value >= INT_MAX)) return false;', 'MD02-WIPHY0-typed-positive', None),
    ('accept-unallocated-WIPHY-INTMAX', 'if (type == NL80211_ATTR_WIPHY && value >= INT_MAX) return false;',
     'if (type == NL80211_ATTR_WIPHY && value > INT_MAX) return false;', 'MD02-WIPHY-allocator-bound', None),
    ('ignore-canonical-observation', 'if (canonical_count!=1) return false;',
     'if (false) return false;', 'MD05-missing-duplicate-foreign-unscoped-owner-reject', None),
    ('accept-foreign-radio-AP-ctx', 'if (iface_id<0 || (u32)model_iface_wiphy[iface_id]!=binding->wiphy) return false;',
     'if (iface_id<0) return false;', 'MD05-missing-duplicate-foreign-unscoped-owner-reject', None),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--inputs', type=Path, default=ROOT / 'MUEDCA-DISPATCH-inputs-r1')
    ap.add_argument('--gcc', default='/opt/homebrew/bin/gcc-16')
    ap.add_argument('--clang', default='/usr/bin/clang')
    args = ap.parse_args()
    out = args.output.resolve()
    require(out.parent == ROOT and out.name.startswith('MUEDCA-DISPATCH-'), 'output scope')
    require(not out.exists(), 'fresh output required')
    out.mkdir()
    owned = [Path(__file__).resolve()] + sorted(p for p in SUPPORT.rglob('*') if p.is_file()
                                                and '__pycache__' not in p.parts)
    identities = {str(p): digest(p) for p in owned}
    (out / 'SCRIPT-IDENTITY.json').write_text(json.dumps(identities, indent=2)+'\n')
    result = {'status': 'INCOMPLETE', 'wire_ready': False, 'wire_status': 'BLOCKED_UNASSIGNED',
              'production_modified': False, 'BE_MLO': 'UNSUPPORTED', 'runs': [], 'negative_controls': []}
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=0',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    try:
        inputs = source.prepare(out, args.inputs / 'libnl-tiny-2025.12.02~40493a65.tar.zst', args.inputs)
        fragments = source.c_sources(out)
        template = (SUPPORT / 'fixture.c').read_text()
        c = template
        ax_probe = fragments.pop('ax_probe')
        probe = out / 'AXoff-header-compatibility.c'
        probe.write_text(template.split('/* @headers@ */')[0] + ax_probe + '\n')
        for name, value in fragments.items():
            c = mutate(c, '/* @'+name+'@ */', value)
        require('/* @' not in c, 'unexpanded C marker')
        positive = out / 'positive.c'
        positive.write_text(c)
        result['prepared'] = {'selected_files': 38, 'additional_support_headers_sources': 7,
            'patches': 373, 'archives': 2, 'recipes': 2, 'libnl_recipe': 1,
            'selected38_offsets': inputs['selected38_offsets'], 'additional_support_offsets': inputs['additional_support_offsets'],
            'full303_replay': False, 'fuzz': 0, 'INPUTS_sha256': digest(out / 'INPUTS.json')}
        common = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                  '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter',
                  '-Wno-sign-compare', '-Wno-misleading-indentation', '-Wno-unused-but-set-variable']
        for label, compiler, extra in [('gcc', args.gcc, []),
              ('clang', args.clang, ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            require(shutil.which(compiler), 'missing compiler ' + compiler)
            version = execute([compiler, '--version'], out / (label+'-version'), env)
            require(version.returncode == 0 and not version.stderr, 'compiler version diagnostics')
            result.setdefault('compilers', {})[label] = version.stdout.decode().splitlines()[0]
            for variant, defines in [('AXon', ['-DCONFIG_IEEE80211AX']), ('AXoff-route-projection', [])]:
                binary = out / (label+'-'+variant)
                p = execute([compiler]+common+extra+defines+[positive, '-o', binary],
                            out / (label+'-'+variant+'-compile'), env)
                require(p.returncode == 0 and not p.stdout and not p.stderr, 'positive compile diagnostic '+label+' '+variant)
                p = execute([binary], out / (label+'-'+variant+'-positive'), env)
                require(p.returncode == 0 and not p.stderr and re.fullmatch(
                    rb'PASS_OFFWIRE cases=\d+ checks=\d+ wire_ready=false BE_MLO=UNSUPPORTED\n', p.stdout),
                    'positive runtime '+label+' '+variant)
                result['runs'].append({'compiler': label, 'variant': variant, 'trace': p.stdout.decode().strip(),
                                       'binary_sha256': digest(binary)})
                p = execute([binary, 'parser-tail'], out / (label+'-'+variant+'-tail'), env)
                require(p.returncode == 0 and p.stdout == b'CHARACTERIZED:libnl-tail-return-success\n' and
                        p.stderr == b'netlink: 1 bytes leftover after parsing attributes.\n', 'original parser tail characterization')
                p = execute([binary, 'semantic-canary'], out / (label+'-'+variant+'-semantic-canary'), env)
                require(p.returncode == 86 and p.stdout == b'ASSERT:semantic-canary\n' and not p.stderr, 'semantic oracle canary')
                p = execute([binary, 'runtime-canary'], out / (label+'-'+variant+'-runtime-canary'), env)
                require(p.returncode == 97 and not p.stdout and not p.stderr, 'runtime anomaly must not qualify')
            p = execute([compiler]+common+['-DCONFIG_IEEE80211AX', '-fsyntax-only', probe],
                        out / (label+'-real-AXon-header-compile'), env)
            require(p.returncode == 0 and not p.stdout and not p.stderr, 'real AXon header probe')
            p = execute([compiler]+common+['-fsyntax-only', probe],
                        out / (label+'-real-AXoff-header-compile'), env)
            diagnostics = p.stderr.decode()
            errors = [line for line in diagnostics.splitlines() if 'error:' in line]
            require(p.returncode != 0 and not p.stdout and errors and all('he_mu_edca' in line and
                ('has no member named' in line or 'no member named' in line) for line in errors) and
                'warning:' not in diagnostics, 'AXoff bounded incompatibility must have only exact missing HE member errors')
            result.setdefault('AXoff_real_header_characterization', []).append({'compiler': label,
                'status': 'BLOCKED_EXISTING_UNGUARDED_AP_WMM_MEMBER_ACCESS', 'error_count': len(errors),
                'runtime_negative': False, 'whole_package_build': False})
            for name, old, new, assertion, special in MUTANTS:
                if special == 'identity-u32':
                    old = 'if (n != sizeof(value)) return false;\n            memcpy(&value, payload, sizeof(value));\n            if (type == NL80211_ATTR_IFINDEX'
                    new = 'if (n < sizeof(value)) return false;\n            memcpy(&value, payload, sizeof(value));\n            if (type == NL80211_ATTR_IFINDEX'
                mutant = out / (label+'-mutant-'+name+'.c')
                mutant.write_text(mutate(c, old, new))
                binary = mutant.with_suffix('')
                p = execute([compiler]+common+extra+['-DCONFIG_IEEE80211AX', mutant, '-o', binary],
                            out / (label+'-mutant-'+name+'-compile'), env)
                require(p.returncode == 0 and not p.stdout and not p.stderr, 'mutant compile is NOT semantic rejection: '+name)
                p = execute([binary], out / (label+'-mutant-'+name+'-run'), env)
                require(p.returncode == 86 and p.stdout == ('ASSERT:'+assertion+'\n').encode() and not p.stderr,
                        'not exact runtime semantic negative '+label+' '+name)
                result['negative_controls'].append({'compiler': label, 'name': name, 'assertion': assertion,
                    'c_sha256': digest(mutant), 'binary_sha256': digest(binary), 'returncode': 86})
        for path, expected in {**inputs['live_inputs'], **identities}.items():
            require(digest(Path(path)) == expected, 'postrun source/test drift '+path)
        result['status'] = 'PASS_OFFWIRE_ONLY'
        result['frozen_test_sha256'] = identities
        result['limits'] = ['No MU wire command, alias, kernel emission, or usable end-to-end protocol',
            'nm_size is capacity; explicit received extent front adapter remains a production prerequisite',
            'Stock BE-off projections and host OS leaves; not whole daemon/kernel ABI or live sockets',
            'Clang ASan+UBSan only; LeakSanitizer unavailable on this macOS host and explicitly off',
            'Canonical/eligibility/counter rules are TEST oracle only, not approved production policy',
            'Real AXoff header probe fails on existing unguarded AP/WMM HE field accesses; AXoff route projection is NOT package compatibility',
            'Selected38 has27 offsets; additional support source offsets separately counted; not full303 zero-offset replay',
            'Stable single-thread caller lifetime required; null/topology rejection is not concurrent teardown safety']
    except Exception as e:
        result['failure'] = str(e)
        raise
    finally:
        (out / 'RESULTS.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'output': str(out), 'status': result['status'], 'runs': result['runs'],
                      'negative_controls': len(result['negative_controls']), 'wire_ready': False}))


if __name__ == '__main__':
    main()
