#include <arpa/inet.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__APPLE__) && !defined(s6_addr32)
#define s6_addr32 __u6_addr.__u6_addr32
#endif
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint8_t __u8;
typedef uint16_t __u16;
typedef uint32_t __u32;
typedef uint16_t __sum16;
typedef uint16_t __be16;
typedef uint32_t __be32;
typedef int spinlock_t;
typedef int rwlock_t;
typedef int atomic_t;
struct rcu_head { int unused; };
struct hlist_node { void *next; };
struct hlist_head { void *first; };
struct timer_list { unsigned long expires; bool pending; };
#define MC_HASH_SIZE 4
#define MC_SRC_GROUP_MAX MC_DEF_SRCS_MAX
#define MC_RT_SRC_MAX MC_DEF_RT_SRCS_MAX
#define MC_FLOOD_IF_MAX MC_DEF_IF_MAX
#define MC_INVALID_PID ((u32)-1)
#define ETH_ALEN 6
#define ETH_P_IP 0x0800
#define ETH_P_IPV6 0x86dd
#define HZ 100UL
#ifndef HOST_JIFFY_MAX
#define HOST_JIFFY_MAX ((LONG_MAX >> 1) - 1)
#endif
#define MAX_JIFFY_OFFSET HOST_JIFFY_MAX
#define GFP_ATOMIC 1
#define MSG_DONTWAIT_HOST 1
#define CAP_NET_ADMIN 12
#define KERN_INFO ""
#define KERN_ERR ""
#define MC_PRINT(...) ((void)0)
#define LINUX_VERSION_CODE 0x061226
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define fallthrough __attribute__((fallthrough))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
#define check_mul_overflow(a,b,p) __builtin_mul_overflow((a),(b),(p))
#define os_hlist_for_each_entry_rcu(p,h,head,member) \
    (void)(h); for((p)=(head)->first;(p);(p)=(p)->member.next)
#define hlist_empty(h) (!(h)->first)
#define atomic_read(p) (*(p))
/* ACTUAL_API */
/* ACTUAL_PRIVATE_STRUCTURES */

