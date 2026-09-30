#!/usr/bin/env python3
"""Exercise prepared APuP error blocks and RRM dispatch with mocked callees.

This checks branch/call behavior, not over-the-air APuP or RRM operation.
"""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

if len(sys.argv) != 2:
    raise SystemExit('usage: test-hostapd-targeted-regressions.py <prepared-hostapd>')
root = Path(sys.argv[1])
apup = (root / 'src/ap/apup.c').read_text()
rrm = (root / 'src/ap/rrm.c').read_text()
start = apup.index('sta_ret = ap_sta_add(hapd, mgmt->bssid);')
allocation = apup[start:apup.index('/* TODO:', start)]
start = apup.index('if (hostapd_get_aid(hapd, sta_ret) < 0)')
aid = apup[start:apup.index('\n\t}', start) + 3]
start = rrm.index('case WLAN_RRM_LINK_MEASUREMENT_REPORT:')
dispatch = rrm[start + len('case WLAN_RRM_LINK_MEASUREMENT_REPORT:'):rrm.index('break;', start)]

model = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
struct hostapd_data { int unused; };
struct ieee80211_mgmt { unsigned char bssid[6]; };
struct sta_info { int unused; };
static struct sta_info peer;
static bool allocation_fails, aid_fails, reached, pending;
static int freed, native_events, ubus_events;
#define MSG_INFO 0
#define wpa_printf(...) ((void)0)
static struct sta_info *ap_sta_add(struct hostapd_data *h, const unsigned char *addr) {
    (void)h; (void)addr; return allocation_fails ? NULL : &peer;
}
static int hostapd_get_aid(struct hostapd_data *h, struct sta_info *s) {
    (void)h; (void)s; return aid_fails ? -1 : 0;
}
static void ap_free_sta(struct hostapd_data *h, struct sta_info *s) {
    (void)h; (void)s; freed++;
}
static void hostapd_handle_link_mesr_report(struct hostapd_data *h, const unsigned char *b, size_t l) {
    (void)h; (void)b; (void)l; pending = false; native_events++;
}
static void hostapd_ubus_handle_link_measurement(struct hostapd_data *h, const unsigned char *b, size_t l) {
    (void)h; (void)b; (void)l; ubus_events++;
}
'''
wrappers = (
    'static void check_alloc(struct hostapd_data *hapd, struct ieee80211_mgmt *mgmt) {\n'
    'struct sta_info *sta_ret;\n' + allocation + '\n(void)sta_ret; reached = true;\n}\n' +
    'static void check_aid(struct hostapd_data *hapd, struct sta_info *sta_ret) {\n' +
    aid + '\nreached = true;\n}\n' +
    'static void check_rrm(struct hostapd_data *hapd, const unsigned char *buf, size_t len) {\n' +
    dispatch + '\n}\n'
)
checks = r'''
#define CHECK(x, msg) do { if (!(x)) { fprintf(stderr, "FAIL: %s\n", msg); failures++; } } while (0)
int main(void) {
    int failures = 0;
    struct hostapd_data hapd = {0}; struct ieee80211_mgmt mgmt = {{0}};
    allocation_fails = true; reached = false; check_alloc(&hapd, &mgmt);
    CHECK(!reached, "allocation failure must return before peer dereference");
    allocation_fails = false; reached = false; check_alloc(&hapd, &mgmt);
    CHECK(reached, "successful allocation must continue");
    aid_fails = true; reached = false; freed = 0; check_aid(&hapd, &peer);
    CHECK(!reached && freed == 1, "AID failure must free the partially created station exactly once");
    aid_fails = false; reached = false; freed = 0; check_aid(&hapd, &peer);
    CHECK(reached && freed == 0, "successful AID must retain station");
    pending = true; native_events = ubus_events = 0; check_rrm(&hapd, NULL, 0);
    CHECK(!pending && native_events == 1 && ubus_events == 1, "RRM must dispatch native and ubus handlers once");
    if (failures) return 1;
    puts("PASS: 5 prepared hostapd APuP/RRM control-flow scenarios");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='hostapd-regression-') as tmp:
    src, binary = Path(tmp) / 'check.c', Path(tmp) / 'check'
    src.write_text(model + wrappers + checks)
    subprocess.run(shlex.split(os.environ.get('CC', 'cc')) +
                   ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                    str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
