/* Explicit host leaves, not Linux netdev/allocator/provider ABI. */
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int64_t loff_t;
#define __user
#define GFP_KERNEL 0
struct ctl_table { int unused; };
struct net_device { char name[16]; int refs; unsigned sentinel; };
#include "types.h"
static struct net_device devices[]={{"ath0",3,0x10203040},{"ath1",7,0x55667788},{"foreign",11,0xaabbccdd}};
static const int base_refs[]={3,7,11};
static int init_net, fail_alloc, provider_status, attempts, releases, successful_allocs, calls;
static void *owned;
static bool frag_id_update;
static size_t true_extent;
static const void *true_input;
static char trace[32768];
static size_t trace_len;
static struct nss_connmgr_tunipip6_maprule_cfg captured;
static void die(const char *marker) { fprintf(stderr,"TUNIP:%s\n",marker); exit(86); }
#define CHECK(c,m) do { if (!(c)) die(m); } while(0)
static void event(const char *fmt,...) {
    va_list ap; va_start(ap,fmt);
    int n=vsnprintf(trace+trace_len,sizeof(trace)-trace_len,fmt,ap); va_end(ap);
    CHECK(n>=0 && (size_t)n<sizeof(trace)-trace_len,"TRACE_CAPACITY"); trace_len+=(size_t)n;
}
static void model_log(const char *fmt,...) { (void)fmt; }
#define pr_info(...) model_log(__VA_ARGS__)
static void *model_allocate(size_t n) {
    attempts++; CHECK(n==MAX_PROC_SIZE+1 && !owned,"ALLOC_SHAPE");
    event("ALLOC %zu %s\n",n,fail_alloc?"FAIL":"OK");
    if(fail_alloc) return NULL;
    owned=calloc(1,n); CHECK(owned,"HOST_ALLOC"); successful_allocs++; return owned;
}
static void model_free(void *p) {
    if(!p) return;
    CHECK(p==owned,"FREE_OWNER"); free(p); owned=NULL; releases++; event("FREE\n");
}
#define kzalloc(n,f) model_allocate(n)
#define kfree(p) model_free(p)
static void *model_copy(void *dst,const void *src,size_t n) {
    CHECK(src && src==true_input && n<=true_extent,"INPUT_EXTENT");
    return memcpy(dst,src,n);
}
static ssize_t strscpy(char *dst,const char *src,size_t cap) {
    size_t n=strlen(src); CHECK(cap,"STRING_CAPACITY");
    size_t copied=n<cap-1?n:cap-1; memcpy(dst,src,copied); dst[copied]=0;
    return n>=cap?-E2BIG:(ssize_t)n;
}
/* Restricted %u leaf based on Linux6.18.38 vsscanf's no-digit return0.
 * In-range native conversions are real; full overflow/lexical equivalence is OPEN. */
static int kernel_scalar(const char *input,const char *fmt,...)
    __attribute__((format(scanf,2,3)));
static int kernel_scalar(const char *input,const char *fmt,...) {
    CHECK(input && !strcmp(fmt,"%u"),"NUMERIC_FORMAT");
    const char *p=input; while(isspace((unsigned char)*p)) p++;
    if(!isdigit((unsigned char)*p)) return 0;
    va_list ap; va_start(ap,fmt); int n=vsscanf(input,fmt,ap); va_end(ap);
    return n==EOF?0:n;
}
static int index_of(struct net_device *dev) {
    for(int i=0;i<3;i++) if(dev==&devices[i]) return i;
    die("FOREIGN_POINTER"); return -1;
}
static struct net_device *dev_get_by_name(void *net,const char *name) {
    CHECK(net==&init_net && name,"GET_ARGUMENT");
    for(int i=0;i<3;i++) if(!strcmp(name,devices[i].name)) {
        event("GET %s %d\n",name,i); devices[i].refs++; return &devices[i];
    }
    event("GET %s NONE\n",name); return NULL;
}
static void dev_put(struct net_device *dev) {
    int i=index_of(dev); CHECK(devices[i].refs>base_refs[i],"PUT_OWNED");
    devices[i].refs--; event("PUT %d\n",i);
}
static int in4_pton(const char *src,int len,uint8_t *dst,int delim,const char **end) {
    CHECK(len==-1 && delim==-1 && !end,"INET_ARGUMENT"); return inet_pton(AF_INET,src,dst);
}
static int in6_pton(const char *src,int len,uint8_t *dst,int delim,const char **end) {
    CHECK(len==-1 && delim==-1 && !end,"INET_ARGUMENT"); return inet_pton(AF_INET6,src,dst);
}
static enum nss_connmgr_tunipip6_err_codes provider(struct net_device *dev,
        struct nss_connmgr_tunipip6_maprule_cfg *cfg,const char *op) {
    CHECK(dev,"PROVIDER_REF"); int i=index_of(dev);
    CHECK(dev->refs>base_refs[i] && !owned,"PROVIDER_REF"); calls++;
    event("CALL %s %d status=%d",op,i,provider_status);
    if(cfg) {
        captured=*cfg;
        event(" rule=%d p6=%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32
              " l6=%" PRIu32 " s6=%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32
              " sl6=%" PRIu32 " p4=%08" PRIx32 " l4=%" PRIu32 " ea=%" PRIu32 " psid=%" PRIu32,
              (int)cfg->rule_type,cfg->ipv6_prefix[0],cfg->ipv6_prefix[1],cfg->ipv6_prefix[2],cfg->ipv6_prefix[3],
              cfg->ipv6_prefix_len,cfg->ipv6_suffix[0],cfg->ipv6_suffix[1],cfg->ipv6_suffix[2],cfg->ipv6_suffix[3],
              cfg->ipv6_suffix_len,cfg->ipv4_prefix,cfg->ipv4_prefix_len,cfg->ea_len,cfg->psid_offset);
    }
    event("\n"); return (enum nss_connmgr_tunipip6_err_codes)provider_status;
}
enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_add_maprule(struct net_device *d,struct nss_connmgr_tunipip6_maprule_cfg *c) { return provider(d,c,"add"); }
enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_del_maprule(struct net_device *d,struct nss_connmgr_tunipip6_maprule_cfg *c) { return provider(d,c,"del"); }
enum nss_connmgr_tunipip6_err_codes nss_connmgr_tunipip6_flush_fmr_rule(struct net_device *d) { return provider(d,NULL,"flush"); }
