#!/usr/bin/env python3
"""Complete real PHY parser and dependencies; OF/provider leaves are explicit models."""
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
types = load('ssdk_types', HERE / 'ssdk-phy-port-admission/source.py')


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_once(body, before, after):
    need(body.count(before) == 1, 'ambiguous mutation: ' + before)
    return body.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    relative = 'src/init/ssdk_dts.c'
    raw = (args.prepared / relative).read_bytes()
    old_raw = (args.baseline / relative).read_bytes()
    names = ['ssdk_dt_get_mdio_node', 'ssdk_mdio_i2c_bus_register',
             'ssdk_dt_read_port_values', 'ssdk_dt_parse_phy_info']
    current = {n: extract.function(raw.decode(), n) for n in names}
    previous = {n: extract.function(old_raw.decode(), n) for n in names}
    public = types.extract(args.prepared)['types']
    port_values = extract.structure(raw.decode(), 'ssdk_dt_port_values')
    need(public == types.extract(args.baseline)['types'] and
         port_values == extract.structure(old_raw.decode(), 'ssdk_dt_port_values'), 'type drift')
    template_path = HERE / 'ssdk-phy-node-fixture.c'
    template = template_path.read_text().replace('/* @TYPES@ */', public).replace('/* @PORT_VALUES@ */', port_values)
    assets = {str(p): digest(p.read_bytes()) for p in [Path(__file__), template_path,
              HERE / 'nss-dp-containment/extract_prepared_c.py', HERE / 'ssdk-phy-port-admission/source.py']}

    def definitions(functions, baseline=False):
        text = ''
        for name, body in functions.items():
            if name == 'ssdk_mdio_i2c_bus_register':
                need(len(re.findall(r'\bdev_id\b', body)) == 1,
                     'unused-parameter exception must remain helper-only')
                body = ('#if IS_ENABLED(CONFIG_MDIO_I2C)\n'
                        '#pragma GCC diagnostic push\n'
                        '#pragma GCC diagnostic ignored "-Wunused-parameter"\n' + body +
                        '#pragma GCC diagnostic pop\n#endif\n')
            text += body + '\n'
        if baseline:
            for name in names:
                text = re.sub(r'\b' + name + r'\b', 'baseline_' + name, text)
        return text

    old = definitions(previous, True)
    records = []

    def run(label, body, *, profile, probe=None, reason=None, baseline=False):
        functions = dict(current)
        functions['ssdk_dt_parse_phy_info'] = body
        code = template.replace('/* @FUNCTIONS@ */', old + definitions(functions))
        need(not re.search(r'@[A-Z_]+@', code), 'unfilled placeholder')
        c = args.output / (label + '.c')
        c.write_text(code)
        command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-DTEST_FEATURES=' + str(profile),
                   '-DCONFIG_MDIO_I2C=' + str(profile & 1)]
        if profile & 2:
            command += ['-DIN_PHY_I2C_MODE=1']
        if profile & 4:
            command += ['-DIN_SFP_PHY=1']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [str(c), '-o', str(c.with_suffix('.host'))]
        result = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '.compile.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.compile.stderr')).write_bytes(result.stderr)
        need(result.returncode == 0 and not result.stdout and not result.stderr, 'clean compile: ' + label)
        run_command = [str(c.with_suffix('.host'))] + (['old' if baseline else 'new', probe] if probe else [])
        result = subprocess.run(run_command, capture_output=True, timeout=90)
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        if reason:
            need(result.returncode == 86 and not result.stdout and result.stderr ==
                 f'PHY_NODE:{probe}:{reason}\n'.encode(), 'exact runtime rejection: ' + label)
            detail = {'witness': probe, 'reason': reason, 'semantic_rejection': True}
        else:
            need(result.returncode == 0 and not result.stderr, 'positive run: ' + label)
            detail = json.loads(result.stdout)
            need(detail == {'scenarios': 5288, 'failures': 0, 'feature_profile': profile,
                            'provider_retirement_unverified': True}, 'complete feature matrix')
        records.append({'label': label, 'feature_profile': profile, 'compile_command': command,
                        'run_command': run_command, 'returncode': result.returncode,
                        'c_sha256': digest(c.read_bytes()), **detail})

    body = current['ssdk_dt_parse_phy_info']
    for profile in range(8):
        run('candidate-' + str(profile), body, profile=profile)
    for probe, profile, reason in [('mdio', 0, 'mdio-lease-balance'), ('i2c', 1, 'i2c-lease-balance'),
                                   ('external-failure', 0, 'external-lease-balance')]:
        run('baseline-' + probe, body, profile=profile, probe=probe, reason=reason, baseline=True)
    mutations = [
        ('mdio-normal-leak', '\t\tof_node_put(mdio_node);\n\t\tmdio_node = NULL;',
         '\t\tmdio_node = NULL;', 0, 'mdio', 'mdio-lease-balance'),
        ('i2c-normal-leak', '\t\tof_node_put(i2c_node);\n\t\ti2c_node = NULL;',
         '\t\ti2c_node = NULL;', 1, 'i2c', 'i2c-lease-balance'),
        ('external-normal-leak', '\t\tof_node_put(switch_external_node);\n\t\tswitch_external_node = NULL;',
         '\t\tswitch_external_node = NULL;', 0, 'external', 'external-lease-balance'),
        ('handle-normal-leak', '\t\tof_node_put(netdev_switch_node);\n\t\tnetdev_switch_node = NULL;',
         '\t\tnetdev_switch_node = NULL;', 0, 'handle', 'handle-lease-balance'),
        ('external-error-leak', '\n\tof_node_put(switch_external_node);', '',
         0, 'external-failure', 'external-lease-balance'),
        ('mdio-error-leak', '\tof_node_put(mdio_node);\n\tof_node_put(port_node);',
         '\tof_node_put(port_node);', 3, 'i2c-address-failure', 'mdio-lease-balance'),
        ('i2c-error-leak', '\n\tof_node_put(i2c_node);', '', 3, 'i2c-address-failure', 'i2c-lease-balance'),
        ('mdio-stale-local', '\t\tmdio_node = NULL;', '', 0, 'second-bad-port', 'foreign-or-double-put'),
        ('i2c-stale-local', '\t\ti2c_node = NULL;', '', 1, 'i2c', 'foreign-or-double-put'),
        ('external-stale-local', '\t\tswitch_external_node = NULL;', '', 0, 'external', 'foreign-or-double-put'),
        ('handle-stale-local', '\t\tnetdev_switch_node = NULL;', '', 0, 'handle', 'foreign-or-double-put'),
        ('foreign-switch-put', '\t\tof_node_put(mdio_node);', '\t\tof_node_put(switch_node);',
         0, 'mdio', 'foreign-or-double-put'),
        ('mdio-early-put', '\t\t\tphy_reset_gpio = of_get_named_gpio(mdio_node, "phy-reset-gpio",',
         '\t\t\tof_node_put(mdio_node);\n\t\t\tphy_reset_gpio = of_get_named_gpio(mdio_node, "phy-reset-gpio",',
         0, 'mdio', 'node-use-after-local-put'),
        ('handle-early-put', '\t\t\tif(netdev_switch_node) {',
         '\t\t\tif(netdev_switch_node) {\n\t\t\t\tof_node_put(netdev_switch_node);',
         0, 'handle', 'node-use-after-local-put'),
        ('registered-bus-free', '\t\t\tssdk_miibus_add(dev_id, mdio_i2c, &miibus_index);',
         '\t\t\tssdk_miibus_add(dev_id, mdio_i2c, &miibus_index);\n\t\t\tmdiobus_free(mdio_i2c);',
         1, 'i2c', 'free-owned-unpublished-bus'),
        ('error-swallowed', '\t\t\trv = SW_NO_RESOURCE;', '\t\t\trv = SW_OK;',
         0, 'external-failure', 'return-value'),
        ('published-table-cleared', '\t\tof_node_put(netdev_switch_node);',
         '\t\tif (netdev_switch) memset(netdev_switch, 0, sizeof(*netdev_switch));\n\t\tof_node_put(netdev_switch_node);',
         0, 'handle', 'non-of-state-changed'),
    ]
    for label, before, after, profile, probe, reason in mutations:
        run('mutant-' + label, replace_once(body, before, after), profile=profile, probe=probe, reason=reason)
    need((args.prepared / relative).read_bytes() == raw and (args.baseline / relative).read_bytes() == old_raw,
         'prepared input changed')
    need(all(digest(Path(p).read_bytes()) == h for p, h in assets.items()), 'test asset drift')
    report = {'qualification': 'HOST_TEMPORARY_NODE_LEASES_NOT_SHARED_PROVIDER_OR_ROOT_RETIREMENT',
              'baseline_sha256': digest(old_raw), 'candidate_sha256': digest(raw),
              'assets': assets, 'records': records}
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'feature_profiles': 8, 'scenarios_per_profile': 5288,
                      'old_source_witnesses': 3, 'exact_runtime_mutants': len(mutations),
                      'report': str(args.output / 'RESULTS.json')}))


if __name__ == '__main__':
    main()
