/* Reduced OF/DTcfg/private/service models, not Linux or public structure ABI. */
#include <arpa/inet.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
typedef uint8_t a_uint8_t;
typedef uint32_t a_uint32_t;
typedef uint32_t __be32;
/* @TYPES@ */
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#ifdef TEST_OLD_VERSION
#define LINUX_VERSION_CODE KERNEL_VERSION(3,13,0)
#else
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
#endif
#if defined(CONFIG_OF) && LINUX_VERSION_CODE >= KERNEL_VERSION(3,14,0)
#define DT_NATIVE 1
#else
#define DT_NATIVE 0
#endif
#define HPPE 1
#define IN_UNIPHY 1
#define IN_QOS 1
#define IN_LED 1
#define IN_NETLINK 1
#define __init
#define GFP_KERNEL 0
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define SSDK_STR "ssdk"
#define PPE_STR "PPE"
/* @MACRO@ */
struct props {
    int id_len, id_error;
    a_uint32_t id;
    const char *mode;
    int mode_error, reg_len, reg_error;
    a_uint32_t reg[3];
    __be32 reg_be[3], id_be;
    bool emulation;
    const char *compatible;
};
struct device_node { int index, refs; const char *name; bool present, enabled; struct props *properties; };
struct property { int unused; };
typedef struct {
    a_uint32_t device_id;
    struct device_node *of_node;
    a_uint8_t *reg_access_mode;
    hsl_reg_mode switch_reg_access_mode, psgmii_reg_access_mode;
    a_uint32_t switchreg_base_addr, switchreg_size, pcie_hw_base;
    void *ess_clk, *cmnblk_clk;
    a_bool_t is_emulation;
    a_uint32_t emu_chip_ver, tm_tick_mode, bm_tick_mode;
    unsigned char unrelated[19];
} ssdk_dt_cfg;
typedef struct { a_uint32_t num_devices; ssdk_dt_cfg **ssdk_dt_switch_nodes; unsigned char unrelated[13]; } ssdk_dt_global_t;
/* Exact three small private structs, not the large actual DTcfg. */
/* @PRIVATE@ */
static ssdk_dt_global_t ssdk_dt_global;
static struct ssdk_dt_admitted_node ssdk_dt_admitted[SW_MAX_NR_DEV];
typedef struct { ssdk_chip_type chip_type; } ssdk_init_cfg;
struct qca_phy_priv { a_uint32_t device_id, ports; struct device_node *of_node; };
static struct qca_phy_priv **qca_phy_priv_global;
struct node_input { int present, enabled, id_len; a_uint32_t id; int id_error; const char *mode; int mode_error, reg_len, reg_error, emulation; const char *compatible; };
struct input {
    const char *name, *flow;
    int instance, count_len; a_uint32_t declared;
    int count_error, fault, foreign, mutate, arg, private_error;
    struct node_input nodes[SW_MAX_NR_DEV];
};
#include "@CASES_PATH@"
static const struct input *input;
static int expected_return, admission_return;
static a_uint32_t effective;
static struct device_node instance, nodes[SW_MAX_NR_DEV];
#if DT_NATIVE
static struct device_node foreign_node;
#endif
static struct props original[SW_MAX_NR_DEV], replacement[SW_MAX_NR_DEV];
static struct props original_snapshot[SW_MAX_NR_DEV];
static struct property property;
static ssdk_dt_cfg foreign_cfg, foreign_cfg_copy;
static ssdk_dt_cfg *foreign_vector[1] = { &foreign_cfg };
static ssdk_dt_global_t foreign_global_copy;
static struct ssdk_dt_admitted_node foreign_map_copy[SW_MAX_NR_DEV];
static char events[512][180];
static unsigned event_count, attempts, root_boundary, private_calls;
static unsigned access_seen[SW_MAX_NR_DEV];
static unsigned char clock_tokens[SW_MAX_NR_DEV];
static bool parsing, reference_mode, unsafe_old, exiting;
static struct device_node *current_parser;
static ssdk_init_cfg *current_cfg;
static jmp_buf root_jump;
struct block { void *ptr; bool live, vector; size_t count, bytes; };
static struct block blocks[16];

