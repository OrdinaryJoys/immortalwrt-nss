#include "model.h"
/* Only the scanner's memcmp leaf is range-instrumented. It fails before any
 * old underflow could access outside the declared firmware range. */
#define memcmp checked_memcmp
#include "actual-scan.c"
#undef memcmp
#include "actual-ppe.c"
/* Guard-removal witness: reject before a NULL copy or empty-name under-read.
 * This leaf instrumentation is not a target crash/UAF reproduction. */
static ssize_t checked_mirror_name_copy(char *dst,const char *src,size_t cap) {
    CHECK(src && *src,"MIRROR_EMPTY_NAME");
    return strscpy(dst,src,cap);
}
static size_t checked_mirror_index_length(const char *text) {
    CHECK(text && *text,"MIRROR_EMPTY_INDEX");
    return strlen(text);
}
#define sscanf model_kernel_sscanf
#define strscpy checked_mirror_name_copy
#define strlen checked_mirror_index_length
#include "actual-mirror.c"
#undef strlen
#undef strscpy
#include "actual-tunip.c"
#undef sscanf

static char storage[NSS_PPE_VP_MAX_CMD_STR];
static struct ctl_table ctl = {storage,sizeof(storage)};
static void clean(void) {
    CHECK(device.refs==1 && !owned && allocations==frees,"OWNER_BALANCE");
}
static int ppe(const char *cmd,int destroy,int write,loff_t *position) {
    char input[1100]={0}; size_t len=strlen(cmd);
    memcpy(input,cmd,len);
    return destroy?nss_ppe_vp_destroy_handler(&ctl,write,input,&len,position):
                   nss_ppe_vp_create_handler(&ctl,write,input,&len,position);
}
static int mirror(const char *cmd) {
    char input[1100]={0}; size_t len=strlen(cmd); loff_t pos=0;
    memcpy(input,cmd,len); ctl.maxlen=128;
    return nss_mirror_ctl_config_handler(&ctl,1,input,&len,&pos);
}
static int tunip(const char *cmd,enum nss_tunipip6_sysctl_mode mode) {
    char input[1100]={0}; size_t len=strlen(cmd); loff_t pos=0;
    memcpy(input,cmd,len);
    switch(mode) {
    case NSS_TUNIPIP6_SYSCTL_ADD_MAPRULE: return nss_tunipip6_cmd_procfs_add_maprule(&ctl,1,input,&len,&pos);
    case NSS_TUNIPIP6_SYSCTL_DEL_MAPRULE: return nss_tunipip6_cmd_procfs_del_maprule(&ctl,1,input,&len,&pos);
    case NSS_TUNIPIP6_SYSCTL_FLUSH_FMR_RULE: return nss_tunipip6_cmd_procfs_flush_fmr_rule(&ctl,1,input,&len,&pos);
    case NSS_TUNIPIP6_SYSCTL_FRAG_ID: return nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,1,input,&len,&pos);
    }
    die("TEST_MODE"); return 0;
}
static void fw(const unsigned char *data,size_t size,int expected) {
    struct platform_device dev={{1}};
    struct firmware f={data,size};
    scan_base=data; scan_extent=size;
    CHECK(nss_hal_firmware_info(&dev,&f)==expected,"FW_RESULT");
    scan_base=NULL; scan_extent=0;
}
static void test_sequence_bounds(void) {
    const unsigned char data[]={1,2,3,4}, seq[]={1,2,3,4,5};
    scan_base=data; scan_extent=sizeof(data);
    for(size_t n=0;n<sizeof(seq);n++)
        CHECK(!search_sequence(data,n,seq,sizeof(seq)),"SEQ_SHORT");
    CHECK(!search_sequence(NULL,4,seq,1) && !search_sequence(data,4,NULL,1) &&
          !search_sequence(data,4,seq,0),"SEQ_NULL_EMPTY");
    scan_base=NULL; scan_extent=0;
}
static void test_sequence_first_last(void) {
    const unsigned char data[]="XYZXYZ", seq[]="XYZ", tail[]="abcXYZ";
    scan_base=data; scan_extent=sizeof(data)-1;
    CHECK(search_sequence(data,sizeof(data)-1,seq,3)==data,"SEQ_FIRST");
    scan_base=tail; scan_extent=sizeof(tail)-1;
    CHECK(search_sequence(tail,sizeof(tail)-1,seq,3)==tail+3,"SEQ_LAST");
    CHECK(!search_sequence(tail,sizeof(tail)-1,(const unsigned char *)"nop",3),"SEQ_ABSENT");
    scan_base=NULL; scan_extent=0;
}
static void test_firmware_terminal(void) {
    const unsigned char data[]="Version: ";
    for(size_t n=0;n<sizeof(data)-1;n++) fw(data,n,-EINVAL);
    fw(data,sizeof(data)-1,-EINVAL); /* Marker ends exactly at the image boundary. */
    fw(data,sizeof(data),0); CHECK(!version_text[0],"FW_EMPTY_PRESERVED");
}
static void test_firmware_version(void) {
    const unsigned char data[]="badVersion: v1.2\0trailer";
    fw(data,sizeof(data),0); CHECK(!strcmp(version_text,"v1.2"),"FW_VERSION");
    unsigned char long_version[310]; memcpy(long_version,"Version: ",9);
    memset(long_version+9,'x',300); long_version[309]=0;
    fw(long_version,sizeof(long_version),0);
    CHECK(strlen(version_text)==255,"FW_TRUNCATION");
    for(size_t n=0;n<255;n++) CHECK(version_text[n]=='x',"FW_VERSION_BYTES");
}
static void test_ppe_valid(void) {
    loff_t pos=0;
    interleave="foreign0 1"; /* Precise serial interleave: overwrite shared proc data. */
    CHECK(ppe("ath0\n",0,1,&pos)==0 && !strcmp(last_action,"ppe-create") &&
          !strcmp(last_name,"ath0") && last_type==NSS_DYNAMIC_INTERFACE_TYPE_NONE,"PPE_VALID");
    CHECK(!strcmp(storage,interleave),"PPE_INTERLEAVE_APPLIED");
    interleave=NULL; pos=0; vp_present=1;
    CHECK(ppe("  ath0 \t6\n",1,1,&pos)==0 && last_type==NSS_DYNAMIC_INTERFACE_TYPE_VAP &&
          !strcmp(last_action,"ppe-destroy"),"PPE_TYPE"); clean();
}
static void test_ppe_invalid(void) {
    const char *bad[]={" ","ath0 nonsense","ath0 -1","ath0 4294967296","ath0 999","ath0 6 extra","abcdefghijklmnop 6"};
    for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
        loff_t pos=0; int old=actions;
        CHECK(ppe(bad[i],0,1,&pos)<0 && actions==old,"PPE_INVALID"); clean();
    }
}
static void test_ppe_read(void) {
    for(int destroy=0;destroy<2;destroy++) {
        loff_t pos=0; int old=actions, old_gets=dev_gets;
        strcpy(storage,"last");
        CHECK(ppe("read-capacity",destroy,0,&pos)==0 && actions==old && dev_gets==old_gets,"PPE_READ");
    }
}
static void test_ppe_errors(void) {
    loff_t pos=0; proc_error=-EPERM;
    CHECK(ppe("ath0 6",0,1,&pos)==-EPERM && !actions && !dev_gets,"PPE_ERROR");
    proc_error=0; ctx_present=0; pos=0;
    CHECK(ppe("ath0",0,1,&pos)==-ENODEV && !actions,"PPE_CONTEXT");
    ctx_present=1; pos=0; api_error=1;
    CHECK(ppe("ath0",0,1,&pos)==-EBUSY && actions==1,"PPE_BACKEND_ERROR"); clean();
}
static void test_ppe_refbalance(void) {
    loff_t pos=0; mapped_if=-1;
    CHECK(ppe("ath0 6",0,1,&pos)==-EFAULT && !actions,"PPE_MAPPING_ERROR"); clean();
    mapped_if=42; pos=0;
    CHECK(ppe("ath0 6",0,1,&pos)==0,"PPE_MAPPING_SUCCESS");
    CHECK(device.refs==1 && dev_gets==dev_puts,"PPE_PUT"); clean();
}
static void test_ppe_bounds(void) {
    char input[201]={0}; size_t lens[]={0,NSS_PPE_VP_MAX_CMD_STR,SIZE_MAX};
    for(size_t i=0;i<3;i++) {
        size_t len=lens[i]; loff_t pos=0; int old=proc_calls;
        CHECK(nss_ppe_vp_parse_vp_cmd(&ctl,1,input,&len,&pos)==-E2BIG && proc_calls==old && !dev_gets,"PPE_LIMIT");
    }
    loff_t pos=1; strcpy(storage,"ath0");
    CHECK(ppe("ath0 6",0,1,&pos)==-EINVAL && !actions,"PPE_POSITION");
    pos=-1; CHECK(ppe("ath0",1,1,&pos)==-EINVAL && !actions,"PPE_POSITION");
}
static void test_mirror_dispatch(void) {
    const char *commands[]={"create\n","enable mirrordev=ath0\n","disable mirrordev=ath0\n",
        "reset_nexthop mirrordev=ath0\n","set_nexthop mirrordev=ath0 mirror_next_hop=n2h\n",
        "display mirrordev=all\n","display mirrordev=ath0\n","destroy mirrordev=ath0\n"};
    const char *expected[]={"mirror-create","mirror-enable","mirror-disable","mirror-reset","mirror-next",
        "mirror-display-all","mirror-display","mirror-destroy"};
    for(size_t i=0;i<8;i++) {
        CHECK(mirror(commands[i])==0 && !strcmp(last_action,expected[i]),"MIRROR_DISPATCH"); clean();
    }
    const char *display_commands[]={"display mirrordev=all","display mirrordev=all\n",
                                    "display mirrordev=ath0","display mirrordev=ath0\n"};
    for(size_t i=0;i<4;i++) {
        CHECK(mirror(display_commands[i])==0 &&
              !strcmp(last_action,i<2?"mirror-display-all":"mirror-display"),"MIRROR_DISPLAY_VALID");
        clean();
    }
    const char *next_values[]={"n2h","n2h\n","eth_rx","eth_rx\n"};
    for(size_t i=0;i<4;i++) {
        char command[100]; snprintf(command,sizeof(command),"set_nexthop mirrordev=ath0 mirror_next_hop=%s",next_values[i]);
        CHECK(mirror(command)==0 && !strcmp(last_action,"mirror-next") &&
              last_type==(uint32_t)(i<2?NSS_N2H_INTERFACE:NSS_ETH_RX_INTERFACE),"MIRROR_NEXTHOP_VALID");
        clean();
    }
    struct net_device *out=NULL;
    CHECK(nss_mirror_ctl_get_netdev_by_name("ath0\n",&out)==0 && out==&device,"MIRROR_NAME_NEWLINE");
    dev_put(out); clean();
    strcpy(device.name,"abcdefghijklmno");
    const char *names[]={"abcdefghijklmno","abcdefghijklmno\n"};
    for(size_t i=0;i<2;i++) {
        out=NULL;
        CHECK(nss_mirror_ctl_get_netdev_by_name((char *)names[i],&out)==0 && out==&device &&
              !strcmp(last_name,"abcdefghijklmno"),"MIRROR_NAME_MAX");
        dev_put(out); clean();
    }
    CHECK(mirror("enable mirrordev=abcdefghijklmno\n")==0 &&
          !strcmp(last_action,"mirror-enable") && !strcmp(last_name,device.name),"MIRROR_NAME_MAX_PARSER");
    const char *display_long[]={"display mirrordev=abcdefghijklmno","display mirrordev=abcdefghijklmno\n"};
    for(size_t i=0;i<2;i++) {
        CHECK(mirror(display_long[i])==0 && !strcmp(last_action,"mirror-display") &&
              !strcmp(last_name,device.name),"MIRROR_DISPLAY_MAX");
        clean();
    }
    clean(); strcpy(device.name,"ath0");
    CHECK(copy_user_calls==0,"MIRROR_KERNEL_INPUT");
}
static void test_mirror_config(void) {
    CHECK(mirror("configure mirrordev=ath0 mirror_size=42 mirror_point=2 mirror_offset=12\n")==0,"MIRROR_CONFIG");
    CHECK(clone_size==42 && clone_point==NSS_MIRROR_PKT_CLONE_POINT_BEFORE_PACKET_START && clone_offset==12 &&
          !strcmp(last_action,"mirror-configure"),"MIRROR_CONFIG_PAYLOAD"); clean();
}
static void test_mirror_invalid(void) {
    struct net_device foreign={"held",7,0}, saved;
    memcpy(&saved,&foreign,sizeof(saved));
    char *names[]={NULL,""};
    for(size_t i=0;i<2;i++) {
        struct net_device *out=&foreign;
        int gets_before=dev_gets, puts_before=dev_puts, alloc_before=allocations;
        CHECK(nss_mirror_ctl_get_netdev_by_name(names[i],&out)==-1 && out==&foreign &&
              !memcmp(&foreign,&saved,sizeof(saved)) && device.refs==1 && dev_gets==gets_before &&
              dev_puts==puts_before && allocations==alloc_before && !actions,"MIRROR_EMPTY_NAME");
        clean();
    }
    const char *bad[]={" ","not-a-command","enable","enable wrong=ath0","enable mirrordev=missing",
                       "enable mirrordev=","disable mirrordev=","reset_nexthop mirrordev=",
                       "display mirrordev="};
    for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
        int gets_before=dev_gets, puts_before=dev_puts;
        CHECK(mirror(bad[i])==-EINVAL && !actions,"MIRROR_INVALID"); clean();
        if(i>=5) CHECK(dev_gets==gets_before && dev_puts==puts_before,"MIRROR_EMPTY_PARSER");
    }
    const char *empty_next[]={"set_nexthop mirror_next_hop= mirrordev=ath0",
                             "set_nexthop mirrordev=ath0 mirror_next_hop="};
    for(size_t i=0;i<2;i++) {
        int gets_before=dev_gets, puts_before=dev_puts;
        CHECK(mirror(empty_next[i])==-EINVAL && !actions &&
              dev_gets==gets_before+(int)i && dev_puts==puts_before+(int)i,"MIRROR_EMPTY_NEXTHOP");
        clean();
    }
}
static void test_mirror_errors(void) {
    proc_error=-EPERM;
    CHECK(mirror("create")==-EPERM && !actions && !allocations,"MIRROR_PROC");
    proc_error=0; alloc_fail=1;
    CHECK(mirror("create")==-ENOMEM && !actions && !owned,"MIRROR_OOM");
    alloc_fail=0; allocations=0; api_error=-1;
    CHECK(mirror("enable mirrordev=ath0")==-EINVAL && device.refs==1,"MIRROR_BACKEND_ERROR"); clean();
    char data[4]={0}; size_t len=sizeof(data); loff_t pos=0; int old=actions;
    CHECK(nss_mirror_ctl_config_handler(&ctl,0,data,&len,&pos)==0 && actions==old,"MIRROR_READ");
}
static void test_mirror_bounds(void) {
    char input[130]; memset(input,' ',sizeof(input)); memcpy(input,"help ",5);
    size_t len=128; loff_t pos=0; ctl.maxlen=128;
    CHECK(nss_mirror_ctl_config_handler(&ctl,1,input,&len,&pos)==0 && !actions,"MIRROR_BOUND_SUCCESS"); clean();
    len=129; pos=0; int old=allocations;
    CHECK(nss_mirror_ctl_config_handler(&ctl,1,input,&len,&pos)==-E2BIG && allocations==old,"MIRROR_LIMIT");
    len=SIZE_MAX; CHECK(nss_mirror_ctl_config_handler(&ctl,1,input,&len,&pos)==-E2BIG,"MIRROR_LIMIT");
    len=0; CHECK(nss_mirror_ctl_config_handler(&ctl,1,input,&len,&pos)==-E2BIG,"MIRROR_LIMIT");
}
static const char map_args[]="netdev=ath0 rule_type=1 ipv6_prefix=2001:db8:: ipv6_prefix_len=32 ipv6_suffix=2001:db8:1:: ipv6_suffix_len=64 ipv4_prefix=192.0.2.0 ipv4_prefix_len=24 ea_len=8 psid_offset=6\n";
static void test_tunip_frag(void) {
    CHECK(tunip("frag_id_update=1\n",NSS_TUNIPIP6_SYSCTL_FRAG_ID)==0 && frag_id_update,"TUNIP_FRAG"); clean();
    CHECK(tunip("frag_id_update=0",NSS_TUNIPIP6_SYSCTL_FRAG_ID)==0 && !frag_id_update && !actions,"TUNIP_FRAG"); clean();
    CHECK(!copy_user_calls,"TUNIP_KERNEL_INPUT");
}
static void test_tunip_map(void) {
    CHECK(tunip(map_args,NSS_TUNIPIP6_SYSCTL_ADD_MAPRULE)==0 && actions==1 && !strcmp(last_action,"map-add"),"TUNIP_MAP");
    struct nss_connmgr_tunipip6_maprule_cfg expected={0};
    expected.rule_type=NSS_CONNMGR_TUNIPIP6_RULE_BMR;
    expected.ipv6_prefix[0]=0x20010db8; expected.ipv6_suffix[0]=0x20010db8; expected.ipv6_suffix[1]=0x00010000;
    expected.ipv6_prefix_len=32; expected.ipv6_suffix_len=64;
    expected.ipv4_prefix=0xc0000200; expected.ipv4_prefix_len=24; expected.ea_len=8; expected.psid_offset=6;
    CHECK(!memcmp(&last_rule,&expected,sizeof(expected)),"TUNIP_MAP_PAYLOAD"); clean();
    int old=actions;
    CHECK(tunip("netdev=ath0 rule_type=1 ipv6_prefix=2001:db8:: ipv6_prefix_len=32 ipv6_suffix=2001:db8:1:: ipv4_prefix=192.0.2.0 ipv4_prefix_len=24 ea_len=8 psid_offset=6",NSS_TUNIPIP6_SYSCTL_ADD_MAPRULE)==0 && actions==old,"TUNIP_SUFFIX_LENGTH"); clean();
}
static void test_tunip_del_flush(void) {
    CHECK(tunip("netdev=ath0 rule_type=1",NSS_TUNIPIP6_SYSCTL_DEL_MAPRULE)==0 && !strcmp(last_action,"map-delete"),"TUNIP_DELETE"); clean();
    CHECK(tunip("netdev=ath0",NSS_TUNIPIP6_SYSCTL_FLUSH_FMR_RULE)==0 && !strcmp(last_action,"map-flush"),"TUNIP_FLUSH"); clean();
}
static void test_tunip_errors(void) {
    alloc_fail=1;
    CHECK(tunip("frag_id_update=1",NSS_TUNIPIP6_SYSCTL_FRAG_ID)==-ENOMEM && !actions && !owned,"TUNIP_OOM");
    alloc_fail=0; allocations=0;
    CHECK(tunip("netdev=missing",NSS_TUNIPIP6_SYSCTL_FLUSH_FMR_RULE)==0 && !actions,"TUNIP_EXISTING_FAIL_RETURN"); clean();
    CHECK(tunip("frag_id_update=2",NSS_TUNIPIP6_SYSCTL_FRAG_ID)==0 && !frag_id_update,"TUNIP_INVALID_VALUE"); clean();
    size_t len=1; loff_t pos=0; char input='1'; int old=allocations;
    CHECK(nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,0,&input,&len,&pos)==-EINVAL && allocations==old,"TUNIP_READ");
    const char *empty_fields[]={"rule_type","ipv4_prefix_len","ipv6_prefix_len","ipv6_suffix_len","ea_len","psid_offset"};
    for(size_t i=0;i<sizeof(empty_fields)/sizeof(empty_fields[0]);i++) {
        char command[100]; struct nss_connmgr_tunipip6_maprule_cfg saved;
        memcpy(&saved,&last_rule,sizeof(saved));
        snprintf(command,sizeof(command),"netdev=ath0 %s=",empty_fields[i]);
        CHECK(tunip(command,NSS_TUNIPIP6_SYSCTL_ADD_MAPRULE)==0 && !actions &&
              !memcmp(&last_rule,&saved,sizeof(saved)),"TUNIP_KERNEL_EMPTY_SCALAR");
        clean();
    }
    frag_id_update=true;
    CHECK(tunip("frag_id_update=",NSS_TUNIPIP6_SYSCTL_FRAG_ID)==0 && frag_id_update && !actions,"TUNIP_KERNEL_EMPTY_FRAG");
    frag_id_update=false; clean();
}
static void test_kernel_numeric_model(void) {
    const char *inputs[]={""," \t\n","wrong","0","42tail"};
    for(size_t i=0;i<sizeof(inputs)/sizeof(inputs[0]);i++) {
        unsigned value=0x87654321u; unsigned short small=0xa55au;
        int expected=i<3?0:1;
        const char *marker=i<2?"KERNEL_SCAN_EMPTY":i==2?"KERNEL_SCAN_MALFORMED":"KERNEL_SCAN_CONVERSION";
        CHECK(model_kernel_sscanf(inputs[i],"%u",&value)==expected &&
              value==(i<3?0x87654321u:i==3?0u:42u),marker);
        CHECK(model_kernel_sscanf(inputs[i],"%hu",&small)==expected &&
              small==(i<3?0xa55au:i==3?0u:42u),marker);
    }
    unsigned value=0; unsigned short small=0;
    CHECK(model_kernel_sscanf("4294967295","%u",&value)==1 && value==UINT32_MAX &&
          model_kernel_sscanf("65535","%hu",&small)==1 && small==UINT16_MAX,"KERNEL_SCAN_CONVERSION");
}
static void test_tunip_bounds(void) {
    char input[MAX_PROC_SIZE+1]; memset(input,' ',sizeof(input));
    size_t len=MAX_PROC_SIZE; loff_t pos=0; want_alloc=MAX_PROC_SIZE+1;
    CHECK(nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,1,input,&len,&pos)==0,"TUNIP_FULL_INPUT"); clean();
    want_alloc=0; memset(input,0,sizeof(input)); len=MAX_PROC_SIZE+1;
    CHECK(nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,1,input,&len,&pos)==-E2BIG,"TUNIP_LIMIT");
    len=SIZE_MAX; CHECK(nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,1,input,&len,&pos)==-E2BIG,"TUNIP_LIMIT");
    len=0; CHECK(nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,1,input,&len,&pos)==-E2BIG,"TUNIP_LIMIT");
}
struct test { const char *name; void (*fn)(void); };
static const struct test tests[]={
    {"sequence-bounds",test_sequence_bounds},{"sequence-first-last",test_sequence_first_last},
    {"firmware-terminal",test_firmware_terminal},{"firmware-version",test_firmware_version},
    {"ppe-valid",test_ppe_valid},{"ppe-invalid",test_ppe_invalid},{"ppe-read",test_ppe_read},
    {"ppe-errors",test_ppe_errors},{"ppe-refbalance",test_ppe_refbalance},{"ppe-bounds",test_ppe_bounds},
    {"mirror-dispatch",test_mirror_dispatch},{"mirror-config",test_mirror_config},
    {"mirror-invalid",test_mirror_invalid},{"mirror-errors",test_mirror_errors},{"mirror-bounds",test_mirror_bounds},
    {"tunip-frag",test_tunip_frag},{"tunip-map",test_tunip_map},{"tunip-del-flush",test_tunip_del_flush},
    {"tunip-errors",test_tunip_errors},{"tunip-bounds",test_tunip_bounds},
    {"kernel-numeric-model",test_kernel_numeric_model}
};
int main(int argc,char **argv) {
    CHECK(argc==2,"CASE_ARGUMENT");
    for(size_t i=0;i<sizeof(tests)/sizeof(tests[0]);i++) if(!strcmp(tests[i].name,argv[1])) {
        tests[i].fn(); clean(); printf("PASS %s\n",tests[i].name); return 0;
    }
    die("UNKNOWN_CASE"); return 1;
}
