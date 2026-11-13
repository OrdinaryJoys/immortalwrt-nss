/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>
#include <sys/types.h>

#define loff_t test_loff_t
typedef long long loff_t;
#define __user
#define PAGE_SIZE 4096
#define TMPBUFLEN 22
#define SYSCTL_WRITES_STRICT 1
#define SYSCTL_WRITES_WARN 0
static int sysctl_writes_strict = SYSCTL_WRITES_STRICT;
struct ctl_table { void *data; int maxlen; const char *procname; };
struct nss_ctx_instance { bool ready; };
#define NSS_CORE_0 0
static struct { struct nss_ctx_instance nss[2]; } nss_top_main;
static struct { uint32_t coredump; } nss_cmd_buf;
static int nss_ctl_debug;
static int sends, stores, ready_checks, failures, cases;
static bool accepting, interleave;
static const char *case_name;
static const char proc_wspace_sep[] = { ' ', '\t', '\n' };
#define printk(...) ((void)0)
static void warn_sysctl_write(const struct ctl_table *p) { (void)p; }
static bool nss_sysctl_ctx_ready(struct nss_ctx_instance *p)
{ ready_checks++; return p->ready; }
static bool nss_coredump_request(struct nss_ctx_instance *p)
{ (void)p; if (!accepting) return false; sends++; return true; }

/* Model a second completed policy write immediately after the snapshot load. */
static uint32_t snapshot(uint32_t *p)
{
    uint32_t value = *p;
    if (interleave && p == &nss_cmd_buf.coredump) {
        interleave = false; *p = 7;
    }
    return value;
}
static void publish(void *p, uint32_t value)
{
    if (p == &nss_cmd_buf.coredump) stores++;
    memcpy(p, &value, sizeof(value));
}
#define READ_ONCE(x) ((__typeof__(x))snapshot((uint32_t *)&(x)))
#define WRITE_ONCE(x, v) publish(&(x), (uint32_t)(v))
/* Only this numeric conversion primitive is a libc stand-in; tests use small decimal values. */
static int strtoul_lenient(const char *p, char **end, unsigned base, unsigned long *value)
{
    errno = 0; *value = strtoul(p, end, base); return errno ? -ERANGE : 0;
}

/* ACTUAL_PARSER_SOURCE */

/* ACTUAL_HANDLER_SOURCE */

static void check(bool ok, const char *id)
{ if (!ok) { printf("FAIL %s:%s\n", case_name, id); failures++; } }
static void run_case(const char *name, const char *input, size_t length, int write,
                     int debug, bool ready, bool open, uint32_t old, bool race,
                     int expected_ret, uint32_t expected_value, int expected_sends,
                     int expected_stores, int expected_checks)
{
    case_name = name; cases++;
    nss_ctl_debug = debug; accepting = open; interleave = race;
    nss_top_main.nss[0].ready = ready; nss_cmd_buf.coredump = old;
    sends = stores = ready_checks = 0;
    struct ctl_table ctl = { &nss_cmd_buf.coredump, sizeof(int), "coredump" };
    char buffer[32] = {0}; memcpy(buffer, input, strlen(input));
    size_t len = length; loff_t pos = 0;
    int ret = nss_coredump_handler(&ctl, write, buffer, &len, &pos);
    check(ret == expected_ret, "errno");
    check(nss_cmd_buf.coredump == expected_value, "policy");
    check(sends == expected_sends, "sends");
    check(stores == expected_stores, "stores");
    check(ready_checks == expected_checks, "readiness");
    if (!length) check(!len && !pos, "empty-position");
    check(ctl.data == &nss_cmd_buf.coredump, "descriptor");
}

