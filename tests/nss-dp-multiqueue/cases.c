/* Only API callbacks, fault injection and assertions; DP functions are extracted. */
enum stage {
    S_NONE, S_INIT, S_VSI, S_MAC, S_MTU, S_OPEN, S_GMAC, S_LINK_UP,
    S_LINK_DOWN, S_UNASSIGN, S_STOP, S_CLOSE, S_DEINIT, S_COUNT
};
struct port {
    struct net_device dev;
    struct nss_dp_dev dp;
    struct nss_dp_data_plane_ctx native_ctx, nss_ctx;
    struct nss_dp_data_plane_ops native_ops, nss_ops;
    struct nss_gmac_hal_dev gmac;
    struct nss_gmac_hal_ops gmac_ops;
    struct phy_device phy;
    enum stage fault;
    unsigned calls[S_COUNT], retires, xmits;
};
static struct port ports[2];
static struct port *owner(struct net_device *dev)
{
    for (unsigned i=0; i<2; i++)
        if (dev == &ports[i].dev) return &ports[i];
    host_internal(false, "unknown-device");
    return NULL;
}
static struct net_device *host_other_device(struct net_device *dev)
{
    return &ports[dev == &ports[0].dev ? 1 : 0].dev;
}
static unsigned starts(const struct net_device *dev)
{
    unsigned n=0;
    for (unsigned i=0; i<4; i++) n+=dev->txq[i].starts;
    return n;
}
static unsigned wakes(const struct net_device *dev)
{
    unsigned n=0;
    for (unsigned i=0; i<4; i++) n+=dev->txq[i].wakes;
    return n;
}
static unsigned schedules(const struct net_device *dev)
{
    unsigned n=0;
    for (unsigned i=0; i<4; i++) n+=dev->txq[i].schedules;
    return n;
}
static int callback(struct net_device *dev, enum stage stage)
{
    struct port *p=owner(dev);
    p->calls[stage]++;
    return p->fault == stage ? -EIO : 0;
}
static int op_init(struct nss_dp_data_plane_ctx *c) { return callback(c->dev, S_INIT); }
static int op_close(struct nss_dp_data_plane_ctx *c) { return callback(c->dev, S_CLOSE); }
static int op_deinit(struct nss_dp_data_plane_ctx *c) { return callback(c->dev, S_DEINIT); }
static int op_open(struct nss_dp_data_plane_ctx *c, uint32_t tx, uint32_t rx, uint32_t mode)
{
    host_internal(!tx && !rx && !mode, "open-arguments");
    return callback(c->dev, S_OPEN);
}
static int op_link(struct nss_dp_data_plane_ctx *c, uint32_t v)
{
    return callback(c->dev, v ? S_LINK_UP : S_LINK_DOWN);
}
static int op_mac(struct nss_dp_data_plane_ctx *c, uint8_t *addr)
{
    host_internal(addr == c->dev->dev_addr, "mac-device");
    return callback(c->dev, S_MAC);
}
static int op_mtu(struct nss_dp_data_plane_ctx *c, uint32_t mtu)
{
    host_internal(mtu == c->dev->mtu, "mtu-device");
    return callback(c->dev, S_MTU);
}
static int op_pause(struct nss_dp_data_plane_ctx *c, uint32_t v)
{
    (void)c; (void)v; return 0;
}
static int op_vsi(struct nss_dp_data_plane_ctx *c, uint32_t v)
{
    host_internal(v == ((struct nss_dp_dev *)c->dev->priv)->vsi, "vsi-device");
    return callback(c->dev, S_VSI);
}
static int op_unassign(struct nss_dp_data_plane_ctx *c, uint32_t v)
{
    (void)v; return callback(c->dev, S_UNASSIGN);
}
static void op_features(struct nss_dp_data_plane_ctx *c)
{
    c->dev->features=c->dev->hw_features=c->dev->vlan_features=c->dev->wanted_features=7;
}
static netdev_tx_t op_xmit(struct nss_dp_data_plane_ctx *c, struct sk_buff *skb)
{
    owner(c->dev)->xmits++;
    dev_kfree_skb_any(skb);
    return NETDEV_TX_OK;
}
static int32_t gmac_start(struct nss_gmac_hal_dev *g) { return callback(g->netdev, S_GMAC); }
static int32_t gmac_stop(struct nss_gmac_hal_dev *g) { return callback(g->netdev, S_STOP); }
static bool edma_retire_port(struct net_device *dev, uint32_t macid)
{
    struct port *p=owner(dev);
    host_internal(macid == p->dp.macid, "retire-device");
    p->retires++;
    return true;
}
HOST_FUNCTIONS

