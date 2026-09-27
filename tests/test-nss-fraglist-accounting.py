#!/usr/bin/env python3
"""Run the prepared NSS linear RX function against an skb ownership model.

This tests accounting/control flow, not DMA, firmware descriptors or the kernel
allocator. Pass the qca-nss-drv directory after all package patches are applied.
"""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

if len(sys.argv) != 2:
    raise SystemExit('usage: test-nss-fraglist-accounting.py <prepared-nss-drv>')
source = (Path(sys.argv[1]) / 'nss_core.c').read_text()
start = source.index('static inline bool nss_core_handle_linear_skb(')
end = source.index('\n}\n', start) + 3
function = source[start:end]

model = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define likely(x) (x)
#define unlikely(x) (x)
#define N2H_BIT_FLAG_FIRST_SEGMENT 1
#define N2H_BIT_FLAG_LAST_SEGMENT 2
#define DMA_FROM_DEVICE 0
#define NSS_PKT_STATS_INC(x) ((void)0)
#define NSS_PKT_STATS_DEC(x) ((void)0)
#define nss_warning(...) ((void)0)
#define prefetch(x) ((void)(x))
struct skb_shared_info { struct sk_buff *frag_list; };
struct sk_buff {
    unsigned char storage[4096], *head, *data, *tail;
    unsigned int len, data_len, truesize, priority;
    struct sk_buff *next;
    struct skb_shared_info shinfo;
    bool freed;
};
struct nss_ctx_instance { void *dev; };
struct n2h_descriptor {
    uint16_t payload_offs, payload_len, bit_flags, pri;
    uintptr_t buffer;
};
static struct skb_shared_info *skb_shinfo(struct sk_buff *s) { return &s->shinfo; }
static bool skb_has_frag_list(struct sk_buff *s) { return s->shinfo.frag_list != NULL; }
static void skb_frag_list_init(struct sk_buff *s) { s->shinfo.frag_list = NULL; }
static void skb_set_tail_pointer(struct sk_buff *s, unsigned int len) { s->tail = s->data + len; }
static void dev_kfree_skb_any(struct sk_buff *s) { assert(!s->freed); s->freed = true; }
static void dma_unmap_single(void *dev, uintptr_t addr, unsigned int size, int direction) {
    (void)dev; (void)addr; (void)size; (void)direction;
}
static void init_skb(struct sk_buff *s, unsigned int allocation) {
    memset(s, 0, sizeof(*s)); s->head = s->storage; s->truesize = allocation;
}
'''
checks = r'''
static bool receive(struct sk_buff **s, struct sk_buff **head, struct sk_buff **tail,
                    unsigned int flags, unsigned int length) {
    struct nss_ctx_instance ctx = {0};
    struct n2h_descriptor d = {64, length, flags, 7, 0};
    return nss_core_handle_linear_skb(&ctx, s, head, tail, &d);
}
static void test_chain(unsigned int segments) {
    struct sk_buff buffers[4], *head = NULL, *tail = NULL, *s;
    unsigned int lengths[] = {1500, 1400, 100, 64};
    unsigned int sizes[] = {4096, 3584, 3072, 2048};
    unsigned int total_len = 0, total_size = 0;
    for (unsigned int i = 0; i < segments; i++) {
        init_skb(&buffers[i], sizes[i]); s = &buffers[i];
        unsigned int flags = (i == 0 ? N2H_BIT_FLAG_FIRST_SEGMENT : 0) |
                             (i + 1 == segments ? N2H_BIT_FLAG_LAST_SEGMENT : 0);
        bool complete = receive(&s, &head, &tail, flags, lengths[i]);
        total_len += lengths[i]; total_size += sizes[i];
        assert(buffers[0].truesize == total_size);
        assert(buffers[0].len == total_len);
        assert(buffers[0].data_len == total_len - lengths[0]);
        assert(buffers[i].data == buffers[i].head + 64);
        assert(buffers[i].tail == buffers[i].data + lengths[i]);
        assert(buffers[0].priority == 7);
        assert(complete == (i + 1 == segments));
        if (complete) { assert(s == &buffers[0]); assert(head == NULL && tail == NULL); }
        else { assert(head == &buffers[0]); }
    }
    struct sk_buff *fragment = buffers[0].shinfo.frag_list;
    for (unsigned int i = 1; i < segments; i++) {
        assert(fragment == &buffers[i]); assert(!fragment->freed); fragment = fragment->next;
    }
    assert(fragment == NULL);
}
static void test_orphan(void) {
    struct sk_buff b, *s = &b, *head = NULL, *tail = NULL;
    init_skb(&b, 4096);
    assert(!receive(&s, &head, &tail, N2H_BIT_FLAG_LAST_SEGMENT, 128));
    assert(b.freed && !head && !tail);
}
static void test_replace_pending(bool full_frame) {
    struct sk_buff old, fresh, *s = &fresh, *head = &old, *tail = NULL;
    init_skb(&old, 4096); init_skb(&fresh, 3072);
    unsigned int flags = N2H_BIT_FLAG_FIRST_SEGMENT |
                         (full_frame ? N2H_BIT_FLAG_LAST_SEGMENT : 0);
    assert(receive(&s, &head, &tail, flags, 128) == full_frame);
    assert(old.freed && !fresh.freed && fresh.truesize == 3072);
    assert(head == (full_frame ? NULL : &fresh));
}
static void test_nested_chain(void) {
    struct sk_buff b, child, *s = &b, *head = NULL, *tail = NULL;
    init_skb(&b, 4096); init_skb(&child, 2048); b.shinfo.frag_list = &child;
    assert(!receive(&s, &head, &tail, N2H_BIT_FLAG_FIRST_SEGMENT, 128));
    assert(b.freed && !head && !tail);
}
int main(void) {
    for (unsigned int count = 1; count <= 4; count++) test_chain(count);
    test_orphan(); test_replace_pending(false); test_replace_pending(true); test_nested_chain();
    puts("PASS: 8 NSS linear RX scenarios; allocation truesize, lengths and chain ownership preserved");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='nss-fraglist-') as tmp:
    src = Path(tmp) / 'check.c'
    binary = Path(tmp) / 'check'
    src.write_text(model + function + checks)
    subprocess.run(shlex.split(os.environ.get('CC', 'cc')) +
                   ['-std=c11', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
