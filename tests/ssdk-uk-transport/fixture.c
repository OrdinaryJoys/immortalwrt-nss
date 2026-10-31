/* Explicit reduced Linux/misc/usercopy/allocator/API provider models.
 * candidate.c below is the whole production C, with only #include lines removed.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sdk.h"

#define __user
#define KVER26
#define KVER32
#define KVER34
#define CONFIG_COMPAT
#define KERNEL_VERSION(a,b,c) (((a) << 16) | ((b) << 8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define THIS_MODULE NULL
#define MISC_DYNAMIC_MINOR 255
#define SSDK_ERROR(...) ((void)0)
#define SSDK_DEBUG(...) ((void)0)
#define SSDK_DUMP_BUF(...) ((void)0)
typedef uint32_t compat_ulong_t;
typedef uint32_t compat_uptr_t;
struct inode { int model; };
struct file { void *private_data; };
struct file_operations {
    void *owner, *read, *write, *poll;
    long (*unlocked_ioctl)(struct file *, unsigned int, unsigned long);
    long (*compat_ioctl)(struct file *, unsigned int, unsigned long);
    int (*open)(struct inode *, struct file *);
    int (*release)(struct inode *, struct file *);
};
struct miscdevice { int minor; const char *name; struct file_operations *fops; };
struct mutex { const char *name; unsigned held, locks, unlocks; };
#define DEFINE_MUTEX(n) struct mutex n = { #n, 0, 0, 0 }
static DEFINE_MUTEX(misc_mtx);
static void fail(const char *marker)
{
    fprintf(stderr, "UK_ASSERT:%s\n", marker);
    exit(86);
}
#define CHECK(condition, marker) do { if (!(condition)) fail(marker); } while (0)
static void model_lock(struct mutex *m);
static int model_trylock(struct mutex *m);
static void model_unlock(struct mutex *m);
#define mutex_lock(m) model_lock(m)
#define mutex_trylock(m) model_trylock(m)
#define mutex_unlock(m) model_unlock(m)
static void *model_alloc(size_t n);
static void model_free(void *p);
#define aos_mem_alloc(n) model_alloc(n)
#define aos_mem_free(p) model_free(p)
#define aos_mem_set(p,v,n) memset(p,v,n)
static void *compat_ptr(unsigned long token);
static unsigned long copy_from_user(void *to, const void *from, size_t n);
static unsigned long copy_to_user(void *to, const void *from, size_t n);
static int misc_register(struct miscdevice *dev);
static void misc_deregister(struct miscdevice *dev);
static sw_error_t sw_api_get(sw_api_t *api);
sw_error_t sw_uk_init(a_uint32_t nl_prot);
sw_error_t sw_uk_cleanup(void);

#include "candidate.c"

/* No real threads, VFS, module pinning, kernel pointers, or hardware exist here. */
struct block { void *p; size_t n; unsigned live; unsigned char saved[SW_MAX_API_BUF]; };
static struct block blocks[128];
static unsigned nblocks, alloc_calls, free_calls, fail_alloc;
static unsigned registers, deregisters, dispatches, lookups, hooks;
static unsigned from_calls, to_calls, fail_from, fail_to;
static int misc_owner; /* 0 empty, 1 this candidate, 2 foreign sentinel */
static unsigned register_error;
static struct file hook_file;
static const uint32_t incoming = 77;

