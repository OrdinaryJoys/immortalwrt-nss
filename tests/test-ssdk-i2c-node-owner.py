#!/usr/bin/env python3
"""Actual SSDK I2C registration helper; OF/bus/adapter APIs are ownership models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'dp_extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)

PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t a_uint32_t;
struct device_node { unsigned refs; };
struct device { int id; };
struct i2c_adapter { struct device dev; unsigned refs; };
struct mii_bus { const char *name; bool allocated, registered; };
enum { MIDO_I2C_QCOM = 7 };
#define SFP_I2C_BUS "sfp-i2c"
#define SSDK_ERROR(...) ((void)0)
static struct device_node node, port;
static struct i2c_adapter adapter;
static struct mii_bus bus;
static unsigned external_refs, node_gets, node_puts, lookups, allocations, registrations, frees;
static unsigned checks;
static int fail_stage;
static const char *case_name;
static void demand(bool condition, const char *reason)
{
    if (!condition) {
        fprintf(stderr, "FAIL:%s:%s\n", case_name, reason);
        exit(86);
    }
}
static struct device_node *of_parse_phandle(struct device_node *p, const char *name, int index)
{
    demand(p == &port && !strcmp(name, "i2c-bus") && !index, "lookup-identity");
    if (fail_stage == 0) return NULL;
    node_gets++; node.refs++; return &node;
}
static void of_node_put(struct device_node *p)
{
    demand(p == &node && node.refs > external_refs, "node-reference-underflow");
    node_puts++; node.refs--;
}
static struct i2c_adapter *of_find_i2c_adapter_by_node(struct device_node *p)
{
    demand(p == &node && node.refs == external_refs + 1, "adapter-node-live");
    lookups++;
    if (fail_stage == 1) return NULL;
    adapter.refs++; return &adapter;
}
/* Typed substitutes preserve the locked vendor call shape, not its unknown internals. */
static struct mii_bus *mdio_i2c_alloc(struct device *parent, struct i2c_adapter *adpt, int protocol)
{
    demand(parent == &adapter.dev && adpt == &adapter && adapter.refs == 1 &&
        protocol == MIDO_I2C_QCOM, "allocator-identity");
    allocations++;
    if (fail_stage == 2) return NULL;
    bus.allocated = true; return &bus;
}
static int of_mdiobus_register(struct mii_bus *b, struct device_node *p)
{
    demand(p == &node && node.refs == external_refs + 1, "node-live-through-register");
    demand(b == &bus && b->allocated && !b->registered &&
        b->name && !strcmp(b->name, SFP_I2C_BUS), "register-identity");
    registrations++;
    if (fail_stage == 3) return -5;
    b->registered = true; return 0;
}
static void mdiobus_free(struct mii_bus *b)
{
    demand(b == &bus && b->allocated && !b->registered, "free-only-unpublished-bus");
    frees++; b->allocated = false;
}
'''

MAIN = r'''
static void scenario(const char *name, int failure, unsigned foreign, unsigned id)
{
    case_name = name; fail_stage = failure; external_refs = foreign;
    node.refs = foreign; port.refs = 17; adapter = (struct i2c_adapter){ .dev.id = 23 };
    bus = (struct mii_bus){0};
    node_gets = node_puts = lookups = allocations = registrations = frees = 0;
    struct mii_bus *result = ssdk_mdio_i2c_bus_register(id, &port);
    demand(node.refs == foreign && node_gets == node_puts && node_gets == (unsigned)(failure != 0),
        "node-balance");
    demand(port.refs == 17 && adapter.dev.id == 23 &&
        adapter.refs == (unsigned)(failure >= 2), "foreign-owner-preserved");
    demand(lookups == (unsigned)(failure >= 1) && allocations == (unsigned)(failure >= 2) &&
        registrations == (unsigned)(failure >= 3), "stage-order");
    demand(frees == (unsigned)(failure == 3) && bus.allocated == (failure == 4) &&
        bus.registered == (failure == 4) && result == (failure == 4 ? &bus : NULL),
        "bus-result-and-rollback");
    /* adapter.refs remains open: this test does not invent provider retirement. */
    checks++;
}
int main(int argc, char **argv)
{
    const char *names[] = { "no-node", "no-adapter", "alloc-failure", "register-failure", "success" };
    if (argc > 2) return 2;
    if (argc == 2) {
        bool found = false;
        for (int f = 0; f < 5; f++)
            if (!strcmp(argv[1], names[f])) { scenario(names[f], f, 0, 0); found = true; }
        if (!found) return 2;
    } else {
        for (int f = 0; f < 5; f++)
        for (unsigned foreign = 0; foreign < 3; foreign++)
        for (unsigned id = 0; id < 3; id++)
            scenario(names[f], f, foreign, id);
    }
    printf("{\"scenarios\":%u,\"failures\":0,\"provider_retirement_unverified\":true}\n", checks);
    return 0;
}
'''


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


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
    path = args.prepared / 'src/init/ssdk_dts.c'
    raw = path.read_bytes()
    helper = extract.function(raw.decode(), 'ssdk_mdio_i2c_bus_register')
    baseline = extract.function((args.baseline / 'src/init/ssdk_dts.c').read_text(),
                                'ssdk_mdio_i2c_bus_register')
    records = []

    def run(label, body, witness=None, reason=None):
        c = args.output / (label + '.c')
        c.write_text(PREFIX + body + MAIN)
        command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-parameter']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [str(c), '-o', str(c.with_suffix('.host'))]
        result = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '.compile.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.compile.stderr')).write_bytes(result.stderr)
        require(result.returncode == 0 and not result.stdout and not result.stderr,
                'compile must be clean: ' + label)
        result = subprocess.run([str(c.with_suffix('.host'))] + ([witness] if witness else []),
                                capture_output=True, timeout=30)
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        if witness:
            require(result.returncode == 86 and not result.stdout and result.stderr ==
                    f'FAIL:{witness}:{reason}\n'.encode(), 'not exact runtime rejection: ' + label)
            detail = {'witness': witness, 'reason': reason, 'semantic_rejection': True}
        else:
            require(result.returncode == 0 and not result.stderr, 'execution failed: ' + label)
            detail = json.loads(result.stdout)
            require(detail == {'scenarios': 45, 'failures': 0,
                               'provider_retirement_unverified': True}, 'incomplete positive matrix')
        records.append({'label': label, 'command': command, 'returncode': result.returncode,
                        'c_sha256': hashlib.sha256(c.read_bytes()).hexdigest(), **detail})

    run('candidate', helper)
    run('baseline', baseline, 'success', 'node-live-through-register')
    mutations = [
        ('early-put', '\tret = of_mdiobus_register(mdio_i2c, i2c_node);',
         '\tof_node_put(i2c_node);\n\tret = of_mdiobus_register(mdio_i2c, i2c_node);',
         'success', 'node-live-through-register'),
        ('adapter-leak', '\t\tSSDK_ERROR("i2c adpt was not found\\n");\n\t\tof_node_put(i2c_node);',
         '\t\tSSDK_ERROR("i2c adpt was not found\\n");', 'no-adapter', 'node-balance'),
        ('alloc-leak', '\t\tSSDK_ERROR("mdio_i2c bus alloc failed\\n");\n\t\tof_node_put(i2c_node);',
         '\t\tSSDK_ERROR("mdio_i2c bus alloc failed\\n");', 'alloc-failure', 'node-balance'),
        ('register-leak', '\tret = of_mdiobus_register(mdio_i2c, i2c_node);\n\tof_node_put(i2c_node);',
         '\tret = of_mdiobus_register(mdio_i2c, i2c_node);', 'register-failure', 'node-balance'),
        ('success-leak', '\tret = of_mdiobus_register(mdio_i2c, i2c_node);\n\tof_node_put(i2c_node);',
         '\tret = of_mdiobus_register(mdio_i2c, i2c_node);\n\tif (ret < 0) of_node_put(i2c_node);',
         'success', 'node-balance'),
        ('double-put', '\tret = of_mdiobus_register(mdio_i2c, i2c_node);\n\tof_node_put(i2c_node);',
         '\tret = of_mdiobus_register(mdio_i2c, i2c_node);\n\tof_node_put(i2c_node);\n\tof_node_put(i2c_node);',
         'success', 'node-reference-underflow'),
        ('bus-leak', '\t\tmdiobus_free(mdio_i2c);', '\t\tif (false) mdiobus_free(mdio_i2c);',
         'register-failure', 'bus-result-and-rollback'),
        ('foreign-bus-free', '\treturn mdio_i2c;', '\tmdiobus_free(mdio_i2c);\n\treturn mdio_i2c;',
         'success', 'free-only-unpublished-bus'),
    ]
    for label, before, after, witness, reason in mutations:
        run('mutant-' + label, replace_once(helper, before, after), witness, reason)
    require(path.read_bytes() == raw, 'prepared source drift')
    report = {'qualification': 'HOST_ACTUAL_HELPER_NOT_PROVIDER_OR_HARDWARE_RETIREMENT',
              'source_sha256': hashlib.sha256(raw).hexdigest(), 'records': records}
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_scenarios': 45, 'exact_runtime_mutants': 8,
                      'baseline_reproduced': True, 'report': str(args.output / 'RESULTS.json')}))


if __name__ == '__main__':
    main()
