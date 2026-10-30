/* TEST ONLY. No MU wire command is defined or recognized by this program. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <limits.h>
#include <unistd.h>
#include <sys/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint8_t __u8;
typedef uint16_t __u16;
typedef uint32_t __u32;
typedef uint64_t __u64;
typedef int32_t __s32;
typedef uint16_t __kernel_sa_family_t;
/* Unused credential storage: host-OS boundary shim, not a receive API. */
struct ucred { int pid; unsigned int uid, gid; };
#define __aligned_u64 __u64 __attribute__((aligned(8)))
#define STRUCT_PACKED __attribute__((packed))
#define ETH_ALEN 6
#define IFNAMSIZ 16
#define BIT(x) (1U << (x))
#define BIT_ULL(x) (1ULL << (x))
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define min_t(type,a,b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define BUG() abort()
#define NL_DBG(...) ((void)0)
#define MSG_DEBUG 0
#define MSG_INFO 1
#define MSG_WARNING 2
#define MSG_ERROR 3
#define HOSTAPD_MODULE_IEEE80211 0
#define HOSTAPD_LEVEL_DEBUG 0
#define TEST_FAIL_TAG(x) ((void)0)
#define os_memcpy memcpy
#define os_memset memset
#define os_memcmp memcmp
#define os_free free
struct wpa_driver_capa { u64 flags; };
/* @headers@ */

static unsigned checks, cases, leaf_calls, warnings, unknown_events;
static unsigned mu_events, incumbent_events, scheduled, replies;
static int model_wiphy[2];
static int model_iface_wiphy[2];
static int alloc_fail, beacon_fail = -1, role_supp;
static struct i802_bss *routes[64];
static bool route_radio_scope[64];
static u32 route_wiphy[64];
static size_t route_n;
static struct hostapd_data *canonicals[64];
static size_t canonical_n;
static struct hostapd_data *hapds[6];
static void *last_event_ctx;
static unsigned beacon_calls[6];
static void check(bool ok, const char *name) {
    checks++;
    if (!ok) { printf("ASSERT:%s\n", name); fflush(stdout); exit(86); }
}
#define CHECK(x,n) check(!!(x), n)
static void wpa_printf(int level, const char *fmt, ...) {
    (void)fmt; if (level == MSG_WARNING) warnings++;
}
static void wpa_dbg(void *ctx, int level, const char *fmt, ...) {
    (void)ctx; (void)level; (void)fmt;
}
static void wpa_msg(void *ctx, int level, const char *fmt, ...) {
    (void)ctx; (void)level; (void)fmt; unknown_events++;
}
static void hostapd_logger(void *h, void *a, int m, int l, const char *f, ...) {
    (void)h; (void)a; (void)m; (void)l; (void)f;
}
static void wpa_hexdump(int l, const char *s, const void *b, size_t n) {
    (void)l; (void)s; (void)b; (void)n;
}
static void *os_zalloc(size_t n) { return alloc_fail ? NULL : calloc(1, n); }
static void leaf_event(const char *s) { (void)s; leaf_calls++; }
static int eloop_register_timeout(unsigned a, unsigned b,
    void (*fn)(void *, void *), void *ctx, void *data) {
    (void)a; (void)b; (void)fn; (void)ctx; (void)data; scheduled++; return 0;
}
static void route_observe(struct i802_bss *, int, struct nlattr **);
/* Wiphy/bridge lookups and hardware leaves are explicit model boundaries. */
static int nl80211_get_wiphy_index(struct i802_bss *bss) {
    return model_wiphy[bss->drv->unique_drv_id-1];
}
static bool nl80211_has_ifidx(struct wpa_driver_nl80211_data *drv, int bridge, int idx) {
    (void)drv; return bridge == idx;
}
static enum chan_width convert2width(int x) { (void)x; return CHAN_WIDTH_20; }
static int nl80211_get_link_id_by_freq(struct i802_bss *bss, int freq) {
    (void)bss; (void)freq; return NL80211_DRV_LINK_ID_NA;
}
static bool is_6ghz_op_class(u8 op) { return op >= 131 && op <= 137; }
static int beacon_gate_projection(struct hostapd_data *hapd);
static int __ieee802_11_set_beacon(struct hostapd_data *hapd) {
    for (int i=0; i<6; i++) if (hapds[i] == hapd) {
        beacon_calls[i]++; if (beacon_gate_projection(hapd)<0) return -1;
        return beacon_fail == i ? -1 : 0;
    }
    CHECK(false, "unknown-beacon-owner"); return -1;
}
static void hostapd_event_update_muedca_params(struct hostapd_data *, struct update_muedca *);
static void wpa_supplicant_event(void *, enum wpa_event_type, union wpa_event_data *);
/* @leaf_stubs@ */
/* @prototypes@ */
/* @lib@ */
/* @original@ */

static void route_observe(struct i802_bss *bss, int cmd, struct nlattr **tb) {
    CHECK(route_n < ARRAY_SIZE(routes), "route-bound");
    route_radio_scope[route_n]=cmd==NL80211_CMD_WIPHY_REG_CHANGE && tb[NL80211_ATTR_WIPHY] &&
        !tb[NL80211_ATTR_IFINDEX] && !tb[NL80211_ATTR_WDEV];
    route_wiphy[route_n]=tb[NL80211_ATTR_WIPHY]?nla_get_u32(tb[NL80211_ATTR_WIPHY]):0;
    routes[route_n++]=bss;
}

struct typed_mu { struct update_muedca params; };

/* Independent TEST oracle, not a production parser or allocated protocol. */
static bool typed_ie(const u8 *ie, size_t len, struct typed_mu *out) {
    if (len != 16) return false;
    if (ie[0] != WLAN_EID_EXTENSION || ie[1] != 14 ||
        ie[2] != WLAN_EID_EXT_HE_MU_EDCA_PARAMS) return false;
    memcpy(out->params.he_mu_ac_be_param, ie+4, 3);
    memcpy(out->params.he_mu_ac_bk_param, ie+7, 3);
    memcpy(out->params.he_mu_ac_vi_param, ie+10, 3);
    memcpy(out->params.he_mu_ac_vo_param, ie+13, 3);
    return true;
}

/* Caller supplies a real per-message received extent, NEVER nm_size/capacity.
 * No current nl_msg callback can supply this fact: a front adapter is required.
 * Command is deliberately NOT inspected/interpreted here. */
static bool strict_extent(const void *bytes, size_t received, bool need_ie,
                          struct typed_mu *out) {
    struct nlmsghdr h;
    size_t pos = NLMSG_HDRLEN + GENL_HDRLEN;
    bool seen[NL80211_ATTR_MAX+1] = {false};
    unsigned identities = 0;
    if (received < sizeof(h)) return false;
    memcpy(&h, bytes, sizeof(h));
    if (h.nlmsg_len < pos || h.nlmsg_len > received ||
        h.nlmsg_len != received || received > INT_MAX) return false;
    while (pos < received) {
        struct nlattr a;
        size_t rem = received-pos;
        if (rem < sizeof(a)) return false;
        memcpy(&a, (const u8 *)bytes+pos, sizeof(a));
        if (a.nla_len < NLA_HDRLEN || a.nla_len > rem ||
            (size_t)NLA_ALIGN(a.nla_len) > rem) return false;
        unsigned type = a.nla_type & NLA_TYPE_MASK;
        if (a.nla_type != type || type == 0 || type > NL80211_ATTR_MAX) return false;
        if (seen[type]) return false;
        seen[type] = true;
        size_t n = a.nla_len-NLA_HDRLEN;
        const u8 *payload = (const u8 *)bytes+pos+NLA_HDRLEN;
        if (type == NL80211_ATTR_IFINDEX || type == NL80211_ATTR_WIPHY) {
            u32 value;
            if (n != sizeof(value)) return false;
            memcpy(&value, payload, sizeof(value));
            if (type == NL80211_ATTR_IFINDEX && (!value || value > INT_MAX)) return false;
            if (type == NL80211_ATTR_WIPHY && value >= INT_MAX) return false;
            identities++;
        } else if (type == NL80211_ATTR_WDEV) {
            u64 value;
            if (n != sizeof(value)) return false;
            memcpy(&value, payload, sizeof(value));
            if ((u32)value == 0 || (value >> 32) >= INT_MAX) return false;
            identities++;
        } else if (type == NL80211_ATTR_IE) {
            if (!typed_ie(payload, n, out)) return false;
        } else return false;
        pos += NLA_ALIGN(a.nla_len);
    }
    return pos == received && identities <= 1 && (!need_ie || seen[NL80211_ATTR_IE]);
}

/* Dedicated typed-radio schema, still off wire: exactly WIPHY + full IE.
 * The generic framing oracle above also characterizes IFINDEX/WDEV routes. */
static bool strict_radio(const void *bytes, size_t received, u32 expected_wiphy,
                         struct typed_mu *out) {
    struct typed_mu temporary;
    if (!strict_extent(bytes,received,true,&temporary)) return false;
    struct nl_msg *m=nlmsg_convert((struct nlmsghdr *)bytes);
    if (!m) return false;
    struct nla_policy policy[NL80211_ATTR_MAX+1]={0};
    policy[NL80211_ATTR_WIPHY]=(struct nla_policy){NLA_U32,4,4};
    policy[NL80211_ATTR_IE]=(struct nla_policy){NLA_BINARY,16,16};
    struct nlattr *tb[NL80211_ATTR_MAX+1];
    struct genlmsghdr *g=nlmsg_data(nlmsg_hdr(m));
    int r=nla_parse(tb,NL80211_ATTR_MAX,genlmsg_attrdata(g,0),genlmsg_attrlen(g,0),policy);
    bool ok=r==0 && tb[NL80211_ATTR_WIPHY] && tb[NL80211_ATTR_IE] &&
        !tb[NL80211_ATTR_IFINDEX] && !tb[NL80211_ATTR_WDEV] &&
        nla_get_u32(tb[NL80211_ATTR_WIPHY])==expected_wiphy;
    if (ok) *out=temporary;
    nlmsg_free(m); return ok;
}

static bool eligible(struct hostapd_data *h) {
#ifdef CONFIG_IEEE80211AX
    return h && h->iconf && h->conf && h->started && h->beacon_set_done && hostapd_is_he_enabled(h);
#else
    (void)h; return false;
#endif
}

/* Approved TEST policy only. Real iface->bss[0], not a synthetic owner. */
static bool iface_ready(struct hostapd_iface *iface) {
    if (!iface || !iface->conf || !iface->num_bss || !iface->bss || !iface->bss[0]) return false;
    for (size_t i=0;i<iface->num_bss;i++) {
        struct hostapd_data *h=iface->bss[i];
        if (!h || h->iface!=iface || h->iconf!=iface->conf || !h->conf) return false;
    }
    return true;
}
static bool prototype_update(struct hostapd_iface *iface, struct update_muedca *p) {
    /* Stable caller-owned object lifetime is required; concurrent teardown is
     * unsupported. These are data/topology guards, not a lifetime protocol. */
    if (!p || !iface_ready(iface)) return false;
    bool any=false, sta=false;
    for (size_t i=0; i<iface->num_bss; i++) if (eligible(iface->bss[i])) {
        any=true; if (iface->bss[i]->num_sta) sta=true;
    }
    if (!any) return false;
    struct hostapd_data *canonical = iface->bss[0];
    CHECK(canonical_n < ARRAY_SIZE(canonicals), "canonical-bound");
    canonicals[canonical_n++] = canonical;
    struct ieee80211_he_mu_edca_parameter_set *mu=&canonical->iface->conf->he_mu_edca;
    memcpy(mu->he_mu_ac_be_param, p->he_mu_ac_be_param, 3);
    memcpy(mu->he_mu_ac_bk_param, p->he_mu_ac_bk_param, 3);
    memcpy(mu->he_mu_ac_vi_param, p->he_mu_ac_vi_param, 3);
    memcpy(mu->he_mu_ac_vo_param, p->he_mu_ac_vo_param, 3);
    if (sta) mu->he_qos_info = (mu->he_qos_info & 0xf0) | ((mu->he_qos_info+1)&0xf);
    for (size_t i=0; i<iface->num_bss; i++)
        if (eligible(iface->bss[i]) && iface->bss[i]->num_sta)
            iface->bss[i]->parameter_set_count++;
    if (ieee802_11_update_beacons(iface))
        wpa_printf(MSG_WARNING, "prototype beacon failure");
    return true;
}

static void hostapd_event_update_muedca_params(struct hostapd_data *h, struct update_muedca *p) {
    baseline_update(h, p);
}
static void wpa_supplicant_event(void *ctx, enum wpa_event_type event, union wpa_event_data *data) {
    if (event == EVENT_UPDATE_MUEDCA_PARAMS) {
        last_event_ctx=ctx;
        mu_events++;
        if (role_supp) supp_event_projection(event); else ap_event_projection(ctx, event, data);
    } else if (event == EVENT_INCUMBT_SIG_INTF_DETECTED) incumbent_events++;
}

static struct nl80211_global global;
static struct wpa_driver_nl80211_data drivers[2];
static struct i802_bss bsses[6];
static struct hostapd_iface ifaces[2];
static struct hostapd_config configs[2];
static struct hostapd_data ap[6];
static struct hostapd_bss_config bconf[6];
static struct hostapd_data *ap_ptrs[2][3];
static void reset(void) {
    memset(&global,0,sizeof(global)); memset(drivers,0,sizeof(drivers));
    memset(bsses,0,sizeof(bsses)); memset(ifaces,0,sizeof(ifaces));
    memset(configs,0,sizeof(configs)); memset(ap,0,sizeof(ap)); memset(bconf,0,sizeof(bconf));
    memset(beacon_calls,0,sizeof(beacon_calls));
    dl_list_init(&global.interfaces); dl_list_init(&global.pending_events);
    route_n=canonical_n=0; mu_events=incumbent_events=0; scheduled=replies=0;
    warnings=unknown_events=0; alloc_fail=0; beacon_fail=-1; role_supp=0;
    last_event_ctx=NULL;
    for (int d=0; d<2; d++) {
        model_wiphy[d]=7+d;
        model_iface_wiphy[d]=7+d;
        drivers[d].global=&global; drivers[d].unique_drv_id=d+1;
        drivers[d].first_bss=&bsses[d*3]; drivers[d].ctx=&ap[d*3];
        dl_list_add_tail(&global.interfaces,&drivers[d].list);
        ifaces[d].conf=&configs[d]; ifaces[d].num_bss=3; ifaces[d].bss=ap_ptrs[d];
        configs[d].ieee80211ax=1; configs[d].he_mu_edca.he_qos_info=0xaf;
        for (int b=0; b<3; b++) {
            int i=d*3+b;
            bsses[i].drv=&drivers[d]; bsses[i].ctx=&ap[i]; bsses[i].ifindex=10+i;
            bsses[i].wdev_id_set=1; bsses[i].wdev_id=100+i;
            bsses[i].br_ifindex=50+d; bsses[i].links[0].freq=5180;
            if (b<2) bsses[i].next=&bsses[i+1];
            ap_ptrs[d][b]=hapds[i]=&ap[i]; ap[i].iface=&ifaces[d];
            ap[i].iconf=&configs[d]; ap[i].conf=&bconf[i];
            ap[i].started=1; ap[i].beacon_set_done=1; ap[i].parameter_set_count=9;
            ap[i].drv_priv=&ap[i];
        }
    }
}
static const u8 ie[16]={WLAN_EID_EXTENSION,14,WLAN_EID_EXT_HE_MU_EDCA_PARAMS,
                       0x75,1,2,3,4,5,6,7,8,9,10,11,12};
static struct nl_msg *message(int command) {
    struct nl_msg *m=nlmsg_alloc_size(4096);
    CHECK(m != NULL, "allocation");
    memset((u8 *)m->nm_nlh+NLMSG_HDRLEN,0,m->nm_size-NLMSG_HDRLEN);
    /* Family/type zero is an in-memory constructor argument, not a new command. */
    CHECK(genlmsg_put(m,0,0,0,0,0,command,0) != NULL, "genl-put"); return m;
}
static void put_id(struct nl_msg *m, int attr, u64 v) {
    int r = attr == NL80211_ATTR_WDEV ? nla_put_u64(m,attr,v) : nla_put_u32(m,attr,(u32)v);
    CHECK(r == 0, "put-id");
}
static void put_ie(struct nl_msg *m) { CHECK(nla_put(m,NL80211_ATTR_IE,16,ie)==0,"put-ie"); }
static void route(struct nl_msg *m) { process_global_event(m,&global); }
static int reply_cb(struct nl_msg *m, void *ctx) { (void)m; (void)ctx; replies++; return NL_OK; }

/* Explicit OFF-WIRE composition: a genuine unrelated event's observed route
 * recipients plus a separately typed IE. Never called by either raw dispatcher. */
struct offwire_binding { struct typed_mu mu; u32 wiphy; bool validated; };
static bool bind_offwire(const void *bytes,size_t received,u32 wiphy,struct offwire_binding *binding) {
    memset(binding,0,sizeof(*binding));
    if (!strict_radio(bytes,received,wiphy,&binding->mu)) return false;
    binding->wiphy=wiphy; binding->validated=true; return true;
}
static bool compose_offwire(struct offwire_binding *binding) {
    struct hostapd_iface *seen[64]; size_t n=0;
    if (!binding || !binding->validated) return false;
    for (size_t j=0; j<route_n; j++) {
        if (!route_radio_scope[j] || route_wiphy[j]!=binding->wiphy ||
            (u32)nl80211_get_wiphy_index(routes[j])!=binding->wiphy) return false;
        struct hostapd_data *h=NULL;
        /* Explicit test role registry, NOT a proposed daemon role API. */
        for (size_t k=0;k<ARRAY_SIZE(hapds);k++)
            if (routes[j]->ctx==hapds[k]) h=hapds[k];
        if (!h) continue;
        if (!iface_ready(h->iface)) return false;
        int iface_id=h->iface==hapds[0]->iface?0:h->iface==hapds[3]->iface?1:-1;
        if (iface_id<0 || (u32)model_iface_wiphy[iface_id]!=binding->wiphy) return false;
        bool found=false;
        for (size_t i=0; i<n; i++) if (seen[i]==h->iface) found=true;
        if (found) continue;
        seen[n++]=h->iface;
    }
    /* Preflight all owners before any shared mutation. Secondaries alone do
     * not authorize an update, and duplicate canonical observations reject. */
    for (size_t i=0;i<n;i++) {
        size_t canonical_count=0;
        for (size_t j=0;j<route_n;j++)
            if (routes[j]->ctx==seen[i]->bss[0]) canonical_count++;
        if (canonical_count!=1) return false;
    }
    for (size_t i=0;i<n;i++) prototype_update(seen[i],&binding->mu.params);
    return true;
}

static void test_routes(void) {
    struct {int attr; u64 value; size_t count; int first;} table[]={
        {NL80211_ATTR_IFINDEX,11,1,1}, {NL80211_ATTR_WDEV,104,1,4},
        {NL80211_ATTR_WIPHY,7,3,0}, {NL80211_ATTR_WIPHY,8,3,3},
        {NL80211_ATTR_IFINDEX,50,1,0}, {NL80211_ATTR_IFINDEX,999,0,0},
        {NL80211_ATTR_WDEV,999,0,0}, {NL80211_ATTR_WIPHY,999,0,0}, {0,0,6,0}};
    for (size_t t=0; t<ARRAY_SIZE(table); t++) {
        reset(); struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE);
        if (table[t].attr) put_id(m,table[t].attr,table[t].value);
        route(m); CHECK(route_n==table[t].count,"MD03-route-count");
        for (size_t j=0; j<route_n; j++) CHECK(routes[j]==&bsses[table[t].first+j],"MD03-route-order");
        CHECK(mu_events==0,"MD03-not-MU"); nlmsg_free(m); cases++;
    }
    reset(); struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE);
    put_id(m,NL80211_ATTR_IFINDEX,11); put_id(m,NL80211_ATTR_WIPHY,8);
    route(m); CHECK(route_n==1 && routes[0]==&bsses[1],"MD03-baseline-identity-precedence");
    struct typed_mu mu; CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD02-conflicting-identity");
    nlmsg_free(m); cases++;
    reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE);
    process_bss_event(m,&bsses[4]); CHECK(route_n==0 && mu_events==0,"MD03-BSS-does-not-global-route");
    nlmsg_free(m); cases++;
}

