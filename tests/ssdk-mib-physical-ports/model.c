/* Host-only translation unit template; markers are replaced with prepared C. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t a_uint32_t, fal_port_t;
typedef unsigned long a_uint64_t;
typedef uint64_t u64;
typedef int sw_error_t, a_bool_t;
_Static_assert(sizeof(a_uint64_t) == 8, "requires LP64 host");
#define SW_OK 0
#define SW_BAD_PARAM -2
#define SW_BAD_PTR -1
#define SW_READ_ERROR -8
#define A_TRUE 1
#define A_FALSE 0
#define SW_MAX_NR_DEV 2
#define SW_MAX_NR_PORT 8
/* @types */

static const char *test;
#define CHECK(id, expr) do { if (!(expr)) { \
    printf("FAIL %s %s\n", test, id); exit(1); } } while (0)
static unsigned acquisitions;
static void take(int *l) { CHECK("lock-reentry", !*l); *l = 1; acquisitions++; }
static void drop(int *l) { CHECK("unlock-unheld", *l); *l = 0; }
#define spin_lock_irqsave(l, f) do { (f) = 0; take(l); } while (0)
#define spin_unlock_irqrestore(l, f) do { (void)(f); drop(l); } while (0)
#define mutex_lock take
#define mutex_unlock drop
static int fal_mib_lock;
static fal_mib_counter_t ram[2][8];
static fal_mib_counter_t *g_mibcounter[] = {ram[0], ram[1]};
struct switch_attr { int unused; };
struct switch_val { int port_vlan, len; union { char *s; } value; };
struct qca_phy_priv { unsigned device_id, ports, mib_loop_cnt; int reg_mutex, mib_lock, version;
    char buf[BUF_SIZE]; };
struct switch_dev { int ports; struct qca_phy_priv *priv; };
#define qca_phy_priv_get(d) ((d)->priv)
#define HPPE 1
#define QCA_VER_HPPE 1
#define QCA_VER_APPE 2
#define QCA_VER_MRPPE 3
#define PORT_XGMAC_TYPE 1
static struct qca_phy_priv priv[] = {{.device_id=0,.ports=3},
    {.device_id=1,.ports=6,.version=QCA_VER_HPPE}};
static struct switch_dev dev[] = {{3,&priv[0]}, {6,&priv[1]}};
static unsigned mac_queries;
static int qca_hppe_port_mac_type_get(unsigned d,int p)
{
    CHECK("mac-query",d==1 && p>0 && p<dev[d].ports);
    mac_queries++;
    return 0; /* This topology contains GMAC ports only. */
}
#define qca_ar8327_sw_print_xgport_mib(d,a,v) (abort(), -EIO)

enum op { RX, TX, BOTH, FLUSH };
struct event { unsigned d,p; enum op op; int status; unsigned rx,tx; };
static struct event trace[256];
static unsigned calls, warnings;
static int fail_port = -1;
static enum op fail_op;
/* Independent per-device register banks. A failed read may already clear data. */
static struct regs {unsigned rx,tx;} hw[2][8];
static int io(unsigned d, unsigned p, enum op op, fal_mib_info_t *out)
{
    CHECK("trace-space", calls < sizeof(trace)/sizeof(trace[0]));
    CHECK("fal-lock", fal_mib_lock);
    int rv = (d >= 2 || !p || p >= priv[d].ports || p >= 8) ? -3 :
        ((int)p == fail_port && op == fail_op ? -17 : SW_OK);
    struct event *e = &trace[calls++];
    *e = (struct event){.d=d,.p=p,.op=op,.status=rv};
    if (rv != -3) {
        struct regs *r = &hw[d][p];
        if (op == FLUSH) {
            if (!rv) *r = (struct regs){0,0};
        } else {
            if (op != TX) { out->RxBroad = e->rx = r->rx; r->rx = 0; }
            if (op != RX) { out->TxBroad = e->tx = r->tx; r->tx = 0; }
        }
    }
    printf("IO dev=%u port=%u op=%s rx=%u tx=%u status=%d\n",d,p,
        (const char*[]){"RX","TX","BOTH","FLUSH"}[op],e->rx,e->tx,rv);
    return rv;
}
#define _fal_get_mib_info(d,p,o) io(d,p,BOTH,o)
#define _fal_get_rx_mib_info(d,p,o) io(d,p,RX,o)
#define _fal_get_tx_mib_info(d,p,o) io(d,p,TX,o)
#define _fal_mib_port_flush_counters(d,p) io(d,p,FLUSH,NULL)
static void warn_io(const char *fmt,unsigned d,unsigned p,const char *dir,int rv)
{
    CHECK("warn-without-io", calls);
    struct event e = trace[calls-1];
    CHECK("warn-args", d==e.d && p==e.p && rv==e.status &&
        !strcmp(dir,e.op==RX?"rx":"tx"));
    warnings++;
    printf(fmt,d,p,dir,rv);
}
#define pr_warn_ratelimited warn_io
/* @fal */
/* Kernel swconfig callbacks have intentionally unused ABI arguments. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
/* @ref */
#pragma GCC diagnostic pop

