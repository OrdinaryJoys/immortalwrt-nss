/* Reduced cfg/API, OS storage and bitmap sources are explicit models. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
typedef uint64_t __a_uint64_t;
/* @TYPES@ */
/* @MACROS@ */
typedef struct {hsl_init_mode cpu_mode;ssdk_port_cfg port_cfg;a_uint32_t cookie;} ssdk_init_cfg;
typedef sw_error_t (*model_sd_token)(void);
typedef struct {
    sw_error_t (*dev_clean)(a_uint32_t);
    model_sd_token reg_get,reg_set,mii_reg_get,mii_reg_set,phy_get,phy_set,
                   phy_i2c_get,phy_i2c_set,uniphy_reg_get,uniphy_reg_set;
} hsl_api_t;
/* @GLOBALS@ */
enum {DEV,RESET,PALLOC,PROP,CLEAN,SET0,SET1,SET2,SET3,SET4,NSITES};
static const char *labels[NSITES]={"DEV","RESET","PALLOC","PROP","CLEAN","SET0","SET1","SET2","SET3","SET4"};
struct input {const char *name,*flow;a_uint32_t dev,cpu,lan,wan,inner,global_bmp,global_inner;
              int synth,first,second,oom_kind,oom_mode,borrow,attempts,clean;};
