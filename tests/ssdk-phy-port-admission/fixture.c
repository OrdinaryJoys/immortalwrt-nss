/* Linux/large structs and service leaves below are explicit host models. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <limits.h>
typedef uint8_t __a_uint8_t;
typedef uint16_t __a_uint16_t;
typedef uint32_t __a_uint32_t;
#define EPROBE_DEFER 517
#define CONFIG_OF 1
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#define IS_ENABLED(x) 0
#define GFP_KERNEL 0
#define SSDK_WARN(...) ((void)0)
#define SSDK_ERROR(...) ((void)0)
/* @TYPES@ */
_Static_assert(SW_MAX_NR_PORT==16, "actual port capacity");
_Static_assert(sizeof(phy_dac_t)==2 && sizeof(((phy_dac_t*)0)->mdac)==1 &&
               sizeof(((phy_dac_t*)0)->edac)==1, "actual two-u8 DAC");
static void fail(const char *s) { fprintf(stderr,"SSDK_PORT %s\n",s); exit(86); }
#define CHECK(c,s) do { if (!(c)) fail(s); } while (0)
static char trace[120000];
static size_t used;
static void event(const char *fmt, ...) __attribute__((format(printf,1,2)));
static void event(const char *fmt, ...)
{
    va_list ap;
    va_start(ap,fmt);
    int n=vsnprintf(trace+used,sizeof(trace)-used,fmt,ap);
    va_end(ap);
    CHECK(n>=0 && (size_t)n<sizeof(trace)-used,"TRACE_CAPACITY");
    used+=(size_t)n;
}
static a_uint32_t safe_bit(a_uint32_t p)
{
    CHECK(p<SW_MAX_NR_PORT || p==24,"PORT_BOUNDS_SAFE");
    return UINT32_C(1)<<p;
}
#define BIT(p) safe_bit(p)
struct port_input {
    int enabled,id_len,id_error,dac_len,dac_error;
    a_uint32_t id,dac0,dac1;
    int i2c,i2c_error,force,c45,combo,sfp,mac,external,external_fail,mdio;
    a_uint32_t address,i2c_address,speed,duplex;
    int rx,tx,present,medium;
};
struct switch_input { int enabled,container,container_enabled,nports,mode; a_uint32_t id; struct port_input ports[4]; };
struct input { const char *name,*flow; int count,repeats,fault,foreign; struct switch_input switches[3]; };
/* @CASES@ */
static const struct input *input;
static int expected_ret,expected_pure;
struct device_node { int ident,kind,s,p,refs; const char *name; };
static struct device_node instance,sw[3],container[3],ports[3][4],external[3][4],foreign_node;
static struct device_node *known(struct device_node *n)
{
    CHECK(n!=NULL,"NODE_NULL_DEREF");
    if (n==&instance || n==&foreign_node) return n;
    for (int s=0;s<3;s++) {
        if(n==&sw[s] || n==&container[s]) return n;
        for(int p=0;p<4;p++) if(n==&ports[s][p] || n==&external[s][p]) return n;
    }
    fail("NODE_IDENTITY"); return NULL;
}
static struct device_node *get(struct device_node *n)
{
    if(n) { known(n); CHECK(n->refs>=2,"NODE_OWNER_BEFORE_GET"); n->refs++; event("GET %d\n",n->ident); }
    return n;
}
static void of_node_put(struct device_node *n)
{
    if(n) { known(n); CHECK(n->refs>2,"NODE_DOUBLE_OR_FOREIGN_PUT"); n->refs--; event("PUT %d\n",n->ident); }
}
static const struct port_input *pi(struct device_node *n)
{
    known(n); CHECK(n->kind==3,"PORT_NODE_KIND");
    return &input->switches[n->s].ports[n->p];
}
static struct device_node *of_get_child_by_name(struct device_node *n,const char *name)
{
    known(n);
    if(n->kind==1 && !strcmp(name,"qcom,port_phyinfo"))
        return input->switches[n->s].container ? get(&container[n->s]) : NULL;
    if(n->kind==3 && !strcmp(name,"switch_external")) return pi(n)->external ? get(&external[n->s][n->p]) : NULL;
    fail("CHILD_LOOKUP_SCOPE"); return NULL;
}
static struct device_node *next_child(struct device_node *parent,struct device_node *prev)
{
    known(parent); CHECK(parent->kind==2,"ITERATOR_PARENT");
    int start=0;
    if(prev) { known(prev); CHECK(prev->kind==3 && prev->s==parent->s,"ITERATOR_PREV"); start=prev->p+1; }
    struct device_node *next=NULL;
    for(int p=start;p<input->switches[parent->s].nports;p++)
        if(input->switches[parent->s].ports[p].enabled) {next=get(&ports[parent->s][p]);break;}
    of_node_put(prev);
    return next;
}
#define for_each_available_child_of_node(parent,child) \
    for((child)=next_child((parent),NULL);(child);(child)=next_child((parent),(child)))
