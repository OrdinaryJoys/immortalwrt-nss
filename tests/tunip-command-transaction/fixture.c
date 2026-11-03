#include "model.h"
#define sscanf kernel_scalar
#undef memcpy
#define memcpy model_copy
#include "actual.c"
#undef memcpy
#undef sscanf

static long number(const char *text) {
    char *end; errno=0; long value=strtol(text,&end,10);
    CHECK(!errno && *text && !*end,"HARNESS_NUMBER"); return value;
}
static int dispatch(int mode,int selector,char *data,size_t *len,loff_t *pos) {
    const struct ctl_table ctl={0};
    if(selector==1) data=NULL;
    if(selector==2) len=NULL;
    int write=selector!=3;
    switch(mode) {
    case 0: return nss_tunipip6_cmd_procfs_add_maprule(&ctl,write,data,len,pos);
    case 1: return nss_tunipip6_cmd_procfs_del_maprule(&ctl,write,data,len,pos);
    case 2: return nss_tunipip6_cmd_procfs_flush_fmr_rule(&ctl,write,data,len,pos);
    case 3: return nss_tunipip6_cmd_procfs_enable_frag_id(&ctl,write,data,len,pos);
    default: return nss_tunipip6_data_parser(&ctl,write,data,len,pos,(enum nss_tunipip6_sysctl_mode)mode);
    }
}
int main(int argc,char **argv) {
    CHECK(argc==12,"HARNESS_ARGUMENTS");
    int mode=(int)number(argv[1]); provider_status=(int)number(argv[2]); fail_alloc=(int)number(argv[3]);
    int selector=(int)number(argv[4]), expected=(int)number(argv[5]);
    frag_id_update=number(argv[6])!=0; int expected_frag=(int)number(argv[7]);
    int repeat=(int)number(argv[8]); CHECK(repeat==1 || repeat==2,"HARNESS_REPEAT");
    unsigned char input[MAX_PROC_SIZE+2]={0};
    FILE *request=fopen(argv[9],"rb"); CHECK(request,"INPUT_FILE");
    true_extent=fread(input,1,sizeof(input),request); CHECK(!ferror(request) && feof(request),"INPUT_FILE"); fclose(request);
    true_input=input;
    struct net_device saved[3]; memcpy(saved,devices,sizeof(saved));
    for(int step=0;step<repeat;step++) {
        size_t len=true_extent; loff_t pos=17;
        if(selector==4) len=SIZE_MAX;
        int result=dispatch(mode,selector,(char *)input,&len,&pos);
        CHECK(result==(step?0:expected),"RETURN");
        CHECK(len==(selector==4?SIZE_MAX:true_extent) && pos==17,"OUTPUT_PARAMETERS");
        CHECK(frag_id_update==(expected_frag!=0),"FRAG_STATE");
        CHECK(!owned && successful_allocs==releases,"ALLOC_BALANCE");
        for(int i=0;i<3;i++) CHECK(devices[i].refs==base_refs[i],"REF_BALANCE");
        CHECK(!memcmp(saved,devices,sizeof(saved)),"DEVICE_BYTES");
        event("RETURN %d\n",result);
        event("END refs=%d,%d,%d frag=%d alloc=%d/%d calls=%d\n",devices[0].refs,devices[1].refs,devices[2].refs,
              frag_id_update?1:0,attempts,releases,calls);
        fail_alloc=0; provider_status=NSS_CONNMGR_TUNIPIP6_SUCCESS;
    }
    FILE *expected_file=fopen(argv[10],"rb"); CHECK(expected_file,"EXPECTED_FILE");
    char expected_trace[32768]; size_t n=fread(expected_trace,1,sizeof(expected_trace),expected_file);
    CHECK(!ferror(expected_file) && feof(expected_file),"EXPECTED_FILE"); fclose(expected_file);
    CHECK(n==trace_len && !memcmp(expected_trace,trace,n),"TRACE");
    CHECK(!strcmp(argv[11],"fixed-contract"),"HARNESS_CONTRACT");
    CHECK(fwrite(trace,1,trace_len,stdout)==trace_len,"OUTPUT_WRITE");
    return 0;
}
