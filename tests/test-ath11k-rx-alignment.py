#!/usr/bin/env python3
"""Compile real prepared alignment blocks against a small empty-skb model.

This checks pointer/length accounting, not DMA hardware or allocator behavior.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
driver = root / 'drivers/net/wireless/ath/ath11k'
source = (driver / 'dp_rx.c').read_text()
header = (driver / 'dp.h').read_text()
constants = {}
for name in ('DP_RX_BUFFER_SIZE', 'DP_RX_BUFFER_ALIGN_SIZE'):
    constants[name] = int(re.search(r'^#define\s+' + name + r'\s+(\d+)\s*$', header, re.M)[1])
blocks = []
for name in ('ath11k_dp_rxbufs_replenish', 'ath11k_dp_rx_alloc_mon_status_buf'):
    start = source.index(name + '(')
    end = source.index('dma_map_single', start)
    match = re.search(r'if \(!IS_ALIGNED\(.*?\n\s*\}', source[start:end], re.S)
    if match is None:
        raise SystemExit('alignment block not found: ' + name)
    blocks.append('void check_' + name + '(struct sk_buff *skb) {\n' + match[0] + '\n}\n')

model = r'''
#include <stdint.h>
#include <stdio.h>
#define IS_ALIGNED(x, a) (((x) & ((a) - 1)) == 0)
#define PTR_ALIGN(x, a) ((unsigned char *)(((uintptr_t)(x) + (a) - 1) & ~((uintptr_t)(a) - 1)))
struct sk_buff {
    unsigned char *data, *tail, *end;
    unsigned int len, data_len, truesize;
};
unsigned char *skb_pull(struct sk_buff *skb, unsigned int len) {
    if (len > skb->len) return NULL;
    skb->len -= len;
    skb->data += len;
    return skb->data;
}
void skb_reserve(struct sk_buff *skb, unsigned int len) {
    skb->data += len;
    skb->tail += len;
}
'''
main = r'''
int main(void) {
    void (*checks[])(struct sk_buff *) = {
        check_ath11k_dp_rxbufs_replenish,
        check_ath11k_dp_rx_alloc_mon_status_buf
    };
    _Alignas(DP_RX_BUFFER_ALIGN_SIZE) unsigned char storage[DP_RX_BUFFER_SIZE + 3 * DP_RX_BUFFER_ALIGN_SIZE];
    for (unsigned int path = 0; path < 2; path++) {
        for (unsigned int offset = 0; offset < DP_RX_BUFFER_ALIGN_SIZE; offset++) {
            unsigned char *data = storage + offset;
            unsigned int expected = (DP_RX_BUFFER_ALIGN_SIZE - offset) % DP_RX_BUFFER_ALIGN_SIZE;
            struct sk_buff skb = { data, data, data + DP_RX_BUFFER_SIZE + DP_RX_BUFFER_ALIGN_SIZE,
                                   0, 0, sizeof(storage) + sizeof(struct sk_buff) };
            unsigned int truesize = skb.truesize;
            checks[path](&skb);
            if (!IS_ALIGNED((uintptr_t)skb.data, DP_RX_BUFFER_ALIGN_SIZE) ||
                skb.data != data + expected || skb.tail != skb.data || skb.len || skb.data_len ||
                skb.end - skb.tail < DP_RX_BUFFER_SIZE || skb.truesize != truesize) {
                fprintf(stderr, "FAIL path=%u offset=%u: empty-skb alignment/accounting\n", path, offset);
                return 1;
            }
        }
    }
    printf("PASS: regular RX + monitor RX, %u offsets; length/truesize preserved, DMA tailroom sufficient\n",
           2 * DP_RX_BUFFER_ALIGN_SIZE);
    return 0;
}
'''
defines = ''.join('#define %s %d\n' % item for item in constants.items())
with tempfile.TemporaryDirectory(prefix='ath11k-alignment-') as tmp:
    src = Path(tmp) / 'check.c'
    binary = Path(tmp) / 'check'
    src.write_text(defines + model + ''.join(blocks) + main)
    subprocess.run(shlex.split(os.environ.get('CC', 'cc')) +
                   ['-std=c11', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