static struct device_node *of_find_node_by_name(struct device_node *from,const char *name)
{
    struct device_node *next=NULL;
    if(!strcmp(name,"ess-instance")) next=get(&instance);
    else {
        int s=-1;
        if(!strcmp(name,"ess-switch")) s=0;
        else if(!strcmp(name,"ess-switch1")) s=1;
        else if(!strcmp(name,"ess-switch2")) s=2;
        CHECK(s>=0,"SWITCH_LOOKUP_SCOPE");
        if(s<input->count) next=get(&sw[s]);
    }
    of_node_put(from);
    return next;
}
static int of_device_is_available(struct device_node *n) { known(n); CHECK(n->kind==1,"AVAILABLE_KIND"); return input->switches[n->s].enabled; }
struct property { int dummy; };
static struct property property;
static struct property *of_find_property(struct device_node *n,const char *name,int *len)
{
    known(n); int length=-1;
    if(n->kind==0 && !strcmp(name,"num_devices")) length=4;
    else if(n->kind==1 && !strcmp(name,"device_id")) length=4;
    else if(n->kind==3 && !strcmp(name,"phy_dac")) length=pi(n)->dac_len;
    else fail("FIND_PROPERTY_SCOPE");
    if(len) *len=length;
    return length<0 ? NULL : &property;
}
typedef a_uint32_t __be32;
static __be32 raw_dac[3];
static a_uint32_t big_endian(a_uint32_t v)
{
    unsigned char *b=(unsigned char *)&v;
    return ((a_uint32_t)b[0]<<24)|((a_uint32_t)b[1]<<16)|((a_uint32_t)b[2]<<8)|b[3];
}
static a_uint32_t be32_to_cpup(const __be32 *p)
{
    CHECK(p==raw_dac || p==raw_dac+1,"RAW_DAC_IDENTITY_BEFORE_READ");
    return big_endian(*p);
}
static const void *of_get_property(struct device_node *n,const char *name,void *length)
{
    const struct port_input *p=pi(n);CHECK(!strcmp(name,"phy_dac"),"RAW_PROPERTY_SCOPE");
    if(length) {a_uint32_t size=(a_uint32_t)p->dac_len;memcpy(length,&size,sizeof(size));}
    if(p->dac_len<0)return NULL;
    /* Instrumented old boundary witness: refuse BEFORE raw prefix dereference. */
    CHECK(p->dac_len>=8 && !p->dac_error,"OLD_RAW_DAC_BOUNDARY");
    unsigned char *raw=(unsigned char *)raw_dac;
    a_uint32_t values[3]={p->dac0,p->dac1,0};
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<4;j++)raw[i*4+j]=(unsigned char)(values[i]>>(24-j*8));
    return raw_dac;
}
static int read_array(struct device_node *n,const char *name,a_uint32_t *out,size_t count)
{
    known(n); int len=-1,error=0; a_uint32_t values[3]={0};
    CHECK(count>0 && count<=3,"ARRAY_MODEL_COUNT");
    if(n->kind==0 && !strcmp(name,"num_devices")) {len=4;values[0]=(a_uint32_t)input->count;}
    else if(n->kind==1 && !strcmp(name,"device_id")) {len=4;values[0]=input->switches[n->s].id;}
    else if(n->kind==1 && !strcmp(name,"reg")) {len=8;values[0]=0xa100u+(a_uint32_t)n->s*256;values[1]=4096u+(a_uint32_t)n->s;}
    else if(n->kind==3) {
        const struct port_input *p=pi(n);
        if(!strcmp(name,"port_id")) {len=p->id_len;error=p->id_error;values[0]=p->id;}
        else if(!strcmp(name,"phy_dac")) {len=p->dac_len;error=p->dac_error;values[0]=p->dac0;values[1]=p->dac1;}
        else if(!strcmp(name,"phy_address")) {len=4;values[0]=p->address;}
        else if(!strcmp(name,"phy_i2c_address")) {len=4;error=p->i2c_error;values[0]=p->i2c_address;}
        else if(!strcmp(name,"forced-speed")) {len=p->force?4:-1;values[0]=p->speed;}
        else if(!strcmp(name,"forced-duplex")) {len=p->force?4:-1;values[0]=p->duplex;}
        else fail("READ_PORT_PROPERTY_SCOPE");
    } else if(n->kind==4 && !strcmp(name,"switch_cpu_port")) {len=4;values[0]=3;}
    else fail("READ_ARRAY_SCOPE");
    int ret=error ? error : len<0 ? -EINVAL : len==0 ? -ENODATA : (size_t)len<count*4 ? -EOVERFLOW : 0;
    event("READ %d %s %zu %d\n",n->ident,name,count,ret);
    if(!ret) memcpy(out,values,count*4);
    return ret; /* fixed array wrapper returns zero, not positive count */
}
#define of_property_read_u32_array read_array
static int of_property_read_u32(struct device_node *n,const char *name,a_uint32_t *out) {return read_array(n,name,out,1);}
static int of_property_read_string(struct device_node *n,const char *name,const char **out)
{
    known(n);
    if(n->kind==1 && !strcmp(name,"switch_access_mode")) {
        int m=input->switches[n->s].mode;
        *out=m==0?"local bus":m==1?"pcie bus":"mdio"; event("ACCESS %d %d\n",n->ident,m); return 0;
    }
    if(n->kind==3) {
        const struct port_input *p=pi(n);
        if(!strcmp(name,"port_mac_sel")) {if(!p->mac)return -EINVAL;*out=p->mac==1?"QGMAC_PORT":"XGMAC_PORT";return 0;}
        if(!strcmp(name,"media-type")) {if(!p->sfp)return -EINVAL;*out=p->sfp==1?"sfp":"sfp_sgmii";return 0;}
    }
    fail("READ_STRING_SCOPE"); return -EINVAL;
}
static int of_property_read_bool(struct device_node *n,const char *name)
{
    const struct port_input *p=pi(n);
    if(!strcmp(name,"phy-i2c-mode"))return p->i2c;
    if(!strcmp(name,"ethernet-phy-ieee802.3-c45"))return p->c45;
    if(!strcmp(name,"ethernet-phy-combo"))return p->combo;
    fail("READ_BOOL_SCOPE"); return 0;
}
struct mii_bus {int token;};
static struct mii_bus bus;
static struct device_node *of_parse_phandle(struct device_node *n,const char *name,int index)
{
    known(n); CHECK(index==0,"PHANDLE_INDEX");
    if(n->kind==3 && !strcmp(name,"mdiobus")) return pi(n)->mdio ? get(&foreign_node) : NULL;
    if(n->kind==4 && !strcmp(name,"switch_handle"))return NULL;
    fail("PHANDLE_SCOPE"); return NULL;
}
static struct device_node *ssdk_dt_get_mdio_node(a_uint32_t d) {CHECK(d<3,"MDIO_DEV");return NULL;}
static struct mii_bus *of_mdio_find_bus(struct device_node *n) {CHECK(n==&foreign_node,"MDIO_TOKEN");return &bus;}
static sw_error_t ssdk_miibus_add(a_uint32_t d,struct mii_bus *b,a_uint32_t *index)
{CHECK(d<3 && b==&bus,"MIIBUS_PARAMETERS");*index=2;event("BUS %u 2\n",d);return SW_OK;}
static int of_get_named_gpio(struct device_node *n,const char *name,int index)
{
    known(n); CHECK(index==0,"GPIO_INDEX");
    if(n==&foreign_node && !strcmp(name,"phy-reset-gpio"))return 17;
    const struct port_input *p=pi(n);
    if(!strcmp(name,"sfp_rx_los_pin"))return p->rx;
    if(!strcmp(name,"sfp_tx_dis_pin"))return p->tx;
    if(!strcmp(name,"sfp_mod_present_pin"))return p->present;
    if(!strcmp(name,"sfp_medium_pin"))return p->medium;
    fail("GPIO_SCOPE");return 0;
}
struct qca_phy_priv { a_uint32_t sfp_rx_los_pin[SW_MAX_NR_PORT],sfp_tx_dis_pin[SW_MAX_NR_PORT],sfp_mod_present_pin[SW_MAX_NR_PORT],sfp_medium_pin[SW_MAX_NR_PORT]; };
static struct qca_phy_priv private_data[SW_MAX_NR_DEV];
static struct qca_phy_priv *ssdk_phy_priv_data_get(a_uint32_t d) {CHECK(d<3,"PRIVATE_DEV");return &private_data[d];}
typedef struct {struct {a_uint32_t wan_bmp,lan_bmp;} port_cfg;} ssdk_init_cfg;
typedef struct {a_uint8_t switch_netdev_port; a_bool_t switch_connected; a_uint8_t switch_dev_id,switch_cpu_port;} ssdk_netdev_switch_t;
static ssdk_netdev_switch_t ext_state;
static a_uint32_t ssdk_dts_netdev_switch_alloc(ssdk_netdev_switch_t **out)
{
    struct device_node *active_port=NULL;
    for(int s=0;s<3;s++)for(int p=0;p<4;p++)if(ports[s][p].refs>2) {
        CHECK(active_port==NULL,"EXTERNAL_SINGLE_CHILD");active_port=&ports[s][p];
    }
    CHECK(active_port!=NULL,"EXTERNAL_ACTIVE");const struct port_input *p=pi(active_port);
    event("EXTERNAL %d %d\n",active_port->ident,p->external_fail);
    if(p->external_fail)return SSDK_NETDEV_SWITCH_NUM;
    *out=&ext_state;return 0;
}
struct metadata {a_uint32_t address,reset,speed,fake,access; a_uint8_t duplex; phy_dac_t dac; a_bool_t c45,combo; phy_features_t features;};
static struct metadata meta[SW_MAX_NR_DEV][SW_MAX_NR_PORT],foreign_meta;
static struct metadata *cell(a_uint32_t d,a_uint32_t p)
{CHECK(d<SW_MAX_NR_DEV && p<SW_MAX_NR_PORT,"SETTER_BOUNDS_SAFE");return &meta[d][p];}
#define SETTER(name,field,type,label) \
static void name(a_uint32_t d,a_uint32_t p,type v) {cell(d,p)->field=v;event("SET %s %u %u %u\n",label,d,p,(unsigned)v);}
SETTER(hsl_phy_address_init,address,a_uint32_t,"ADDRESS")
SETTER(hsl_port_phy_reset_gpio_set,reset,a_uint32_t,"RESET")
SETTER(hsl_port_force_speed_set,speed,a_uint32_t,"SPEED")
SETTER(hsl_port_force_duplex_set,duplex,a_uint8_t,"DUPLEX")
SETTER(qca_ssdk_phy_mdio_fake_address_set,fake,a_uint32_t,"FAKE")
static void hsl_port_phy_access_type_set(a_uint32_t d,a_uint32_t p,a_uint8_t v)
{
    struct metadata *m=cell(d,p);m->access=v;
    m->features=v==PHY_I2C_ACCESS ? m->features|PHY_F_I2C : m->features&~PHY_F_I2C;
    event("SET ACCESS %u %u %u\n",d,p,v);
}
#define CAPABILITY(name,field,bit,label) \
static void name(a_uint32_t d,a_uint32_t p,a_bool_t v) {struct metadata *m=cell(d,p);m->field=v; \
    m->features=v?m->features|(bit):m->features&~(bit);event("SET %s %u %u %d\n",label,d,p,v);}