struct region { void *p; size_t n; uint32_t token; };
static struct region regions[32];
static unsigned nregions;
static void *compat_ptr(unsigned long token)
{
    unsigned i;
    for (i = 0; i < nregions; ++i)
        if (token == regions[i].token) return regions[i].p;
    return NULL;
}
static uint32_t region(void *p, size_t n)
{
    unsigned i;
    for (i = 0; i < nregions; ++i)
        if (regions[i].p == p && regions[i].n == n) return regions[i].token;
    CHECK(nregions < 32, "REGION_CAPACITY");
    regions[nregions] = (struct region){p, n, 0x1000u + nregions * 0x100u};
    return regions[nregions++].token;
}
static int user_range(const void *p, size_t n)
{
    unsigned i;
    uintptr_t a = (uintptr_t)p;
    for (i = 0; i < nregions; ++i) {
        uintptr_t b = (uintptr_t)regions[i].p;
        if (a >= b && a - b <= regions[i].n && n <= regions[i].n - (a - b)) return 1;
    }
    return 0;
}
static unsigned long copy_from_user(void *to, const void *from, size_t n)
{
    ++from_calls;
    if ((fail_from && from_calls == fail_from) || !user_range(from, n)) return n;
    memcpy(to, from, n);
    return 0;
}
static unsigned long copy_to_user(void *to, const void *from, size_t n)
{
    ++to_calls;
    if ((fail_to && to_calls == fail_to) || !user_range(to, n)) return n;
    memcpy(to, from, n);
    return 0;
}
static void model_lock(struct mutex *m)
{
    CHECK(!(m == &misc_mtx && api_ioctl_lock.held), "MISC_LOCK_ORDER");
    CHECK(!m->held, "MUTEX_SELF_LOCK");
    m->held = 1; ++m->locks;
}
static int model_trylock(struct mutex *m)
{
    if (m->held) return 0;
    model_lock(m);
    return 1;
}
static void model_unlock(struct mutex *m)
{
    CHECK(m->held, "MUTEX_UNLOCK");
    m->held = 0; ++m->unlocks;
}
static struct block *block_of(void *p)
{
    unsigned i;
    for (i = 0; i < nblocks; ++i) if (blocks[i].p == p) return &blocks[i];
    fail("ALLOCATION_IDENTITY");
    return NULL;
}
static void *model_alloc(size_t n)
{
    void *p;
    ++alloc_calls;
    if (fail_alloc && alloc_calls == fail_alloc) return NULL;
    CHECK(nblocks < 128 && n <= SW_MAX_API_BUF, "ALLOCATION_SHAPE");
    p = calloc(1, n);
    CHECK(p != NULL, "HOST_ALLOCATION");
    blocks[nblocks++] = (struct block){.p=p, .n=n, .live=1};
    return p;
}
static void model_free(void *p)
{
    struct block *b;
    if (!p) return;
    b = block_of(p);
    CHECK(b->live, "FREE_ONCE");
    b->live = 0; ++free_calls;
    /* Quarantine: preserve bytes for ownership assertions; physically free at end. */
}
static unsigned live_count(void)
{
    unsigned i, n = 0;
    for (i = 0; i < nblocks; ++i) n += blocks[i].live;
    return n;
}
struct snapshot {
    int state, owner, minor;
    uint32_t protocol;
    uint64_t epoch;
    void *buffer;
    unsigned alloc, freed, registered, deregistered, live, count;
    unsigned char payload[128][SW_MAX_API_BUF];
    unsigned char livebits[128];
};
static struct snapshot snap(void)
{
    struct snapshot s;
    unsigned i;
    memset(&s, 0, sizeof(s));
    s.state=uk_state; s.owner=misc_owner; s.minor=switch_device.minor;
    s.protocol=uk_protocol; s.epoch=uk_epoch; s.buffer=cmd_buf;
    s.alloc=alloc_calls; s.freed=free_calls; s.registered=registers;
    s.deregistered=deregisters; s.live=live_count(); s.count=nblocks;
    for (i=0; i<nblocks; ++i) {
        s.livebits[i]=(unsigned char)blocks[i].live;
        memcpy(s.payload[i], blocks[i].p, blocks[i].n);
    }
    return s;
}
static void same(const struct snapshot *s, const char *marker)
{
    struct snapshot now = snap();
    CHECK(!memcmp(s, &now, sizeof(now)), marker);
}
static void reader_hook(enum uk_state state)
{
    struct snapshot before = snap();
    unsigned long args[SW_MAX_API_PARAM] = {0}, rtn = 0xabc;
    uint32_t ca[SW_MAX_API_PARAM] = {0}, cr = 0xdef;
    args[1]=(unsigned long)&rtn;
    ca[1]=region(&cr,sizeof(cr));
    region(args,sizeof(args)); region(&rtn,sizeof(rtn));
    CHECK(misc_mtx.held && !api_ioctl_lock.held && uk_lifecycle_lock.held,
          "HOOK_LOCKS");
    CHECK(uk_state == state && cmd_buf == NULL, "UNPUBLISHED_STATE");
    CHECK(switch_device.fops->open(NULL,&hook_file) == -ENODEV, "HOOK_OPEN_REJECT");
    same(&before,"HOOK_OPEN_UNCHANGED");
    CHECK(switch_device.fops->unlocked_ioctl(&hook_file,0,(unsigned long)args) == -ENODEV,
          "HOOK_NATIVE_REJECT");
    same(&before,"HOOK_NATIVE_UNCHANGED");
    CHECK(switch_device.fops->compat_ioctl(&hook_file,0,region(ca,sizeof(ca))) == -ENODEV,
          "HOOK_COMPAT_REJECT");
    same(&before,"HOOK_COMPAT_UNCHANGED");
    CHECK(sw_uk_init(incoming) == SW_BUSY, "HOOK_INIT_BUSY");
    same(&before,"HOOK_INIT_UNCHANGED");
    CHECK(sw_uk_cleanup() == SW_BUSY, "HOOK_CLEANUP_BUSY");
    same(&before,"HOOK_CLEANUP_UNCHANGED");
    CHECK(rtn == 0xabc && cr == 0xdef, "HOOK_NO_RETURN_WRITE");
    nregions=0; ++hooks;
}
static int misc_register(struct miscdevice *dev)
{
    CHECK(dev == &switch_device, "MISC_IDENTITY");
    model_lock(&misc_mtx); ++registers;
    if (misc_owner == 2 || register_error) {
        model_unlock(&misc_mtx);
        return -EEXIST;
    }
    CHECK(!misc_owner, "REGISTER_EMPTY");
    reader_hook(UK_STARTING);
    misc_owner=1;
    if (dev->minor == MISC_DYNAMIC_MINOR) dev->minor=42;
    model_unlock(&misc_mtx);
    return 0;
}
static void misc_deregister(struct miscdevice *dev)
{
    CHECK(dev == &switch_device && misc_owner == 1, "FOREIGN_DEREGISTER");
    model_lock(&misc_mtx); ++deregisters;
    reader_hook(UK_STOPPING);
    misc_owner=0;
    model_unlock(&misc_mtx);
}