static void test_identity_domains(void) {
    reset(); model_wiphy[0]=model_iface_wiphy[0]=0;
    struct typed_mu mu;
    struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,0);
    route(m); CHECK(route_n==3 && routes[0]==&bsses[0],"MD04-original-WIPHY0-route");
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,0,&mu),"MD02-radio-missing-IE");
    put_ie(m);
    CHECK(strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,0,&mu),"MD02-WIPHY0-typed-positive");
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,1,&mu),"MD02-WIPHY0-foreign-radio");
    nlmsg_free(m); cases++;
    reset(); model_wiphy[0]=model_iface_wiphy[0]=INT_MAX-1;
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,INT_MAX-1); route(m); put_ie(m);
    CHECK(route_n==3 && strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,INT_MAX-1,&mu),"MD02-max-allocated-WIPHY");
    nlmsg_free(m); cases++;
    u32 invalid[]={INT_MAX,UINT32_C(0x80000000),UINT32_MAX};
    for (size_t i=0;i<ARRAY_SIZE(invalid);i++) {
        reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,invalid[i]);
        route(m); CHECK(route_n==0,"MD04-original-high-WIPHY-no-broadcast"); put_ie(m);
        CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,true,&mu),"MD02-WIPHY-allocator-bound");
        nlmsg_free(m); cases++;
    }
    reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_IFINDEX,UINT32_MAX);
    route(m); CHECK(route_n==6,"MD04-original-IFINDEX-minus1-sentinel-broadcast");
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD02-IFINDEX-sentinel-reject"); nlmsg_free(m); cases++;
    reset(); model_wiphy[0]=model_iface_wiphy[0]=0; bsses[0].wdev_id=1;
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WDEV,1); route(m);
    CHECK(route_n==1 && routes[0]==&bsses[0] && strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD02-WDEV-phy0-id1-valid");
    nlmsg_free(m); cases++;
    u64 bad_wdev[]={0,UINT64_C(1)<<32,(u64)INT_MAX<<32|1};
    for (size_t i=0;i<ARRAY_SIZE(bad_wdev);i++) {
        m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WDEV,bad_wdev[i]);
        CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD02-WDEV-domain-not-uniform-zero");
        nlmsg_free(m); cases++;
    }
}

