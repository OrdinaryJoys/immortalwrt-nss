/* Actual DP declarations/functions replace the three extraction markers. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <arpa/inet.h>

#define NSS_DP_IPQ807X 1
#define NSS_DP_EDMA_TX_SMALL_PKT_WAR 1
#define __iomem
#define GFP_KERNEL 0
#define GFP_ATOMIC 1
#define DMA_TO_DEVICE 1
#define ETH_HLEN 14
#define SKBTX_HW_TSTAMP 1
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 1
#define unlikely(x) (x)
#define likely(x) (x)
#define netdev_dbg(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_warn_ratelimited(...) ((void)0)
#define cpu_to_le32(x) htole32((uint32_t)(x))
#define le32_to_cpu(x) le32toh((uint32_t)(x))
#if defined(__APPLE__)
#include <libkern/OSByteOrder.h>
#define htole32(x) OSSwapHostToLittleInt32(x)
#define le32toh(x) OSSwapLittleToHostInt32(x)
#else
#include <endian.h>
#endif
typedef uint64_t dma_addr_t;
typedef int irqreturn_t;
typedef int netdev_tx_t;
typedef struct { pthread_mutex_t mutex; bool initialized; } spinlock_t;
struct napi_struct { int unused; };
struct device { unsigned cookie; };
struct platform_device { struct device dev; };
struct nss_dp_dev { unsigned macid; };
struct net_device {
    struct nss_dp_dev priv;
    unsigned needed_headroom, needed_tailroom;
    struct { unsigned tx_dropped; } stats;
    bool stopped;
};
struct sk_buff {
    unsigned char *data, *allocation;
    size_t len, capacity;
    unsigned id, queue, protocol;
    bool cloned, nonlinear, freed;
    struct { unsigned tx_flags; } shinfo;
};
struct nss_dp_data_plane_ctx { struct net_device *dev; };
static struct { bool tx_requeue_stop; } dp_global_ctx;
static atomic_uint checks;
static unsigned cases, zero_unmaps, timestamps, expansions, maps, unmaps, frees;
static bool trace_on, pad_fail, map_fail, expand_fail;
static dma_addr_t next_dma;
static _Thread_local spinlock_t *held_lock;
static _Thread_local bool cleaner_thread, producer_thread;
static struct edma_hw *current;
static uint32_t registers[0x80000 / 4];
static pthread_mutex_t ledger_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t schedule_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t schedule_cond = PTHREAD_COND_INITIALIZER;
static int schedule_mode;
static bool paused, released, attempted;
static unsigned hook_seen;
static void check(bool ok, const char *why) {
    atomic_fetch_add(&checks, 1);
    if (!ok) { fprintf(stderr, "EDMA_TX_CONTRACT %s\n", why); exit(86); }
}
static void event(const char *fmt, ...) {
    if (!trace_on) return;
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
}
static void spin_lock_init(spinlock_t *l) {
    check(!l->initialized, "lock-init-not-reentrant");
    check(!pthread_mutex_init(&l->mutex, NULL), "mutex-init"); l->initialized = true;
}
static void spin_lock_bh(spinlock_t *l) {
    check(l->initialized && !held_lock, "lock-initialized-balanced");
    if (producer_thread) {
        pthread_mutex_lock(&schedule_lock); attempted = true;
        pthread_cond_broadcast(&schedule_cond); pthread_mutex_unlock(&schedule_lock);
    }
    check(!pthread_mutex_lock(&l->mutex), "mutex-lock"); held_lock = l;
}
static void spin_unlock_bh(spinlock_t *l) {
    check(held_lock == l, "lock-unlock-identity"); held_lock = NULL;
    check(!pthread_mutex_unlock(&l->mutex), "mutex-unlock");
}

/* DP_HEADERS */

struct edma_hw edma_hw;

