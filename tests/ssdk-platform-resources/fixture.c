/* Serial native state models, not Linux ABI, real clocks, MMIO or readers. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t a_uint8_t;
typedef uint16_t a_uint16_t;
typedef uint32_t a_uint32_t;
typedef unsigned a_bool_t;
typedef uint8_t u8;
#define __iomem
@ACTUAL_TYPES@
@ACTUAL_MAX_DEV@
struct qca_phy_priv { u8 *hw_addr, *psgmii_hw_addr, *uniphy_hw_addr; };
struct clk { unsigned refs; };
struct resource { unsigned token; };
struct mutex { bool held; };
#define DEFINE_MUTEX(name) struct mutex name
static bool locked;
static void fail(const char *marker)
{ fprintf(stderr, "PLATFORM:%s\n", marker); exit(86); }
static void need(bool ok, const char *marker) { if (!ok) fail(marker); }
static void mutex_lock(struct mutex *m)
{ need(!locked && !m->held, "LOCK_REENTRY"); locked = m->held = true; }
static void mutex_unlock(struct mutex *m)
{ need(locked && m->held, "LOCK_PAIR"); locked = m->held = false; }
static void cold(void)
{
#ifdef CANDIDATE
    need(locked, "LOCK_MISSING");
#endif
}
static unsigned logs;
#define SSDK_ERROR(...) do { ++logs; } while (0)
#define SSDK_INFO(...) do { ++logs; } while (0)
static struct qca_phy_priv slots[SW_MAX_NR_DEV], foreign_slot;
static struct qca_phy_priv *table[SW_MAX_NR_DEV], **qca_phy_priv_global = table;
static ssdk_init_cfg cfgs[SW_MAX_NR_DEV], originals[SW_MAX_NR_DEV];
static unsigned modes, fault, clock_mode, attempts, unmapped, claims, releases;
static unsigned enables, disables, gcc_starts, gcc_stops;
static bool gcc_live, changed_dt;
static struct clk ess, cmn;
static struct resource region_tokens[SW_MAX_NR_DEV];
static bool regions[SW_MAX_NR_DEV];
static unsigned region_base[SW_MAX_NR_DEV], region_size[SW_MAX_NR_DEV];
static unsigned map_count;
static ssdk_reg_map_info requested_map;
static bool map_requested;
static unsigned init_device, init_map_step;
static struct { unsigned base, size; u8 token; bool live; } maps[32];
static u8 foreign_byte;
#define ERR_CLK ((struct clk *)(intptr_t)-ENOENT)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
static unsigned live_maps(void)
{ unsigned n = 0; for (unsigned i = 0; i < map_count; ++i) n += maps[i].live; return n; }
static unsigned live_for(unsigned id)
{
    unsigned n = 0;
    for (unsigned i = 0; i < map_count; ++i) n += maps[i].live && (maps[i].base >> 16) == id + 1;
    return n;
}
static unsigned base(unsigned id, unsigned kind)
{ return 0x10000 * (id + 1) + 0x100 * kind + (changed_dt ? 0x400000 : 0); }
static unsigned required_map_kind(unsigned step)
{
    unsigned index = 0;
#ifdef IN_UNIPHY
    if ((modes & 1) && step == index++) return 0;
#endif
    if ((modes & 2) && step == index++) return 1;
#ifdef DESS
    if ((modes & 4) && step == index++) return 2;
#endif
    fail("MAP_ROLE"); return 0;
}
static void map_info(unsigned id, unsigned kind, ssdk_reg_map_info *map)
{
    cold(); need(id < SW_MAX_NR_DEV, "GETTER_ID");
#ifdef CANDIDATE
    need(id == init_device, "MAP_DEVICE_ROLE");
    need(kind == required_map_kind(init_map_step++), "MAP_ROLE");
#endif
    map->base_addr = base(id, kind); map->size = 0x80;
    requested_map = *map; map_requested = true;
}
static void ssdk_uniphy_reg_map_info_get(unsigned id, ssdk_reg_map_info *map) { map_info(id, 0, map); }
static void ssdk_switch_reg_map_info_get(unsigned id, ssdk_reg_map_info *map) { map_info(id, 1, map); }
static void ssdk_psgmii_reg_map_info_get(unsigned id, ssdk_reg_map_info *map) { map_info(id, 2, map); }
static hsl_reg_mode mode(unsigned id, unsigned bit)
{ cold(); need(id < SW_MAX_NR_DEV, "GETTER_ID"); return modes & bit ? HSL_REG_LOCAL_BUS : HSL_REG_MDIO; }
static hsl_reg_mode ssdk_uniphy_reg_access_mode_get(unsigned id) { return mode(id, 1); }
static hsl_reg_mode ssdk_switch_reg_access_mode_get(unsigned id) { return mode(id, 2); }
static hsl_reg_mode ssdk_psgmii_reg_access_mode_get(unsigned id) { return mode(id, 4); }
static unsigned ssdk_switch_device_num_get(void) { return SW_MAX_NR_DEV; }
static void no_publication(unsigned id)
{
#ifdef CANDIDATE
    need(!slots[id].hw_addr && !slots[id].uniphy_hw_addr && !slots[id].psgmii_hw_addr,
         "EARLY_PUBLICATION");
    need(memcmp(&cfgs[id], &originals[id], sizeof(cfgs[id])) == 0, "EARLY_CFG");
#else
    (void)id;
#endif
}
static void *ioremap(unsigned address, unsigned size)
{
    cold(); need(size == 0x80 && map_count < 32, "MAP_ARGS");
    unsigned id = (address >> 16) - 1;
    need(id < SW_MAX_NR_DEV, "MAP_DEVICE"); no_publication(id);
    need(map_requested && address == requested_map.base_addr && size == requested_map.size,
         "MAP_IDENTITY");
    map_requested = false;
    if (++attempts == fault) return NULL;
    maps[map_count].base = address; maps[map_count].size = size;
    maps[map_count].live = true; return &maps[map_count++].token;
}
static void iounmap(void *p)
{
    cold();
    if (!p) return;
    for (unsigned i = 0; i < map_count; ++i) if (p == &maps[i].token) {
        need(maps[i].live, "MAP_DOUBLE_FREE"); maps[i].live = false; ++unmapped; return;
    }
    fail("UNOWNED_MAP");
}
static struct resource *request_mem_region(unsigned address, unsigned size, const char *name)
{
    cold(); need(size == 0x80 && strcmp(name, "psgmii_mem") == 0, "REGION_ARGS");
    unsigned id = (address >> 16) - 1; need(id < SW_MAX_NR_DEV, "REGION_DEVICE");
    no_publication(id);
    need(map_requested && address == requested_map.base_addr && size == requested_map.size,
         "REGION_IDENTITY");
    if (fault == 10) return NULL;
    need(!regions[id], "REGION_DUPLICATE");
    regions[id] = true; region_base[id] = address; region_size[id] = size; ++claims;
    return &region_tokens[id];
}
static void release_mem_region(unsigned address, unsigned size)
{
    cold();
    for (unsigned id = 0; id < SW_MAX_NR_DEV; ++id)
        if (regions[id] && region_base[id] == address && region_size[id] == size) {
            regions[id] = false; ++releases; return;
        }
    fail("REGION_PAIR");
}
static struct clk *ssdk_dts_essclk_get(unsigned id)
{
    cold(); need(id < SW_MAX_NR_DEV, "GETTER_ID");
    return clock_mode == 3 ? NULL : (clock_mode == 0 || clock_mode == 4 || clock_mode == 6 ? &ess : ERR_CLK);
}
static struct clk *ssdk_dts_cmnclk_get(unsigned id)
{
    cold(); need(id < SW_MAX_NR_DEV, "GETTER_ID");
    return clock_mode == 2 || clock_mode == 6 ? ERR_CLK : (clock_mode == 5 ? NULL : &cmn);
}
static int clk_prepare_enable(struct clk *p)
{
    cold(); ++enables; need(!IS_ERR(p), "CLOCK_BAD_PTR");
    if (clock_mode == 4) return -EIO;
    if (p) { need(p == &ess, "CLOCK_ID"); ++p->refs; }
    return 0;
}
static void clk_disable_unprepare(struct clk *p)
{
    cold(); ++disables; need(!IS_ERR(p), "CLOCK_BAD_PTR");
    if (p) { need(p == &ess && p->refs, "UNOWNED_CLOCK"); --p->refs; }
}
static void ssdk_gcc_clock_init(void)
{ cold(); need(!gcc_live, "GCC_DOUBLE_START"); gcc_live = true; ++gcc_starts; }
static void ssdk_gcc_clock_exit(void)
{ cold(); need(gcc_live, "GCC_DOUBLE_STOP"); gcc_live = false; ++gcc_stops; }
static sw_error_t qca_uniphy_reg_write(unsigned id, unsigned index, unsigned reg, u8 *data, unsigned len)
{ need(id < SW_MAX_NR_DEV && index < 3 && reg < 4096 && data && len == 4, "CALLBACK_ARGS"); return SW_OK; }
static sw_error_t qca_uniphy_reg_read(unsigned id, unsigned index, unsigned reg, u8 *data, unsigned len)
{ return qca_uniphy_reg_write(id, index, reg, data, len); }
static sw_error_t qca_psgmii_reg_write(unsigned id, unsigned reg, u8 *data, unsigned len)
{ return qca_uniphy_reg_write(id, 0, reg, data, len); }
static sw_error_t qca_psgmii_reg_read(unsigned id, unsigned reg, u8 *data, unsigned len)
{ return qca_uniphy_reg_write(id, 0, reg, data, len); }
static sw_error_t saved_uniphy(unsigned id, unsigned index, unsigned reg, u8 *data, unsigned len)
{ return qca_uniphy_reg_write(id, index, reg, data, len); }
static sw_error_t saved_psgmii(unsigned id, unsigned reg, u8 *data, unsigned len)
{ return qca_psgmii_reg_write(id, reg, data, len); }
@ACTUAL_CODE@
static void published_map_identity(u8 *pointer, unsigned id, unsigned kind, bool selected)
{
    need((pointer != NULL) == selected, "MAP_SLOT_IDENTITY");
    if (!selected) return;
    for (unsigned i = 0; i < map_count; ++i) if (pointer == &maps[i].token) {
        need(maps[i].live && maps[i].base == base(id, kind) && maps[i].size == 0x80,
             "MAP_SLOT_IDENTITY");
        return;
    }
    fail("MAP_SLOT_IDENTITY");
}
static void rejected_foreign_exit(unsigned id)
{
#ifdef CANDIDATE
    struct ssdk_plat_resources rights;
    memcpy(&rights, &ssdk_plat_resources[id], sizeof(rights));
    struct qca_phy_priv owner, foreign;
    memcpy(&owner, &slots[id], sizeof(owner));
    memcpy(&foreign, &foreign_slot, sizeof(foreign));
    unsigned maps_before = live_maps();
    unsigned before[] = {attempts, unmapped, claims, releases, enables, disables, gcc_starts, gcc_stops};
    unsigned refs = ess.refs;
    bool live = gcc_live;
#if defined(HPPE) || defined(MP)
    unsigned users = ssdk_plat_gcc_users;
#endif
#endif
    ssdk_plat_exit(id);
#ifdef CANDIDATE
    need(maps_before == live_maps() && memcmp(&owner, &slots[id], sizeof(owner)) == 0 &&
         memcmp(&foreign, &foreign_slot, sizeof(foreign)) == 0, "FOREIGN_RETIRE");
    unsigned after[] = {attempts, unmapped, claims, releases, enables, disables, gcc_starts, gcc_stops};
    need(memcmp(&rights, &ssdk_plat_resources[id], sizeof(rights)) == 0 &&
         memcmp(before, after, sizeof(before)) == 0 && refs == ess.refs && live == gcc_live,
         "FOREIGN_RIGHTS");
#if defined(HPPE) || defined(MP)
    need(users == ssdk_plat_gcc_users, "FOREIGN_RIGHTS");
#endif
#endif
}
static int model_init(unsigned id)
{
    init_device = id; init_map_step = 0; map_requested = false;
    memcpy(&originals[id], &cfgs[id], sizeof(cfgs[id]));
    int rv = ssdk_plat_init(&cfgs[id], id);
    if (!rv) {
        bool uniphy = false, psgmii = false;
#ifdef IN_UNIPHY
        uniphy = !!(modes & 1);
#endif
#ifdef DESS
        psgmii = !!(modes & 4);
#endif
        published_map_identity(slots[id].uniphy_hw_addr, id, 0, uniphy);
        published_map_identity(slots[id].hw_addr, id, 1, !!(modes & 2));
        published_map_identity(slots[id].psgmii_hw_addr, id, 2, psgmii);
    }
    return rv;
}
static void admission_snapshot(unsigned id, int error)
{
    ssdk_init_cfg copy; memcpy(&copy, &cfgs[id], sizeof(copy));
    unsigned before = attempts + enables + gcc_starts + claims + unmapped + releases + disables + gcc_stops;
    need(model_init(id) == error, "ADMISSION_RESULT");
    need(before == attempts + enables + gcc_starts + claims + unmapped + releases + disables + gcc_stops &&
         memcmp(&copy, &cfgs[id], sizeof(copy)) == 0, "ADMISSION_SIDE_EFFECT");
}
static unsigned expected_maps(void)
{
    unsigned n = !!(modes & 2);
#ifdef IN_UNIPHY
    n += !!(modes & 1);
#endif
#ifdef DESS
    n += !!(modes & 4);
#endif
    return n;
}
static bool region_failure(void)
{
#ifdef DESS
    return fault == 10 && (modes & 4);
#else
    return false;
#endif
}
static void clean_all(void)
{
    need(!live_maps(), "MAP_LEAK");
    need(!ess.refs, "CLOCK_LEAK");
    need(!gcc_live, "GCC_LEAK");
    for (unsigned id = 0; id < SW_MAX_NR_DEV; ++id) need(!regions[id], "REGION_LEAK");
#ifdef CANDIDATE
    struct ssdk_plat_resources zero;
    memset(&zero, 0, sizeof(zero));
    for (unsigned id = 0; id < SW_MAX_NR_DEV; ++id)
        need(memcmp(&zero, &ssdk_plat_resources[id], sizeof(zero)) == 0, "LEDGER_LEAK");
#if defined(HPPE) || defined(MP)
    need(ssdk_plat_gcc_users == 0, "GCC_ACCOUNTING");
#endif
#endif
    need(!locked, "LOCK_LEAK");
}
static void exited(unsigned id)
{
    need(!slots[id].hw_addr && !slots[id].uniphy_hw_addr && !slots[id].psgmii_hw_addr, "EXIT_PUBLICATION");
}
int main(int argc, char **argv)
{
    need(argc == 5, "ARGUMENTS");
    modes = (unsigned)strtoul(argv[1], NULL, 10);
    fault = (unsigned)strtoul(argv[2], NULL, 10);
    clock_mode = (unsigned)strtoul(argv[3], NULL, 10);
    unsigned scenario = (unsigned)strtoul(argv[4], NULL, 10);
    need(modes < 8 && fault <= 10 && clock_mode < 7 && scenario < 11, "ARGUMENT_RANGE");
    unsigned initial_modes = modes;
    for (unsigned id = 0; id < SW_MAX_NR_DEV; ++id) {
        table[id] = &slots[id]; cfgs[id].reg_mode = HSL_HEADER; cfgs[id].chip_revision = 99;
        cfgs[id].reg_func.uniphy_reg_get = saved_uniphy;
        cfgs[id].reg_func.uniphy_reg_set = saved_uniphy;
        cfgs[id].reg_func.psgmii_reg_get = saved_psgmii;
        cfgs[id].reg_func.psgmii_reg_set = saved_psgmii;
        memcpy(&originals[id], &cfgs[id], sizeof(cfgs[id]));
    }
    unsigned id = scenario == 7 ? SW_MAX_NR_DEV - 1 : 0;
    if (scenario == 5) {
        need(ssdk_plat_init(NULL, 0) == -EINVAL && ssdk_plat_init(&cfgs[0], SW_MAX_NR_DEV) == -EINVAL, "INVALID_RESULT");
        qca_phy_priv_global = NULL;
        need(ssdk_plat_init(&cfgs[0], 0) == -EINVAL, "INVALID_RESULT");
        qca_phy_priv_global = table; table[0] = NULL;
        need(ssdk_plat_init(&cfgs[0], 0) == -EINVAL, "INVALID_RESULT");
        table[0] = &slots[0]; ssdk_plat_exit(SW_MAX_NR_DEV);
        need(!attempts && !enables && !gcc_starts && !claims, "INVALID_SIDE_EFFECT");
    } else if (scenario == 3) {
        slots[0].hw_addr = &foreign_byte; admission_snapshot(0, -EBUSY); ssdk_plat_exit(0);
        need(slots[0].hw_addr == &foreign_byte, "FOREIGN_CLEAR"); slots[0].hw_addr = NULL;
    } else {
        unsigned n = expected_maps();
        bool failed = (fault && fault <= n) || region_failure();
        int rv = model_init(id);
        need(rv == (failed ? -1 : 0), "RETURN_VALUE");
        if (failed) {
            need(memcmp(&cfgs[id], &originals[id], sizeof(cfgs[id])) == 0 &&
                 !slots[id].hw_addr && !slots[id].uniphy_hw_addr && !slots[id].psgmii_hw_addr, "ERROR_PUBLICATION");
            need(!enables && !gcc_starts, "CLOCK_BEFORE_MAP_COMPLETE");
            ssdk_plat_exit(id); clean_all();
            if (scenario == 8) {
                fault = 0;
                need(model_init(id) == 0, "FAILED_RETRY");
                ssdk_plat_exit(id); exited(id); clean_all();
            }
        } else {
            need(cfgs[id].reg_mode == (modes & 2 ? HSL_HEADER : HSL_MDIO) && cfgs[id].chip_revision == 99, "CFG_MODE");
#ifdef IN_UNIPHY
            if (modes & 1) {
                need(slots[id].uniphy_hw_addr && cfgs[id].reg_func.uniphy_reg_set == qca_uniphy_reg_write, "UNIPHY_PUBLICATION");
                need(cfgs[id].reg_func.uniphy_reg_get == qca_uniphy_reg_read, "UNIPHY_READ_PUBLICATION");
            }
#endif
#ifdef DESS
            if (modes & 4) {
                need(slots[id].psgmii_hw_addr && cfgs[id].reg_func.psgmii_reg_set == qca_psgmii_reg_write, "PSGMII_PUBLICATION");
                need(cfgs[id].reg_func.psgmii_reg_get == qca_psgmii_reg_read, "PSGMII_READ_PUBLICATION");
            }
#endif
            if (scenario == 1) admission_snapshot(id, -EBUSY);
            if (scenario == 4) {
                unsigned count = live_maps(); u8 *saved = slots[id].hw_addr;
                table[id] = &foreign_slot; rejected_foreign_exit(id);
                need(live_maps() == count && !foreign_slot.hw_addr && !foreign_slot.psgmii_hw_addr, "FOREIGN_RETIRE");
                table[id] = &slots[id]; slots[id].hw_addr = &foreign_byte; rejected_foreign_exit(id);
                need(live_maps() == count && slots[id].hw_addr == &foreign_byte, "FOREIGN_RETIRE");
                slots[id].hw_addr = saved;
            }
            if (scenario == 2 || scenario == 6) {
                struct qca_phy_priv owner_snapshot = slots[id];
                if (scenario == 6) fault = attempts + n;
                int peer = model_init(1);
                need(peer == (scenario == 6 && n ? -1 : 0), "PEER_RESULT");
                need(memcmp(&owner_snapshot, &slots[id], sizeof(owner_snapshot)) == 0 && live_for(id) == n,
                     "PEER_IDENTITY_LOSS");
                struct qca_phy_priv peer_snapshot = slots[1];
                if (scenario == 6 && n) {
                    need(live_for(id) == n && !live_for(1), "PEER_MAP_LOSS");
                    need(memcmp(&cfgs[1], &originals[1], sizeof(cfgs[1])) == 0, "ERROR_PUBLICATION");
                }
                ssdk_plat_exit(id); exited(id); ssdk_plat_exit(id);
                if (scenario == 2) {
                    need(!live_for(id) && live_for(1) == n &&
                         memcmp(&peer_snapshot, &slots[1], sizeof(peer_snapshot)) == 0, "PEER_MAP_LOSS");
#if defined(HPPE) || defined(MP)
                    if ((modes & 2) && (clock_mode == 1 || clock_mode == 5))
                        need(gcc_live && gcc_starts == 1 && !gcc_stops, "GCC_PEER_RETIRE");
#endif
                }
                ssdk_plat_exit(1); exited(1);
            } else {
                if (scenario != 10) { changed_dt = true; modes ^= 7; }
                ssdk_plat_exit(id); exited(id); ssdk_plat_exit(id);
            }
            clean_all();
            if (scenario == 9) {
                changed_dt = false; modes = initial_modes;
                need(model_init(id) == 0, "SUCCESS_REINIT");
                ssdk_plat_exit(id); exited(id); clean_all();
            }
        }
    }
    clean_all();
    printf("{\"status\":\"PLATFORM_CASE\",\"maps\":%u,\"unmaps\":%u,\"claims\":%u,\"releases\":%u,\"enables\":%u,\"disables\":%u,\"gcc_starts\":%u,\"gcc_stops\":%u}\n",
           map_count, unmapped, claims, releases, enables, disables, gcc_starts, gcc_stops);
    return 0;
}
