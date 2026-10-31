/* Actual bodies plus explicitly reduced cfg/API, serial OS and driver leaf models. */
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
typedef struct {hsl_init_mode cpu_mode;ssdk_chip_type chip_type;ssdk_port_cfg port_cfg;unsigned nl_prot,cookie;} ssdk_init_cfg;
typedef sw_error_t (*sd_token)(void);
typedef struct {sw_error_t (*dev_clean)(unsigned);sd_token reg_get,reg_set,mii_reg_get,mii_reg_set,phy_get,phy_set,
    phy_i2c_get,phy_i2c_set,uniphy_reg_get,uniphy_reg_set;unsigned extra[3];} hsl_api_t;
typedef struct {unsigned sentinel;} adpt_api_t;
typedef struct {unsigned sentinel;} sid_pool_t;
typedef struct {unsigned sentinel;} v_array_t;
typedef struct {unsigned sentinel;} sll_head_t;
/* @GUARD_TYPES@ */
/* @GLOBALS@ */
/* @DECLARATIONS@ */
sw_error_t fal_init(unsigned,ssdk_init_cfg*);
sw_error_t fal_cleanup(unsigned);
sw_error_t hsl_api_init(unsigned);
sw_error_t old_hsl_api_init(unsigned);
sw_error_t hppe_init(unsigned,ssdk_init_cfg*);
sw_error_t hppe_cleanup(unsigned);
sw_error_t hppe_init_state_check(unsigned);
static sw_error_t hsl_dev_init_core(unsigned,ssdk_init_cfg*);
static sw_error_t sd_init(unsigned,ssdk_init_cfg*);
static sw_error_t sw_uk_init(unsigned);
static sw_error_t sw_uk_cleanup(void);
static sw_error_t hsl_api_lock_init(void);
static sw_error_t fal_vlan_init(unsigned);
static sw_error_t fal_vlan_cleanup(unsigned);
static sw_error_t adpt_init(unsigned,ssdk_init_cfg*);
static sw_error_t isis_init(unsigned,ssdk_init_cfg*);
static sw_error_t isisc_init(unsigned,ssdk_init_cfg*);
static sw_error_t mht_init(unsigned,ssdk_init_cfg*);
static sw_error_t dess_init(unsigned,ssdk_init_cfg*);
static sw_error_t scomphy_init(unsigned,ssdk_init_cfg*);
struct input {const char *name,*flow,*fault,*probe;unsigned dev,chip,cpu,lan,wan,inner,bmp;
    int residue,oom,clean,repeat,replace,partial,childbusy,nullcfg;unsigned long long start_epoch;int schedule;};
/* @CASES@ */
static const struct input *in;static ssdk_init_cfg *incoming;
static int oldapi,probing,alloc_role,serial,nb,alloc_count;
static char trace[150000];static size_t used;
static void fail(const char *s) {fprintf(stderr,"OUTER %s\n",s);exit(86);}
#define CHECK(c,s) do {if(!(c))fail(s);} while(0)
static void event(const char *fmt,...) __attribute__((format(printf,1,2)));
static void event(const char *fmt,...)
{va_list ap;va_start(ap,fmt);int n=vsnprintf(trace+used,sizeof(trace)-used,fmt,ap);va_end(ap);
 CHECK(n>=0 && (size_t)n<sizeof(trace)-used,"TRACE_EXTENT");used+=(size_t)n;}
