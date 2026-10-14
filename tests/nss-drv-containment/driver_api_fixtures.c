/* API fixtures and deterministic observers only; selected DRV logic is real C. */
static pthread_mutex_t rendezvous=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t rendezvous_cond=PTHREAD_COND_INITIALIZER;
static int events[128],event_core[128],event_count;
static bool hold_config,config_entered,release_config,writer_done;
static bool hold_notify,notify_entered,release_notify;
static unsigned notify_calls;
static unsigned override_calls,start_calls,restore_calls,hal_unregister_calls,stats_clean_calls,hal_register_calls,ops_prepare_calls,probe_calls;
static int override_result;
static struct net_device port,napi_devices[NSS_MAX_CORES];
static struct nss_data_plane_ops host_plane_ops={ .data_plane_register=__nss_data_plane_register, .data_plane_unregister=__nss_data_plane_unregister };
static void host_observe(enum host_api_event event,int core) {
    assert(pthread_mutex_lock(&rendezvous)==0); assert(event_count<128);
    events[event_count]=event; event_core[event_count++]=core;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
}
static void free_irq(unsigned irq,void *cookie) {
    struct int_ctx_instance *ctx=cookie; assert(ctx && ctx->irq==irq && irq && !ctx->napi.active);
    host_observe(HOST_IRQ_FREE,ctx->nss_ctx->id);
}
static struct net_device *nss_dp_get_netdev_by_nss_if_num(int number) { return number==1 ? &port : NULL; }
static bool nss_dp_is_in_open_state(struct net_device *dev) { assert(dev==&port); return dev->host_admin_up; }
static int nss_dp_override_data_plane(struct net_device *dev,struct nss_dp_data_plane_ops *ops,struct nss_dp_data_plane_ctx *ctx) {
    assert(dev==&port && ops==&dp_ops && ctx->dev==dev); override_calls++; return override_result;
}
static void nss_dp_start_data_plane(struct net_device *dev,struct nss_dp_data_plane_ctx *ctx) { assert(dev==&port && ctx->dev==dev); start_calls++; }
static void nss_dp_restore_data_plane(struct net_device *dev) { assert(dev==&port); restore_calls++; }
static void nss_dp_receive(struct net_device *dev,struct sk_buff *skb,struct napi_struct *napi) { (void)dev; (void)skb; (void)napi; }
static void nss_phys_if_register_handler(struct nss_ctx_instance *ctx,int number) { assert(ctx && number==1); }
static void nss_data_plane_hal_add_dp_ops(struct nss_dp_data_plane_ops *ops) { assert(ops==&dp_ops); ops_prepare_calls++; }
static void nss_data_plane_hal_register(struct nss_ctx_instance *ctx) { assert(ctx); hal_register_calls++; }
static void nss_data_plane_hal_unregister(struct nss_ctx_instance *ctx) { assert(ctx); hal_unregister_calls++; }
static void nss_stats_clean(void) { stats_clean_calls++; }
static void nss_hal_disable_interrupt(struct nss_ctx_instance *ctx,unsigned shift,unsigned mask) { assert(ctx && shift<NSS_MAX_IRQ_PER_CORE && mask==NSS_HAL_SUPPORTED_INTERRUPTS); }
static void nss_hal_enable_interrupt(struct nss_ctx_instance *ctx,unsigned shift,unsigned mask) { assert(ctx && shift<NSS_MAX_IRQ_PER_CORE && mask==NSS_HAL_SUPPORTED_INTERRUPTS); host_irq_rearm_calls++; }
/* Never invokes firmware, panic, coredump, hardware, or the real notifier. */
static void nss_fw_coredump_notify(struct nss_ctx_instance *ctx,unsigned status) {
    assert(ctx==&nss_top_main.nss[0] && status==0);
    assert(pthread_mutex_lock(&rendezvous)==0); notify_calls++; notify_entered=true;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0);
    while(hold_notify && !release_notify) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(pthread_mutex_unlock(&rendezvous)==0); host_observe(HOST_NOTIFY_RETURN,ctx->id);
}
/* Only the actual public probe admission wrapper is tested, not probe setup. */
static int __nss_hal_probe(struct platform_device *dev) { assert(dev); probe_calls++; return 0; }
static int nss_n2h_update_queue_config_sync(struct nss_ctx_instance *ctx,bool enabled,uint16_t *limits) {
    assert(ctx==&nss_top_main.nss[0]); (void)enabled; (void)limits;
    assert(pthread_mutex_lock(&rendezvous)==0);
    if(hold_config) { config_entered=true; assert(pthread_cond_broadcast(&rendezvous_cond)==0); while(!release_config) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0); }
    assert(pthread_mutex_unlock(&rendezvous)==0); return NSS_TX_SUCCESS;
}
static int nss_project_pri_mq_map_configure(struct nss_ctx_instance *ctx) { assert(ctx==&nss_top_main.nss[0]); return NSS_TX_SUCCESS; }
static bool initialized;
static void setup(void) {
    if(initialized) for(int core=0;core<NSS_MAX_CORES;core++) for(int i=0;i<NSS_MAX_IRQ_PER_CORE;i++) {
        struct napi_struct *napi=&nss_top_main.nss[core].int_ctx[i].napi;
        assert(!napi->active && !napi->tail_active);
        assert(pthread_mutex_destroy(&napi->lock)==0); assert(pthread_cond_destroy(&napi->cond)==0);
    }
    memset(&nss_top_main,0,sizeof(nss_top_main)); memset(nss_data_plane_params,0,sizeof(nss_data_plane_params));
    memset(&port,0,sizeof(port)); memset(napi_devices,0,sizeof(napi_devices));
    nss_top_main.num_nss=NSS_MAX_CORES; nss_top_main.data_plane_ops=&host_plane_ops;
    for(int core=0;core<NSS_MAX_CORES;core++) {
        struct nss_ctx_instance *ctx=&nss_top_main.nss[core];
        ctx->nss_top=&nss_top_main; ctx->id=core; ctx->num_irq=1; ctx->napi_ndev=&napi_devices[core]; napi_devices[core].host_core=core;
        for(int i=0;i<NSS_MAX_IRQ_PER_CORE;i++) {
            struct int_ctx_instance *irq=&ctx->int_ctx[i]; irq->nss_ctx=ctx; irq->irq=i==0 ? 100+core : 0; irq->shift_factor=i;
            irq->napi.host_core=core; irq->napi.enabled=irq->irq!=0;
            assert(pthread_mutex_init(&irq->napi.lock,NULL)==0); assert(pthread_cond_init(&irq->napi.cond,NULL)==0);
        }
    }
    event_count=override_calls=start_calls=restore_calls=hal_unregister_calls=stats_clean_calls=hal_register_calls=ops_prepare_calls=probe_calls=0;
    hold_config=config_entered=release_config=writer_done=false;
    hold_notify=notify_entered=release_notify=false; notify_calls=host_napi_complete_calls=host_irq_rearm_calls=0;
    override_result=0; host_create_fail=false; initialized=true;
}
static void passed(const char *name) { printf("PASS %s\n",name); }
static int event_index(enum host_api_event event,int core) { for(int i=0;i<event_count;i++) if(events[i]==(int)event && event_core[i]==core) return i; return -1; }
HOST_EXTRACTED_FUNCTIONS
