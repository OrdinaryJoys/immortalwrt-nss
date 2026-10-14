/* Reduced opaque NSS scaffolding, not target ABI or replacement DRV logic.
 * Exact registry/int_ctx/ndpp/API structures are inserted by the extractor. */
HOST_EXTRACTED_STRUCTURES
struct nss_ctx_instance {
    struct nss_top_instance *nss_top;
    int id,num_irq;
    struct int_ctx_instance int_ctx[NSS_MAX_IRQ_PER_CORE];
    struct nss_subsystem_dataplane_register subsys_dp_register[NSS_MAX_NET_INTERFACES];
    struct net_device *napi_ndev;
    void *nmap,*vmap;
};
struct nss_top_instance {
    int num_nss;
    struct nss_ctx_instance nss[NSS_MAX_CORES];
    struct nss_data_plane_ops *data_plane_ops;
    int phys_if_handler_id[NSS_MAX_NET_INTERFACES];
};
static struct nss_top_instance nss_top_main;
static struct nss_data_plane_param nss_data_plane_params[NSS_DP_MAX_INTERFACES];
static struct nss_dp_data_plane_ops dp_ops;
static int nss_skip_nw_process;
bool pn_mq_en;
uint16_t pn_qlimits[NSS_MAX_NUM_PRI];
/* Actual functions are forward declared only to order the extracted units. */
static void __nss_data_plane_register(struct nss_ctx_instance *);
static void __nss_data_plane_unregister(void);
static bool nss_data_plane_register_to_nss_dp(struct nss_ctx_instance *,int);
void nss_core_register_subsys_dp(struct nss_ctx_instance *,uint32_t,nss_phys_if_rx_callback_t,nss_phys_if_rx_ext_data_callback_t,void *,struct net_device *,uint32_t);
void nss_core_unregister_subsys_dp(struct nss_ctx_instance *,uint32_t);
HOST_COMMON_API_DECLARATIONS
