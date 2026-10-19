#!/usr/bin/env python3
"""Actual HAL/cache functions; samples and pthread lock substitution are models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('extract_c',ROOT/'nss-dp-containment/extract_prepared_c.py')
extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('prepared',type=Path);p.add_argument('--ssdk',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path)
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)

def definition(text,name):
    matches=list(re.finditer(r'^(?:static\s+)?(?:int32_t|void|int)\s+'+re.escape(name)+r'\([^;{}]*\)\s*\{',extract.code_mask(text),re.M))
    if len(matches)!=1:raise ValueError(name)
    m=matches[0];return text[m.start():extract.block_end(text,m.end()-1)]+'\n'

header=(args.ssdk/'include/fal/fal_mib.h').read_text()
PREFIX=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
typedef uint64_t a_uint64_t;
typedef uint32_t a_uint32_t;
#define BUG_ON(c) assert(!(c))
struct rtnl_link_stats64 {uint64_t rx_packets,tx_packets,rx_bytes,tx_bytes,rx_errors,tx_errors,
 rx_dropped,tx_dropped,multicast,collisions,rx_length_errors,rx_over_errors,rx_crc_errors,
 rx_frame_errors,rx_fifo_errors,rx_missed_errors,tx_aborted_errors,tx_carrier_errors,
 tx_fifo_errors,tx_heartbeat_errors,tx_window_errors;};
struct nss_gmac_hal_dev {int unused;};
static int read_error;
static unsigned checks;
static void check(bool ok) {checks++;assert(ok);}
'''
CACHE_PREFIX=r'''
struct ops {int (*getndostats)(struct nss_gmac_hal_dev *,struct rtnl_link_stats64 *);};
struct nss_dp_dev {struct ops *gmac_hal_ops;struct nss_gmac_hal_dev *gmac_hal_ctx;
 pthread_mutex_t stats_lock;struct rtnl_link_stats64 last_stats;uint64_t stats_read_failures;
 bool stats_valid,stats_stale;};
#define spin_lock_irqsave(l,f) do {(f)=0;assert(!pthread_mutex_lock(l));} while(0)
#define spin_unlock_irqrestore(l,f) do {(void)(f);assert(!pthread_mutex_unlock(l));} while(0)
'''
MAIN=r'''
int main(void) {
    DEVICE
    struct rtnl_link_stats64 s={0},saved;
    PREPARE_SAMPLE
    int direct=HAL(d,&s);
    check(!direct&&s.rx_packets==10);
    check(s.rx_errors==17&&s.rx_length_errors==LENGTH_EXPECTED);
    check(s.tx_fifo_errors==11&&s.rx_dropped==DROP_EXPECTED);
    struct ops ops={.getndostats=HAL};
    struct nss_dp_dev priv={.gmac_hal_ops=&ops,.gmac_hal_ctx=d,.stats_lock=PTHREAD_MUTEX_INITIALIZER};
    nss_dp_collect_stats(&priv,&s);saved=s;
    check(priv.stats_valid&&!priv.stats_stale&&!priv.stats_read_failures);
    read_error=1;memset(&s,0,sizeof(s));nss_dp_collect_stats(&priv,&s);
    check(!memcmp(&s,&saved,sizeof(s))&&priv.stats_read_failures==1&&priv.stats_stale);
    struct nss_dp_dev empty={.gmac_hal_ops=&ops,.gmac_hal_ctx=d,.stats_lock=PTHREAD_MUTEX_INITIALIZER};
    memset(&s,0xa5,sizeof(s));nss_dp_collect_stats(&empty,&s);
    check(!s.rx_packets&&!empty.stats_valid&&empty.stats_stale&&empty.stats_read_failures==1);
    read_error=0;nss_dp_collect_stats(&priv,&s);
    check(priv.stats_valid&&!priv.stats_stale&&priv.stats_read_failures==1);
    check(!memcmp(&s,&saved,sizeof(s)));
    printf("{\"checks\":%u,\"failures\":0,\"hardware_modeled\":true}\n",checks);
    return 0;
}
'''

records=[]
for label,path,typ,name in [
 ('syn-gmac','hal/gmac_ops/syn/gmac/syn_if.c','fal_mib_counter_t','syn_get_netdev_stats'),
 ('syn-xgmac','hal/gmac_ops/syn/xgmac/syn_if.c','fal_xgmib_info_t','syn_get_netdev_stats'),
 ('qcom','hal/gmac_ops/qcom/qcom_if.c','fal_mib_counter_t','qcom_get_netdev_stats')]:
    text=(args.prepared/path).read_text()
    prefix=PREFIX+re.search(r'typedef\s+struct\s*\{[^}]+\}\s*'+typ+';',header).group()+'\n'
    prefix+='static '+typ+' sample;\n'
    if label=='qcom':
        prefix+='struct qcom_hal_dev {struct nss_gmac_hal_dev base;'+typ+' stats;};\n'
        prefix+='static int qcom_get_mib_stats(struct nss_gmac_hal_dev *d) {if(read_error)return -1;((struct qcom_hal_dev*)d)->stats=sample;return 0;}\n'
        device='struct qcom_hal_dev dev={0};struct nss_gmac_hal_dev *d=&dev.base;'
    else:
        helper='syn_get_xmib_stats' if label=='syn-xgmac' else 'syn_get_mib_stats'
        prefix+='static int '+helper+'(struct nss_gmac_hal_dev *d,'+typ+' *v) {(void)d;if(read_error)return -1;*v=sample;return 0;}\n'
        device='struct nss_gmac_hal_dev dev={0},*d=&dev;'
    cache=definition((args.prepared/'nss_dp_main.c').read_text(),'nss_dp_collect_stats')
    sample=('sample.RxUnicastGood=10;sample.RxFcsErr=2;sample.RxLengthError=3;sample.RxRuntErr=5;sample.RxOverFlow=7;sample.TxUnderFlowError=11;sample.RxDropFrameGoodBad=13;'
        if label=='syn-xgmac' else 'sample.RxUniCast=10;sample.RxFcsErr=2;sample.RxTooLong=3;sample.RxRunt=5;sample.RxOverFlow=7;sample.TxUnderRun=11;')
    main=MAIN.replace('DEVICE',device).replace('PREPARE_SAMPLE',sample).replace('HAL',name)
    main=main.replace('LENGTH_EXPECTED','3' if label=='syn-xgmac' else '8').replace('DROP_EXPECTED','13' if label=='syn-xgmac' else '0')
    c=args.output/(label+'.c');c.write_text(prefix+CACHE_PREFIX+definition(text,name)+cache+main)
    command=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-pthread',str(c),'-o',str(c.with_suffix(''))]
    result=subprocess.run(command,capture_output=True)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(c.with_suffix(''))],capture_output=True)
    (args.output/(label+'.stdout')).write_bytes(result.stdout);(args.output/(label+'.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(label+' failed: '+result.stderr.decode())
    records.append(dict(label=label,hal_sha256=hashlib.sha256(text.encode()).hexdigest(),**json.loads(result.stdout)))

# The XGMAC structure consists of 64-bit fields, not u32 samples.
xg=(args.prepared/'hal/gmac_ops/syn/xgmac/syn_if.c').read_text()
body=re.search(r'typedef\s+struct\s*\{([^}]+)\}\s*fal_xgmib_info_t;',header).group(1)
assert not re.search(r'\ba_uint32_t\b',body)
prefix=PREFIX+re.search(r'typedef\s+struct\s*\{[^}]+\}\s*fal_xgmib_info_t;',header).group()+'\n'
prefix+=r'''
struct nss_dp_gmac_stats {uint64_t count;};
#define SYN_STATS_LEN 1
#define SYN_MIB_STATS_LEN 2
struct desc {unsigned stat_offset;};
static struct desc syn_gstrings_stats[]={{offsetof(struct nss_dp_gmac_stats,count)}};
static struct desc syn_gstrings_xmib_stats[]={{offsetof(fal_xgmib_info_t,RxByte)},{offsetof(fal_xgmib_info_t,RxFcsErr)}};
static int syn_get_xmib_stats(struct nss_gmac_hal_dev *d,fal_xgmib_info_t *v) {
 (void)d;v->RxByte=0x100000123ULL;v->RxFcsErr=0x200000007ULL;return 0;
}
'''
main=r'''
int main(void) {struct nss_gmac_hal_dev d={0};struct nss_dp_gmac_stats s={9};uint64_t data[3]={0};
 check(!syn_get_eth_stats(&d,data,&s));check(data[0]==9&&data[1]==0x100000123ULL&&data[2]==0x200000007ULL);
 printf("{\"checks\":%u,\"failures\":0}\n",checks);return 0;}
'''
for label,tree,must_pass in [('xg-width',args.prepared,True)]+([('baseline-xg-width',args.baseline,False)] if args.baseline else []):
    text=(tree/'hal/gmac_ops/syn/xgmac/syn_if.c').read_text()
    c=args.output/(label+'.c');c.write_text(prefix+definition(text,'syn_get_eth_stats')+main)
    result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable',str(c),'-o',str(c.with_suffix(''))],capture_output=True)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(c.with_suffix(''))],capture_output=True)
    (args.output/(label+'.stdout')).write_bytes(result.stdout);(args.output/(label+'.stderr')).write_bytes(result.stderr)
    if (result.returncode==0)!=must_pass:raise SystemExit('unexpected '+label)
    records.append(dict(label=label,returncode=result.returncode,expected=True))

def run_extra(label,code):
    c=args.output/(label+'.c');c.write_text(code)
    result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-pthread',str(c),'-o',str(c.with_suffix(''))],capture_output=True)
    (args.output/(label+'-compile.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(result.stderr.decode())
    result=subprocess.run([str(c.with_suffix(''))],capture_output=True)
    (args.output/(label+'.stdout')).write_bytes(result.stdout);(args.output/(label+'.stderr')).write_bytes(result.stderr)
    if result.returncode:raise SystemExit(label+': '+result.stderr.decode())
    records.append(dict(label=label,**json.loads(result.stdout)))

cache=definition((args.prepared/'nss_dp_main.c').read_text(),'nss_dp_collect_stats')
run_extra('concurrent-cache',PREFIX+CACHE_PREFIX+cache+r'''
static unsigned sequence;
static int sequenced(struct nss_gmac_hal_dev *d,struct rtnl_link_stats64 *s) {
 (void)d;unsigned n=++sequence;if(n%5==0)return -1;s->rx_packets=n;s->tx_bytes=n*17;return 0;
}
static void *reader(void *p) {
 struct nss_dp_dev *priv=p;uint64_t previous=0;
 for(int i=0;i<500;i++) {struct rtnl_link_stats64 s={0};nss_dp_collect_stats(priv,&s);
  assert(s.tx_bytes==s.rx_packets*17&&s.rx_packets>=previous);previous=s.rx_packets;}
 return NULL;
}
int main(void) {
 read_error=0;struct ops ops={.getndostats=sequenced};
 struct nss_dp_dev priv={.gmac_hal_ops=&ops,.stats_lock=PTHREAD_MUTEX_INITIALIZER};
 pthread_t workers[4];for(int i=0;i<4;i++)assert(!pthread_create(&workers[i],NULL,reader,&priv));
 for(int i=0;i<4;i++)assert(!pthread_join(workers[i],NULL));
 check(sequence==2000&&priv.stats_read_failures==400&&priv.stats_valid&&priv.stats_stale);
 printf("{\"reads\":2000,\"injected_failures\":400,\"threads\":4,\"failures\":0,\"kernel_lock_is_pthread_model\":true}\n");return 0;
}
''')
eth=(args.prepared/'nss_dp_ethtools.c').read_text()
start=eth.index('static const char nss_dp_stats_diag')
opening=eth.index('{',start);end=extract.block_end(eth,opening)
diagnostic=eth[start:end]+';\n#define NSS_DP_STATS_DIAG_COUNT (sizeof(nss_dp_stats_diag)/sizeof(nss_dp_stats_diag[0]))\n'
prefix=PREFIX+r'''
#define ETH_GSTRING_LEN 32
#define ETH_SS_STATS 1
#define ETH_SS_PRIV_FLAGS 2
#define NSS_DP_MAX_ETHTOOL_PRIV_FLAGS 1
static const char nss_dp_priv_flg_str[1][ETH_GSTRING_LEN]={"priv"};
struct nss_dp_gmac_stats {uint64_t value;};
struct ethtool_stats {int unused;};
struct ops {int (*getssetcount)(struct nss_gmac_hal_dev*,int32_t);
 int (*getstrings)(struct nss_gmac_hal_dev*,uint32_t,uint8_t*);
 int (*getethtoolstats)(struct nss_gmac_hal_dev*,uint64_t*,struct nss_dp_gmac_stats*);};
struct nss_dp_dev {struct ops *gmac_hal_ops;struct nss_gmac_hal_dev *gmac_hal_ctx;
 pthread_mutex_t stats_lock;uint64_t stats_read_failures;bool stats_valid,stats_stale;};
struct net_device {struct nss_dp_dev *priv;};
#define netdev_priv(n) ((n)->priv)
#define spin_lock_irqsave(l,f) do {(f)=0;assert(!pthread_mutex_lock(l));} while(0)
#define spin_unlock_irqrestore(l,f) do {(void)(f);assert(!pthread_mutex_unlock(l));} while(0)
struct plane_ops {void (*get_stats)(void*,struct nss_dp_gmac_stats*);};
struct nss_dp_plane_ref {struct plane_ops *ops;void *dpc;};
static bool nss_dp_plane_get(struct nss_dp_dev *p,struct nss_dp_plane_ref *r) {(void)p;(void)r;return false;}
static void nss_dp_plane_put(struct nss_dp_dev *p) {(void)p;}
static int count(struct nss_gmac_hal_dev *d,int32_t set) {(void)d;return set==ETH_SS_STATS?2:-5;}
static int strings(struct nss_gmac_hal_dev *d,uint32_t set,uint8_t *v) {(void)d;(void)set;memcpy(v,"HAL0",5);memcpy(v+32,"HAL1",5);return 0;}
static int raw(struct nss_gmac_hal_dev *d,uint64_t *v,struct nss_dp_gmac_stats *s) {(void)d;(void)s;v[0]=3;if(read_error)return -1;v[1]=5;return 0;}
'''
body=''.join(definition(eth,n) for n in ('nss_dp_get_ethtool_stats','nss_dp_get_strset_count','nss_dp_get_strings'))
run_extra('ethtool-quality',prefix+diagnostic+body+r'''
int main(void) {
 struct ops ops={.getssetcount=count,.getstrings=strings,.getethtoolstats=raw};
 struct nss_dp_dev priv={.gmac_hal_ops=&ops,.stats_lock=PTHREAD_MUTEX_INITIALIZER,.stats_read_failures=2,.stats_valid=true,.stats_stale=true};
 struct net_device dev={&priv};struct ethtool_stats request={0};
 struct {uint64_t values[6],canary;} data={{0},0x123456789ULL};
 struct {uint8_t values[6*32];uint64_t canary;} names={{0},0x987654321ULL};
 check(nss_dp_get_strset_count(&dev,ETH_SS_STATS)==6);
 check(nss_dp_get_strset_count(&dev,ETH_SS_PRIV_FLAGS)==1);
 check(nss_dp_get_strset_count(&dev,99)==-5);
 nss_dp_get_strings(&dev,ETH_SS_STATS,names.values);
 check(!strcmp((char*)names.values+2*32,"ndo_mib_read_failures"));
 check(!strcmp((char*)names.values+5*32,"ethtool_mib_failed")&&names.canary==0x987654321ULL);
 read_error=1;nss_dp_get_ethtool_stats(&dev,&request,data.values);
 check(data.values[0]==3&&!data.values[1]&&data.values[2]==2&&data.values[3]==1&&data.values[4]==1&&data.values[5]==1);
 check(data.canary==0x123456789ULL);
 read_error=0;nss_dp_get_ethtool_stats(&dev,&request,data.values);
 check(data.values[1]==5&&!data.values[5]&&data.canary==0x123456789ULL);
 printf("{\"checks\":%u,\"failures\":0,\"ethtool_count_strings_payload_consistent\":true}\n",checks);return 0;
}
''')
(args.output/'RESULT.json').write_text(json.dumps(dict(results=records,scope='actual mapping/cache/raw-XG functions, modeled samples and lock primitives; not kernel IRQ latency or counter-epoch qualification'),indent=2)+'\n')
print(json.dumps(records,indent=2))
