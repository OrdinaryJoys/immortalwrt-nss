/* Complete source functions/types; kernel locks, allocation and PHY I/O are host models. */
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#ifdef NDEBUG
#error Fixture checks cannot be disabled
#endif
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
typedef uint64_t a_uint64_t;
typedef int32_t a_int32_t;
typedef int a_bool_t;
#define phy_features_t a_uint16_t
#define SSDK_ERROR(...) ((void)0)
#define SSDK_INFO(...) ((void)0)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_ACQUIRE)
static void check(bool yes, const char *tag) {
    if (!yes) { fprintf(stderr, "PHY_OPS %s\n", tag); exit(86); }
}
typedef struct { pthread_mutex_t mutex; } host_spinlock_t;
#define DEFINE_SPINLOCK(name) host_spinlock_t name = {PTHREAD_MUTEX_INITIALIZER}
static _Thread_local bool irq_disabled, lock_held;
static atomic_uint locks, unlocks;
static void host_lock(host_spinlock_t *lock) {
    check(!lock_held && irq_disabled, "lock-acquire-state");
    check(!pthread_mutex_lock(&lock->mutex), "lock-acquire");
    lock_held = true; atomic_fetch_add(&locks, 1);
}
static void host_unlock(host_spinlock_t *lock) {
    check(lock_held && irq_disabled, "lock-release-state");
    lock_held = false; atomic_fetch_add(&unlocks, 1);
    check(!pthread_mutex_unlock(&lock->mutex), "lock-release");
}
#define spin_lock_irqsave(lock, flags) do { (flags)=irq_disabled; irq_disabled=true; host_lock(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { host_unlock(lock); irq_disabled=!!(flags); } while (0)
static void host_callback_unlocked(void);
/* TYPES */
int aquantia_phy_init(a_uint32_t, a_uint32_t);
/* GLOBALS */
static hsl_phy_ops_t borrowed_static;
static hsl_phy_ops_t *host_heap_borrow;
static phy_info_t *allocated_info[SW_MAX_NR_DEV];
static unsigned frees[SW_MAX_NR_DEV], callback_count, hw_calls, register_calls;
static int inject_registration, hw_result;
static unsigned exit_calls, exit_device, exit_bitmap;
static void kfree(void *pointer) {
    check(!lock_held, "free-outside-lock");
    for (unsigned i=0; i<SW_MAX_NR_DEV; ++i) {
        if (pointer && pointer==allocated_info[i]) {
            check(!frees[i], "metadata-free-once");
            ++frees[i]; free(pointer); return;
        }
    }
    check(false, "ops-not-owned");
}
/* CALLBACKS */
/* TABLE */
/* REGISTRY */
static int host_register_boundary(phy_type_t type, hsl_phy_ops_t *ops) {
    ++register_calls;
    if (inject_registration) { int result=inject_registration; inject_registration=0; return result; }
    return hsl_phy_api_ops_register(type, ops);
}
static int aquantia_phy_hw_init(a_uint32_t device, a_uint32_t bitmap) {
    (void)device; (void)bitmap;
    check(!lock_held && !irq_disabled, "hw-outside-lock");
    check(ssdk_phy_driver[AQUANTIA_PHY_CHIP].phy_ops==&aquantia_phy_api_ops,
          "hw-after-registration");
    ++hw_calls; return hw_result;
}
#define hsl_phy_api_ops_register host_register_boundary
/* AQUA */
#undef hsl_phy_api_ops_register
/* MAPPING */

