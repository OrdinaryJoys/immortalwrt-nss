/* API/resource substitutes only. The runner inserts byte-preserved driver C. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define BIT(n) (1U << (n))
#define DMA_BIT_MASK(n) ((1ULL << (n)) - 1)
#define CE_ATTR_DIS_INTR BIT(0)
#define IRQ_NOAUTOEN BIT(0)
#define IRQ_DISABLE_UNLAZY BIT(1)
#define IRQF_TRIGGER_RISING BIT(2)
#define GFP_KERNEL 0
#define IOMMU_READ 1
#define IOMMU_WRITE 2
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define ATH11K_BUS_AHB 0
#define ATH11K_FIRMWARE_MODE_NORMAL 0
#define ath11k_err(...) ((void)0)
#define dev_err(...) ((void)0)
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
#define PAGE_SIZE 4096
#define DMA_FROM_DEVICE 2
HOST_SOURCE_DECLARATIONS

struct device_node { int fwnode; const char *name; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; void *data; };
struct platform_device_info { void *fwnode; struct device *parent; const char *name; uint64_t dma_mask; };
struct net_device { char name[32]; bool live; };
struct napi_struct { bool attached; };
struct ath11k_base;
struct ath11k_ce_pipe { int intr_tq; };
struct ath11k_ext_irq_grp {
    struct ath11k_base *ab; unsigned grp_id, num_irq;
    unsigned irqs[ATH11K_EXT_IRQ_NUM_MAX];
    struct net_device *napi_ndev; struct napi_struct napi;
};
struct ath11k_hw_params {
    bool hybrid_bus_type, fixed_fw_mem;
    u32 ce_count; u8 max_radios;
    const struct ath11k_hw_ring_mask *ring_mask;
};
struct iommu_domain { int unused; };
struct ath11k_ahb {
    struct rproc *tgt_rproc;
    dma_addr_t msi_addr;
    bool msi_addr_mapped;
    struct { bool use_tz; struct device *dev; struct iommu_domain *iommu_domain;
             uint64_t msa_paddr, ce_paddr; size_t msa_size, ce_size; } fw;
};
enum ath11k_hw_rev { ATH11K_HW_IPQ8074, ATH11K_HW_IPQ6018_HW10, ATH11K_HW_IPQ5018_HW10,
                     ATH11K_HW_WCN6750_HW10, ATH11K_HW_QCN6122_HW10 };
struct ath11k_hif_ops { int unused; };
struct ath11k_pci_ops { int unused; };
static const struct ath11k_hif_ops ath11k_ahb_hif_ops_ipq8074, ath11k_ahb_hif_ops_wcn6750, ath11k_ahb_hif_ops_qcn6122;
static const struct ath11k_pci_ops ath11k_ahb_pci_ops_wcn6750;
struct ath11k_base {
    struct ath11k_hw_params hw_params;
    struct { bool enabled; } nss;
    struct { struct ath11k_ce_pipe ce_pipe[16]; } ce;
    struct ath11k_ext_irq_grp ext_irq_grp[ATH11K_EXT_IRQ_GRP_NUM_MAX];
    int irq_num[ATH11K_IRQ_NUM_MAX];
    struct { const struct ath11k_hif_ops *ops; } hif;
    struct platform_device *pdev; struct device *dev;
    enum ath11k_hw_rev hw_rev; int userpd_id, fw_mode;
    struct ath11k_ahb ahb;
};
static struct ath11k_base base;
static struct device_node node = { .name="wifi-firmware" };
static struct device host_device = { .of_node=&node };
static struct platform_device firmware_device;
static struct iommu_domain domain;
static struct net_device devices[ATH11K_EXT_IRQ_GRP_NUM_MAX];
static void *irq_owners[256];
static unsigned checks, failures, bad_api, live_irqs, live_devices, live_napi;
static unsigned lookup_calls, request_calls, allocation_calls;
static unsigned skip_ce, selected_rev;
static bool selected_nss, selected_hybrid, core_live, pcic_live, child_present;
static unsigned core_calls, core_before_irq, free_live_core, live_resources, node_refs, iommu_live, attached, mappings;
enum fault { NONE, LOOKUP, REQUEST, ALLOCATION };
static enum fault fault_kind;
static unsigned fault_at;
static uint64_t success_signatures[6];
enum stage { DMA=1, BASE_ALLOC, PCI_OPS, PRE_INIT, RESOURCES, CE_REMAP, FW_RESOURCES,
             SMP, HAL, CE_ALLOC, RPROC, CORE_INIT, MSA, FW_REGISTER, DMA_CONFIG,
             DOMAIN_ALLOC, DOMAIN_ATTACH, MAP_MSA, MAP_CE };
static enum stage fail_stage;
#define CHECK(expr) do { checks++; if (!(expr)) { if (failures < 12) fprintf(stderr,"failed line %d: %s\n",__LINE__,#expr); failures++; } } while(0)
static int failed(enum stage s) { return s==fail_stage ? -EIO : 0; }
static void reset(bool nss, unsigned skip) {
    memset(&base,0,sizeof(base)); memset(devices,0,sizeof(devices)); memset(irq_owners,0,sizeof(irq_owners));
    selected_nss=nss; selected_hybrid=false; skip_ce=skip; selected_rev=ATH11K_HW_IPQ8074;
    base.hw_params.ce_count=12; base.hw_params.max_radios=3;
    base.hw_params.ring_mask=&ath11k_hw_ring_mask_ipq8074; base.nss.enabled=nss;
    base.dev=&host_device;
    fault_kind=NONE; fault_at=0; fail_stage=0; core_live=pcic_live=false; child_present=true;
    bad_api=live_irqs=live_devices=live_napi=lookup_calls=request_calls=allocation_calls=0;
    core_calls=core_before_irq=free_live_core=live_resources=node_refs=iommu_live=attached=mappings=0;
}
static int ath11k_ce_get_attr_flags(struct ath11k_base *ab,int i) { (void)ab; return skip_ce&BIT(i) ? CE_ATTR_DIS_INTR : 0; }
static int ath11k_hw_get_mac_from_pdev_id(struct ath11k_hw_params *hw,int i) { (void)hw; return ath11k_hw_ipq8074_mac_from_pdev_id(i); }
static int platform_get_irq_byname(struct platform_device *pdev,const char *name) {
    (void)pdev; lookup_calls++;
    if (fault_kind==LOOKUP && lookup_calls==fault_at) return -517;
    for (unsigned i=0;i<ATH11K_IRQ_NUM_MAX;i++) if (!strcmp(name,irq_name[i])) return i==ATH11K_IRQ_CE0_OFFSET ? 0 : (int)i+100;
    bad_api++; return -EINVAL;
}
static int request_irq(int irq,void (*handler)(void),unsigned flags,const char *name,void *owner) {
    (void)handler;(void)flags;(void)name; request_calls++;
    if (irq<0 || irq>=256) { bad_api++;return -EINVAL; }
    if (fault_kind==REQUEST && request_calls==fault_at) return -ENXIO;
    if (irq_owners[irq]) { bad_api++; return -EBUSY; }
    irq_owners[irq]=owner;live_irqs++;return 0;
}
static void free_irq(int irq,void *owner) {
    if (irq<0 || irq>=256 || irq_owners[irq]!=owner) {bad_api++;return;}
    irq_owners[irq]=NULL;live_irqs--;
}
static void irq_set_status_flags(int irq,unsigned flags) { (void)flags;if(irq<0)bad_api++; }
static struct net_device *alloc_netdev_dummy(int size) {
    (void)size; allocation_calls++;
    if (fault_kind==ALLOCATION && allocation_calls==fault_at) return NULL;
    struct net_device *d=&devices[allocation_calls-1];d->live=true;live_devices++;return d;
}
static void free_netdev(struct net_device *d) {if(!d||!d->live){bad_api++;return;}d->live=false;live_devices--;}
static void netif_napi_add(struct net_device *d,struct napi_struct *n,void (*poll)(void)) {
    (void)poll;if(!d||!d->live||n->attached)bad_api++;n->attached=true;live_napi++;
}
static void netif_napi_del(struct napi_struct *n) {if(!n->attached){bad_api++;return;}n->attached=false;live_napi--;}
static void ath11k_ahb_ext_grp_napi_poll(void) { }
static void ath11k_ahb_ce_interrupt_handler(void) { }
static void ath11k_ahb_ext_interrupt_handler(void) { }
static void ath11k_ahb_ce_tasklet(void) { }
static void tasklet_setup(int *tasklet,void (*func)(void)) {(void)func;*tasklet=1;}
static int ath11k_pcic_config_irq(struct ath11k_base *ab) {(void)ab;pcic_live=true;return 0;}
static void ath11k_pcic_free_irq(struct ath11k_base *ab) {(void)ab;if(!pcic_live)bad_api++;pcic_live=false;}
static void *device_get_match_data(struct device *d) {(void)d;return (void*)(uintptr_t)selected_rev;}
static int ath11k_get_userpd_id(struct device *d) {(void)d;return 0;}
static int dma_set_mask_and_coherent(struct device *d,uint64_t mask) {(void)d;(void)mask;return failed(DMA);}
static struct ath11k_base *ath11k_core_alloc(struct device *d,size_t size,int bus) {
    (void)size;(void)bus;if(failed(BASE_ALLOC))return NULL;base.dev=d;live_resources|=BIT(BASE_ALLOC);return &base;
}
static void platform_set_drvdata(struct platform_device *p,void *data) {p->data=data;}
static int ath11k_pcic_register_pci_ops(struct ath11k_base *ab,const struct ath11k_pci_ops *ops) {(void)ab;(void)ops;return failed(PCI_OPS);}
static int ath11k_core_pre_init(struct ath11k_base *ab) {ab->hw_params.hybrid_bus_type=selected_hybrid;return failed(PRE_INIT);}
static int ath11k_ahb_setup_resources(struct ath11k_base *ab) {(void)ab;return failed(RESOURCES);}
static int acquire(enum stage s) {int ret=failed(s);if(!ret)live_resources|=BIT(s);return ret;}
static void release(enum stage s) {if(!(live_resources&BIT(s)))bad_api++;live_resources&=~BIT(s);}
static int ath11k_ahb_ce_remap(struct ath11k_base *ab) {(void)ab;return acquire(CE_REMAP);}
static void ath11k_ahb_ce_unmap(struct ath11k_base *ab) {(void)ab;release(CE_REMAP);}
static int host_fw_resources(struct ath11k_base *ab) {(void)ab;return acquire(FW_RESOURCES);}
static int host_fw_deinit(struct ath11k_base *ab) {(void)ab;release(FW_RESOURCES);return 0;}
static int ath11k_ahb_setup_smp2p_handle(struct ath11k_base *ab) {(void)ab;return acquire(SMP);}
static void ath11k_ahb_release_smp2p_handle(struct ath11k_base *ab) {(void)ab;release(SMP);}
static int ath11k_hal_srng_init(struct ath11k_base *ab) {(void)ab;return acquire(HAL);}
static void ath11k_hal_srng_deinit(struct ath11k_base *ab) {(void)ab;release(HAL);}
static int ath11k_ce_alloc_pipes(struct ath11k_base *ab) {(void)ab;return acquire(CE_ALLOC);}
static void ath11k_ce_free_pipes(struct ath11k_base *ab) {(void)ab;release(CE_ALLOC);}
static void ath11k_ahb_init_qmi_ce_config(struct ath11k_base *ab) {(void)ab;}
static int ath11k_core_get_rproc(struct ath11k_base *ab) {(void)ab;return failed(RPROC);}
static int ath11k_core_init(struct ath11k_base *ab) {
    (void)ab;core_calls++;if(!live_irqs&&!pcic_live)core_before_irq++;
    if(failed(CORE_INIT))
        return -EIO;
    core_live=true;
    return 0;
}
static void ath11k_core_free(struct ath11k_base *ab) {(void)ab;if(core_live)free_live_core++;release(BASE_ALLOC);}
/* The IRQ-only fixture never acquires providers: any release is unexpected. */
static void rproc_put(struct rproc *rproc) {(void)rproc;bad_api++;}
static void dma_unmap_resource(struct device *device,dma_addr_t address,size_t size,int direction,unsigned attrs) {
    (void)device;(void)address;(void)size;(void)direction;(void)attrs;bad_api++;
}
static void ath11k_qmi_fwreset_from_cold_boot(struct ath11k_base *ab) {(void)ab;}
static struct ath11k_ahb *ath11k_ahb_priv(struct ath11k_base *ab) {return &ab->ahb;}
static struct device_node *of_get_child_by_name(struct device_node *parent,const char *name) {
    (void)parent;(void)name;if(!child_present)return NULL;node_refs++;return &node;
}
static void of_node_put(struct device_node *n) {if(n!=&node||!node_refs)bad_api++;else node_refs--;}
static int ath11k_ahb_setup_msa_resources(struct ath11k_base *ab) {
    ab->ahb.fw.msa_paddr=0x1000;ab->ahb.fw.ce_paddr=0x4000;
    ab->ahb.fw.msa_size=ab->ahb.fw.ce_size=0x1000;return failed(MSA);
}
static struct platform_device *platform_device_register_full(struct platform_device_info *i) {
    (void)i;if(failed(FW_REGISTER))return ERR_PTR(-EIO);live_resources|=BIT(FW_REGISTER);return &firmware_device;
}
static void platform_device_unregister(struct platform_device *p) {if(p!=&firmware_device)bad_api++;release(FW_REGISTER);}
static struct platform_device *to_platform_device(struct device *d) {return (struct platform_device*)d;}
static int of_dma_configure(struct device *d,struct device_node *n,bool force) {(void)d;(void)n;(void)force;return failed(DMA_CONFIG);}
static struct iommu_domain *iommu_paging_domain_alloc(struct device *d) {
    (void)d;if(failed(DOMAIN_ALLOC))return ERR_PTR(-ENOMEM);iommu_live++;return &domain;
}
static int iommu_attach_device(struct iommu_domain *d,struct device *dev) {(void)d;(void)dev;if(failed(DOMAIN_ATTACH))return -EIO;attached++;return 0;}
static int iommu_map(struct iommu_domain *d,uint64_t iova,uint64_t pa,size_t size,int access,int flags) {
    (void)d;(void)pa;(void)size;(void)access;(void)flags;
    if(failed(iova==0x1000?MAP_MSA:MAP_CE))
        return -EIO;
    mappings++;
    return 0;
}
static size_t iommu_unmap(struct iommu_domain *d,uint64_t iova,size_t size) {(void)d;(void)iova;if(!mappings)bad_api++;else mappings--;return size;}
static void iommu_detach_device(struct iommu_domain *d,struct device *dev) {(void)d;(void)dev;if(!attached)bad_api++;else attached--;}
static void iommu_domain_free(struct iommu_domain *d) {(void)d;if(!iommu_live)bad_api++;else iommu_live--;}
HOST_DRIVER_FUNCTIONS