struct block {void *p,*saved;size_t size;int id,kind,live,foreign;};
static struct block blocks[40];
static adpt_api_t adpt_token[3];static sid_pool_t pool_token[3];static v_array_t db_token[3];static sll_head_t list_token[3];
static struct block *owned(void *p,int kind)
{
    for(int i=0;i<nb;i++)if(p && blocks[i].p==p) {
        CHECK(blocks[i].live && blocks[i].kind==kind && blocks[i].size==
            (kind==3?sizeof(port_info_t):sizeof(ssdk_init_cfg)),"OWNER_BEFORE_DEREF");return &blocks[i];
    }
    fail("OWNER_IDENTITY");return NULL;
}
static int id(void *p,int kind) {return p?owned(p,kind)->id:0;}
static int flag(unsigned d)
{
#ifdef HPPE
    return hsl_hppe_owned[d];
#else
    (void)d;return 0;
#endif
}
static a_uint64_t outer_epoch(unsigned d)
{
#ifdef HPPE
    return hsl_hppe_owner_epoch[d];
#else
    (void)d;return 0;
#endif
}
/* Preservation oracle includes all known blocks, not only currently published slots. */
#define BLOCK_BYTES (sizeof(port_info_t)>sizeof(ssdk_init_cfg)?sizeof(port_info_t):sizeof(ssdk_init_cfg))
struct checkpoint {
    hsl_api_t api[3];hsl_dev_t dev[3];ssdk_init_cfg *outer[3],*child[3];
    hsl_port_prop_owner_t *token[3];port_info_t *port[3];hsl_dev_lifecycle_guard_t guards[3];
    ssdk_chip_type chips[3];a_bool_t childbusy[3];int acquired[3];ssdk_init_cfg input;
    adpt_api_t *adpt[3];sid_pool_t *pool[3];v_array_t *db[3];sll_head_t *list[3];
    adpt_api_t adpt_values[3];sid_pool_t pool_values[3];v_array_t db_values[3];sll_head_t list_values[3];
    struct {void *p;size_t size;int id,kind,live,foreign;unsigned char bytes[BLOCK_BYTES];} objects[40];
    a_uint64_t child_epoch[3],outer_epoch[3];int count,serial,alloc_count;
};
static void capture(struct checkpoint *s)
{
    memset(s,0,sizeof(*s));memcpy(s->api,hsl_api_table,sizeof(s->api));memcpy(s->dev,dev_table,sizeof(s->dev));
    memcpy(s->outer,dev_ssdk_cfg,sizeof(s->outer));memcpy(s->child,hppe_cfg,sizeof(s->child));
    memcpy(s->token,hppe_port_owner,sizeof(s->token));memcpy(s->port,p_port_info,sizeof(s->port));
    memcpy(s->guards,hsl_dev_guards,sizeof(s->guards));memcpy(s->chips,SSDK_CURRENT_CHIP_TYPE,sizeof(s->chips));
    memcpy(s->childbusy,hppe_initializing,sizeof(s->childbusy));for(unsigned d=0;d<3;d++)s->acquired[d]=flag(d);
    memcpy(s->child_epoch,hppe_owner_epoch,sizeof(s->child_epoch));for(unsigned d=0;d<3;d++)s->outer_epoch[d]=outer_epoch(d);
    s->input=*incoming;memcpy(s->adpt,g_adpt_api,sizeof(s->adpt));memcpy(s->pool,vlan_pool,sizeof(s->pool));
    memcpy(s->db,vlan_db,sizeof(s->db));memcpy(s->list,vlan_list,sizeof(s->list));
    memcpy(s->adpt_values,adpt_token,sizeof(adpt_token));memcpy(s->pool_values,pool_token,sizeof(pool_token));
    memcpy(s->db_values,db_token,sizeof(db_token));memcpy(s->list_values,list_token,sizeof(list_token));
    CHECK(nb>=0 && nb<=40,"CAPTURE_OBJECT_COUNT");s->count=nb;s->serial=serial;s->alloc_count=alloc_count;
    for(int i=0;i<nb;i++) {
        struct block *b=&blocks[i];CHECK(b->p && b->kind>=1 && b->kind<=3 && b->size==
            (b->kind==3?sizeof(port_info_t):sizeof(ssdk_init_cfg)),"CAPTURE_OWNER_BEFORE_DEREF");
        s->objects[i].p=b->p;s->objects[i].size=b->size;s->objects[i].id=b->id;s->objects[i].kind=b->kind;
        s->objects[i].live=b->live;s->objects[i].foreign=b->foreign;
        if(b->live)memcpy(s->objects[i].bytes,b->p,b->size);
    }
}
static void unchanged(struct checkpoint *before)
{struct checkpoint after;capture(&after);CHECK(!memcmp(before,&after,sizeof(after)),"REENTRY_STATE_UNCHANGED");}
static void probe(const char *site)
{
    if(probing || strcmp(in->probe,site))return;
    probing=1;unsigned d=in->dev;CHECK(d<3,"PROBE_ID");int phase=hsl_dev_guards[d].phase;
    sw_error_t r[6];struct checkpoint before;
    capture(&before);r[0]=fal_init(d,incoming);CHECK(r[0]==SW_BUSY,"REENTRY_BUSY");unchanged(&before);
    capture(&before);r[1]=hsl_dev_init(d,incoming);CHECK(r[1]==SW_BUSY,"REENTRY_BUSY");unchanged(&before);
    capture(&before);r[2]=oldapi?old_hsl_api_init(d):hsl_api_init(d);CHECK(r[2]==SW_BUSY,"REENTRY_BUSY");unchanged(&before);
    capture(&before);r[3]=fal_cleanup(d);CHECK(r[3]==SW_BUSY,"REENTRY_BUSY");unchanged(&before);
    capture(&before);r[4]=hsl_dev_cleanup(d);CHECK(r[4]==SW_BUSY,"REENTRY_BUSY");unchanged(&before);
    capture(&before);r[5]=fal_init((d+1)%3,incoming);CHECK(r[5]==SW_ALREADY_EXIST,"PEER_ADMISSION");unchanged(&before);
    if(phase==HSL_DEV_INIT_RUNNING || phase==HSL_DEV_CLEAN_RUNNING) {
        hsl_dev_lifecycle_guard_t *g=&hsl_dev_guards[d];capture(&before);sw_error_t end=hsl_dev_guard_end(&g);
        CHECK(end==SW_BAD_STATE,"RUNNING_END_REJECT");unchanged(&before);event("RUNNING_END %s %d %d\n",site,phase,end);
    }
    event("PROBE %s %d",site,phase);for(unsigned i=0;i<6;i++)event(" %d",r[i]);event("\n");probing=0;
}
struct counter {const char *name;int n;};
static struct counter calls[20];static int nc;
static int call_count(const char *name)
{for(int i=0;i<nc;i++)if(!strcmp(calls[i].name,name))return ++calls[i].n;
 CHECK(nc<20,"COUNTER_EXTENT");calls[nc++]=(struct counter){name,1};return 1;}