static void trace(struct port *p, const char *phase)
{
    struct net_device *d=&p->dev;
    printf("{\"case\":\"%s\",\"phase\":\"%s\",\"device\":%u,"
           "\"running\":%d,\"present\":%d,\"carrier\":%d,"
           "\"blocked\":%d,\"pending\":%d,\"quarantined\":%d,"
           "\"queues\":[%lu,%lu,%lu,%lu],\"starts\":%u,\"wakes\":%u,\"schedules\":%u}\n",
           case_name, phase, d->id, d->running, d->device_present, d->carrier,
           p->dp.plane_blocked, p->dp.plane_pending, p->dp.plane_quarantined,
           d->txq[0].state, d->txq[1].state, d->txq[2].state, d->txq[3].state,
           starts(d), wakes(d), schedules(d));
}
static void queues(struct port *p, bool stopped, const char *marker)
{
    for (unsigned i=0; i<4; i++)
        check(!!(p->dev.txq[i].state & BIT(__QUEUE_STATE_DRV_XOFF)) == stopped, marker);
}
static void peer_unchanged(const struct port *snapshot)
{
    check(!memcmp(snapshot, &ports[1], sizeof(*snapshot)), "peer-state");
}
static void setup(bool running, bool phy)
{
    memset(ports, 0, sizeof(ports));
    memset(&dp_global_ctx, 0, sizeof(dp_global_ctx));
    polling_starts=0;
    for (unsigned i=0; i<2; i++) {
        struct port *p=&ports[i];
        p->dev.priv=&p->dp;
        p->dev.id=i;
        p->dev.mtu=1500;
        p->dev.num_tx_queues=p->dev.real_num_tx_queues=4;
        p->dev.running=i ? true : running;
        p->dev.carrier=p->dev.running;
        p->dev.device_present=true;
        p->native_ctx.dev=p->nss_ctx.dev=&p->dev;
        p->native_ops=(struct nss_dp_data_plane_ops) {
            .init=op_init, .open=op_open, .close=op_close, .deinit=op_deinit,
            .link_state=op_link, .mac_addr=op_mac, .change_mtu=op_mtu,
            .pause_on_off=op_pause, .set_features=op_features, .xmit=op_xmit,
            .vsi_assign=op_vsi, .vsi_unassign=op_unassign
        };
        p->nss_ops=p->native_ops;
        p->gmac.netdev=&p->dev;
        p->gmac_ops.start=gmac_start;
        p->gmac_ops.stop=gmac_stop;
        p->dp.netdev=&p->dev;
        p->dp.macid=i+1;
        p->dp.vsi=10+i;
        p->dp.dpc=&p->native_ctx;
        p->dp.data_plane_ops=&p->native_ops;
        p->dp.gmac_hal_ctx=&p->gmac;
        p->dp.gmac_hal_ops=&p->gmac_ops;
        p->dp.phydev=phy ? &p->phy : NULL;
        nss_dp_plane_init(&p->dp);
        p->dp.phy_started=p->dev.running && phy;
        p->dp.flags=p->dev.running ? BIT(__NSS_DP_UP) : 0;
        p->dp.drv_flags=NSS_DP_PRIV_FLAG(INIT_DONE);
        p->dp.link_state=p->dev.running ? __NSS_DP_LINK_UP : __NSS_DP_LINK_DOWN;
    }
    /* A foreign device has mixed independent queue states, not a boolean. */
    for (unsigned q=0; q<4; q++)
        ports[1].dev.txq[q].state=q;
    check(host_other_device(&ports[0].dev)==&ports[1].dev, "fixture-other-device");
}
static void quiesced(struct port *p)
{
    trace(p, "quiesced");
    check(p->dp.plane_blocked && !p->dev.device_present &&
          !p->dev.carrier && !p->dp.plane_readers, "quiesced-state");
    queues(p, true, "quiesced-queues");
}
static void override_ok(struct port *p)
{
    unsigned before=starts(&p->dev)+wakes(&p->dev);
    check(nss_dp_override_data_plane(&p->dev, &p->nss_ops, &p->nss_ctx)==0, "override-result");
    quiesced(p);
    check(p->dp.plane_pending && p->dp.data_plane_ops==&p->nss_ops &&
          p->dp.dpc==&p->nss_ctx, "override-pair");
    check(starts(&p->dev)+wakes(&p->dev)==before, "pending-no-start");
}
static void ready(struct port *p)
{
    check(!p->dp.plane_blocked && !p->dp.plane_pending &&
          !p->dp.plane_quarantined && p->dev.device_present &&
          test_bit(__NSS_DP_UP, &p->dp.flags), "active-state");
    queues(p, false, "queues-ready");
    check(p->dp.plane_readers==0, "reader-balance");
    if (p->dp.phydev)
        check(p->dp.phy_started && !p->dev.carrier &&
              p->phy.starts && p->phy.anegs, "phy-start");
    else
        check(p->dev.carrier && p->dp.link_state==__NSS_DP_LINK_UP, "no-phy-link");
}
static void isolated(struct port *p)
{
    trace(p, "isolated");
    queues(p, true, "quarantine-queues");
    check(p->dp.plane_quarantined && p->dp.plane_blocked &&
          !p->dp.plane_pending && !p->dp.plane_was_open && !p->dp.plane_readers &&
          !p->dev.device_present && !p->dev.carrier &&
          !test_bit(__NSS_DP_UP, &p->dp.flags) &&
          p->dp.data_plane_ops==&nss_dp_quarantine_ops &&
          p->dp.dpc==&p->dp.quarantine_ctx, "quarantine-state");
}
/* Only the net/core/dev.c START bit envelope is substituted, not DP open/close. */
static int linux_open(struct port *p)
{
    check(p->dev.device_present, "open-present");
    p->dev.running=true;
    int ret=nss_dp_open(&p->dev);
    if (ret) p->dev.running=false;
    /* dev_activate/carrier/linkwatch change qdisc state, not DRV_XOFF. */
    p->dev.activations+=!ret;
    trace(p, "ndo-open");
    return ret;
}
static int linux_close(struct port *p)
{
    p->dev.running=false;
    int ret=nss_dp_close(&p->dev);
    trace(p, "ndo-close");
    return ret;
}
static void api_semantics(void)
{
    setup(false, false);
    struct net_device *d=&ports[0].dev;
    for (unsigned i=0; i<4; i++)
        d->txq[i].state=BIT(__QUEUE_STATE_DRV_XOFF)|BIT(__QUEUE_STATE_STACK_XOFF)|BIT(__QUEUE_STATE_FROZEN);
    netif_start_queue(d);
    check(d->txq[0].state==6 && d->txq[1].state==7 &&
          d->txq[2].state==7 && d->txq[3].state==7 && !d->running, "api-single");
    netif_tx_start_all_queues(d);
    for (unsigned i=0; i<4; i++) check(d->txq[i].state==6, "api-all-preserves-other-bits");
    check(!schedules(d), "api-start-no-schedule");
    netif_tx_disable(d);
    netif_device_detach(d);
    netif_device_attach(d);
    queues(&ports[0], true, "api-attach-down");
    check(!wakes(d), "api-attach-down-no-wake");
    d->running=true;
    netif_device_attach(d);
    queues(&ports[0], true, "api-attach-present");
    netif_device_detach(d);
    netif_device_attach(d);
    queues(&ports[0], false, "api-attach-running");
    check(wakes(d)==4 && schedules(d)==4, "api-wake-schedules");
    netif_device_attach(d);
    check(wakes(d)==4, "api-idempotent-attach");
    trace(&ports[0], "api-verified");
}
static void takeover_case(bool up, bool phy, bool uninitialized)
{
    setup(up, phy);
    struct port *p=&ports[0], peer=ports[1];
    if (uninitialized) p->dp.drv_flags=0;
    override_ok(p);
    peer_unchanged(&peer);
    nss_dp_start_data_plane(&p->dev, &p->nss_ctx);
    trace(p, "readiness");
    peer_unchanged(&peer);
    if (!up) {
        queues(p, true, "down-admin-queues");
        check(!starts(&p->dev) && !wakes(&p->dev) && !p->dev.running, "down-admin-no-start");
        check(p->calls[S_OPEN]==0, "down-not-opened-at-readiness");
        check(linux_open(p)==0, "open-result");
        peer_unchanged(&peer);
        check(schedules(&p->dev)==0, "activation-no-schedule");
    } else {
        check(wakes(&p->dev)==4 && schedules(&p->dev)==4, "running-attach-wake");
        check(p->calls[S_OPEN]==1 && p->calls[S_CLOSE]==1, "up-reopened");
    }
    ready(p);
    check(p->calls[S_INIT]==1 && p->calls[S_DEINIT]==(unsigned)!uninitialized,
          "takeover-init-deinit");
    check(polling_starts==1, "polling-once");
}
static void reopen_case(bool phy)
{
    setup(true, phy);
    struct port *p=&ports[0], peer=ports[1];
    override_ok(p);
    nss_dp_start_data_plane(&p->dev, &p->nss_ctx);
    ready(p);
    for (unsigned n=0; n<3; n++) {
        check(linux_close(p)==0, "close-result");
        check(!test_bit(__NSS_DP_UP, &p->dp.flags) && !p->dev.carrier, "closed-state");
        check(linux_open(p)==0, "reopen-result");
        ready(p);
        peer_unchanged(&peer);
    }
    check(polling_starts==1, "reopen-polling-once");
}
static void quarantine_case(void)
{
    setup(true, true);
    struct port *p=&ports[0], peer=ports[1];
    unsigned before=starts(&p->dev)+wakes(&p->dev);
    nss_dp_restore_data_plane(&p->dev);
    isolated(p);
    check(starts(&p->dev)+wakes(&p->dev)==before, "quarantine-no-start");
    nss_dp_plane_resume(&p->dp);
    nss_dp_start_data_plane(&p->dev, &p->nss_ctx);
    check(nss_dp_open(&p->dev)==-ENODEV, "quarantine-open-denied");
    check(nss_dp_override_data_plane(&p->dev,&p->nss_ops,&p->nss_ctx)==-ENODEV,
          "quarantine-override-denied");
    struct sk_buff skb={0};
    check(nss_dp_xmit(&skb,&p->dev)==NETDEV_TX_OK && skb.freed==1 &&
          p->dev.stats.tx_dropped==1 && p->xmits==0, "quarantine-xmit-dropped");
    check(nss_dp_close(&p->dev)==0, "quarantine-close");
    isolated(p);
    check(starts(&p->dev)+wakes(&p->dev)==before, "quarantine-no-start");
    peer_unchanged(&peer);
}
static void pending_case(bool wrong_readiness)
{
    setup(false, true);
    struct port *p=&ports[0], peer=ports[1];
    override_ok(p);
    if (wrong_readiness) {
        nss_dp_start_data_plane(&p->dev, &p->native_ctx);
        isolated(p);
    } else {
        check(nss_dp_open(&p->dev)==-ENODEV, "pending-open-denied");
        quiesced(p);
        check(!starts(&p->dev) && !wakes(&p->dev), "pending-no-start");
    }
    peer_unchanged(&peer);
}
static void error_case(enum stage fault, bool readiness, bool takeover, bool closing)
{
    setup(readiness || closing || takeover, false);
    struct port *p=&ports[0], peer=ports[1];
    if (fault==S_INIT && !takeover) p->dp.drv_flags=0;
    if (!takeover && fault!=S_INIT) {
        override_ok(p);
        if (!readiness) nss_dp_start_data_plane(&p->dev, &p->nss_ctx);
    }
    p->fault=fault;
    unsigned before=starts(&p->dev)+wakes(&p->dev);
    unsigned called_before=p->calls[fault];
    int ret=0;
    if (takeover) ret=nss_dp_override_data_plane(&p->dev,&p->nss_ops,&p->nss_ctx);
    else if (readiness) nss_dp_start_data_plane(&p->dev,&p->nss_ctx);
    else if (closing) ret=linux_close(p);
    else ret=linux_open(p);
    trace(p, "injected-error");
    check(starts(&p->dev)+wakes(&p->dev)==before, "error-no-start");
    check(p->calls[fault]==called_before+1, "error-stage-reached-once");
    if (!readiness)
        check(ret==(takeover ? -EIO : (fault==S_INIT ? -ENOMEM : -EAGAIN)), "error-result");
    isolated(p);
    check(nss_dp_open(&p->dev)==-ENODEV, "error-reopen-denied");
    peer_unchanged(&peer);
}
int main(int argc, char **argv)
{
    if (argc!=2) return 2;
    setvbuf(stdout, NULL, _IONBF, 0);
    case_name=argv[1];
    rtnl_held=true;
    if (!strcmp(case_name,"api-semantics")) api_semantics();
    else if (!strcmp(case_name,"down-phy")) takeover_case(false,true,false);
    else if (!strcmp(case_name,"down-no-phy")) takeover_case(false,false,false);
    else if (!strcmp(case_name,"down-uninitialized")) takeover_case(false,false,true);
    else if (!strcmp(case_name,"up-phy")) takeover_case(true,true,false);
    else if (!strcmp(case_name,"up-no-phy")) takeover_case(true,false,false);
    else if (!strcmp(case_name,"reopen-phy")) reopen_case(true);
    else if (!strcmp(case_name,"reopen-no-phy")) reopen_case(false);
    else if (!strcmp(case_name,"quarantine")) quarantine_case();
    else if (!strcmp(case_name,"pending-open")) pending_case(false);
    else if (!strcmp(case_name,"wrong-readiness")) pending_case(true);
    else {
        const char *names[S_COUNT]={"none","init","vsi","mac","mtu","open","gmac",
            "link-up","link-down","unassign","stop","close","deinit"};
        bool matched=false;
        for (unsigned s=1; s<S_COUNT; s++) {
            char name[80];
            const char *modes[]={"open-error","readiness-error","takeover-error","close-error"};
            for (unsigned mode=0; mode<4; mode++) {
                snprintf(name,sizeof(name),"%s-%s",modes[mode],names[s]);
                if (!strcmp(case_name,name)) {
                    error_case((enum stage)s,mode==1,mode==2,mode==3);
                    matched=true;
                }
            }
        }
        if (!matched) return 2;
    }
    printf("{\"pass\":\"%s\"}\n",case_name);
    return 0;
}