/* ACTUAL_NETLINK_HEADER */
_Static_assert(sizeof(struct nlmsghdr)==16,"netlink-header-layout");
_Static_assert(MC_MSG_HDRLEN==36,"private-header-layout");
_Static_assert(sizeof(struct __mc_encaptbl_entry)==170,"packed-ENCAP-layout");
#define NLMSG_ALIGNTO 4U
#define NLMSG_ALIGN(n) (((n)+3U)&~3U)
#define NLMSG_HDRLEN ((int)sizeof(struct nlmsghdr))
#define NLMSG_LENGTH(n) ((n)+NLMSG_HDRLEN)
#define NLMSG_DATA(p) ((void *)((char *)(p)+NLMSG_HDRLEN))
struct sk_buff { unsigned char *data; size_t len,capacity; unsigned *refs; bool privileged; struct { u32 portid,dst_group; } cb; };
#define NETLINK_CB(s) ((s)->cb)
struct sock { int unused; };
static int init_net;
static struct net_device { char name[16]; int ifindex; } bridge={"br-lan",7};
static struct mc_struct model;
static struct mc_mdb_entry mdb;
static struct mc_port_group pg;
static struct { struct mc_fdb_group fg; unsigned char overread_guard[128]; } fg_store;
#define host_fg fg_store.fg
static unsigned long jiffies=1000;
static unsigned checks,failures,cases,refs,skb_live,unicast_calls,lookup_calls,attach_calls,detach_calls,notify_calls;
static bool missing_bridge,missing_mc,copy_failure,new_failure,put_failure,attach_failure;
static unsigned rcu_depth;
static unsigned capability_calls;
static unsigned char reply_bytes[8192];
static size_t reply_length;
static u32 reply_destination;
static struct sock model_socket;
static void check(bool ok,const char *why) { checks++; if(!ok){failures++;fprintf(stderr,"FAIL %s\n",why);} }
static void invariant(bool ok,const char *why) { if(!ok){fprintf(stderr,"MCS_HOST_CONTRACT %s\n",why);exit(86);} }
#ifdef memcpy
#undef memcpy
#endif
static void *checked_memcpy(void *d,const void *s,size_t n) {
    uintptr_t a=(uintptr_t)d,b=(uintptr_t)s;
    invariant(!n||a+n<=b||b+n<=a,"overlapping-memcpy");return memcpy(d,s,n);
}
#define memcpy checked_memcpy
static bool is_zero_ether_addr(const u8 *p) { static const u8 z[6];return !memcmp(p,z,6); }
static int ipv6_addr_cmp(const struct in6_addr *a,const struct in6_addr *b) { return memcmp(a,b,16); }
static int ipv6_addr_any(const struct in6_addr *a) { static const struct in6_addr z;return !memcmp(a,&z,16); }
static void ipv6_addr_set(struct in6_addr *a,u32 x,u32 y,u32 z,u32 w) { u32 words[4]={x,y,z,w};memcpy(a,words,16); }
static void spin_lock_bh(int *p) { invariant(!(*p)++,"recursive-lock"); }
static void spin_unlock_bh(int *p) { invariant((*p)--==1,"unlock-owner"); }
#define write_lock_bh spin_lock_bh
#define write_unlock_bh spin_unlock_bh
static void rcu_read_lock(void) { rcu_depth++; }
static void rcu_read_unlock(void) { invariant(rcu_depth>0,"rcu-underflow");rcu_depth--; }
static int gfp_any(void) { return GFP_ATOMIC; }
static bool netlink_capable(struct sk_buff *s,int capability) { capability_calls++;invariant(s->cb.portid!=0,"zero-ingress-before-capability");invariant(capability==CAP_NET_ADMIN,"capability-id");return s->privileged; }
static struct sk_buff *new_skb(size_t n) {
    struct sk_buff *s=calloc(1,sizeof(*s));invariant(s!=NULL,"fixture-allocation");
    s->capacity=n+256;s->data=malloc(s->capacity);s->refs=malloc(sizeof(unsigned));
    invariant(s->data&&s->refs,"fixture-allocation");*s->refs=1;memset(s->data,0xa5,s->capacity);s->len=n;skb_live++;return s;
}
static struct sk_buff *skb_copy(struct sk_buff *in,int flags) {
    invariant(flags==GFP_ATOMIC,"sleeping-copy-under-rcu");if(copy_failure)return NULL;
    struct sk_buff *s=new_skb(in->len);memcpy(s->data,in->data,in->len);s->cb=in->cb;s->privileged=in->privileged;return s;
}
static struct sk_buff *skb_clone(struct sk_buff *in,int flags) {
    invariant(flags==GFP_ATOMIC,"clone-flags");if(copy_failure)return NULL;
    struct sk_buff *s=malloc(sizeof(*s));invariant(s!=NULL,"fixture-clone");*s=*in;(*s->refs)++;skb_live++;return s;
}
static void kfree_skb(struct sk_buff *s) {
    invariant(s&&skb_live&&*s->refs,"skb-free-owner");if(!--(*s->refs)){free(s->data);free(s->refs);}free(s);skb_live--;
}
static void skb_trim(struct sk_buff *s,size_t n) { invariant(n<=s->len,"skb-trim-bound");s->len=n; }
static struct nlmsghdr *nlmsg_hdr(struct sk_buff *s) { return (void *)s->data; }
static bool nlmsg_ok(const struct nlmsghdr *h,size_t len) { return len>=sizeof(*h)&&h->nlmsg_len>=sizeof(*h)&&h->nlmsg_len<=len; }
static size_t nlmsg_len(const struct nlmsghdr *h) { return h->nlmsg_len-sizeof(*h); }
static struct sk_buff *nlmsg_new(size_t n,int flags) { invariant(flags==GFP_ATOMIC,"event-allocation-flags");return new_failure?NULL:new_skb(n+NLMSG_HDRLEN); }
static struct nlmsghdr *nlmsg_put(struct sk_buff *s,u32 pid,u32 seq,unsigned type,size_t n,int flags) {
    if(put_failure)return NULL;
    invariant(n+sizeof(struct nlmsghdr)<=s->capacity,"put-bound");s->len=n+sizeof(struct nlmsghdr);
    struct nlmsghdr *h=nlmsg_hdr(s);*h=(struct nlmsghdr){(u32)s->len,(uint16_t)type,(uint16_t)flags,seq,pid};return h;
}
static int netlink_unicast(struct sock *sk,struct sk_buff *s,u32 pid,int flags) {
    (void)flags;invariant(pid!=0,"zero-kernel-unicast-forbidden");invariant(sk==&model_socket&&s->len<=sizeof(reply_bytes),"unicast-owner");
    unicast_calls++;reply_destination=pid;reply_length=s->len;memcpy(reply_bytes,s->data,s->len);kfree_skb(s);return (int)reply_length;
}
static struct net_device *dev_get_by_name(int *net,const char *name) { invariant(net==&init_net&&rcu_depth,"device-lookup-context");lookup_calls++;if(missing_bridge||strcmp(name,"br-lan"))return NULL;refs++;return &bridge; }
static void dev_put(struct net_device *d) { invariant(d==&bridge&&refs,"device-reference");refs--; }
static struct mc_struct *mc_dev_get(struct net_device *d) { invariant(d==&bridge&&rcu_depth,"mc-lookup-context");return missing_mc?NULL:&model; }
#define MC_DEV(d) mc_dev_get(d)
static int mc_attach(struct net_device *d) { invariant(d==&bridge,"attach-owner");attach_calls++;return attach_failure?-ENOMEM:0; }
static void mc_detach(struct net_device *d) { invariant(d==&bridge,"detach-owner");detach_calls++; }
static int mc_mdb_destroy_by_port(struct mc_struct *m,struct mc_ip *g,u8 *mac,u32 index) { (void)g;(void)mac;invariant(m==&model&&index==7,"delete-MDB-owner");return 1; }
static int timer_pending(struct timer_list *t) { return t->pending; }
static int timer_delete_sync_try(struct timer_list *t) { t->pending=false;return 1; }
static int time_after(unsigned long a,unsigned long b) { return (long)(b-a)<0; }
static void mod_timer(struct timer_list *t,unsigned long when) { t->expires=when;t->pending=true; }
static unsigned long jiffies_to_msecs(unsigned long j) { return j*10; }
static u8 *mc_fdb_mac_get(struct mc_fdb_group *f) { return f->mac; }
typedef void (*mc_bridge_ipv4_update_callback_t)(struct net_device *,__be32);
typedef void (*mc_bridge_ipv6_update_callback_t)(struct net_device *,struct in6_addr *);
static void notify4(struct net_device *d,__be32 g) { (void)g;invariant(d==&bridge,"notify-owner");notify_calls++; }
static void notify6(struct net_device *d,struct in6_addr *g) { (void)g;invariant(d==&bridge,"notify-owner");notify_calls++; }
static mc_bridge_ipv4_update_callback_t mc_bridge_ipv4_update_callback_get(void) { return notify4; }
static mc_bridge_ipv6_update_callback_t mc_bridge_ipv6_update_callback_get(void) { return notify6; }
static ssize_t strscpy(char *d,const char *s,size_t n) { size_t l=strnlen(s,n);if(!n)return -E2BIG;size_t count=l<n?l:n-1;memcpy(d,s,count);d[count]=0;return l<n?(ssize_t)count:-E2BIG; }
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "The host bitfield profile is little-endian only"
#endif
#define __LITTLE_ENDIAN_BITFIELD 1
#define __struct_group(TAG,NAME,ATTRS,...) union { struct { __VA_ARGS__ } ATTRS; struct TAG { __VA_ARGS__ } ATTRS NAME; } ATTRS
/* ACTUAL_IP_HEADERS */
_Static_assert(offsetof(struct iphdr,saddr)==12&&sizeof(struct iphdr)==20,"IPv4-source-layout");
_Static_assert(offsetof(struct ipv6hdr,saddr)==8&&sizeof(struct ipv6hdr)==40,"IPv6-source-layout");
static unsigned mc_group_hash(unsigned salt,__be32 group) { (void)salt;(void)group;return 0; }
static struct mc_mdb_entry *mc_mdb_find(struct hlist_head *head,struct mc_ip *group) { invariant(head==&model.hash[0],"MDB-lookup-head");return memcmp(group,&mdb.group,sizeof(*group))?NULL:&mdb; }
#define read_lock spin_lock_bh
#define read_unlock spin_unlock_bh
static void ether_addr_copy(u8 *dst,const u8 *src) { memcpy(dst,src,6); }
static void mc_ipv6_addr_copy(struct in6_addr *dst,const struct in6_addr *src) { memcpy(dst,src,sizeof(*dst)); }
/* ACTUAL_FUNCTIONS */

