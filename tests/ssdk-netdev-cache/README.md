# SSDK030 Bounded Cache Retirement Fixture

Author tests, not independent review or kernel/target acceptance. No make, target,
firmware, device, network or old evidence program is invoked. The runner imports
the current parent-owned text preparation helper, freshly replays all 18 declared
patch contexts at exact d9a196497ecee2530722d906e0efe1b7408b6ef6, binds all
692 output files and checks input/output inventories again after host execution.
Existing029 is fixed at a0e19f941d404525dd21bc4c374e577ac3ca8d6663425e2a5a437d36adcf8cd5.

## Source Scope

Complete actual C definitions are extracted without body rewrites for cache
publish/replace/retire/sweep/name/identity/localdev access, ready, actual notifier
callback/admission and registration wrappers, G3, sysfs name consumer, FDB NEW and
EXPIRE consumer, DT accessors, PHY-info getter and property checker. It also
extracts producer mark, the actual HPPE scalar initializer and three read-only
HSL/adapter metadata getters. The manifest
records definition hashes and exact prepared-source coordinates. Both primary
and switch raw cache families are converted together by030. Primary-only mapping
is valid even when optional switch topology is absent. All slots own independent
references; duplicate registration does not add one; detached refs are put outside
the cache lock before callback return. Identity retirement and rename precede
chip/MP/PHY/admission calculations. Static topology stays configured after retire.

`ssdk_port_to_ifname_copy` returns an owned bounded value, never a borrowed name.
Ever-managed cells remain marked through retire/stop, disallowing legacy fallback
when no managed live binding exists. Replacement/re-register may provide a new
live name; late old-owner events cannot retire the replacement. Never-managed
misses still use the original legacy branch, including optional-notifier failure
with zero publications. This preserves stable legacy functionality, NOT its raw
PHY/attached_dev source lifetime, rename, BH safety or root/private ownership.
In-flight never-managed fallback versus first publication/detach is NOT a proven
attachment transaction. A new call after managed retirement cannot fall back.

Optional notifier registration records/logs the exact errno, sweeps incomplete
replay (including the current failing device), and does not acquire notifier
ownership on failure. It remains nonfatal. Repeated register is an owned-only
no-op, preserving the original notifier and cache rather than reacquiring it.
This does not add runtime restart support. Root module init/error policy and
cleanup ordering are text-inspected; full regi_init/regi_exit are not compiled or
invoked. Replay errors after publication are explicit framework fault injections;
stock ssdk_dev_event still returns NOTIFY_DONE, not a naturally failing callback.
Modeled replay rollback excludes the current failed device. This is not execution
of Linux's notifier implementation or its complete namespace/priority protocol.

## Public C APIs

030 adds the actual `bool ssdk_netdev_cache_ready(void)` definition and matching
prototype in the actually installed include/init/ssdk_init.h, using one short
spin_lock_bh domain to read LIVE and
the SDK-style `EXPORT_SYMBOL(ssdk_netdev_cache_ready)`. Source gates check the
prototype/export/short-lock read and the recipe's real InstallDev path, without
changing or executing that recipe. Ready/mark declarations are extracted from the
actual public header and compiled with consumer function-pointer initializers and
type assertions; they are not hand-written consumer externs. The full public
header is retained as data, not compiled as a complete Linux SDK include graph.
Private plat.h does not declare ready. Native compilation replaces EXPORT_SYMBOL with
a retained symbol-name constant; it does NOT generate a Linux export table or
validate modpost, target linking, module loader or built-in configuration.
COLD/STARTING/failure/STOPPED are false; success commits LIVE only after notifier
registration/replay and owned state. The result is an instantaneous snapshot, not
an admission lease or PHY/DSA/FW readiness statement. Future modular selected DP
must prove a strong-symbol provider reference/dependency plus provider root stop
restricted to the proven init/exit interval. A built-in DP cannot depend on a
module-only SSDK provider; built-in/module/link policy requires a separate gate.
No DP/recipe or wire/FW protocol change is made here. DP init remains unapproved.

`bool ssdk_netdev_cache_mark_native_port(a_uint32_t, a_uint32_t)` is also declared
in installed ssdk_init.h and explicitly EXPORT_SYMBOL'd. Only LIVE, device0,
HPPE scalar identity, adapter HPPE_TYPE (not CPPE revision), physical ports1..6,
initialized CPU metadata and a non-CPU port may set the existing managed bit.
No binding, name, reference, HW/PHY/FAL operation or HSL property checker is used.
The three metadata getters read bounded static tables. The actual hsl_dev_init
clears the HSL table; actual hppe_dev_init writes CPU index from cfg.cpu_bmp
before assigning nonzero nr_ports. nr_ports is an initialization witness only,
NOT a maximum physical index. A sparse count2 with CPU3 still allows port6.
Adapter identity defaults unspecified and is initialized in adpt_init; LIVE alone
does not imply device0 metadata, so skipped/mixed/failed metadata is rejected.
These metadata writers are on the stock normal init chain before notifier start;
arbitrary external runtime SDK reinitialization is not certified. Existing
ssdk_init may overwrite an earlier FAL error with PHY-init status; this patch does
not repair or treat that return as a complete initialization certificate.