static void test_queue(void) {
    reset(); struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE);
    put_id(m,NL80211_ATTR_IFINDEX,11); global.sync_reply_handling=1;
    route(m); CHECK(route_n==0 && scheduled==1,"MD04-deferred-not-immediate");
    CHECK(m->nm_refcnt==2 && !dl_list_empty(&global.pending_events),"MD04-queue-reference");
    global.sync_reply_handling=0;
    struct nl_msg *m2=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m2,NL80211_ATTR_IFINDEX,14);
    route(m2); CHECK(route_n==0 && m2->nm_refcnt==2,"MD04-order-queue");
    nlmsg_free(m); nlmsg_free(m2);
    nl80211_deliver_pending_events(&global,NULL);
    CHECK(route_n==2 && routes[0]==&bsses[1] && routes[1]==&bsses[4],"MD04-deliver-order");
    CHECK(dl_list_empty(&global.pending_events),"MD04-queue-empty"); cases++;
    reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE);
    global.sync_reply_handling=1; global.reply_seq=77; global.reply_handler=reply_cb;
    nlmsg_hdr(m)->nlmsg_pid=12; nlmsg_hdr(m)->nlmsg_seq=77;
    route(m); CHECK(replies==1 && route_n==0 && dl_list_empty(&global.pending_events),"MD04-reply-separation");
    nlmsg_free(m); cases++;
    reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE); global.sync_reply_handling=1; alloc_fail=1;
    route(m); CHECK(route_n==0 && m->nm_refcnt==1 && dl_list_empty(&global.pending_events),"MD04-alloc-fail-drop");
    alloc_fail=0; nlmsg_free(m); cases++;
    reset(); m=message(NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS);
    CHECK(nla_put(m,NL80211_ATTR_HE_MUEDCA_PARAMS,13,ie+3)==0,"put-legacy");
    global.sync_reply_handling=1; process_bss_event(m,&bsses[1]);
    CHECK(mu_events==0 && m->nm_refcnt==2,"MD04-BSS-queued");
    global.sync_reply_handling=0; nlmsg_free(m); nl80211_deliver_pending_events(&global,NULL);
    CHECK(mu_events==1 && dl_list_empty(&global.pending_events),"MD04-BSS-delivered"); cases++;
}

