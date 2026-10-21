#!/usr/bin/env python3
"""Actual QCOM getter/tables/types; transport and device wrapper are models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', ROOT / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared', type=Path)
p.add_argument('--ssdk', type=Path, required=True)
p.add_argument('--baseline', type=Path)
p.add_argument('--cc', default='cc')
p.add_argument('--sanitize', action='store_true')
p.add_argument('--mutations', action='store_true')
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
relative = 'hal/gmac_ops/qcom/qcom_if.c'
text = (args.prepared / relative).read_text()
header = (args.ssdk / 'include/fal/fal_mib.h').read_text()
mib = re.search(r'typedef\s+struct\s*\{([^}]+)\}\s*fal_mib_counter_t;', header)
if not mib or re.search(r'\ba_uint32_t\b', mib.group(1)):
    raise ValueError('expected paired all-u64 SSDK MIB type')
start = text.index('#define QCOM_STAT(')
end = text.index('/*\n * Array of strings describing private flag names', start)
tables = text[start:end]
body = extract.function(text, 'qcom_get_eth_stats')
prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t a_uint64_t;
#define ETH_GSTRING_LEN 32
#define NR_CPUS 4
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
'''
models = r'''
struct nss_gmac_hal_dev {unsigned unused;};
struct qcom_hal_dev {struct nss_gmac_hal_dev base; fal_mib_counter_t stats;};
static fal_mib_counter_t sample;
static bool read_error;
static unsigned checks, failures;
static void check(bool ok) {checks++; if (!ok) failures++;}
static int qcom_get_mib_stats(struct nss_gmac_hal_dev *d) {
    if (read_error) return -1;
    ((struct qcom_hal_dev *)d)->stats = sample;
    return 0;
}
#define QCOM_STATS_LEN ARRAY_SIZE(qcom_gstrings_stats)
#define QCOM_MIB_STATS_LEN ARRAY_SIZE(qcom_gstrings_mib_stats)
'''
main = r'''
int main(void) {
    const uint64_t seeds[] = {0, 17, UINT32_MAX, UINT64_C(1)<<32,
        UINT64_C(0x200000017), UINT64_C(1)<<63, UINT64_MAX-256};
    struct qcom_hal_dev dev = {0};
    struct nss_dp_gmac_stats sw = {};
    struct {uint64_t before, data[QCOM_STATS_LEN+QCOM_MIB_STATS_LEN], after;} out;
    check(QCOM_MIB_STATS_LEN == 42);
#ifdef NSS_DP_EDMA_V2
    check(QCOM_STATS_LEN == 20);
#else
    check(QCOM_STATS_LEN == 0);
#endif
    for (unsigned s = 0; s < ARRAY_SIZE(seeds); s++) {
        uint64_t expected[QCOM_MIB_STATS_LEN];
        memset(&sample, 0, sizeof(sample));
        for (unsigned i = 0; i < QCOM_MIB_STATS_LEN; i++) {
            unsigned offset = qcom_gstrings_mib_stats[i].stat_offset;
            check(offset % sizeof(uint64_t) == 0 && offset+sizeof(uint64_t) <= sizeof(sample));
            expected[i] = seeds[s] + (s == 2 || s == 3 ? 0 : i);
            memcpy((uint8_t *)&sample+offset, &expected[i], sizeof(uint64_t));
        }
        for (unsigned i = 0; i < QCOM_STATS_LEN; i++) {
            uint64_t v = UINT64_C(0x500000000)+i;
            unsigned offset = qcom_gstrings_stats[i].stat_offset;
            check(offset+sizeof(v) <= sizeof(sw));
            memcpy((uint8_t *)&sw+offset, &v, sizeof(v));
        }
        memset(&out, 0xa5, sizeof(out));
        check(qcom_get_eth_stats(&dev.base, out.data, &sw) == 0);
        for (unsigned i = 0; i < QCOM_MIB_STATS_LEN; i++)
            check(out.data[QCOM_STATS_LEN+i] == expected[i]);
        for (unsigned i = 0; i < QCOM_STATS_LEN; i++)
            check(out.data[i] == UINT64_C(0x500000000)+i);
        check(out.before == UINT64_C(0xa5a5a5a5a5a5a5a5));
        check(out.after == UINT64_C(0xa5a5a5a5a5a5a5a5));
    }
    read_error = true;
    memset(&out, 0xa5, sizeof(out));
    check(qcom_get_eth_stats(&dev.base, out.data, &sw) == -1);
    for (unsigned i = 0; i < QCOM_MIB_STATS_LEN; i++)
        check(out.data[QCOM_STATS_LEN+i] == UINT64_C(0xa5a5a5a5a5a5a5a5));
    check(out.before == UINT64_C(0xa5a5a5a5a5a5a5a5));
    check(out.after == UINT64_C(0xa5a5a5a5a5a5a5a5));
    printf("{\"checks\":%u,\"failures\":%u,\"mib_entries\":%zu,\"data_entries\":%zu}\n",
        checks, failures, QCOM_MIB_STATS_LEN, QCOM_STATS_LEN);
    return failures ? 1 : 0;
}
'''
variants = [('candidate', body, True)]
if args.baseline:
    variants.append(('baseline', extract.function((args.baseline / relative).read_text(), 'qcom_get_eth_stats'), False))
if args.mutations:
    replacements = [
        ('u32-truncation', 'i = QCOM_STATS_LEN + i_mib;\n\t\tdata[i] = *(uint64_t *)p;',
         'i = QCOM_STATS_LEN + i_mib;\n\t\tdata[i] = *(uint32_t *)p;', 1),
        ('missing-last', 'i_mib < QCOM_MIB_STATS_LEN', 'i_mib + 1 < QCOM_MIB_STATS_LEN', 1),
        ('wrong-output-offset', 'i = QCOM_STATS_LEN + i_mib;', 'i = i_mib;', 1),
        ('ignored-read-error', 'if (qcom_get_mib_stats(nghd))', 'if (qcom_get_mib_stats(nghd) && false)', 1),
    ]
    for label, old, new, count in replacements:
        if body.count(old) != count:
            raise ValueError('mutation context drift: ' + label)
        variants.append((label, body.replace(old, new), False))
records = []
for soc in ('ipq807x', 'ipq60xx', 'ipq95xx', 'ipq53xx', 'ipq54xx'):
    arch = (args.prepared / f'hal/soc_ops/{soc}/nss_{soc}.h').read_text()
    types = extract.structure(arch, 'nss_dp_hal_gmac_stats')
    api = extract.structure((args.prepared / 'exports/nss_dp_api_if.h').read_text(), 'nss_dp_gmac_stats')
    defines = '#define NSS_DP_EDMA_V2 1\n' if soc in ('ipq95xx', 'ipq53xx', 'ipq54xx') else ''
    for label, function, must_pass in variants:
        if label == 'wrong-output-offset' and soc in ('ipq807x', 'ipq60xx'):
            continue  # The v1 dataplane prefix is empty; this mutation is identical there.
        name = soc + '-' + label
        c = args.output / (name + '.c')
        c.write_text(prefix + defines + mib.group() + '\n' + types + api + tables + models + function + main)
        command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror',
            '-Wno-sign-compare', '-Wno-type-limits']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [str(c), '-o', str(c.with_suffix(''))]
        result = subprocess.run(command, capture_output=True)
        (args.output / (name + '-compile.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise SystemExit(result.stderr.decode())
        result = subprocess.run([str(c.with_suffix(''))], capture_output=True)
        (args.output / (name + '.stdout')).write_bytes(result.stdout)
        (args.output / (name + '.stderr')).write_bytes(result.stderr)
        data = json.loads(result.stdout)
        if result.stderr or result.returncode != (0 if must_pass else 1) or (data['failures'] == 0) != must_pass:
            raise SystemExit('unexpected result: ' + name)
        records.append(dict(label=name, command=command, source_sha256=hashlib.sha256(c.read_bytes()).hexdigest(),
                            expected_failure=not must_pass, **data))
result = dict(results=records, prepared=str(args.prepared),
    getter_sha256=hashlib.sha256(body.encode()).hexdigest(),
    tables_sha256=hashlib.sha256(tables.encode()).hexdigest(),
    ssdk_mib_sha256=hashlib.sha256(mib.group().encode()).hexdigest(),
    scope='actual getter, tables and public layouts; modeled transport/device, not target or runtime')
(args.output / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps([dict(label=r['label'], checks=r['checks'], failures=r['failures']) for r in records], indent=2))
