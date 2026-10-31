/* Explicit reduced cfg/API and serial OS model, not kernel ABI or reader lifetime. */
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
typedef sw_error_t (*sd_token)(void);
typedef struct {sw_error_t (*dev_clean)(a_uint32_t);sd_token reg_get,reg_set,mii_reg_get,mii_reg_set,
    phy_get,phy_set,phy_i2c_get,phy_i2c_set,uniphy_reg_get,uniphy_reg_set;} hsl_api_t;
/* @GLOBALS@ */
/* Actual installed public owner declarations, compiled against complete definitions. */
/* @DECLARATIONS@ */
sw_error_t hppe_init(a_uint32_t,ssdk_init_cfg*);
sw_error_t hppe_cleanup(a_uint32_t);
static sw_error_t old_hppe_portproperty_init(a_uint32_t);
sw_error_t old_hppe_init(a_uint32_t,ssdk_init_cfg*);
sw_error_t old_hppe_cleanup(a_uint32_t);
struct input {const char *name,*flow;unsigned dev,cpu,lan,wan,inner,bmp,ibmp;
    int borrow,hook,oom_kind,oom_mode,synth,conflict,nested,attempts,clean,mismatch,nullcfg,tokenold;};
/* @CASES@ */
static const struct input *in;
static int old_mode,serial,nb,alloc_calls[3],map_calls,set_calls,publish_calls,nesting;
static char trace[100000];static size_t used;
static void fail(const char *s) {fprintf(stderr,"HPPE_OWNER %s\n",s);exit(86);}
#define CHECK(c,s) do {if(!(c))fail(s);} while(0)
static void event(const char *fmt,...) __attribute__((format(printf,1,2)));
static void event(const char *fmt,...)
{va_list ap;va_start(ap,fmt);int n=vsnprintf(trace+used,sizeof(trace)-used,fmt,ap);va_end(ap);
 CHECK(n>=0 && (size_t)n<sizeof(trace)-used,"TRACE_CAPACITY");used+=(size_t)n;}
