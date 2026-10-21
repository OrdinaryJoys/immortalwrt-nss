#!/usr/bin/env python3
"""Actual IGS fill/tx and driver lookup/range paths with isolated host effects."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('extract_c', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('clients', type=Path)
parser.add_argument('--driver', type=Path, required=True)
parser.add_argument('--baseline', type=Path)
parser.add_argument('--cc', default='cc')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--mutations', action='store_true')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
clients = extract.Prepared(args.clients)
driver = extract.Prepared(args.driver)
relative = 'nss_qdisc/igs/nss_ifb.c'
names = ['nss_ifb_config_msg_init', 'nss_ifb_config_msg_fill',
         'nss_ifb_config_msg_tx', 'nss_ifb_config_msg_tx_sync']
body = ''.join(clients.function(relative, name) for name in names)


def enum(text, name):
    return extract.structure(text, name, 'enum')


cmn = driver.read('exports/nss_cmn.h')
if_header = driver.read('exports/nss_if.h')
types = enum(cmn, 'nss_cmn_response')
match = re.findall(r'typedef enum\s*\{[^{}]*\}\s*nss_tx_status_t;', cmn)
if len(match) != 1:
    raise ValueError('expected unique status enum')
types += match[0] + '\n'
types += enum(if_header, 'nss_if_message_types')
types += enum(driver.read('exports/nss_dynamic_interface.h'), 'nss_dynamic_interface_type')
types += enum(clients.read('nss_qdisc/igs/nss_ifb.h'), 'nss_ifb_if_config')
types += driver.structure('exports/nss_cmn.h', 'nss_cmn_msg')
for name in ['nss_if_igs_config', 'nss_if_set_nexthop', 'nss_if_open', 'nss_if_close']:
    types += driver.structure('exports/nss_if.h', name)
api = driver.read('exports/nss_api_if.h') + driver.read('exports/nss_dynamic_interface.h')
constants = ''
for name in ['NSS_MAX_DEVICE_INTERFACES', 'NSS_MAX_NET_INTERFACES',
             'NSS_MAX_PHYSICAL_INTERFACES', 'NSS_MAX_VIRTUAL_INTERFACES',
             'NSS_MAX_TUNNEL_INTERFACES', 'NSS_MAX_SPECIAL_INTERFACES',
             'NSS_MAX_DYNAMIC_INTERFACES', 'NSS_PHYSICAL_IF_START']:
    found = re.findall(r'^#define ' + name + r'\s+[^\n]+', api, re.M)
    if len(found) != 1:
        raise ValueError('expected unique constant: ' + name)
    constants += found[0] + '\n'
common_init = driver.function('nss_cmn.c', 'nss_cmn_msg_init')
lookups = ''.join(driver.function('nss_cmn.c', name) for name in [
    'nss_cmn_get_interface_number_by_dev_and_type', 'nss_cmn_get_interface_number_by_dev'])
send = ''.join(driver.function('nss_if.c', name) for name in [
    'nss_if_tx_msg_with_size', 'nss_if_tx_msg'])
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t nss_ptr_t;
#define NSS_HLOS_MESSAGE_VERSION 1
#define NSS_NBUF_PAYLOAD_SIZE 2048
#define NSS_IFB_MSG_TIMEOUT 1
#define nss_igs_error(...) ((void)0)
#define nss_warning(...) ((void)0)
#define nss_assert assert
'''
models = r'''
/* The selected payload structures and common header are actual source above;
 * this reduced union/context is not a complete kernel message ABI model. */
struct nss_if_msg {
    struct nss_cmn_msg cm;
    union {
        struct nss_if_igs_config config_igs;
        struct nss_if_set_nexthop set_nexthop;
        struct nss_if_open open;
        struct nss_if_close close;
    } msg;
};
struct net_device { bool ifb; const char *name; };
struct nss_subsystem_dataplane_register { struct net_device *ndev; uint32_t type; };
struct nss_ctx_instance { struct nss_subsystem_dataplane_register subsys_dp_register[NSS_MAX_NET_INTERFACES]; };
static struct { int num_nss; struct nss_ctx_instance nss[2]; } nss_top_main;
static struct { int sem, wq; enum nss_cmn_response response; bool cond; } msg_response;
static unsigned checks, failures, cases, context_checks, sends, waits, downs, ups;
static nss_tx_status_t send_status;
static bool wait_success;
static enum nss_cmn_response reply;
static struct nss_if_msg captured;
static uint64_t signature = UINT64_C(1469598103934665603);
static void check(bool condition) { ++checks; if (!condition) ++failures; }
static void mix(uint64_t value) { signature ^= value; signature *= UINT64_C(1099511628211); }
#define NSS_VERIFY_CTX_MAGIC(ctx) do { ++context_checks; check((ctx) == &nss_top_main.nss[0]); } while (0)
static bool netif_is_ifb_dev(struct net_device *dev) { return dev->ifb; }
static struct nss_ctx_instance *nss_igs_get_context(void) { return &nss_top_main.nss[0]; }
static void nss_if_log_tx_msg(struct nss_if_msg *msg) { (void)msg; }
static nss_tx_status_t nss_core_send_cmd(struct nss_ctx_instance *ctx, struct nss_if_msg *msg, size_t size, uint32_t payload) {
    check(ctx == &nss_top_main.nss[0] && size == sizeof(*msg) && payload == NSS_NBUF_PAYLOAD_SIZE);
    ++sends; captured = *msg; return send_status;
}
static void down(int *sem) { ++downs; ++*sem; }
static void up(int *sem) { ++ups; --*sem; }
static unsigned model_wait(void) { ++waits; msg_response.response = reply; msg_response.cond = 0; return wait_success; }
#define wait_event_timeout(wq, condition, timeout) ((void)(wq), (void)(timeout), model_wait())
static void nss_ifb_wake_up_cb(void *data, struct nss_if_msg *msg) { (void)data; (void)msg; }
static void nss_ifb_clear_config_cb(void *data, struct nss_if_msg *msg) { (void)data; (void)msg; }
static void nss_ifb_async_cb(void *data, struct nss_if_msg *msg) { (void)data; (void)msg; }
'''
main = r'''
static int app_data;
static void reset(struct net_device *dev, int index) {
    ++cases; memset(&nss_top_main, 0, sizeof(nss_top_main)); nss_top_main.num_nss = 2;
    if (index >= 0) {
        nss_top_main.nss[0].subsys_dp_register[index].ndev = dev;
        nss_top_main.nss[0].subsys_dp_register[index].type = dev->ifb ? NSS_DYNAMIC_INTERFACE_TYPE_IGS : 0;
    }
    memset(&msg_response, 0, sizeof(msg_response)); memset(&captured, 0, sizeof(captured));
    context_checks = sends = waits = downs = ups = 0;
    send_status = NSS_TX_SUCCESS; wait_success = true; reply = NSS_CMN_RESPONSE_ACK;
}
static void message_check(const struct nss_if_msg *msg, int index, int config, int ifb_num) {
    static const unsigned message_types[] = {NSS_IF_SET_IGS_NODE, NSS_IF_CLEAR_IGS_NODE,
        NSS_IF_SET_NEXTHOP, NSS_IF_RESET_NEXTHOP, NSS_IF_OPEN, NSS_IF_CLOSE};
    void *callback = config <= NSS_IFB_SET_NEXTHOP ?
        (config == NSS_IFB_CLEAR_IGS_NODE ? (void *)nss_ifb_clear_config_cb : (void *)nss_ifb_wake_up_cb) :
        (void *)nss_ifb_async_cb;
    unsigned length = config <= NSS_IFB_CLEAR_IGS_NODE ? sizeof(struct nss_if_igs_config) :
        config <= NSS_IFB_RESET_NEXTHOP ? sizeof(struct nss_if_set_nexthop) :
        config == NSS_IFB_OPEN ? sizeof(struct nss_if_open) : sizeof(struct nss_if_close);
    check(msg->cm.interface == (unsigned)index && msg->cm.type == message_types[config]);
    check(msg->cm.version == NSS_HLOS_MESSAGE_VERSION && msg->cm.len == length);
    check(msg->cm.cb == (nss_ptr_t)callback && msg->cm.app_data == (nss_ptr_t)&app_data);
    if (config <= NSS_IFB_CLEAR_IGS_NODE) check(msg->msg.config_igs.igs_num == ifb_num);
    else if (config <= NSS_IFB_RESET_NEXTHOP) check(msg->msg.set_nexthop.nexthop == (unsigned)ifb_num);
    else if (config == NSS_IFB_OPEN) {
        struct nss_if_open zero = {0}; check(!memcmp(&msg->msg.open, &zero, sizeof(zero)));
    } else { struct nss_if_close zero = {0}; check(!memcmp(&msg->msg.close, &zero, sizeof(zero))); }
    mix(msg->cm.interface); mix(msg->cm.type); mix(msg->cm.len);
    if (config <= NSS_IFB_RESET_NEXTHOP) mix(ifb_num);
}
int main(void) {
    const int indices[] = {-1, 0, 7, 28, 42, NSS_MAX_NET_INTERFACES-1};
    for (int ifb=0; ifb<2; ++ifb) for (int config=0; config<=NSS_IFB_CLOSE; ++config)
    for (unsigned i=0; i<sizeof(indices)/sizeof(indices[0]); ++i) for (int entry=0; entry<3; ++entry) {
        struct net_device dev = {.ifb=ifb,.name="isolated"}; int index=indices[i], ret;
        struct nss_if_msg msg, before; memset(&msg, 0xa5, sizeof(msg)); before=msg;
        reset(&dev,index);
        if (entry==0) ret=nss_ifb_config_msg_fill(&msg,&dev,42,config,&app_data);
        else if (entry==1) ret=nss_ifb_config_msg_tx(&dev,42,config,&app_data);
        else ret=nss_ifb_config_msg_tx_sync(&dev,42,config,&app_data);
        if (index<0) {
            check(ret==(entry==0 ? 1 : -1)); check(!context_checks && !sends && !downs && !ups && !waits);
            if (entry==0) check(!memcmp(&msg,&before,sizeof(msg)));
        } else {
            check(ret==0); message_check(entry==0 ? &msg : &captured,index,config,42);
            check(sends==(entry!=0) && context_checks==(entry==0 ? 0u : 2u));
            check(downs==(entry==2) && ups==(entry==2) && waits==(entry==2));
        }
        check(!msg_response.sem);
    }
    for (int ifb=0; ifb<2; ++ifb) for (int config=0; config<=NSS_IFB_CLOSE; ++config)
    for (int entry=1; entry<3; ++entry) for (int status=NSS_TX_FAILURE; status<NSS_TX_FAILURE_MAX; ++status) {
        struct net_device dev={.ifb=ifb,.name="isolated"}; reset(&dev,42); send_status=status;
        int ret=entry==1 ? nss_ifb_config_msg_tx(&dev,42,config,&app_data) : nss_ifb_config_msg_tx_sync(&dev,42,config,&app_data);
        check(ret==-1 && sends==1 && context_checks==2 && !waits);
        check(downs==(entry==2) && ups==(entry==2) && !msg_response.sem);
        message_check(&captured,42,config,42);
    }
    for (int config=0; config<=NSS_IFB_CLOSE; ++config) for (int failure=0; failure<2; ++failure) {
        struct net_device dev={.ifb=true,.name="isolated"}; reset(&dev,42);
        wait_success=failure!=0; reply=NSS_CMN_RESPONSE_EINTERFACE;
        check(nss_ifb_config_msg_tx_sync(&dev,42,config,&app_data)==-1);
        check(sends==1 && waits==1 && downs==1 && ups==1 && !msg_response.sem);
    }
    /* Downstream backstop is independently retained even for directly formed messages. */
    const uint32_t bad_interfaces[]={NSS_MAX_NET_INTERFACES,65535,UINT32_MAX};
    for (unsigned i=0;i<sizeof(bad_interfaces)/sizeof(bad_interfaces[0]);++i) {
        struct net_device dev={0}; reset(&dev,-1); struct nss_if_msg msg={0};
        msg.cm.type=NSS_IF_OPEN; msg.cm.interface=bad_interfaces[i];
        check(nss_if_tx_msg(nss_igs_get_context(),&msg)==NSS_TX_FAILURE_BAD_PARAM && !sends);
    }
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u,\"normal_signature\":\"%016llx\"}\n",
        cases,checks,failures,(unsigned long long)signature);
    return failures ? 1 : 0;
}
'''
variants = [('candidate', body, True)]
if args.baseline:
    old = (args.baseline / relative).read_text()
    variants.append(('baseline', ''.join(extract.function(old, name) for name in names), False))
if args.mutations:
    def changed(label, before, after, count=1):
        if body.count(before) != count:
            raise ValueError('mutation context: ' + label)
        return (label, body.replace(before, after), False)
    variants.append(changed('unsigned-again', 'int32_t if_src_num;', 'uint32_t if_src_num;'))
    guard = 'if (if_src_num < 0)'
    if body.count(guard) != 2:
        raise ValueError('expected two guards')
    variants += [('missing-ifb-check', body.replace(guard, 'if (false)', 1), False),
                 ('missing-ordinary-check', body.replace(guard, 'if (false)').replace('if (false)', guard, 1), False)]
    variants.append(changed('signed-too-narrow', 'int32_t if_src_num;', 'int8_t if_src_num;'))
    variants.append(changed('wrong-message-interface', 'nss_cmn_msg_init(&ncm->cm, if_num,', 'nss_cmn_msg_init(&ncm->cm, if_num + 1,'))
    variants.append(changed('wrong-callback-data', 'type, len, cb, app_data);',
                            'type, len, cb, app_data ? NULL : app_data);'))
records = []
normal = None
for label, code, expected in variants:
    path = args.output / (label + '.c')
    path.write_text(prefix + constants + types + models + common_init + lookups + send + code + main)
    command = shlex.split(args.cc) + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-type-limits',
                                    str(path), '-o', str(path.with_suffix(''))]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    built = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / (label + '-compile.stderr')).write_bytes(built.stderr)
    if built.returncode:
        raise SystemExit(built.stderr.decode())
    ran = subprocess.run([str(path.with_suffix(''))], capture_output=True, timeout=20)
    (args.output / (label + '.stdout')).write_bytes(ran.stdout)
    (args.output / (label + '.stderr')).write_bytes(ran.stderr)
    result = json.loads(ran.stdout)
    if ran.stderr or ran.returncode != (0 if expected else 1) or (result['failures'] == 0) != expected:
        raise SystemExit('unexpected variant: ' + label)
    if label == 'candidate':
        normal = result['normal_signature']
    if label == 'baseline' and result['normal_signature'] != normal:
        raise SystemExit('normal message signature changed')
    records.append(dict(label=label, command=command, result=result,
                        generated_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
summary = dict(records=records, clients=clients.manifest(), driver=driver.manifest(),
               asset_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               scope='Actual complete fill/init/async/sync, common initializer, lookups, send/range paths and selected enums/structs; modeled context/union, synchronization, callbacks and command transmission. Not full ABI, firmware, late ACK, kernel concurrency or runtime/performance.')
(args.output / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps([dict(label=row['label'], **row['result']) for row in records], indent=2))