static _Noreturn void fail(const char *marker)
{ fprintf(stderr, "SSDK_DT %s\n", marker); exit(86); }
static void check(bool ok, const char *marker) { if (!ok) fail(marker); }
static void event(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void event(const char *fmt, ...)
{
    if (reference_mode) return;
    check(event_count < 512, "EVENT_CAPACITY");
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(events[event_count], sizeof(events[0]), fmt, ap); va_end(ap);
    check(n > 0 && (size_t)n < sizeof(events[0]), "EVENT_LENGTH"); ++event_count;
}
static int node_index(struct device_node *node)
{
    for (unsigned i = 0; i < SW_MAX_NR_DEV; ++i) if (node == &nodes[i]) return (int)i;
    fail("FOREIGN_NODE");
}
static void foreign_unchanged(void)
{
    if (!input->foreign) return;
    check(memcmp(&ssdk_dt_global, &foreign_global_copy, sizeof(ssdk_dt_global)) == 0 &&
          memcmp(&foreign_cfg, &foreign_cfg_copy, sizeof(foreign_cfg)) == 0 &&
          foreign_vector[0] == &foreign_cfg &&
          memcmp(ssdk_dt_admitted, foreign_map_copy, sizeof(ssdk_dt_admitted)) == 0, "FOREIGN_OWNER");
}
static void of_node_put(struct device_node *node)
{
    if (!node) return;
    check(node->refs > 0, "OF_DOUBLE_PUT");
    --node->refs;
    if (node == &instance) event("PUT I\n");
    else event("PUT N %d\n", node_index(node));
}
static struct device_node *of_node_get(struct device_node *node)
{
    check(node!=NULL,"OF_GET_ARGUMENT");++node->refs;
    event("GET N %d\n",node_index(node));return node;
}
static struct device_node *of_find_node_by_name(struct device_node *from, const char *name)
{
#ifndef CONFIG_OF
    (void)from;(void)name;event("OF_STUB NULL\n");return NULL;
#else
    check(!parsing, "PARSE_SECOND_LOOKUP");
    if (!strcmp(name, "ess-instance")) {
        check(from == NULL, "OF_FROM_ARGUMENT"); event("FIND I %d\n", input->instance);
        if (!input->instance) return NULL;
        ++instance.refs; return &instance;
    }
    unsigned n = 0;
    if (strcmp(name, "ess-switch")) {
        int consumed = 0;
        check(sscanf(name, "ess-switch%u%n", &n, &consumed) == 1 && name[consumed] == '\0', "OF_NAME_ARGUMENT");
    }
    check(from == (input->instance ? &instance : NULL), "OF_FROM_ARGUMENT");
    bool present = n < SW_MAX_NR_DEV && nodes[n].present;
    event("FIND N %u %u\n", n, (unsigned)present);
    struct device_node *result = present ? &nodes[n] : NULL;
    if (result) ++result->refs;
    /* Actual of_find_node_by_name consumes from even on not-found. */
    of_node_put(from);
    return result;
#endif
}
static bool of_device_is_available(struct device_node *node)
{
    int i = node_index(node); event("AVAILABLE %d %u\n", i, (unsigned)node->enabled); return node->enabled;
}
static struct property *of_find_property(struct device_node *node, const char *name, int *len)
{
    check(!parsing, "PARSE_ID_REREAD");
    int length;
    if (node == &instance) { check(!strcmp(name, "num_devices"), "COUNT_PROPERTY_ARGUMENT"); length = input->count_len; event("PROP I %d\n", length); }
    else { int i = node_index(node); check(!strcmp(name, "device_id"), "ID_PROPERTY_ARGUMENT"); length = node->properties->id_len; event("PROP N %d %d\n", i, length); }
    if (length < 0) return NULL;
    if (len) *len = length;
    return &property;
}
static int typed_error(int length, unsigned need, int error)
{ return error ? error : length < 0 ? -EINVAL : length == 0 ? -ENODATA : (unsigned)length < need * sizeof(a_uint32_t) ? -EOVERFLOW : 0; }
static int of_property_read_u32(struct device_node *node, const char *name, a_uint32_t *out)
{
    check(out != NULL, "TYPED_OUTPUT");
    if (node == &instance) {
        check(!parsing && !strcmp(name, "num_devices"), "COUNT_READ_ARGUMENT");
        int ret = typed_error(input->count_len, 1, input->count_error);
        if (!ret) *out = input->declared;
        event("READ I %d %u\n", ret, ret ? 0u : input->declared); return ret;
    }
    int i = node_index(node);
    if (!strcmp(name, "device_id")) {
        check(!parsing, "PARSE_ID_REREAD");
        int ret = typed_error(node->properties->id_len, 1, node->properties->id_error);
        if (!ret) *out = node->properties->id;
        event("READ N %d %d %u\n", i, ret, ret ? 0u : node->properties->id); return ret;
    }
    check(parsing && node == current_parser &&
          (!strcmp(name, "tm_tick_mode") || !strcmp(name, "bm_tick_mode")), "TICK_ARGUMENT");
    *out = !strcmp(name, "tm_tick_mode") ? (a_uint32_t)(31 + i) : (a_uint32_t)(41 + i);
    event("TICK %d %s %u\n", i, name, *out); return 0;
}
static int of_property_read_string(struct device_node *node, const char *name, const char **out)
{
    check(!parsing && !strcmp(name, "switch_access_mode") && out != NULL, "PARSE_ACCESS_REREAD");
    int i = node_index(node), ret = node->properties->mode_error;
    if (!ret && !node->properties->mode) ret = -EINVAL;
    if (!ret) *out = node->properties->mode;
    event("STRING %d %d\n", i, ret);
    if (!ret && strcmp(*out, "local bus") && strcmp(*out, "pcie bus")) ++access_seen[i];
    return ret;
}
static int of_property_read_u32_array(struct device_node *node, const char *name, a_uint32_t *out, size_t n)
{
    int i = node_index(node);
    check(!parsing && !strcmp(name, "reg") && out && (n == 1 || n == 2), "PARSE_REG_REREAD");
    int ret = typed_error(node->properties->reg_len, (unsigned)n, node->properties->reg_error);
    if (!ret) { for (size_t j = 0; j < n; ++j) out[j] = node->properties->reg[j]; ++access_seen[i]; }
    event("ARRAY %d %zu %d\n", i, n, ret);
    return ret; /* of_property_read_u32_array wrapper returns0, not positive count. */
}
static const void *of_get_property(struct device_node *node, const char *name, void *len_out)
{
    if (!strcmp(name, "device_id")) fail(unsafe_old ? "OLD_RAW_ID_GUARD" : "PARSE_RAW_ID");
    check(reference_mode && !strcmp(name, "reg"), "UNEXPECTED_RAW_PROPERTY");
    if (len_out) *(a_uint32_t *)len_out = (a_uint32_t)node->properties->reg_len;
    return node->properties->reg_be;
}
static a_uint32_t be32_to_cpup(const __be32 *p)
{
    check(reference_mode, "UNSAFE_RAW_READ");
    for (unsigned i = 0; i < SW_MAX_NR_DEV; ++i) for (unsigned j = 0; j < 3; ++j)
        if (p == &original[i].reg_be[j]) {
            check(original[i].reg_len >= (int)((j + 1) * sizeof(*p)), "OLD_REG_EXTENT"); return ntohl(*p);
        }
    fail("OLD_REG_OWNER");
}
static bool of_property_read_bool(struct device_node *node, const char *name)
{ check(parsing && node == current_parser && !strcmp(name, "qcom,emulation"), "BOOL_ARGUMENT"); bool b = node->properties->emulation; event("BOOL %d %u\n", node_index(node), (unsigned)b); return b; }
static bool of_device_is_compatible(struct device_node *node, const char *name)
{ check(parsing && node == current_parser, "COMPAT_ARGUMENT"); return !strcmp(node->properties->compatible, name); }
static void *of_clk_get_by_name(struct device_node *node, const char *name)
{ check(parsing && node == current_parser && !strcmp(name, "cmn_ahb_clk"), "CLOCK_ARGUMENT"); int n=node_index(node);event("CLOCK %d\n",n);return &clock_tokens[n]; }
static const char *mode_name(hsl_reg_mode mode)
{ if (mode == HSL_REG_MDIO) return "mdio"; if (mode == HSL_REG_LOCAL_BUS) return "local"; if (mode == HSL_REG_PCIE_BUS) return "pcie"; fail("MODE_DOMAIN"); }
static void expected_access(ssdk_dt_cfg *cfg, unsigned ordinal)
{
    const struct props *p = &original[ordinal];
    cfg->reg_access_mode = (a_uint8_t *)p->mode;
    cfg->switch_reg_access_mode = HSL_REG_MDIO;
    if (!strcmp(p->mode, "local bus")) { cfg->switch_reg_access_mode = HSL_REG_LOCAL_BUS; cfg->switchreg_base_addr = p->reg[0]; cfg->switchreg_size = p->reg[1]; }
    else if (!strcmp(p->mode, "pcie bus")) { cfg->switch_reg_access_mode = HSL_REG_PCIE_BUS; cfg->pcie_hw_base = p->reg[0]; }
}
static void access_equal(const ssdk_dt_cfg *a, const ssdk_dt_cfg *b)
{ check(a->reg_access_mode == b->reg_access_mode && a->switch_reg_access_mode == b->switch_reg_access_mode && a->switchreg_base_addr == b->switchreg_base_addr && a->switchreg_size == b->switchreg_size && a->pcie_hw_base == b->pcie_hw_base, "ACCESS_VALUES"); }
static void leaf(a_uint32_t id, struct device_node *node, ssdk_init_cfg *cfg, const char *name)
{
    check(parsing && node == current_parser && (!cfg || cfg == current_cfg) && id < effective && id < SW_MAX_NR_DEV, "LEAF_ARGUMENT");
    unsigned ordinal = (unsigned)node_index(node);
    a_uint32_t wanted = original[ordinal].id_len < 0 ? 0 : original[ordinal].id;
    check(id == wanted && ssdk_dt_global.ssdk_dt_switch_nodes[id]->of_node == node && node->refs == 1, "LEAF_ID_NODE_OWNER");
    ssdk_dt_cfg wanted_cfg; memset(&wanted_cfg, 0, sizeof(wanted_cfg)); expected_access(&wanted_cfg, ordinal);
    access_equal(ssdk_dt_global.ssdk_dt_switch_nodes[id], &wanted_cfg);
    event("LEAF %s %u %u\n", name, ordinal, id);
}
static void ssdk_dt_parse_mac_mode(a_uint32_t id, struct device_node *n, ssdk_init_cfg *c) { leaf(id,n,c,"MAC"); }
static void ssdk_dt_parse_mdio(a_uint32_t id, struct device_node *n, ssdk_init_cfg *c) { leaf(id,n,c,"MDIO"); }
static void ssdk_dt_parse_port_bmp(a_uint32_t id, struct device_node *n, ssdk_init_cfg *c) { leaf(id,n,c,"BMP"); }
static sw_error_t ssdk_dt_parse_interrupt(a_uint32_t id, struct device_node *n) { leaf(id,n,NULL,"IRQ"); return SW_OK; }
static void ssdk_dt_parse_led(a_uint32_t id, struct device_node *n) { leaf(id,n,NULL,"LED"); }
static void ssdk_dt_parse_uniphy(a_uint32_t id) { leaf(id,current_parser,NULL,"UNIPHY"); }
static void ssdk_dt_parse_scheduler_cfg(a_uint32_t id, struct device_node *n) { leaf(id,n,NULL,"SCHED"); }
static void ssdk_dt_parse_intf_mac(void)
{ check(parsing && current_parser, "INTF_ARGUMENT"); event("LEAF INTF %d\n", node_index(current_parser)); }
static void model_log(const char *fmt, ...) __attribute__((format(printf,1,2)));
static void model_log(const char *fmt, ...)
{
    char text[160]; va_list ap; va_start(ap,fmt); int n=vsnprintf(text,sizeof(text),fmt,ap); va_end(ap);
    check(n > 0 && (size_t)n < sizeof(text), "LOG_FORMAT"); if (reference_mode) return;
    if (strstr(text,"cannot find")) event("WARN MISSING\n");
    else if (strstr(text,"is disabled")) event("WARN DISABLED\n");
    else if (strstr(text,"RUMI")) event("LOG EMULATION\n");
    else if (strstr(text,"PCIE bus")) event("LOG PCIE\n");
    else if (strstr(text,"invalid compatible")) event("WARN COMPAT\n");
    else if (strstr(text,"qca83xx")) event("LOG QCA83\n");
    else fail("UNEXPECTED_LOG");
}
#define SSDK_INFO(...) model_log(__VA_ARGS__)
#define SSDK_WARN(...) model_log(__VA_ARGS__)
#define SSDK_ERROR(...) model_log(__VA_ARGS__)
#define SW_RTN_ON_ERROR(r) do { if ((r) != SW_OK) return (r); } while (0)
static void *allocate(size_t n, size_t bytes, bool vector)
{
    foreign_unchanged();
    check(!ssdk_dt_global.ssdk_dt_switch_nodes && !ssdk_dt_global.num_devices, "PREMATURE_GLOBAL");
    if (DT_NATIVE) {
        check(admission_return == 0, "PREFLIGHT_BEFORE_ALLOC");
        for (unsigned i=0;i<effective;++i) if (nodes[i].enabled && nodes[i].present)
            check(access_seen[i] == 1, "ALL_NODES_BEFORE_ALLOC");
        struct ssdk_dt_admitted_node zero[SW_MAX_NR_DEV] = {0};
        check(memcmp(ssdk_dt_admitted,zero,sizeof(zero))==0, "PREMATURE_MAP");
    }
    check(attempts < 16 && (!bytes || n <= SIZE_MAX/bytes), "ALLOC_DOMAIN");
    check(vector ? n == effective && bytes == sizeof(ssdk_dt_cfg *) : n == 1 && bytes == sizeof(ssdk_dt_cfg), "ALLOC_SHAPE");
    ++attempts; bool ok = attempts != (unsigned)input->fault;
    event("ALLOC %u %c %u\n",attempts,vector?'V':'C',(unsigned)ok); if(!ok)return NULL;
    size_t total=n*bytes; void *p=calloc(1,total?total:1); check(p!=NULL,"HOST_ALLOC");
    blocks[attempts-1]=(struct block){.ptr=p,.live=true,.vector=vector,.count=n,.bytes=bytes};return p;
}
static void *kcalloc(size_t n,size_t bytes,int flags) { check(flags==GFP_KERNEL,"ALLOC_FLAGS");return allocate(n,bytes,true); }
static void *kzalloc(size_t bytes,int flags) { check(flags==GFP_KERNEL,"ALLOC_FLAGS");return allocate(1,bytes,false); }
static void kfree(void *p)
{
    if(!p)return;
    foreign_unchanged();
    for(unsigned i=0;i<attempts;++i)if(blocks[i].ptr==p){check(blocks[i].live,"DOUBLE_FREE");blocks[i].live=false;event("FREE %u\n",i+1);free(p);return;}
    fail("FOREIGN_FREE");
}
/* @FUNCTIONS@ */
static int legacy_string_compare(const void *a,const void *b) { return strcmp(a,b); }
/* @REFERENCE@ */
static _Noreturn void late(void) { fail("ROOT_LATE_RESOURCE"); }
static int ssdk_alloc_priv(a_uint32_t n) { check(n==effective,"PRIVATE_COUNT"); ++private_calls; event("PRIVATE %u %d\n",n,input->private_error); return input->private_error; }
static void ssdk_free_priv(void) { fail("GLOBAL_CLEANUP"); }
static void ssdk_cfg_default_init(ssdk_init_cfg *c) { c->chip_type=CHIP_UNSPECIFIED;event("CFG LEAF\n"); }
static sw_error_t root_dt_boundary(ssdk_init_cfg *c,a_uint32_t n,a_uint32_t *id) { (void)c;check(n==0&&id,"ROOT_BOUNDARY_ARGUMENT");root_boundary=1;event("STOP DT\n");longjmp(root_jump,1); }
static a_uint32_t ssdk_device_id_get(a_uint32_t id) { (void)id;late(); }
static struct device_node *ssdk_dts_node_get(a_uint32_t id) { (void)id;late(); }
static int ssdk_plat_init(ssdk_init_cfg *c,a_uint32_t id) { (void)c;(void)id;late(); }
static void ssdk_driver_register(a_uint32_t id) { (void)id;late(); }
static int chip_ver_get(a_uint32_t id,ssdk_init_cfg *c) { (void)c;(void)id;late(); }
static int ssdk_init(a_uint32_t id,ssdk_init_cfg *c) { (void)c;(void)id;late(); }
static void qca_hppe_hw_init(a_uint32_t id) { (void)id;late(); }
static int ssdk_switch_register(a_uint32_t id,ssdk_chip_type chip) { (void)id;(void)chip;late(); }
static void ssdk_sysfs_init(void) { check(effective==0,"ROOT_ZERO_BOUNDARY");root_boundary=2;event("STOP ZERO_SYSFS\n");longjmp(root_jump,1); }
static void ssdk_genl_init(void) { late(); }
static void ssdk_netdev_notifier_register(void) { late(); }
#define ssdk_dt_parse root_dt_boundary
/* @ROOT@ */
#undef ssdk_dt_parse

static void refs_zero(void)
{ check(instance.refs==0,"INSTANCE_REF");for(unsigned i=0;i<SW_MAX_NR_DEV;++i)check(nodes[i].refs==0,"NODE_REF_LEDGER"); }
static void memory_zero(void)
{ for(unsigned i=0;i<attempts;++i)check(!blocks[i].live,"MEMORY_LEDGER"); }
static void retired(void)
{
    check(!ssdk_dt_global.ssdk_dt_switch_nodes && ssdk_dt_global.num_devices==0,"TOPOLOGY_RETIRED");
#if DT_NATIVE
    struct ssdk_dt_admitted_node zero[SW_MAX_NR_DEV]={0};check(memcmp(ssdk_dt_admitted,zero,sizeof(zero))==0,"MAP_RETIRED");
#endif
    refs_zero();memory_zero();
}
static void inspect_topology(void)
{
    /* MODEL_OWNER_SHAPE_INJECTION */
    check(ssdk_switch_device_num_get()==effective,"TOPOLOGY_PUBLISHED");
    /* Validate the vector itself before even indexing it. */
    check(attempts==effective+1 && blocks[0].live && blocks[0].vector &&
          blocks[0].count==effective && blocks[0].bytes==sizeof(ssdk_dt_cfg *) &&
          ssdk_dt_global.ssdk_dt_switch_nodes==blocks[0].ptr,"VECTOR_IDENTITY_SHAPE");
    unsigned live=0;for(unsigned i=0;i<attempts;++i)live+=blocks[i].live;
    check(live==effective+1,"TOPOLOGY_OWNER_LEDGER");
    bool seen[16]={0};seen[0]=true;
    for(unsigned d=0;d<effective;++d){
        struct block *owner=&blocks[d+1];
        check(owner->live && !owner->vector && owner->count==1 && owner->bytes==sizeof(ssdk_dt_cfg) &&
              ssdk_dt_global.ssdk_dt_switch_nodes[d]==owner->ptr,"SLOT_IDENTITY_SHAPE");
        check(!seen[d+1],"SLOT_OWNER_DUPLICATE");seen[d+1]=true;
        for(unsigned p=0;p<d;++p)
            check(ssdk_dt_global.ssdk_dt_switch_nodes[p]!=ssdk_dt_global.ssdk_dt_switch_nodes[d],"SLOT_OWNER_DUPLICATE");
    }
    for(unsigned i=0;i<attempts;++i)check(seen[i]==blocks[i].live,"OWNER_SEEN_CLOSURE");
    /* All owner/extent checks have completed before any cfg payload read. */
    for(unsigned d=0;d<effective;++d){
        ssdk_dt_cfg expected;memset(&expected,0,sizeof(expected));expected.switch_reg_access_mode=HSL_REG_MDIO;expected.psgmii_reg_access_mode=HSL_REG_MDIO;
        int ordinal=-1;
#if DT_NATIVE
        for(unsigned n=0;n<effective;++n)if(nodes[n].enabled&&((original[n].id_len<0?0:original[n].id)==d)){
            ordinal=(int)n;expected.device_id=d;expected.of_node=&nodes[n];expected_access(&expected,n);
        }
#endif
        ssdk_dt_cfg *actual=ssdk_dt_global.ssdk_dt_switch_nodes[d];
        check(actual&&memcmp(actual,&expected,sizeof(expected))==0,"CFG_FULL_VALUE");
        event("CFG %u %d %s %u %u %u\n",d,ordinal,mode_name(actual->switch_reg_access_mode),actual->switchreg_base_addr,actual->switchreg_size,actual->pcie_hw_base);
    }
#if DT_NATIVE
    for(unsigned n=0;n<SW_MAX_NR_DEV;++n){
        bool enabled=n<effective&&nodes[n].enabled;
        a_uint32_t id=enabled?(original[n].id_len<0?0:original[n].id):0;
        check(ssdk_dt_admitted[n].enabled==(enabled?A_TRUE:A_FALSE)&&ssdk_dt_admitted[n].id==id,"ADMITTED_MAP");
        check(nodes[n].refs==(enabled?1:0),"ADOPTED_NODE_REF");
        event("MAP %u %u %u\n",n,(unsigned)enabled,id);
    }
#endif
    check(instance.refs==0,"INSTANCE_REF");
}
static void retire_model(void)
{ event("MODEL_RETIRE\n");exiting=true;ssdk_switch_device_num_exit();retired();event("EXIT AGAIN\n");ssdk_switch_device_num_exit();retired(); }
#if DT_NATIVE
static bool selected_hppe(const char *name)
{
    return !strcmp(name,"qcom,ess-switch-ipq807x")||!strcmp(name,"qcom,ess-switch-ipq95xx")||
           !strcmp(name,"qcom,ess-switch-ipq60xx")||!strcmp(name,"qcom,ess-switch-ipq53xx")||
           !strcmp(name,"qcom,ess-switch-ipq54xx");
}
static void parse_writeback(unsigned ordinal)
{
    a_uint32_t id=original[ordinal].id_len<0?0:original[ordinal].id;
    check(id<effective && ssdk_dt_global.ssdk_dt_switch_nodes==blocks[0].ptr &&
          blocks[id+1].live && ssdk_dt_global.ssdk_dt_switch_nodes[id]==blocks[id+1].ptr,"PARSE_CFG_OWNER");
    ssdk_dt_cfg expected;memset(&expected,0,sizeof(expected));
    expected.device_id=id;expected.of_node=&nodes[ordinal];expected.psgmii_reg_access_mode=HSL_REG_MDIO;
    expected_access(&expected,ordinal);expected.ess_clk=ERR_PTR(-ENOENT);expected.cmnblk_clk=ERR_PTR(-ENOENT);
    bool hppe=selected_hppe(nodes[ordinal].properties->compatible);
    expected.is_emulation=nodes[ordinal].properties->emulation?A_TRUE:A_FALSE;
    if(hppe){expected.cmnblk_clk=&clock_tokens[ordinal];expected.tm_tick_mode=31+ordinal;expected.bm_tick_mode=41+ordinal;}
    ssdk_dt_cfg *actual=ssdk_dt_global.ssdk_dt_switch_nodes[id];
    check(memcmp(actual,&expected,sizeof(expected))==0,"PARSE_COMPLETE_WRITEBACK");
    event("STATE %u %u %u %u %s %u\n",ordinal,(unsigned)actual->is_emulation,
          actual->tm_tick_mode,actual->bm_tick_mode,hppe?"clock-token":"clock-error",actual->emu_chip_ver);
}
static void reference_projection(unsigned ordinal)
{
    ssdk_dt_cfg reference;memset(&reference,0,sizeof(reference));reference.switch_reg_access_mode=HSL_REG_MDIO;
    reference_mode=true;check(reference_access(&nodes[ordinal],&reference)==SW_OK,"REFERENCE_ACCESS");reference_mode=false;
    ssdk_dt_cfg expected;memset(&expected,0,sizeof(expected));expected_access(&expected,ordinal);access_equal(&reference,&expected);
    event("REFERENCE %u OK\n",ordinal);
}
static void parse_nodes(void)
{
    for(unsigned n=0;n<effective;++n)if(nodes[n].enabled)reference_projection(n);
    if(input->mutate){for(unsigned n=0;n<effective;++n)nodes[n].properties=&replacement[n];event("PROPERTIES REPLACED\n");}
    for(unsigned n=0;n<effective;++n){
        ssdk_init_cfg cfg={0};a_uint32_t id=1234;current_cfg=&cfg;current_parser=&nodes[n];parsing=true;
        sw_error_t ret=ssdk_dt_parse(&cfg,n,&id);parsing=false;
        a_uint32_t want=original[n].id_len<0?0:original[n].id;
        check(ret==(nodes[n].enabled?SW_OK:SW_DISABLE)&&id==(nodes[n].enabled?want:1234),"PARSE_RETURN_ID");
        check(nodes[n].refs==(nodes[n].enabled?1:0),"PARSE_BORROW_REF");
        if(nodes[n].enabled)parse_writeback(n);
        event("PARSE %u %d %u\n",n,ret,id);
    }
}
#endif
int main(int argc,char **argv)
{
    check(argc==4,"ARGS");unsigned row=(unsigned)strtoul(argv[1],NULL,10);check(row<sizeof(inputs)/sizeof(inputs[0]),"CASE_INDEX");
    input=&inputs[row];expected_return=(int)strtol(argv[2],NULL,10);admission_return=(int)strtol(argv[3],NULL,10);
    effective=input->instance&&input->count_len>=0?input->declared:1;
#ifndef CONFIG_OF
    effective=1;
#endif
    instance.index=-1;instance.present=input->instance!=0;
    static const char *const node_names[]={"ess-switch","ess-switch1","ess-switch2"};
    memset(ssdk_dt_global.unrelated,0x51,sizeof(ssdk_dt_global.unrelated));
    for(unsigned n=0;n<SW_MAX_NR_DEV;++n){
        const struct node_input *p=&input->nodes[n];nodes[n].index=(int)n;nodes[n].name=node_names[n];nodes[n].present=p->present!=0;nodes[n].enabled=p->enabled!=0;
        original[n]=(struct props){.id_len=p->id_len,.id_error=p->id_error,.id=p->id,.mode=p->mode,.mode_error=p->mode_error,.reg_len=p->reg_len,.reg_error=p->reg_error,.emulation=p->emulation!=0,.compatible=p->compatible};
        original[n].reg[0]=0xa100+n*0x100;original[n].reg[1]=0x1000+n*17;original[n].reg[2]=0xdead;
        for(unsigned j=0;j<3;++j)original[n].reg_be[j]=htonl(original[n].reg[j]);
        original[n].id_be=htonl(p->id);
        replacement[n]=original[n];replacement[n].id=UINT32_MAX;replacement[n].mode="pcie bus";replacement[n].reg[0]=0xbad0+n;replacement[n].emulation=true;
        nodes[n].properties=&original[n];
    }
    memcpy(original_snapshot,original,sizeof(original));
    if(input->foreign){memset(&foreign_cfg,0xa7,sizeof(foreign_cfg));memcpy(&foreign_cfg_copy,&foreign_cfg,sizeof(foreign_cfg));
        ssdk_dt_global.ssdk_dt_switch_nodes=input->foreign&1?foreign_vector:NULL;ssdk_dt_global.num_devices=input->foreign&2?1:0;
        memcpy(&foreign_global_copy,&ssdk_dt_global,sizeof(ssdk_dt_global));
        memset(ssdk_dt_admitted,0x17,sizeof(ssdk_dt_admitted));memcpy(foreign_map_copy,ssdk_dt_admitted,sizeof(ssdk_dt_admitted));}
    int ret=0;
#if DT_NATIVE
    if(!strcmp(input->flow,"lookup")){
        struct device_node *out=&foreign_node;
        ret=ssdk_dt_get_switch_node(input->arg?NULL:&out,input->declared);
        check(ret==expected_return,"LOOKUP_RETURN");
        check(input->arg||(!ret?(out==&nodes[input->declared]&&out->refs==1):out==NULL),"LOOKUP_OWNER_ESCAPE");
        event("LOOKUP %d\n",ret);if(!ret)of_node_put(out);
    }else if(!strcmp(input->flow,"id")){
        a_uint32_t id=1234;ret=ssdk_dt_read_device_id(&nodes[0],input->declared,&id);
        check(ret==expected_return&&id==(ret?1234:(original[0].id_len<0?0:original[0].id)),"ID_RETURN_VALUE");event("ID %d %u\n",ret,id);
    }else if(!strcmp(input->flow,"access")){
        struct ssdk_dt_access access;memset(&access,0,sizeof(access));ret=ssdk_dt_read_access_mode(&nodes[0],&access);
        check(ret==expected_return,"ACCESS_RETURN");
        if(!ret){ssdk_dt_cfg wanted;memset(&wanted,0,sizeof(wanted));expected_access(&wanted,0);check(access.name==original[0].mode&&access.mode==wanted.switch_reg_access_mode&&access.base==wanted.switchreg_base_addr&&access.size==wanted.switchreg_size&&access.pcie==wanted.pcie_hw_base,"ACCESS_VALUES");reference_projection(0);}
        else{struct ssdk_dt_access zero={0};check(memcmp(&access,&zero,sizeof(zero))==0,"ACCESS_FAILURE_WRITE");}event("ACCESS %d\n",ret);
    }else if(!strcmp(input->flow,"oldraw")){
        unsafe_old=true;ssdk_init_cfg cfg={0};a_uint32_t id=0;(void)old_parse(&cfg,0,&id);fail("OLD_GUARD_NOT_REACHED");
    }else
#endif
    {
        if(!strcmp(input->flow,"root")){if(setjmp(root_jump)==0)ret=regi_init();else ret=0;}
        else ret=ssdk_switch_device_num_init();
        check(ret==expected_return,"INIT_RETURN");event("INIT %d\n",ret);
        if(!strcmp(input->flow,"root"))
            check(private_calls==((admission_return==0&&!input->fault&&!input->foreign)?1u:0u),"ROOT_PRIVATE_COUNT");
        if(input->foreign){foreign_unchanged();refs_zero();memory_zero();}
        else if(!ret){
            inspect_topology();
            if(!strcmp(input->flow,"root"))check(private_calls==1&&root_boundary==(effective?1u:2u),"ROOT_BOUNDARY");
#if DT_NATIVE
            if(!strcmp(input->flow,"parse"))parse_nodes();
            if(!strcmp(input->flow,"parsebad")){
                ssdk_init_cfg cfg={0};a_uint32_t id=1234;
                sw_error_t p=ssdk_dt_parse(input->arg==1?NULL:&cfg,input->arg==3?effective:0,input->arg==2?NULL:&id);
                check(p==SW_BAD_PARAM&&id==1234,"PARSE_BAD_ARGUMENT");event("PARSE_BAD %d\n",p);
            }
#endif
            unsigned before_events=event_count;check(ssdk_switch_device_num_init()==-EBUSY&&event_count==before_events,"REENTRY_OWNER");event("REENTRY BUSY\n");retire_model();
        }else retired();
    }
    refs_zero();memory_zero();foreign_unchanged();
    check(memcmp(original,original_snapshot,sizeof(original))==0,"ORIGINAL_PROPERTY_CONTENT");
    for(unsigned i=0;i<sizeof(ssdk_dt_global.unrelated);++i)check(ssdk_dt_global.unrelated[i]==0x51,"GLOBAL_UNRELATED");
    event("END CLEAN\n");
    for(unsigned i=0;i<event_count;++i)fputs(events[i],stdout);
    return 0;
}
