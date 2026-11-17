#!/usr/bin/env python3
"""Exercise the AX6 hostapd and prepared netifd/odhcpd functions on the host."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def function(path, return_type, name):
    text = path.read_text()
    match = re.search(
        r"^static " + re.escape(return_type) + r"(?:\n| ?)" + re.escape(name)
        + r"\([^\n]+\)\n\{.*?^\}", text, re.S | re.M,
    )
    if not match:
        raise ValueError(f"missing controlled function {name} in {path}")
    return match[0]


HOSTAPD_SHIM = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>

typedef struct { int unused; } uc_vm_t;
typedef struct { void *data; } uc_value_t;
struct hostapd_bss_config { int unused; };
struct hostapd_config { struct hostapd_bss_config **bss; size_t num_bss; };
struct hostapd_iface {
    size_t num_bss;
    struct hostapd_data **bss;
    struct hostapd_config *conf;
};
struct hostapd_data {
    struct hostapd_iface *iface;
    struct hostapd_bss_config *conf;
    int interface_added;
};
static struct hostapd_iface *current;
static struct hostapd_data *first;
static uc_value_t list[2], ok;
enum { UC_ARRAY = 1 };
#define uc_fn_thisval(type) (current)
#define uc_fn_arg(index) (list)
#define ucv_type(v) (UC_ARRAY)
#define ucv_array_length(v) ((size_t)2)
#define ucv_array_get(v, i) (&(v)[i])
#define ucv_resource_data(v, type) ((v)->data)
#define ucv_boolean_new(v) ((v) ? &ok : NULL)
#define hostapd_drv_set_first_bss(bss) (first = (bss))
"""

HOSTAPD_CASES = r"""
int main(void) {
    struct hostapd_bss_config c0, c1;
    struct hostapd_config cfg = {calloc(2, sizeof(*cfg.bss)), 2};
    struct hostapd_iface iface = {2, calloc(2, sizeof(*iface.bss)), &cfg};
    struct hostapd_iface foreign = {0};
    struct hostapd_data a = {&iface, &c0, 0}, b = {&iface, &c1, 1};
    struct hostapd_data alien = {&foreign, &c1, 1};
    assert(cfg.bss && iface.bss);
    iface.bss[0] = &a;
    iface.bss[1] = &b;
    cfg.bss[0] = &c0;
    cfg.bss[1] = &c1;
    current = &iface;
    void *invalid[] = {NULL, &alien, &a};
    for (size_t i = 0; i < sizeof(invalid) / sizeof(*invalid); i++) {
        list[0].data = &a;
        list[1].data = invalid[i];
        assert(!uc_hostapd_iface_set_bss_order(NULL, 1));
        assert(iface.bss[0] == &a && iface.bss[1] == &b && !first);
        assert(cfg.bss[0] == &c0 && cfg.bss[1] == &c1);
        assert(!a.interface_added && b.interface_added);
    }
    list[0].data = &b;
    list[1].data = &a;
    assert(uc_hostapd_iface_set_bss_order(NULL, 1) == &ok);
    assert(first == &b && iface.bss[1] == &a);
    assert(cfg.bss[0] == &c1 && cfg.bss[1] == &c0);
    assert(!b.interface_added && a.interface_added);
    free(cfg.bss);
    free(iface.bss);
    return 0;
}
"""

NETIFD_SHIM = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