A successful mark is permanent for the provider module life: failed attach,
failed REGISTER/chip/HSL admission, UNREGISTER and stop do not turn that port into
never-managed legacy. Other unknown legacy ports retain their original branch.
Reassignment of a marked native port to generic legacy without provider reload is
unsupported. Mark itself is not a lease/root lifetime guarantee. Future selected
modular DP must call this actual API before P exposure and both PHY attach paths,
prove strong-symbol/provider lifetime and abort before those actions when false.
No DP caller is added here; native attempts in unchanged DP that never publish a
primary remain an integration gap until that separate producer wiring is done.
Native fixture cases explicitly begin with both attachment directions empty,
call the actual producer API, then model attachment before the actual failed
REGISTER/UNREGISTER/copyAPI sequence. They do not execute Linux PHY attach/detach.

## Native Model

HPPE, HPPE+DSA, APPE+DSA, MP and MP+DSA compile profiles use actual array constants,
actual DT switch/PHY-info/FDB record declarations, and actual mapping constants.
They are not full SDK configurations or target ABI builds. Kernel net_device,
PHY, DSA, private/FDB entry and list infrastructure are minimal native projections;
the exact extracted PHY-info layout uses modeled underlying scalar types. A real
pthread mutex backs the cache spin/BH abstraction; deterministic operation ordering
tests a pinned reader spanning retirement, not a concurrent kernel stress/RCU test.
Every cell and reader token is checked separately. The all-slots test deliberately
seeds extra held cells to check scan bounds; it is not a claim that stock publishers
populate all devices. Mapping/bounds and primary-only tests call the actual writer.
35 complete definitions are extracted. The two DSA-only helpers compile only in
DSA profiles; HPPE scalar init compiles only in HPPE-macro profiles. The unused DT
find(port) accessor is compiled, not invoked. Extraction count is not path/branch
coverage, a kernel ABI claim or an assertion all35 execute in every profile.

The HSL property enum is extracted from actual include/hsl/hsl_port_prop.h before
the actual port_info_t. There is no handwritten int typedef or EXCL_CPU/BUTT
alias: the pinned values are2/5, not the old fixture's1/2. An additional native
case checks all six enum values, five table rows and their distinct bitmaps,
plus domain/device rejection. A wrong-row actual-checker mutant must fail exactly
PROPERTY_ROW_ISOLATION. A separate compiled test-model control recreates the old
1/2 macro projection before the actual table definition and must fail exactly
PROPERTY_ENUM_DOMAIN; it is not counted as a production-code mutant. Earlier
160/31 campaigns retain their old property-model limitation and are not upgraded.

Stable DSA child/ops are fixtures. Local get/put closes only the netdev allocation
claim; generic child teardown, synchronous MHT callbacks, RTNL/API/HSL/MDIO outer
locks and root lifetimes remain OPEN. Actual ref_misc/ref_vlan/MHT callers are not
extracted/executed. Actual FDB consumer runs in a modeled BH scope through a
serialization leaf that retires/renames between snapshot and copying output. It
does not execute genl/socket/module admission. Sysfs formatting/FAL call sites are
actual; FAL is a typed-output leaf, not an implementation of FAL/HW. The first
sanitizer round exposed the existing u8-member-to-fal_pbmp_t pointer cast.030 now
receives into an aligned fal_pbmp_t local, then copies to the existing u8 member,
preserving truncation and prior value on a modeled no-write FAL error. Record
layout/query/error policy is unchanged. Sentinels compare both actual switch
records' dev/connected/netdev-port/dev-id/CPU/standby and every non-output VID,
while independently checking intentional bitmap/VID/athtag outputs. An old-cast
semantic mutant fails the leaf's explicit output-alignment
check before a sanitizer fault, not because a crash counts as success.
PHY fallback/map leaves require a stable fixture attachment; G3 tests balance
netdev refs/all exits/no post-put access without certifying PHY attach lifetime.

## Commands And Oracle

Use a new evidence output each time:

```sh
python3 -B tests/test-ssdk-netdev-cache.py --upstream-cache /Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-ssdk --cc /opt/homebrew/bin/gcc-16 --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/SSDK-CACHE-ADOPT-parent-r4-property-gcc
python3 -B tests/test-ssdk-netdev-cache.py --upstream-cache /Volumes/FX-MD87/Review-AX6/upstreams/nss/qca-ssdk --cc /usr/bin/clang --sanitize --output /Volumes/FX-MD87/Review-AX6/audits/20261030/ssdk-dp-retirement/SSDK-CACHE-ADOPT-parent-r5-property-clang
```

All ordinary candidate and semantic-mutant compiles must succeed with empty
stdout/stderr. Positive runs require exact case stdout, rc0 and empty stderr.
Semantic negatives require rc86, empty stdout and exactly one specified marker;
compile failure, timeout, signal, unrelated/new assertion, sanitizer diagnostic or
extra output is never a semantic PASS. Oracle pollution controls exercise those
rejections. ASan+UBSan uses halt-on-error and disables leak detection explicitly;
no LSan, kernel capability/namespace/RCU, real work drain, IRQ or DMA claim is made.
Two standalone ASan/UBSan activation canaries are compiled/run only in the
sanitized profile and recorded separately as expected sanitizer failures, never
semantic negatives. Both ASAN_OPTIONS and UBSAN_OPTIONS specify the SAME per-case
CommonFlags exitcode and abort_on_error=0: ASan UAF must exit exactly97; UBSan
overflow exactly98. A signal, wrong exit, or diagnostic without the exact exit
fails activation. Actual runtime environments are recorded for every command.
Seven text-gate controls remove public ready/mark declarations/exports, contaminate
optional init policy, add a forbidden mark property call, and inject a raw reader. Those are
uncompiled minimal text trees, not firmware/source preparation qualification.
Raw compiler/run commands, streams, hashes and end-inventory checks are retained.
029/private/sysfs/genl/module lifetime is not globally certified by these030 tests.
