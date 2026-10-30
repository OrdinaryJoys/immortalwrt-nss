#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#define A_TRUE 1
#define A_FALSE 0
#define QCA_VER_HPPE 0x15
#define QCA_VER_APPE 0x20
#define QCA_VER_MRPPE 0x21
#define QCA_VER_MHT 0x17
#define QCA_FDB_SW_SYNC_WORK_DELAY 100
#define SSDK_DEBUG(...) ((void)0)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define SW_PBMP_OR(a,b) ((a)|=(b))
#define SW_PBMP_AND(a,b) ((a)&=(b))
#define msecs_to_jiffies(x) (x)
#define aos_lock_init(p) ((void)(p))
#define aos_lock_bh(p) ((void)(p))
#define aos_unlock_bh(p) ((void)(p))
#define INIT_LIST_HEAD(p) ((void)(p))
typedef unsigned fal_pbmp_t;
struct work_struct {void(*fn)(struct work_struct*);bool pending;};
struct delayed_work {struct work_struct work;};
struct qca_phy_priv {unsigned version,fdb_sw_sync_lock,sw_fdb_tbl,fdb_sw_sync_port_map;bool fdb_polling_started;struct delayed_work fdb_sw_sync_dwork;};
#define INIT_DELAYED_WORK(w,f) ((w)->work.fn=(f))
static int schedule_delayed_work(struct delayed_work *w,unsigned n){(void)n;w->work.pending=true;return 1;}
static bool cancel_delayed_work_sync(struct delayed_work *w){bool p=w->work.pending;w->work.pending=false;return p;}
static void ref_fdb_sw_sync_reset(struct qca_phy_priv *p,fal_pbmp_t m){(void)p;(void)m;}
static void ref_fdb_sw_sync_task(struct qca_phy_priv *p){(void)p;}
/* OLD_FUNCTIONS */
int main(void){struct qca_phy_priv p={.version=QCA_VER_MHT};qca_fdb_sw_sync_work_init(&p);qca_fdb_sw_sync_work_start(&p,2);qca_fdb_sw_sync_work_stop(&p,2);if(p.fdb_polling_started&&p.fdb_sw_sync_dwork.work.pending){fprintf(stderr,"SSDK_FDB old-mht-still-running\n");return 86;}return 0;}
