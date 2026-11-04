#!/usr/bin/env python3
"""Historical pre-049 ownership witness, never current-driver qualification.

The retirement substitutes record frees and endpoint shutdown; they do not free
host storage or pretend that RCU, callers or hardware have been drained.
"""
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

HISTORICAL_FUNCTIONS = {
    'hsl_phy_api_ops_get': '4438c617d2f28e8dc36c75a38f3ae0079e625b26d3bfa2f2685d481c0b1878ac',
    'ssdk_phy_driver_cleanup': '6c3b8328d7723d979fad46dfe8fc229080f1bd5a479a82ea8e4ff52fa4bafc84',
    'hsl_dev_cleanup_core': '5758b6f3f059a23057124b1c416b2a6a83625628bb24b94c5016d026266f0b0c',
}


def admit_hashes(actual):
    if actual != HISTORICAL_FUNCTIONS:
        raise RuntimeError('historical SSDK36/pre-049 functions required; use current PHY049/SSDK051 suites for current code')

PHY = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef unsigned a_uint32_t;
typedef int sw_error_t;
typedef unsigned phy_type_t;
enum { SW_MAX_NR_DEV = 2, MAX_PHY_CHIP = 1, SW_OK = 0 };
typedef struct { unsigned identity; } hsl_phy_ops_t;
typedef struct { phy_type_t phy_type[1]; } phy_info_t;
struct phy_driver { unsigned port_bmp[2]; hsl_phy_ops_t *phy_ops;
    void (*exit)(unsigned, unsigned); };
static struct phy_driver ssdk_phy_driver[1];
static phy_info_t info[2], *phy_info[2];
static hsl_phy_ops_t ops;
static unsigned retired_ops, retired_info[2];
static void require(bool yes) { if (!yes) exit(2); }
static void kfree(void *p)
{
    if (p == &ops) retired_ops++;
    else if (p == &info[0]) retired_info[0]++;
    else if (p == &info[1]) retired_info[1]++;
    else exit(2);
}
'''
PHY_MAIN = r'''
int main(void)
{
    for (unsigned own = 0; own < 2; own++) {
        retired_ops = retired_info[0] = retired_info[1] = 0;
        info[0].phy_type[0] = info[1].phy_type[0] = 0;
        phy_info[0] = &info[0]; phy_info[1] = &info[1];
        ssdk_phy_driver[0] = (struct phy_driver){ .port_bmp = {own, 1}, .phy_ops = &ops };
        hsl_phy_ops_t *reader = hsl_phy_api_ops_get(1, 0);
        require(reader == &ops && !retired_ops);
        require(ssdk_phy_driver_cleanup(0) == SW_OK);
        require(retired_ops == 1 && retired_info[0] == 1 && !retired_info[1] &&
            phy_info[1] == &info[1] && ssdk_phy_driver[0].port_bmp[1] == 1 &&
            hsl_phy_api_ops_get(1, 0) == NULL && reader == &ops);
    }
    puts("{\"status\":\"KNOWN_OPEN_REPRODUCED\",\"witnesses\":2,\"actual_free_modeled\":true}");
    return 0;
}
'''

UK = r'''
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
typedef unsigned a_uint32_t;
typedef int sw_error_t;
enum { SW_OK = 0, SW_BAD_PTR = -1 };
#define UK_IF 1
#define SW_RTN_ON_ERROR(rv) do { if ((rv) != SW_OK) return (rv); } while (0)
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_BAD_PTR; } while (0)
struct cfg { unsigned identity; };
typedef struct { sw_error_t (*dev_clean)(a_uint32_t); } hsl_api_t;
static struct cfg configs[2], *dev_ssdk_cfg[2];
static hsl_api_t api[2];
static bool endpoint_live;
static unsigned freed[2], stopped;
static void require(bool yes) { if (!yes) exit(2); }
static hsl_api_t *hsl_api_ptr_get(unsigned id) { require(id < 2); return &api[id]; }
static void aos_mem_free(void *p)
{
    if (p == &configs[0]) freed[0]++;
    else if (p == &configs[1]) freed[1]++;
    else exit(2);
}
static sw_error_t sw_uk_cleanup(void) { require(endpoint_live); endpoint_live = false; stopped++; return SW_OK; }
'''
UK_MAIN = r'''
int main(void)
{
    endpoint_live = true;
    dev_ssdk_cfg[0] = &configs[0]; dev_ssdk_cfg[1] = &configs[1];
    require(hsl_dev_cleanup_core(0) == SW_OK);
    require(!endpoint_live && stopped == 1 && freed[0] == 1 && !freed[1] &&
        !dev_ssdk_cfg[0] && dev_ssdk_cfg[1] == &configs[1]);
    puts("{\"status\":\"KNOWN_OPEN_REPRODUCED\",\"witnesses\":1,\"profile\":\"UK_IF_WITHOUT_HPPE\"}");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--historical-pre049', action='store_true',
                        help='Explicitly acknowledge this is a frozen historical counterexample')
    args = parser.parse_args()
    if not args.historical_pre049:
        parser.error('--historical-pre049 is required; this does not test current driver ownership')
    paths = {'phy': args.prepared / 'src/hsl/phy/hsl_phy.c',
             'uk': args.prepared / 'src/hsl/hsl_dev.c'}
    raw = {key: path.read_bytes() for key, path in paths.items()}
    functions = {name: extract.function(raw['phy' if name != 'hsl_dev_cleanup_core' else 'uk'].decode(), name)
                 for name in HISTORICAL_FUNCTIONS}
    admit_hashes({name: hashlib.sha256(body.encode()).hexdigest() for name, body in functions.items()})
    args.output.mkdir(parents=True, exist_ok=False)
    phy = functions['hsl_phy_api_ops_get'] + functions['ssdk_phy_driver_cleanup']
    uk = functions['hsl_dev_cleanup_core']
    report = {'status': 'HISTORICAL_PRE049_WITNESSES_ONLY_NOT_CURRENT_FAULTS',
              'scope': 'THREE_FROZEN_OLD_FUNCTIONS_NOT_CURRENT_SDK_OR_RUNTIME_REACHABILITY',
              'function_contract': HISTORICAL_FUNCTIONS,
              'source_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
              'records': []}
    for label, source in [('phy', PHY + phy + PHY_MAIN), ('uk', UK + uk + UK_MAIN)]:
        c = args.output / (label + '.c')
        c.write_text(source)
        command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   str(c), '-o', str(c.with_suffix('.host'))]
        result = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '.compile.stderr')).write_bytes(result.stderr)
        if result.returncode or result.stdout or result.stderr:
            raise RuntimeError('witness must compile cleanly: ' + label)
        result = subprocess.run([str(c.with_suffix('.host'))], capture_output=True, timeout=30)
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        if result.returncode or result.stderr:
            raise RuntimeError('witness preconditions not reproduced: ' + label)
        record = json.loads(result.stdout)
        if record['status'] != 'KNOWN_OPEN_REPRODUCED' or record['witnesses'] != (2 if label == 'phy' else 1):
            raise RuntimeError('witness classification mismatch')
        report['records'].append({'label': label, 'command': command, **record})
    if any(path.read_bytes() != raw[key] for key, path in paths.items()):
        raise RuntimeError('source drift')
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'witnesses': 3,
                      'report': str(args.output / 'RESULTS.json')}))


if __name__ == '__main__':
    main()