static void test_bounds(void) {
    reset(); struct typed_mu mu;
    struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m);
    size_t n=nlmsg_hdr(m)->nlmsg_len;
    CHECK(strict_extent(nlmsg_hdr(m),n,true,&mu),"MD01-valid-framing");
    CHECK(nlmsg_get_max_size(m)>n,"MD01-capacity-is-not-extent");
    CHECK(!strict_extent(nlmsg_hdr(m),n-1,true,&mu),"MD01-received-not-capacity");
    for (size_t extent=0; extent<n; extent++) {
        u8 *shortbuf=malloc(extent?extent:1); CHECK(shortbuf!=NULL,"short-allocation");
        memcpy(shortbuf,nlmsg_hdr(m),extent);
        CHECK(!strict_extent(shortbuf,extent,true,&mu),"MD01-physical-truncation"); free(shortbuf);
    }
    u8 *copy=calloc(1,n+8); CHECK(copy!=NULL,"copy-alloc"); memcpy(copy,nlmsg_hdr(m),n);
    CHECK(!strict_extent(copy,n+1,true,&mu),"MD01-tail-outside-declared");
    ((struct nlmsghdr *)copy)->nlmsg_len=NLMSG_HDRLEN;
    CHECK(nlmsg_ok((struct nlmsghdr *)copy,NLMSG_HDRLEN),"MD01-libnl-base-header-only");
    CHECK(!strict_extent(copy,NLMSG_HDRLEN,true,&mu),"MD01-genl-minimum");
    ((struct nlmsghdr *)copy)->nlmsg_len=n;
    for (size_t len=0; len<=24; len++) {
        u8 padded[32]={0}; memcpy(padded,ie,16);
        CHECK(typed_ie(padded,len,&mu)==(len==16),"MD02-IE-exact-length");
    }
    for (int b=0; b<3; b++) { u8 bad[16]; memcpy(bad,ie,16); bad[b]^=1;
        CHECK(!typed_ie(bad,16,&mu),"MD02-IE-prefix"); }
    CHECK(typed_ie(ie,16,&mu) && mu.params.he_mu_ac_be_param[0]==1 &&
          mu.params.he_mu_ac_vo_param[2]==12,"MD02-AC-mapping");
    struct nlattr *a=(struct nlattr *)(copy+NLMSG_HDRLEN+GENL_HDRLEN);
    for (int len=0; len<4; len++) { a->nla_len=len;
        CHECK(!strict_extent(copy,n,true,&mu),"MD01-short-nla"); }
    a->nla_len=100; CHECK(!strict_extent(copy,n,true,&mu),"MD01-overrun-nla");
    a->nla_len=20; a->nla_type=NL80211_ATTR_IE|NLA_F_NESTED;
    CHECK(!strict_extent(copy,n,true,&mu),"MD02-nested-flag");
    a->nla_type=NL80211_ATTR_IE|NLA_F_NET_BYTEORDER;
    CHECK(!strict_extent(copy,n,true,&mu),"MD02-net-byteorder-flag");
    a->nla_type=NL80211_ATTR_MAX+1; CHECK(!strict_extent(copy,n,true,&mu),"MD02-unknown-attr");
    a->nla_type=0; CHECK(!strict_extent(copy,n,true,&mu),"MD02-zero-attr");
    a->nla_type=NL80211_ATTR_IE; a->nla_len=5;
    ((struct nlmsghdr *)copy)->nlmsg_len=25;
    CHECK(!strict_extent(copy,25,true,&mu),"MD01-missing-aligned-span");
    free(copy); nlmsg_free(m); cases++;
    for (int attr=0; attr<3; attr++) {
        int ids[]={NL80211_ATTR_IFINDEX,NL80211_ATTR_WDEV,NL80211_ATTR_WIPHY};
        for (int len=0; len<=12; len++) {
            m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m); u8 value[12]={1};
            CHECK(nla_put(m,ids[attr],len,value)==0,"put-sized-id");
            CHECK(strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,true,&mu)==
                  (len==(attr==1?8:4)),"MD02-identity-width"); nlmsg_free(m); cases++;
        }
    }
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m); put_id(m,NL80211_ATTR_IFINDEX,0);
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,true,&mu),"MD02-zero-identity"); nlmsg_free(m);
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m); put_id(m,NL80211_ATTR_IFINDEX,10); put_id(m,NL80211_ATTR_IFINDEX,11);
    struct nlattr *tb[NL80211_ATTR_MAX+1];
    struct genlmsghdr *g=nlmsg_data(nlmsg_hdr(m));
    CHECK(nla_parse(tb,NL80211_ATTR_MAX,genlmsg_attrdata(g,0),genlmsg_attrlen(g,0),NULL)==0 &&
          nla_get_u32(tb[NL80211_ATTR_IFINDEX])==11,"MD02-baseline-last-duplicate-wins");
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,true,&mu),"MD02-duplicate-identity"); nlmsg_free(m);
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m); put_ie(m);
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,true,&mu),"MD02-duplicate-IE"); nlmsg_free(m); cases++;
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m);
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,7,&mu),"MD02-radio-needs-WIPHY");
    put_id(m,NL80211_ATTR_WIPHY,7);
    CHECK(strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,7,&mu),"MD02-radio-policy-positive");
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,8,&mu),"MD02-radio-foreign");
    put_id(m,NL80211_ATTR_IFINDEX,10);
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,7,&mu),"MD02-radio-rejects-IFINDEX"); nlmsg_free(m); cases++;
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_ie(m); put_id(m,NL80211_ATTR_WDEV,100);
    CHECK(!strict_radio(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,7,&mu),"MD02-radio-rejects-WDEV"); nlmsg_free(m); cases++;
    for (int len=0;len<=8;len++) {
        m=message(NL80211_CMD_WIPHY_REG_CHANGE); u8 value[8]={1};
        CHECK(nla_put(m,NL80211_ATTR_WIPHY,len,value)==0,"policy-put");
        struct nla_policy policy[NL80211_ATTR_MAX+1]={0};
        policy[NL80211_ATTR_WIPHY]=(struct nla_policy){NLA_U32,4,4};
        g=nlmsg_data(nlmsg_hdr(m));
        int result=nla_parse(tb,NL80211_ATTR_MAX,genlmsg_attrdata(g,0),genlmsg_attrlen(g,0),policy);
        CHECK(result==(len==4?0:-NLE_RANGE),"MD02-real-policy-min-max"); nlmsg_free(m); cases++;
    }
}

