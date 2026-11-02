#!/usr/bin/env python3
"""Actual default/legacy functions; check OF leases separately from borrowed providers."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load('dp_extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
types = load('ssdk_port_source', HERE / 'ssdk-phy-port-admission/source.py')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def replace_once(text, before, after):
    require(text.count(before) == 1, 'ambiguous mutation: ' + before)
    return text.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    path = 'src/init/ssdk_dts.c'
    new_raw, old_raw = (args.prepared / path).read_bytes(), (args.baseline / path).read_bytes()
    names = ['ssdk_dt_get_mdio_node', 'ssdk_dt_parse_default_mdio_bus', 'ssdk_dt_parse_mdio']
    current = {name: extract.function(new_raw.decode(), name) for name in names}
    previous = {name: extract.function(old_raw.decode(), name) for name in names}
    public_types = types.extract(args.prepared)['types']
    require(public_types == types.extract(args.baseline)['types'], 'public type drift')
    template = (HERE / 'ssdk-mdio-node-fixture.c').read_text().replace('/* @TYPES@ */', public_types)
    old = '\n'.join(previous.values())
    for name in names:
        old = re.sub(r'\b' + name + r'\b', 'baseline_' + name, old)
    records = []

    def run(label, functions, *, kernel, probe=None, reason=None, baseline=False):
        body = old + '\n' + '\n'.join(functions.values())
        code = template.replace('/* @FUNCTIONS@ */', body)
        require(not re.search(r'@[A-Z_]+@', code), 'unfilled C placeholder')
        c = args.output / (label + '.c')
        c.write_text(code)
        command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-DTEST_KERNEL=' + str(kernel)]
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [str(c), '-o', str(c.with_suffix('.host'))]
        result = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '.compile.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.compile.stderr')).write_bytes(result.stderr)
        require(result.returncode == 0 and not result.stdout and not result.stderr, 'clean compile: ' + label)
        command_run = [str(c.with_suffix('.host'))] + (['old' if baseline else 'new', probe] if probe else [])
        result = subprocess.run(command_run, capture_output=True, timeout=30)
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        if reason:
            require(result.returncode == 86 and not result.stdout and
                    result.stderr == f'MDIO_NODE:{probe}:{reason}\n'.encode(), 'exact semantic rejection: ' + label)
            detail = {'witness': probe, 'reason': reason, 'semantic_rejection': True}
        else:
            require(result.returncode == 0 and not result.stderr, 'execution: ' + label)
            detail = json.loads(result.stdout)
            require(detail == {'scenarios': 1254, 'failures': 0,
                               'provider_retirement_unverified': True}, 'matrix coverage')
        records.append({'label': label, 'kernel': kernel, 'compile_command': command,
                        'run_command': command_run, 'returncode': result.returncode,
                        'c_sha256': hashlib.sha256(c.read_bytes()).hexdigest(), **detail})

    profiles = {'6.18': (6 << 16) | (18 << 8) | 38, '6.1': (6 << 16) | (1 << 8),
                '5.15': (5 << 16) | (15 << 8)}
    for label, kernel in profiles.items():
        run('candidate-' + label, current, kernel=kernel)
    for probe, reason in [('explicit', 'node-lease-balance'), ('fallback-missing', 'node-lease-balance'),
                          ('legacy-break', 'node-lease-balance')]:
        run('baseline-' + probe, current, kernel=profiles['6.18'], probe=probe, reason=reason, baseline=True)

    default, legacy = names[1:]
    mutations = [
        ('explicit-leak', default, '\t\t\tof_node_put(mdio_node);', '', 'explicit', 'node-lease-balance'),
        ('explicit-early-put', default, '\t\t\trv = ssdk_miibus_add(dev_id, of_mdio_find_bus(mdio_node),',
         '\t\t\tof_node_put(mdio_node);\n\t\t\trv = ssdk_miibus_add(dev_id, of_mdio_find_bus(mdio_node),',
         'explicit', 'node-use-after-local-put'),
        ('fallback-leak', default, '\tmdio_plat = of_find_device_by_node(mdio_node);\n\tof_node_put(mdio_node);',
         '\tmdio_plat = of_find_device_by_node(mdio_node);', 'fallback-missing', 'node-lease-balance'),
        ('fallback-early-put', default, '\tmdio_plat = of_find_device_by_node(mdio_node);',
         '\tof_node_put(mdio_node);\n\tmdio_plat = of_find_device_by_node(mdio_node);',
         'fallback', 'node-use-after-local-put'),
        ('wrong-resource', default, '\tmdio_plat = of_find_device_by_node(mdio_node);\n\tof_node_put(mdio_node);',
         '\tmdio_plat = of_find_device_by_node(mdio_node);\n\tof_node_put(mdio_node);\n\tif (mdio_plat) put_device(&mdio_plat->dev);',
         'fallback', 'provider-not-held'),
        ('foreign-switch-put', default, '\t\t\tof_node_put(mdio_node);', '\t\t\tof_node_put(switch_node);',
         'explicit', 'foreign-or-double-node-put'),
        ('legacy-parent-leak', legacy, '\tof_node_put(mdio_node);', '', 'legacy-empty', 'node-lease-balance'),
        ('legacy-break-child-leak', legacy, '\t\tof_node_put(child);', '', 'legacy-break', 'child-lease-balance'),
        ('legacy-child-double-put', legacy, '\t\tof_node_put(child);',
         '\t\tof_node_put(child);\n\t\tof_node_put(child);', 'legacy-break', 'foreign-or-double-node-put'),
        ('error-swallowed', default, '\t\t\treturn rv;', '\t\t\treturn SW_OK;', 'add-failure', 'return-value'),
    ]
    for label, name, before, after, probe, reason in mutations:
        changed = dict(current)
        changed[name] = replace_once(changed[name], before, after)
        run('mutant-' + label, changed, kernel=profiles['6.18'], probe=probe, reason=reason)
    require((args.prepared / path).read_bytes() == new_raw and (args.baseline / path).read_bytes() == old_raw,
            'source changed during verification')
    report = {'qualification': 'HOST_NODE_LEASE_AND_UNCHANGED_OBSERVABLES_NOT_KERNEL_OR_PROVIDER_DRAIN',
              'baseline_sha256': hashlib.sha256(old_raw).hexdigest(),
              'candidate_sha256': hashlib.sha256(new_raw).hexdigest(), 'records': records}
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_scenarios_per_profile': 1254, 'profiles': 3,
                      'baseline_witnesses': 3, 'exact_runtime_mutants': len(mutations),
                      'report': str(args.output / 'RESULTS.json')}))


if __name__ == '__main__':
    main()
