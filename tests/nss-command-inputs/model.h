/* Explicit Linux/device/allocator/provider leaf models. No target ABI or FW. */
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int64_t loff_t;
typedef int32_t nss_if_num_t;
#define __user
#define GFP_KERNEL 0
#define IFNAMSIZ 16
#define IFF_UP 1
#include "types.h"

static void die(const char *marker) { fprintf(stderr,"NSS_INPUT:%s\n",marker); exit(86); }
#define CHECK(c,m) do { if (!(c)) die(m); } while (0)
struct ctl_table { void *data; int maxlen; };
struct net_device { char name[IFNAMSIZ]; int refs; unsigned flags; };
struct nss_ctx_instance { unsigned magic; };
struct device { int token; };
struct platform_device { struct device dev; };
struct firmware { const unsigned char *data; size_t size; };
static struct net_device device = {"ath0",1,0};
static struct nss_ctx_instance context = {0x1234};
static int init_net, ctx_present=1, mapped_if=42, vp_present, api_error, proc_error;
static int proc_calls, dev_gets, dev_puts, actions, logs, copy_user_calls;
static int allocations, frees, alloc_fail, want_alloc;
static char last_action[40], last_name[IFNAMSIZ], version_text[256];
static uint32_t last_type;
static uint16_t clone_size, clone_offset;
static enum nss_mirror_pkt_clone_point clone_point;
static struct nss_connmgr_tunipip6_maprule_cfg last_rule;
static bool frag_id_update;
static const char *interleave;
static void *owned;
static size_t owned_size;
static void event(const char *name) { actions++; snprintf(last_action,sizeof(last_action),"%s",name); }
static void model_log(const char *format, ...) { (void)format; logs++; }
#define nss_warning(...) model_log(__VA_ARGS__)
#define nss_info(...) model_log(__VA_ARGS__)
#define nss_mirror_warn(...) model_log(__VA_ARGS__)
#define nss_mirror_info(...) model_log(__VA_ARGS__)
#define pr_info(...) model_log(__VA_ARGS__)
#define NSS_VERIFY_CTX_MAGIC(c) CHECK((c)==&context && (c)->magic==0x1234,"CTX_MAGIC")
static void info(struct device *d, const char *fmt, ...) {
    va_list ap; CHECK(d && fmt,"FW_LOG"); va_start(ap,fmt);
    snprintf(version_text,sizeof(version_text),"%s",va_arg(ap,const char *)); va_end(ap); logs++;
}
#define dev_info(d,...) info(d,__VA_ARGS__)
#define dev_err(d,...) do { (void)(d); model_log(__VA_ARGS__); } while(0)
static ssize_t strscpy(char *dst,const char *src,size_t cap) {
    size_t n=strlen(src); if (!cap) return -E2BIG;
    size_t copied=n<cap-1?n:cap-1; memcpy(dst,src,copied); dst[copied]=0;
    return n>=cap?-E2BIG:(ssize_t)n;
}
static char *strim(char *p) {
    while(isspace((unsigned char)*p)) p++;
    size_t n=strlen(p); while(n && isspace((unsigned char)p[n-1])) p[--n]=0;
    return p;
}
int kstrtou32(const char *p,unsigned base,uint32_t *out) {
    char *end; unsigned long n;
    if (!*p || *p=='-') return -EINVAL;
    errno=0; n=strtoul(p,&end,(int)base);
    if(errno==ERANGE || n>UINT32_MAX) return -ERANGE;
    if(end==p || *end) return -EINVAL;
    *out=(uint32_t)n; return 0;
}
static void *allocate(size_t n) {
    allocations++;
    if (want_alloc) CHECK(n==(size_t)want_alloc,"TUNIP_ALLOC");
    if(alloc_fail) return NULL;
    CHECK(!owned && n && n<=2048,"ALLOC_SIZE");
    owned=calloc(1,n); owned_size=n; CHECK(owned,"HOST_ALLOC"); return owned;
}
static void release(void *p) {
    CHECK(p && p==owned,"FREE_OWNER"); free(p); owned=NULL; owned_size=0; frees++;
}
#define vzalloc(n) allocate(n)
#define vfree(p) release(p)
#define kzalloc(n,f) allocate(n)
#define kfree(p) release(p)
/* Kernel buffers are intentionally NOT userspace: old usercopy must fail safely. */
static size_t __attribute__((unused)) model_usercopy(void *to,const void *from,size_t n) {
    (void)to; (void)from; copy_user_calls++; return n;
}
#define copy_from_user(d,s,n) model_usercopy(d,s,n)
static int proc_dostring(const struct ctl_table *ctl,int write,void *buf,size_t *len,loff_t *pos) {
    proc_calls++; if(proc_error) return proc_error;
    if(!ctl->data || ctl->maxlen<=0 || !*len) { *len=0; return 0; }
    char *data=ctl->data;
    if(write) {
        size_t old=strlen(data), offset=(size_t)*pos;
        if(offset>old) return 0; /* Actual strict sysctl string offset semantics. */
        *pos+=(loff_t)*len;
        for(size_t i=0;i<*len && offset<(size_t)ctl->maxlen-1;i++) {
            char c=((char *)buf)[i]; if(!c || c=='\n') break; data[offset++]=c;
        }
        data[offset]=0;
        if(interleave) strscpy(data,interleave,(size_t)ctl->maxlen);
    } else {
        size_t n=strlen(data); if((size_t)*pos>n) { *len=0; return 0; }
        n-=(size_t)*pos; if(n>*len) n=*len;
        memcpy(buf,data+(size_t)*pos,n);
        if(n<*len) ((char *)buf)[n++]='\n';
        *len=n; *pos+=(loff_t)n;
    }
    return 0;
}
static struct net_device *dev_get_by_name(void *net,const char *name) {
    CHECK(net==&init_net,"NET_NAMESPACE"); dev_gets++; strscpy(last_name,name,sizeof(last_name));
    if(strcmp(name,device.name)) return NULL;
    device.refs++; return &device;
}
static void dev_put(struct net_device *dev) { CHECK(dev==&device && dev->refs>1,"DEV_PUT"); dev->refs--; dev_puts++; }
static struct nss_ctx_instance *nss_ppe_vp_get_context(void) { return ctx_present?&context:NULL; }
static int nss_cmn_get_interface_number_by_dev_and_type(struct net_device *dev,uint32_t type) {
    CHECK(dev==&device && dev->refs>1,"DEV_LOOKUP_HOLD"); last_type=type; return mapped_if;
}
static int nss_cmn_get_interface_number_by_dev(struct net_device *dev) { CHECK(dev==&device,"DEV_IDENTITY"); return mapped_if; }
static int nss_ppe_vp_get_ppe_port_by_nssif(struct nss_ctx_instance *ctx,int id) {
    CHECK(ctx==&context && id>=0,"PPE_KEY"); return vp_present;
}
static nss_tx_status_t nss_ppe_vp_create(struct nss_ctx_instance *ctx,int id) {
    CHECK(ctx==&context && id>=0,"PPE_KEY"); event("ppe-create"); return api_error?NSS_TX_FAILURE:NSS_TX_SUCCESS;
}
static nss_tx_status_t nss_ppe_vp_destroy(struct nss_ctx_instance *ctx,int id) {
    CHECK(ctx==&context && id>=0,"PPE_KEY"); event("ppe-destroy"); return api_error?NSS_TX_FAILURE:NSS_TX_SUCCESS;
}
static void nss_ppe_vp_proc_help(void) { logs++; }
static struct net_device *nss_mirror_create(void) { event("mirror-create"); return api_error?NULL:&device; }
static int mirror_op(struct net_device *dev,const char *name) { CHECK(dev==&device,"MIRROR_DEVICE"); event(name); return api_error; }
#define MIRROR_OP(fn,label) static int fn(struct net_device *d) { return mirror_op(d,label); }
MIRROR_OP(nss_mirror_enable,"mirror-enable")
MIRROR_OP(nss_mirror_disable,"mirror-disable")
MIRROR_OP(nss_mirror_destroy,"mirror-destroy")
MIRROR_OP(nss_mirror_reset_nexthop,"mirror-reset")
MIRROR_OP(nss_mirror_deconfigure_mirror,"mirror-deconfigure")
static int nss_mirror_set_nexthop(struct net_device *d,int id) { last_type=(uint32_t)id; return mirror_op(d,"mirror-next"); }
static int nss_mirror_configure(struct net_device *d,enum nss_mirror_pkt_clone_point point,uint16_t size,uint16_t offset) {
    clone_point=point; clone_size=size; clone_offset=offset; return mirror_op(d,"mirror-configure");
}
static void nss_mirror_display_all_info(void) { event("mirror-display-all"); }
static void nss_mirror_display_info(struct net_device *d) { (void)mirror_op(d,"mirror-display"); }
static struct nss_ctx_instance *nss_mirror_get_context(void) { return ctx_present?&context:NULL; }
static struct nss_ctx_instance *nss_wifili_get_context(void) { return &context; }
static int nss_dynamic_interface_get_type(struct nss_ctx_instance *ctx,int id) {
    CHECK(ctx==&context && id==mapped_if,"DYNAMIC_KEY"); return NSS_DYNAMIC_INTERFACE_TYPE_VAP;
}
static nss_tx_status_t next_hop(struct nss_ctx_instance *ctx,int id,int next) {
    CHECK(ctx==&context && id==mapped_if && next==mapped_if,"NEXTHOP_ARGS"); event("next-hop"); return NSS_TX_SUCCESS;
}
#define nss_wifi_vdev_set_next_hop next_hop
#define nss_phys_if_set_nexthop next_hop
static nss_tx_status_t nss_mirror_reset_if_nexthop(int id) { CHECK(id==mapped_if,"NEXTHOP_ARGS"); event("reset-hop"); return NSS_TX_SUCCESS; }
static nss_tx_status_t nss_phys_if_reset_nexthop(struct nss_ctx_instance *ctx,int id) { CHECK(ctx==&context,"CTX_IDENTITY"); return nss_mirror_reset_if_nexthop(id); }
static int in4_pton(const char *src,int len,uint8_t *dst,int delim,const char **end) {
    CHECK(len==-1 && delim==-1 && !end,"INET_ARGS"); return inet_pton(AF_INET,src,dst);
}
static int in6_pton(const char *src,int len,uint8_t *dst,int delim,const char **end) {
    CHECK(len==-1 && delim==-1 && !end,"INET_ARGS"); return inet_pton(AF_INET6,src,dst);
}
static enum nss_connmgr_tunipip6_err_codes rule_op(struct net_device *d,struct nss_connmgr_tunipip6_maprule_cfg *cfg,const char *label) {
    CHECK(d==&device && d->refs>1,"RULE_DEVICE_HOLD"); last_rule=*cfg; event(label);
    return api_error?NSS_CONNMGR_TUNIPIP6_INVALID_PARAM:NSS_CONNMGR_TUNIPIP6_SUCCESS;
}
static enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_add_maprule(struct net_device *d,struct nss_connmgr_tunipip6_maprule_cfg *cfg) { return rule_op(d,cfg,"map-add"); }
static enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_del_maprule(struct net_device *d,struct nss_connmgr_tunipip6_maprule_cfg *cfg) { return rule_op(d,cfg,"map-delete"); }
static enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_flush_fmr_rule(struct net_device *d) {
    CHECK(d==&device && d->refs>1,"RULE_DEVICE_HOLD"); event("map-flush"); return NSS_CONNMGR_TUNIPIP6_SUCCESS;
}
static const unsigned char *scan_base;
static size_t scan_extent;
static int checked_memcmp(const void *a,const void *b,size_t n) {
    uintptr_t off=(uintptr_t)a-(uintptr_t)scan_base;
    CHECK((uintptr_t)a>=(uintptr_t)scan_base && off<=scan_extent && n<=scan_extent-off,"SEQ_RANGE");
    return memcmp(a,b,n);
}