static void point(unsigned point_id) {
    if (point_id == 3) {
#if CANDIDATE
        check(held_lock == &current->tx_slot_lock, "take-slot-lock");
#endif
    }
    if (!cleaner_thread || !schedule_mode) return;
    bool stop = (schedule_mode == 1 && point_id == 1) ||
                (schedule_mode == 2 && point_id == 2) ||
                ((schedule_mode == 1 || schedule_mode == 2) && point_id == 3) ||
                (schedule_mode == 4 && point_id == 4);
    if (!stop) return;
    pthread_mutex_lock(&schedule_lock);
    if (!hook_seen++) {
        paused = true; pthread_cond_broadcast(&schedule_cond);
        while (!released) pthread_cond_wait(&schedule_cond, &schedule_lock);
    }
    pthread_mutex_unlock(&schedule_lock);
}
static void *netdev_priv(struct net_device *dev) { return &dev->priv; }
static unsigned skb_get_queue_mapping(struct sk_buff *s) { return s->queue; }
static bool skb_is_nonlinear(struct sk_buff *s) { return s->nonlinear; }
static bool skb_cloned(struct sk_buff *s) { return s->cloned; }
static unsigned skb_headroom(struct sk_buff *s) { return (unsigned)(s->data-s->allocation); }
static unsigned skb_tailroom(struct sk_buff *s) { return (unsigned)(s->capacity-skb_headroom(s)-s->len); }
static size_t skb_headlen(struct sk_buff *s) { check(!s->freed, "skb-live-headlen"); return s->len; }
#define skb_shinfo(s) (&(s)->shinfo)
static void *skb_push(struct sk_buff *s, size_t len) {
    check(skb_headroom(s) >= len, "skb-headroom"); s->data -= len; s->len += len; return s->data;
}
struct mapping { struct sk_buff *skb; dma_addr_t dma; size_t len; struct device *dev; int direction; bool live; };
static struct mapping ledger[4096];
static unsigned ledger_count;
static struct sk_buff *skbs[4096];
static unsigned skb_count;
static struct platform_device pdev = { .dev = { .cookie = 42 } };
static struct net_device netdev;
static struct sk_buff *new_skb(unsigned id, size_t len) {
    struct sk_buff *s = calloc(1, sizeof(*s)); check(s != NULL, "skb-allocation");
    s->capacity = 4096; s->allocation = calloc(1, s->capacity);
    check(s->allocation && skb_count < 4096, "skb-data-allocation");
    s->data = s->allocation + 128; s->len = len; s->id = id; s->protocol = htons(0x0800);
    skbs[skb_count++] = s; return s;
}
static void dev_kfree_skb_any(struct sk_buff *s) {
    check(s && !s->freed, "skb-free-once");
    pthread_mutex_lock(&ledger_lock);
    for (unsigned i=0; i<ledger_count; ++i)
        check(ledger[i].skb != s || !ledger[i].live, "free-before-unmap");
    s->freed = true; ++frees; event("FREE %u\n", s->id);
    pthread_mutex_unlock(&ledger_lock);
    /* Poison payload while retaining the fixture identity until end-of-case. */
    free(s->allocation); s->allocation = NULL; s->data = NULL;
}
static int skb_padto(struct sk_buff *s, unsigned size) {
    if (pad_fail) { dev_kfree_skb_any(s); return -ENOMEM; }
    check(skb_tailroom(s) >= size-s->len, "pad-tailroom");
    memset(s->data+s->len, 0, size-s->len); return 0;
}
static int pskb_expand_head(struct sk_buff *s, unsigned head, unsigned tail, int flags) {
    (void)head; (void)tail; (void)flags; ++expansions;
    if (expand_fail) return -ENOMEM;
    s->cloned = false; return 0;
}
static void netif_stop_queue(struct net_device *dev) { dev->stopped = true; }
static void nss_phy_tstamp_tx_buf(struct net_device *dev, struct sk_buff *s) {
    (void)dev; check(held_lock && !s->freed && s->len >= EDMA_TX_PKT_MIN_SIZE, "timestamp-order"); ++timestamps;
}
static dma_addr_t dma_map_single(struct device *dev, void *data, size_t len, int dir) {
#if CANDIDATE
    check(held_lock == &current->tx_slot_lock, "producer-slot-lock");
#endif
    check(dev == &pdev.dev && dir == DMA_TO_DEVICE, "map-device-direction");
    pthread_mutex_lock(&ledger_lock);
    struct sk_buff *s = NULL;
    for (unsigned i=0; i<skb_count; ++i) if (!skbs[i]->freed && skbs[i]->data == data) s = skbs[i];
    check(s && len == s->len, "map-exact-pushed-length");
    if (map_fail) { pthread_mutex_unlock(&ledger_lock); return UINT64_MAX; }
    check(ledger_count < 4096, "ledger-capacity");
    dma_addr_t d = next_dma; next_dma += 0x10000;
    ledger[ledger_count++] = (struct mapping){s,d,len,dev,dir,true}; ++maps;
    event("MAP %u %llu %zu\n", s->id, (unsigned long long)d, len);
    pthread_mutex_unlock(&ledger_lock); return d;
}
static bool dma_mapping_error(struct device *dev, dma_addr_t dma) { check(dev == &pdev.dev, "map-error-device"); return dma == UINT64_MAX; }
static void dma_unmap_single(struct device *dev, dma_addr_t dma, size_t len, int dir) {
    check(!held_lock, "unmap-outside-slot-lock"); point(4);
    pthread_mutex_lock(&ledger_lock);
    struct mapping *m = NULL;
    for (unsigned i=0; i<ledger_count; ++i)
        if (ledger[i].live && ledger[i].dma == dma) { check(!m, "unique-live-map"); m = &ledger[i]; }
    check(m && m->dev == dev && m->len == len && m->direction == dir, "map-unmap-identity");
    m->live = false; ++unmaps; if (!dma) ++zero_unmaps;
    event("UNMAP %u %llu %zu\n", m->skb->id, (unsigned long long)dma, len);
    pthread_mutex_unlock(&ledger_lock);
}
struct coherent { void *ptr; size_t len; dma_addr_t dma; bool live; };
static struct coherent coherent[16];
static unsigned coherent_count;
static void *dma_alloc_coherent(struct device *dev, size_t n, dma_addr_t *dma, int flags) {
    (void)flags; check(dev == &pdev.dev && coherent_count < 16, "coherent-allocate");
    void *p = calloc(1,n); check(p != NULL, "coherent-memory");
    *dma = 0x400000 + coherent_count*0x1000;
    coherent[coherent_count++] = (struct coherent){p,n,*dma,true}; return p;
}
static void dma_free_coherent(struct device *dev, size_t n, void *ptr, dma_addr_t dma) {
    check(dev == &pdev.dev && !held_lock, "coherent-free-context");
    struct coherent *c = NULL;
    for (unsigned i=0; i<coherent_count; ++i) if (coherent[i].ptr == ptr && coherent[i].live) c = &coherent[i];
    check(c && c->len == n && c->dma == dma, "coherent-free-identity"); c->live = false; free(ptr);
}
uint32_t edma_reg_read(uint32_t off) { check(off/4 < sizeof(registers)/4, "register-range"); return registers[off/4]; }
void edma_reg_write(uint32_t off, uint32_t val) {
    check(off/4 < sizeof(registers)/4, "register-range"); registers[off/4] = val;
    for (unsigned i=0; current && i<current->txdesc_rings; ++i) {
        struct edma_txdesc_ring *r = &current->txdesc_ring[i];
        if (off == EDMA_REG_TXDESC_PROD_IDX(r->id)) {
            unsigned index = (val-1) & (r->count-1);
            struct edma_txdesc_desc *desc = EDMA_TXDESC_DESC(r,index);
            struct mapping *m = &ledger[ledger_count-1]; uint32_t opaque;
            memcpy(&opaque,m->skb->data,sizeof(opaque));
            check(opaque == index && le32_to_cpu(desc->buffer_addr) == (uint32_t)m->dma, "descriptor-opaque-address");
            check((desc->word1 & EDMA_TXDESC_DATA_LENGTH_MASK) == m->len-EDMA_TX_PREHDR_SIZE, "descriptor-payload-length");
#if CANDIDATE
            check(current->tx_slots[index].txdesc_id == r->id, "published-ring-owner");
#endif
            event("PUBLISH %u %u %u\n",r->id,index,val);
        }
    }
}
static void wmb(void) { atomic_thread_fence(memory_order_seq_cst); }
#define CONFIGURE_STUB(kind) static void edma_configure_##kind##_ring(struct edma_hw *h, struct edma_##kind##_ring *r) { (void)h; (void)r; }
CONFIGURE_STUB(txdesc)
CONFIGURE_STUB(txcmpl)
CONFIGURE_STUB(rxdesc)
CONFIGURE_STUB(rxfill)

