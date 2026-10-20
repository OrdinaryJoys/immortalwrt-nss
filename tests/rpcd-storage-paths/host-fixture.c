#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#define LOG_ERR 3
#define syslog(...) ((void)0)
static char storage[256], files[288], delta[288];
#define RPC_CHECKED_DIR storage
#define RPC_CHECKED_SNAPSHOT_FILES files
#define RPC_CHECKED_SNAPSHOT_DELTA delta
static bool checked_journal_blocked;
static unsigned calls[4], fd_errors;
static bool live[1024];
static int fault_kind, fault_at;
static bool checked_enabled=true;
#define RPCD_CHECKED_UCI_SUPPORT checked_enabled
static unsigned journal_load_calls, destroy_calls, register_calls;
static void *cursor;
#define UBUS_STATUS_UNKNOWN_ERROR 7
struct ubus_context { int unused; };
struct ubus_method { const char *name; int (*handler)(void); };
struct ubus_object_type { int unused; };
struct ubus_object { const char *name; struct ubus_object_type *type; const struct ubus_method *methods; size_t n_methods; };
struct rpc_session_cb { void (*cb)(void); };
#define ARRAY_SIZE(v) (sizeof(v)/sizeof((v)[0]))
#define UBUS_METHOD(n,f,p) { .name=(n) }
#define UBUS_METHOD_NOARG(n,f) { .name=(n) }
#define UBUS_OBJECT_TYPE(n,m) { 0 }
static int rpc_uci_configs(void) { return 0; }
static void rpc_uci_purge_savedir_cb(void) { }
static void *uci_alloc_context(void) { return fault_kind==6?NULL:&cursor; }
static void rpc_session_destroy_cb(struct rpc_session_cb *cb) { (void)cb;destroy_calls++; }
static int ubus_add_object(struct ubus_context *ctx,struct ubus_object *obj) { (void)ctx;(void)obj;register_calls++;return 0; }
static void checked_journal_load(void) { journal_load_calls++; }
static bool inject(int kind)
{
    calls[kind-1]++;
    return fault_kind==kind && calls[kind-1]==(unsigned)fault_at;
}
static int host_mkdir(const char *path, mode_t mode)
{
    if (inject(1)) { errno=EACCES; return -1; }
    return mkdir(path,mode);
}
static int host_open(const char *path,int flags,...)
{
    if (inject(2)) { errno=EACCES; return -1; }
    /* Linux resolves a trailing slash before the final O_NOFOLLOW check. */
    if (strlen(path)>1 && path[strlen(path)-1]=='/') flags&=~O_NOFOLLOW;
    int fd=open(path,flags);
    if (fd>=0) {
        if (fd>=(int)(sizeof(live)/sizeof(live[0])) || live[fd]) abort();
        live[fd]=true;
    }
    return fd;
}
static int host_fstat(int fd,struct stat *info)
{
    if (inject(3)) { errno=EIO; return -1; }
    int ret=fstat(fd,info);
    if (!ret && fault_kind==5 && calls[2]==(unsigned)fault_at)
        info->st_uid=geteuid()+1;
    return ret;
}
static int host_close(int fd)
{
    bool fail=inject(4);
    if (fd<0 || fd>=1024 || !live[fd]) fd_errors++;
    else live[fd]=false;
    int ret=close(fd);
    if (fail) { errno=EINTR; return -1; }
    return ret;
}
#define mkdir host_mkdir
#define open host_open
#define fstat host_fstat
#define close host_close
HOST_FUNCTIONS
#undef mkdir
#undef open
#undef fstat
#undef close
int main(int argc,char **argv)
{
    if (argc!=7 || strlen(argv[1])>=sizeof(storage)) return 2;
    strcpy(storage,argv[1]);
    if (snprintf(files,sizeof(files),"%s/snapshot-files/",storage)>=(int)sizeof(files) ||
        snprintf(delta,sizeof(delta),"%s/snapshot-delta/",storage)>=(int)sizeof(delta)) return 2;
    fault_kind=atoi(argv[2]);fault_at=atoi(argv[3]);
    checked_journal_blocked=atoi(argv[5])!=0;
    checked_enabled=atoi(argv[6])!=0;
    (void)host_open;(void)host_fstat;(void)host_close;
    struct ubus_context ctx={0};
    int status=rpc_uci_api_init(&ctx);
    unsigned leaks=0;
    for (unsigned i=0;i<sizeof(live)/sizeof(live[0]);i++) leaks+=live[i];
    bool alloc_ok=fault_kind!=6;
    unsigned expected_load=alloc_ok && checked_enabled && !checked_journal_blocked;
    unsigned failures=(checked_journal_blocked!=(atoi(argv[4])!=0))+(leaks!=0)+(fd_errors!=0)+
        (journal_load_calls!=expected_load)+(destroy_calls!=(unsigned)alloc_ok || register_calls!=(unsigned)alloc_ok)+
        (status!=(alloc_ok?0:UBUS_STATUS_UNKNOWN_ERROR));
    printf("{\"blocked\":%s,\"leaks\":%u,\"fd_errors\":%u,\"journal_load_calls\":%u,\"checks\":6,\"failures\":%u}\n",
        checked_journal_blocked?"true":"false",leaks,fd_errors,journal_load_calls,failures);
    return failures?1:0;
}