static sw_error_t leaf(const char *name,unsigned a,unsigned b)
{
    probe(name);int count=call_count(name);sw_error_t r=strcmp(in->fault,name)?SW_OK:count==1?SW_READ_ERROR:
        in->schedule==1?SW_OK:in->schedule==3?SW_READ_ERROR:SW_WRITE_ERROR;
    event("LEAF %s %u %u %d %d\n",name,a,b,count,r);return r;
}
static void *aos_mem_alloc(size_t size)
{
    probe("ALLOC");int kind=size==sizeof(port_info_t)?3:alloc_role;
    CHECK((kind>=1 && kind<=3) && sizeof(port_info_t)!=sizeof(ssdk_init_cfg),"ALLOC_SHAPE");
    int ident=++serial,ok=++alloc_count!=in->oom;event("ALLOC %d %d %zu %d\n",ident,kind,size,ok);
    if(!ok)return NULL;
    void *p=calloc(1,size);CHECK(p && nb<40,"HOST_ALLOC");blocks[nb++]=(struct block){p,NULL,size,ident,kind,1,0};return p;
}
static void aos_mem_free(void *p)
{if(!p)return;for(int i=0;i<nb;i++)if(blocks[i].p==p) {
 CHECK(blocks[i].live && !blocks[i].foreign,"ONLY_OWNED_FREE");blocks[i].live=0;event("FREE %d\n",blocks[i].id);return;}
 fail("FREE_IDENTITY");}
static void aos_mem_copy(void *p,const void *src,size_t n)
{struct block *b=NULL;for(int i=0;i<nb;i++)if(blocks[i].p==p)b=&blocks[i];
 CHECK(b && b->live && !b->foreign && b->kind!=3 && n==b->size,"CFG_COPY_OWNER");memcpy(p,src,n);event("COPY %d %zu\n",b->id,n);}