/* DP_FUNCTIONS */

static void setup(unsigned rings) {
    ++cases; check(!held_lock, "case-lock-balance");
    current = &edma_hw; memset(current,0,sizeof(*current));
    current->pdev = &pdev; current->txdesc_rings = rings; current->txcmpl_rings = 1;
    current->txdesc_ring = calloc(rings,sizeof(*current->txdesc_ring));
    current->txcmpl_ring = calloc(1,sizeof(*current->txcmpl_ring));
    check(current->txdesc_ring && current->txcmpl_ring, "ring-arrays");
    for (unsigned i=0; i<rings; ++i) {
        current->txdesc_ring[i].id = 23-i; current->txdesc_ring[i].count = EDMA_RING_SIZE;
        check(!edma_setup_txdesc_ring_res(current,&current->txdesc_ring[i]), "actual-txdesc-setup");
    }
    current->txcmpl_ring[0].id = 7; current->txcmpl_ring[0].count = EDMA_RING_SIZE;
    check(!edma_setup_txcmpl_ring_res(current,&current->txcmpl_ring[0]), "actual-txcmpl-setup");
    edma_configure_rings(current);
    memset(registers,0,sizeof(registers)); memset(&netdev,0,sizeof(netdev)); netdev.priv.macid = 2;
    netdev.needed_headroom = EDMA_TX_PREHDR_SIZE;
    dp_global_ctx.tx_requeue_stop = true; next_dma = 0x100000;
    pad_fail = map_fail = expand_fail = false;
}
static unsigned outstanding(void) { unsigned n=0; for (unsigned i=0;i<ledger_count;++i) n+=ledger[i].live; return n; }
static void finish(void) {
    check(!held_lock && !outstanding(), "all-mappings-retired");
#if CANDIDATE
    for (unsigned i=0;i<EDMA_RING_SIZE;++i) {
        struct edma_tx_slot *s=&current->tx_slots[i];
        check(!s->skb && !s->dma && !s->len && !s->txdesc_id, "empty-tuple-all-fields");
    }
    pthread_mutex_destroy(&current->tx_slot_lock.mutex);
#endif
    for (unsigned i=0;i<current->txdesc_rings;++i) pthread_mutex_destroy(&current->txdesc_ring[i].tx_lock.mutex);
    for (unsigned i=0;i<coherent_count;++i) if (coherent[i].live) {
        dma_free_coherent(&pdev.dev,coherent[i].len,coherent[i].ptr,coherent[i].dma);
    }
    for (unsigned i=0;i<skb_count;++i) { check(skbs[i]->freed, "every-input-consumed"); free(skbs[i]); }
    free(current->txdesc_ring); free(current->txcmpl_ring); current=NULL;
    ledger_count=skb_count=coherent_count=0;
}
static enum edma_tx send_on(unsigned ring, struct sk_buff *s) { return edma_ring_xmit(current,&netdev,s,&current->txdesc_ring[ring]); }
static void completion(unsigned opaque) {
    struct edma_txcmpl_ring *r=current->txcmpl_ring;
    unsigned p=edma_reg_read(EDMA_REG_TXCMPL_PROD_IDX(r->id));
    ((struct edma_txcmpl_desc *)r->desc)[p].buffer_addr=cpu_to_le32(opaque);
    registers[EDMA_REG_TXCMPL_PROD_IDX(r->id)/4]=(p+1)%r->count;
}
static void clean(void) { check(edma_clean_tx(current,current->txcmpl_ring)==1, "one-completion-consumed"); }
static void success_trace(void) {
    setup(1);
    for (unsigned i=0;i<5;++i) {
        struct sk_buff *s=new_skb(i+1,i ? 60+i : 20);
        if (!i) next_dma=0;
        s->shinfo.tx_flags=SKBTX_HW_TSTAMP;
        check(send_on(0,s)==EDMA_TX_OK, "producer-success");
        registers[EDMA_REG_TXDESC_CONS_IDX(23)/4]=edma_reg_read(EDMA_REG_TXDESC_PROD_IDX(23));
        completion(i); clean();
    }
    finish();
}
static void exits(void) {
    for (unsigned mode=0;mode<8;++mode) {
        setup(1); struct sk_buff *s=new_skb(1,mode==1 ? 20 : 64);
        struct nss_dp_data_plane_ctx ctx={&netdev};
        if (mode==0) registers[EDMA_REG_TXDESC_CONS_IDX(23)/4]=1;
        if (mode==1) pad_fail=true;
        if (mode==2) map_fail=true;
        if (mode==3) s->nonlinear=true;
        if (mode==4) s->len=1;
        if (mode==5) {s->cloned=true; expand_fail=true;}
        if (mode==6) {registers[EDMA_REG_TXDESC_CONS_IDX(23)/4]=1; dp_global_ctx.tx_requeue_stop=false;}
        if (mode==7) s->cloned=true;
        unsigned before=maps; int ret=edma_if_xmit(&ctx,s);
        check(!held_lock, "producer-return-lock-balance");
        if (mode==6) {check(ret==NETDEV_TX_BUSY && netdev.stopped && !s->freed && s->len==64, "busy-not-consumed");dev_kfree_skb_any(s);}
        else check(ret==NETDEV_TX_OK, "wrapper-consumed-return");
        if (mode==7) {check(maps==before+1, "expanded-success"); completion(0);clean();}
        else check(maps==before, "failure-no-map-publication");
        finish();
    }
}
static void occupied_and_wrap(void) {
    setup(3);
    for (unsigned n=0;n<EDMA_RING_SIZE*3+5;++n) {
        unsigned ring=n%3,index=n%EDMA_RING_SIZE;
        unsigned id=current->txdesc_ring[ring].id;
        registers[EDMA_REG_TXDESC_PROD_IDX(id)/4]=index;
        registers[EDMA_REG_TXDESC_CONS_IDX(id)/4]=(index+2)%EDMA_RING_SIZE;
        struct sk_buff *a=new_skb(n*2+1,60+n%32),*b=new_skb(n*2+2,70);
        enum edma_tx ret = send_on(ring,a);
        if(ret!=EDMA_TX_OK) fprintf(stderr,"wrap n=%u ring=%u index=%u ret=%d prod=%u cons=%u\n",n,ring,index,ret,edma_reg_read(EDMA_REG_TXDESC_PROD_IDX(id)),edma_reg_read(EDMA_REG_TXDESC_CONS_IDX(id)));
        check(ret==EDMA_TX_OK, "wrap-publish");
        unsigned peer=(ring+1)%3;
        unsigned peer_id=current->txdesc_ring[peer].id;
        registers[EDMA_REG_TXDESC_PROD_IDX(peer_id)/4]=index;
        registers[EDMA_REG_TXDESC_CONS_IDX(peer_id)/4]=(index+2)%EDMA_RING_SIZE;
        check(send_on(peer,b)==EDMA_TX_DESC && b->len==70 && !held_lock, "occupied-other-ring");
        dev_kfree_skb_any(b); completion(index); clean();
    }
    completion(EDMA_RING_SIZE); clean(); completion(UINT32_MAX); clean(); completion(0); clean();
    finish();
}
static void teardown_cases(void) {
    for (unsigned mode=0;mode<4;++mode) {
        setup(2); struct sk_buff *s=new_skb(1,63);
        next_dma=mode==3 ? UINT64_C(0x100100000) : (mode ? 0x100000 : 0);
        check(send_on(0,s)==EDMA_TX_OK, "teardown-publish");
        if (mode==0 || mode==3) {
            if (mode==3) s->len+=7; /* The saved map argument must win. */
            edma_cleanup_txdesc_ring_res(current,&current->txdesc_ring[0]);
            completion(0); clean();
        } else if (mode==1) {
            registers[EDMA_REG_TXDESC_PROD_IDX(22)/4]=1;
            edma_cleanup_txdesc_ring_res(current,&current->txdesc_ring[1]);
            check(!s->freed && outstanding()==1, "foreign-ring-not-claimed");
            completion(0); clean();
        } else {
            registers[EDMA_REG_TXDESC_CONS_IDX(23)/4]=1;
            completion(0); edma_cleanup_txcmpl_ring_res(current,current->txcmpl_ring);
            check(s->freed && !outstanding(), "txcmpl-teardown-indirect-take");
        }
        finish();
    }
}
static struct sk_buff *race_b;
static void *clean_worker(void *unused) { (void)unused; cleaner_thread=true; clean(); return NULL; }
static void *producer_worker(void *unused) { (void)unused; producer_thread=true; check(send_on(0,race_b)==EDMA_TX_OK,"race-producer-success");return NULL; }
static void race(unsigned mode) {
    setup(1); struct sk_buff *a=new_skb(1,60); race_b=new_skb(2,70);
    check(send_on(0,a)==EDMA_TX_OK,"race-initial"); completion(0);
    registers[EDMA_REG_TXDESC_PROD_IDX(23)/4]=0;
    registers[EDMA_REG_TXDESC_CONS_IDX(23)/4]=2;
    pthread_mutex_lock(&schedule_lock); schedule_mode=(int)mode;
    paused=released=attempted=false;hook_seen=0;pthread_mutex_unlock(&schedule_lock);
    pthread_t c,p;check(!pthread_create(&c,NULL,clean_worker,NULL),"clean-thread");
    pthread_mutex_lock(&schedule_lock);
    while(!paused)pthread_cond_wait(&schedule_cond,&schedule_lock);
    pthread_mutex_unlock(&schedule_lock);
    check(!pthread_create(&p,NULL,producer_worker,NULL),"producer-thread");
    pthread_mutex_lock(&schedule_lock);
    while(!attempted)pthread_cond_wait(&schedule_cond,&schedule_lock);
#if CANDIDATE
    if(mode!=4) check(pthread_mutex_trylock(&current->tx_slot_lock.mutex)==EBUSY,"take-excludes-producer");
    else {
        pthread_mutex_unlock(&schedule_lock); check(!pthread_join(p,NULL),"reuse-join");
        pthread_mutex_lock(&schedule_lock);
    }
#else
    pthread_mutex_unlock(&schedule_lock);check(!pthread_join(p,NULL),"old-race-join");pthread_mutex_lock(&schedule_lock);
#endif
    released=true;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);
    check(!pthread_join(c,NULL),"clean-join");
#if CANDIDATE
    if(mode!=4) check(!pthread_join(p,NULL),"producer-join");
#endif
    schedule_mode=0; completion(0);clean();finish();
}
int main(int argc,char **argv) {
    check(argc==2,"mode-argument");
    if(!strcmp(argv[1],"trace")) {trace_on=true;success_trace();return 0;}
    if(!strcmp(argv[1],"race-a")) {race(1);return 0;}
    if(!strcmp(argv[1],"race-b")) {race(2);return 0;}
    if(!strcmp(argv[1],"reuse")) {race(4);return 0;}
    check(!strcmp(argv[1],"suite"),"known-mode");
    success_trace();exits();occupied_and_wrap();teardown_cases();
    for(unsigned i=0;i<20;++i) {race(1);race(2);race(4);}
    check(maps==unmaps && zero_unmaps>0 && expansions>0 && timestamps>0,"summary-map-counts");
    printf("cases=%u checks=%u maps=%u unmaps=%u zero_unmaps=%u frees=%u\n",cases,atomic_load(&checks),maps,unmaps,zero_unmaps,frees);
    return 0;
}
