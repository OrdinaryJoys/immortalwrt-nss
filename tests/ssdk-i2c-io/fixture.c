#include "model.h"
#include "actual.c"

static void data_ok(unsigned n,int write) {
    reset();
    uint8_t *allocation=malloc((size_t)n+2);
    CHECK(allocation,"HOST_ALLOCATION"); memset(allocation,0xa5,(size_t)n+2);
    uint8_t *buffer=allocation+1;
    if (write) for(unsigned i=0;i<n;i++) buffer[i]=(uint8_t)(i+17);
    expected_buffer=buffer; expected_address=0xf0; write_mode=write;
    int ret=write?qca_i2c_data_set(0,0x44,expected_address,buffer,n):
                  qca_i2c_data_get(0,0x44,expected_address,buffer,n);
    CHECK(ret==SW_OK && bytes==n,"LENGTH_WIDTH");
    CHECK(transfers==(n+7)/8,"CHUNK_COUNT");
    CHECK(allocation[0]==0xa5 && allocation[n+1]==0xa5,"BUFFER_GUARDS");
    for(unsigned i=0;i<n;i++) CHECK(buffer[i]==(uint8_t)(i+17),"DATA_RESULT");
    balanced(); free(allocation);
}
static void data_error(int value,int write,unsigned at) {
    reset();
    uint8_t buffer[17]; memset(buffer,0xa5,sizeof(buffer));
    fault=value; fault_at=at; write_mode=write;
    int ret=write?qca_i2c_data_set(0,0x44,0,buffer,sizeof(buffer)):
                  qca_i2c_data_get(0,0x44,0,buffer,sizeof(buffer));
    CHECK(ret==(value==-ENXIO?SW_NO_RESOURCE:SW_FAIL),write?"WRITE_FAILURE":"READ_FAILURE");
    CHECK(transfers==at,"STOP_ON_FIRST_TRANSFER_FAILURE"); balanced();
}
static void test_data(const char *name) {
    if (!strcmp(name,"data-chunks")) {
        unsigned sizes[]={1,2,7,8,9,15,16,17,255,256};
        for(unsigned i=0;i<ARRAY_SIZE(sizes);i++) for(int w=0;w<2;w++) data_ok(sizes[i],w);
    } else if (!strcmp(name,"data-width")) {
        unsigned sizes[]={32767,32768,65535,65536,65537};
        for(unsigned i=0;i<ARRAY_SIZE(sizes);i++) for(int w=0;w<2;w++) data_ok(sizes[i],w);
    } else if (!strcmp(name,"short-read")) data_error(1,0,1);
    else if (!strcmp(name,"short-write")) data_error(0,1,1);
    else if (!strcmp(name,"negative-read")) {
        int errors[]={-EIO,-ENXIO,-ENODEV,-EAGAIN,-254};
        for(unsigned i=0;i<ARRAY_SIZE(errors);i++) data_error(errors[i],0,1);
    } else if (!strcmp(name,"negative-write")) {
        int errors[]={-EIO,-ENXIO,-ENODEV,-EAGAIN,-254};
        for(unsigned i=0;i<ARRAY_SIZE(errors);i++) data_error(errors[i],1,1);
    } else if (!strcmp(name,"midstream")) {
        data_error(-EIO,0,2); data_error(-ENXIO,1,2);
    } else if (!strcmp(name,"data-reference")) { data_ok(1,0); data_ok(1,1); }
    else if (!strcmp(name,"adapter-missing")) {
        for(int w=0;w<2;w++) {
            reset(); absent=1; uint8_t b=0;
            CHECK((w?qca_i2c_data_set(0,0x44,0,&b,1):qca_i2c_data_get(0,0x44,0,&b,1))==
                  SW_NOT_INITIALIZED && !transfers && !locks,"MISSING_ADAPTER"); balanced();
            reset(); fail_get=2;
            CHECK((w?qca_i2c_data_set(0,0x44,0,&b,1):qca_i2c_data_get(0,0x44,0,&b,1))==
                  SW_FAIL && !transfers,"MISSING_INNER_ADAPTER"); balanced();
        }
    } else if (!strcmp(name,"data-null")) {
        for(int w=0;w<2;w++) {
            reset(); CHECK((w?qca_i2c_data_set(0,0x44,0,NULL,1):qca_i2c_data_get(0,0x44,0,NULL,1))==
                          SW_BAD_PTR && !transfers,"NULL_DATA"); balanced();
        }
    } else if (!strcmp(name,"data-zero")) {
        for(int w=0;w<2;w++) {
            reset(); CHECK((w?qca_i2c_data_set(0,0x44,0,NULL,0):qca_i2c_data_get(0,0x44,0,NULL,0))==
                          SW_OK && !transfers,"ZERO_LENGTH"); balanced();
        }
    } else if (!strcmp(name,"unlocked-data")) {
        for(int w=0;w<2;w++) {
            reset(); struct i2c_adapter *a=i2c_get_adapter(0); i2c_lock_bus(a,I2C_LOCK_SEGMENT);
            uint8_t b=17; write_mode=w; expected_buffer=&b;
            CHECK((w?__qca_i2c_data_set(0,0x44,0,&b,1):__qca_i2c_data_get(0,0x44,0,&b,1))==SW_OK,
                  "UNLOCKED_DATA_RESULT");
            CHECK(locks==1 && !unlocks && bus.locked && bus.refs==2,"CALLER_LOCK_UNCHANGED");
            i2c_unlock_bus(a,I2C_LOCK_SEGMENT); i2c_put_adapter(a); balanced();
        }
    } else fail("UNKNOWN_DATA_CASE");
}
#ifdef IN_PHY_I2C_MODE
static uint32_t reg_address(int mmd) { return mmd?QCA_PHY_MII_ADDR_C45|(1u<<16)|0x1234:0x1234; }
static void phy_call(int write,int mmd,int result,int use_fault,int unlocked) {
    reset(); write_mode=write; fault=result; fault_at=use_fault?1:0;
    expected_address=mmd?0:0x34;
    uint16_t output=0x5678;
    struct i2c_adapter *held=NULL;
    if (unlocked) { held=i2c_get_adapter(0); i2c_lock_bus(held,I2C_LOCK_SEGMENT); }
    int ret=write?(unlocked?__qca_phy_i2c_write(0,0x44,reg_address(mmd),0xabcd):
                           qca_phy_i2c_write(0,0x44,reg_address(mmd),0xabcd)):
                  (unlocked?__qca_phy_i2c_read(0,0x44,reg_address(mmd),&output):
                           qca_phy_i2c_read(0,0x44,reg_address(mmd),&output));
    int expected=use_fault?(mmd?SW_FAIL:(result==-ENXIO?SW_NO_RESOURCE:SW_FAIL)):SW_OK;
    CHECK(ret==expected,"PHY_FAILURE_PROPAGATION");
    if (!write && !use_fault) CHECK(output==(mmd?0xabcd:0x1112),"PHY_VALUE");
    if (unlocked) {
        CHECK(bus.refs==2 && bus.locked && locks==1 && !unlocks,"PHY_CALLER_LOCK");
        i2c_unlock_bus(held,I2C_LOCK_SEGMENT); i2c_put_adapter(held);
    }
    balanced();
}
static void test_phy(const char *name) {
    if (!strcmp(name,"phy-valid")) {
        for(int w=0;w<2;w++) for(int m=0;m<2;m++) phy_call(w,m,0,0,0);
    } else if (!strcmp(name,"phy-errors")) {
        int errors[]={0,1,-EIO,-ENXIO,-254};
        for(unsigned e=0;e<ARRAY_SIZE(errors);e++) for(int w=0;w<2;w++) for(int m=0;m<2;m++) {
            if (w && !m && errors[e]==1) continue;
            phy_call(w,m,errors[e],1,0);
        }
    } else if (!strcmp(name,"unlocked-phy")) {
        for(int w=0;w<2;w++) for(int m=0;m<2;m++) {
            phy_call(w,m,0,0,1); phy_call(w,m,-EIO,1,1);
        }
    } else if (!strcmp(name,"phy-reference")) {
        for(int w=0;w<2;w++) for(int m=0;m<2;m++) phy_call(w,m,0,0,0);
    } else if (!strcmp(name,"mmd-result")) {
        for(int w=0;w<2;w++) {
            reset(); fault=-254; fault_at=1; write_mode=w;
            struct i2c_adapter *a=i2c_get_adapter(0); i2c_lock_bus(a,I2C_LOCK_SEGMENT);
            uint16_t out=0x5678;
            CHECK((w?__qca_phy_i2c_mmd_write(0,0x44,1,0x1234,0xabcd):
                      __qca_phy_i2c_mmd_read(0,0x44,1,0x1234,&out))==SW_FAIL,"MMD_SIGNED_RESULT");
            i2c_unlock_bus(a,I2C_LOCK_SEGMENT); i2c_put_adapter(a); balanced();
        }
    } else if (!strcmp(name,"mmd-publication")) {
        reset(); fault=1; fault_at=1;
        struct i2c_adapter *a=i2c_get_adapter(0); i2c_lock_bus(a,I2C_LOCK_SEGMENT);
        uint16_t out=0x5678;
        CHECK(__qca_phy_i2c_mmd_read(0,0x44,1,0x1234,&out)==SW_FAIL && out==0x5678,"MMD_FAILURE_OUTPUT");
        i2c_unlock_bus(a,I2C_LOCK_SEGMENT); i2c_put_adapter(a); balanced();
    } else if (!strcmp(name,"phy-invalid")) {
        reset(); uint16_t out=0x5678;
        CHECK(qca_phy_i2c_read(0,0x40,0,&out)==SW_BAD_PARAM && !transfers,"PHY_BAD_ADDRESS"); balanced();
        reset(); CHECK(qca_phy_i2c_write(0,0x44,QCA_PHY_MII_ADDR_C45|(2u<<16),0)==SW_FAIL &&
                       !transfers,"PHY_BAD_MMD"); balanced();
        reset(); absent=1;
        CHECK(qca_phy_i2c_read(0,0x44,0,&out)==SW_NOT_INITIALIZED && !transfers,"PHY_NO_ADAPTER"); balanced();
    } else if (!strcmp(name,"phy-null")) {
        reset(); CHECK(qca_phy_i2c_read(0,0x44,reg_address(1),NULL)==SW_BAD_PTR &&
                       !transfers,"NULL_PHY_OUTPUT"); balanced();
    } else fail("UNKNOWN_PHY_CASE");
}
#endif
static __attribute__((noinline)) void canary_store(volatile int *p,int offset) { p[offset]=1; }
int main(int argc,char **argv) {
    CHECK(argc==2,"CASE_ARGUMENT");
    if (!strcmp(argv[1],"asan-canary")) { int *p=malloc(sizeof(int)); canary_store(p,argc); free(p); return 0; }
    if (!strcmp(argv[1],"ubsan-canary")) { volatile int a=INT_MAX,b=argc; return a+b; }
#ifdef IN_PHY_I2C_MODE
    if (!strncmp(argv[1],"phy-",4) || !strncmp(argv[1],"mmd-",4) || !strcmp(argv[1],"unlocked-phy")) test_phy(argv[1]);
    else
#endif
        test_data(argv[1]);
    printf("PASS %s\n",argv[1]); return 0;
}
