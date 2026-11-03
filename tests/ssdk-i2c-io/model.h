#ifndef SSDK_I2C_IO_HOST_MODEL
#define SSDK_I2C_IO_HOST_MODEL
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vendor-errors.h"
#include "vendor-constants.h"
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
typedef int16_t a_int16_t;
typedef int32_t a_int32_t;
typedef int a_bool_t;
#define A_TRUE 1
#define A_FALSE 0
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define aos_mem_set memset
#define SW_RTN_ON_NULL(p) do { if (!(p)) return SW_NOT_INITIALIZED; } while (0)
#define EXPORT_SYMBOL(x)
#ifdef IN_PHY_I2C_MODE
static unsigned diagnostics;
static void diagnostic(const char *format,...) { (void)format; diagnostics++; }
#endif
#define SSDK_ERROR(...) diagnostic(__VA_ARGS__)
#define I2C_M_RD 1
#define I2C_LOCK_SEGMENT 2
struct i2c_adapter { int refs, locked; };
struct i2c_msg { uint16_t addr, flags, len; uint8_t *buf; };
static struct i2c_adapter bus = {1, 0};
static unsigned adapter_gets, adapter_puts, locks, unlocks, transfers, bytes, target_calls;
static unsigned fail_get, fault_at;
static int fault, absent, write_mode;
static uint8_t *expected_buffer;
static uint32_t expected_address;
static void fail(const char *marker) { fprintf(stderr,"I2C_IO %s\n",marker); exit(86); }
#define CHECK(c,m) do { if (!(c)) fail(m); } while (0)
static struct i2c_adapter *i2c_get_adapter(unsigned id) {
    CHECK(id==I2C_ADAPTER_DEFAULT_ID,"ADAPTER_ID"); adapter_gets++;
    if (absent || (fail_get && adapter_gets==fail_get)) return NULL;
    bus.refs++; return &bus;
}
static void i2c_put_adapter(struct i2c_adapter *adapter) {
    CHECK(adapter==&bus && bus.refs>1,"FOREIGN_OR_DOUBLE_PUT");
    bus.refs--; adapter_puts++;
}
static void i2c_lock_bus(struct i2c_adapter *adapter,unsigned flags) {
    CHECK(adapter==&bus && bus.refs>1 && !bus.locked && flags==I2C_LOCK_SEGMENT,"LOCK_OWNER");
    bus.locked=1; locks++;
}
static void i2c_unlock_bus(struct i2c_adapter *adapter,unsigned flags) {
    CHECK(adapter==&bus && bus.refs>1 && bus.locked && flags==I2C_LOCK_SEGMENT,"UNLOCK_OWNER");
    bus.locked=0; unlocks++;
}
static int __i2c_transfer(struct i2c_adapter *adapter,struct i2c_msg *msg,int num) {
    CHECK(adapter==&bus && bus.refs>1 && bus.locked,"TRANSFER_REQUIRES_CALLER_LOCK");
    CHECK(num==1 || num==2,"MESSAGE_COUNT"); transfers++; target_calls++;
    int ret=fault_at && transfers>=fault_at?fault:num;
    if (ret!=num) return ret;
    CHECK(msg[0].buf && msg[0].addr==0x44,"REQUEST_ADDRESS");
    if (num==2 && msg[0].len==4) {
        CHECK(msg[0].flags==0 && msg[1].flags==(write_mode?0:I2C_M_RD) &&
              msg[1].len==(write_mode?3:2),"MMD_FRAME");
        CHECK(msg[0].buf[1]==0x12 && msg[0].buf[2]==0x34 && msg[0].buf[3]==0,"MMD_REGISTER");
        CHECK(msg[1].buf,"NULL_PAYLOAD");
        if (write_mode) CHECK(msg[1].buf[1]==0xab && msg[1].buf[2]==0xcd,"MMD_VALUE");
        else { msg[1].buf[0]=0xab; msg[1].buf[1]=0xcd; }
        return num;
    }
    CHECK((num==1)==write_mode && msg[0].flags==0,"DATA_DIRECTION");
    unsigned address_size=(num==2)?msg[0].len:(((expected_address+bytes)&0xff00)?2:1);
    CHECK(address_size==1 || address_size==2,"DATA_ADDRESS_SIZE");
    unsigned address=address_size==2?((unsigned)msg[0].buf[0]<<8)|msg[0].buf[1]:msg[0].buf[0];
    CHECK(address==((expected_address+bytes)&0xffff),"DATA_REGISTER");
    unsigned n=num==2?msg[1].len:msg[0].len-address_size;
    CHECK(n && n<=8,"CHUNK_SIZE");
    uint8_t *payload=num==2?msg[1].buf:msg[0].buf+address_size;
    CHECK(payload,"NULL_PAYLOAD");
    if (num==2) {
        CHECK(msg[1].flags==I2C_M_RD,"READ_FLAG");
        for(unsigned i=0;i<n;i++) payload[i]=(uint8_t)(bytes+i+17);
    } else if (expected_buffer) CHECK(!memcmp(payload,expected_buffer+bytes,n),"WRITE_BYTES");
    bytes+=n;
    return num;
}
static void reset(void) {
    CHECK(bus.refs==1 && !bus.locked,"PREVIOUS_REFERENCE_BALANCE");
    adapter_gets=adapter_puts=locks=unlocks=transfers=bytes=target_calls=0;
    fail_get=fault_at=0; fault=absent=write_mode=0;
    expected_buffer=NULL; expected_address=0;
}
static void balanced(void) {
    CHECK(bus.refs==1 && !bus.locked,"REFERENCE_BALANCE");
    CHECK(locks==unlocks,"LOCK_BALANCE");
}
#endif
