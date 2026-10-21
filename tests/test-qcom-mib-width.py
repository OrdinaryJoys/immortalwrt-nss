#!/usr/bin/env python3
"""Actual QCOM strings/count/getter contract; host transport/device models."""
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
prepared = extract.Prepared(args.prepared)
ssdk = extract.Prepared(args.ssdk)
header = ssdk.read('include/fal/fal_mib.h')
mib = re.search(r'typedef\s+struct\s*\{([^}]+)\}\s*fal_mib_counter_t;', header)
if not mib or re.search(r'\ba_uint32_t\b', mib.group(1)):
    raise ValueError('expected paired all-u64 SSDK MIB type')
function_names = ('qcom_get_strset_count', 'qcom_get_strings', 'qcom_get_eth_stats')


def qcom_contract(tree):
    text = tree.read(relative)
    start = text.index('#define QCOM_STAT(')
    end = text.index('/*\n * qcom_rx_flow_control()', start)
    return text[start:end], {name: tree.function(relative, name) for name in function_names}


tables, functions = qcom_contract(prepared)
body = functions['qcom_get_eth_stats']
prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t a_uint64_t;
/* Linux ethtool ABI constants; no host Linux headers are required. */
enum {ETH_SS_TEST = 0, ETH_SS_STATS = 1, ETH_SS_PRIV_FLAGS = 2};
#define ETH_GSTRING_LEN 32
#define NR_CPUS 4
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
/* Kernel byte strings include u8 arrays; libc strlen uses signed char here. */
static size_t host_byte_strlen(const void *s) {return strlen(s);}
#define strlen host_byte_strlen
'''
models = r'''
struct net_device {unsigned unused;};
struct nss_gmac_hal_dev {struct net_device *netdev;};
struct qcom_hal_dev {struct nss_gmac_hal_dev base; fal_mib_counter_t stats;};
static fal_mib_counter_t sample;
static bool read_error;
static unsigned checks, failures, mib_reads;
static void check(bool ok) {checks++; if (!ok) failures++;}
#define netdev_dbg(dev, ...) ((void)(dev))
static int qcom_get_mib_stats(struct nss_gmac_hal_dev *d) {
    mib_reads++;
    if (read_error) return -1;
    ((struct qcom_hal_dev *)d)->stats = sample;
    return 0;
}
'''
main = r'''
#define STAT_ENTRIES (QCOM_STATS_LEN + QCOM_MIB_STATS_LEN)
#define CANARY UINT64_C(0xa5a5a5a5a5a5a5a5)
struct string_output {
    uint8_t before[ETH_GSTRING_LEN];
    uint8_t data[STAT_ENTRIES][ETH_GSTRING_LEN];
    uint8_t after[ETH_GSTRING_LEN];
};
static bool bytes_are(const void *buffer, size_t length, uint8_t value) {
    const uint8_t *p = buffer;
    for (size_t i = 0; i < length; i++)
        if (p[i] != value) return false;
    return true;
}
static void check_string_set(struct nss_gmac_hal_dev *dev, int32_t sset,
                            size_t expected_count, struct string_output *out) {
    int32_t count = qcom_get_strset_count(dev, sset);
    check(count == (int32_t)expected_count);
    memset(out, 0xa5, sizeof(*out));
    /* Model the ethtool caller's zeroed slots, but only for the advertised count. */
    if (count >= 0 && (size_t)count <= STAT_ENTRIES)
        memset(out->data, 0, (size_t)count * ETH_GSTRING_LEN);
    check(qcom_get_strings(dev, sset, &out->data[0][0]) == 0);
    for (size_t i = 0; i < expected_count; i++) {
        const char *name;
        if (sset == ETH_SS_PRIV_FLAGS)
            name = qcom_strings_priv_flags[i];
        else if (i < QCOM_STATS_LEN)
            name = (const char *)qcom_gstrings_stats[i].stat_string;
        else
            name = (const char *)qcom_gstrings_mib_stats[i-QCOM_STATS_LEN].stat_string;
        size_t length = strlen(name);
        check(length > 0 && length < ETH_GSTRING_LEN);
        if (length >= ETH_GSTRING_LEN) continue;
        check(memcmp(out->data[i], name, length) == 0);
        check(bytes_are(out->data[i]+length, ETH_GSTRING_LEN-length, 0));
        for (size_t j = 0; j < i; j++)
            check(memcmp(out->data[i], out->data[j], ETH_GSTRING_LEN) != 0);
    }
    if (count >= 0 && (size_t)count <= STAT_ENTRIES)
        check(bytes_are((const uint8_t *)out->data+(size_t)count*ETH_GSTRING_LEN,
                        (STAT_ENTRIES-(size_t)count)*ETH_GSTRING_LEN, 0xa5));
    check(bytes_are(out->before, sizeof(out->before), 0xa5));
    check(bytes_are(out->after, sizeof(out->after), 0xa5));
}
static void check_named_payload(const struct string_output *names, const uint64_t *data,
                                const uint64_t *expected_mib) {
    /* Join actual returned names to the source table, not to a modeled HAL callback. */
    for (size_t i = 0; i < STAT_ENTRIES; i++) {
        unsigned matches = 0;
        for (size_t j = 0; j < QCOM_STATS_LEN; j++)
            if (memcmp(names->data[i], qcom_gstrings_stats[j].stat_string, ETH_GSTRING_LEN) == 0) {
                matches++;
                check(data[i] == UINT64_C(0x500000000)+j);
            }
        for (size_t j = 0; j < QCOM_MIB_STATS_LEN; j++)
            if (memcmp(names->data[i], qcom_gstrings_mib_stats[j].stat_string, ETH_GSTRING_LEN) == 0) {
                matches++;
                check(data[i] == expected_mib[j]);
            }
        check(matches == 1);
    }
}
int main(void) {
    const uint64_t seeds[] = {0, 17, UINT32_MAX, UINT64_C(1)<<32,
        UINT64_C(0x200000017), UINT64_C(1)<<63, UINT64_MAX-256};
    const int32_t unknown_sets[] = {INT32_MIN, -1, ETH_SS_TEST,
        ETH_SS_PRIV_FLAGS+1, 31, INT32_MAX};
    struct net_device netdev = {0};
    struct qcom_hal_dev dev = {0};
    struct nss_dp_gmac_stats sw = {};
    struct string_output names, private_names, unknown;
    struct {uint64_t before, data[STAT_ENTRIES], after;} out;
    dev.base.netdev = &netdev;
    check(QCOM_MIB_STATS_LEN == 42);
#ifdef NSS_DP_EDMA_V2
    check(QCOM_STATS_LEN == 20);
#else
    check(QCOM_STATS_LEN == 0);
#endif
    check(QCOM_PRIV_FLAGS_LEN == 3);
    check_string_set(&dev.base, ETH_SS_STATS, STAT_ENTRIES, &names);
    check_string_set(&dev.base, ETH_SS_PRIV_FLAGS, QCOM_PRIV_FLAGS_LEN, &private_names);
    for (unsigned i = 0; i < ARRAY_SIZE(unknown_sets); i++) {
        memset(&unknown, 0xa5, sizeof(unknown));
        check(qcom_get_strset_count(&dev.base, unknown_sets[i]) == -EPERM);
        check(qcom_get_strings(&dev.base, unknown_sets[i], &unknown.data[0][0]) == -EPERM);
        check(bytes_are(&unknown, sizeof(unknown), 0xa5));
    }
    /* Alternating sets must not leave an offset or count behind. */
    check_string_set(&dev.base, ETH_SS_STATS, STAT_ENTRIES, &names);
    check(mib_reads == 0);
    unsigned strings_checks = checks, strings_failures = failures;
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
        check(mib_reads == s+1);
        check_named_payload(&names, out.data, expected);
        check(out.before == CANARY);
        check(out.after == CANARY);
    }
    unsigned payload_checks = checks-strings_checks, payload_failures = failures-strings_failures;
    read_error = true;
    memset(&out, 0xa5, sizeof(out));
    check(qcom_get_eth_stats(&dev.base, out.data, &sw) == -1);
    check(mib_reads == ARRAY_SIZE(seeds)+1);
    for (unsigned i = 0; i < QCOM_STATS_LEN; i++)
        check(out.data[i] == UINT64_C(0x500000000)+i);
    for (unsigned i = 0; i < QCOM_MIB_STATS_LEN; i++)
        check(out.data[QCOM_STATS_LEN+i] == CANARY);
    check(out.before == CANARY);
    check(out.after == CANARY);
    printf("{\"checks\":%u,\"failures\":%u,\"mib_entries\":%zu,\"data_entries\":%zu,"
        "\"total_entries\":%zu,\"private_entries\":%zu,\"unknown_sets\":%zu,"
        "\"strings_checks\":%u,\"strings_failures\":%u,"
        "\"payload_checks\":%u,\"payload_failures\":%u,\"read_error_failures\":%u}\n",
        checks, failures, QCOM_MIB_STATS_LEN, QCOM_STATS_LEN, STAT_ENTRIES,
        QCOM_PRIV_FLAGS_LEN, ARRAY_SIZE(unknown_sets), strings_checks, strings_failures,
        payload_checks, payload_failures, failures-strings_failures-payload_failures);
    return failures ? 1 : 0;
}
'''
variants = [('candidate', tables, functions, None)]
baseline = None
if args.baseline:
    baseline = extract.Prepared(args.baseline)
    baseline_tables, baseline_functions = qcom_contract(baseline)
    variants.append(('baseline', baseline_tables, baseline_functions, 'payload'))
if args.mutations:
    replacements = [
        ('u32-truncation', 'qcom_get_eth_stats', 'i = QCOM_STATS_LEN + i_mib;\n\t\tdata[i] = *(uint64_t *)p;',
         'i = QCOM_STATS_LEN + i_mib;\n\t\tdata[i] = *(uint32_t *)p;', 1, 'payload'),
        ('missing-last', 'qcom_get_eth_stats', 'i_mib < QCOM_MIB_STATS_LEN',
         'i_mib + 1 < QCOM_MIB_STATS_LEN', 1, 'payload'),
        ('wrong-output-offset', 'qcom_get_eth_stats', 'i = QCOM_STATS_LEN + i_mib;', 'i = i_mib;', 1, 'payload'),
        ('ignored-read-error', 'qcom_get_eth_stats', 'if (qcom_get_mib_stats(nghd))',
         'if (qcom_get_mib_stats(nghd) && false)', 1, 'read_error'),
        ('strings-rotated-mib', 'qcom_get_strings', 'qcom_gstrings_mib_stats[i].stat_string',
         'qcom_gstrings_mib_stats[(i+1)%QCOM_MIB_STATS_LEN].stat_string', 2, 'strings'),
        ('strings-missing-last', 'qcom_get_strings', 'i < QCOM_MIB_STATS_LEN',
         'i + 1 < QCOM_MIB_STATS_LEN', 1, 'strings'),
        ('strings-wrong-stride', 'qcom_get_strings', 'data += ETH_GSTRING_LEN;',
         'data += ETH_GSTRING_LEN-1;', 3, 'strings'),
        ('private-missing-last', 'qcom_get_strings', 'i < QCOM_PRIV_FLAGS_LEN',
         'i + 1 < QCOM_PRIV_FLAGS_LEN', 1, 'strings'),
        ('count-stats-short', 'qcom_get_strset_count', 'return (QCOM_STATS_LEN + QCOM_MIB_STATS_LEN);',
         'return (QCOM_STATS_LEN + QCOM_MIB_STATS_LEN - 1);', 1, 'strings'),
        ('count-private-long', 'qcom_get_strset_count', 'return QCOM_PRIV_FLAGS_LEN;',
         'return QCOM_PRIV_FLAGS_LEN + 1;', 1, 'strings'),
        ('count-unknown-success', 'qcom_get_strset_count', 'return -EPERM;', 'return 0;', 1, 'strings'),
        ('strings-unknown-success', 'qcom_get_strings', 'return -EPERM;', 'return 0;', 1, 'strings'),
        ('strings-unknown-write', 'qcom_get_strings', 'return -EPERM;',
         'data[0] = 0;\n\t\treturn -EPERM;', 1, 'strings'),
    ]
    for label, function, old, new, count, stage in replacements:
        original = functions[function]
        if original.count(old) != count:
            raise ValueError('mutation context drift: ' + label)
        mutated = dict(functions)
        mutated[function] = original.replace(old, new)
        variants.append((label, tables, mutated, stage))
records = []
compiler = subprocess.run(shlex.split(args.cc) + ['--version'], capture_output=True, check=True).stdout.decode()
for soc in ('ipq807x', 'ipq60xx', 'ipq95xx', 'ipq53xx', 'ipq54xx'):
    types = prepared.structure(f'hal/soc_ops/{soc}/nss_{soc}.h', 'nss_dp_hal_gmac_stats')
    api = prepared.structure('exports/nss_dp_api_if.h', 'nss_dp_gmac_stats')
    defines = '#define NSS_DP_EDMA_V2 1\n' if soc in ('ipq95xx', 'ipq53xx', 'ipq54xx') else ''
    for label, variant_tables, variant_functions, expected_stage in variants:
        must_pass = expected_stage is None
        if label == 'wrong-output-offset' and soc in ('ipq807x', 'ipq60xx'):
            continue  # The v1 dataplane prefix is empty; this mutation is identical there.
        name = soc + '-' + label
        c = args.output / (name + '.c')
        c.write_text(prefix + defines + mib.group() + '\n' + types + api + variant_tables + models +
                     ''.join(variant_functions[name] for name in function_names) + main)
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
        if expected_stage and not data[expected_stage + '_failures']:
            raise SystemExit('negative control missed its contract stage: ' + name)
        if expected_stage in ('payload', 'read_error') and data['strings_failures']:
            raise SystemExit('getter control failed unrelated strings contract: ' + name)
        records.append(dict(label=name, command=command, source_sha256=hashlib.sha256(c.read_bytes()).hexdigest(),
                            binary_sha256=hashlib.sha256(c.with_suffix('').read_bytes()).hexdigest(),
                            expected_failure=not must_pass, expected_stage=expected_stage, **data))
result = dict(results=records, prepared=str(args.prepared),
    getter_sha256=hashlib.sha256(body.encode()).hexdigest(),
    functions_sha256={name: hashlib.sha256(function.encode()).hexdigest() for name, function in functions.items()},
    tables_sha256=hashlib.sha256(tables.encode()).hexdigest(),
    ssdk_mib_sha256=hashlib.sha256(mib.group().encode()).hexdigest(),
    compiler=compiler, test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    inputs=dict(candidate=prepared.manifest(), ssdk=ssdk.manifest(),
                baseline=baseline.manifest() if baseline else None),
    scope='actual QCOM strings/count/getter, tables and public layouts; modeled transport/device/libc/logging, not target or runtime')
(args.output / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps([dict(label=r['label'], checks=r['checks'], failures=r['failures']) for r in records], indent=2))