static void aos_mem_zero(void *p,size_t n)
{struct block *b=owned(p,3);CHECK(!b->foreign && n==b->size,"PORT_ZERO_OWNER");memset(p,0,n);event("ZERO %d %zu\n",b->id,n);}
static void aos_mem_set(void *p,int v,size_t n)
{
    CHECK(v==0,"SET_VALUE");unsigned d=in->dev;CHECK(d<3,"SET_ID");
    if(p==&hsl_api_table[d]) {probe("APISET");CHECK(n==sizeof(hsl_api_t),"API_EXTENT");event("SET API %u\n",d);}
    else {probe("METASET");CHECK(p==&dev_table[d] && n==sizeof(hsl_dev_t),"META_EXTENT");event("SET META %u\n",d);}
    memset(p,v,n);
}
static a_uint32_t qca_ssdk_port_bmp_get(unsigned d) {CHECK(d<3,"BMP_ID");return in->bmp;}
#define SD(n) static sw_error_t n(void) {return SW_OK;}
SD(sd_reg_hdr_get) SD(sd_reg_hdr_set) SD(sd_reg_mii_mdio_get) SD(sd_reg_mii_mdio_set)
SD(sd_reg_mdio_get) SD(sd_reg_mdio_set) SD(sd_reg_i2c_get) SD(sd_reg_i2c_set)
SD(sd_reg_uniphy_get) SD(sd_reg_uniphy_set) SD(foreign_sd)
static sw_error_t foreign_clean(unsigned d) {(void)d;return SW_OK;}
static sw_error_t legacy_clean(unsigned d)
{sw_error_t r=leaf("LEGACY_CLEAN",d,0);if(!r && in->replace==7)hsl_api_table[d].dev_clean=foreign_clean;return r;}
/* @BODIES@ */
static sw_error_t hsl_dev_init_core(unsigned d,ssdk_init_cfg *cfg)
{int saved=alloc_role;alloc_role=1;sw_error_t r=actual_hsl_core(d,cfg);alloc_role=saved;return r;}
#ifdef HPPE
sw_error_t hppe_init(unsigned d,ssdk_init_cfg *cfg)
{probe("HPPE");int saved=alloc_role;alloc_role=2;sw_error_t r=actual_hppe_init(d,cfg);alloc_role=saved;return r;}
sw_error_t hppe_cleanup(unsigned d)
{probe("CHILD_CLEAN");return actual_hppe_cleanup(d);}
#endif
static sw_error_t sd_init(unsigned d,ssdk_init_cfg *cfg)
{sw_error_t r=leaf("SD",d,cfg->chip_type);
#ifdef HPPE
 if(!r && !strcmp(in->flow,"sd-child")) {r=hppe_init(d,cfg);CHECK(r==SW_OK,"SD_CHILD_ACTOR");event("SD_CHILD_RETURN %d\n",r);}
#endif
 return r;}
static sw_error_t sw_uk_init(unsigned p) {return leaf("UK_INIT",p,0);}
static sw_error_t sw_uk_cleanup(void) {return leaf("UK_CLEAN",0,0);}
static sw_error_t hsl_api_lock_init(void) {return leaf("LOCK",0,0);}
static sw_error_t fal_vlan_init(unsigned d) {return leaf("VLAN_INIT",d,0);}
static sw_error_t fal_vlan_cleanup(unsigned d) {return leaf("VLAN_CLEAN",d,0);}
static sw_error_t adpt_init(unsigned d,ssdk_init_cfg *cfg) {return leaf("ADPT",d,cfg->chip_type);}
static sw_error_t legacy_init(unsigned d,ssdk_init_cfg *cfg,const char *chip)
{
    sw_error_t r=leaf(chip,d,cfg->chip_type);if(r)return r;
    dev_table[d]=(hsl_dev_t){.dev_id=d,.cpu_port_nr=0,.nr_ports=6,.nr_phy=5,.nr_queue=4,.nr_vlans=4096,.hw_vlan_query=A_TRUE,.cpu_mode=cfg->cpu_mode,.wan_bmp=cfg->port_cfg.wan_bmp};
    hsl_api_table[d].dev_clean=legacy_clean;return SW_OK;
}
#define LEGACY(fn,label) static sw_error_t fn(unsigned d,ssdk_init_cfg *cfg) {return legacy_init(d,cfg,label);}
LEGACY(isis_init,"ISIS") LEGACY(isisc_init,"ISISC") LEGACY(mht_init,"MHT")
LEGACY(dess_init,"DESS") LEGACY(scomphy_init,"SCOMPHY")
static void *seed(unsigned d,int kind,int ident)
{
    size_t n=kind==3?sizeof(port_info_t):sizeof(ssdk_init_cfg);void *p=calloc(1,n);CHECK(p && nb<40,"SEED_ALLOC");
    if(kind==3) {port_info_t *v=p;v->dev_portmap=0x88;for(unsigned i=0;i<5;i++)v->property[i]=1u<<i;
        for(unsigned i=0;i<16;i++)v->phy_id[i]=1000+d*16+i;}
    else {ssdk_init_cfg *v=p;v->chip_type=CHIP_DESS;v->cookie=0xbadc0de;}
    void *saved=malloc(n);CHECK(saved,"SEED_SAVE");memcpy(saved,p,n);blocks[nb++]=(struct block){p,saved,n,ident,kind,1,1};return p;
}
static int clean_id(sw_error_t (*p)(unsigned))
{if(!p)return 0;
#ifdef HPPE
 if(p==hppe_cleanup)return 1;
#endif
 if(p==foreign_clean)return 2;
 CHECK(p==legacy_clean,"API_CALLBACK_IDENTITY");return 3;}
