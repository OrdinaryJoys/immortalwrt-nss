#!/usr/bin/env python3
"""Execute the complete prepared DP callback/helper; kernel queries are models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'dp_extract', HERE / 'nss-dp-containment/extract_prepared_c.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)

PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
enum { NETDEV_CHANGEUPPER = 7, NETDEV_PRECHANGEUPPER = 8,
       NOTIFY_DONE = 0, BR_STATE_FORWARDING = 3 };
struct notifier_block { int unused; };
struct nss_dp_dev { int state, writes; };
struct net_device {
    bool bridge, physical;
    struct net_device *master;
    struct nss_dp_dev *priv;
};
struct netdev_notifier_info { struct net_device *dev; };
struct netdev_notifier_changeupper_info {
    struct netdev_notifier_info info;
    struct net_device *upper_dev;
    bool master, linking;
};
static unsigned locks, unlocks, queries, depth, checks;
static const char *case_name;
static int stp_error;
static void demand(bool condition, const char *reason)
{
    if (!condition) {
        fprintf(stderr, "FAIL:%s:%s\n", case_name, reason);
        exit(86);
    }
}
static void rcu_read_lock(void) { demand(!depth, "nested-rcu"); depth++; locks++; }
static void rcu_read_unlock(void) { demand(depth == 1, "unbalanced-rcu"); depth--; unlocks++; }
static struct net_device *netdev_master_upper_dev_get_rcu(struct net_device *dev)
{
    demand(depth == 1 && dev, "query-lifetime"); queries++; return dev->master;
}
static bool netif_is_bridge_master(struct net_device *dev) { return dev->bridge; }
static struct net_device *netdev_notifier_info_to_dev(void *ptr)
{
    demand(ptr != NULL, "payload-before-admission");
    return ((struct netdev_notifier_info *)ptr)->dev;
}
static bool nss_dp_is_phy_dev(struct net_device *dev) { return dev->physical; }
static struct nss_dp_dev *netdev_priv(struct net_device *dev) { return dev->priv; }
#define netdev_dbg(...) ((void)0)
static int nss_dp_stp_state_set(struct nss_dp_dev *priv, u8 state)
{
    demand(priv != NULL, "private-before-admission");
    demand(!depth, "stp-under-rcu");
    priv->writes++;
    if (!stp_error) priv->state = state;
    return stp_error;
}
'''

MAIN = r'''
static void scenario(const char *name, unsigned long event, bool linking,
    bool was_master, int upper_kind, int current_kind, bool physical,
    bool has_priv, int state, bool missing_info, bool missing_dev, int error)
{
    struct nss_dp_dev priv = { .state = state }, other_priv = { .state = 4 };
    struct net_device bridge = { .bridge = true }, vlan = {0}, bond = {0}, other = {0};
    struct net_device *uppers[] = { NULL, &bridge, &vlan, &bond, &other };
    struct net_device *masters[] = { NULL, &bridge, &bond };
    struct net_device dev = { .physical = physical, .master = masters[current_kind],
        .priv = has_priv ? &priv : NULL };
    struct netdev_notifier_changeupper_info info = {
        .info.dev = missing_dev ? NULL : &dev, .upper_dev = uppers[upper_kind],
        .master = was_master, .linking = linking };
    struct net_device saved_dev = dev, saved_bridge = bridge;
    struct netdev_notifier_changeupper_info saved_info = info;
    bool eligible = event == NETDEV_CHANGEUPPER && !missing_info && !missing_dev &&
        !linking && was_master && upper_kind == 1 && physical && has_priv;
    bool write = eligible && current_kind != 1;
    case_name = name; locks = unlocks = queries = depth = 0; stp_error = error;
    int result = nss_dp_netdev_event(NULL, event, missing_info ? NULL : &info);
    demand(result == NOTIFY_DONE, "notifier-result");
    demand(priv.writes == (int)write && priv.state ==
        (write && !error ? BR_STATE_FORWARDING : state), "stp-ownership");
    demand(!depth && locks == unlocks && queries == locks && locks == (unsigned)eligible,
        "reader-balance");
    demand(!memcmp(&saved_dev, &dev, sizeof(dev)) &&
        !memcmp(&saved_bridge, &bridge, sizeof(bridge)) &&
        !memcmp(&saved_info, &info, sizeof(info)) &&
        other_priv.state == 4 && !other_priv.writes, "foreign-state");
    checks++;
}
static bool witness(const char *selected, const char *name, unsigned long event,
    bool linking, bool master, int upper, int current, bool physical)
{
    if (selected && strcmp(selected, name)) return false;
    scenario(name, event, linking, master, upper, current, physical, true, 4,
        false, false, 0);
    return true;
}
int main(int argc, char **argv)
{
    const char *selected = argc == 2 ? argv[1] : NULL;
    if (argc > 2) return 2;
    witness(selected, "nonmaster-bridge", NETDEV_CHANGEUPPER, false, false, 1, 0, true);
    witness(selected, "vlan-unlink", NETDEV_CHANGEUPPER, false, true, 2, 0, true);
    witness(selected, "still-bridged", NETDEV_CHANGEUPPER, false, true, 1, 1, true);
    witness(selected, "bridge-link", NETDEV_CHANGEUPPER, true, true, 1, 0, true);
    witness(selected, "prechange", NETDEV_PRECHANGEUPPER, false, true, 1, 0, true);
    witness(selected, "nonphysical", NETDEV_CHANGEUPPER, false, true, 1, 0, false);
    witness(selected, "real-detach", NETDEV_CHANGEUPPER, false, true, 1, 0, true);
    if (selected) {
        if (checks != 1) return 2;
    } else {
        for (int event = 7; event <= 8; event++)
        for (int link = 0; link < 2; link++)
        for (int master = 0; master < 2; master++)
        for (int upper = 0; upper < 5; upper++)
        for (int current = 0; current < 3; current++)
        for (int phy = 0; phy < 2; phy++)
        for (int priv = 0; priv < 2; priv++)
        for (int state = 0; state < 5; state++)
        for (int error = 0; error < 2; error++)
            scenario("matrix", event, link, master, upper, current, phy, priv, state,
                false, false, error ? -5 : 0);
        scenario("null-payload", 7, false, true, 1, 0, true, true, 4, true, false, 0);
        scenario("null-device", 7, false, true, 1, 0, true, true, 4, false, true, 0);
        scenario("other-event-null", 1, false, true, 1, 0, true, true, 4, true, false, 0);
    }
    printf("{\"scenarios\":%u,\"failures\":0,\"kernel_and_fal_modeled\":true}\n", checks);
    return 0;
}
'''


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def replace_once(text, old, new):
    require(text.count(old) == 1, 'ambiguous mutation: ' + old)
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.prepared / 'nss_dp_switchdev.c'
    raw = source.read_bytes()
    text = raw.decode()
    helper = extract.function(text, 'nss_dp_is_bridge_port')
    callback = extract.function(text, 'nss_dp_netdev_event')
    old = extract.function((args.baseline / source.name).read_text(), 'nss_dp_netdev_event')
    records = []

    def run(label, body, selected=None, failure=None):
        c = args.output / (label + '.c')
        # The helper remains compiled even if a mutant stops using it.
        c.write_text(PREFIX + helper + body + MAIN)
        command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-parameter', '-Wno-unused-function']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [str(c), '-o', str(c.with_suffix('.host'))]
        result = subprocess.run(command, capture_output=True, timeout=60)
        (args.output / (label + '.compile.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.compile.stderr')).write_bytes(result.stderr)
        require(result.returncode == 0 and not result.stdout and not result.stderr,
                'compile must be clean: ' + label)
        result = subprocess.run([str(c.with_suffix('.host'))] + ([selected] if selected else []),
                                capture_output=True, timeout=30)
        (args.output / (label + '.stdout')).write_bytes(result.stdout)
        (args.output / (label + '.stderr')).write_bytes(result.stderr)
        if failure:
            require(result.returncode == 86 and not result.stdout and
                    result.stderr == ('FAIL:' + failure + ':stp-ownership\n').encode(),
                    'not exact semantic rejection: ' + label)
            detail = {'witness': failure, 'semantic_rejection': True}
        else:
            require(result.returncode == 0 and not result.stderr, 'execution: ' + label)
            detail = json.loads(result.stdout)
            require(detail == {'scenarios': 4810, 'failures': 0,
                               'kernel_and_fal_modeled': True}, 'incomplete positive matrix')
        records.append({'label': label, 'command': command, 'returncode': result.returncode,
                        'c_sha256': hashlib.sha256(c.read_bytes()).hexdigest(), **detail})

    run('candidate', callback)
    run('baseline', old, 'vlan-unlink', 'vlan-unlink')
    mutations = [
        ('master', '!info->master || ', '', 'nonmaster-bridge'),
        ('upper-type', '!netif_is_bridge_master(info->upper_dev)', 'false', 'vlan-unlink'),
        ('current-owner', 'if (nss_dp_is_bridge_port(dev))', 'if (false)', 'still-bridged'),
        ('linking', 'info->linking || ', '', 'bridge-link'),
        ('event', 'event != NETDEV_CHANGEUPPER || ', '', 'prechange'),
        ('physical', '!dev || !nss_dp_is_phy_dev(dev)', '!dev', 'nonphysical'),
        ('lost-detach', 'nss_dp_stp_state_set(dp_priv, BR_STATE_FORWARDING);',
         'if (false) nss_dp_stp_state_set(dp_priv, BR_STATE_FORWARDING);', 'real-detach'),
        ('wrong-state', 'nss_dp_stp_state_set(dp_priv, BR_STATE_FORWARDING);',
         'nss_dp_stp_state_set(dp_priv, 0);', 'real-detach'),
    ]
    for label, before, after, witness_name in mutations:
        run('mutant-' + label, replace_once(callback, before, after), witness_name, witness_name)
    require(source.read_bytes() == raw, 'prepared input changed during test')
    report = {'qualification': 'HOST_CALLBACK_AND_QUERY_MODEL_NOT_KERNEL_OR_HARDWARE',
              'prepared_sha256': hashlib.sha256(raw).hexdigest(), 'records': records}
    (args.output / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_scenarios': 4810, 'exact_runtime_mutants': 8,
                      'baseline_reproduced': True, 'report': str(args.output / 'RESULTS.json')}))


if __name__ == '__main__':
    main()
