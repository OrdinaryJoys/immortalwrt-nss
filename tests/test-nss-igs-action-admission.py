#!/usr/bin/env python3
"""Offline host contract for complete prepared IGS action init/release bodies.

This is a bounded API/state substitute, not a kernel, firmware or ABI test.
Only newly generated host programs in a newly created output directory run.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    'extract_prepared_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)
REL = 'nss_qdisc/igs/nss_mirred.c'
IFB = 'nss_qdisc/igs/nss_ifb.c'
GCC16 = '/opt/homebrew/bin/gcc-16'
CLANG = '/usr/bin/clang'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def modern(prepared, name):
    """Strictly adapt the signature seam, never the function body.

    init has an unmatched #endif *inside* its complete modern body. release
    has it between signature and opening brace, which the shared reader does
    not accept. Blank exactly that directive at identical offsets for lexical
    discovery, then slice the ORIGINAL bytes using the shared block reader.
    A synthetic #if/#else balances the original directive at compile time.
    """
    text = prepared.read(REL)
    mask = extract.code_mask(text)
    signature = (r'static int nss_mirred_init\(struct net \*net, struct nlattr \*nla,\s*'
                 r'struct nlattr \*est, struct tc_action \*\*tc_act,\s*'
                 r'struct tcf_proto \*tp, u32 flags, struct netlink_ext_ack \*extack\)'
                 if name == 'nss_mirred_init' else
                 r'static void nss_mirred_release\(struct tc_action \*tc_act\)')
    matches = list(re.finditer(r'^' + signature, mask, re.M))
    if len(matches) != 1:
        raise ValueError('expected exact unique modern signature: ' + name)
    match = matches[0]
    if not re.search(r'^#else\s*\Z', mask[:match.start()], re.M):
        raise ValueError('modern signature must immediately follow #else')
    prefix = mask[:match.start()]
    legacy_start = prefix.rfind('#if (LINUX_VERSION_CODE < KERNEL_VERSION(5, 4, 0))')
    if legacy_start < 0 or prefix[legacy_start:].count(name + '(') != 1:
        raise ValueError('missing unique legacy signature envelope')
    discovery = text
    if name == 'nss_mirred_release':
        seam = re.match(r'\s*\n#endif\s*\n\{', mask[match.end():])
        if seam is None:
            raise ValueError('unexpected release signature/#endif/brace seam')
        start = mask.index('#endif', match.end(), match.end() + seam.end())
        discovery = text[:start] + ' ' * len('#endif') + text[start + len('#endif'):]
    # Use the repository reader, including its complete lexical brace scan.
    definitions = list(re.finditer(r'^static (?:int|void) ' + name + r'\(',
                                  extract.code_mask(discovery), re.M))
    selected = next((i for i, row in enumerate(definitions)
                     if row.start() == match.start()), None)
    if selected is None or len(definitions) != 2:
        raise ValueError('expected exactly legacy and modern signatures')
    # Isolate the already-validated modern signature: the shared reader's
    # permissive parameter regex could otherwise span both release signatures.
    raw_discovered = extract.function(discovery[match.start():], name)
    opening = discovery.index('{', match.end())
    end = extract.block_end(text, opening)
    raw = text[match.start():end] + '\n'
    if raw_discovered != discovery[match.start():end] + '\n':
        raise ValueError('shared extractor disagrees with full-body slice')
    envelope = text[legacy_start:end] + '\n'
    adapted = '#if 0\n#error host excludes legacy signature\n#else\n' + raw
    record = dict(source=REL, function=name, bytes=len(raw.encode()), sha256=digest(raw),
                  body_sha256=digest(text[opening:end]),
                  envelope_sha256=digest(envelope), adapted_sha256=digest(adapted),
                  start_line=text.count('\n', 0, match.start()) + 1,
                  end_line=text.count('\n', 0, end) + 1,
                  adaptation='prefix #if 0/#error/#else; original #endif retained; '
                             'release discovery only: offset-preserving blank #endif')
    prepared.extracted.append(record)
    return raw, adapted, envelope, record


def load(root, output, label):
    prepared = extract.Prepared(root)
    raw, code, envelopes, records = {}, {}, {}, []
    for name in ('nss_mirred_init', 'nss_mirred_release'):
        raw[name], code[name], envelopes[name], row = modern(prepared, name)
        records.append(row)
        (output / (label + '-' + name + '.raw.c.txt')).write_text(raw[name])
        (output / (label + '-' + name + '.envelope.c.txt')).write_text(envelopes[name])
        (output / (label + '-' + name + '.adapted.c.txt')).write_text(code[name])
    types = prepared.structure('nss_qdisc/igs/nss_mirred.h', 'nss_mirred_tcf')
    types += prepared.structure('nss_qdisc/igs/nss_ifb.h', 'nss_ifb_info')
    config_enum = extract.structure(prepared.read('nss_qdisc/igs/nss_ifb.h'),
                                    'nss_ifb_if_config', 'enum')
    types += config_enum
    prepared.extracted.append(dict(source='nss_qdisc/igs/nss_ifb.h',
                                   enum='nss_ifb_if_config',
                                   bytes=len(config_enum.encode()), sha256=digest(config_enum)))
    if label == 'baseline':
        if ('tcf_idr_release(*tc_act, bind);' not in raw['nss_mirred_init'] or
                'prepared_binding' in raw['nss_mirred_init']):
            raise ValueError('baseline must contain action admission but predate binding preflight')
        helper_names = ('nss_ifb_bind', 'nss_ifb_delete_if', 'nss_ifb_create_if')
    else:
        helper_names = ('nss_ifb_prepare_bind', 'nss_ifb_abort_bind', 'nss_ifb_bind',
                        'nss_ifb_delete_if', 'nss_ifb_create_if')
    helpers = ''.join(prepared.function(IFB, name) for name in helper_names)
    return dict(prepared=prepared, raw=raw, code=code, types=types, helpers=helpers,
                records=records)


PREFIX = r'''
/* ALL kernel/API/layout effects below are host substitutes, not a target ABI. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint32_t __u32;
#define __rcu
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#ifndef LINUX_VERSION_CODE
#error host version must be explicitly selected
#endif
#define TCA_ACT_FLAGS_BIND 1U
#define TC_NSS_MIRRED_MAX 1
#define TC_NSS_MIRRED_PARMS 1
#define ACT_P_CREATED 1
#define GFP_KERNEL 0
#define NSS_TX_SUCCESS 0
#define NSS_DYNAMIC_INTERFACE_TYPE_IGS 1
#define nss_igs_error(...) ((void)0)
#define nss_igs_info(...) ((void)0)
/* Consume the actual init's unused tp without editing its body or warnings. */
#define ASSERT_RTNL() ((void)tp)
#define spin_lock_bh(lock) ((void)(lock))
#define spin_unlock_bh(lock) ((void)(lock))
#define rcu_dereference_protected(pointer,condition) ((void)(condition),(pointer))
#define rcu_assign_pointer(pointer,value) ((pointer)=(value))
#define tcf_action common.tcfa_action
struct net { int unused; };
struct tcf_proto { int unused; };
struct netlink_ext_ack { int unused; };
struct nss_cmn_msg { int unused; };
struct nss_ctx_instance { int unused; };
struct net_device { const char *name; u32 ifindex; bool ifb; int refs; };
struct list_head { struct list_head *next, *prev; };
struct tc_action { int tcfa_action, refs, binds; bool alive; };
struct tc_action_net { int unused; };
struct tc_nss_mirred { u32 index, from_ifindex, to_ifindex; int action; };
struct nlattr { struct tc_nss_mirred *data; };
static struct tc_action_net action_net;
static unsigned nss_mirred_net_id;
static int nss_mirred_act_ops, nss_mirred_policy;
static int nss_mirred_list_lock, nss_ifb_list_lock;
static struct list_head nss_mirred_list;
'''

MODEL = r'''
static struct net_device from, to, old_to;
static struct nss_mirred_tcf fresh, old;
static struct nss_ifb_info info, sentinel, *local_info;
static struct nss_ctx_instance context;
static struct tc_action *active;
static struct tc_nss_mirred parms;
static struct nlattr attribute;
static bool registered, allocated, from_known, alloc_fail, register_fail, bind_fail;
static bool check_fail, create_fail, missing_parms, existing, in_release;
static bool reset_ok, clear_ok;
static int config_fail, parse_error, slot, module_refs;
static unsigned checks, failures, total_failures;
static unsigned idr_checks, creates, cleanups, releases, callbacks, mutations;
static unsigned allocs, registers, deletes, deallocs, holds, dev_puts, null_lookups;
static unsigned set_igs, set_nh, resets, clears, adds;
static unsigned host_allocs, host_frees, map_publishes;
static bool host_live;
/* FW values: 0 absent, 1 reported ACK, 2 unknown failed configuration effect. */
static int fw_igs, fw_nh;
static const char *case_name;
static char trace[4096];
static size_t trace_used;
static uint64_t signature = UINT64_C(1469598103934665603);
static void check(bool ok) { ++checks; if (!ok) { ++failures; ++total_failures; } }
static void event(const char *name) {
    int n = snprintf(trace + trace_used, sizeof(trace) - trace_used,
                     "%s%s", trace_used ? "," : "", name);
    if (n < 0 || (size_t)n >= sizeof(trace) - trace_used) abort();
    trace_used += (size_t)n;
}
static void mix(unsigned value) { signature ^= value; signature *= UINT64_C(1099511628211); }
static void INIT_LIST_HEAD(struct list_head *h) { h->next=h; h->prev=h; }
static bool valid_list(struct list_head *h) { return h->next && h->prev; }
static bool list_empty(struct list_head *h) {
    bool valid=valid_list(h); check(valid);
    /* Report model failure instead of crashing: negative controls must run. */
    if (!valid) { INIT_LIST_HEAD(h); return true; }
    return h->next == h;
}
static void list_add(struct list_head *h, struct list_head *root) {
    check(valid_list(h) && valid_list(root));
    h->next=root->next; h->prev=root; root->next->prev=h; root->next=h;
    ++adds; event("publish");
}
static void list_del_init(struct list_head *h) {
    check(valid_list(h));
    if (valid_list(h)) { h->prev->next=h->next; h->next->prev=h->prev; }
    INIT_LIST_HEAD(h); event("unlink");
}
static struct nss_mirred_tcf *nss_mirred_get(struct tc_action *a) {
    return (struct nss_mirred_tcf *)a;
}
static void admission(void) {
    ++mutations;
    check(active && active->alive && active->refs > 0 && slot >= 2);
    check(host_live || local_info);
    if (active == &fresh.common) {
        check(valid_list(&fresh.tcfm_list)); check(fresh.tcfm_dev == NULL);
        check(fresh.tcfm_list.next==&fresh.tcfm_list && fresh.tcfm_list.prev==&fresh.tcfm_list);
    }
}
static void *net_generic(struct net *net, unsigned id) {
    (void)net; (void)id; return &action_net;
}
static int nla_parse_nested_deprecated(struct nlattr **arr, int max,
        struct nlattr *nla, int policy, struct netlink_ext_ack *extack) {
    (void)max; (void)policy; (void)extack;
    arr[TC_NSS_MIRRED_PARMS]=missing_parms ? NULL : nla; return parse_error;
}
static void *nla_data(struct nlattr *attr) { return attr->data; }
static struct net_device *__dev_get_by_index(struct net *net, u32 index) {
    (void)net; return index==1 ? &from : index==2 ? &to : NULL;
}
static bool netif_is_ifb_dev(struct net_device *dev) { return dev->ifb; }
static int32_t nss_cmn_get_interface_number_by_dev(struct net_device *dev) {
    return dev==&from && from_known ? 7 : -1;
}
static int32_t nss_cmn_get_interface_number_by_dev_and_type(struct net_device *dev, int type) {
    check(dev==&to && type==NSS_DYNAMIC_INTERFACE_TYPE_IGS); return registered ? 42 : -1;
}
static struct nss_ifb_info *nss_ifb_find_map_dev(struct net_device *dev) {
    return local_info && local_info->map_dev==dev ? local_info : NULL;
}
static struct nss_ifb_info *nss_ifb_find_dev(struct net_device *dev) {
    /* A hostile unrelated entry makes accidental NULL lookups observable. */
    if (!dev) { ++null_lookups; return &sentinel; }
    if (dev==&old_to) return &sentinel;
    return local_info && local_info->ifb_dev==dev ? local_info : NULL;
}
static bool nss_ifb_is_mapped(struct nss_ifb_info *i) { return i->is_mapped; }
static int32_t nss_dynamic_interface_alloc_node(int type) {
    check(type==NSS_DYNAMIC_INTERFACE_TYPE_IGS); admission(); ++allocs; event("create");
    if (alloc_fail) return -1;
    allocated=true; return 42;
}
static int nss_dynamic_interface_dealloc_node(int number, int type) {
    check(number==42 && type==NSS_DYNAMIC_INTERFACE_TYPE_IGS);
    admission(); ++deallocs; allocated=false; event("dealloc"); return NSS_TX_SUCCESS;
}
static void nss_ifb_event_cb(void *data, struct nss_cmn_msg *msg) { (void)data; (void)msg; }
static struct nss_ctx_instance *nss_igs_register_if(int number, int type,
        void (*cb)(void *,struct nss_cmn_msg *), struct net_device *dev, uint32_t features) {
    check(number==42 && type==NSS_DYNAMIC_INTERFACE_TYPE_IGS &&
          cb==nss_ifb_event_cb && dev==&to && features==0);
    admission(); ++registers; event("register");
    if (register_fail) return NULL;
    registered=true; return &context;
}
static void nss_igs_unregister_if(int number) {
    check(number==42); admission(); ++deletes; registered=false; event("delete");
    /* Deliberately do NOT infer that unregister clears unknown FW effects. */
}
static int32_t nss_ifb_config_msg_tx_sync(struct net_device *dev, int32_t number,
                                        int config, void *data) {
    check(dev==&from && number==42 && data==NULL); admission();
    int *fw=config==NSS_IFB_SET_IGS_NODE ? &fw_igs : &fw_nh;
    if (config==NSS_IFB_SET_IGS_NODE) { ++set_igs; event("set_igs"); }
    else { check(config==NSS_IFB_SET_NEXTHOP); ++set_nh; event("set_nh"); }
    *fw=config_fail==config ? 2 : 1; return config_fail==config ? -1 : 0;
}
static void *model_kmalloc(size_t size, int flags) {
    check(size==sizeof(info) && flags==GFP_KERNEL);
    check(active && active->alive && !host_live && !local_info);
    ++host_allocs; event("reserve");
    if (bind_fail) return NULL;
    host_live=true; return &info;
}
#define kmalloc model_kmalloc
static void model_kfree(void *pointer) {
    ++host_frees; event("cancel");
    check(pointer==&info && host_live && local_info!=pointer);
    host_live=false;
}
#define kfree model_kfree
static void nss_ifb_list_add(struct nss_ifb_info *i) {
    admission(); check(host_live && i==&info && local_info==NULL);
    check(valid_list(&i->map_list) && i->is_mapped && i->ifb_dev==&to && i->map_dev==&from);
    ++map_publishes; local_info=i; event("map_publish");
}
static bool nss_ifb_reset_nexthop(struct nss_ifb_info *i) {
    check(in_release); ++resets; event("reset"); i->is_mapped=false; return reset_ok;
}
static bool nss_ifb_clear_igs_node(struct nss_ifb_info *i) {
    check(in_release); ++clears; event("clear"); i->is_mapped=false; return clear_ok;
}
static void dev_hold(struct net_device *dev) {
    check(dev==&to); admission(); ++holds; ++dev->refs; event("dev_hold");
}
static void dev_put(struct net_device *dev) {
    check(in_release && dev && dev->refs>0); ++dev_puts;
    if (dev && dev->refs>0) --dev->refs;
    event("dev_put");
}
static int tcf_idr_check_alloc(struct tc_action_net *tn, u32 *index,
                              struct tc_action **a, int bind) {
    check(tn==&action_net); ++idr_checks; event("idr_check");
    if (check_fail) { check(slot==0); *a=NULL; return -EAGAIN; }
    if (existing) {
        check(*index==37 && slot==3 && old.common.alive);
        ++old.common.refs; old.common.binds+=bind; *a=&old.common; active=*a; return 1;
    }
    check(slot==0); if (!*index) *index=37;
    slot=1; *a=NULL; return 0;
}
static int tcf_idr_create(struct tc_action_net *tn, u32 index, struct nlattr *est,
        struct tc_action **a, int *ops, int bind, bool per_cpu, unsigned flags) {
    (void)est; check(tn==&action_net && index==37 && ops==&nss_mirred_act_ops && per_cpu && !flags);
    check(slot==1); ++creates; event("idr_create");
    if (create_fail) return -ENOMEM;
    memset(&fresh,0,sizeof(fresh)); fresh.common.refs=1; fresh.common.binds=bind;
    fresh.common.alive=true; ++module_refs; slot=2; *a=&fresh.common; active=*a; return 0;
}
static void tcf_idr_cleanup(struct tc_action_net *tn, u32 index) {
    check(tn==&action_net && index==37 && slot==1); ++cleanups; slot=0; event("idr_cleanup");
}
static void nss_mirred_release(struct tc_action *tc_act);
static void tcf_idr_release(struct tc_action *a, int bind) {
    ++releases; event("idr_release");
    check(a && a->alive && a->refs>0 && (!bind || a->binds>0));
    if (!a || !a->alive || a->refs<=0) return;
    --a->refs; a->binds-=bind;
    if (!a->refs) {
        check(a->binds==0); ++callbacks; in_release=true;
        nss_mirred_release(a); in_release=false;
        a->alive=false; --module_refs; slot=0; active=NULL;
    }
}
'''

MAIN = r'''
static void setup(bool have_old, int conflict, bool borrowed) {
    memset(&fresh,0,sizeof(fresh)); memset(&old,0,sizeof(old));
    memset(&info,0,sizeof(info)); memset(&sentinel,0,sizeof(sentinel));
    INIT_LIST_HEAD(&nss_mirred_list);
    from=(struct net_device){.name="host-from",.ifindex=1};
    to=(struct net_device){.name="host-ifb",.ifindex=2,.ifb=true};
    old_to=(struct net_device){.name="host-old",.ifindex=3,.ifb=true,.refs=1};
    parms=(struct tc_nss_mirred){.index=have_old ? 37u : 0u,
                               .from_ifindex=1,.to_ifindex=2,.action=9};
    attribute.data=&parms; existing=have_old; slot=have_old ? 3 : 0;
    module_refs=have_old ? 1 : 0; active=NULL; local_info=NULL;
    sentinel.ifb_dev=&old_to; sentinel.is_mapped=true;
    old.common=(struct tc_action){.tcfa_action=4,.refs=2,.binds=1,.alive=true};
    old.tcfm_dev=&old_to; old.tcfm_from_ifindex=8; old.tcfm_to_ifindex=3;
    INIT_LIST_HEAD(&old.tcfm_list);
    if (have_old) list_add(&old.tcfm_list,&nss_mirred_list);
    if (conflict) {
        local_info=&info; info.is_mapped=conflict!=3;
        info.ifb_dev=conflict==1 ? &old_to : &to;
        info.map_dev=conflict==2 ? &old_to : &from;
        INIT_LIST_HEAD(&info.map_list);
    }
    registered=allocated=borrowed; from_known=true;
    alloc_fail=register_fail=bind_fail=check_fail=create_fail=missing_parms=in_release=false;
    reset_ok=clear_ok=true; config_fail=-1; parse_error=0;
    checks=failures=0; idr_checks=creates=cleanups=releases=callbacks=mutations=0;
    allocs=registers=deletes=deallocs=holds=dev_puts=null_lookups=0;
    set_igs=set_nh=resets=clears=adds=0; fw_igs=fw_nh=0;
    host_allocs=host_frees=map_publishes=0; host_live=false;
    trace_used=0; trace[0]=0;
}
static void report(int rc) {
    printf("{\"case\":\"%s\",\"rc\":%d,\"checks\":%u,\"failures\":%u,"
           "\"idr\":%d,\"module_refs\":%d,\"refs\":%d,\"binds\":%d,"
           "\"release_calls\":%u,\"cleanup_calls\":%u,\"callbacks\":%u,"
           "\"registered\":%s,\"fw_igs\":%d,\"fw_nh\":%d,"
           "\"delete_calls\":%u,\"idr_check_calls\":%u,\"create_calls\":%u,"
           "\"alloc_calls\":%u,\"register_calls\":%u,\"dealloc_calls\":%u,"
           "\"dev_holds\":%u,\"dev_puts\":%u,\"null_lookups\":%u,"
           "\"list_initialized\":%s,\"device_target\":%u,\"host_allocs\":%u,"
           "\"host_frees\":%u,\"host_live\":%s,\"map_publishes\":%u,\"trace\":\"%s\"}\n",
           case_name,rc,checks,failures,slot,module_refs,
           existing ? old.common.refs : fresh.common.refs,
           existing ? old.common.binds : fresh.common.binds,
           releases,cleanups,callbacks,registered ? "true" : "false",
           fw_igs,fw_nh,deletes,idr_checks,creates,allocs,registers,deallocs,
           holds,dev_puts,null_lookups,
           valid_list(existing ? &old.tcfm_list : &fresh.tcfm_list) ? "true" : "false",
           (existing ? old.tcfm_dev : fresh.tcfm_dev) ?
               (existing ? old.tcfm_dev : fresh.tcfm_dev)->ifindex : 0u,
           host_allocs,host_frees,host_live ? "true" : "false",map_publishes,trace);
}
static void old_preserved(void) {
    check(old.common.alive && old.common.refs==2 && old.common.binds==1);
    check(old.common.tcfa_action==4 && old.tcfm_dev==&old_to && old_to.refs==1);
    check(old.tcfm_from_ifindex==8 && old.tcfm_to_ifindex==3);
    check(old.tcfm_list.next==&nss_mirred_list && old.tcfm_list.prev==&nss_mirred_list);
    check(nss_mirred_list.next==&old.tcfm_list && nss_mirred_list.prev==&old.tcfm_list);
    check(slot==3 && module_refs==1 && sentinel.is_mapped);
}
/* Each listed mode selects an actual init error branch or success contrast. */
enum mode { NORMAL, NO_NLA, PARSE, NO_PARMS, ZERO_FROM, ZERO_TO, MISSING_FROM,
    UNKNOWN_FROM, FROM_IFB, MISSING_TO, TO_NOT_IFB, IDR_RACE, IDR_NOMEM,
    FROM_CONFLICT, TO_CONFLICT, ALLOC, REGISTER, IGS, NH, BIND, REUSE,
    REUSE_ALLOC_FAIL, REUSE_IGS_FAIL, REUSE_NH_FAIL };
static void run_case(const char *name, enum mode mode, bool have_old, bool bind, bool borrowed) {
    case_name=name;
    int conflict=mode==FROM_CONFLICT ? 1 : mode==TO_CONFLICT ? 2 :
        (mode==REUSE || mode==REUSE_ALLOC_FAIL || mode==REUSE_IGS_FAIL || mode==REUSE_NH_FAIL) ? 3 : 0;
    setup(have_old,conflict,borrowed);
    switch (mode) {
    case PARSE: parse_error=-ERANGE; break;
    case NO_PARMS: missing_parms=true; break;
    case ZERO_FROM: parms.from_ifindex=0; break;
    case ZERO_TO: parms.to_ifindex=0; break;
    case MISSING_FROM: parms.from_ifindex=99; break;
    case UNKNOWN_FROM: from_known=false; break;
    case FROM_IFB: from.ifb=true; break;
    case MISSING_TO: parms.to_ifindex=99; break;
    case TO_NOT_IFB: to.ifb=false; break;
    case IDR_RACE: check_fail=true; break;
    case IDR_NOMEM: create_fail=true; break;
    case ALLOC: alloc_fail=true; break;
    case REGISTER: register_fail=true; break;
    case IGS: case REUSE_IGS_FAIL: config_fail=NSS_IFB_SET_IGS_NODE; break;
    case NH: case REUSE_NH_FAIL: config_fail=NSS_IFB_SET_NEXTHOP; break;
    case BIND: case REUSE_ALLOC_FAIL: bind_fail=true; break;
    default: break;
    }
    int expected=ACT_P_CREATED;
    if (mode==NO_NLA || mode==NO_PARMS || mode==ZERO_FROM || mode==ZERO_TO ||
        mode==ALLOC || mode==REGISTER || mode==IGS || mode==NH ||
        mode==REUSE_IGS_FAIL || mode==REUSE_NH_FAIL) expected=-EINVAL;
    if (mode==PARSE) expected=-ERANGE;
    if (mode>=MISSING_FROM && mode<=TO_NOT_IFB) expected=-ENODEV;
    if (mode==IDR_RACE) expected=-EAGAIN;
    if (mode==IDR_NOMEM || mode==BIND) expected=-ENOMEM;
    if (mode==FROM_CONFLICT || mode==TO_CONFLICT) expected=-EEXIST;
    bool pre=mode>=NO_NLA && mode<=TO_NOT_IFB;
    if (have_old && bind && !pre) expected=0;
    unsigned attempts=have_old && expected<0 && !pre ? 3u : 1u;
    int rc=0;
    for (unsigned attempt=0; attempt<attempts; ++attempt) {
        struct tc_action *a=NULL;
        rc=nss_mirred_init(NULL,mode==NO_NLA ? NULL : &attribute,NULL,&a,NULL,
                           bind ? TCA_ACT_FLAGS_BIND : 0,NULL);
        check(rc==expected);
        check(!null_lookups && !resets && !clears && !dev_puts && sentinel.is_mapped);
        if (expected<0) {
            check(!holds && !adds);
            if (pre || mode==IDR_RACE || mode==IDR_NOMEM) check(!mutations);
            if (pre) check(!idr_checks && !creates && !cleanups && !releases);
            else if (mode==IDR_RACE) check(idr_checks==1 && !cleanups && !releases && slot==0);
            else if (mode==IDR_NOMEM) check(creates==1 && cleanups==1 && !releases && slot==0);
            else {
                check(releases==attempt+1 && !cleanups);
                if (!have_old) {
                    check(callbacks==1 && slot==0 && module_refs==0 && !fresh.common.alive);
                    check(fresh.common.refs==0 && fresh.common.binds==0 && fresh.tcfm_dev==NULL);
                    check(list_empty(&fresh.tcfm_list) && list_empty(&nss_mirred_list));
                }
            }
            if (have_old) { old_preserved(); check(!callbacks); }
            else check(slot==0 && module_refs==0);
            if (mode==FROM_CONFLICT || mode==TO_CONFLICT) check(info.is_mapped && !mutations);
            if (mode==ALLOC) check(!registered && !allocated && allocs==attempt+1 && !registers);
            if (mode==REGISTER) check(!registered && !allocated && registers==attempt+1 && deallocs==attempt+1);
            /* OPEN S01: retain unknown effects, never invent rollback. */
            if (mode==IGS || mode==REUSE_IGS_FAIL) check(registered && fw_igs==2 && fw_nh==0 && !deletes && !deallocs);
            if (mode==NH || mode==REUSE_NH_FAIL) check(registered && fw_igs==1 && fw_nh==2 && !deletes && !deallocs);
            /* No firmware side effect may precede fallible host reservation. */
            if (mode==BIND) {
                check(registered==borrowed && allocated==borrowed && !allocs && !registers);
                check(!set_igs && !set_nh && !deletes && !deallocs && !fw_igs && !fw_nh);
                check(host_allocs==attempt+1 && !host_frees && !host_live && !map_publishes);
            } else if (mode==ALLOC || mode==REGISTER || mode==IGS || mode==NH) {
                check(host_allocs==attempt+1 && host_frees==attempt+1 && !host_live && !map_publishes);
                check(local_info==NULL);
            } else {
                check(!host_allocs && !host_frees && !host_live && !map_publishes);
            }
            if (mode==REUSE_IGS_FAIL || mode==REUSE_NH_FAIL) {
                check(local_info==&info && !info.is_mapped && info.ifb_dev==&to && info.map_dev==&from);
            }
        } else if (have_old && bind) {
            check(a==&old.common && old.common.refs==3 && old.common.binds==2);
            check(!mutations && !creates && !cleanups && !releases && !callbacks && !holds && !adds);
            check(!host_allocs && !host_frees && !host_live && !map_publishes);
            check(old.tcfm_dev==&old_to && old.common.tcfa_action==4 && sentinel.is_mapped);
            /* The caller owns the added reference; init must not release it. */
            tcf_idr_release(a,bind); old_preserved(); check(!callbacks);
        } else {
            struct nss_mirred_tcf *act=have_old ? &old : &fresh;
            check(a==&act->common && a->alive && a->refs==(have_old ? 3 : 1));
            check(a->binds==(have_old ? 1 : (int)bind));
            check(!cleanups && !releases && !callbacks && holds==1 && to.refs==1);
            check(act->tcfm_dev==&to && act->tcfm_from_ifindex==1 && act->tcfm_to_ifindex==2);
            check(act->common.tcfa_action==9 && local_info && local_info->is_mapped);
            if (local_info) check(local_info->ifb_dev==&to && local_info->map_dev==&from && registered);
            else check(false);
            check(set_igs==1 && set_nh==1 && fw_igs==1 && fw_nh==1);
            check(adds==(have_old ? 0u : 1u) && module_refs==1);
            /* Compare successful observable behavior with baseline, not IDR position. */
            mix((unsigned)rc); mix((unsigned)a->refs); mix((unsigned)a->binds);
            mix(allocs); mix(registers); mix(set_igs); mix(set_nh); mix(holds); mix(adds);
            mix(act->tcfm_to_ifindex); mix(act->tcfm_from_ifindex); mix((unsigned)act->common.tcfa_action);
            const char *igs=strstr(trace,"set_igs"), *nh=strstr(trace,"set_nh");
            const char *hold=strstr(trace,"dev_hold");
            check(igs && nh && hold && igs<nh && nh<hold);
            if (mode!=REUSE && mode!=REUSE_ALLOC_FAIL) {
                const char *reserved=strstr(trace,"reserve"), *published=strstr(trace,"map_publish");
                check(reserved && igs && reserved<igs && published && nh<published && published<hold);
                check(host_allocs==1 && !host_frees && host_live && map_publishes==1);
            } else {
                check(!host_allocs && !host_frees && !host_live && !map_publishes);
            }
            if (!borrowed) {
                const char *create=strstr(trace,",create,"), *reg=strstr(trace,"register");
                if (!create && !strncmp(trace,"create,",7)) create=trace;
                check(create && reg && create<reg && reg<igs);
            }
            if (!have_old) {
                const char *publish=strstr(trace,"publish");
                /* map_publish precedes hold; the final publish must follow it. */
                if (publish && publish<hold) publish=strstr(hold,"publish");
                check(publish && hold<publish);
            }
        }
    }
    report(rc);
}
static void release_case(const char *name, bool linked, bool device, bool mapped, bool fail) {
    case_name=name; setup(false,0,false);
    INIT_LIST_HEAD(&fresh.tcfm_list);
    if (linked) list_add(&fresh.tcfm_list,&nss_mirred_list);
    if (device) { fresh.tcfm_dev=&to; to.refs=1; }
    if (mapped) { local_info=&info; info.ifb_dev=&to; info.is_mapped=true; }
    reset_ok=clear_ok=!fail;
    in_release=true; nss_mirred_release(&fresh.common); in_release=false;
    check(list_empty(&fresh.tcfm_list) && list_empty(&nss_mirred_list));
    check(!null_lookups && sentinel.is_mapped && dev_puts==(unsigned)device);
    check(resets==(unsigned)(device && mapped) && clears==(unsigned)(device && mapped));
    check(to.refs==0 && !deletes && !deallocs);
    if (!device) {
        in_release=true; nss_mirred_release(&fresh.common); in_release=false;
        check(!resets && !clears && !dev_puts && !null_lookups && sentinel.is_mapped);
    }
    report(0);
}
int main(void) {
    /* Older source never frees preflight storage; keep its stub type-checked. */
    (void)model_kfree;
    run_case("normal_new_bind",NORMAL,false,true,false);
    run_case("normal_new_nonbind",NORMAL,false,false,false);
    run_case("normal_borrowed",NORMAL,false,true,true);
    run_case("normal_reuse_entry",REUSE,false,true,true);
    run_case("normal_reuse_allocation_disabled",REUSE_ALLOC_FAIL,false,true,true);
    run_case("reuse_borrowed_set_igs_failure",REUSE_IGS_FAIL,false,true,true);
    run_case("reuse_existing_nonbind_set_nh_failure",REUSE_NH_FAIL,true,false,true);
    run_case("normal_existing_nonbind",NORMAL,true,false,true);
    const char *names[]={"no_nla","parse_error","missing_parms","zero_from","zero_to",
        "missing_from","unknown_from","from_ifb","missing_to","to_not_ifb"};
    for (int mode=NO_NLA; mode<=TO_NOT_IFB; ++mode)
        run_case(names[mode-NO_NLA],(enum mode)mode,false,true,false);
    run_case("idr_check_race",IDR_RACE,false,true,false);
    run_case("idr_create_failure",IDR_NOMEM,false,true,false);
    const char *post[]={"from_conflict","to_conflict","alloc_failure","register_failure",
                        "set_igs_failure","set_nh_failure","binding_failure"};
    for (int mode=FROM_CONFLICT; mode<=BIND; ++mode) {
        for (int binding=0; binding<=1; ++binding) {
            char name[96]; snprintf(name,sizeof(name),"new_%s_%s",post[mode-FROM_CONFLICT],binding?"bind":"nonbind");
            run_case(name,(enum mode)mode,false,binding,false);
        }
        char name[96]; snprintf(name,sizeof(name),"existing_nonbind_%s_replay",post[mode-FROM_CONFLICT]);
        run_case(name,(enum mode)mode,true,false,false);
    }
    run_case("borrowed_binding_failure",BIND,false,true,true);
    run_case("borrowed_set_igs_failure",IGS,false,true,true);
    run_case("borrowed_set_nh_failure",NH,false,true,true);
    run_case("existing_nonbind_borrowed_binding_replay",BIND,true,false,true);
    run_case("existing_bind",NORMAL,true,true,false);
    run_case("existing_bind_allocation_disabled",BIND,true,true,true);
    run_case("existing_bind_from_conflict",FROM_CONFLICT,true,true,true);
    run_case("existing_bind_to_conflict",TO_CONFLICT,true,true,true);
    release_case("release_empty_null",false,false,false,false);
    release_case("release_linked_null",true,false,false,false);
    release_case("release_live",true,true,true,false);
    release_case("release_missing_ifb",true,true,false,false);
    release_case("release_config_failure",true,true,true,true);
    printf("{\"summary\":true,\"failures\":%u,\"normal_signature\":\"%016llx\"}\n",
           total_failures,(unsigned long long)signature);
    return total_failures ? 1 : 0;
}
'''


def changed(code, before, after, count=1):
    if code.count(before) != count:
        raise ValueError('mutation context must match exactly: ' + before)
    return code.replace(before, after)


def variants(candidate, baseline, mutations):
    init = candidate['code']['nss_mirred_init']
    release = candidate['code']['nss_mirred_release']
    rows = [('candidate', init, release, True, None)]
    if baseline:
        rows.append(('baseline', baseline['code']['nss_mirred_init'],
                     baseline['code']['nss_mirred_release'], False, 'borrowed_binding_failure'))
    if mutations:
        rows.extend([
            ('omit-return-reference', changed(init, 'tcf_idr_release(*tc_act, bind);',
                                              '(void)(*tc_act);'), release, False, 'new_from_conflict_bind'),
            ('release-existing-bound', changed(init, 'if (ret && bind) {\n\t\treturn 0;',
                'if (ret && bind) {\n\t\ttcf_idr_release(*tc_act, bind);\n\t\treturn 0;'),
             release, False, 'existing_bind'),
            ('omit-list-init', changed(init, 'INIT_LIST_HEAD(&act->tcfm_list);',
                                       '(void)(&act->tcfm_list);'), release, False, 'new_from_conflict_bind'),
            ('null-release-side-effects', init, changed(release,
                'if (!dev) {\n\t\treturn;',
                'if (!dev) {\n\t\tnss_ifb_reset_nexthop(&sentinel);\n'
                '\t\tnss_ifb_clear_igs_node(&sentinel);\n\t\treturn;'),
             False, 'release_empty_null'),
            ('nss-before-idr', changed(init, 'index = parm->index;',
                'nss_ifb_config_msg_tx_sync(from_dev, 42, NSS_IFB_SET_IGS_NODE, NULL);\n'
                '\tindex = parm->index;'), release, False, 'idr_check_race'),
            ('omit-placeholder-cleanup', changed(init, 'tcf_idr_cleanup(tn, index);',
                                                '(void)tcf_idr_cleanup; (void)index;'),
             release, False, 'idr_create_failure'),
            ('wrong-release-bind', changed(init, 'tcf_idr_release(*tc_act, bind);',
                                           'tcf_idr_release(*tc_act, !bind);'),
             release, False, 'new_from_conflict_bind'),
        ])
    expanded = [(label, init_code, release_code,
                 (baseline if label == 'baseline' else candidate)['helpers'], expected, sensitive)
                for label, init_code, release_code, expected, sensitive in rows]
    if mutations:
        helpers = candidate['helpers']
        reserve = ('\t/* Reserve all fallible local binding storage before any NSS side effect. */\n'
                   '\tprepared_binding = nss_ifb_prepare_bind(ifb_info, &new_binding);\n'
                   '\tif (!prepared_binding) {\n\t\tret = -ENOMEM;\n\t\tgoto init_failed;\n\t}\n\n')
        bind_call = '\tnss_ifb_bind(prepared_binding, from_dev, to_dev, new_binding);'
        late = changed(changed(init, reserve, ''), bind_call, reserve + bind_call)
        expanded.extend([
            ('late-host-reservation', late, release, helpers, False, 'new_binding_failure_bind'),
            ('omit-private-abort', changed(init,
                'nss_ifb_abort_bind(prepared_binding, new_binding);',
                '(void)nss_ifb_abort_bind; (void)prepared_binding;'),
             release, helpers, False, 'new_set_igs_failure_bind'),
            ('abort-borrowed-storage', init, release,
             changed(helpers, 'if (new_entry) {\n\t\tkfree(ifb_info);',
                     'if (new_entry || ifb_info) {\n\t\tkfree(ifb_info);'),
             False, 'reuse_borrowed_set_igs_failure'),
            ('lose-private-ownership', init, release,
             changed(helpers, '*new_entry = true;', '*new_entry = false;'),
             False, 'new_set_igs_failure_bind'),
            ('claim-borrowed-storage', init, release,
             changed(helpers, 'if (ifb_info) {\n\t\treturn ifb_info;',
                     'if (ifb_info) {\n\t\t*new_entry = true;\n\t\treturn ifb_info;'),
             False, 'reuse_borrowed_set_igs_failure'),
            ('omit-binding-publication', changed(init, bind_call,
                '\t(void)nss_ifb_bind; (void)prepared_binding;'),
             release, helpers, False, 'normal_new_bind'),
        ])
    return expanded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clients', type=Path)
    parser.add_argument('--cc', default='cc',
                        help='compiler command (default: %(default)s); Clang: ' + CLANG)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--mutations', action='store_true')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output = args.output.absolute()
    args.output.mkdir(parents=True, exist_ok=False)
    candidate = load(args.clients, args.output, 'candidate')
    baseline = load(args.baseline, args.output, 'baseline') if args.baseline else None
    rows = variants(candidate, baseline, args.mutations)
    records = []
    result_path = args.output / 'RESULT.json'
    metadata = dict(status='INCOMPLETE', records=records, expected_cases_per_variant=54,
                    script_sha256=digest(Path(__file__).read_text()),
                    extractor_sha256=digest((HERE / 'nss-dp-containment/extract_prepared_c.py').read_text()),
                    host_adaptations=dict(prefix=PREFIX, model=MODEL,
                                          compiler_flags=['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror'],
                                          versions=['5.4.0', '6.18.38']),
                    open_findings=['S01 failed configuration FW effect UNKNOWN; registration may remain',
                                   'S03 host-allocation trigger removed; full registration ownership OPEN',
                                   'complete SQM transaction OPEN; no automatic unknown FW cleanup'],
                    scope='Complete actual modern init/release and IFB prepare/abort/bind/create/delete; '
                          'host IDR/ref/bind/module/list/dev/FW and private-allocation substitutes. No real kernel, ABI, '
                          'concurrency, target build, firmware or successful replace expansion.')

    def save():
        metadata['clients'] = candidate['prepared'].manifest()
        metadata['baseline'] = baseline['prepared'].manifest() if baseline else None
        result_path.write_text(json.dumps(metadata, indent=2) + '\n')

    save()
    try:
        for version in ((5, 4, 0), (6, 18, 38)):
            normal = None
            for label, init, release, helpers, expected, sensitive_case in rows:
                source = baseline if label == 'baseline' else candidate
                stem = label + '-' + '.'.join(map(str, version))
                path = args.output / (stem + '.c')
                program = PREFIX + source['types'] + MODEL + helpers + release + init + MAIN
                path.write_text(program)
                command = shlex.split(args.cc) + metadata['host_adaptations']['compiler_flags'] + [
                    '-DLINUX_VERSION_CODE=' + str((version[0] << 16) | (version[1] << 8) | version[2]),
                    str(path), '-o', str(path.with_suffix(''))]
                if args.sanitize:
                    command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                '-fno-omit-frame-pointer']
                record = dict(label=label, version=version, command=command,
                              generated_sha256=digest(program), expected_pass=expected,
                              sensitive_case=sensitive_case)
                records.append(record)
                built = subprocess.run(command, capture_output=True, timeout=90)
                record['compile_returncode'] = built.returncode
                (args.output / (stem + '-compile.stdout')).write_bytes(built.stdout)
                (args.output / (stem + '-compile.stderr')).write_bytes(built.stderr)
                if built.returncode:
                    raise ValueError('COMPILE ERROR (never a negative-control pass): ' + stem)
                ran = subprocess.run([str(path.with_suffix(''))], capture_output=True, timeout=20)
                record['runtime_returncode'] = ran.returncode
                (args.output / (stem + '.stdout')).write_bytes(ran.stdout)
                (args.output / (stem + '.stderr')).write_bytes(ran.stderr)
                parsed = [json.loads(line) for line in ran.stdout.decode().splitlines()]
                if not parsed or parsed[-1].get('summary') is not True:
                    raise ValueError('missing complete runtime summary: ' + stem)
                summary, cases = parsed[-1], parsed[:-1]
                record.update(summary=summary, cases=cases)
                if (len(cases) != metadata['expected_cases_per_variant'] or
                        len({row['case'] for row in cases}) != len(cases)):
                    raise ValueError('incomplete/duplicate runtime cases: ' + stem)
                if (ran.stderr or ran.returncode != (0 if expected else 1) or
                        (summary['failures'] == 0) != expected or
                        summary['failures'] != sum(row['failures'] for row in cases)):
                    raise ValueError('unexpected runtime result: ' + stem)
                if sensitive_case and not any(row['case'] == sensitive_case and row['failures']
                                              for row in cases):
                    raise ValueError('negative control missed its intended case: ' + stem)
                if label == 'candidate':
                    normal = summary['normal_signature']
                if label == 'baseline':
                    if summary['normal_signature'] != normal:
                        raise ValueError('old successful nonbind/new behavior changed')
                    for required in ('new_binding_failure_bind', 'normal_new_bind'):
                        if not any(row['case'] == required and row['failures'] for row in cases):
                            raise ValueError('baseline insensitive to ' + required)
                save()
        metadata['status'] = 'PASS_BOUNDED_HOST_CONTRACT'
        save()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        metadata.update(status='FAIL', error=str(error))
        save()
        raise SystemExit(str(error)) from error
    print(json.dumps(dict(status=metadata['status'], output=str(result_path),
                          variants=len(records)), indent=2))


if __name__ == '__main__':
    main()