static sw_api_param_t params[SW_MAX_API_PARAM];
static sw_api_func_t function;
static unsigned nr, pointer_mode, active_probe;
static sw_error_t lookup_error, command_error;
static unsigned char input_bytes[16], output_bytes[16];
static sw_error_t command(unsigned long first, ...)
{
    va_list ap;
    unsigned i;
    struct snapshot before;
    CHECK(api_ioctl_lock.held && uk_state == UK_READY, "COMMAND_LOCK");
    ++dispatches;
    if (pointer_mode) {
        CHECK(first == 0x51 && nr == 3, "COMMAND_SCALAR");
        va_start(ap,first);
        for (i=1; i<3; ++i) {
            unsigned char *p=(unsigned char *)va_arg(ap,unsigned long);
            CHECK(p == (unsigned char *)&cmd_buf[3+(i-1)], "POINTER_PLACEMENT");
            CHECK(!memcmp(p,input_bytes,8), "INPUT_PAYLOAD");
            memcpy(p,output_bytes,8);
        }
        va_end(ap);
    } else {
        CHECK(first == 101, "DISPATCH_ARGUMENTS");
        va_start(ap,first);
        for (i=1; i<nr; ++i)
            CHECK(va_arg(ap,unsigned long) == 101+i, "DISPATCH_ARGUMENTS");
        va_end(ap);
    }
    if (active_probe) {
        before=snap();
        CHECK(sw_uk_cleanup() == SW_BUSY, "COMMAND_CLEANUP_BUSY");
        same(&before,"COMMAND_CLEANUP_UNCHANGED");
        CHECK(sw_uk_init(incoming) == SW_BUSY, "COMMAND_INIT_BUSY");
        same(&before,"COMMAND_INIT_UNCHANGED");
    }
    return command_error;
}
static sw_error_t sw_api_get(sw_api_t *api)
{
    ++lookups;
    CHECK(api->api_id == 123, "API_ID");
    if (lookup_error) return lookup_error;
    function.api_id=123; function.func=(void *)command;
    api->api_fp=&function; api->api_pp=params; api->api_nr=nr;
    return SW_OK;
}
static void setup_command(unsigned n, int pointers)
{
    unsigned i;
    nr=n; pointer_mode=(unsigned)pointers; lookup_error=SW_OK; command_error=SW_OK;
    active_probe=0; fail_from=fail_to=from_calls=to_calls=0; nregions=0;
    memset(params,0,sizeof(params));
    for (i=0;i<n && i<SW_MAX_API_PARAM;++i) params[i].api_id=123;
    for (i=0;i<16;++i) { input_bytes[i]=(unsigned char)(0x30+i); output_bytes[i]=(unsigned char)(0xa0+i); }
    if (pointers) {
        params[1].param_type=SW_PARAM_PTR|SW_PARAM_IN|SW_PARAM_OUT;
        params[1].data_size=5;
        params[2].param_type=SW_PARAM_PTR|SW_PARAM_IN|SW_PARAM_OUT;
        params[2].data_size=1;
    }
}
static long issue(struct file *file, int compat, sw_error_t expected, int return_copy_fails)
{
    unsigned long args[SW_MAX_API_PARAM] = {123}, result=0x1234;
    uint32_t ca[SW_MAX_API_PARAM] = {123}, cr=0x1234;
    unsigned char payload[2][16];
    unsigned i, before=dispatches;
    long rv;
    memset(payload,0xcc,sizeof(payload));
    for(i=0;i<2;++i) memcpy(payload[i],input_bytes,8);
    region(args,sizeof(args)); region(&result,sizeof(result));
    args[1]=(unsigned long)&result; ca[1]=region(&cr,sizeof(cr));
    for(i=0;i<10;++i) { args[i+2]=101+i; ca[i+2]=101+i; }
    if (pointer_mode) {
        args[2]=ca[2]=0x51;
        for(i=0;i<2;++i) {
            args[i+3]=(unsigned long)payload[i]; ca[i+3]=region(payload[i],sizeof(payload[i]));
        }
    }
    rv=compat ? switch_compat_ioctl(file,0,region(ca,sizeof(ca))) :
                switch_ioctl(file,0,(unsigned long)args);
    if (expected == (sw_error_t)-ENODEV) {
        CHECK(rv == -ENODEV && dispatches == before, "STALE_FD_REJECT");
        CHECK(result == 0x1234 && cr == 0x1234, "STALE_FD_NO_WRITE");
    } else if (fail_from == 1) {
        CHECK(rv == SW_NO_RESOURCE && dispatches == before, "HEADER_COPY_FAILURE");
    } else {
        CHECK(rv == SW_OK, "IOCTL_RETURN_CONTRACT");
        if (return_copy_fails) CHECK(result==0x1234 && cr==0x1234, "RETURN_COPY_FAILURE");
        else if (compat) CHECK(cr == (uint32_t)expected, "API_RETURN_WORD");
        else CHECK(result == (unsigned long)expected, "API_RETURN_WORD");
        if (pointer_mode && expected == SW_OK) {
            for(i=0;i<2;++i) {
                size_t written=compat && i==1 ? 4 : 8;
                CHECK(!memcmp(payload[i],output_bytes,written), "OUTPUT_PAYLOAD");
                CHECK(!memcmp(payload[i]+written,input_bytes+written,8-written), "OUTPUT_EXTENT");
                CHECK(payload[i][8] == 0xcc, "OUTPUT_EXTENT");
            }
        }
    }
    nregions=0;
    return rv;
}
static void opened(struct file *f)
{
    unsigned old=live_count();
    model_lock(&misc_mtx);
    CHECK(switch_device.fops->open(NULL,f)==SW_OK,"OPEN_READY");
    model_unlock(&misc_mtx);
    CHECK(f->private_data && block_of(f->private_data)->live &&
          block_of(f->private_data)->n==sizeof(struct uk_file_context) &&
          ((struct uk_file_context *)f->private_data)->epoch==uk_epoch && live_count()==old+1,
          "CONTEXT_IDENTITY");
}
static void closed(struct file *f)
{
    void *p=f->private_data;
    unsigned long *buffer=cmd_buf;
    CHECK(switch_close(NULL,f)==SW_OK && !f->private_data, "CONTEXT_CLOSE");
    CHECK(p && !block_of(p)->live && cmd_buf==buffer, "CONTEXT_CLOSE_OWNER");
    CHECK(switch_close(NULL,f)==SW_OK && cmd_buf==buffer, "CONTEXT_CLOSE_REPEAT");
}
static void ready(void)
{
    uint64_t epoch=uk_epoch;
    unsigned a=alloc_calls, r=registers;
    CHECK(sw_uk_init(incoming)==SW_OK,"INIT_SUCCESS");
    CHECK(uk_state==UK_READY && cmd_buf && block_of(cmd_buf)->live &&
          block_of(cmd_buf)->n==SW_MAX_API_BUF && misc_owner==1 &&
          alloc_calls==a+1 && registers==r+1 && uk_epoch==epoch+1,
          "INIT_COMMIT");
#ifdef UK_MINOR_DEV
    CHECK(uk_protocol==UK_MINOR_DEV && switch_device.minor==UK_MINOR_DEV,"EFFECTIVE_MINOR");
#else
    CHECK(uk_protocol==incoming && switch_device.minor==(int)incoming,"EFFECTIVE_MINOR");
#endif
}
static void retired(void)
{
    uint64_t epoch=uk_epoch;
    unsigned live=live_count(), freed=free_calls, dr=deregisters;
    CHECK(sw_uk_cleanup()==SW_OK,"CLEANUP_SUCCESS");
    CHECK(uk_state==UK_OFF && !cmd_buf && !misc_owner && uk_epoch==epoch &&
          live_count()==live-1 && free_calls==freed+1 && deregisters==dr+1,
          "CLEANUP_LEDGER");
}
static void reset_model(void)
{
    unsigned i;
    CHECK(!api_ioctl_lock.held && !uk_lifecycle_lock.held && !misc_mtx.held,"LOCKS_RELEASED");
    CHECK(!live_count() && !cmd_buf && uk_state==UK_OFF && !misc_owner,"CASE_OWNER_CLOSURE");
    for(i=0;i<nblocks;++i) free(blocks[i].p);
    memset(blocks,0,sizeof(blocks)); nblocks=alloc_calls=free_calls=fail_alloc=0;
    registers=deregisters=dispatches=lookups=hooks=register_error=0;
    from_calls=to_calls=fail_from=fail_to=nregions=0;
    uk_epoch=0; uk_protocol=0; switch_device.minor=MISC_DYNAMIC_MINOR;
    hook_file.private_data=NULL;
}
static const char *const cases[] = {
    "empty", "buffer-oom", "register-foreign-retry", "register-error-retry",
    "minor-repeat-conflict", "context-oom", "payload-native", "payload-compat",
    "dispatch-arity", "copy-errors", "old-fd", "active-command", "epoch-cap",
    "inconsistent-state", "dynamic-minor"
};
static void run_case(unsigned index)
{
    struct file a={0}, b={0};
    struct snapshot before;
    unsigned i, d, frees;
    uint64_t epoch;
    switch(index) {
    case 0:
        before=snap();
        CHECK(sw_uk_cleanup()==SW_OK,"EMPTY_CLEANUP"); same(&before,"EMPTY_UNCHANGED");
        CHECK(switch_open(NULL,&a)==-ENODEV && !a.private_data,"OFF_OPEN");
        setup_command(1,0); issue(&a,0,(sw_error_t)-ENODEV,0);
        setup_command(1,0); issue(&a,1,(sw_error_t)-ENODEV,0);
        break;
    case 1:
        fail_alloc=1;
        CHECK(sw_uk_init(incoming)==SW_OUT_OF_MEM && uk_state==UK_OFF && !cmd_buf &&
              !registers && !free_calls && !uk_epoch && !live_count(),"BUFFER_OOM");
        fail_alloc=0; ready(); retired(); break;
    case 2:
    case 3:
        misc_owner=index==2?2:0; register_error=index==3;
        CHECK(sw_uk_init(incoming)==SW_INIT_ERROR,"REGISTER_ERROR");
        CHECK(uk_state==UK_OFF && !cmd_buf && !uk_epoch && live_count()==0 &&
              alloc_calls==1 && free_calls==1 && registers==1 && !deregisters &&
              misc_owner==(index==2?2:0),"REGISTER_ROLLBACK");
        misc_owner=0; register_error=0; ready(); retired(); break;
    case 4:
        ready(); before=snap();
        CHECK(sw_uk_init(incoming)==SW_OK,"REPEAT_SUCCESS"); same(&before,"REPEAT_UNCHANGED");
#ifdef UK_MINOR_DEV
        CHECK(sw_uk_init(incoming+1)==SW_OK,"MINOR_OVERRIDE");
#else
        CHECK(sw_uk_init(incoming+1)==SW_BAD_PARAM,"MINOR_CONFLICT");
#endif
        same(&before,"CONFLICT_UNCHANGED"); retired(); break;
    case 5:
        ready(); fail_alloc=alloc_calls+1;
        CHECK(switch_open(NULL,&a)==-ENOMEM && !a.private_data && live_count()==1,
              "CONTEXT_OOM");
        fail_alloc=0; opened(&a); closed(&a); retired(); break;
    case 6:
    case 7:
        ready(); opened(&a); setup_command(3,1);
        issue(&a,index==7,SW_OK,0); CHECK(dispatches==1,"PAYLOAD_DISPATCH");
        closed(&a); retired(); break;
    case 8:
        ready(); opened(&a);
        for(i=1;i<=10;++i) {
            setup_command(i,0); issue(&a,0,SW_OK,0);
            setup_command(i,0); issue(&a,1,SW_OK,0);
        }
        CHECK(dispatches==20,"DISPATCH_ARITY_COUNT");
        setup_command(0,0); issue(&a,0,SW_OUT_OF_RANGE,0);
        setup_command(0,0); issue(&a,1,SW_OUT_OF_RANGE,0);
        CHECK(input_parser(params,0,NULL,NULL)==SW_BAD_PARAM &&
              output_parser(params,0,NULL,NULL)==SW_BAD_PARAM &&
              sw_api_cmd(NULL,NULL)==SW_BAD_PARAM,"NULL_PARSER_ARGUMENTS");
        closed(&a); retired(); break;
    case 9:
        ready(); opened(&a);
        for(i=0;i<2;++i) {
            setup_command(1,0); fail_from=1; issue(&a,(int)i,SW_NO_RESOURCE,0);
            setup_command(1,0); lookup_error=SW_NOT_FOUND; issue(&a,(int)i,SW_NOT_FOUND,0);
            setup_command(1,0); command_error=SW_FAIL; issue(&a,(int)i,SW_FAIL,0);
            setup_command(3,1); fail_from=2; issue(&a,(int)i,SW_NO_RESOURCE,0);
            setup_command(3,1); params[1].data_size=SW_MAX_API_BUF;
            issue(&a,(int)i,SW_NO_RESOURCE,0);
            setup_command(3,1); fail_to=1; issue(&a,(int)i,SW_NO_RESOURCE,0);
            setup_command(1,0); fail_to=1; issue(&a,(int)i,SW_OK,1);
        }
        closed(&a); retired(); break;
    case 10:
        ready(); opened(&a); epoch=uk_epoch; retired();
        setup_command(1,0); issue(&a,0,(sw_error_t)-ENODEV,0);
        setup_command(1,0); issue(&a,1,(sw_error_t)-ENODEV,0);
        ready(); CHECK(uk_epoch==epoch+1,"EPOCH_MONOTONIC");
        setup_command(1,0); issue(&a,0,(sw_error_t)-ENODEV,0);
        setup_command(1,0); issue(&a,1,(sw_error_t)-ENODEV,0);
        opened(&b); d=dispatches;
        setup_command(1,0); issue(&b,0,SW_OK,0);
        setup_command(1,0); issue(&b,1,SW_OK,0);
        CHECK(dispatches==d+2,"NEW_FD_DISPATCH");
        before=snap(); frees=free_calls; closed(&a);
        CHECK(free_calls==frees+1 && cmd_buf==before.buffer &&
              block_of(cmd_buf)->live && misc_owner==1 && uk_epoch==before.epoch,
              "OLD_CLOSE_PRESERVES_BUFFER");
        setup_command(1,0); issue(&b,0,SW_OK,0);
        closed(&b); retired(); break;
    case 11:
        ready(); opened(&a);
        for(i=0;i<2;++i) {
            setup_command(1,0); active_probe=1; issue(&a,(int)i,SW_OK,0);
        }
        closed(&a); retired(); break;
    case 12:
        uk_epoch=UINT64_MAX-1; ready(); CHECK(uk_epoch==UINT64_MAX,"EPOCH_FULL_WIDTH");
        opened(&a); setup_command(1,0); issue(&a,1,SW_OK,0); closed(&a); retired();
        before=snap(); CHECK(sw_uk_init(incoming)==SW_NO_RESOURCE,"EPOCH_CAP");
        same(&before,"EPOCH_CAP_UNCHANGED"); break;
    case 13:
        uk_state=UK_STARTING; before=snap();
        CHECK(sw_uk_init(incoming)==SW_BAD_STATE,"INCONSISTENT_INIT");
        same(&before,"INCONSISTENT_UNCHANGED");
        CHECK(sw_uk_cleanup()==SW_BAD_STATE,"INCONSISTENT_CLEANUP");
        same(&before,"INCONSISTENT_UNCHANGED"); uk_state=UK_OFF; break;
    case 14:
#ifndef UK_MINOR_DEV
        CHECK(sw_uk_init(MISC_DYNAMIC_MINOR)==SW_OK,"DYNAMIC_INIT");
        CHECK(uk_protocol==MISC_DYNAMIC_MINOR && switch_device.minor==42,"DYNAMIC_REQUEST_IDENTITY");
        before=snap(); CHECK(sw_uk_init(MISC_DYNAMIC_MINOR)==SW_OK,"DYNAMIC_REPEAT");
        same(&before,"DYNAMIC_REPEAT_UNCHANGED");
        CHECK(sw_uk_init(42)==SW_BAD_PARAM,"DYNAMIC_ASSIGNED_CONFLICT");
        same(&before,"DYNAMIC_CONFLICT_UNCHANGED"); retired();
#else
        ready(); retired();
#endif
        break;
    default: fail("UNKNOWN_CASE");
    }
    CHECK(!api_ioctl_lock.held && !uk_lifecycle_lock.held && !misc_mtx.held &&
          api_ioctl_lock.locks==api_ioctl_lock.unlocks &&
          uk_lifecycle_lock.locks==uk_lifecycle_lock.unlocks && misc_mtx.locks==misc_mtx.unlocks,
          "STABLE_MUTEX_BALANCE");
    reset_model();
}
int main(int argc, char **argv)
{
    unsigned i, matched=0;
    CHECK(sizeof(unsigned long)==8 && sizeof(compat_ulong_t)==4,"HOST_WORD_MODEL");
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        if(argc==1 || (argc==2 && !strcmp(argv[1],cases[i]))) {
            run_case(i); ++matched;
        }
    }
    CHECK(matched==(argc==1?15u:1u),"CASE_INVENTORY");
    /* No partial stdout: a negative must terminate before any success output. */
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);++i)
        if(argc==1 || !strcmp(argv[1],cases[i])) printf("OK %s\n",cases[i]);
    return 0;
}
