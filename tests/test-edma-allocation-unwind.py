#!/usr/bin/env python3
"""Replay pinned DP patches, extract actual C, and test allocation ownership."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile


PIN = 'd8f802f08fd8ff31057ba58edb20bbe448e7b505'
REL = Path('hal/dp_ops/edma_dp/edma_v1')
PATCH = '013-edma-v1-unwind-unpublished-ring-allocations.patch'
SOURCE = Path(__file__).resolve().parents[1]
PATCHES = SOURCE / 'package/qca-nss/qca-nss-dp/patches'
ALLOWED = {'edma_free_unpublished_ring_resources', 'edma_setup_ring_resources',
           'edma_free_rings', 'edma_alloc_rings', 'edma_init_rings'}
FUNCTIONS = [
    'edma_cleanup_rxfill_ring_res', 'edma_setup_rxfill_ring_res',
    'edma_setup_rxdesc_ring_res', 'edma_cleanup_rxdesc_ring_res',
    'edma_cleanup_txcmpl_ring_res', 'edma_setup_txcmpl_ring_res',
    'edma_cleanup_txdesc_ring_res', 'edma_setup_txdesc_ring_res',
    'edma_free_unpublished_ring_resources', 'edma_setup_ring_resources',
    'edma_free_rings', 'edma_alloc_rings', 'edma_cleanup_rings', 'edma_init_rings',
    'edma_configure_txdesc_ring', 'edma_configure_txcmpl_ring',
    'edma_configure_rxdesc_ring', 'edma_configure_rxfill_ring',
    'edma_configure_rings', 'edma_hw_init',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def mask_c(text):
    # Preserve offsets while ignoring braces in comments and literals.
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def functions(text):
    masked = mask_c(text)
    found = {}
    pattern = r'^(?:static )?(?:int|void) (\w+)\([^;{}]*\)\s*\{'
    for match in re.finditer(pattern, masked, re.M):
        depth = 1
        end = match.end()
        while depth and end < len(masked):
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        require(depth == 0 and match[1] not in found, 'ambiguous C definition')
        found[match[1]] = (match.start(), end, text[match.start():end])
    return found


def replace_function(text, name, replacement):
    begin, end, _ = functions(text)[name]
    return text[:begin] + replacement + text[end:]


PREFIX = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#define NSS_DP_IPQ807X 1
#define __iomem
typedef uint64_t dma_addr_t;
typedef unsigned spinlock_t;
typedef int irqreturn_t;
struct napi_struct { int placeholder; };
struct device { unsigned cookie; };
struct platform_device { struct device dev; };
struct sk_buff { unsigned placeholder; };
#define GFP_KERNEL 0
#define DMA_FROM_DEVICE 0
#define DMA_TO_DEVICE 1
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define le32_to_cpu(v) ((uint32_t)(v))
#else
#define le32_to_cpu(v) __builtin_bswap32((uint32_t)(v))
#endif
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_warn(...) ((void)0)
static unsigned checks, cases, retry_successes, fault_cases, zero_frees, fixture_zero_discards;
static void require_c(bool ok, const char *why) {
    ++checks;
    if (!ok) { fprintf(stderr, "EDMA_CONTRACT %s\n", why); exit(86); }
}
static bool trace_enabled, allocation_failed, mmio_forbidden;
static volatile uint32_t observed_mmio_offset;
static unsigned allocation_calls, fail_at, zero_at, coherent_calls;
static unsigned mmio_after_failure, stream_unmaps, packet_frees;
static struct platform_device fixture_pdev = { .dev = { .cookie = 42 } };
static struct { uint32_t rx_buf_size; } dp_global_ctx = { 2048 };
struct allocation { void *ptr; size_t size; dma_addr_t dma; bool coherent, live; unsigned kind; };
static struct allocation ledger[4096];
static unsigned ledger_count;
static uint32_t registers[0x80000 / 4];
static void event(const char *format, ...) {
    if (!trace_enabled) return;
    va_list ap; va_start(ap, format); vprintf(format, ap); va_end(ap);
}
static struct allocation *live_entry(void *ptr) {
    for (unsigned i = ledger_count; i; --i)
        if (ledger[i-1].ptr == ptr && ledger[i-1].live) return &ledger[i-1];
    return NULL;
}
static unsigned outstanding(void) {
    unsigned n = 0;
    for (unsigned i = 0; i < ledger_count; ++i) n += ledger[i].live;
    return n;
}
static bool allocation_fails(void) {
    ++allocation_calls;
    if (allocation_calls == fail_at) { allocation_failed = true; return true; }
    return false;
}
static void record(void *p, size_t n, dma_addr_t dma, bool coherent, unsigned kind) {
    require_c(p && ledger_count < 4096, "fixture-allocation");
    ledger[ledger_count++] = (struct allocation){p, n, dma, coherent, true, kind};
}
static void *kzalloc(size_t n, int flags) {
    (void)flags;
    if (allocation_fails()) { event("SW_FAIL %u %zu\n", allocation_calls, n); return NULL; }
    void *p = calloc(1, n); record(p, n, 0, false, allocation_calls);
    event("SW_ALLOC %u %zu\n", allocation_calls, n); return p;
}
static void *dma_alloc_coherent(struct device *dev, size_t n, dma_addr_t *dma, int flags) {
    (void)flags; require_c(dev == &fixture_pdev.dev, "allocation-device");
    ++coherent_calls;
    if (allocation_fails()) { event("DMA_FAIL %u %zu\n", allocation_calls, n); return NULL; }
    *dma = coherent_calls == zero_at ? 0 : 0x100000ULL + coherent_calls * 0x10000ULL;
    void *p = calloc(1, n); record(p, n, *dma, true, 0);
    event("DMA_ALLOC %u %zu %llu\n", allocation_calls, n, (unsigned long long)*dma); return p;
}
static void dma_free_coherent(struct device *dev, size_t n, void *p, dma_addr_t dma) {
    struct allocation *a = live_entry(p);
    require_c(dev == &fixture_pdev.dev && a && a->coherent && a->size == n && a->dma == dma,
              "coherent-free-ownership");
    if (!dma) ++zero_frees;
    a->live = false; free(p);
}
static void kfree(void *p);
static void host_spin_init(spinlock_t *p) { *p = 1; event("LOCK_INIT\n"); }
#define spin_lock_init(p) host_spin_init(p)
static uint32_t edma_reg_read(uint32_t offset);
static void edma_reg_write(uint32_t offset, uint32_t value);
static void dma_unmap_single(struct device *dev, dma_addr_t dma, size_t n, int direction) {
    (void)dev; (void)dma; (void)n; (void)direction; ++stream_unmaps;
    require_c(false, "streaming-unmap-in-allocation-rollback");
}
static void *phys_to_virt(dma_addr_t dma) {
    (void)dma; require_c(false, "packet-preheader-in-allocation-rollback"); return NULL;
}
static unsigned skb_headlen(struct sk_buff *skb) { (void)skb; return 32; }
static void dev_kfree_skb_any(struct sk_buff *skb) {
    (void)skb; ++packet_frees; require_c(false, "packet-free-in-allocation-rollback");
}
'''

STUBS = r'''
static void kfree(void *p) {
    if (!p) return;
    struct allocation *a = live_entry(p);
    require_c(a && !a->coherent, "software-free-ownership");
#define CHECK_ARRAY(type) do { \
    require_c(a->size % sizeof(struct type) == 0, "array-size"); \
    struct type *rings = p; \
    for (size_t j = 0; j < a->size / sizeof(*rings); ++j) \
        require_c(rings[j].desc == NULL, "descriptor-not-retired-before-array-free"); \
} while (0)
    switch (a->kind) {
        case 1: CHECK_ARRAY(edma_rxfill_ring); break;
        case 2: CHECK_ARRAY(edma_rxdesc_ring); break;
        case 3: CHECK_ARRAY(edma_txdesc_ring); break;
        case 4: CHECK_ARRAY(edma_txcmpl_ring); break;
        default: require_c(false, "software-array-kind");
    }
#undef CHECK_ARRAY
    a->live = false; free(p);
}
uint32_t edma_reg_read(uint32_t offset) {
    observed_mmio_offset = offset;
    require_c(!mmio_forbidden, "mmio-in-unpublished-phase");
    if (allocation_failed) { ++mmio_after_failure; require_c(false, "mmio-after-allocation-failure"); }
    require_c(offset % 4 == 0 && offset < sizeof(registers), "mmio-range");
    event("READ %x %x\n", offset, registers[offset / 4]); return registers[offset / 4];
}
void edma_reg_write(uint32_t offset, uint32_t value) {
    observed_mmio_offset = offset;
    require_c(!mmio_forbidden, "mmio-in-unpublished-phase");
    if (allocation_failed) { ++mmio_after_failure; require_c(false, "mmio-after-allocation-failure"); }
    require_c(offset % 4 == 0 && offset < sizeof(registers), "mmio-range");
    event("WRITE %x %x\n", offset, value); registers[offset / 4] = value;
}
uint32_t edma_clean_tx(struct edma_hw *hw, struct edma_txcmpl_ring *ring) {
    (void)hw; observed_mmio_offset = ring->id;
    require_c(false, "live-tx-clean-in-allocation-rollback"); return 0;
}
int edma_alloc_rx_buffer(struct edma_hw *hw, struct edma_rxfill_ring *ring) {
    require_c(!allocation_failed && hw->pdev == &fixture_pdev, "rx-fill-before-allocation-success");
    event("RX_FILL %u %u\n", ring->id, ring->count); return ring->count - 1;
}
static int edma_hw_reset(struct edma_hw *hw) {
    require_c(hw->pdev == &fixture_pdev, "reset-device");
    for (unsigned i = 0; i < sizeof(registers) / sizeof(*registers); ++i) registers[i] = 0x55aa0081;
    event("RESET\n"); return 0;
}
'''

MAIN = r'''
struct geometry { unsigned txd, txc, rxf, rxd, td_start, tc_start, rf_start, rd_start; };
static const struct geometry geometry[] = { STOCK_GEOMETRY, {3, 2, 2, 5, 19, 5, 4, 9} };
static void begin_attempt(struct edma_hw *hw, unsigned g, unsigned fail, unsigned zero, bool fresh) {
    require_c(outstanding() == 0, "ledger-not-empty-at-attempt-start");
    if (fresh) {
        memset(hw, 0, sizeof(*hw));
        const struct geometry *p = &geometry[g]; hw->pdev = &fixture_pdev;
        hw->txdesc_rings = p->txd; hw->txcmpl_rings = p->txc;
        hw->rxfill_rings = p->rxf; hw->rxdesc_rings = p->rxd;
        hw->txdesc_ring_start = p->td_start; hw->txcmpl_ring_start = p->tc_start;
        hw->rxfill_ring_start = p->rf_start; hw->rxdesc_ring_start = p->rd_start;
        hw->txdesc_ring_end = p->td_start + p->txd; hw->txcmpl_ring_end = p->tc_start + p->txc;
        hw->rxfill_ring_end = p->rf_start + p->rxf; hw->rxdesc_ring_end = p->rd_start + p->rxd;
    }
    for (unsigned i = 0; i < EDMA_RING_SIZE; ++i) {
        hw->rx_skb_store[i] = (struct sk_buff *)(uintptr_t)0x12340;
        hw->tx_skb_store[i] = (struct sk_buff *)(uintptr_t)0x56780; hw->tx_dma_store[i] = 0xabc;
    }
    ledger_count = allocation_calls = coherent_calls = 0;
    fail_at = fail; zero_at = zero; allocation_failed = false; mmio_forbidden = false;
}
static void all_arrays_null(struct edma_hw *hw) {
    require_c(!hw->rxfill_ring && !hw->rxdesc_ring && !hw->txdesc_ring && !hw->txcmpl_ring,
              "software-array-pointer-not-null");
}
static void failed_attempt(struct edma_hw *hw, unsigned fail) {
    ++cases; ++fault_cases;
    unsigned zero_before = zero_frees;
    require_c(edma_hw_init(hw) == -ENOMEM, "fault-return");
    require_c(allocation_calls == fail && allocation_failed && !hw->edma_initialized, "fault-stage");
    require_c(outstanding() == 0, "allocation-leak"); all_arrays_null(hw);
    require_c(zero_frees == zero_before + (zero_at && fail > 4 + zero_at), "zero-DMA-rollback-ownership");
    for (unsigned i = 0; i < EDMA_RING_SIZE; ++i)
        require_c(hw->rx_skb_store[i] == (struct sk_buff *)(uintptr_t)0x12340 &&
                  hw->tx_skb_store[i] == (struct sk_buff *)(uintptr_t)0x56780 && hw->tx_dma_store[i] == 0xabc,
                  "packet-store-touched-on-failure");
}
static void validate_success(struct edma_hw *hw) {
    unsigned n = hw->txdesc_rings + hw->txcmpl_rings + hw->rxfill_rings + hw->rxdesc_rings;
    require_c(allocation_calls == n + 4 && outstanding() == n + 4 && hw->edma_initialized, "success-owned-resources");
#define RINGS(kind) do { \
    for (unsigned j = 0; j < hw->kind##_rings; ++j) { \
        struct edma_##kind##_ring *r = &hw->kind##_ring[j]; \
        require_c(r->count == EDMA_RING_SIZE && r->id == hw->kind##_ring_start + j && live_entry(r->desc), "ring-geometry"); \
    } \
} while (0)
    RINGS(txdesc); RINGS(txcmpl); RINGS(rxfill); RINGS(rxdesc);
#undef RINGS
    for (unsigned j = 0; j < hw->rxdesc_rings; ++j)
        require_c(hw->rxdesc_ring[j].rxfill == &hw->rxfill_ring[j % hw->rxfill_rings], "rx-mapping");
    for (unsigned i = 0; i < EDMA_RING_SIZE; ++i)
        require_c(!hw->rx_skb_store[i] && !hw->tx_skb_store[i] && !hw->tx_dma_store[i], "store-initialization");
}
static void dispose_success(struct edma_hw *hw, bool test_array_release) {
    /* The fixture has no DMA device. This is NOT production live cleanup. */
    for (unsigned i = 0; i < ledger_count; ++i) if (ledger[i].live && ledger[i].coherent) {
        if (!ledger[i].dma) ++fixture_zero_discards;
        ledger[i].live = false; free(ledger[i].ptr);
    }
    if (test_array_release) {
#define CLEAR_DESC(kind) for (unsigned j = 0; j < hw->kind##_rings; ++j) hw->kind##_ring[j].desc = NULL
        CLEAR_DESC(txdesc); CLEAR_DESC(txcmpl); CLEAR_DESC(rxfill); CLEAR_DESC(rxdesc);
#undef CLEAR_DESC
        edma_free_rings(hw); all_arrays_null(hw);
    } else {
        for (unsigned i = 0; i < ledger_count; ++i) if (ledger[i].live) { ledger[i].live = false; free(ledger[i].ptr); }
    }
    require_c(outstanding() == 0, "fixture-disposal");
}
static void successful_attempt(struct edma_hw *hw, bool test_array_release) {
    ++cases; require_c(edma_hw_init(hw) == 0, "success-return"); validate_success(hw);
    trace_enabled = false; dispose_success(hw, test_array_release);
}
int main(int argc, char **argv) {
    require_c(argc >= 2, "fixture-mode");
    struct edma_hw hw;
    if (!strcmp(argv[1], "fault")) {
        require_c(argc == 5, "fault-arguments"); unsigned g = (unsigned)atoi(argv[2]);
        unsigned fail = (unsigned)atoi(argv[3]), zero = (unsigned)atoi(argv[4]);
        require_c(g < 2, "geometry-argument"); begin_attempt(&hw, g, fail, zero, true); failed_attempt(&hw, fail);
    } else if (!strcmp(argv[1], "trace")) {
        require_c(argc == 3, "trace-arguments"); unsigned g = (unsigned)atoi(argv[2]); require_c(g < 2, "geometry-argument");
        begin_attempt(&hw, g, 0, 0, true); trace_enabled = true; successful_attempt(&hw, false);
    } else {
        require_c(!strcmp(argv[1], "matrix"), "unknown-mode");
        for (unsigned g = 0; g < 2; ++g) {
            const struct geometry *p = &geometry[g]; unsigned n = p->txd + p->txc + p->rxf + p->rxd;
            for (unsigned zero = 0; zero <= 1; ++zero) for (unsigned fail = 1; fail <= n + 4; ++fail) {
                begin_attempt(&hw, g, fail, zero, true); failed_attempt(&hw, fail);
                begin_attempt(&hw, g, 0, zero, false); successful_attempt(&hw, true); ++retry_successes;
            }
            for (unsigned zero = 0; zero <= n; ++zero) {
                begin_attempt(&hw, g, 0, zero, true); successful_attempt(&hw, true);
            }
            for (unsigned zero = 1; zero < n; ++zero) {
                unsigned fail = 4 + zero + 1;
                begin_attempt(&hw, g, fail, zero, true); failed_attempt(&hw, fail);
            }
#if HAS_UNPUBLISHED_HELPER
            for (unsigned zero = 1; zero <= n; ++zero) {
                begin_attempt(&hw, g, 0, zero, true); ++cases; mmio_forbidden = true;
                require_c(edma_alloc_rings(&hw) == 0 && edma_setup_ring_resources(&hw) == 0, "unpublished-setup");
                unsigned zero_before = zero_frees;
                edma_free_unpublished_ring_resources(&hw);
                edma_free_unpublished_ring_resources(&hw);
                require_c(zero_frees == zero_before + 1, "zero-DMA-helper-ownership");
                edma_free_rings(&hw); all_arrays_null(&hw);
                require_c(outstanding() == 0, "unpublished-helper-idempotence"); mmio_forbidden = false;
            }
#endif
            begin_attempt(&hw, g, 2, 0, true); failed_attempt(&hw, 2);
            begin_attempt(&hw, g, n + 4, 1, false); failed_attempt(&hw, n + 4);
            begin_attempt(&hw, g, 0, 1, false); successful_attempt(&hw, true); ++retry_successes;
        }
        require_c(zero_frees > 0, "zero-DMA-handle-not-exercised");
    }
    require_c(!mmio_after_failure && !stream_unmaps && !packet_frees, "rollback-side-effects");
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":0,\"fault_cases\":%u,\"retry_successes\":%u,\"zero_handle_releases\":%u,\"fixture_zero_discards\":%u}\n",
           cases, checks, fault_cases, retry_successes, zero_frees, fixture_zero_discards);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path, help='fresh pre-013 qca-nss-dp input')
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--upstream-cache', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'RUNNING', 'qualification': 'Extracted host C, not a target build or DMA hardware proof',
              'pin': PIN, 'commands': [], 'inputs': [], 'extracted': {}, 'runs': [], 'mutations': []}

    def input_hash(path):
        data = path.read_bytes()
        result['inputs'].append({'path': str(path.resolve()), 'sha256': digest(data), 'bytes': len(data)})
        return data

    def command(argv, label, cwd=None, env=None):
        completed = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
        result['commands'].append({'command': shlex.join([str(x) for x in argv]), 'cwd': str(cwd) if cwd else None,
                                   'label': label, 'returncode': completed.returncode})
        (args.output / (label + '.stdout.log')).write_text(completed.stdout)
        (args.output / (label + '.stderr.log')).write_text(completed.stderr)
        return completed

    try:
        receipt = json.loads(input_hash(args.receipt))
        component = next(x for x in receipt['components'] if x['package'] == 'qca-nss-dp')
        require(component['pin'] == PIN, 'receipt pin mismatch')
        require(len(component['patches']) == 12, 'expected pre-013 baseline receipt')
        version = command([args.cc, '--version'], 'compiler-version')
        require(version.returncode == 0, 'compiler unavailable')
        result['compiler'] = version.stdout.strip()
        if args.sanitize:
            require('clang' in version.stdout.lower(), 'sanitizer suite requires Clang')
        else:
            require('gcc' in version.stdout.lower() and 'clang' not in version.stdout.lower(), 'plain suite requires real GCC')
        archive = subprocess.run(['git', '-C', str(args.upstream_cache), 'archive', '--format=tar', PIN],
                                 capture_output=True, check=True, timeout=120).stdout
        result['archive_sha256'] = digest(archive)
        fresh = args.output / 'fresh-dp'
        fresh.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar:
                relative = Path(item.name)
                require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe archive path')
                target = fresh / relative
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    require(item.isfile(), 'archive contains nonregular entry')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(item).read())
        for item in component['patches']:
            patch = SOURCE / item['path']
            require(digest(input_hash(patch)) == item['sha256'], 'pre-013 patch changed: ' + str(patch))
            applied = command(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', patch], patch.stem, fresh)
            require(applied.returncode == 0 and not re.search(r'offset|fuzz|reversed|FAILED', applied.stdout + applied.stderr, re.I),
                    'inexact baseline patch replay')
        for name in ['edma_cfg.c', 'edma_data_plane.h', 'edma_regs.h']:
            require((fresh / REL / name).read_bytes() == input_hash(args.prepared / REL / name), 'prepared/replay mismatch: ' + name)
        original = (fresh / REL / 'edma_cfg.c').read_text()
        patch_data = input_hash(PATCHES / PATCH)
        require(re.findall(rb'^\+\+\+ b/(.+)$', patch_data, re.M) == [str(REL / 'edma_cfg.c').encode()], 'patch escapes edma_cfg.c')
        applied = command(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', PATCHES / PATCH], 'apply-013', fresh)
        require(applied.returncode == 0 and not re.search(r'offset|fuzz|reversed|FAILED', applied.stdout + applied.stderr, re.I), 'inexact 013 replay')
        candidate = (fresh / REL / 'edma_cfg.c').read_text()
        old_functions, new_functions = functions(original), functions(candidate)
        require(set(new_functions) - set(old_functions) == {'edma_free_unpublished_ring_resources'}, 'unexpected new functions')
        changed = {name for name in old_functions if old_functions[name][2] != new_functions[name][2]}
        require(changed == ALLOWED - {'edma_free_unpublished_ring_resources'}, 'changed functions escape allocation scope')
        def nonallocation_tokens(text):
            remaining = text
            for name, (begin, end, _) in sorted(functions(text).items(), key=lambda item: item[1][0], reverse=True):
                if name in ALLOWED:
                    remaining = remaining[:begin] + remaining[end:]
            return re.findall(r'\w+|[^\s]', mask_c(remaining))
        require(nonallocation_tokens(original) == nonallocation_tokens(candidate), 'nonallocation tokens changed')
        result['scope'] = {'changed_functions': sorted(changed), 'added_functions': ['edma_free_unpublished_ring_resources'],
                           'all_other_function_definitions_byte_identical': True,
                           'nonallocation_code_tokens_identical': True,
                           'candidate_cfg_sha256': digest(candidate.encode())}
        header = (fresh / REL / 'edma_data_plane.h').read_text()
        for include in ['#include <linux/netdevice.h>\n', '#include <nss_dp_arch.h>\n']:
            require(header.count(include) == 1, 'unexpected header includes')
            header = header.replace(include, '')
        soc = input_hash(fresh / 'hal/soc_ops/ipq807x/nss_ipq807x.h').decode()
        soc_defines = '\n'.join(re.findall(r'^#define NSS_DP_HAL_(?:MAX_PORTS|START_IFNUM)\s+\d+.*$', soc, re.M))
        require(len(soc_defines.splitlines()) == 2, 'missing actual SoC constants')
        dts_path = SOURCE / 'target/linux/qualcommax/files/arch/arm64/boot/dts/qcom/ipq8074-ess.dtsi'
        dts = input_hash(dts_path).decode()
        topology = {}
        for name in ['txdesc', 'txcmpl', 'rxfill', 'rxdesc']:
            for prop in ['rings', 'ring-start']:
                matches = re.findall(r'qcom,' + name + '-' + prop + r'\s*=\s*<(\d+)>;', dts)
                require(len(matches) == 1, 'ambiguous stock geometry')
                topology[name + '-' + prop] = int(matches[0])
        result['stock_geometry'] = topology
        geometry = [topology[n + '-rings'] for n in ['txdesc', 'txcmpl', 'rxfill', 'rxdesc']]
        geometry += [topology[n + '-ring-start'] for n in ['txdesc', 'txcmpl', 'rxfill', 'rxdesc']]
        main_c = MAIN.replace('STOCK_GEOMETRY', '{' + ','.join(map(str, geometry)) + '}')
        registers = (fresh / REL / 'edma_regs.h').read_text()
        common = PREFIX + '\n' + soc_defines + '\n' + registers + '\n' + header + '\n' + STUBS
        flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-Wno-sign-compare', '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-type-limits']
        env = os.environ.copy()
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            env['ASAN_OPTIONS'] = 'detect_leaks=0:redzone=128:abort_on_error=1:halt_on_error=1'
            env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        result['sanitizer_environment'] = {k: env[k] for k in ['ASAN_OPTIONS', 'UBSAN_OPTIONS'] if k in env}

        def compile_variant(name, text):
            path = args.output / (name + '.c')
            definitions = functions(text)
            extracted = []
            bodies = []
            for function in FUNCTIONS:
                if function not in definitions:
                    require(function == 'edma_free_unpublished_ring_resources', 'missing extracted function')
                    continue
                begin, _, body = definitions[function]
                line = text.count('\n', 0, begin) + 1
                extracted.append({'function': function, 'line': line, 'sha256': digest(body.encode())})
                bodies.append('#line ' + str(line) + ' ' + json.dumps(name + '/edma_cfg.c') + '\n' + body)
            has_helper = int('edma_free_unpublished_ring_resources' in definitions)
            generated = common + '\n#define HAS_UNPUBLISHED_HELPER ' + str(has_helper) + '\n' + '\n\n'.join(bodies) + '\n#line 1 "host-main"\n' + main_c
            path.write_text(generated)
            result['extracted'][name] = {'definitions': extracted, 'generated_c_sha256': digest(generated.encode()),
                                         'cfg_sha256': digest(text.encode())}
            compiled = command([args.cc] + flags + [path, '-o', args.output / name], name + '-compile')
            require(compiled.returncode == 0 and compiled.stdout == '' and compiled.stderr == '', 'compile failed or emitted diagnostics: ' + name)
            return args.output / name

        def positive(binary, parameters, label):
            run = command([binary] + parameters, label, env=env)
            require(run.returncode == 0 and run.stderr == '', 'positive failed or stderr nonempty: ' + label)
            result['runs'].append({'label': label, 'returncode': run.returncode, 'stderr_empty': True,
                                   'summary': json.loads(run.stdout.splitlines()[-1]), 'stdout_sha256': digest(run.stdout.encode())})
            return run.stdout

        def negative(binary, parameters, label, diagnostic):
            run = command([binary] + parameters, label, env=env)
            require(run.returncode != 0 and re.search(diagnostic, run.stderr, re.S), 'negative control not specifically detected: ' + label)
            result['mutations'].append({'label': label, 'returncode': run.returncode, 'expected_diagnostic': diagnostic,
                                        'stderr_sha256': digest(run.stderr.encode())})

        candidate_bin = compile_variant('candidate', candidate)
        baseline_bin = compile_variant('baseline', original)
        positive(candidate_bin, ['matrix'], 'candidate-matrix')
        for g in ['0', '1']:
            before = positive(baseline_bin, ['trace', g], 'baseline-success-' + g)
            after = positive(candidate_bin, ['trace', g], 'candidate-success-' + g)
            require(before == after, 'success allocation/MMIO/RX-fill trace changed')
        result['success_trace_byte_identical'] = True
        negative(baseline_bin, ['fault', '0', '5', '0'], 'baseline-negative-index',
                 r'AddressSanitizer: heap-buffer-overflow' if args.sanitize else r'EDMA_CONTRACT mmio-after-allocation-failure')
        negative(baseline_bin, ['fault', '0', '6', '0'], 'baseline-txcmpl-negative-index',
                 r'AddressSanitizer: heap-buffer-overflow' if args.sanitize else r'EDMA_CONTRACT live-tx-clean-in-allocation-rollback')
        negative(baseline_bin, ['fault', '0', '2', '0'], 'baseline-array-pointer', r'EDMA_CONTRACT software-array-pointer-not-null')
        index_only = original.replace('while (i-- >= 0)', 'while (--i >= 0)')
        index_bin = compile_variant('index-only', index_only)
        negative(index_bin, ['fault', '0', '5', '0'], 'index-only-array-leak', r'EDMA_CONTRACT allocation-leak')
        negative(index_bin, ['fault', '0', '6', '0'], 'index-only-live-cleanup', r'EDMA_CONTRACT mmio-after-allocation-failure')
        init = new_functions['edma_init_rings'][2]
        mutations = [
            ('omit-array-free', replace_function(candidate, 'edma_init_rings', init.replace('\t\tedma_free_rings(ehw);\n', '')),
             ['fault', '0', '5', '0'], r'EDMA_CONTRACT allocation-leak'),
            ('retain-array-pointers', candidate.replace('\tehw->rxfill_ring = NULL;\n', '').replace('\tehw->rxdesc_ring = NULL;\n', '')
             .replace('\tehw->txdesc_ring = NULL;\n', '').replace('\tehw->txcmpl_ring = NULL;\n', ''),
             ['fault', '0', '2', '0'], r'EDMA_CONTRACT software-array-pointer-not-null'),
            ('skip-zero-dma', candidate.replace('if (!ring->desc)', 'if (!ring->desc || !ring->dma)'),
             ['fault', '0', '6', '1'], r'EDMA_CONTRACT descriptor-not-retired-before-array-free'),
            ('retain-descriptor-pointer', candidate.replace('\t\tring->desc = NULL;\n', ''),
             ['fault', '0', '6', '0'], r'EDMA_CONTRACT descriptor-not-retired-before-array-free'),
            ('free-unacquired', candidate.replace('\t\tif (!ring->desc)\n\t\t\tcontinue;\n', ''),
             ['fault', '0', '5', '0'], r'EDMA_CONTRACT coherent-free-ownership'),
            ('live-rollback', candidate.replace('\tedma_free_unpublished_ring_resources(ehw);', '\tedma_cleanup_rings(ehw);'),
             ['fault', '0', '6', '0'], r'EDMA_CONTRACT mmio-after-allocation-failure'),
        ]
        for name, mutated, parameters, diagnostic in mutations:
            require(mutated != candidate, 'mutation did not change code: ' + name)
            negative(compile_variant(name, mutated), parameters, name + '-negative', diagnostic)
        if args.sanitize:
            probes = {
                'asan': '#include <stdlib.h>\nint main(void) { volatile int *p=malloc(sizeof(int)); volatile int i=2; p[i]=1; free((void *)p); return 0; }\n',
                'ubsan': '#include <limits.h>\n#include <stdio.h>\nint main(void) { volatile int v=INT_MAX; int x=v+1; puts("CANARY_CONTINUED"); return x==0; }\n',
            }
            for name, code in probes.items():
                path = args.output / (name + '-probe.c')
                path.write_text(code)
                binary = args.output / (name + '-probe')
                compiled = command([args.cc] + flags + [path, '-o', binary], name + '-probe-compile')
                require(compiled.returncode == 0 and compiled.stdout == '' and compiled.stderr == '', 'sanitizer probe compile failed')
                negative(binary, [], name + '-probe-run', r'AddressSanitizer: heap-buffer-overflow' if name == 'asan' else r'runtime error: signed integer overflow')
                require('CANARY_CONTINUED' not in (args.output / (name + '-probe-run.stdout.log')).read_text(), 'UBSan did not halt')
        result['status'] = 'PASS'
    except Exception as error:
        result['status'] = 'FAIL'
        result['error'] = str(error)
        raise
    finally:
        result['runner_sha256'] = digest(Path(__file__).read_bytes())
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(args.output / 'result.json'),
                      'positive_runs': len(result['runs']), 'negative_controls': len(result['mutations'])}))


if __name__ == '__main__':
    main()