static void test_legacy(void) {
    CHECK(NL80211_CMD_INCUMBENT_SIGNAL_DETECT==160 && NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS==161,
          "MD08-current-command-values");
    CHECK(NL80211_ATTR_HE_MUEDCA_PARAMS==351 && NL80211_ATTR_IE==42,"MD08-current-attr-values");
    CHECK(KERNEL_NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS==160 &&
          KERNEL_NL80211_ATTR_HE_MUEDCA_PARAMS==346,"MD08-real-kernel-values");
    for (int full=0; full<2; full++) {
        reset(); struct nl_msg *m=message(NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS);
        CHECK(nla_put(m,NL80211_ATTR_HE_MUEDCA_PARAMS,full?16:13,full?ie:ie+3)==0,"legacy-payload");
        route(m); CHECK(mu_events==0 && route_n==6,"MD08-global-no-MU-case");
        process_bss_event(m,&bsses[1]); CHECK(mu_events==1,"MD08-BSS-legacy-consumes");
        CHECK(last_event_ctx==&ap[0] && last_event_ctx!=bsses[1].ctx,"MD08-legacy-uses-drv-not-selected-BSS-context");
#ifdef CONFIG_IEEE80211AX
        CHECK(configs[0].he_mu_edca.he_mu_ac_be_param[0]==(full?14:1),"MD08-IE-prefix-misparsed-as-raw13");
        CHECK(beacon_calls[0]==1 && beacon_calls[1]==1 && beacon_calls[2]==1,"MD08-real-beacon-iteration");
#else
        CHECK(beacon_calls[0]==0,"MD09-AX-off-branch");
#endif
        nlmsg_free(m); cases++;
    }
    struct nl_msg *m;
    reset(); m=message(NL80211_CMD_WIPHY_REG_CHANGE); u8 short_id=11;
    CHECK(nla_put(m,NL80211_ATTR_IFINDEX,1,&short_id)==0,"short-scalar-put");
    route(m); CHECK(route_n==1 && routes[0]==&bsses[1],"MD02-baseline-short-scalar-padding-read");
    struct typed_mu mu;
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD02-short-scalar-guard");
    nlmsg_free(m); cases++;
    reset(); ap[1].num_sta=1; m=message(NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS);
    /* Padded allocation remains >=4KB: characterize the missing payload length
     * check without deliberately reading outside allocated memory. */
    CHECK(nla_put(m,NL80211_ATTR_HE_MUEDCA_PARAMS,0,NULL)==0,"empty-legacy-put");
    process_bss_event(m,&bsses[1]); CHECK(mu_events==1,"MD08-baseline-no-payload-length-gate");
    CHECK(configs[0].he_mu_edca.he_qos_info==0xaf,"MD08-baseline-misses-secondary-STA");
    nlmsg_free(m); cases++;
    reset(); m=message(NL80211_CMD_INCUMBENT_SIGNAL_DETECT);
    /* Kernel legacy raw MU uses attr346, which is not host MU attr351. */
    CHECK(nla_put(m,346,13,ie+3)==0,"kernel-existing-attr346");
    route(m); process_bss_event(m,&bsses[1]);
    CHECK(mu_events==0 && incumbent_events==0,"MD08-kernel160-not-MU"); nlmsg_free(m); cases++;
    for (int cmd=160; cmd<=161; cmd++) {
        reset(); m=message(cmd); put_ie(m); route(m); process_bss_event(m,&bsses[1]);
        CHECK(mu_events==0 && incumbent_events==0,"MD08-full-IE-no-legacy-inference"); nlmsg_free(m); cases++;
    }
    reset(); m=message(NL80211_CMD_INCUMBENT_SIGNAL_DETECT); put_id(m,NL80211_ATTR_IFINDEX,11);
    put_id(m,NL80211_ATTR_WIPHY_FREQ,5180); put_id(m,NL80211_ATTR_CHANNEL_WIDTH,0);
    put_id(m,NL80211_ATTR_CENTER_FREQ1,5180);
    put_id(m,NL80211_ATTR_INCUMBENT_SIGNAL_INTERFERENCE_BITMAP,1);
    route(m); CHECK(incumbent_events==1 && mu_events==0,"MD08-genuine-incumbent-preserved"); nlmsg_free(m); cases++;
    reset(); role_supp=1; m=message(NL80211_CMD_UPDATE_HE_MUEDCA_PARAMS);
    CHECK(nla_put(m,NL80211_ATTR_HE_MUEDCA_PARAMS,13,ie+3)==0,"supp-legacy");
    process_bss_event(m,&bsses[1]);
    CHECK(mu_events==1 && unknown_events==1 && beacon_calls[0]==0,"MD09-real-supp-default-projection"); nlmsg_free(m); cases++;
}