struct block {void *ptr,*snapshot;size_t size;int id,kind,live,foreign;};
static struct block blocks[48];
static struct block *block(void *p,int kind)
{
    for(int i=0;i<nb;i++)if(p && blocks[i].ptr==p) {
        CHECK(blocks[i].live && blocks[i].kind==kind &&
              blocks[i].size==(kind==1?sizeof(ssdk_init_cfg):sizeof(port_info_t)),"OWNER_BEFORE_DEREF");
        return &blocks[i];
    }
    fail("OWNER_IDENTITY");return NULL;
}
static int ident(void *p,int kind) {return p?block(p,kind)->id:0;}
static void *seed_block(unsigned d,int kind,int tag)
{
    size_t n=kind==1?sizeof(ssdk_init_cfg):sizeof(port_info_t);void *p=calloc(1,n);
    CHECK(p!=NULL && nb<48,"HOST_SEED");
    blocks[nb++]=(struct block){p,NULL,n,tag,kind,1,1};
    if(kind==1)((ssdk_init_cfg*)p)->cookie=0xbadc0de;
    else {port_info_t *v=p;v->dev_portmap=0x88;
        for(unsigned i=0;i<16;i++)v->phy_id[i]=1000+i+d;
        for(unsigned i=0;i<5;i++)v->property[i]=1u<<i;}
    blocks[nb-1].snapshot=malloc(n);CHECK(blocks[nb-1].snapshot!=NULL,"HOST_SEED_SNAPSHOT");
    memcpy(blocks[nb-1].snapshot,p,n);return p;
}
static void *aos_mem_alloc(size_t n)
{
    int k=n==sizeof(ssdk_init_cfg)?1:n==sizeof(port_info_t)?2:0;
    CHECK(k && sizeof(ssdk_init_cfg)!=sizeof(port_info_t),"ALLOC_SHAPE");
    if(in->nested && !nesting && k==1) {
        nesting=1;ssdk_init_cfg cfg={0};cfg.port_cfg.cpu_bmp=1;
        sw_error_t a=hppe_init(in->dev,&cfg),b=hppe_cleanup(in->dev);
        sw_error_t c=hppe_init((in->dev+1)%3,&cfg);
        CHECK(a==SW_BUSY && b==SW_BUSY && c==SW_ALREADY_EXIST,"NESTED_BUSY_DOMAIN");
        event("NESTED %d %d %d\n",a,b,c);nesting=0;
    }
    int call=++alloc_calls[k],ok=!(in->oom_kind==k && (in->oom_mode==2 || call==1));
    int id=++serial;event("ALLOC %d %d %zu %d\n",id,k,n,ok);if(!ok)return NULL;
    void *p=calloc(1,n);CHECK(p!=NULL && nb<48,"HOST_ALLOC");
    blocks[nb++]=(struct block){p,NULL,n,id,k,1,0};return p;
}
static void aos_mem_free(void *p)
{
    if(!p)return;
    for(int i=0;i<nb;i++)if(blocks[i].ptr==p) {
        CHECK(blocks[i].live && !blocks[i].foreign,"ONLY_OWNED_FREE");
        blocks[i].live=0;event("FREE %d\n",blocks[i].id);return;
    }
    fail("FREE_IDENTITY");
}
static void aos_mem_copy(void *p,const void *s,size_t n)
{struct block *b=block(p,1);CHECK(!b->foreign && n==b->size,"OWNED_COPY");memcpy(p,s,n);event("COPY %d %zu\n",b->id,n);}
static void aos_mem_zero(void *p,size_t n)
{struct block *b=block(p,2);CHECK(!b->foreign && n==b->size,"OWNED_ZERO");memset(p,0,n);event("ZERO %d %zu\n",b->id,n);}
static a_uint32_t qca_ssdk_port_bmp_get(a_uint32_t d)
{CHECK(d<3,"BMP_ID");event("BMP %u\n",in->bmp);return in->bmp;}
static a_uint32_t hsl_dev_inner_ports_get(a_uint32_t d)
{CHECK(d<3,"INNER_ID");event("INNER %u\n",in->ibmp);return in->ibmp;}
#define SD(n) static sw_error_t n(void) {return SW_OK;}
SD(sd_reg_hdr_get) SD(sd_reg_hdr_set) SD(sd_reg_mii_mdio_get) SD(sd_reg_mii_mdio_set)
SD(sd_reg_mdio_get) SD(sd_reg_mdio_set) SD(sd_reg_i2c_get) SD(sd_reg_i2c_set)
SD(sd_reg_uniphy_get) SD(sd_reg_uniphy_set) SD(foreign_sd)
static sw_error_t foreign_clean(a_uint32_t d) {(void)d;return SW_OK;}
/* @HELPERS@ */
static void private_check(hsl_port_prop_owner_t *p)
{
    struct block *v=block(p,2);CHECK(!v->foreign,"PRIVATE_OWNED");
    if(!strcmp(in->flow,"root")) {
        CHECK(in->dev<3 && !hppe_cfg[in->dev] && !hppe_port_owner[in->dev] && !p_port_info[in->dev],"PRIVATE_BEFORE_PUBLICATION");
    }
}
sw_error_t hsl_port_prop_build_portmap_set(hsl_port_prop_owner_t *p,fal_port_t port)
{
    if(p)private_check(p);
    int call=++map_calls;
    sw_error_t r=(in->synth==1 && call==1)?SW_READ_ERROR:real_map(p,port);
    event("MAP %d %u %d\n",ident(p,2),port,r);return r;
}
sw_error_t hsl_port_prop_build_set(hsl_port_prop_owner_t *p,fal_port_t port,hsl_port_prop_t type)
{
    if(p)private_check(p);
    int call=++set_calls;
    sw_error_t r=(in->synth==2 && call==1)?SW_READ_ERROR:real_set(p,port,type);
    event("SET %d %u %d %d\n",ident(p,2),port,(int)type,r);return r;
}
sw_error_t hsl_port_prop_build_publish(a_uint32_t d,hsl_port_prop_owner_t **p)
{
    int before=p?ident(*p,2):0;int call=++publish_calls;
    if(in->conflict && call==1) {CHECK(d<3 && !p_port_info[d],"CONFLICT_EMPTY");p_port_info[d]=seed_block(d,2,900);event("CONFLICT %u 900\n",d);}
    sw_error_t r=(in->synth==3 && call==1)?SW_READ_ERROR:real_publish(d,p);
    event("PUBLISH %u %d %d %d\n",d,before,p?ident(*p,2):0,r);return r;
}
sw_error_t hsl_port_prop_cleanup_owned(a_uint32_t d,hsl_port_prop_owner_t *p)
{int before=ident(p,2);sw_error_t r=real_owned(d,p);event("OWNED_CLEAN %u %d %d\n",d,before,r);return r;}
/* @ENTRY@ */
static hsl_dev_t initial_dev[3];static hsl_api_t initial_api[3];
static ssdk_init_cfg *initial_cfg[3];static port_info_t *initial_port[3];
static void foreign_check(void)
{
    for(int i=0;i<nb;i++)if(blocks[i].foreign)CHECK(blocks[i].live &&
        !memcmp(blocks[i].ptr,blocks[i].snapshot,blocks[i].size),"FOREIGN_BYTES");
    for(unsigned d=0;d<3;d++)if(d!=in->dev)CHECK(!memcmp(&dev_table[d],&initial_dev[d],sizeof(hsl_dev_t)) &&
        !memcmp(&hsl_api_table[d],&initial_api[d],sizeof(hsl_api_t)) &&
        hppe_cfg[d]==initial_cfg[d] && p_port_info[d]==initial_port[d] && !hppe_port_owner[d] && !hppe_initializing[d],"PEER_STATE");
}
static int clean_id(sw_error_t (*p)(a_uint32_t))
{if(!p)return 0;if(p==hppe_cleanup || p==old_hppe_cleanup)return 1;CHECK(p==foreign_clean,"CALLBACK_IDENTITY");return 2;}
static int sd_id(sd_token p,sd_token expected)
{if(!p)return 0;if(p==expected)return 1;CHECK(p==foreign_sd,"API_IDENTITY");return 2;}
static void dump(void)
{
    foreign_check();
    for(unsigned d=0;d<3;d++) {
        hsl_dev_t *v=&dev_table[d];
        event("META %u %u %u %u %u %u %u %d %d %u\n",d,v->dev_id,v->cpu_port_nr,v->nr_ports,v->nr_phy,v->nr_queue,v->nr_vlans,v->hw_vlan_query,v->cpu_mode,v->wan_bmp);
        int c=ident(hppe_cfg[d],1),p=ident(p_port_info[d],2),t=ident(hppe_port_owner[d],2);
        event("SLOTS %u %d %d %d %d\n",d,c,p,t,hppe_initializing[d]);
        if(c) {ssdk_init_cfg *x=hppe_cfg[d];event("CFG %u %d %u %u %u %u %u\n",d,x->cpu_mode,x->port_cfg.cpu_bmp,x->port_cfg.lan_bmp,x->port_cfg.wan_bmp,x->port_cfg.inner_bmp,x->cookie);}
        if(p) {port_info_t *x=p_port_info[d];event("PORT %u %u",d,x->dev_portmap);
            for(unsigned i=0;i<5;i++)event(" %u",x->property[i]);
            for(unsigned i=0;i<16;i++)event(" %u",x->phy_id[i]);
            event("\n");}
        hsl_api_t *a=&hsl_api_table[d];event("API %u %d",d,clean_id(a->dev_clean));
#define TOKEN(f,n) event(" %d",sd_id(a->f,n))
        TOKEN(reg_get,sd_reg_hdr_get);TOKEN(reg_set,sd_reg_hdr_set);TOKEN(mii_reg_get,sd_reg_mii_mdio_get);TOKEN(mii_reg_set,sd_reg_mii_mdio_set);
        TOKEN(phy_get,sd_reg_mdio_get);TOKEN(phy_set,sd_reg_mdio_set);TOKEN(phy_i2c_get,sd_reg_i2c_get);TOKEN(phy_i2c_set,sd_reg_i2c_set);
        TOKEN(uniphy_reg_get,sd_reg_uniphy_get);TOKEN(uniphy_reg_set,sd_reg_uniphy_set);event("\n");
#undef TOKEN
    }
    for(int i=0;i<nb;i++) {
        int reach=0;for(unsigned d=0;d<3;d++)if(blocks[i].ptr==(void*)hppe_cfg[d] || blocks[i].ptr==(void*)p_port_info[d] || blocks[i].ptr==(void*)hppe_port_owner[d])reach=1;
        event("OWNER %d %d %d %d %d\n",blocks[i].id,blocks[i].kind,blocks[i].live,blocks[i].foreign,reach);
    }
}
static int returns[128],nr,next;
static void returned(sw_error_t r)
{CHECK(next<nr && r==returns[next++],"FIRST_ERROR");event("RET %d\n",r);}
static void builder_payload(hsl_port_prop_owner_t *p,hsl_port_prop_owner_t *local,unsigned stage)
{
    CHECK(stage<13 && in->dev<3,"BUILDER_STAGE");
    struct block *b=block(p,2);int published=stage==12;
    CHECK(b->id==1 && !b->foreign && !hppe_cfg[in->dev] && !hppe_port_owner[in->dev] &&
          !hppe_initializing[in->dev] && (published ? (!local && p_port_info[in->dev]==p) :
          (local==p && !p_port_info[in->dev])),"BUILDER_IDENTITY");
    const a_uint32_t *expected=builder_expected[stage];
    const char *marker=published?"BUILDER_PUBLISHED_PAYLOAD":"BUILDER_PRIVATE_PAYLOAD";
    CHECK(p->dev_portmap==expected[0],marker);
    for(unsigned t=0;t<5;t++)CHECK(p->property[t]==expected[1+t],marker);
    for(unsigned i=0;i<16;i++)CHECK(p->phy_id[i]==expected[6+i],marker);
    event("BUILDER_PAYLOAD %u %u %d %d %d %u",stage,in->dev,b->id,ident(local,2),ident(p_port_info[in->dev],2),p->dev_portmap);
    for(unsigned t=0;t<5;t++)event(" %u",p->property[t]);
    for(unsigned i=0;i<16;i++)event(" %u",p->phy_id[i]);
    event("\n");
}
static void builders(void)
{
    unsigned d=in->dev;hsl_port_prop_owner_t *p=NULL,*token;
    returned(hsl_port_prop_slot_available(d));returned(hsl_port_prop_build_alloc(d,NULL));
    returned(hsl_port_prop_build_alloc(3,&p));returned(hsl_port_prop_build_alloc(d,&p));
    returned(hsl_port_prop_build_alloc(d,&p));
    returned(hsl_port_prop_build_portmap_set(NULL,0));returned(hsl_port_prop_build_portmap_set(p,16));
    returned(hsl_port_prop_build_portmap_set(p,UINT32_MAX));returned(hsl_port_prop_build_portmap_set(p,15));
    builder_payload(p,p,0);
    returned(hsl_port_prop_build_set(NULL,0,HSL_PP_PHY));returned(hsl_port_prop_build_set(p,16,HSL_PP_PHY));
    returned(hsl_port_prop_build_set(p,15,(hsl_port_prop_t)-1));returned(hsl_port_prop_build_set(p,15,HSL_PP_BUTT));
    returned(hsl_port_prop_build_set(p,0,HSL_PP_PHY));
    for(int t=0;t<5;t++) {returned(hsl_port_prop_build_set(p,15,(hsl_port_prop_t)t));builder_payload(p,p,1+(unsigned)t);}
    /* Distinct row prefixes retain wrong-row evidence even after all five setters. */
    for(int t=0;t<5;t++) {
        returned(hsl_port_prop_build_portmap_set(p,(fal_port_t)t));
        returned(hsl_port_prop_build_set(p,(fal_port_t)t,(hsl_port_prop_t)t));
        builder_payload(p,p,6+(unsigned)t);
    }
    builder_payload(p,p,11);
    returned(hsl_port_prop_build_publish(d,NULL));hsl_port_prop_owner_t *empty=NULL;
    returned(hsl_port_prop_build_publish(d,&empty));returned(hsl_port_prop_build_publish(3,&p));
    p_port_info[d]=seed_block(d,2,900);returned(hsl_port_prop_build_alloc(d,&empty));CHECK(!empty,"FAILED_ALLOC_OUTPUT");
    returned(hsl_port_prop_build_publish(d,&p));
    p_port_info[d]=NULL;token=p;returned(hsl_port_prop_build_publish(d,&p));CHECK(!p,"PUBLISH_CONSUME");
    builder_payload(token,p,12);
    hsl_port_prop_build_abort(&p);hsl_port_prop_build_abort(NULL);
    returned(hsl_port_prop_cleanup_owned(3,token));returned(hsl_port_prop_cleanup_owned(d,NULL));
    returned(hsl_port_prop_cleanup_owned(d,token));returned(hsl_port_prop_slot_available(d));
    returned(hsl_port_prop_build_alloc(d,&p));hsl_port_prop_build_abort(&p);CHECK(!p,"ABORT_CONSUME");hsl_port_prop_build_abort(&p);
    dump();
}
int main(int argc,char **argv)
{
    CHECK(argc==5,"ARGS");unsigned ix=(unsigned)strtoul(argv[1],NULL,10);CHECK(ix<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");in=&inputs[ix];old_mode=atoi(argv[4]);
    const char *s=argv[2];char *end;while(*s) {CHECK(nr<128,"RETURN_EXTENT");long r=strtol(s,&end,10);CHECK(end>s,"RETURN_CSV");returns[nr++]=(int)r;if(!*end)break;CHECK(*end==',',"RETURN_CSV");s=end+1;}
    for(unsigned d=0;d<3;d++) {
        int mask=d==in->dev?in->borrow:3;
        if(mask&1)hppe_cfg[d]=seed_block(d,1,101+(int)d*10);
        if(mask&2)p_port_info[d]=seed_block(d,2,102+(int)d*10);
        dev_table[d]=(hsl_dev_t){.dev_id=d,.cpu_port_nr=7,.nr_ports=9,.nr_phy=11,.nr_queue=13,.nr_vlans=17,.wan_bmp=0x44};
        int hook=d==in->dev?in->hook:2;hsl_api_t *a=&hsl_api_table[d];a->dev_clean=hook==2?foreign_clean:hook==1?(old_mode?old_hppe_cleanup:hppe_cleanup):NULL;
#define SEED(f) a->f=foreign_sd
        SEED(reg_get);SEED(reg_set);SEED(mii_reg_get);SEED(mii_reg_set);SEED(phy_get);SEED(phy_set);
        SEED(phy_i2c_get);SEED(phy_i2c_set);SEED(uniphy_reg_get);SEED(uniphy_reg_set);
#undef SEED
    }
    if(in->tokenold && in->dev<3)hppe_port_owner[in->dev]=p_port_info[in->dev]?p_port_info[in->dev]:seed_block(in->dev,2,800);
    memcpy(initial_dev,dev_table,sizeof(dev_table));memcpy(initial_api,hsl_api_table,sizeof(hsl_api_table));
    memcpy(initial_cfg,hppe_cfg,sizeof(hppe_cfg));memcpy(initial_port,p_port_info,sizeof(p_port_info));
    ssdk_init_cfg cfg={0};cfg.cpu_mode=(hsl_init_mode)1;cfg.port_cfg=(ssdk_port_cfg){.cpu_bmp=in->cpu,.lan_bmp=in->lan,.wan_bmp=in->wan,.inner_bmp=in->inner};cfg.cookie=0xc0ffee;
    if(!strcmp(in->flow,"builders"))builders();
    else if(!strcmp(in->flow,"legacy")) {
        returned(hsl_port_prop_init(in->dev));returned(hsl_port_prop_init_by_dev(in->dev));
        returned(hsl_port_prop_portmap_set(in->dev,15));returned(hsl_port_prop_set(in->dev,15,HSL_PP_INNER));dump();
        returned(hsl_port_prop_cleanup_by_dev(in->dev));dump();
    } else {
        sw_error_t r=SW_OK;
        for(int attempt=0;attempt<in->attempts;attempt++) {
            event("ATTEMPT %d\n",attempt);r=old_mode?old_hppe_init(in->dev,in->nullcfg?NULL:&cfg):hppe_init(in->dev,in->nullcfg?NULL:&cfg);
            returned(r);dump();
            if(!r && in->clean) {
                if(in->mismatch && hppe_port_owner[in->dev]) {p_port_info[in->dev]=seed_block(in->dev,2,900);event("DISPLACE 900\n");}
                if(in->clean==1) {
                    if(hsl_api_table[in->dev].dev_clean) {event("CALLBACK\n");r=hsl_api_table[in->dev].dev_clean(in->dev);returned(r);}
                    else event("CALLBACK_ABSENT_OPEN\n");
                } else {event("DIRECT_CLEAN\n");r=old_mode?old_hppe_cleanup(in->dev):hppe_cleanup(in->dev);returned(r);}
                dump();
                if(!r && in->clean==2) {event("IDEMPOTENT_CLEAN\n");returned(old_mode?old_hppe_cleanup(in->dev):hppe_cleanup(in->dev));dump();}
            }
        }
        if(in->dev>=3) {event("INVALID_CLEAN\n");returned(hppe_cleanup(in->dev));}
    }
    CHECK(next==nr,"RETURN_COUNT");event("END SERIAL_HOST_ONLY\n");
    FILE *f=fopen(argv[3],"rb");CHECK(f!=NULL,"EXPECTED_OPEN");char exp[sizeof(trace)];size_t n=fread(exp,1,sizeof(exp),f);
    CHECK(!ferror(f) && feof(f) && fclose(f)==0,"EXPECTED_EXTENT");CHECK(n==used && !memcmp(trace,exp,n),"EXACT_OWNER_TRACE");
    CHECK(fwrite(trace,1,n,stdout)==n,"STDOUT");
    /* Quarantined logical frees and final harness storage release are not a UAF/drain test. */
    for(int i=0;i<nb;i++){free(blocks[i].snapshot);free(blocks[i].ptr);}return 0;
}