CAPABILITY(hsl_port_phy_c45_capability_set,c45,PHY_F_CLAUSE45,"C45")
CAPABILITY(hsl_port_phy_combo_capability_set,combo,PHY_F_COMBO,"COMBO")
static void hsl_port_phy_dac_set(a_uint32_t d,a_uint32_t p,phy_dac_t v)
{cell(d,p)->dac=v;event("SET DAC %u %u %u %u\n",d,p,v.mdac,v.edac);}
static sw_error_t hsl_port_feature_set(a_uint32_t d,a_uint32_t p,phy_features_t v)
{cell(d,p)->features|=v;event("SET FEATURE %u %u %u\n",d,p,(unsigned)v);return SW_OK;}
static sw_error_t sfp_phy_init(a_uint32_t d,a_uint32_t p,a_uint32_t index)
{cell(d,p);event("SFP %u %u %u\n",d,p,index);return SW_OK;}
typedef struct {a_uint32_t device_id;struct device_node *of_node; a_uint8_t *reg_access_mode; hsl_reg_mode switch_reg_access_mode,psgmii_reg_access_mode; a_uint32_t switchreg_base_addr,switchreg_size,pcie_hw_base;} ssdk_dt_cfg;
static struct {a_uint32_t num_devices;ssdk_dt_cfg **ssdk_dt_switch_nodes;} ssdk_dt_global;
/* @PRIVATE@ */
static struct ssdk_dt_admitted_node ssdk_dt_admitted[SW_MAX_NR_DEV];
struct block {void *ptr;size_t count,size;int live,kind;};
static struct block blocks[4];
static int allocations;
static void *alloc(size_t count,size_t size,int kind)
{
    CHECK(expected_pure==0,"PREFLIGHT_BEFORE_ALLOC");
    CHECK(allocations<4,"ALLOC_LIMIT");
    int index=allocations++,ok=allocations!=input->fault;
    event("ALLOC %d %d %zu %d\n",index+1,kind,count,ok);
    if(!ok)return NULL;
    void *p=calloc(count?count:1,size);CHECK(p!=NULL,"HOST_ALLOC");
    blocks[index]=(struct block){p,count,size,1,kind};return p;
}
static void *kcalloc(size_t n,size_t s,int flags) {CHECK(flags==0,"ALLOC_FLAGS");return alloc(n,s,0);}
static void *kzalloc(size_t s,int flags) {CHECK(flags==0,"ALLOC_FLAGS");return alloc(1,s,1);}
static void kfree(void *p)
{
    if(!p)return;
    for(int i=0;i<4;i++)if(blocks[i].ptr==p) {CHECK(blocks[i].live,"FREE_ONCE");blocks[i].live=0;event("FREE %d\n",i+1);free(p);return;}
    fail("FREE_OWNED_ONLY");
}
/* @FUNCTIONS@ */
/* @BASELINE@ */
static void init_nodes(void)
{
    instance=(struct device_node){1,0,0,0,2,"ess-instance"};
    foreign_node=(struct device_node){999,5,0,0,7,"foreign"};
    for(int s=0;s<3;s++) {
        sw[s]=(struct device_node){100+s,1,s,0,2,"switch"};
        container[s]=(struct device_node){200+s,2,s,0,2,"qcom,port_phyinfo"};
        for(int p=0;p<4;p++) {
            ports[s][p]=(struct device_node){300+s*4+p,3,s,p,2,"port"};
            external[s][p]=(struct device_node){400+s*4+p,4,s,p,2,"switch_external"};
        }
    }
}
static void node_end(void)
{
    CHECK(instance.refs==2 && foreign_node.refs>=7,"FOREIGN_INSTANCE_REFS");
    for(int s=0;s<3;s++) {
        CHECK(sw[s].refs==2 && container[s].refs==2,"LOCAL_CONTAINER_REFS");
        for(int p=0;p<4;p++)CHECK(ports[s][p].refs==2,"LOCAL_CHILD_REFS");
        /* External references are deliberately outside this local retirement contract. */
    }
}
static void topology_shape(void)
{
    CHECK(ssdk_dt_global.ssdk_dt_switch_nodes==blocks[0].ptr && blocks[0].live &&
          blocks[0].kind==0 && blocks[0].count==(size_t)input->count &&
          blocks[0].size==sizeof(ssdk_dt_cfg*) && ssdk_dt_global.num_devices==(a_uint32_t)input->count,
          "VECTOR_OWNER_SHAPE");
    unsigned seen=0;
    for(int d=0;d<input->count;d++) {
        CHECK(blocks[d+1].live && blocks[d+1].kind==1 && blocks[d+1].count==1 &&
              blocks[d+1].size==sizeof(ssdk_dt_cfg) && ssdk_dt_global.ssdk_dt_switch_nodes[d]==blocks[d+1].ptr,
              "SLOT_OWNER_SHAPE");
        CHECK(!(seen&(1u<<(d+1))),"SLOT_UNIQUENESS"); seen|=1u<<(d+1);
        ssdk_dt_cfg *c=ssdk_dt_global.ssdk_dt_switch_nodes[d];
        int s=-1;
        for(int i=0;i<input->count;i++)if(input->switches[i].enabled && input->switches[i].id==(a_uint32_t)d)s=i;
        CHECK(c->of_node==(s<0?NULL:&sw[s]),"TOPOLOGY_NODE_IDENTITY");
        event("CFG %d %d %u %u %u %u\n",d,s,c->device_id,c->switchreg_base_addr,c->switchreg_size,c->pcie_hw_base);
    }
    CHECK(seen==((1u<<(input->count+1))-2),"SLOT_CLOSURE");
}
static void dump_state(ssdk_init_cfg *cfg)
{
    event("OPEN_MDIO_HELD %d\n",foreign_node.refs-7);
    for(int s=0;s<3;s++)for(int p=0;p<4;p++)event("OPEN_EXTERNAL_HELD %d %d\n",external[s][p].ident,external[s][p].refs-2);
    event("EXTERNAL_STATE %u %d %u %u\n",ext_state.switch_netdev_port,ext_state.switch_connected,ext_state.switch_dev_id,ext_state.switch_cpu_port);
    event("BITMAP %u %u\n",cfg->port_cfg.wan_bmp,cfg->port_cfg.lan_bmp);
    for(unsigned d=0;d<SW_MAX_NR_DEV;d++)for(unsigned p=0;p<SW_MAX_NR_PORT;p++) {
        struct metadata *m=&meta[d][p];struct qca_phy_priv *q=&private_data[d];
        event("STATE %u %u %u %u %u %u %u %u %u %u %d %d %u %u %u %u %u\n",d,p,
              m->address,m->reset,m->speed,m->fake,m->access,m->duplex,m->dac.mdac,m->dac.edac,
              m->c45,m->combo,(unsigned)m->features,q->sfp_rx_los_pin[p],q->sfp_tx_dis_pin[p],q->sfp_mod_present_pin[p],q->sfp_medium_pin[p]);
    }
}
int main(int argc,char **argv)
{
    CHECK(argc==5,"ARGUMENTS");int i=atoi(argv[1]);
    CHECK(i>=0 && (size_t)i<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");
    input=&inputs[i];expected_ret=atoi(argv[2]);expected_pure=atoi(argv[3]);
    init_nodes(); memset(meta,0xa5,sizeof(meta));memset(private_data,0xa5,sizeof(private_data));
    memset(&foreign_meta,0x3c,sizeof(foreign_meta));struct metadata foreign_copy=foreign_meta;
    ssdk_init_cfg cfg={0};
    for(int repeat=0;repeat<input->repeats;repeat++) {
        event("BEGIN %s %d\n",input->flow,repeat);int ret=0;
        if(!strcmp(input->flow,"reader")) {
            struct ssdk_dt_port_values out;memset(&out,0x6b,sizeof(out));
            struct ssdk_dt_port_values old;memcpy(&old,&out,sizeof(old));
            ret=ssdk_dt_read_port_values(&ports[0][0],&out);
            CHECK(ret==expected_ret,"READER_RETURN");
            if(ret)CHECK(!memcmp(&out,&old,sizeof(out)),"OUTPUT_ATOMIC");
            event("OUTPUT %d %u %d %u %u\n",ret,out.id,out.has_dac,out.dac.mdac,out.dac.edac);
        } else if(!strcmp(input->flow,"validate")) {
            ret=ssdk_dt_validate_phy_ports(&sw[0]);CHECK(ret==expected_ret,"VALIDATE_RETURN");
        } else if(!strcmp(input->flow,"prepare")) {
            struct ssdk_dt_prepared_node prepared[SW_MAX_NR_DEV]={0};
            ret=ssdk_dt_prepare_nodes(prepared,(a_uint32_t)input->count);
            CHECK(ret==expected_ret,"PREPARE_RETURN");
            for(int s=0;s<input->count;s++)of_node_put(prepared[s].node);
        } else if(!strcmp(input->flow,"topology")) {
            allocations=0;memset(blocks,0,sizeof(blocks));
            ssdk_dt_cfg *foreign_vector[1]={NULL};
            if(input->foreign) {ssdk_dt_global.ssdk_dt_switch_nodes=foreign_vector;ssdk_dt_global.num_devices=1;}
            ret=ssdk_switch_device_num_init();CHECK(ret==expected_ret,"TOPOLOGY_RETURN");
            if(!ret) {topology_shape();ssdk_switch_device_num_exit();ssdk_switch_device_num_exit();}
            if(input->foreign) {
                CHECK(ssdk_dt_global.ssdk_dt_switch_nodes==foreign_vector && ssdk_dt_global.num_devices==1 &&
                      foreign_vector[0]==NULL && allocations==0,"FOREIGN_TOPOLOGY");
                ssdk_dt_global.ssdk_dt_switch_nodes=NULL;ssdk_dt_global.num_devices=0;
            }
            CHECK(!ssdk_dt_global.num_devices && !ssdk_dt_global.ssdk_dt_switch_nodes,"TOPOLOGY_EMPTY");
            for(int b=0;b<4;b++)CHECK(!blocks[b].live,"ALLOCATION_LEDGER");
        } else if(!strcmp(input->flow,"parse") || !strcmp(input->flow,"oldparse")) {
            /* Leaf allocation chooses current child by its live iterator reference. */
            ret=!strcmp(input->flow,"parse") ? ssdk_dt_parse_phy_info(&sw[0],input->switches[0].id,&cfg) :
                baseline_parse_phy(&sw[0],input->switches[0].id,&cfg);
            CHECK(ret==expected_ret,"PARSE_RETURN");
        } else fail("FLOW");
        event("RETURN %d\n",ret);node_end();
    }
    CHECK(!memcmp(&foreign_meta,&foreign_copy,sizeof(foreign_meta)),"FOREIGN_METADATA");
    dump_state(&cfg);event("END CLEAN\n");
    FILE *f=fopen(argv[4],"rb");CHECK(f!=NULL,"EXPECTED_OPEN");
    char expected[sizeof(trace)];size_t n=fread(expected,1,sizeof(expected),f);
    CHECK(!ferror(f) && feof(f),"EXPECTED_EXTENT");CHECK(fclose(f)==0,"EXPECTED_CLOSE");
    CHECK(n==used && !memcmp(expected,trace,used),"EXACT_MODEL_TRACE");
    CHECK(fwrite(trace,1,used,stdout)==used,"STDOUT_WRITE");return 0;
}