static void test_consumer(void) {
#ifdef CONFIG_IEEE80211AX
    struct typed_mu mu; CHECK(typed_ie(ie,16,&mu),"typed-positive");
    reset(); ap[1].num_sta=1; baseline_update(&ap[0],&mu.params);
    CHECK(configs[0].he_mu_edca.he_qos_info==0xaf && ap[1].parameter_set_count==9,"MD05-baseline-primary-misses-secondary-STA");
    reset(); ap[0].started=0; ap[0].conf->disable_11ax=true; ap[1].num_sta=1;
    prototype_update(&ifaces[0],&mu.params);
    CHECK(canonical_n==1 && canonicals[0]==ifaces[0].bss[0],"MD05-actual-bss0-canonical");
    CHECK(configs[0].he_mu_edca.he_qos_info==0xa0 && ap[1].parameter_set_count==10 &&
          ap[0].parameter_set_count==9 && ap[2].parameter_set_count==9,"MD06-secondary-eligible-count");
    CHECK(beacon_calls[0]==0 && beacon_calls[1]==1 && beacon_calls[2]==1,"MD07-real-started-beacon-filter"); cases++;
    /* Exhaust all per-BSS started/beacon/HE/STA combinations on three BSSs. */
    for (unsigned mask=0; mask<4096; mask++) {
        reset(); bool any=false, sta=false; unsigned bits=mask;
        for (int i=0; i<3; i++) {
            unsigned b=bits&15; bits>>=4;
            ap[i].started=!!(b&1); ap[i].beacon_set_done=!!(b&2);
            bconf[i].disable_11ax=!(b&4); ap[i].num_sta=!!(b&8);
            bool e=(b&7)==7; any|=e; sta|=e && (b&8);
        }
        prototype_update(&ifaces[0],&mu.params);
        CHECK(canonical_n==(unsigned)any,"MD05-all-BSS-eligibility");
        CHECK(configs[0].he_mu_edca.he_qos_info==(sta?0xa0:0xaf),"MD06-shared-once-wrap-preserve-high");
        for (int i=0; i<3; i++) {
            bool e=ap[i].started && ap[i].beacon_set_done && !bconf[i].disable_11ax;
            CHECK(ap[i].parameter_set_count==9+(e && ap[i].num_sta),"MD06-per-BSS-WMM");
            CHECK(beacon_calls[i]==(unsigned)(any && ap[i].started && ap[i].beacon_set_done),"MD07-original-beacon-loop");
        }
        cases++;
    }
    reset(); ap[0].num_sta=ap[1].num_sta=1;
    for (int i=0;i<3;i++) baseline_update(&ap[i],&mu.params);
    CHECK(configs[0].he_mu_edca.he_qos_info==0xa1 && beacon_calls[0]==3,"MD06-baseline-repeated-shared-update");
    reset(); ap[0].num_sta=ap[1].num_sta=1;
    model_wiphy[1]=model_iface_wiphy[1]=7;
    struct offwire_binding binding;
    struct nl_msg *typed=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(typed,NL80211_ATTR_WIPHY,7); put_ie(typed);
    CHECK(bind_offwire(nlmsg_hdr(typed),nlmsg_hdr(typed)->nlmsg_len,7,&binding),"MD05-offwire-typed-radio"); nlmsg_free(typed);
    struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,7); route(m);
    CHECK(compose_offwire(&binding),"MD05-offwire-bound-radio-compose"); nlmsg_free(m);
    CHECK(canonical_n==2 && canonicals[0]==&ap[0] && canonicals[1]==&ap[3],"MD05-offwire-one-owner-per-iface");
    CHECK(configs[0].he_mu_edca.he_qos_info==0xa0 && configs[1].he_mu_edca.he_qos_info==0xaf,"MD06-offwire-shared-count");
    for (int i=0;i<6;i++) CHECK(beacon_calls[i]==1,"MD07-offwire-beacon-once"); cases++;
    reset(); bsses[1].ctx=&ap[3]; model_iface_wiphy[1]=7;
    dl_list_del(&drivers[1].list); /* One driver, two AP ifaces on the SAME radio. */
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,7); route(m);
    CHECK(compose_offwire(&binding),"MD05-legal-shared-drv-same-radio"); nlmsg_free(m);
    CHECK(canonical_n==2 && canonicals[0]==&ap[0] && canonicals[1]==&ap[3],"MD05-group-by-iface-not-drv"); cases++;
    reset(); int station_role_token=0;
    model_wiphy[1]=model_iface_wiphy[1]=7;
    for (int i=3;i<6;i++) bsses[i].ctx=&station_role_token;
    m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,7); route(m);
    CHECK(compose_offwire(&binding),"MD05-role-same-bound-radio"); nlmsg_free(m);
    CHECK(canonical_n==1 && canonicals[0]==&ap[0] && beacon_calls[3]==0,"MD05-offwire-role-registry-no-STA-cast"); cases++;
    for (int topology=0;topology<5;topology++) {
        reset();
        if (topology==0) drivers[0].first_bss=&bsses[1];
        if (topology==1) bsses[1].ctx=&ap[0];
        if (topology==2) bsses[1].ctx=&ap[3]; /* Deliberately FOREIGN radio ctx. */
        m=message(NL80211_CMD_WIPHY_REG_CHANGE);
        if (topology!=3) put_id(m,NL80211_ATTR_WIPHY,topology==4?8:7);
        route(m); CHECK(!compose_offwire(&binding),"MD05-missing-duplicate-foreign-unscoped-owner-reject");
        CHECK(canonical_n==0 && beacon_calls[0]==0 && configs[0].he_mu_edca.he_qos_info==0xaf,
              "MD05-rejected-topology-no-partial-mutation"); nlmsg_free(m); cases++;
    }
    reset(); struct offwire_binding invalid_binding={0};
    CHECK(!compose_offwire(&invalid_binding),"MD05-unvalidated-binding-reject"); cases++;
    reset(); ap[1].num_sta=1;
    for (int event=0;event<2;event++) {
        route_n=0; m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_WIPHY,7); route(m);
        CHECK(compose_offwire(&binding),"MD05-new-observed-event-compose"); nlmsg_free(m);
    }
    CHECK(canonical_n==2 && configs[0].he_mu_edca.he_qos_info==0xa1 && beacon_calls[1]==2,
          "MD06-composed-equal-events-separate"); cases++;
    for (int invalid=0;invalid<9;invalid++) {
        reset(); struct hostapd_iface *target=&ifaces[0];
        if (invalid==0) target=NULL;
        if (invalid==1) target->conf=NULL;
        if (invalid==2) target->num_bss=0;
        if (invalid==3) target->bss=NULL;
        if (invalid==4) target->bss[0]=NULL;
        if (invalid==5) target->bss[1]=NULL;
        if (invalid==6) target->bss[1]->iface=&ifaces[1];
        if (invalid==7) target->bss[1]->iconf=NULL;
        if (invalid==8) target->bss[1]->conf=NULL;
        CHECK(!prototype_update(target,&mu.params) && canonical_n==0 && beacon_calls[0]==0,
              "MD05-invalid-caller-topology-reject"); cases++;
    }
    reset(); ap[1].num_sta=1;
    prototype_update(&ifaces[0],&mu.params); prototype_update(&ifaces[0],&mu.params);
    CHECK(configs[0].he_mu_edca.he_qos_info==0xa1 && ap[1].parameter_set_count==11 && beacon_calls[1]==2,
          "MD06-repeated-same-valued-events-counted"); cases++;
    reset(); beacon_fail=1; prototype_update(&ifaces[0],&mu.params);
    CHECK(warnings==1 && beacon_calls[0]==1 && beacon_calls[1]==1 && beacon_calls[2]==1,"MD07-failed-beacon-continues-no-rollback");
    u8 encoded[32]; memset(encoded,0xcc,sizeof(encoded));
    u8 *end=hostapd_eid_he_mu_edca_parameter_set(&ap[0],encoded);
    CHECK(end==encoded+16 && encoded[16]==0xcc,"MD07-actual-IE-generator-length");
    struct typed_mu decoded;
    CHECK(typed_ie(encoded,16,&decoded) && memcmp(&decoded,&mu,sizeof(mu))==0,"MD07-generator-typed-roundtrip");
    memset(&configs[0].he_mu_edca,0,sizeof(configs[0].he_mu_edca));
    CHECK(hostapd_eid_he_mu_edca_parameter_set(&ap[0],encoded)==encoded,"MD07-zero-config-IE-omitted"); cases++;
    reset(); bconf[0].wmm_enabled=1;
    prototype_update(&ifaces[0],&mu.params);
    CHECK(hostapd_eid_he_mu_edca_parameter_set(&ap[0],encoded)==encoded+16 &&
          ap[0].parameter_set_count==9 && configs[0].he_mu_edca.he_qos_info==0xaf,"MD07-reg-stable-no-extra-count");
    struct hostapd_channel_data chan={.freq=5180,.wmm_rules_valid=1};
    struct hostapd_hw_modes hw={.num_channels=1,.channels=&chan};
    ifaces[0].current_mode=&hw; ifaces[0].freq=5180;
    chan.wmm_rules[0].min_cwmin=3;
    hostapd_eid_he_mu_edca_parameter_set(&ap[0],encoded);
    CHECK(ifaces[0].prev_wmm[0].cwmin==3 && ap[0].parameter_set_count==10 &&
          configs[0].he_mu_edca.he_qos_info==0xa0,"MD07-reg-change-extra-original-count");
    hostapd_eid_he_mu_edca_parameter_set(&ap[0],encoded);
    CHECK(ap[0].parameter_set_count==10 && configs[0].he_mu_edca.he_qos_info==0xa0,"MD07-reg-change-not-repeated"); cases++;
    for (int gate=0;gate<3;gate++) {
        reset();
        if (gate==0) ap[1].drv_priv=NULL;
        if (gate==1) ap[1].csa_in_progress=1;
        if (gate==2) ap[1].cca_in_progress=true;
        prototype_update(&ifaces[0],&mu.params);
        CHECK(warnings==1 && beacon_calls[0]==1 && beacon_calls[1]==1 && beacon_calls[2]==1,"MD07-real-gates-no-rollback"); cases++;
    }
    reset(); configs[0].ieee80211ax=0; prototype_update(&ifaces[0],&mu.params);
    CHECK(canonical_n==0 && beacon_calls[0]==0,"MD09-runtime-AX-off"); cases++;