/* @CASES@ */
static const struct input *in;
static int old_mode,counts[NSITES],alloc_calls[3];
static char trace[80000];static size_t used;
static void fail(const char *s) {fprintf(stderr,"SSDK_HPPE %s\n",s);exit(86);}
#define CHECK(c,s) do {if(!(c))fail(s);} while(0)
static void event(const char *fmt,...) __attribute__((format(printf,1,2)));
static void event(const char *fmt,...)
{
    va_list ap;va_start(ap,fmt);int n=vsnprintf(trace+used,sizeof(trace)-used,fmt,ap);va_end(ap);
    CHECK(n>=0 && (size_t)n<sizeof(trace)-used,"TRACE_CAPACITY");used+=(size_t)n;
}
struct block {void *ptr,*snapshot;size_t bytes;int id,kind,live,foreign;};
static struct block blocks[32];static int nb,serial;
static struct block *owner(void *p,int kind)
{
    for(int i=0;i<nb;i++)if(blocks[i].ptr==p && p) {
        CHECK(blocks[i].live && blocks[i].kind==kind && blocks[i].bytes==(kind==1?sizeof(ssdk_init_cfg):sizeof(port_info_t)),"OWNER_BEFORE_DEREF");return &blocks[i];
    }
    fail("OWNER_IDENTITY");return NULL;
}
static int id(void *p,int kind) {return p?owner(p,kind)->id:0;}
static void *aos_mem_alloc(size_t bytes)
{
    int kind=bytes==sizeof(ssdk_init_cfg)?1:bytes==sizeof(port_info_t)?2:0;
    CHECK(kind!=0 && sizeof(ssdk_init_cfg)!=sizeof(port_info_t),"MODEL_ALLOC_SHAPE");
    int n=++alloc_calls[kind],ok=!(in->oom_kind==kind && (in->oom_mode==2 || n==1));
    int ident=++serial;event("ALLOC %d %d %zu %d\n",ident,kind,bytes,ok);
    if(!ok)return NULL;
    void *p=calloc(1,bytes);CHECK(p!=NULL && nb<32,"HOST_ALLOC");
    blocks[nb++]=(struct block){p,NULL,bytes,ident,kind,1,0};return p;
}
static void aos_mem_free(void *p)
{
    if(!p)return;
    for(int i=0;i<nb;i++)if(blocks[i].ptr==p) {
        CHECK(blocks[i].live && !blocks[i].foreign,"FREE_LIVE_OWNED_ONLY");blocks[i].live=0;event("FREE %d\n",blocks[i].id);return;
    }
    fail("FREE_IDENTITY");
}
static void aos_mem_zero(void *p,size_t bytes)
{
    struct block *b=owner(p,2);CHECK(!b->foreign && bytes==b->bytes,"ZERO_EXTENT");
    memset(p,0,bytes);event("ZERO %d %zu\n",b->id,bytes);
}
static void aos_mem_copy(void *p,const void *src,size_t bytes)
{
    struct block *b=owner(p,1);CHECK(bytes==b->bytes,"COPY_EXTENT");
    memcpy(p,src,bytes);event("COPY %d %zu\n",b->id,bytes);
}
static a_uint32_t qca_ssdk_port_bmp_get(a_uint32_t d)
{CHECK(d<SW_MAX_NR_DEV,"BMP_DEV");event("GLOBAL_BMP %u\n",in->global_bmp);return in->global_bmp;}
static a_uint32_t hsl_dev_inner_ports_get(a_uint32_t d)
{CHECK(d<SW_MAX_NR_DEV,"INNER_DEV");event("GLOBAL_INNER %u\n",in->global_inner);return in->global_inner;}
#define SD(name) static sw_error_t name(void) {return SW_OK;}
SD(sd_reg_hdr_get) SD(sd_reg_hdr_set) SD(sd_reg_mii_mdio_get) SD(sd_reg_mii_mdio_set)
SD(sd_reg_mdio_get) SD(sd_reg_mdio_set) SD(sd_reg_i2c_get) SD(sd_reg_i2c_set)
SD(sd_reg_uniphy_get) SD(sd_reg_uniphy_set) SD(foreign_sd)
static sw_error_t foreign_clean(a_uint32_t d) {(void)d;return SW_OK;}
static sw_error_t hsl_port_prop_set(a_uint32_t,fal_port_t,hsl_port_prop_t);
static sw_error_t hsl_port_prop_portmap_set(a_uint32_t,fal_port_t);
static sw_error_t hsl_port_prop_init(a_uint32_t);
static sw_error_t hsl_port_prop_init_by_dev(a_uint32_t);
static sw_error_t hsl_port_prop_cleanup_by_dev(a_uint32_t);
static sw_error_t hppe_dev_init(a_uint32_t,ssdk_init_cfg*);
static sw_error_t hppe_portproperty_init(a_uint32_t);
/* @HELPERS@ */
static int enter(int site,a_uint32_t d,unsigned p,unsigned type)
{
    CHECK(site>=0 && site<NSITES,"SITE_DOMAIN");int call=++counts[site];
    event("CALL %s %u %u %u %d\n",labels[site],d,p,type,call);
    if(in->synth==site) {int ret=call==1?in->first:in->second;if(ret)event("SYNTH %s %d\n",labels[site],ret);return ret;}
    return 0;
}
static sw_error_t done(int site,sw_error_t ret) {event("DONE %s %d\n",labels[site],ret);return ret;}
static sw_error_t hppe_dev_init(a_uint32_t d,ssdk_init_cfg *cfg)
{int e=enter(DEV,d,0,0);return done(DEV,e?e:real_dev(d,cfg));}
static sw_error_t hsl_port_prop_init(a_uint32_t d)
{int e=enter(RESET,d,0,0);return done(RESET,e?e:real_reset(d));}
static sw_error_t hsl_port_prop_init_by_dev(a_uint32_t d)
{int e=enter(PALLOC,d,0,0);return done(PALLOC,e?e:real_palloc(d));}
static sw_error_t hppe_portproperty_init(a_uint32_t d)
{int e=enter(PROP,d,0,0);return done(PROP,e?e:old_mode?real_old_prop(d):real_prop(d));}
static sw_error_t hsl_port_prop_cleanup_by_dev(a_uint32_t d)
{int e=enter(CLEAN,d,0,0);return done(CLEAN,e?e:real_clean(d));}
static sw_error_t hsl_port_prop_portmap_set(a_uint32_t d,fal_port_t p)
{
    CHECK(d<SW_MAX_NR_DEV && p<SW_MAX_NR_PORT,"MAP_SAFE_DOMAIN");owner(p_port_info[d],2);
    event("MAP %u %u\n",d,p);return real_map(d,p);
}
static sw_error_t hsl_port_prop_set(a_uint32_t d,fal_port_t p,hsl_port_prop_t t)
{
    CHECK(d<SW_MAX_NR_DEV && p<SW_MAX_NR_PORT && t>=0 && t<HSL_PP_BUTT,"SET_SAFE_DOMAIN");owner(p_port_info[d],2);
    int site=SET0+(int)t,e=enter(site,d,p,(unsigned)t);return done(site,e?e:real_set(d,p,t));
}
/* @ENTRY@ */
static hsl_dev_t peer_dev[SW_MAX_NR_DEV];static hsl_api_t peer_api[SW_MAX_NR_DEV];
static ssdk_init_cfg *peer_cfg[SW_MAX_NR_DEV];static port_info_t *peer_port[SW_MAX_NR_DEV];
static void seed(unsigned d,int mask)
{
    if(mask&1) {
        ssdk_init_cfg *p=calloc(1,sizeof(*p));CHECK(p!=NULL,"HOST_SEED");p->cookie=0xbadc0de;
        hppe_cfg[d]=p;blocks[nb++]=(struct block){p,NULL,sizeof(*p),101+(int)d*10,1,1,1};
    }
    if(mask&2) {
        port_info_t *p=calloc(1,sizeof(*p));CHECK(p!=NULL,"HOST_SEED");p->dev_portmap=0x88;
        for(unsigned i=0;i<SW_MAX_NR_PORT;i++)p->phy_id[i]=1000+i;
        for(unsigned i=0;i<HSL_PP_BUTT;i++)p->property[i]=1u<<i;
        p_port_info[d]=p;blocks[nb++]=(struct block){p,NULL,sizeof(*p),102+(int)d*10,2,1,1};
    }
}
static void peer_check(void)
{
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)if(d!=in->dev)CHECK(!memcmp(&dev_table[d],&peer_dev[d],sizeof(hsl_dev_t)) &&
        !memcmp(&hsl_api_table[d],&peer_api[d],sizeof(hsl_api_t)) && hppe_cfg[d]==peer_cfg[d] && p_port_info[d]==peer_port[d],"PEER_IDENTITY_STATE");
    for(int i=0;i<nb;i++)if(blocks[i].foreign && !(in->dev<SW_MAX_NR_DEV && blocks[i].kind==1 && blocks[i].id==101+(int)in->dev*10))
        CHECK(blocks[i].live && !memcmp(blocks[i].ptr,blocks[i].snapshot,blocks[i].bytes),"FOREIGN_UNRELATED_BYTES");
}
static void dump(void)
{
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++) {
        hsl_dev_t *v=&dev_table[d];event("DEVSTATE %u %u %u %u %u %u %u %d %d %u\n",d,v->dev_id,v->cpu_port_nr,v->nr_ports,v->nr_phy,v->nr_queue,v->nr_vlans,v->hw_vlan_query,v->cpu_mode,v->wan_bmp);
        int c=id(hppe_cfg[d],1),p=id(p_port_info[d],2);event("SLOTS %u %d %d\n",d,c,p);
        if(c) {ssdk_init_cfg *v=hppe_cfg[d];event("CFG %u %d %u %u %u %u %u\n",d,v->cpu_mode,v->port_cfg.cpu_bmp,v->port_cfg.lan_bmp,v->port_cfg.wan_bmp,v->port_cfg.inner_bmp,v->cookie);}
        if(p) {port_info_t *v=p_port_info[d];event("PORT %u %u",d,v->dev_portmap);
            for(unsigned i=0;i<HSL_PP_BUTT;i++)event(" %u",v->property[i]);
            for(unsigned i=0;i<SW_MAX_NR_PORT;i++)event(" %u",v->phy_id[i]);
            event("\n");}
        if(d==in->dev) {
            hsl_api_t *a=&hsl_api_table[d];sw_error_t (*clean)(a_uint32_t)=old_mode?old_hppe_cleanup:hppe_cleanup;
            CHECK(!a->dev_clean || a->dev_clean==clean,"API_CALLBACK_IDENTITY");event("API %u %d",d,a->dev_clean!=NULL);
#define TOKEN(field,fn) CHECK(!a->field || a->field==fn,"API_FIELD_IDENTITY");event(" %d",a->field!=NULL)
            TOKEN(reg_get,sd_reg_hdr_get);TOKEN(reg_set,sd_reg_hdr_set);TOKEN(mii_reg_get,sd_reg_mii_mdio_get);TOKEN(mii_reg_set,sd_reg_mii_mdio_set);
            TOKEN(phy_get,sd_reg_mdio_get);TOKEN(phy_set,sd_reg_mdio_set);TOKEN(phy_i2c_get,sd_reg_i2c_get);TOKEN(phy_i2c_set,sd_reg_i2c_set);
            TOKEN(uniphy_reg_get,sd_reg_uniphy_get);TOKEN(uniphy_reg_set,sd_reg_uniphy_set);event("\n");
#undef TOKEN
        }
    }
    for(int i=0;i<nb;i++) {
        int reachable=0;
        for(unsigned d=0;d<SW_MAX_NR_DEV;d++)if(blocks[i].ptr==(void*)hppe_cfg[d] || blocks[i].ptr==(void*)p_port_info[d])reachable=1;
        event(blocks[i].foreign?"FOREIGN %d %d %d %d\n":"OWNER %d %d %d %d\n",blocks[i].id,blocks[i].kind,blocks[i].live,reachable);
    }
    event("OPEN_FOREIGN_CFG_COPY_AND_DISPLACED_PORTS\n");
}
static int csv(const char *s,int *out,int limit)
{
    int n=0;char *end;
    while(*s) {CHECK(n<limit,"CSV_EXTENT");long v=strtol(s,&end,10);CHECK(end>s && v>=-100000 && v<=100000,"CSV_VALUE");out[n++]=(int)v;
        if(!*end)break;
        CHECK(*end==',',"CSV_SEPARATOR");s=end+1;}
    return n;
}
static void returned(sw_error_t ret,int *expected,int *next,int nr)
{CHECK(*next<nr && ret==expected[(*next)++],"FIRST_RETURN");event("RETURN %d\n",ret);}
int main(int argc,char **argv)
{
    CHECK(argc==6,"ARGUMENTS");int index=atoi(argv[1]);CHECK(index>=0 && (size_t)index<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");in=&inputs[index];old_mode=atoi(argv[5]);
    int expected[4],nr=csv(argv[2],expected,4),next=0,expect_calls[NSITES];CHECK(csv(argv[3],expect_calls,NSITES)==NSITES,"COUNTS_EXTENT");
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++) {
        seed(d,d==in->dev?in->borrow:3);dev_table[d].dev_id=d;dev_table[d].cpu_port_nr=7;
        dev_table[d].nr_ports=9;dev_table[d].nr_phy=11;dev_table[d].nr_queue=13;dev_table[d].nr_vlans=17;dev_table[d].wan_bmp=0x44;
        if(d!=in->dev) {hsl_api_table[d].dev_clean=foreign_clean;
#define PEER_TOKEN(field) hsl_api_table[d].field=foreign_sd
            PEER_TOKEN(reg_get);PEER_TOKEN(reg_set);PEER_TOKEN(mii_reg_get);PEER_TOKEN(mii_reg_set);PEER_TOKEN(phy_get);PEER_TOKEN(phy_set);
            PEER_TOKEN(phy_i2c_get);PEER_TOKEN(phy_i2c_set);PEER_TOKEN(uniphy_reg_get);PEER_TOKEN(uniphy_reg_set);
#undef PEER_TOKEN
        }
    }
    memcpy(peer_dev,dev_table,sizeof(dev_table));memcpy(peer_api,hsl_api_table,sizeof(hsl_api_table));memcpy(peer_cfg,hppe_cfg,sizeof(hppe_cfg));memcpy(peer_port,p_port_info,sizeof(p_port_info));
    for(int i=0;i<nb;i++) {blocks[i].snapshot=malloc(blocks[i].bytes);CHECK(blocks[i].snapshot!=NULL,"HOST_SNAPSHOT");memcpy(blocks[i].snapshot,blocks[i].ptr,blocks[i].bytes);}
    ssdk_init_cfg cfg={0};cfg.cpu_mode=(hsl_init_mode)1;cfg.port_cfg.cpu_bmp=in->cpu;cfg.port_cfg.lan_bmp=in->lan;
    cfg.port_cfg.wan_bmp=in->wan;cfg.port_cfg.inner_bmp=in->inner;cfg.cookie=0xc0ffee;
    sw_error_t ret=SW_OK;
    for(int attempt=0;attempt<in->attempts;attempt++) {
        event("ATTEMPT %d\n",attempt);
        if(!strcmp(in->flow,"helpers")) {
            ret=hppe_dev_init(in->dev,&cfg);
            if(!ret)ret=hsl_port_prop_init(in->dev);
            if(!ret)ret=hsl_port_prop_init_by_dev(in->dev);
            if(!ret)ret=hppe_portproperty_init(in->dev);
        } else ret=old_mode?old_hppe_init(in->dev,&cfg):hppe_init(in->dev,&cfg);
        returned(ret,expected,&next,nr);peer_check();
    }
    if(in->clean && !ret) {
        CHECK(in->dev<SW_MAX_NR_DEV && !in->borrow,"CLEANUP_VALID_FRESH_ONLY");
        if(in->clean==1) {
            if(hsl_api_table[in->dev].dev_clean) {event("CALLBACK\n");ret=hsl_api_table[in->dev].dev_clean(in->dev);returned(ret,expected,&next,nr);}
            else event("CALLBACK_ABSENT_OPEN_CFG\n");
        } else {
            event(in->clean==3?"DIRECT_PORT_HELPER\n":"DIRECT_HPPE_HELPER\n");
            ret=in->clean==3?hsl_port_prop_cleanup_by_dev(in->dev):old_mode?old_hppe_cleanup(in->dev):hppe_cleanup(in->dev);
            returned(ret,expected,&next,nr);
        }
    }
    CHECK(next==nr,"RETURN_COUNT");
    for(int i=0;i<NSITES;i++)CHECK(counts[i]==expect_calls[i],"SINGLE_EVALUATION");
    peer_check();dump();event("END MODEL_ONLY_NO_FAILURE_UNWIND\n");
    FILE *f=fopen(argv[4],"rb");CHECK(f!=NULL,"EXPECTED_OPEN");char expected_bytes[sizeof(trace)];size_t n=fread(expected_bytes,1,sizeof(expected_bytes),f);
    CHECK(!ferror(f) && feof(f) && fclose(f)==0,"EXPECTED_EXTENT");CHECK(n==used && !memcmp(expected_bytes,trace,n),"EXACT_MODEL_TRACE");
    CHECK(fwrite(trace,1,n,stdout)==n,"STDOUT");
    /* Fixture storage release does not change the reported driver owner ledger. */
    for(int i=0;i<nb;i++) {free(blocks[i].snapshot);free(blocks[i].ptr);}return 0;
}