static void reset(void) {
    invariant(!skb_live&&!refs&&!rcu_depth,"case-resource-leak");memset(&model,0,sizeof(model));memset(&mdb,0,sizeof(mdb));memset(&pg,0,sizeof(pg));memset(&fg_store,0,sizeof(fg_store));
    model.dev=&bridge;model.started=1;model.hash[0].first=&mdb;mdb.users=1;mdb.pslist.first=&pg;mdb.group.pro=htons(ETH_P_IP);mdb.group.u.ip4=htonl(0xef010101);
    pg.port=&bridge;pg.fslist.first=&host_fg;host_fg.a.nsrcs=1;host_fg.a.srcs[0]=1;host_fg.mac[0]=2;
    missing_bridge=missing_mc=copy_failure=new_failure=put_failure=attach_failure=false;unicast_calls=lookup_calls=attach_calls=detach_calls=notify_calls=0;
    capability_calls=0;reply_length=0;reply_destination=0;memset(reply_bytes,0xcc,sizeof(reply_bytes));mc_nl_sk=&model_socket;event_pid=MC_INVALID_PID;cases++;
}
static struct sk_buff *request(unsigned type,size_t payload,u32 declared) {
    struct sk_buff *s=new_skb(NLMSG_LENGTH(MC_MSG_HDRLEN+payload));memset(s->data,0,s->len);s->privileged=true;s->cb.portid=777;
    struct nlmsghdr *h=nlmsg_hdr(s);h->nlmsg_len=s->len;h->nlmsg_type=type;h->nlmsg_seq=123;h->nlmsg_pid=888;
    struct __mcctl_msg_header *p=NLMSG_DATA(h);memcpy(p->if_name,"br-lan",7);p->buf_len=declared;p->bytes_written=0xdddd;p->bytes_needed=0xeeee;p->status=99;return s;
}
static struct __mcctl_msg_header *response(void) { return (void *)(reply_bytes+NLMSG_HDRLEN); }
static void deliver(struct sk_buff *s) {
    unsigned char *original=malloc(s->capacity);invariant(original!=NULL,"snapshot-allocation");memcpy(original,s->data,s->capacity);
    mc_netlink_receive(s);check(!memcmp(original,s->data,s->capacity),"request-data-unchanged");free(original);kfree_skb(s);
    check(!skb_live&&!refs&&!rcu_depth,"request-resources-retired");
}
static size_t fixed_size(unsigned type) {
    switch(type){case MC_MSG_SET_RETAG:return sizeof(struct __mc_param_retag);case MC_MSG_SET_ROUTER_PORT:return sizeof(struct __mc_param_router_port);
    case MC_MSG_SET_ADD_ACL_RULE:return sizeof(struct __mc_param_acl_rule);case MC_MSG_SET_FLUSH_ACL_RULE:return sizeof(u32);case MC_MSG_SET_TIMEOUT:return sizeof(struct __mc_param_timeout);
    case MC_MSG_DEL_MDB:return sizeof(struct __mc_mdb_entry);default:return sizeof(struct __mc_param_value);}
}
static void set_valid_payload(struct sk_buff *s,unsigned type) {
    void *data=MC_MSG_DATA(nlmsg_hdr(s));
    if(type==MC_MSG_SET_POLICY)((struct __mc_param_value *)data)->val=MC_POLICY_FLOOD;
    else if(type==MC_MSG_SET_ADD_ACL_RULE){struct __mc_param_acl_rule *a=data;a->pattern.rule=MC_ACL_RULE_MULTICAST;a->pattern.ip[0]=239;}
    else if(type==MC_MSG_DEL_MDB){struct __mc_mdb_entry *e=data;e->group.pro=htons(ETH_P_IP);e->ifindex=7;}
    else if(type==MC_MSG_SET_TIMEOUT)((struct __mc_param_timeout *)data)->enable=1;
    else if(type==MC_MSG_SET_ROUTER_PORT)((struct __mc_param_router_port *)data)->type=MC_RTPORT_FLOOD;
    else if(type!=MC_MSG_SET_FLUSH_ACL_RULE&&type!=MC_MSG_SET_RETAG)((struct __mc_param_value *)data)->val=1;
}
static bool is_array_or_get(unsigned t) { return t==MC_MSG_SET_PSW_ENCAP||t==MC_MSG_SET_PSW_FLOOD||t==MC_MSG_SET_NOTIFY||t==MC_MSG_GET_ACL||t==MC_MSG_GET_MDB||t==MC_MSG_GET_ROUTER_PORT; }
static void normal_commands(void) {
    for(unsigned type=0;type<MC_MSG_MAX;type++)for(unsigned mode=0;mode<2;mode++){
        reset();size_t n=is_array_or_get(type)?0:fixed_size(type);struct sk_buff *s=request(type,n,mode?n:0);if(n)set_valid_payload(s,type);deliver(s);
        check(unicast_calls==1&&response()->status==(type==MC_MSG_GET_MDB?MC_STATUS_BUFFER_OVERFLOW:MC_STATUS_SUCCESS),"valid-command-status");
        check(reply_destination==777&&((struct nlmsghdr *)reply_bytes)->nlmsg_pid==0&&((struct nlmsghdr *)reply_bytes)->nlmsg_seq==123,"trusted-reply-route");
        if(type==MC_MSG_SET_ENABLE)check(attach_calls==1,"enable-dispatched");
        if(type==MC_MSG_SET_DEBUG)check(model.debug==1,"debug-dispatched");
        if(type==MC_MSG_SET_POLICY)check(model.forward_policy==MC_POLICY_FLOOD,"policy-dispatched");
        if(type==MC_MSG_SET_EVENT_PID)check(event_pid==1,"event-destination-preserved");
    }
}
static void permission_case(void) {reset();struct sk_buff *s=request(MC_MSG_SET_DEBUG,4,4);set_valid_payload(s,MC_MSG_SET_DEBUG);s->privileged=false;deliver(s);check(!unicast_calls&&!lookup_calls&&!model.debug,"unprivileged-command-refused");}
static void bounds_cases(void) {
    for(size_t n=0;n<NLMSG_LENGTH(MC_MSG_HDRLEN);n++) {reset();struct sk_buff *s=request(MC_MSG_SET_DEBUG,4,4);s->len=n;nlmsg_hdr(s)->nlmsg_len=n;deliver(s);check(!unicast_calls&&!lookup_calls,"short-frame-rejected");}
    for(unsigned type=0;type<MC_MSG_MAX;type++)if(!is_array_or_get(type))for(size_t n=0;n<fixed_size(type);n++){
        reset();struct sk_buff *s=request(type,n,n);deliver(s);check(unicast_calls==1&&response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"short-fixed-payload-rejected");}
    for(unsigned type=0;type<MC_MSG_MAX;type++) {reset();struct sk_buff *s=request(type,0,1);deliver(s);check(unicast_calls==1&&response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"declared-payload-bound");}
    reset();struct sk_buff *s=request(MC_MSG_SET_DEBUG,4,4);memset(((struct __mcctl_msg_header *)NLMSG_DATA(nlmsg_hdr(s)))->if_name,'x',16);deliver(s);check(response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"unterminated-name");
    reset();s=request(MC_MSG_SET_DEBUG,4,4);s->len+=NLMSG_HDRLEN;deliver(s);check(!unicast_calls&&!lookup_calls,"second-frame-refused-before-effects");
    reset();s=request(MC_MSG_MAX,0,0);deliver(s);check(response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"unknown-command-refused");
    reset();s=request(MC_EVENT_MDB_UPDATED,0,0);deliver(s);check(response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"event-not-an-input-command");
}
static void domain_cases(void) {
    const unsigned types[]={MC_MSG_SET_POLICY,MC_MSG_SET_ROUTER_PORT,MC_MSG_SET_TIMEOUT,MC_MSG_SET_ADD_ACL_RULE,MC_MSG_SET_FLUSH_ACL_RULE};
    for(unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++){reset();unsigned t=types[i];struct sk_buff *s=request(t,fixed_size(t),0);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=UINT32_MAX;deliver(s);check(response()->status==MC_STATUS_INVALID_PARAMETER&&!lookup_calls,"invalid-domain-refused");}
    for(unsigned t=MC_MSG_SET_MEMBERSHIP_INTERVAL;t<=MC_MSG_SET_LOCAL_QUERY_INTERVAL;t+=MC_MSG_SET_LOCAL_QUERY_INTERVAL-MC_MSG_SET_MEMBERSHIP_INTERVAL){
        reset();struct sk_buff *s=request(t,4,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=0;deliver(s);check(response()->status==MC_STATUS_SUCCESS,"zero-interval-compatibility");
        reset();s=request(t,4,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=UINT32_MAX;deliver(s);
        bool fits=(uint64_t)UINT32_MAX*HZ<=(uint64_t)MAX_JIFFY_OFFSET;
        unsigned long actual=t==MC_MSG_SET_MEMBERSHIP_INTERVAL?model.membership_interval:model.local_query_interval;
        check(response()->status==(fits?MC_STATUS_SUCCESS:MC_STATUS_INVALID_PARAMETER)&&
              (fits||(!lookup_calls&&!actual)),"jiffy-limit-and-no-side-effect");
        if(fits)check(actual==(unsigned long)UINT32_MAX*HZ,"interval-no-u32-overflow");
        if((uint64_t)MAX_JIFFY_OFFSET/HZ<UINT32_MAX)for(unsigned over=0;over<2;over++){
            reset();s=request(t,4,4);u32 seconds=MAX_JIFFY_OFFSET/HZ+over;*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=seconds;deliver(s);
            actual=t==MC_MSG_SET_MEMBERSHIP_INTERVAL?model.membership_interval:model.local_query_interval;
            check(response()->status==(over?MC_STATUS_INVALID_PARAMETER:MC_STATUS_SUCCESS)&&
                  actual==(over?0:(unsigned long)seconds*HZ),"jiffy-exact-boundary");
        }
    }
}
static void compatibility_cases(void) {
    reset();struct sk_buff *s=request(MC_MSG_SET_ENABLE,36,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=1;deliver(s);
    check(response()->status==MC_STATUS_SUCCESS&&attach_calls==1&&((struct nlmsghdr *)reply_bytes)->nlmsg_flags==0,"real-igmpproxy-extra-zero-tail-flags-zero");
    for(unsigned capacity=0;capacity<3*sizeof(struct __mc_param_acl_rule);capacity++){
        reset();model.igmp_acl.pattern_count=2;
#ifdef MC_SUPPORT_MLD
        model.mld_acl.pattern_count=1;
        const unsigned total=3;
#else
        const unsigned total=2;
#endif
        s=request(MC_MSG_GET_ACL,3*sizeof(struct __mc_param_acl_rule),capacity);deliver(s);
        unsigned count=capacity/sizeof(struct __mc_param_acl_rule);if(count>total)count=total;
        check(response()->status==(count<total?MC_STATUS_BUFFER_OVERFLOW:MC_STATUS_SUCCESS)&&response()->bytes_written==count*sizeof(struct __mc_param_acl_rule),"GET-capacity-floor-not-array-size");
        check(response()->bytes_needed==(count<total?total*sizeof(struct __mc_param_acl_rule):0),"ACL-total-needed-includes-MLD");
    }
    for(unsigned bad=0;bad<2;bad++){
        reset();s=request(MC_MSG_SET_PSW_ENCAP,2*sizeof(struct __mc_encaptbl_entry),2*sizeof(struct __mc_encaptbl_entry));
        struct __mc_encaptbl_entry *e=MC_MSG_DATA(nlmsg_hdr(s));
        for(unsigned i=0;i<2;i++){e[i].group.pro=htons(ETH_P_IP);e[i].group.u.ip4=mdb.group.u.ip4;e[i].dev_cnt=2;e[i].dev[0].in_nsrcs=1;}
        e[1].dev[0].in_nsrcs=bad?5:1;deliver(s);
        check(response()->status==(bad?MC_STATUS_INVALID_PARAMETER:MC_STATUS_SUCCESS)&&mdb.encap_dev_cnt==(bad?0:1),"packed-array-all-validated-before-effect-outer-clamp");
    }
    reset();s=request(MC_MSG_SET_PSW_FLOOD,sizeof(struct __mc_floodtbl_entry),sizeof(struct __mc_floodtbl_entry));
    struct __mc_floodtbl_entry *f=MC_MSG_DATA(nlmsg_hdr(s));f->group.pro=htons(ETH_P_IP);f->group.u.ip4=mdb.group.u.ip4;f->ifcnt=MC_DEF_IF_MAX+1;deliver(s);
    check(response()->status==MC_STATUS_SUCCESS&&mdb.flood_ifcnt==MC_DEF_IF_MAX,"flood-outer-count-clamped");
}
static void acl_cases(void) {
    reset();struct __mc_param_acl_rule a={0};a.pattern.rule=MC_ACL_RULE_MULTICAST;
#ifdef MC_SUPPORT_MLD
    a.pattern_type=MC_ACL_PATTERN_MLD;
    for(unsigned i=0;i<8;i++){a.pattern.ip[0]=0xff;a.pattern.ip[15]=i+1;mc_acltbl_update(&model,&a);}
    a.pattern.ip[15]=4;a.pattern.rule=MC_ACL_RULE_MANAGEMENT;u32 sentinel=0x12345678;model.convert_all=sentinel;mc_acltbl_update(&model,&a);
    check(model.mld_acl.pattern_count==8&&model.mld_acl.patterns[3].rule==MC_ACL_RULE_MANAGEMENT&&model.convert_all==sentinel,"full-MLD-update-matched-index");
    a.pattern.rule=MC_ACL_RULE_DISABLE;mc_acltbl_update(&model,&a);check(model.mld_acl.pattern_count==7&&model.mld_acl.patterns[3].ip.ip6.s6_addr[15]==5,"overlapping-MLD-delete");
#endif
    reset();a.pattern_type=MC_ACL_PATTERN_IGMP;a.pattern.rule=MC_ACL_RULE_MULTICAST;memset(a.pattern.ip,0,16);
    for(unsigned i=0;i<8;i++){a.pattern.ip[0]=239;a.pattern.ip[3]=i+1;mc_acltbl_update(&model,&a);}
    a.pattern.ip[3]=4;a.pattern.rule=MC_ACL_RULE_DISABLE;mc_acltbl_update(&model,&a);check(model.igmp_acl.pattern_count==7,"overlapping-IGMP-delete");
}
static void nested_cases(void) {
    for(unsigned pro=0;pro<2;pro++)for(unsigned count=0;count<=5;count++){
#ifndef MC_SUPPORT_MLD
        if(pro)continue;
#endif
        reset();struct sk_buff *s=request(MC_MSG_SET_PSW_ENCAP,sizeof(struct __mc_encaptbl_entry),sizeof(struct __mc_encaptbl_entry));
        struct __mc_encaptbl_entry *e=MC_MSG_DATA(nlmsg_hdr(s));e->group.pro=htons(pro?ETH_P_IPV6:ETH_P_IP);e->group.u.ip4=mdb.group.u.ip4;e->dev_cnt=1;e->dev[0].in_nsrcs=count;
        deliver(s);check(response()->status==(count>4?MC_STATUS_INVALID_PARAMETER:MC_STATUS_SUCCESS),"nested-include-count");if(count>4)check(!mdb.encap_dev_cnt,"invalid-nested-no-side-effect");
    }
    for(unsigned count=0;count<=6;count++) {reset();struct sk_buff *s=request(MC_MSG_SET_PSW_ENCAP,sizeof(struct __mc_encaptbl_entry),sizeof(struct __mc_encaptbl_entry));struct __mc_encaptbl_entry *e=MC_MSG_DATA(nlmsg_hdr(s));e->group.pro=htons(ETH_P_IP);e->dev_cnt=1;e->dev[0].ex_nsrcs=count==6?MC_DEF_EX_SRCS_INVAL:count;deliver(s);check(response()->status==((count==5)?MC_STATUS_INVALID_PARAMETER:MC_STATUS_SUCCESS),"nested-exclude-count-and-sentinel");}
    for(unsigned t=MC_MSG_SET_PSW_ENCAP;t<=MC_MSG_SET_PSW_FLOOD;t++){reset();struct sk_buff *s=request(t,1,1);deliver(s);check(response()->status==MC_STATUS_INVALID_PARAMETER,"array-unit-bound");}
    reset();struct __mc_encaptbl_dev d={0};d.in_nsrcs=5;struct iphdr ip={0};check(mc_translate_filter_source(&d,&ip,htons(ETH_P_IP))==1,"consumer-invalid-count-denied");
    struct { u8 sources[64]; u8 guard[64]; } sources;memset(&sources,0,sizeof(sources));
    check(mc_stranslate_check_source(htons(ETH_P_IP),sources.sources,4,&ip)==0,"consumer-source-index-bound");
}
static void source_match_cases(void) {
    for(unsigned ipv6=0;ipv6<2;ipv6++)for(unsigned placement=0;placement<4;placement++)for(unsigned slot=0;slot<4;slot++){
#ifndef MC_SUPPORT_MLD
        if(ipv6)continue;
#endif
        reset();unsigned char storage[sizeof(struct __mc_encaptbl_dev)+4];memset(storage,0,sizeof(storage));
        struct __mc_encaptbl_dev *d=(void *)(storage+placement);struct iphdr ip={.saddr=htonl(0xc0000201)};
        struct ipv6hdr ip6={0};ip6.saddr.s6_addr[0]=0x20;ip6.saddr.s6_addr[1]=1;ip6.saddr.s6_addr[15]=1;
        unsigned size=ipv6?16:4;void *packet=ipv6?(void *)&ip6:(void *)&ip;const void *source=ipv6?(const void *)&ip6.saddr:(const void *)&ip.saddr;
        __be16 protocol=htons(ipv6?ETH_P_IPV6:ETH_P_IP);
        d->in_nsrcs=4;memcpy(d->in_srcs+slot*size,source,size);
        check(mc_translate_filter_source(d,packet,protocol)==0,"packed-include-match");
        memset(d->in_srcs,0,sizeof(d->in_srcs));d->ex_nsrcs=MC_DEF_EX_SRCS_INVAL;
        check(mc_translate_filter_source(d,packet,protocol)==1,"packed-include-miss-exclude-sentinel");
        d->in_nsrcs=0;d->ex_nsrcs=4;memcpy(d->ex_srcs+slot*size,source,size);
        check(mc_translate_filter_source(d,packet,protocol)==1,"packed-exclude-match");
        memset(d->ex_srcs,0,sizeof(d->ex_srcs));
        check(mc_translate_filter_source(d,packet,protocol)==0,"packed-exclude-miss");
    }
}
static void event_zero_cases(void) {
    reset();event_pid=999;struct sk_buff *s=request(MC_MSG_SET_EVENT_PID,4,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=0;deliver(s);
    check(response()->status==MC_STATUS_INVALID_PARAMETER&&event_pid==999,"zero-event-destination-rejected");
    reset();event_pid=0;mc_netlink_event_send(&model,MC_EVENT_MDB_UPDATED,0,NULL);check(!unicast_calls&&!skb_live,"zero-event-not-emitted");
    const u32 destinations[]={MC_INVALID_PID,0x80000001U,999};
    for(unsigned i=0;i<3;i++){reset();s=request(MC_MSG_SET_EVENT_PID,4,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=destinations[i];deliver(s);
        check(response()->status==MC_STATUS_SUCCESS&&event_pid==destinations[i],"event-sentinel-and-highbit-proxy-preserved");}
}
static void zero_ingress_case(void) { reset();struct sk_buff *s=request(MC_EVENT_MDB_UPDATED,0,0);s->cb.portid=0;deliver(s);check(!capability_calls&&!unicast_calls&&!lookup_calls,"zero-ingress-before-capability"); }
static void ecm_cases(bool capacities,bool ipv4_only) {
    for(unsigned ipv6=0;ipv6<(ipv4_only?1U:2U);ipv6++)for(unsigned exclude=0;exclude<2;exclude++)for(unsigned hit=0;hit<2;hit++)for(unsigned zero=0;zero<(capacities?2U:1U);zero++){
#ifndef MC_SUPPORT_MLD
        if(ipv6)continue;
#endif
        reset();mdb.encap_dev_cnt=1;mdb.encap_dev[0].ifindex=17;memset(mdb.encap_dev[0].mac,0x22,6);
        __be32 source4=htonl(0xc0000201),group4=mdb.group.u.ip4;
        struct in6_addr source6={0},group6={0};source6.s6_addr[0]=0x20;source6.s6_addr[15]=1;group6.s6_addr[0]=0xff;group6.s6_addr[15]=1;
#ifdef MC_SUPPORT_MLD
        if(ipv6){mdb.group.pro=htons(ETH_P_IPV6);mdb.group.u.ip6=group6;}
#endif
        struct __mc_encaptbl_dev *d=&mdb.encap_dev[0];
        if(exclude)d->ex_nsrcs=1;else {d->in_nsrcs=1;d->ex_nsrcs=MC_DEF_EX_SRCS_INVAL;}
        if(hit)memcpy(exclude?d->ex_srcs:d->in_srcs,ipv6?(const void *)&source6:(const void *)&source4,ipv6?16:4);
        u32 destination=0xdeadbeef;u8 mac[6];int result;
#ifdef MC_SUPPORT_MLD
        if(ipv6)result=mc_bridge_ipv6_get_if(&bridge,&source6,&group6,zero?0:1,&destination,mac);else
#endif
        result=mc_bridge_ipv4_get_if(&bridge,source4,group4,zero?0:1,&destination,mac);
        bool allowed=exclude?!hit:hit;
        if(zero)check(result==(allowed?-1:0)&&destination==0xdeadbeef,"ECM-zero-capacity-no-write");
        else check(result==(allowed?1:0)&&destination==(allowed?17U:0xdeadbeef),"ECM-source-address-and-filter-result");
        check(!rcu_depth&&!mdb.rwlock,"ECM-return-lock-balanced");
    }
}
static void ecm_flood_cases(void) {
    for(int count=-1;count<=5;count++)for(unsigned exclude=0;exclude<2;exclude++){
        reset();mdb.flood_ifcnt=1;mdb.flood_ifindex[0]=bridge.ifindex;host_fg.a.nsrcs=count;
        host_fg.filter_mode=exclude?MC_DEF_FILTER_EXCLUDE:MC_DEF_FILTER_INCLUDE;
        __be32 source=htonl(0xc0000201);memcpy(host_fg.a.srcs,&source,sizeof(source));u32 destination=0xdeadbeef;u8 mac[6];
        int result=mc_bridge_ipv4_get_if(&bridge,source,mdb.group.u.ip4,1,&destination,mac);
        bool allowed=count>=0&&count<=4&&(exclude?count==0:count>0);
        check(result==(allowed?1:0)&&destination==(allowed?(u32)bridge.ifindex:0xdeadbeef),"ECM-flood-source-bound-and-match");
    }
}
static void mdb_count_case(int count) {
    reset();host_fg.a.nsrcs=count;struct sk_buff *s=request(MC_MSG_GET_MDB,sizeof(struct __mc_mdb_entry),sizeof(struct __mc_mdb_entry));deliver(s);
    check(response()->status==((count<0||count>4)?MC_STATUS_FAILURE:MC_STATUS_SUCCESS),"MDB-internal-source-bound");
}
static void output_cases(void) {
    for(int count=-1;count<=5;count++)mdb_count_case(count);
    reset();model.igmp_acl.pattern_count=1;memset(&model.igmp_acl.patterns[0].ip_mask,0xbb,sizeof(model.igmp_acl.patterns[0].ip_mask));model.igmp_acl.patterns[0].ip_mask.ip4_mask=0;
    struct sk_buff *s=request(MC_MSG_GET_ACL,2*sizeof(struct __mc_param_acl_rule),sizeof(struct __mc_param_acl_rule));memset(MC_MSG_DATA(nlmsg_hdr(s)),0xee,2*sizeof(struct __mc_param_acl_rule));deliver(s);
    struct __mc_param_acl_rule *e=(void *)(reply_bytes+NLMSG_HDRLEN+MC_MSG_HDRLEN);
    for(unsigned i=4;i<16;i++)check(!e->pattern.ip[i]&&!e->pattern.ip_mask[i],"IPv4-unused-union-bytes-zero");
    for(size_t i=sizeof(*e);i<2*sizeof(*e);i++)check(!((u8 *)e)[i],"GET-unused-payload-zero");
    check(response()->bytes_written==sizeof(*e)&&!response()->bytes_needed,"GET-output-metadata");
    reset();event_pid=999;mc_netlink_event_send(&model,MC_EVENT_MDB_UPDATED,0,NULL);check(unicast_calls==1&&reply_destination==999,"event-route");
    check(((struct nlmsghdr *)reply_bytes)->nlmsg_pid==0,"event-kernel-source");
    const u8 *p=(const void *)response();for(size_t i=16;i<MC_MSG_HDRLEN;i++)check(!p[i],"event-private-header-zero");
    unsigned previous=unicast_calls;mc_netlink_event_send(&model,MC_EVENT_MDB_UPDATED,1,NULL);mc_netlink_event_send(&model,0,0,NULL);check(previous==unicast_calls,"unsupported-event-no-send");
}
static void failure_cases(void) {
    for(unsigned fault=0;fault<5;fault++){reset();struct sk_buff *s=request(MC_MSG_SET_ENABLE,4,4);*(u32 *)MC_MSG_DATA(nlmsg_hdr(s))=1;
    copy_failure=fault==0;missing_bridge=fault==1;missing_mc=fault==2;attach_failure=fault==3;if(fault==4)s->privileged=false;deliver(s);
    check(!refs&&!skb_live,"failure-no-resource-leak");if(fault==0||fault==4)check(!attach_calls&&!unicast_calls,"allocation-or-capability-before-effects");if(fault==3)check(response()->status==MC_STATUS_FAILURE,"attach-failure-propagated");}
    reset();event_pid=999;new_failure=true;mc_netlink_event_send(&model,MC_EVENT_MDB_UPDATED,0,NULL);check(!skb_live&&!unicast_calls,"event-allocation-failure");new_failure=false;put_failure=true;mc_netlink_event_send(&model,MC_EVENT_MDB_UPDATED,0,NULL);check(!skb_live&&!unicast_calls,"event-put-failure");
}
int main(int argc,char **argv) {
    const char *test=argc>1?argv[1]:"all";
    if(!strcmp(test,"all")||!strcmp(test,"normal"))normal_commands();
    if(!strcmp(test,"all")||!strcmp(test,"permission"))permission_case();
    if(!strcmp(test,"all")||!strcmp(test,"bounds"))bounds_cases();
    if(!strcmp(test,"all")||!strcmp(test,"domains"))domain_cases();
    if(!strcmp(test,"all")||!strcmp(test,"compatibility"))compatibility_cases();
    if(!strcmp(test,"all")||!strcmp(test,"acl"))acl_cases();
    if(!strcmp(test,"all")||!strcmp(test,"nested"))nested_cases();
    if(!strcmp(test,"all")||!strcmp(test,"source-match"))source_match_cases();
    if(!strcmp(test,"all")||!strcmp(test,"event-zero"))event_zero_cases();
    if(!strcmp(test,"all")||!strcmp(test,"zero-ingress"))zero_ingress_case();
    if(!strcmp(test,"all")||!strcmp(test,"ecm"))ecm_cases(true,false);
    if(!strcmp(test,"ecm-positive"))ecm_cases(false,false);
    if(!strcmp(test,"ecm-v4"))ecm_cases(false,true);
    if(!strcmp(test,"ecm-capacity"))ecm_cases(true,false);
    if(!strcmp(test,"all")||!strcmp(test,"ecm-flood"))ecm_flood_cases();
    if(!strcmp(test,"all")||!strcmp(test,"output"))output_cases();
    if(!strcmp(test,"output-count"))mdb_count_case(5);
    if(!strcmp(test,"all")||!strcmp(test,"failure"))failure_cases();
    invariant(!refs&&!skb_live&&!rcu_depth,"final-resource-leak");
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",cases,checks,failures);return failures?1:0;
}