static void parser_contracts(void)
{
    struct ctl_table ctl;
    uint32_t value;
    char input[] = "2";
    size_t len;
    loff_t pos;
    ctl.data = &value; ctl.maxlen = sizeof(int); ctl.procname = "parser";
    case_name = "parser-empty"; cases++; value = 1; len = 0; pos = 4;
    sysctl_writes_strict = SYSCTL_WRITES_STRICT;
    check(proc_dointvec(&ctl, 1, input, &len, &pos) == 0, "errno");
    check(value == 1 && len == 0 && pos == 4, "noop");

    case_name = "parser-offset-strict"; cases++; value = 1; len = 1; pos = 4;
    check(proc_dointvec(&ctl, 1, input, &len, &pos) == 0, "errno");
    check(value == 1 && len == 1 && pos == 5, "ignored-consumed-position");

    case_name = "parser-offset-legacy"; cases++; value = 1; len = 1; pos = 4;
    sysctl_writes_strict = -1;
    check(proc_dointvec(&ctl, 1, input, &len, &pos) == 0, "errno");
    check(value == 2 && len == 1 && pos == 5, "accepted");
    sysctl_writes_strict = SYSCTL_WRITES_STRICT;
}

/* Preserve and expose the separate nonempty-offset behavior, not a fix for it. */
static void offset_regression(bool strict)
{
    case_name = strict ? "offset-strict" : "offset-legacy"; cases++;
    struct ctl_table ctl = { &nss_cmd_buf.coredump, sizeof(int), "coredump" };
    nss_cmd_buf.coredump = 1; nss_ctl_debug = 0; interleave = false;
    nss_top_main.nss[0].ready = true; accepting = true;
    stores = sends = ready_checks = 0;
    char input[] = "2"; size_t len = 1; loff_t pos = 4;
    sysctl_writes_strict = strict ? SYSCTL_WRITES_STRICT : -1;
    check(nss_coredump_handler(&ctl, 1, input, &len, &pos) == 0, "errno");
    check(nss_cmd_buf.coredump == (strict ? 1u : 2u), "policy");
    check(stores == 1, "stores");
    check(!sends && !ready_checks && len == 1 && pos == 5, "unchanged-contract");
    sysctl_writes_strict = SYSCTL_WRITES_STRICT;
}

int main(void)
{
    parser_contracts();
    run_case("empty-live", "", 0, 1, 1, true, true, 1, false, 0, 1, 0, 0, 0);
    run_case("empty-cold", "", 0, 1, 1, false, true, 1, false, 0, 1, 0, 0, 0);
    run_case("empty-closed", "", 0, 1, 1, true, false, 1, false, 0, 1, 0, 0, 0);
    run_case("empty-debug-off", "", 0, 1, 0, true, true, 2, false, 0, 2, 0, 0, 0);
    run_case("empty-interleaved", "", 0, 1, 0, true, true, 2, true, 0, 7, 0, 0, 0);
    run_case("read", "", 8, 0, 1, true, true, 1, false, 0, 1, 0, 0, 0);
    run_case("empty-read", "", 0, 0, 1, true, true, 1, false, 0, 1, 0, 0, 0);
    run_case("invalid", "x", 1, 1, 1, true, true, 1, false, -EINVAL, 1, 0, 0, 0);
    run_case("whitespace", " ", 1, 1, 1, true, true, 1, false, -EINVAL, 1, 0, 0, 0);
    run_case("trigger", "1", 1, 1, 1, true, true, 2, false, 0, 1, 1, 1, 1);
    run_case("trigger-cold", "1", 1, 1, 1, false, true, 2, false, -ENODEV, 2, 0, 0, 1);
    run_case("trigger-closed", "1", 1, 1, 1, true, false, 2, false, -ESHUTDOWN, 1, 0, 1, 1);
    run_case("policy", "2", 1, 1, 1, false, false, 1, false, 0, 2, 0, 1, 0);
    run_case("debug-off", "1", 1, 1, 0, false, false, 2, false, 0, 1, 0, 1, 0);
    offset_regression(true);
    offset_regression(false);
    printf("SUMMARY cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}

