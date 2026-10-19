/* Only fixtures, API callbacks and assertions live here; DP logic is extracted. */
enum read_kind { NONE, XMIT, RFS, PHY, STATS, RECEIVE, KIND_COUNT };
static pthread_mutex_t rendezvous = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t rendezvous_cond = PTHREAD_COND_INITIALIZER;
static int block_kind, callback_entered, release_callback, writer_waiting, writer_done;
static atomic_uint reads[KIND_COUNT];
static unsigned init_calls, close_calls, deinit_calls, open_calls;
static int init_result, close_result, deinit_result, open_result, link_result;
static struct nss_dp_data_plane_ctx *deinit_ctx;
static struct net_device dev;
static struct nss_dp_dev dp;
static struct phy_device phy;
static struct nss_dp_data_plane_ctx old_ctx, new_ctx;
static struct rps_dev_flow_table flow_table;
static struct rps_sock_flow_table sock_table;
static struct netdev_rx_queue rxqueue;
static void host_writer_waiting(void) {
    assert(pthread_mutex_lock(&rendezvous)==0); writer_waiting=1;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
}
static void callback(enum read_kind kind, struct nss_dp_data_plane_ctx *ctx) {
    assert(ctx==&old_ctx || ctx==&new_ctx); assert(ctx->dev==&dev);
    atomic_fetch_add(&reads[kind],1);
    assert(pthread_mutex_lock(&rendezvous)==0);
    if ((int)kind==block_kind && !callback_entered) {
        assert(ctx==&old_ctx); callback_entered=1;
        assert(pthread_cond_broadcast(&rendezvous_cond)==0);
        while(!release_callback) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    }
    assert(pthread_mutex_unlock(&rendezvous)==0);
}
static int host_init(struct nss_dp_data_plane_ctx *ctx) { assert(ctx==&old_ctx || ctx==&new_ctx); init_calls++; return init_result; }
static int host_close(struct nss_dp_data_plane_ctx *ctx) { assert(ctx==&old_ctx || ctx==&new_ctx); close_calls++; return close_result; }
static int host_deinit(struct nss_dp_data_plane_ctx *ctx) { deinit_ctx=ctx; deinit_calls++; return deinit_result; }
static int host_open(struct nss_dp_data_plane_ctx *ctx, uint32_t tx, uint32_t rx, uint32_t mode) { (void)ctx; (void)tx; (void)rx; (void)mode; open_calls++; return open_result; }
static int host_link(struct nss_dp_data_plane_ctx *ctx, uint32_t state) { (void)state; callback(PHY,ctx); return link_result; }
static int host_mac(struct nss_dp_data_plane_ctx *ctx, uint8_t *mac) { (void)ctx; (void)mac; return 0; }
static int host_mtu(struct nss_dp_data_plane_ctx *ctx, uint32_t mtu) { (void)ctx; (void)mtu; return 0; }
static int host_pause(struct nss_dp_data_plane_ctx *ctx, uint32_t pause) { (void)ctx; (void)pause; return 0; }
static netdev_tx_t host_xmit(struct nss_dp_data_plane_ctx *ctx, struct sk_buff *skb) { callback(XMIT,ctx); dev_kfree_skb_any(skb); return NETDEV_TX_OK; }
static void host_features(struct nss_dp_data_plane_ctx *ctx) { struct net_device *ndev=ctx->dev; ndev->features=ndev->hw_features=ndev->vlan_features=ndev->wanted_features=0xff; }
static int host_rfs(struct nss_dp_data_plane_ctx *ctx, struct sk_buff *skb, uint32_t cpu, bool add) { (void)skb; (void)cpu; (void)add; callback(RFS,ctx); return 0; }
static void host_stats(struct nss_dp_data_plane_ctx *ctx, struct nss_dp_gmac_stats *stats) { (void)stats; callback(STATS,ctx); }
static void host_napi_receive(struct napi_struct *napi, struct sk_buff *skb) {
    assert(napi && skb->dev==&dev && skb->protocol==0x0800);
    /* A delivery API substitute, not a registry/netdev lifetime model. */
    callback(RECEIVE,dp.dpc); dev_kfree_skb_any(skb);
}
static int host_ethtool(struct nss_gmac_hal_dev *ctx, uint64_t *data, struct nss_dp_gmac_stats *stats) { (void)ctx; (void)stats; *data=123; return 0; }
static int host_sset_count(struct nss_gmac_hal_dev *ctx, int set) { (void)ctx; assert(set==ETH_SS_STATS); return 1; }
static struct nss_dp_data_plane_ops old_ops = { .init=host_init, .open=host_open, .close=host_close, .link_state=host_link, .mac_addr=host_mac, .change_mtu=host_mtu, .xmit=host_xmit, .set_features=host_features, .pause_on_off=host_pause, .deinit=host_deinit, .rx_flow_steer=host_rfs, .get_stats=host_stats };
static struct nss_dp_data_plane_ops new_ops;
static struct nss_dp_data_plane_ops default_ops;
static struct nss_dp_data_plane_ctx dp_global_data_plane_ctx[NSS_DP_MAX_PORTS];
static struct nss_dp_data_plane_ops *nss_dp_hal_get_data_plane_ops(void) { return &default_ops; }
HOST_EXTRACTED_FUNCTIONS
static const struct net_device_ops host_ndo={ .ndo_open=nss_dp_open, .ndo_stop=nss_dp_close };
static struct nss_gmac_hal_ops host_gmac={ .getethtoolstats=host_ethtool, .getssetcount=host_sset_count };
static bool initialized;
static void setup(bool up, bool overridden) {
    if(initialized) { assert(pthread_mutex_destroy(&dp.plane_lock)==0); assert(pthread_mutex_destroy(&dp.plane_wait.lock)==0); assert(pthread_cond_destroy(&dp.plane_wait.cond)==0); }
#ifdef HOST_DP_STATS_CACHE
    if(initialized) assert(pthread_mutex_destroy(&dp.stats_lock)==0);
#endif
    memset(&dev,0,sizeof(dev)); memset(&dp,0,sizeof(dp)); memset(&phy,0,sizeof(phy));
#ifdef HOST_DP_STATS_CACHE
    spin_lock_init(&dp.stats_lock);
#endif
    old_ctx.dev=new_ctx.dev=&dev; dev.priv=&dp; dev.netdev_ops=&host_ndo; dev.mtu=1500;
    dev.features=0x11; dev.hw_features=0x22; dev.vlan_features=0x44; dev.wanted_features=0x88;
    dev.queue_started=dev.carrier=up; dev.device_present=true;
    dp.macid=1; dp.netdev=&dev; dp.dpc=&old_ctx; dp.data_plane_ops=&old_ops; dp.gmac_hal_ops=&host_gmac;
    nss_dp_plane_init(&dp); dp.plane_wait.reader_lock=&dp.plane_lock; initialized=true;
    dp.flags=up ? 1UL<<__NSS_DP_UP : 0; dp.drv_flags=NSS_DP_PRIV_FLAG(INIT_DONE)|(overridden ? NSS_DP_PRIV_FLAG(INIT_OVERRIDE) : 0);
    new_ops=default_ops=old_ops;
    init_result=close_result=deinit_result=open_result=link_result=0; init_calls=close_calls=deinit_calls=open_calls=0; deinit_ctx=NULL;
    block_kind=callback_entered=release_callback=writer_waiting=writer_done=0;
    for(int i=0;i<KIND_COUNT;i++) atomic_store(&reads[i],0);
    memset(&flow_table,0,sizeof(flow_table)); memset(&sock_table,0,sizeof(sock_table));
    flow_table.log=1; sock_table.mask=1; sock_table.ents[0]=1; rxqueue.rps_flow_table=&flow_table;
    dev._rx=&rxqueue; net_hotdata.rps_sock_flow_table=&sock_table; net_hotdata.rps_cpu_mask=3;
}
static void isolated(void) {
    struct nss_dp_plane_ref ref;
    assert(nss_dp_plane_is_quarantined(&dp)); assert(!nss_dp_plane_get(&dp,&ref));
    assert(dp.data_plane_ops==&nss_dp_quarantine_ops && dp.dpc==&dp.quarantine_ctx);
    assert(dp.plane_readers==0 && dp.plane_blocked && !dp.plane_pending && !dp.plane_was_open);
    assert(!(dev.features|dev.hw_features|dev.vlan_features|dev.wanted_features));
    assert(!test_bit(__NSS_DP_UP,&dp.flags)); assert(!(dp.drv_flags&(NSS_DP_PRIV_FLAG(INIT_DONE)|NSS_DP_PRIV_FLAG(INIT_OVERRIDE))));
    assert(!dev.queue_started && !dev.carrier && !dev.device_present);
}
static void detach(void) { rtnl_lock(); nss_dp_restore_data_plane(&dev); rtnl_unlock(); }
static void passed(const char *name) { printf("PASS %s\n",name); }
static void call_reader(enum read_kind kind, struct sk_buff *skb) {
    struct ethtool_stats stats={0}; struct napi_struct napi={0};
    struct { uint64_t data[5]; uint64_t canary; } sample={{0},0x12345678};
    if(kind==XMIT) assert(nss_dp_xmit(skb,&dev)==NETDEV_TX_OK);
    else if(kind==RFS) { int result=nss_dp_rx_flow_steer(&dev,skb,0,0); assert(result==0 || result==-ENODEV); }
    else if(kind==PHY) nss_dp_adjust_link(&dev);
    else if(kind==STATS) { nss_dp_get_ethtool_stats(&dev,&stats,sample.data); assert(sample.canary==0x12345678); }
    else if(kind==RECEIVE) nss_dp_receive(&dev,skb,&napi);
    else assert(0);
}
static void *reader_thread(void *arg) { struct sk_buff skb={.len=100}; call_reader((enum read_kind)(intptr_t)arg,&skb); return NULL; }
static void *writer_thread(void *arg) {
    (void)arg; detach(); assert(pthread_mutex_lock(&rendezvous)==0); writer_done=1;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0); return NULL;
}
static void drain_case(enum read_kind kind,const char *name) {
    pthread_t reader,writer; struct nss_dp_plane_ref ref; struct sk_buff new_skb={.len=100};
    setup(true,true); phy.link=true; phy.speed=1000; dp.phydev=&phy; dp.phy_started=true; dp.link_state=__NSS_DP_LINK_DOWN;
    block_kind=kind;
    assert(pthread_create(&reader,NULL,reader_thread,(void *)(intptr_t)kind)==0);
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(!callback_entered) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_create(&writer,NULL,writer_thread,NULL)==0);
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(!writer_waiting) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(!writer_done); assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(dp.data_plane_ops==&old_ops && dp.dpc==&old_ctx); assert(!nss_dp_plane_get(&dp,&ref));
    unsigned before=atomic_load(&reads[kind]); call_reader(kind,&new_skb); assert(atomic_load(&reads[kind])==before);
    if(kind==XMIT) assert(new_skb.freed==1 && dev.stats.tx_dropped==1);
    if(kind==RECEIVE) assert(new_skb.freed==1 && dev.stats.rx_dropped==1);
    assert(pthread_mutex_lock(&rendezvous)==0); release_callback=1;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0);
    assert(pthread_join(reader,NULL)==0); assert(pthread_join(writer,NULL)==0);
    isolated(); assert(close_calls==0 && deinit_calls==0); passed(name);
}
static int teardown_turn;
static void *two_teardowns(void *arg) {
    int turn=(int)(intptr_t)arg;
    assert(pthread_mutex_lock(&rendezvous)==0);
    while(teardown_turn!=turn) assert(pthread_cond_wait(&rendezvous_cond,&rendezvous)==0);
    assert(pthread_mutex_unlock(&rendezvous)==0); detach();
    assert(pthread_mutex_lock(&rendezvous)==0); teardown_turn++;
    assert(pthread_cond_broadcast(&rendezvous_cond)==0); assert(pthread_mutex_unlock(&rendezvous)==0); return NULL;
}
int main(void) {
    setup(false,true); detach(); isolated(); assert(close_calls==0 && deinit_calls==0); passed("candidate_down_detach_clears_four_masks_without_hardware_callback");
    setup(true,true); detach(); isolated(); assert(close_calls==0 && atomic_load(&reads[PHY])==0); passed("candidate_up_detach_clears_four_masks_without_nss_close_or_link");
    setup(true,true); detach(); rtnl_lock();
    assert(nss_dp_open(&dev)==-ENODEV); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==-ENODEV);
    nss_dp_start_data_plane(&dev,&new_ctx); nss_dp_plane_resume(&dp); assert(nss_dp_close(&dev)==0); rtnl_unlock();
    isolated(); assert(init_calls==0 && close_calls==0); passed("permanent_latch_refuses_reopen_restart_reoverride_resume");
    setup(true,true); detach(); detach(); detach(); isolated(); assert(close_calls==0 && deinit_calls==0); passed("repeated_detach_idempotent_no_hardware_callback");
    setup(true,true); teardown_turn=0; pthread_t caller0,caller1;
    assert(pthread_create(&caller1,NULL,two_teardowns,(void *)(intptr_t)1)==0); assert(pthread_create(&caller0,NULL,two_teardowns,(void *)(intptr_t)0)==0);
    assert(pthread_join(caller0,NULL)==0); assert(pthread_join(caller1,NULL)==0); isolated(); assert(teardown_turn==2 && close_calls==0); passed("two_ordered_teardown_callers_same_port_no_reactivation");
    setup(true,true); close_result=-EIO; rtnl_lock(); assert(nss_dp_close(&dev)==-EAGAIN); rtnl_unlock(); isolated(); assert(close_calls==1); passed("normal_close_failure_quarantines_after_reader_release");
    setup(true,true); link_result=-EIO; rtnl_lock(); assert(nss_dp_close(&dev)==-EAGAIN); rtnl_unlock(); isolated(); assert(close_calls==0); passed("normal_close_link_failure_quarantines");
    setup(false,false); init_result=-EIO; rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==-EIO); rtnl_unlock(); isolated(); assert(deinit_ctx==&old_ctx && init_calls==1); passed("initial_takeover_init_failure_quarantines_and_uses_old_deinit_context");
    setup(true,false); close_result=-EIO; rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==-EIO); rtnl_unlock(); isolated(); assert(init_calls==0 && close_calls==1); passed("initial_takeover_close_failure_never_initializes_new_plane");
    setup(false,true); dp.drv_flags&=~NSS_DP_PRIV_FLAG(INIT_DONE); init_result=-EIO; rtnl_lock(); assert(nss_dp_open(&dev)==-ENOMEM); rtnl_unlock(); isolated(); passed("ndo_open_init_failure_quarantines_without_up_publication");
    setup(true,false); rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==0);
    assert(dp.plane_pending && dp.plane_blocked && !nss_dp_plane_is_quarantined(&dp)); assert(deinit_ctx==&old_ctx);
    assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==-EBUSY);
    nss_dp_start_data_plane(&dev,&new_ctx); rtnl_unlock();
    assert(!nss_dp_plane_is_quarantined(&dp) && !dp.plane_blocked && !dp.plane_pending);
    assert(dev.queue_started && dev.carrier && dev.device_present && test_bit(__NSS_DP_UP,&dp.flags));
    assert(dev.features==0xff && dev.hw_features==0xff && dev.vlan_features==0xff && dev.wanted_features==0xff); passed("normal_initial_up_takeover_reopens_only_after_readiness");
    setup(false,false); rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==0); nss_dp_start_data_plane(&dev,&new_ctx);
    assert(!test_bit(__NSS_DP_UP,&dp.flags) && !dev.queue_started && open_calls==0 && dev.device_present);
    assert(nss_dp_open(&dev)==0); rtnl_unlock(); assert(dev.queue_started && open_calls==1); passed("normal_initial_down_takeover_preserves_admin_down_then_opens");
    setup(true,false); rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==0); open_result=-EIO; nss_dp_start_data_plane(&dev,&new_ctx); rtnl_unlock(); isolated(); passed("readiness_open_failure_quarantines");
    setup(false,false); rtnl_lock(); assert(nss_dp_override_data_plane(&dev,&new_ops,&new_ctx)==0); nss_dp_start_data_plane(&dev,&old_ctx); rtnl_unlock(); isolated(); passed("readiness_wrong_context_quarantines");
    setup(true,true); detach(); netif_wake_queue(&dev); struct sk_buff skb={.len=100};
    assert(nss_dp_xmit(&skb,&dev)==NETDEV_TX_OK); assert(skb.freed==1 && dev.stats.tx_dropped==1 && atomic_load(&reads[XMIT])==0);
    passed("externally_woken_queue_still_drops_xmit_exactly_once");
    setup(true,true); detach(); struct sk_buff rx_skb={.len=100}; struct napi_struct napi={0};
    nss_dp_receive(&dev,&rx_skb,&napi);
    assert(rx_skb.freed==1 && dev.stats.rx_dropped==1 && atomic_load(&reads[RECEIVE])==0);
    isolated(); passed("quarantined_actual_receive_refused_counted_and_freed_once");
    drain_case(XMIT,"inflight_xmit_drains_and_new_xmit_is_refused");
    drain_case(RFS,"inflight_rfs_pair_drains_and_new_rfs_is_refused");
    drain_case(PHY,"inflight_phy_link_drains_and_carrier_is_reasserted_off");
    drain_case(STATS,"inflight_actual_ethtool_dp_stats_drains_and_new_reader_is_refused");
    drain_case(RECEIVE,"inflight_actual_receive_delivery_drains_and_new_receive_is_refused");
    return 0;
}
