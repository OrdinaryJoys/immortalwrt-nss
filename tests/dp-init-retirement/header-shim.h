/* Only host OS declarations for compiling the complete installed SDK header. */
#ifndef DP_INIT_HEADER_SHIM_H
#define DP_INIT_HEADER_SHIM_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t __u8;
typedef int8_t __s8;
typedef uint16_t __u16;
typedef int16_t __s16;
typedef uint32_t __u32;
typedef int32_t __s32;
typedef uint64_t __u64;
typedef int64_t __s64;
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef uint64_t u64;
typedef int64_t s64;
typedef int spinlock_t;
struct mutex { int opaque; };
struct timer_list { int opaque; };
struct device;
struct net_device;
struct phy_device;
struct mii_bus;
struct notifier_block;
#define __iomem
#define GFP_KERNEL 1U
#define __GFP_ZERO 2U
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,38)
static inline void *kmalloc(size_t size,unsigned flags) { (void)flags;return malloc(size); }
static inline void kfree(void *p) { free(p); }
static inline void udelay(int n) { (void)n; }
static inline void mdelay(int n) { (void)n; }
#endif