static void host_callback_unlocked(void) {
    check(!lock_held && !irq_disabled, "callback-outside-lock");
    ++callback_count;
    check(hsl_phy_api_ops_register(F1_PHY_CHIP, &borrowed_static)==SW_OK, "callback-reentry");
}
static void reset_module(void) {
    check(!lock_held && !irq_disabled && atomic_load(&locks)==atomic_load(&unlocks), "balanced-locks");
    for (unsigned i=0; i<SW_MAX_NR_DEV; ++i) {
        if (allocated_info[i] && !frees[i]) free(allocated_info[i]);
    }
    memset(allocated_info,0,sizeof(allocated_info)); memset(frees,0,sizeof(frees));
    memset(phy_info,0,sizeof(phy_info)); memset(port_bmp,0,sizeof(port_bmp));
    for (unsigned i=0; i<MAX_PHY_CHIP; ++i) {
        ssdk_phy_driver[i].phy_ops=NULL;
        memset(ssdk_phy_driver[i].port_bmp,0,sizeof(ssdk_phy_driver[i].port_bmp));
        ssdk_phy_driver[i].exit=NULL;
    }
    /* Fixture module teardown, after dropping every publication; not SDK free. */
    free(host_heap_borrow); host_heap_borrow=NULL;
    inject_registration=hw_result=0; callback_count=hw_calls=register_calls=exit_calls=0;
}
static void info(unsigned device, unsigned port, phy_type_t type) {
    check(device<SW_MAX_NR_DEV && port<SW_MAX_NR_PORT && !phy_info[device], "fixture-info");
    allocated_info[device]=calloc(1,sizeof(phy_info_t)); check(allocated_info[device]!=NULL, "fixture-allocation");
    phy_info[device]=allocated_info[device];
    for(unsigned p=0;p<SW_MAX_NR_PORT;++p) phy_info[device]->phy_type[p]=MAX_PHY_CHIP;
    phy_info[device]->phy_type[port]=type;
}
static void lock_delta(unsigned before, const char *tag) {
    check(!lock_held && !irq_disabled && atomic_load(&locks)==before+1 &&
          atomic_load(&unlocks)==atomic_load(&locks), tag);
}
static void registration(void) {
    unsigned before=atomic_load(&locks);
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,&borrowed_static)==SW_OK,"register-first");
    lock_delta(before,"register-locked");
    before=atomic_load(&locks);
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,&borrowed_static)==SW_OK,"register-idempotent");
    lock_delta(before,"register-locked");
    hsl_phy_ops_t other={0};
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,&other)==SW_BUSY &&
          ssdk_phy_driver[F1_PHY_CHIP].phy_ops==&borrowed_static,"register-no-replace");
}
static void invalid_registration(void) {
    phy_driver_instance_t before[MAX_PHY_CHIP+1]; memcpy(before,ssdk_phy_driver,sizeof(before));
    const phy_type_t ids[]={(phy_type_t)-1,MAX_PHY_CHIP,(phy_type_t)(MAX_PHY_CHIP+1),(phy_type_t)UINT32_MAX};
    for(unsigned i=0;i<sizeof(ids)/sizeof(ids[0]);++i) {
        check(hsl_phy_api_ops_register(ids[i],&borrowed_static)==SW_BAD_PARAM,"register-invalid");
        check(hsl_phy_api_ops_unregister(ids[i],&borrowed_static)==SW_BAD_PARAM,"unregister-invalid");
        check(phy_api_ops_init(ids[i])==SW_BAD_PARAM,"prepare-invalid");
    }
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,NULL)==SW_BAD_PARAM,"register-invalid");
    check(hsl_phy_api_ops_unregister(F1_PHY_CHIP,NULL)==SW_BAD_PARAM,"unregister-invalid");
    check(!memcmp(before,ssdk_phy_driver,sizeof(before)),"invalid-preserves-registry");
}
static void unregister_live(void) {
    registration(); hsl_phy_ops_t other={0};
    phy_driver_instance_t expected[MAX_PHY_CHIP+1]; memcpy(expected,ssdk_phy_driver,sizeof(expected));
    unsigned before=atomic_load(&locks);
    check(hsl_phy_api_ops_unregister(F1_PHY_CHIP,&other)==SW_NOT_FOUND &&
          !memcmp(expected,ssdk_phy_driver,sizeof(expected)),"unregister-stale");
    lock_delta(before,"unregister-locked");
    check(hsl_phy_api_ops_unregister(F1_PHY_CHIP,&borrowed_static)==SW_BUSY &&
          !memcmp(expected,ssdk_phy_driver,sizeof(expected)),"unregister-live");
}
static void prepare_slot(void) {
    unsigned before=atomic_load(&locks);
    check(phy_api_ops_init(F1_PHY_CHIP)==SW_OK,"prepare-empty");
    lock_delta(before,"prepare-locked"); registration();
    check(phy_api_ops_init(F1_PHY_CHIP)==SW_BUSY &&
          ssdk_phy_driver[F1_PHY_CHIP].phy_ops==&borrowed_static,"prepare-occupied");
}
static void getters(void) {
    check(!hsl_phy_api_ops_get(SW_MAX_NR_DEV,0) && !hsl_phy_api_ops_get(UINT32_MAX,0) &&
          !hsl_phy_api_ops_get(0,SW_MAX_NR_PORT) && !hsl_phy_api_ops_get(0,UINT32_MAX) &&
          !hsl_phy_api_ops_get(0,0),"getter-invalid");
    info(SW_MAX_NR_DEV-1,SW_MAX_NR_PORT-1,F1_PHY_CHIP); registration();
    unsigned before=atomic_load(&locks);
    check(hsl_phy_api_ops_get(SW_MAX_NR_DEV-1,SW_MAX_NR_PORT-1)==&borrowed_static,"getter-valid");
    lock_delta(before,"getter-locked");
    phy_info[SW_MAX_NR_DEV-1]->phy_type[SW_MAX_NR_PORT-1]=UINT32_MAX;
    check(!hsl_phy_api_ops_get(SW_MAX_NR_DEV-1,SW_MAX_NR_PORT-1),"getter-invalid-type");
    phy_info[SW_MAX_NR_DEV-1]->phy_type[SW_MAX_NR_PORT-1]=MAX_PHY_CHIP;
    check(!hsl_phy_api_ops_get(SW_MAX_NR_DEV-1,SW_MAX_NR_PORT-1),"getter-invalid-type");
}
static void peer(unsigned own, bool heap) {
    hsl_phy_ops_t *ops=heap?calloc(1,sizeof(*ops)):&borrowed_static;
    if(heap) host_heap_borrow=ops;
    check(ops!=NULL,"borrow-allocation"); info(0,0,F1_PHY_CHIP); info(1,0,F1_PHY_CHIP);
    ssdk_phy_driver[F1_PHY_CHIP].phy_ops=ops;
    ssdk_phy_driver[F1_PHY_CHIP].port_bmp[0]=own;
    ssdk_phy_driver[F1_PHY_CHIP].port_bmp[1]=1; port_bmp[0]=own; port_bmp[1]=1;
    phy_driver_instance_t expected[MAX_PHY_CHIP+1]; memcpy(expected,ssdk_phy_driver,sizeof(expected));
    expected[F1_PHY_CHIP].port_bmp[0]=0;
    hsl_phy_ops_t *reader=hsl_phy_api_ops_get(1,0);
    check(reader==ops,"peer-initial");
    check(ssdk_phy_driver_cleanup(0)==SW_OK,"cleanup-status");
    check(hsl_phy_api_ops_get(1,0)==ops && reader==ops,"peer-visible");
    check(frees[0]==1 && !frees[1] && phy_info[1]==allocated_info[1],"peer-metadata");
    check(!memcmp(expected,ssdk_phy_driver,sizeof(expected)) && port_bmp[1]==1,"peer-state");
    check(!port_bmp[0] && !phy_info[0] && !ssdk_phy_driver[F1_PHY_CHIP].port_bmp[0],"local-state");
    check(ssdk_phy_driver_cleanup(0)==SW_OK && frees[0]==1,"cleanup-repeat");
    if(heap) check(ops->phy_speed_get==NULL,"borrowed-heap-live");
}
static void old_zero(void) { peer(0,false); }
static void old_own(void) { peer(1,false); }
static void heap_peer(void) { peer(1,true); }
static void empty_device(void) {
    info(1,0,F1_PHY_CHIP); registration();
    check(ssdk_phy_driver_cleanup(0)==SW_OK &&
          hsl_phy_api_ops_get(1,0)==&borrowed_static && !frees[1],"empty-device-peer");
}
static void invalid_cleanup(void) {
    check(ssdk_phy_driver_cleanup(SW_MAX_NR_DEV)==SW_BAD_PARAM &&
          ssdk_phy_driver_cleanup(UINT32_MAX)==SW_BAD_PARAM,"cleanup-bounds");
}
static void exit_callback(unsigned device,unsigned bitmap) {
    check(!lock_held && !irq_disabled,"exit-outside-lock");
    check(ssdk_phy_driver[F1_PHY_CHIP].port_bmp[device]==bitmap,"exit-before-bitmap-clear");
    ++exit_calls; exit_device=device; exit_bitmap=bitmap;
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,&borrowed_static)==SW_OK,"exit-reentry");
}
static void callback_exit(void) {
    info(0,0,F1_PHY_CHIP); registration();
    ssdk_phy_driver[F1_PHY_CHIP].exit=exit_callback; ssdk_phy_driver[F1_PHY_CHIP].port_bmp[0]=3;
    check(ssdk_phy_driver_cleanup(0)==SW_OK && exit_calls==1 && exit_device==0 && exit_bitmap==3,"exit-local");
    check(ssdk_phy_driver_cleanup(0)==SW_OK && exit_calls==1,"exit-repeat");
}
static void aqua_repeated(void) {
    check_mapping(); check(!aquantia_phy_init(0,1) && !aquantia_phy_init(1,2),"aqua-register");
    check(hw_calls==2 && register_calls==2,"aqua-repeated-hw");
    info(1,0,AQUANTIA_PHY_CHIP);
    hsl_phy_ops_t *ops=hsl_phy_api_ops_get(1,0);
    check(ops==&aquantia_phy_api_ops,"aqua-static");
    check(!ops->phy_speed_get(1,0,NULL) && callback_count==1,"aqua-callback");
    check(!ssdk_phy_driver_cleanup(0) && hsl_phy_api_ops_get(1,0)==ops,"aqua-peer");
}
static void aqua_retry(void) {
    inject_registration=SW_FAIL;
    check(aquantia_phy_init(0,1)==SW_FAIL && !hw_calls,"registration-first-error");
    check(aquantia_phy_init(0,1)==SW_OK && hw_calls==1 && register_calls==2,"registration-retry");
}
static void aqua_foreign(void) {
    check(hsl_phy_api_ops_register(AQUANTIA_PHY_CHIP,&borrowed_static)==SW_OK,"aqua-foreign-setup");
    check(aquantia_phy_init(0,1)==SW_BUSY && !hw_calls &&
          ssdk_phy_driver[AQUANTIA_PHY_CHIP].phy_ops==&borrowed_static,"aqua-foreign-preserved");
}
static void aqua_hw_error(void) {
    hw_result=SW_TIMEOUT;
    check(aquantia_phy_init(0,1)==SW_TIMEOUT && hw_calls==1,"hw-first-error");
    hw_result=SW_OK;
    check(aquantia_phy_init(0,1)==SW_OK && hw_calls==2,"hw-retry");
}
static void irq_restore(void) {
    irq_disabled=true;
    check(hsl_phy_api_ops_register(F1_PHY_CHIP,&borrowed_static)==SW_OK && irq_disabled && !lock_held,"irq-restored");
    irq_disabled=false;
}
static pthread_mutex_t start_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t start_cond=PTHREAD_COND_INITIALIZER;
static unsigned ready; static bool go;
struct writer { hsl_phy_ops_t ops; int rv; };
static void *writer(void *p) {
    struct writer *w=p;
    check(!pthread_mutex_lock(&start_mutex),"thread-start-lock"); ++ready;
    check(!pthread_cond_broadcast(&start_cond),"thread-start-signal");
    while(!go) check(!pthread_cond_wait(&start_cond,&start_mutex),"thread-start-wait");
    check(!pthread_mutex_unlock(&start_mutex),"thread-start-unlock");
    w->rv=hsl_phy_api_ops_register(F1_PHY_CHIP,&w->ops);
    check(!lock_held && !irq_disabled,"thread-restored"); return NULL;
}
static void concurrent_writers(void) {
    struct writer a={0},b={0}; pthread_t ta,tb; ready=0; go=false;
    check(!pthread_create(&ta,NULL,writer,&a) && !pthread_create(&tb,NULL,writer,&b),"thread-create");
    check(!pthread_mutex_lock(&start_mutex),"start-lock");
    while(ready!=2) check(!pthread_cond_wait(&start_cond,&start_mutex),"start-wait");
    go=true; check(!pthread_cond_broadcast(&start_cond),"start-signal");
    check(!pthread_mutex_unlock(&start_mutex),"start-unlock");
    check(!pthread_join(ta,NULL) && !pthread_join(tb,NULL),"thread-join");
    check((a.rv==SW_OK && b.rv==SW_BUSY && ssdk_phy_driver[0].phy_ops==&a.ops) ||
          (b.rv==SW_OK && a.rv==SW_BUSY && ssdk_phy_driver[0].phy_ops==&b.ops),"one-publisher");
}
struct testcase { const char *name; void (*run)(void); };
static struct testcase cases[]={
    {"registration",registration},{"invalid-registration",invalid_registration},
    {"unregister-live",unregister_live},{"prepare-slot",prepare_slot},{"getters",getters},
    {"old-phy-no-own",old_zero},{"old-phy-own",old_own},{"borrowed-heap",heap_peer},
    {"empty-device",empty_device},{"invalid-cleanup",invalid_cleanup},{"callback-exit",callback_exit},
    {"aqua-repeated",aqua_repeated},{"aqua-retry",aqua_retry},{"aqua-foreign",aqua_foreign},
    {"aqua-hw-error",aqua_hw_error},{"irq-restore",irq_restore},{"concurrent-writers",concurrent_writers}
};
int main(int argc,char **argv) {
    check(argc==1 || argc==2,"cli"); bool found=false;
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        if(argc==2 && strcmp(argv[1],cases[i].name)) continue;
        found=true; reset_module(); cases[i].run();
        check(!lock_held && !irq_disabled,"lock-restored");
        printf("PASS %s\n",cases[i].name);
    }
    check(found,"unknown-case"); reset_module(); return 0;
}
