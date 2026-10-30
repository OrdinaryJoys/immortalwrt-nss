/* Host substitutes around complete extracted Linux permission functions. */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint8_t __u8;
typedef uint16_t __u16;
#define BIT(n) (1U << (n))
#define NLMSG_ALIGN(n) (((n) + 3U) & ~3U)
#define NLM_F_DUMP 0x300
#include "kernel-uapi.inc"

struct sk_buff;
struct genl_info { int unused; };
struct netlink_callback;
struct nla_policy { int unused; };
struct netlink_ext_ack { int unused; };
#include "kernel-types.inc"

struct user_namespace { unsigned slot; };
static struct user_namespace init_user_ns = {0}, child_user_ns = {1};
struct net { struct user_namespace *user_ns; };
static struct net init_net = {&init_user_ns}, child_net = {&child_user_ns};
struct socket { void *file; };
struct sock { struct net *net; struct socket *sk_socket; };
struct netlink_skb_parms { unsigned flags; struct sock *sk; };
struct sk_buff { struct sock *sk; struct netlink_skb_parms cb; };
#define NETLINK_CB(skb) ((skb)->cb)
struct nlmsghdr {
    u32 nlmsg_len;
    u16 nlmsg_type, nlmsg_flags;
    u32 nlmsg_seq, nlmsg_pid;
    struct genlmsghdr genl;
};

/* Reduced family layout: this is not a target kernel ABI/layout test. */
struct genl_family {
    bool netnsok;
    unsigned hdrsize, n_ops, maxattr;
    const struct nla_policy *policy;
    const struct genl_ops *ops;
    int (*pre_doit)(const struct genl_split_ops *, struct sk_buff *, struct genl_info *);
    void (*post_doit)(const struct genl_split_ops *, struct sk_buff *, struct genl_info *);
};
static unsigned host_file_caps, host_sender_caps, host_dispatches, host_effects;
static unsigned cases, checks, failures, flow_failures, policy_failures;
static int host_bad_header, host_socket_tag;
static int (*host_expected_handler)(struct sk_buff *, struct genl_info *);
static bool failed_ops[58];

static bool has_cap(unsigned mask, struct user_namespace *ns) {
    return (mask & 1U) || ((mask & 2U) && ns == &child_user_ns);
}
static bool file_ns_capable(void *file, struct user_namespace *ns, int cap) {
    if (file != &host_socket_tag || cap != CAP_NET_ADMIN) abort();
    return has_cap(host_file_caps, ns);
}
static bool ns_capable(struct user_namespace *ns, int cap) {
    if (cap != CAP_NET_ADMIN) abort();
    return has_cap(host_sender_caps, ns);
}
static struct net *sock_net(struct sock *sk) { return sk->net; }
static bool net_eq(struct net *a, struct net *b) { return a == b; }
static void *nlmsg_data(struct nlmsghdr *nlh) { return &nlh->genl; }
static u32 nlmsg_msg_size(int length) { return 16U + (u32)length; }
static int genl_header_check(const struct genl_family *f, struct nlmsghdr *n,
                             struct genlmsghdr *h, struct netlink_ext_ack *e) {
    return host_bad_header;
}
static void genl_op_fill_in_reject_policy(const struct genl_family *f, struct genl_ops *op) {
    /* Attribute policy parsing is deliberately not modeled. */
}
static int genl_get_cmd(u32 cmd, u8 flags, const struct genl_family *family,
                        struct genl_split_ops *op);
static int genl_family_rcv_msg_doit(const struct genl_family *f, struct sk_buff *s,
        struct nlmsghdr *n, struct netlink_ext_ack *e,
        const struct genl_split_ops *op, int length, struct net *net) {
    if (op->doit != host_expected_handler) abort();
    ++host_dispatches;
    struct genl_info info = {0};
    return op->doit(s, &info);
}
static int genl_family_rcv_msg_dumpit(const struct genl_family *f, struct sk_buff *s,
        struct nlmsghdr *n, struct netlink_ext_ack *e,
        const struct genl_split_ops *op, int length, struct net *net) {
    abort();
}
#include "kernel-bodies.inc"

static int genl_get_cmd(u32 cmd, u8 flags, const struct genl_family *family,
                        struct genl_split_ops *op) {
    struct genl_ops full;
    int err = genl_get_cmd_full(cmd, family, &full);
    if (err) return err;
    return genl_cmd_full_to_split(op, family, &full, flags);
}

#include "nss-enums.inc"
#include "handlers.inc"
#include "actual-tables.inc"

struct host_family {
    const char *name;
    struct genl_ops *ops;
    unsigned count;
    bool netnsok;
};
struct host_row {
    const char *name;
    unsigned family, cmd;
    int (*handler)(struct sk_buff *, struct genl_info *);
    unsigned policy; /* 1: global admin, 2: actual stats noop, 0: unchanged dormant. */
};
#include "rows.inc"