struct device { unsigned int vlan_aliases; };
struct parent { struct device *dev; };
struct vlandev_device {
    struct device dev;
    struct parent parent;
    bool vid_invalid;
    int config;
    int (*set_state)(struct device *, bool);
};
static int claims, creates, deletes, releases, state_rc, create_rc, claim_rc;
static int device_claim(struct parent *p) { assert(p); claims++; return claim_rc; }
static void device_release(struct parent *p) { assert(p); releases++; }
static int system_vlandev_add(struct device *d, struct device *p, int *config) {
    assert(d && p && config);
    creates++;
    return create_rc;
}
static void system_vlandev_del(struct device *d) { assert(d); deletes++; }
static int set_state(struct device *d, bool up) { assert(d && up); return state_rc; }
static unsigned int *kvlist_get(unsigned int *aliases, const char *key) {
    return !strcmp(key, "guest") ? aliases : NULL;
}
#define D(category, ...)
"""

NETIFD_CASES = r"""
int main(void) {
    struct device parent = { 200 };
    struct vlandev_device v = {
        .parent = { &parent },
        .vid_invalid = true,
        .set_state = set_state,
    };
    assert(vlandev_get_vid(&parent, "") < 0);
    assert(vlandev_get_vid(NULL, "guest") < 0);
    assert(vlandev_get_vid(&parent, "missing") < 0);
    assert(vlandev_get_vid(&parent, "4095") < 0);
    assert(vlandev_get_vid(&parent, "184467440737095516160") < 0);
    assert(vlandev_get_vid(&parent, "0") == 0);
    assert(vlandev_get_vid(&parent, "1") == 1);
    assert(vlandev_get_vid(&parent, "4094") == 4094);
    assert(vlandev_get_vid(&parent, "guest") == 200);
    parent.vlan_aliases = 5000;
    assert(vlandev_get_vid(&parent, "guest") < 0);
    assert(vlandev_set_up(&v) == -EINVAL);
    assert(!claims && !creates && !deletes && !releases);
    v.vid_invalid = false;
    claim_rc = -EACCES;
    assert(vlandev_set_up(&v) == -EACCES && claims == 1 && !creates && !releases);
    claim_rc = 0;
    create_rc = -EIO;
    assert(vlandev_set_up(&v) == -EIO && creates == 1 && releases == 1 && !deletes);
    create_rc = 0;
    state_rc = -EPERM;
    assert(vlandev_set_up(&v) == -EPERM && deletes == 1 && releases == 2);
    state_rc = 0;
    assert(!vlandev_set_up(&v) && claims == 4 && creates == 3);
    assert(deletes == 1 && releases == 2);
    return 0;
}
"""

ODHCPD_CASES = r"""
int main(void) {
    char buf[64], small[5];
    assert(!strcmp(statefiles_escape_hostname(buf, sizeof(buf),
        " AX6\n#\t<>\\\xff"), "\\x20AX6\\x0a\\x23\\x09\\x3c\\x3e\\x5c\\xff"));
    assert(!strcmp(statefiles_escape_hostname(buf, sizeof(buf),
        "valid-Device_1.local"), "valid-Device_1.local"));
    assert(!strcmp(statefiles_escape_hostname(small, sizeof(small), "\nA"), "\\x0a"));
    assert(!strcmp(statefiles_escape_hostname(small, 4, "\n"), ""));
    assert(!strcmp(statefiles_escape_hostname(small, sizeof(small), "ABCDE"), "ABCD"));
    return 0;
}
"""


def exercise(name, contents):
    with tempfile.TemporaryDirectory() as tmp:
        source, binary = Path(tmp, name + ".c"), Path(tmp, name)
        source.write_text("\n".join(contents))
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-Wno-unused-parameter", "-o", binary, source], check=True)
        subprocess.run([binary], check=True)
    print(f"{name}: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--prepared-netifd", required=True, type=Path)
    parser.add_argument("--prepared-odhcpd", required=True, type=Path)
    args = parser.parse_args()
    netifd = args.prepared_netifd / "vlandev.c"
    hostapd = args.source / "package/network/services/hostapd/src/src/ap/ucode.c"
    exercise("hostapd-bss-order", [HOSTAPD_SHIM, function(hostapd, "uc_value_t *",
              "uc_hostapd_iface_set_bss_order"), HOSTAPD_CASES])
    exercise("netifd-vid", [NETIFD_SHIM, function(netifd, "int", "vlandev_get_vid"),
              function(netifd, "int", "vlandev_set_up"), NETIFD_CASES])
    exercise("odhcpd-lease-hostname", ["#include <assert.h>\n#include <stdio.h>\n#include <string.h>",
              function(args.prepared_odhcpd / "src/statefiles.c", "const char *",
                       "statefiles_escape_hostname"), ODHCPD_CASES])


if __name__ == "__main__":
    main()