#else
    reset(); struct typed_mu mu; CHECK(typed_ie(ie,16,&mu),"typed-no-AX");
    prototype_update(&ifaces[0],&mu.params);
    CHECK(canonical_n==0 && beacon_calls[0]==0,"MD09-build-AX-off"); cases++;
#endif
}

static int parser_tail_characterization(void) {
    struct nl_msg *m=message(NL80211_CMD_WIPHY_REG_CHANGE); put_id(m,NL80211_ATTR_IFINDEX,11);
    CHECK(nlmsg_reserve(m,1,0)!=NULL,"tail-reserve");
    struct genlmsghdr *g=nlmsg_data(nlmsg_hdr(m)); struct nlattr *tb[NL80211_ATTR_MAX+1];
    int r=nla_parse(tb,NL80211_ATTR_MAX,genlmsg_attrdata(g,0),genlmsg_attrlen(g,0),NULL);
    CHECK(r==0 && nla_get_u32(tb[NL80211_ATTR_IFINDEX])==11,"MD01-original-tail-accepts");
    struct typed_mu mu;
    CHECK(!strict_extent(nlmsg_hdr(m),nlmsg_hdr(m)->nlmsg_len,false,&mu),"MD01-strict-tail-reject");
    nlmsg_free(m); puts("CHARACTERIZED:libnl-tail-return-success"); return 0;
}

int main(int argc,char **argv) {
    if (argc==2 && !strcmp(argv[1],"parser-tail")) return parser_tail_characterization();
    if (argc==2 && !strcmp(argv[1],"semantic-canary")) CHECK(false,"semantic-canary");
    if (argc==2 && !strcmp(argv[1],"runtime-canary")) return 97;
    CHECK(sizeof(struct ieee80211_he_mu_edca_parameter_set)==13,"real-payload-size");
    test_bounds(); test_identity_domains(); test_routes(); test_queue(); test_legacy(); test_consumer();
    printf("PASS_OFFWIRE cases=%u checks=%u wire_ready=false BE_MLO=UNSUPPORTED\n",cases,checks);
    return 0;
}