static void event(unsigned i,unsigned d,unsigned p,enum op op,int rv)
{
    CHECK("event-missing",i<calls);
    struct event e=trace[i];
    CHECK("event-device",e.d==d);
    CHECK("event-port",e.p==p);
    CHECK("event-direction",e.op==op);
    CHECK("event-status",e.status==rv);
}
static void tick(unsigned d,unsigned p,enum op op,int rv)
{
    unsigned n=calls,w=warnings;
    qca_ar8327_sw_mib_task(&priv[d]);
    CHECK("worker-call-count",calls==n+1);
    event(n,d,p,op,rv);
    CHECK("warning-count",warnings==w+(rv!=0));
}
static void publish(unsigned d,unsigned p,unsigned rx,unsigned tx)
{
    struct switch_val v={.port_vlan=(int)p};
    unsigned n=calls,m=mac_queries;
    CHECK("publish-status",!qca_ar8327_sw_get_port_mib(&dev[d],NULL,&v));
    CHECK("publish-dispatch",mac_queries==m+(d==1));
    CHECK("publish-calls",calls==n+1);
    event(n,d,p,BOTH,0);
    CHECK("publish-output",v.value.s==priv[d].buf && v.len==(int)strlen(v.value.s));
    char line[80];
    snprintf(line,sizeof(line),"Port %u MIB counters\n",p);
    CHECK("publish-port",!strncmp(v.value.s,line,strlen(line)));
    snprintf(line,sizeof(line),"\n%-12s: %u\n","RxBroad",rx);
    CHECK("publish-rx",strstr(v.value.s,line));
    snprintf(line,sizeof(line),"\n%-12s: %u\n","TxBroad",tx);
    CHECK("publish-tx",strstr(v.value.s,line));
}
static void blocked(unsigned d,unsigned p)
{
    fal_mib_counter_t old,out;
    memset(&old,0xa5,sizeof(old)); out=old;
    unsigned n=calls;
    CHECK("invalid-fal",fal_mib_counter_get(d,p,&out)==SW_READ_ERROR);
    CHECK("partial-output",!memcmp(&out,&old,sizeof(out)));
    char sentinel[]="unchanged";
    struct switch_val v={.port_vlan=(int)p,.len=79,.value.s=sentinel};
    CHECK("invalid-swconfig",qca_ar8327_sw_get_port_mib(&dev[d],NULL,&v)==-EIO);
    CHECK("invalid-output",v.len==79 && v.value.s==sentinel && calls==n);
}
static void single(unsigned d,int p,int rv)
{
    unsigned n=calls;
    struct switch_val v={.port_vlan=p};
    CHECK("single-result",qca_ar8327_sw_set_port_reset_mib(&dev[d],NULL,&v)==rv);
    CHECK("single-count",calls==n+(rv!=-EINVAL));
    if (rv!=-EINVAL) event(n,d,p,FLUSH,rv ? -17 : 0);
}
static void all(unsigned d,int bad)
{
    unsigned n=calls, ports=priv[d].ports, count=ports ? ports-1 : 0;
    fail_port=bad; fail_op=FLUSH;
    CHECK("reset-all-status",qca_ar8327_sw_set_reset_mibs(&dev[d],NULL,NULL)==
        (bad<0 ? 0 : -EIO));
    CHECK("reset-all-count",calls==n+count);
    for(unsigned p=1;p<ports;p++) event(n+p-1,d,p,FLUSH,(int)p==bad?-17:0);
    fail_port=-1;
}
static void cycles(void)
{
    struct regs totals[2][8]={0};
    /* Interleave unequal topologies. Stop each after exactly two laps + RX1. */
    for(unsigned i=0;i<21;i++) for(unsigned d=0;d<2;d++) {
        unsigned span=d?10:4;
        if(i>2*span) continue;
        unsigned p=1+(i%span)/2, value=1000*(d+1)+10*p+i;
        enum op op=i%2 ? TX : RX;
        if(op==RX) { hw[d][p].rx=value; totals[d][p].rx+=value; }
        else { hw[d][p].tx=value; totals[d][p].tx+=value; }
        tick(d,p,op,0);
        CHECK("read-clear-value",trace[calls-1].rx==(op==RX?value:0) &&
            trace[calls-1].tx==(op==TX?value:0));
        CHECK("cursor",priv[d].mib_loop_cnt==2+(i+1)%span);
        publish(d,p,totals[d][p].rx,totals[d][p].tx);
    }
    /* Check all ports again after both devices finish. */
    for(unsigned d=0;d<2;d++) for(unsigned p=1;p<priv[d].ports;p++)
        publish(d,p,totals[d][p].rx,totals[d][p].tx);
}
static void minimum_nonempty(void)
{
    const unsigned d=1,p=1;
    priv[d].ports=dev[d].ports=2;
    for(unsigned i=0;i<5;i++) {
        enum op op=i%2 ? TX : RX;
        unsigned value=11*(i+1);
        if(op==RX) hw[d][p].rx=value; else hw[d][p].tx=value;
        tick(d,p,op,0);
        CHECK("minimum-read-value",trace[calls-1].rx==(op==RX ? value : 0) &&
              trace[calls-1].tx==(op==TX ? value : 0));
        CHECK("minimum-cursor",priv[d].mib_loop_cnt==(op==RX ? 3U : 2U));
    }
    publish(d,p,99,66);
    single(d,0,-EINVAL); single(d,2,-EINVAL);
    all(d,-1); publish(d,p,0,0);
    CHECK("minimum-call-total",calls==8 && !warnings);
}
static void resets(void)
{
    for(unsigned d=0;d<2;d++) for(unsigned p=1;p<priv[d].ports;p++) {
        hw[d][p]=(struct regs){10+d+p,40+d+p};
        publish(d,p,10+d+p,40+d+p);
        hw[d][p]=(struct regs){1,2};
    }
    single(1,-1,-EINVAL); single(1,0,-EINVAL); single(1,6,-EINVAL);
    single(1,5,0); publish(1,5,0,0);
    all(1,3);
    for(unsigned p=1;p<6;p++) {
        if(p==3) { CHECK("flush-preserves-ram",ram[1][3].RxBroad==14); blocked(1,3); }
        else publish(1,p,0,0);
    }
    for(unsigned p=1;p<3;p++) publish(0,p,11+p,42+p);
    all(1,-1);
    for(unsigned p=1;p<6;p++) publish(1,p,0,0);
}
static void faults(enum op op)
{
    unsigned d=1,p=2;
    priv[d].mib_loop_cnt=4+(op==TX);
    hw[d][p]=(struct regs){7,13}; publish(d,p,7,13);
    hw[d][p]=(struct regs){31,37}; fail_port=p; fail_op=op;
    tick(d,p,op,-17);
    CHECK("partial-not-added",ram[d][p].RxBroad==7 && ram[d][p].TxBroad==13);
    blocked(d,p);
    fail_port=-1;
    unsigned next=op==TX?3:2;
    tick(d,next,op==TX?RX:TX,0);
    priv[d].mib_loop_cnt=4; hw[d][p].rx=41; tick(d,p,RX,0);
    blocked(d,p);
    fail_port=p; fail_op=FLUSH; single(d,p,-EIO); blocked(d,p);
    fail_port=-1; publish(0,p,0,0);
    single(d,p,0); publish(d,p,0,0);
    hw[d][p].tx=53; tick(d,p,TX,0); publish(d,p,0,53);
}
static void reset_between_ticks(void)
{
    unsigned d=1,p=3;
    priv[d].mib_loop_cnt=2*p;
    hw[d][p]=(struct regs){71,97};
    tick(d,p,RX,0);
    CHECK("rx-before-reset",ram[d][p].RxBroad==71 && hw[d][p].tx==97);
    single(d,p,0);
    hw[d][p].tx+=11;
    tick(d,p,TX,0); publish(d,p,0,11);
    fail_port=p; fail_op=FLUSH;
    single(d,p,-EIO);
    fail_port=-1; priv[d].mib_loop_cnt=2*p;
    hw[d][p].rx=37; tick(d,p,RX,0);
    blocked(d,p);
    single(d,p,0); publish(d,p,0,0);
}
static void empty_tick(unsigned d)
{
    unsigned n=calls,w=warnings,a=acquisitions,cursor=priv[d].mib_loop_cnt;
    qca_ar8327_sw_mib_task(&priv[d]);
    CHECK("empty-worker-issued-io",calls==n);
    CHECK("empty-worker-warning",warnings==w);
    CHECK("empty-worker-took-lock",acquisitions==a);
    CHECK("empty-worker-moved-cursor",priv[d].mib_loop_cnt==cursor);
    CHECK("empty-worker-cleared-state",ram[d][1].RxBroad==59 &&
        hw[d][1].rx==83 && g_mibcounter_invalid[d][1]==A_TRUE);
}
static void empty_range(unsigned ports)
{
    /* Run the empty topology in each slot; the peer straddles it at RX1/TX1. */
    for(unsigned d=0;d<2;d++) {
        unsigned peer=1-d,saved=priv[d].ports;
        priv[d].ports=dev[d].ports=(int)ports;
        ram[d][1].RxBroad=59; hw[d][1].rx=83;
        g_mibcounter_invalid[d][1]=A_TRUE;
        priv[d].mib_loop_cnt=0;
        all(d,-1); single(d,0,-EINVAL); single(d,1,-EINVAL);
        empty_tick(d);
        hw[peer][1]=(struct regs){29,47};
        tick(peer,1,RX,0);
        priv[d].mib_loop_cnt=7;
        empty_tick(d);
        tick(peer,1,TX,0);
        publish(peer,1,29,47);
        printf("ISOLATION empty=%u ports=%u peer=%u RX1=29 TX1=47\n",d,ports,peer);
        /* Restore this test topology before it takes the role of healthy peer. */
        priv[d].ports=dev[d].ports=(int)saved;
        single(d,1,0); priv[d].mib_loop_cnt=0;
    }
}
int main(int argc,char **argv)
{
    if(argc!=2) return 2;
    test=argv[1];
    if(!strcmp(test,"cycles")) cycles();
    else if(!strcmp(test,"ports-2")) minimum_nonempty();
    else if(!strcmp(test,"resets")) resets();
    else if(!strcmp(test,"rx-error")) faults(RX);
    else if(!strcmp(test,"tx-error")) faults(TX);
    else if(!strcmp(test,"reset-between-ticks")) reset_between_ticks();
    else if(!strcmp(test,"empty-0") || !strcmp(test,"empty-1"))
        empty_range((unsigned)(test[6]-'0'));
    else return 2;
    CHECK("lock-balance",!fal_mib_lock && !priv[0].mib_lock && !priv[1].mib_lock &&
        !priv[0].reg_mutex && !priv[1].reg_mutex);
    printf("PASS %s\n",test); return 0;
}
