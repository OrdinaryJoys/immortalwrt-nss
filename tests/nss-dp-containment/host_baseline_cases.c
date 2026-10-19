/* This file contains test assertions/callback substitutes, never the DP logic. */
static int init_result, close_result, deinit_result;
static unsigned init_calls, close_calls, deinit_calls, xmit_calls;
static struct nss_dp_data_plane_ctx *deinit_ctx;
static void host_writer_waiting(void) { }
static int host_init(struct nss_dp_data_plane_ctx *ctx) { (void)ctx; init_calls++; return init_result; }
static int host_close(struct nss_dp_data_plane_ctx *ctx) { (void)ctx; close_calls++; return close_result; }
static int host_deinit(struct nss_dp_data_plane_ctx *ctx) { deinit_ctx=ctx; deinit_calls++; return deinit_result; }
static int host_open(struct nss_dp_data_plane_ctx *ctx, uint32_t tx, uint32_t rx, uint32_t mode) { (void)ctx; (void)tx; (void)rx; (void)mode; return 0; }
static int host_link(struct nss_dp_data_plane_ctx *ctx, uint32_t state) { (void)ctx; (void)state; return 0; }
static int host_mac(struct nss_dp_data_plane_ctx *ctx, uint8_t *mac) { (void)ctx; (void)mac; return 0; }
static int host_mtu(struct nss_dp_data_plane_ctx *ctx, uint32_t mtu) { (void)ctx; (void)mtu; return 0; }
static int host_pause(struct nss_dp_data_plane_ctx *ctx, uint32_t pause) { (void)ctx; (void)pause; return 0; }
static netdev_tx_t host_xmit(struct nss_dp_data_plane_ctx *ctx, struct sk_buff *skb) { (void)ctx; xmit_calls++; dev_kfree_skb_any(skb); return NETDEV_TX_OK; }
static void host_features(struct nss_dp_data_plane_ctx *ctx) { struct net_device *dev=ctx->dev; dev->features=dev->hw_features=dev->vlan_features=dev->wanted_features=0xff; }
static int host_stats(struct nss_gmac_hal_dev *ctx, struct rtnl_link_stats64 *stats) { (void)ctx; stats->rx_packets++; return 0; }
static struct nss_dp_data_plane_ops old_ops = { .init=host_init, .open=host_open, .close=host_close, .link_state=host_link, .mac_addr=host_mac, .change_mtu=host_mtu, .xmit=host_xmit, .set_features=host_features, .pause_on_off=host_pause, .deinit=host_deinit };
static struct nss_dp_data_plane_ops default_ops;
static struct nss_dp_data_plane_ctx dp_global_data_plane_ctx[NSS_DP_MAX_PORTS];
static struct nss_dp_data_plane_ops *nss_dp_hal_get_data_plane_ops(void) { return &default_ops; }
/* Actual extracted functions are inserted here by the runner. */
HOST_EXTRACTED_FUNCTIONS
static const struct net_device_ops host_ndo={ .ndo_open=nss_dp_open, .ndo_stop=nss_dp_close };
static struct nss_gmac_hal_ops host_gmac={ .getndostats=host_stats };
static struct net_device dev;
static struct nss_dp_dev dp;
static struct nss_dp_data_plane_ctx old_ctx, new_ctx;
#ifdef HOST_DP_STATS_CACHE
static bool initialized;
#endif
static void setup(bool up) {
#ifdef HOST_DP_STATS_CACHE
    if(initialized) assert(pthread_mutex_destroy(&dp.stats_lock)==0);
#endif
    memset(&dev,0,sizeof(dev)); memset(&dp,0,sizeof(dp));
#ifdef HOST_DP_STATS_CACHE
    spin_lock_init(&dp.stats_lock); initialized=true;
#endif
    old_ctx.dev=new_ctx.dev=&dev;
    dev.priv=&dp; dev.netdev_ops=&host_ndo; dev.mtu=1500;
    dev.features=0x11; dev.hw_features=0x22; dev.vlan_features=0x44; dev.wanted_features=0x88;
    dev.queue_started=dev.carrier=up;
    dp.macid=1; dp.netdev=&dev; dp.dpc=&old_ctx; dp.data_plane_ops=&old_ops; dp.gmac_hal_ops=&host_gmac;
    dp.flags=up ? 1UL<<__NSS_DP_UP : 0; dp.drv_flags=NSS_DP_PRIV_FLAG(INIT_DONE)|NSS_DP_PRIV_FLAG(INIT_OVERRIDE);
    default_ops=old_ops;
    init_result=close_result=deinit_result=0; init_calls=close_calls=deinit_calls=xmit_calls=0; deinit_ctx=NULL;
}
static void passed(const char *name) { printf("PASS %s\n",name); }
int main(void) {
    setup(false); nss_dp_restore_data_plane(&dev);
    assert(dp.data_plane_ops==&default_ops); assert(dp.dpc==&dp_global_data_plane_ctx[0]);
    assert(dev.features==0x11 && dev.hw_features==0x22 && dev.vlan_features==0x44 && dev.wanted_features==0x88);
    passed("baseline_down_restore_preserves_stale_four_masks_control");
    setup(true); nss_dp_restore_data_plane(&dev);
    assert(!(dev.features|dev.hw_features|dev.vlan_features|dev.wanted_features));
    assert(!test_bit(__NSS_DP_UP,&dp.flags)); assert(close_calls==1);
    passed("baseline_up_restore_resets_four_masks_control");
    setup(true); close_result=-EIO; nss_dp_restore_data_plane(&dev);
    assert(dp.data_plane_ops==&default_ops); assert(test_bit(__NSS_DP_UP,&dp.flags));
    assert(!(dev.features|dev.hw_features|dev.vlan_features|dev.wanted_features));
    passed("baseline_ignored_close_failure_retains_up_control");
    setup(false); dp.drv_flags=NSS_DP_PRIV_FLAG(INIT_DONE); init_result=-EIO;
    assert(nss_dp_override_data_plane(&dev,&default_ops,&new_ctx)==-EFAULT);
    assert(dp.data_plane_ops==&default_ops && dp.dpc==&new_ctx);
    assert(dp.drv_flags & NSS_DP_PRIV_FLAG(INIT_OVERRIDE)); assert(!(dp.drv_flags & NSS_DP_PRIV_FLAG(INIT_DONE)));
    passed("baseline_failed_init_leaves_partial_override_control");
    setup(false); dp.drv_flags=NSS_DP_PRIV_FLAG(INIT_DONE);
    assert(nss_dp_override_data_plane(&dev,&default_ops,&new_ctx)==0);
    assert(dp.data_plane_ops==&default_ops && dp.dpc==&new_ctx && init_calls==1 && deinit_calls==1);
    passed("baseline_initial_override_control");
    return 0;
}
