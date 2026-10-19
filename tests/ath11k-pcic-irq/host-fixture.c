/* Host resource substitutes; the runner inserts unmodified prepared C. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define CE_ATTR_DIS_INTR BIT(0)
#define IRQF_SHARED BIT(1)
#define IRQF_NOBALANCING BIT(2)
#define IRQ_DISABLE_UNLAZY BIT(3)
#define ATH11K_FLAG_MULTI_MSI_VECTORS 0
#define EXPORT_SYMBOL(s)
#define ath11k_dbg(...) ((void)0)
#define ath11k_err(...) ((void)0)
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
HOST_DECLARATIONS

struct net_device { char name[32]; bool live; };
struct napi_struct { bool attached; };
struct ath11k_base;
struct ath11k_ce_pipe { int intr_tq; };
struct ath11k_ext_irq_grp {
    struct ath11k_base *ab; unsigned grp_id, num_irq;
    unsigned irqs[ATH11K_EXT_IRQ_NUM_MAX];
    struct net_device *napi_ndev; struct napi_struct napi;
};
struct ath11k_base {
    struct { bool hybrid_bus_type; unsigned ce_count;
             const struct ath11k_hw_ring_mask *ring_mask; } hw_params;
    struct { bool enabled; } nss;
    struct { struct ath11k_ce_pipe ce_pipe[12]; } ce;
    struct ath11k_ext_irq_grp ext_irq_grp[ATH11K_EXT_IRQ_GRP_NUM_MAX];
    int irq_num[ATH11K_IRQ_NUM_MAX];
    unsigned long dev_flags;
    struct { struct { const struct ath11k_msi_config *config; u32 ep_base_data; } msi; } pci;
};
struct ath11k_pci { struct ath11k_base *ab; };
struct action { int irq; void *owner; unsigned flags; bool live; };
static struct ath11k_base base;
static struct net_device devices[ATH11K_EXT_IRQ_GRP_NUM_MAX];
static struct action actions[64];
static bool affinity_hint[64];
static unsigned disabled[64], checks, failures, bad_api;
static unsigned live_irq, live_ndev, live_napi, skip_mask;
static unsigned lookup_calls, request_calls, allocation_calls;
static unsigned ce_freed, disable_calls;
static bool assignment_ce_error, assignment_dp_error, post_config_error;
enum fault { NO_FAULT, LOOKUP, REQUEST, ALLOCATION };
static enum fault fault_kind;
static unsigned fault_at;
static uint64_t signatures[48];
#define CHECK(x) do { checks++; if (!(x)) { if (failures < 12) fprintf(stderr,"line %d: %s\n",__LINE__,#x); failures++; } } while (0)
static bool test_bit(unsigned bit, const unsigned long *flags) { return !!(*flags & (1UL << bit)); }
static int ath11k_ce_get_attr_flags(struct ath11k_base *ab, int i) { (void)ab; return skip_mask & BIT(i) ? CE_ATTR_DIS_INTR : 0; }
static int ath11k_pcic_get_msi_irq(struct ath11k_base *ab, unsigned vector) {
    lookup_calls++;
    if (fault_kind == LOOKUP && lookup_calls == fault_at) return -517;
    if (vector >= ab->pci.msi.config->total_vectors || vector >= ARRAY_SIZE(disabled)) { bad_api++; return -EINVAL; }
    return vector; /* Includes valid IRQ 0, shared by CE/DP in one-vector mode. */
}
static int request_irq(int irq, void (*handler)(void), unsigned flags, const char *name, void *owner) {
    (void)handler; (void)name; request_calls++;
    if (fault_kind == REQUEST && request_calls == fault_at) return -ENXIO;
    if (irq < 0 || irq >= 64 || !owner || !(flags & IRQF_SHARED)) { bad_api++; return -EINVAL; }
    for (unsigned i=0; i<ARRAY_SIZE(actions); i++)
        if (actions[i].live && actions[i].irq==irq && actions[i].owner==owner) { bad_api++; return -EBUSY; }
    for (unsigned i=0; i<ARRAY_SIZE(actions); i++) if (!actions[i].live) {
        actions[i]=(struct action){ .irq=irq, .owner=owner, .flags=flags, .live=true }; live_irq++; return 0;
    }
    bad_api++; return -ENOMEM;
}
static void free_irq(int irq, void *owner) {
    if (irq < 0 || irq >= 64) { bad_api++; return; }
    /* A stronger ownership contract: the bus clears hints before any free. */
    if (affinity_hint[irq]) bad_api++;
    for (unsigned i=0; i<ARRAY_SIZE(actions); i++)
        if (actions[i].live && actions[i].irq==irq && actions[i].owner==owner) {
            actions[i].live=false; live_irq--; return;
        }
    bad_api++;
}
static int ath11k_pci_set_irq_affinity_hint(struct ath11k_pci *pci, void *hint) {
    (void)pci; (void)hint; memset(affinity_hint,0,sizeof(affinity_hint)); return 0;
}
static int ath11k_pci_config_msi_data(struct ath11k_pci *pci) { (void)pci; return post_config_error ? -EIO : 0; }
static void irq_set_status_flags(int irq, unsigned flags) { (void)flags; if (irq<0 || irq>=64) bad_api++; }
static void disable_irq_nosync(int irq) {
    if (irq<0 || irq>=64) { bad_api++; return; } disabled[irq]++; disable_calls++;
}
static struct net_device *alloc_netdev_dummy(int size) {
    (void)size; allocation_calls++;
    if (fault_kind==ALLOCATION && allocation_calls==fault_at) return NULL;
    struct net_device *d=&devices[allocation_calls-1]; d->live=true; live_ndev++; return d;
}
static void free_netdev(struct net_device *d) { if (!d || !d->live) { bad_api++; return; } d->live=false; live_ndev--; }
static void netif_napi_add(struct net_device *d, struct napi_struct *n, void (*poll)(void)) {
    (void)poll; if (!d || !d->live || n->attached) bad_api++; n->attached=true; live_napi++;
}
static void netif_napi_del(struct napi_struct *n) { if (!n->attached) { bad_api++; return; } n->attached=false; live_napi--; }
static void tasklet_setup(int *tasklet, void (*func)(void)) { (void)func; *tasklet=1; }
static void ath11k_pcic_ce_tasklet(void) {}
static void ath11k_pcic_ce_interrupt_handler(void) {}
static void ath11k_pcic_ext_interrupt_handler(void) {}
static void ath11k_pcic_ext_grp_napi_poll(void) {}
static void ath11k_ce_free_pipes(struct ath11k_base *ab) { (void)ab; ce_freed++; }
HOST_FUNCTIONS
HOST_CALL_SITES