static int sd_id(sd_token p,sd_token own)
{if(!p)return 0;if(p==own)return 1;CHECK(p==foreign_sd,"API_FIELD_IDENTITY");return 2;}
static int cfg_id(ssdk_init_cfg *p)
{if(!p)return 0;if(p==incoming)return -1;for(int i=0;i<nb;i++)if(blocks[i].p==p)return id(p,blocks[i].kind);fail("CFG_IDENTITY");return 0;}
static void cfg_dump(const char *name,unsigned d,ssdk_init_cfg *p)
{if(!p)return;int ident=cfg_id(p);event("CFG %s %u %d %d %d %u %u %u %u %u %u\n",name,d,ident,p->cpu_mode,p->chip_type,
 p->port_cfg.cpu_bmp,p->port_cfg.lan_bmp,p->port_cfg.wan_bmp,p->port_cfg.inner_bmp,p->nl_prot,p->cookie);}
static void snapshot(const char *label)
{
    event("SNAP %s\n",label);
    for(unsigned d=0;d<3;d++) {
        hsl_dev_t *v=&dev_table[d];event("META %u %u %u %u %u %u %u %d %d %u\n",d,v->dev_id,v->cpu_port_nr,v->nr_ports,v->nr_phy,v->nr_queue,v->nr_vlans,v->hw_vlan_query,v->cpu_mode,v->wan_bmp);
        event("OUTER %u %d %d %d %d %d\n",d,cfg_id(dev_ssdk_cfg[d]),flag(d),hsl_dev_guards[d].phase,cfg_id(hsl_dev_guards[d].cfg),SSDK_CURRENT_CHIP_TYPE[d]);
        event("EPOCH %u %llu %llu\n",d,(unsigned long long)hppe_owner_epoch[d],(unsigned long long)outer_epoch(d));
        cfg_dump("O",d,dev_ssdk_cfg[d]);cfg_dump("C",d,hppe_cfg[d]);
        event("CHILD %u %d %d %d %d\n",d,cfg_id(hppe_cfg[d]),id(p_port_info[d],3),id(hppe_port_owner[d],3),hppe_initializing[d]);
        if(p_port_info[d]) {port_info_t *p=p_port_info[d];event("PORT %u %u",d,p->dev_portmap);
            for(unsigned t=0;t<5;t++)event(" %u",p->property[t]);
            for(unsigned i=0;i<16;i++)event(" %u",p->phy_id[i]);
            event("\n");}
        hsl_api_t *a=&hsl_api_table[d];event("API %u %d",d,clean_id(a->dev_clean));
#define TOK(f,n) event(" %d",sd_id(a->f,n))
        TOK(reg_get,sd_reg_hdr_get);TOK(reg_set,sd_reg_hdr_set);TOK(mii_reg_get,sd_reg_mii_mdio_get);TOK(mii_reg_set,sd_reg_mii_mdio_set);
        TOK(phy_get,sd_reg_mdio_get);TOK(phy_set,sd_reg_mdio_set);TOK(phy_i2c_get,sd_reg_i2c_get);TOK(phy_i2c_set,sd_reg_i2c_set);
        TOK(uniphy_reg_get,sd_reg_uniphy_get);TOK(uniphy_reg_set,sd_reg_uniphy_set);
#undef TOK
        for(unsigned i=0;i<3;i++)event(" %u",a->extra[i]);
        event("\n");
        CHECK(!g_adpt_api[d] || g_adpt_api[d]==&adpt_token[d],"ADPT_IDENTITY");
        CHECK(!vlan_pool[d] || vlan_pool[d]==&pool_token[d],"VLAN_IDENTITY");
        CHECK(!vlan_db[d] || vlan_db[d]==&db_token[d],"VLAN_IDENTITY");
        CHECK(!vlan_list[d] || vlan_list[d]==&list_token[d],"VLAN_IDENTITY");
        event("RESIDUE %u %d %d %d %d\n",d,g_adpt_api[d]!=NULL,vlan_pool[d]!=NULL,vlan_db[d]!=NULL,vlan_list[d]!=NULL);
    }
    for(int i=0;i<nb;i++) {
        if(blocks[i].foreign)CHECK(blocks[i].live && !memcmp(blocks[i].p,blocks[i].saved,blocks[i].size),"FOREIGN_BYTES");
        int reachable=0;for(unsigned d=0;d<3;d++)if(blocks[i].p==(void*)dev_ssdk_cfg[d] || blocks[i].p==(void*)hppe_cfg[d] || blocks[i].p==(void*)p_port_info[d] || blocks[i].p==(void*)hppe_port_owner[d])reachable=1;
        event("OWNER %d %d %d %d %d\n",blocks[i].id,blocks[i].kind,blocks[i].live,blocks[i].foreign,reachable);
        if(blocks[i].live) {
            struct block *b=owned(blocks[i].p,blocks[i].kind);
            if(b->kind==3) {port_info_t *p=b->p;event("PORTBLOCK %d %u",b->id,p->dev_portmap);
                for(unsigned t=0;t<5;t++)event(" %u",p->property[t]);
                for(unsigned j=0;j<16;j++)event(" %u",p->phy_id[j]);
                event("\n");}
            else {ssdk_init_cfg *p=b->p;event("CFGBLOCK %d %d %d %u %u %u %u %u %u\n",b->id,p->cpu_mode,p->chip_type,
                p->port_cfg.cpu_bmp,p->port_cfg.lan_bmp,p->port_cfg.wan_bmp,p->port_cfg.inner_bmp,p->nl_prot,p->cookie);}
        }
    }
    event("COUNTERS");for(int i=0;i<nc;i++)event(" %s=%d",calls[i].name,calls[i].n);event(" ALLOC=%d\n",alloc_count);
}
static int expects[100],nr,next;
static void result(sw_error_t r) {CHECK(next<nr && r==expects[next++],"FIRST_ERROR");event("RETURN %d\n",r);snapshot("AFTER_CALL");}
static void token_flow(unsigned d,ssdk_init_cfg *cfg)
{
    hsl_dev_lifecycle_guard_t rogue={0},*g=NULL,*stale;
    result(hsl_dev_init_begin(d,NULL,&g));result(hsl_dev_init_begin(d,cfg,NULL));
    g=&rogue;result(hsl_dev_init_begin(d,cfg,&g));g=NULL;
    result(hsl_dev_init_guarded(NULL));result(hsl_dev_init_guarded(&rogue));result(hsl_dev_cleanup_guarded(&rogue));
    result(hsl_dev_api_init_guarded(&rogue));result(hsl_dev_guard_end(NULL));result(hsl_dev_guard_end(&g));
    result(hsl_dev_init_begin(d,cfg,&g));stale=g;
    struct {unsigned prefix;hsl_dev_lifecycle_guard_t token;} holder={0};holder.token=*g;
    result(hsl_dev_init_guarded(&holder.token));result(hsl_dev_api_init_guarded(&holder.token));
    result(hsl_dev_cleanup_guarded(&holder.token));hsl_dev_lifecycle_guard_t *foreign=&holder.token;
    result(hsl_dev_guard_end(&foreign));CHECK(foreign==&holder.token,"FOREIGN_GUARD_HANDLE");
    result(hsl_dev_cleanup_guarded(g));result(hsl_dev_api_init_guarded(g));result(hsl_dev_api_init_guarded(g));
    result(hsl_dev_guard_end(&g));CHECK(!g,"GUARD_CONSUME");
    result(hsl_dev_init_guarded(stale));result(hsl_dev_api_init_guarded(stale));result(hsl_dev_guard_end(&stale));
    result(hsl_dev_guard_end(&g));result(hsl_dev_cleanup_begin(d,&g));stale=g;
    result(hsl_dev_init_guarded(g));result(hsl_dev_api_init_guarded(g));result(hsl_dev_cleanup_guarded(g));
    result(hsl_dev_cleanup_guarded(g));result(hsl_dev_guard_end(&g));CHECK(!g,"GUARD_CONSUME");
    result(hsl_dev_cleanup_guarded(stale));
}
int main(int argc,char **argv)
{
    CHECK(argc==5,"ARGUMENTS");unsigned ix=(unsigned)strtoul(argv[1],NULL,10);CHECK(ix<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");in=&inputs[ix];oldapi=atoi(argv[4]);
    const char *s=argv[2];char *end;while(*s) {CHECK(nr<100,"RETURN_COUNT");long r=strtol(s,&end,10);CHECK(end>s,"RETURN_CSV");expects[nr++]=(int)r;if(!*end)break;CHECK(*end==',',"RETURN_CSV");s=end+1;}
    ssdk_init_cfg cfg={0};cfg.cpu_mode=HSL_CPU_1;cfg.chip_type=(ssdk_chip_type)in->chip;
    cfg.port_cfg=(ssdk_port_cfg){.cpu_bmp=in->cpu,.lan_bmp=in->lan,.wan_bmp=in->wan,.inner_bmp=in->inner};cfg.nl_prot=77;cfg.cookie=0xc0ffee;incoming=&cfg;
    for(unsigned d=0;d<3;d++) {
        dev_table[d]=(hsl_dev_t){.dev_id=d,.cpu_port_nr=7,.nr_ports=9,.nr_phy=11,.nr_queue=13,.nr_vlans=17,.wan_bmp=68};
        if(d!=in->dev) {dev_ssdk_cfg[d]=seed(d,1,100+d*10);p_port_info[d]=seed(d,3,102+d*10);}
        hsl_api_t *a=&hsl_api_table[d];if(d!=in->dev)a->dev_clean=foreign_clean;
#define SEED(f) a->f=foreign_sd
        SEED(reg_get);SEED(reg_set);SEED(mii_reg_get);SEED(mii_reg_set);SEED(phy_get);SEED(phy_set);
        SEED(phy_i2c_get);SEED(phy_i2c_set);SEED(uniphy_reg_get);SEED(uniphy_reg_set);
#undef SEED
        for(unsigned i=0;i<3;i++)a->extra[i]=10000+d*10+i;
    }
    unsigned d=in->dev;
    if(d<3) {
        hppe_owner_epoch[d]=(a_uint64_t)in->start_epoch;
        if(in->residue==1)p_port_info[d]=seed(d,3,900);
        if(in->residue==2)dev_ssdk_cfg[d]=seed(d,1,901);
        if(in->residue==3)hsl_api_table[d].dev_clean=foreign_clean;
        if(in->residue==4)g_adpt_api[d]=&adpt_token[d];
#ifdef HPPE
        if(in->residue==5)hsl_hppe_owned[d]=A_TRUE;
        if(in->residue==6)hsl_hppe_owner_epoch[d]=13;
#endif
        if(in->residue>=8) {unsigned mask=(unsigned)in->residue-8;
            if(mask&1)vlan_pool[d]=&pool_token[d];
            if(mask&2)vlan_db[d]=&db_token[d];
            if(mask&4)vlan_list[d]=&list_token[d];}
    }
    snapshot("ENTRY");
    if(!strcmp(in->flow,"token"))token_flow(d,&cfg);
#ifdef HPPE
    else if(!strcmp(in->flow,"partial-serial")) {
        ssdk_init_cfg broken=cfg;broken.port_cfg.cpu_bmp=0;result(hsl_dev_init(d,&broken));
        result(hppe_init(d,&cfg));snapshot("SERIAL_PARTIAL_BEFORE_CLEAN");result(hsl_dev_cleanup(d));
    }
    else if(!strcmp(in->flow,"recreate") || !strcmp(in->flow,"retire-only")) {
        result(fal_init(d,&cfg));ssdk_init_cfg *old_c=hppe_cfg[d];int old_id=id(old_c,2);
        snapshot("BEFORE_DIRECT_RETIRE");result(hppe_cleanup(d));
        if(!strcmp(in->flow,"recreate")) {ssdk_init_cfg other=cfg;other.cookie++;result(hppe_init(d,&other));
            CHECK(hppe_cfg[d] && hppe_cfg[d]!=old_c,"DISTINCT_CHILD_ALLOCATIONS");event("REPLACEMENT %d %d\n",old_id,id(hppe_cfg[d],2));}
        snapshot("BEFORE_STALE_OUTER_CLEAN");result(fal_cleanup(d));
    } else if(!strcmp(in->flow,"epoch-api")) {
        a_uint64_t token=77,empty=0;result(hppe_init_owned(d,&cfg,NULL));result(hppe_init_owned(3,&cfg,&token));result(hppe_cleanup_owned(3,0));result(hppe_init_owned(d,&cfg,&token));
        event("OWNED_OUTPUT %llu\n",(unsigned long long)token);token=0;result(hppe_init_owned(d,NULL,&token));event("OWNED_OUTPUT %llu\n",(unsigned long long)token);result(hppe_init_owned(d,&cfg,&token));
        event("OWNED_OUTPUT %llu\n",(unsigned long long)token);result(hppe_init_owned(d,&cfg,&empty));event("OWNED_OUTPUT %llu\n",(unsigned long long)empty);
        hppe_initializing[d]=A_TRUE;result(hppe_init_owned(d,&cfg,&empty));result(hppe_cleanup_owned(d,0));hppe_initializing[d]=A_FALSE;
        result(hppe_cleanup_owned(d,0));result(hppe_cleanup_owned(d,token+1));
        hppe_initializing[d]=A_TRUE;result(hppe_cleanup_owned(d,token));hppe_initializing[d]=A_FALSE;
        snapshot("BEFORE_OWNED_CLEAN");result(hppe_cleanup_owned(d,token));result(hppe_cleanup_owned(d,token));
    } else if(!strcmp(in->flow,"epoch-retry")) {
        a_uint64_t token=0;ssdk_init_cfg first=cfg;if(in->partial)first.port_cfg.cpu_bmp=0;
        result(hppe_init_owned(d,&first,&token));event("OWNED_OUTPUT %llu\n",(unsigned long long)token);
        result(hppe_init_owned(d,&cfg,&token));event("OWNED_OUTPUT %llu\n",(unsigned long long)token);
        snapshot("BEFORE_OWNED_CLEAN");result(hppe_cleanup_owned(d,token));
    } else if(!strcmp(in->flow,"epoch-max")) {
        result(fal_init(d,&cfg));result(hppe_init(d,&cfg));snapshot("BEFORE_MAX_CLEAN");result(fal_cleanup(d));
        snapshot("BEFORE_EXHAUST_DIRECT");result(hppe_init(d,&cfg));result(fal_init(d,&cfg));
    }
#endif
    else if(!strcmp(in->flow,"unowned") || !strcmp(in->flow,"unowned-init")) {
#ifdef HPPE
        ssdk_init_cfg child=cfg;child.chip_type=CHIP_HPPE;alloc_role=2;result(hppe_init(d,&child));
        if(in->partial)dev_ssdk_cfg[d]=seed(d,1,901);
        if(in->childbusy)hppe_initializing[d]=A_TRUE;
        snapshot("UNOWNED_BEFORE_OUTER");if(!strcmp(in->flow,"unowned"))result(fal_cleanup(d));result(fal_init(d,&cfg));
#else
        fail("UNSUPPORTED_CASE");
#endif
    } else if(!strcmp(in->flow,"api"))result(oldapi?old_hsl_api_init(d):hsl_api_init(d));
    else {
        sw_error_t r=SW_OK;
        for(int repeat=0;repeat<in->repeat;repeat++) {
            r=!strcmp(in->flow,"hsl")?hsl_dev_init(d,in->nullcfg?NULL:&cfg):fal_init(d,in->nullcfg?NULL:&cfg);result(r);
        }
        if(in->clean && (r==SW_OK || in->clean==2)) {
            if(d<3 && in->replace==1)hsl_api_table[d].dev_clean=foreign_clean;
            if(d<3 && in->replace==2 && hppe_port_owner[d])p_port_info[d]=seed(d,3,900);
#ifdef HPPE
            if(d<3 && in->replace==3)hsl_hppe_owner_epoch[d]=0;
            if(d<3 && in->replace==4)hsl_hppe_owned[d]=A_FALSE;
            if(d<3 && in->replace==5)hsl_hppe_owner_epoch[d]++;
            if(d<3 && in->replace==6)dev_ssdk_cfg[d]=NULL;
#endif
            snapshot("BEFORE_CLEAN");result(!strcmp(in->flow,"hsl")?hsl_dev_cleanup(d):fal_cleanup(d));
            if(in->partial==2) {snapshot("BEFORE_RETRY_CLEAN");result(!strcmp(in->flow,"hsl")?hsl_dev_cleanup(d):fal_cleanup(d));}
        }
        if(d>=3) {result(hsl_dev_init(d,&cfg));result(hsl_api_init(d));result(fal_cleanup(d));result(hsl_dev_cleanup(d));}
    }
    CHECK(next==nr,"RETURN_COUNT");event("END SERIAL_REDUCED_MODEL\n");
    FILE *f=fopen(argv[3],"rb");CHECK(f,"EXPECTED_OPEN");char expected[sizeof(trace)];size_t n=fread(expected,1,sizeof(expected),f);
    CHECK(!ferror(f) && feof(f) && fclose(f)==0,"EXPECTED_EXTENT");CHECK(n==used && !memcmp(expected,trace,n),"EXACT_STATE_TRACE");
    CHECK(fwrite(trace,1,n,stdout)==n,"STDOUT");
    for(int i=0;i<nb;i++){free(blocks[i].saved);free(blocks[i].p);}return 0;
}