static bool no_irq_resources(void) {return !live_irqs&&!live_devices&&!live_napi&&!bad_api&&!pcic_live;}
static uint64_t irq_signature(void) {
    uint64_t sig=1469598103934665603ULL;
    for(unsigned irq=0;irq<256;irq++)if(irq_owners[irq]) {
        unsigned owner=0;
        for(unsigned i=0;i<12;i++)if(irq_owners[irq]==&base.ce.ce_pipe[i])owner=1+i;
        for(unsigned i=0;i<ATH11K_EXT_IRQ_GRP_NUM_MAX;i++)if(irq_owners[irq]==&base.ext_irq_grp[i])owner=64+i;
        sig=(sig^irq)*1099511628211ULL;sig=(sig^owner)*1099511628211ULL;
    }
    return sig;
}
static void irq_matrix(void) {
    for(unsigned nss=0;nss<2;nss++)for(unsigned skipped=0;skipped<3;skipped++) {
        unsigned mask=skipped==0?0:skipped==1?0xaaa:0xfff;
        reset(nss,mask);int ret=ath11k_ahb_config_irq(&base);
        unsigned lookups=lookup_calls,requests=request_calls,allocs=allocation_calls;
        CHECK(!ret&&!bad_api&&live_devices==ATH11K_EXT_IRQ_GRP_NUM_MAX);
        success_signatures[nss*3+skipped]=irq_signature();
        ath11k_ahb_free_irq(&base);CHECK(no_irq_resources());
#ifdef HOST_FIXED_IRQ_OWNERSHIP
        ath11k_ahb_free_irq(&base);CHECK(no_irq_resources());
#endif
        for(unsigned kind=LOOKUP;kind<=ALLOCATION;kind++) {
            unsigned count=kind==LOOKUP?lookups:kind==REQUEST?requests:allocs;
            for(unsigned at=1;at<=count;at++) {
                reset(nss,mask);fault_kind=kind;fault_at=at;
                ret=ath11k_ahb_config_irq(&base);
                CHECK(ret==(kind==LOOKUP?-517:kind==REQUEST?-ENXIO:-ENOMEM));CHECK(no_irq_resources());
            }
        }
    }
    reset(true,0);base.hw_params.hybrid_bus_type=true;
    CHECK(!ath11k_ahb_config_irq(&base)&&pcic_live&&!request_calls&&!allocation_calls);
    ath11k_ahb_free_irq(&base);CHECK(no_irq_resources());
}
static void probe_matrix(void) {
    for(unsigned hybrid=0;hybrid<2;hybrid++) {
        for(unsigned s=DMA;s<=CORE_INIT;s++) {
            reset(true,0xaaa);selected_hybrid=hybrid;selected_rev=hybrid?ATH11K_HW_WCN6750_HW10:ATH11K_HW_IPQ8074;
            fail_stage=s;struct platform_device p={0};
            int ret=ath11k_ahb_probe(&p);
            CHECK(ret<0);CHECK(!live_resources&&!core_live&&!free_live_core&&!core_before_irq&&!p.data);
            CHECK(no_irq_resources());
        }
    }
    for(unsigned kind=LOOKUP;kind<=ALLOCATION;kind++) {
        reset(true,0xaaa);fault_kind=kind;fault_at=2;struct platform_device p={0};
        CHECK(ath11k_ahb_probe(&p)<0);CHECK(!core_calls&&!core_live&&!free_live_core&&!live_resources);
        CHECK(no_irq_resources());
    }
    reset(true,0xaaa);struct platform_device p={0};
    CHECK(!ath11k_ahb_probe(&p)&&p.data==&base&&core_live&&!core_before_irq);
    core_live=false;ath11k_ahb_free_irq(&base);host_fw_deinit(&base);
    ath11k_ce_free_pipes(&base);ath11k_hal_srng_deinit(&base);
    ath11k_ahb_release_smp2p_handle(&base);ath11k_ahb_ce_unmap(&base);ath11k_core_free(&base);
    CHECK(!live_resources&&no_irq_resources());
}
static void firmware_matrix(void) {
    reset(true,0);CHECK(!ath11k_ahb_fw_resources_init(&base)&&!node_refs);
    reset(true,0);base.hw_params.fixed_fw_mem=true;child_present=false;
    CHECK(!ath11k_ahb_fw_resources_init(&base)&&base.ahb.fw.use_tz&&!node_refs);
    for(unsigned s=MSA;s<=MAP_CE;s++) {
        reset(true,0);base.hw_params.fixed_fw_mem=true;fail_stage=s;
        CHECK(ath11k_ahb_fw_resources_init(&base)<0);
        CHECK(!node_refs&&!live_resources&&!iommu_live&&!attached&&!mappings&&!bad_api);
    }
    reset(true,0);base.hw_params.fixed_fw_mem=true;
    CHECK(!ath11k_ahb_fw_resources_init(&base)&&!node_refs&&iommu_live==1&&attached==1&&mappings==2);
    CHECK(!ath11k_ahb_fw_resource_deinit(&base)&&!live_resources&&!iommu_live&&!attached&&!mappings&&!bad_api);
}
int main(void) {
    irq_matrix();unsigned irq_checks=checks,irq_failures=failures;
    probe_matrix();unsigned probe_checks=checks-irq_checks,probe_failures=failures-irq_failures;
    firmware_matrix();
    printf("{\"checks\":%u,\"failures\":%u,\"resource_apis_modeled\":true,\"hardware_tested\":false,"
           "\"groups\":{\"irq\":{\"checks\":%u,\"failures\":%u},\"probe\":{\"checks\":%u,\"failures\":%u},"
           "\"firmware\":{\"checks\":%u,\"failures\":%u}},\"native_success_signatures\":[",checks,failures,irq_checks,irq_failures,
           probe_checks,probe_failures,checks-irq_checks-probe_checks,failures-irq_failures-probe_failures);
    for(unsigned i=0;i<6;i++)printf("%s\"%016llx\"",i?",":"",(unsigned long long)success_signatures[i]);
    puts("]}");
    return failures?1:0;
}
