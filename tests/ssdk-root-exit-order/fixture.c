/* Complete actual regi_exit plus explicit serial producer/cleanup/log models. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "sdk.h"
#define __exit
#define SSDK_STR "host"
struct private_model { a_bool_t qca_ssdk_sw_dev_registered; unsigned sentinel; };
static struct private_model private_slots[SW_MAX_NR_DEV];
static struct private_model *qca_phy_priv_global[SW_MAX_NR_DEV];
static unsigned ndev, registered, drivers[SW_MAX_NR_DEV], switches[SW_MAX_NR_DEV];
static unsigned sfps[SW_MAX_NR_DEV], cleaned[SW_MAX_NR_DEV], platforms[SW_MAX_NR_DEV];
static unsigned notifier, controls, freed;
static sw_error_t errors[SW_MAX_NR_DEV];
static char trace[262144]; static size_t used;
struct input { unsigned n,mask; int errors[3]; };
#include "cases.h"
static _Noreturn void fail(const char *s) { fprintf(stderr,"ROOT_ASSERT:%s\n",s); exit(86); }
#define CHECK(c,s) do { if (!(c)) fail(s); } while (0)
static void emit(const char *fmt,...) __attribute__((format(printf,1,2)));
static void emit(const char *fmt,...)
{
    va_list ap; va_start(ap,fmt); int len=vsnprintf(trace+used,sizeof(trace)-used,fmt,ap); va_end(ap);
    CHECK(len>=0 && (size_t)len<sizeof(trace)-used,"TRACE_CAPACITY"); used+=(size_t)len;
}
static int all(const unsigned *values)
{ for (unsigned d=0;d<ndev;++d) if (values[d]!=1) return 0; return 1; }
static int producers_stopped(void)
{
    for (unsigned d=0;d<ndev;++d)
        if (!drivers[d] || (HAS_SWITCH_GUARD && (registered&(1u<<d)) && !switches[d])) return 0;
    return 1;
}
static void valid(unsigned d) { CHECK(d<ndev,"DEVICE_BOUNDARY"); }
void ssdk_netdev_notifier_unregister(void)
{ CHECK(!notifier,"NOTIFIER_ONCE"); notifier=1; emit("NOTIFIER\n"); }
void ssdk_fdb_retire_controls(void)
{ CHECK(notifier && !controls,"CONTROLS_ORDER"); controls=1; emit("CONTROLS\n"); }
a_uint32_t ssdk_switch_device_num_get(void) { emit("GET %u\n",ndev); return ndev; }
void ssdk_driver_unregister(a_uint32_t d)
{ valid(d); CHECK(notifier && controls && !drivers[d],"PRODUCER_ONCE"); drivers[d]=1; emit("DRIVER %u\n",d); }
void ssdk_switch_unregister(a_uint32_t d)
{
    valid(d); CHECK(HAS_SWITCH_GUARD && private_slots[d].qca_ssdk_sw_dev_registered==A_TRUE,"REGISTERED_GUARD");
    CHECK(drivers[d] && !switches[d],"SWITCH_ONCE"); switches[d]=1; emit("SWITCH %u\n",d);
}
void sfp_phy_exit(a_uint32_t d)
{
    valid(d); CHECK(producers_stopped(),"PRODUCER_BARRIER");
    CHECK(EXPECT_SFP && !sfps[d],"SFP_ONCE"); sfps[d]=1; emit("SFP %u\n",d);
}
sw_error_t ssdk_cleanup(a_uint32_t d)
{
    valid(d); CHECK(producers_stopped(),"PRODUCER_BARRIER"); CHECK(!EXPECT_SFP || all(sfps),"SFP_BARRIER");
    CHECK(!cleaned[d],"CLEANUP_ONCE"); cleaned[d]=1; emit("CLEANUP %u %d\n",d,errors[d]); return errors[d];
}
void ssdk_plat_exit(a_uint32_t d)
{ valid(d); CHECK(all(cleaned),"PLATFORM_EARLY"); CHECK(!platforms[d],"PLATFORM_ONCE"); platforms[d]=1; emit("PLATFORM %u\n",d); }
void ssdk_free_priv(void)
{ CHECK(all(platforms) && all(cleaned) && !freed,"PRIVATE_TAIL"); freed=1; emit("FREE\n"); }
static void model_log(const char *level,const char *fmt,...) __attribute__((format(printf,2,3)));
static void model_log(const char *level,const char *fmt,...)
{
    char line[256], expected[256]; va_list ap;
    va_start(ap,fmt); int len=vsnprintf(line,sizeof(line),fmt,ap); va_end(ap);
    CHECK(len>=0 && (size_t)len<sizeof(line),"LOG_CAPACITY");
    if (strstr(fmt,"module exit")) {
        CHECK(all(cleaned),"CLEANUP_MISSING");
        if (strstr(fmt,"failed")) {
            int first=0; for (unsigned d=0;d<ndev;++d) if (errors[d] && !first) first=errors[d];
            snprintf(expected,sizeof(expected),"qca-host module exit failed! (code: %d)\n",first);
            CHECK(!strcmp(line,expected),"FIRST_ERROR");
        }
    }
    emit("%s %s",level,line);
}
#define SSDK_INFO(...) model_log("INFO",__VA_ARGS__)
#define SSDK_ERROR(...) model_log("ERROR",__VA_ARGS__)
#include "actual.c"
static void run_case(unsigned ix)
{
    const struct input *in=&inputs[ix]; ndev=in->n; registered=in->mask;
    CHECK(ndev<=SW_MAX_NR_DEV,"MODEL_CAPACITY"); notifier=controls=freed=0;
    memset(drivers,0,sizeof(drivers)); memset(switches,0,sizeof(switches)); memset(sfps,0,sizeof(sfps));
    memset(cleaned,0,sizeof(cleaned)); memset(platforms,0,sizeof(platforms));
    for (unsigned d=0;d<SW_MAX_NR_DEV;++d) {
        errors[d]=(sw_error_t)in->errors[d]; private_slots[d].qca_ssdk_sw_dev_registered=(registered&(1u<<d))?A_TRUE:A_FALSE;
        private_slots[d].sentinel=0x100u+d; qca_phy_priv_global[d]=&private_slots[d];
    }
    emit("CASE %u %u %u %d %d %d\n",ix,ndev,registered,errors[0],errors[1],errors[2]); regi_exit();
    CHECK(notifier && controls && freed && all(drivers) && all(cleaned) && all(platforms),"COMPLETE_TAIL");
    CHECK(!EXPECT_SFP || all(sfps),"SFP_COMPLETE");
    for (unsigned d=0;d<SW_MAX_NR_DEV;++d) {
        CHECK(private_slots[d].sentinel==0x100u+d,"PRIVATE_SENTINEL");
        if (d>=ndev) CHECK(!drivers[d] && !switches[d] && !sfps[d] && !cleaned[d] && !platforms[d],"FOREIGN_PEER");
    }
    emit("END\n");
}
int main(int argc,char **argv)
{
    unsigned count=0, selected=argc==2?(unsigned)strtoul(argv[1],NULL,10):0;
    CHECK(argc==1 || argc==2,"ARGUMENTS");
    for (unsigned i=0;i<sizeof(inputs)/sizeof(inputs[0]);++i) if (argc==1 || selected==i) { run_case(i); ++count; }
    CHECK(count==(argc==1?26u:1u),"CASE_INVENTORY");
    CHECK(fwrite(trace,1,used,stdout)==used,"STDOUT"); return 0;
}