static void check(bool ok, bool flow) {
    ++checks;
    if (!ok) {
        ++failures;
        if (flow) ++flow_failures;
        else ++policy_failures;
    }
}
struct profile {
    unsigned opener, sender, dst;
    bool child;
};
static const struct profile profiles[] = {
    {0, 0, 0, false}, {2, 2, 0, true},
    {1, 1, 0, false}, {1, 1, 0, true},
    {1, 0, 0, false}, {0, 1, 0, false},
    {0, 1, NETLINK_SKB_DST, false},
    {0, 0, NETLINK_SKB_DST, false}
};

static void run_row(unsigned index) {
    struct host_row *row = &rows[index];
    struct host_family *entry = &families[row->family];
    struct genl_ops *actual = NULL;
    for (unsigned j = 0; j < entry->count; ++j)
        if (entry->ops[j].cmd == row->cmd) actual = &entry->ops[j];
    if (!actual || actual->doit != row->handler) abort();
    unsigned before = failures;
    check(actual->flags == (row->policy == 1 ? GENL_ADMIN_PERM : 0), false);
    for (unsigned p = 0; p < sizeof(profiles)/sizeof(profiles[0]); ++p) {
        const struct profile *profile = &profiles[p];
        struct socket socket = {&host_socket_tag};
        struct sock sk = {profile->child ? &child_net : &init_net, &socket};
        struct sk_buff skb = {&sk, {profile->dst, &sk}};
        struct nlmsghdr header = {0};
        struct netlink_ext_ack extack = {0};
        struct genl_family family = {
            .netnsok = entry->netnsok, .hdrsize = 16,
            .ops = entry->ops, .n_ops = entry->count
        };
        header.nlmsg_len = 16U + GENL_HDRLEN + family.hdrsize;
        header.genl.cmd = (u8)row->cmd;
        host_file_caps = profile->opener;
        host_sender_caps = profile->sender;
        host_dispatches = host_effects = 0;
        host_bad_header = 0;
        host_expected_handler = row->handler;
        bool global_allowed = (profile->sender & 1U) &&
            ((profile->opener & 1U) || profile->dst);
        int expected = profile->child && !entry->netnsok ? -ENOENT :
            row->policy == 1 && !global_allowed ? -EPERM : 0;
        ++cases;
        int ret = genl_family_rcv_msg(&family, &skb, &header, &extack);
        check(ret == expected, true);
        check(host_dispatches == (expected == 0), true);
        check(host_effects == (expected == 0 && row->policy != 2), true);

        /* Malformed headers and unsupported dump must never enter a handler. */
        host_dispatches = host_effects = 0;
        header.nlmsg_len--;
        ++cases;
        ret = genl_family_rcv_msg(&family, &skb, &header, &extack);
        check(ret == (profile->child && !entry->netnsok ? -ENOENT : -EINVAL), true);
        check(!host_dispatches && !host_effects, true);
        header.nlmsg_len++;
        host_bad_header = 1;
        ++cases;
        ret = genl_family_rcv_msg(&family, &skb, &header, &extack);
        check(ret == (profile->child && !entry->netnsok ? -ENOENT : -EINVAL), true);
        check(!host_dispatches && !host_effects, true);
        host_bad_header = 0;
        header.nlmsg_flags = NLM_F_DUMP;
        ++cases;
        ret = genl_family_rcv_msg(&family, &skb, &header, &extack);
        check(ret == (profile->child && !entry->netnsok ? -ENOENT : -EOPNOTSUPP), true);
        check(!host_dispatches && !host_effects, true);
    }
    failed_ops[index] = failures != before;
}
int main(int argc, char **argv) {
    if (argc != 3) return 70;
    char *end;
    unsigned long index = strtoul(argv[2], &end, 10);
    if (*end || index >= sizeof(rows)/sizeof(rows[0])) return 70;
    struct host_row *row = &rows[index];
    struct host_family *family = &families[row->family];
    struct genl_ops *op = NULL;
    for (unsigned j = 0; j < family->count; ++j)
        if (family->ops[j].cmd == row->cmd) op = &family->ops[j];
    if (!op) return 70;
    if (!strcmp(argv[1], "omit")) op->flags = 0;
    else if (!strcmp(argv[1], "restrict")) op->flags = GENL_ADMIN_PERM;
    else if (!strcmp(argv[1], "uns")) op->flags = GENL_UNS_ADMIN_PERM;
    else if (strcmp(argv[1], "none")) return 70;

    _Static_assert(sizeof(rows)/sizeof(rows[0]) == 58, "all actual operations");
    _Static_assert(sizeof(families)/sizeof(families[0]) == 23, "all actual tables");
    _Static_assert(GENL_ADMIN_PERM == 1 && GENL_UNS_ADMIN_PERM == 16, "official flags");
    for (unsigned i = 0; i < sizeof(rows)/sizeof(rows[0]); ++i) run_row(i);
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u,"
           "\"flow_failures\":%u,\"policy_failures\":%u,\"failed_ops\":[",
           cases, checks, failures, flow_failures, policy_failures);
    bool comma = false;
    for (unsigned i = 0; i < 58; ++i) if (failed_ops[i]) {
        printf("%s%u", comma ? "," : "", i);
        comma = true;
    }
    puts("]}");
    return failures ? 1 : 0;
}