static const struct ath11k_hw_ring_mask *const masks[] = {
    &ath11k_hw_ring_mask_qca6390, &ath11k_hw_ring_mask_qcn9074,
    &ath11k_hw_ring_mask_wcn6750, &ath11k_hw_ring_mask_qcn6122
};
static const unsigned profile_ce_count[] = { HOST_CE_COUNTS };
static const enum ath11k_hw_rev revisions[] = {
    ATH11K_HW_QCA6390_HW20, ATH11K_HW_QCN9074_HW10,
    ATH11K_HW_WCN6750_HW10, ATH11K_HW_QCN6122_HW10
};
static void reset(unsigned profile, bool multi, bool nss, unsigned skip) {
    memset(&base,0,sizeof(base)); memset(devices,0,sizeof(devices)); memset(actions,0,sizeof(actions));
    memset(affinity_hint,0,sizeof(affinity_hint)); memset(disabled,0,sizeof(disabled));
    base.hw_params.ce_count=profile_ce_count[profile]; base.hw_params.ring_mask=masks[profile];
    base.nss.enabled=nss; base.dev_flags=multi ? BIT(ATH11K_FLAG_MULTI_MSI_VECTORS) : 0;
    base.hw_params.hybrid_bus_type=true;
    base.pci.msi.config=&msi_config_one_msi;
    if (multi) for (unsigned i=0; i<ARRAY_SIZE(ath11k_msi_config); i++)
        if (ath11k_msi_config[i].hw_rev==revisions[profile]) base.pci.msi.config=&ath11k_msi_config[i];
    skip_mask=skip; bad_api=live_irq=live_ndev=live_napi=ce_freed=disable_calls=0;
    lookup_calls=request_calls=allocation_calls=0; fault_kind=NO_FAULT; fault_at=0;
    assignment_ce_error=assignment_dp_error=post_config_error=false;
}
static bool clean(void) { return !live_irq && !live_ndev && !live_napi && !bad_api; }
static uint64_t signature(void) {
    uint64_t s=1469598103934665603ULL;
    for (unsigned i=0; i<ARRAY_SIZE(actions); i++) if (actions[i].live) {
        unsigned owner=0;
        for (unsigned j=0;j<12;j++) if(actions[i].owner==&base.ce.ce_pipe[j]) owner=1+j;
        for (unsigned j=0;j<ATH11K_EXT_IRQ_GRP_NUM_MAX;j++) if(actions[i].owner==&base.ext_irq_grp[j]) owner=64+j;
        s=(s^(unsigned)actions[i].irq)*1099511628211ULL; s=(s^owner)*1099511628211ULL;
        s=(s^actions[i].flags)*1099511628211ULL;
    }
    for (unsigned i=0;i<ARRAY_SIZE(disabled);i++) s=(s^disabled[i])*1099511628211ULL;
    return s;
}
static void matrix(void) {
    unsigned profile_idx=0;
    for (unsigned p=0;p<4;p++) for(unsigned multi=0;multi<2;multi++)
    for(unsigned nss=0;nss<2;nss++) for(unsigned skip=0;skip<3;skip++) {
        unsigned mask=skip==0?0:skip==1?0xaaa:0xfff;
        reset(p,multi,nss,mask);
        int ret=host_pci_config_call(&base);
        unsigned lookups=lookup_calls, requests=request_calls, allocs=allocation_calls;
        CHECK(!ret && !bad_api && live_ndev==ATH11K_EXT_IRQ_GRP_NUM_MAX);
        CHECK(multi || !disable_calls); signatures[profile_idx++]=signature();
        ath11k_pcic_free_irq(&base); CHECK(clean());
#ifdef HOST_FIXED
        ath11k_pcic_free_irq(&base); CHECK(clean());
#endif
        for(unsigned bus=0;bus<2;bus++) for(unsigned kind=LOOKUP;kind<=ALLOCATION;kind++) {
            unsigned count=kind==LOOKUP?lookups:kind==REQUEST?requests:allocs;
            for(unsigned at=1;at<=count;at++) {
                reset(p,multi,nss,mask); fault_kind=kind; fault_at=at;
                if (!multi && !bus) affinity_hint[0]=true;
                ret=bus?host_ahb_config_call(&base):host_pci_config_call(&base);
                CHECK(ret==(kind==LOOKUP?-517:kind==REQUEST?-ENXIO:-ENOMEM)); CHECK(clean());
#ifdef HOST_FIXED
                ath11k_pcic_free_irq(&base); CHECK(clean());
#endif
            }
        }
    }
}
static void exceptional(void) {
    for(unsigned multi=0;multi<2;multi++) {
        reset(1,multi,true,0); post_config_error=true;
        if (!multi) affinity_hint[0]=true;
        CHECK(host_pci_config_call(&base)==-EIO); CHECK(clean());
    }
    for(unsigned bus=0;bus<2;bus++) for(unsigned dp=0;dp<2;dp++) {
        reset(1,true,true,0); assignment_dp_error=dp; assignment_ce_error=!dp;
        int ret=bus?host_ahb_config_call(&base):host_pci_config_call(&base);
        CHECK(ret==-EINVAL); CHECK(clean());
    }
#ifdef HOST_FIXED
    /* Malformed MSI counts must not reach modulo-by-zero. Upstream static
     * tables are positive; these are candidate-only defensive boundary tests. */
    for(unsigned bus=0;bus<2;bus++) for(unsigned dp=0;dp<2;dp++) {
        reset(1,true,false,0);
        struct ath11k_msi_user users[2]={{ .name="CE", .num_vectors=dp?5:0, .base_vector=0 },
                                      { .name="DP", .num_vectors=dp?0:8, .base_vector=5 }};
        struct ath11k_msi_config config={ .total_users=2, .total_vectors=13, .users=users };
        base.pci.msi.config=&config;
        CHECK((bus?host_ahb_config_call(&base):host_pci_config_call(&base))==-EINVAL); CHECK(clean());
    }
#endif
    /* A successful new request may share a vector with an unrelated owner.
     * The driver's free must remove its own dev_id only. */
    reset(1,false,false,0); int external;
    CHECK(!request_irq(0,NULL,IRQF_SHARED,"external",&external));
    CHECK(!host_pci_config_call(&base)); ath11k_pcic_free_irq(&base);
    CHECK(live_irq==1 && !live_ndev && !live_napi && !bad_api);
    free_irq(0,&external); CHECK(clean());
}
int main(void) {
    matrix(); exceptional();
    printf("{\"checks\":%u,\"failures\":%u,\"success_signatures\":[",checks,failures);
    for(unsigned i=0;i<ARRAY_SIZE(signatures);i++) printf("%s\"%llu\"",i?",":"",(unsigned long long)signatures[i]);
    puts("]}"); return failures?1:0;
}
