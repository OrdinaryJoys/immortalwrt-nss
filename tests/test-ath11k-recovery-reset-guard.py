#!/usr/bin/env python3
"""Compile the prepared recovery prefix against a modeled IRQ lifecycle.

Pass the fully patched backports directory. This checks call ordering and
reset/crash selection, not real interrupt concurrency or firmware recovery.
"""

from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: test-ath11k-recovery-reset-guard.py <prepared-backports>")
    root = Path(sys.argv[1]) / "drivers/net/wireless/ath/ath11k"
    core = (root / "core.c").read_text()
    start = core.index("static int ath11k_core_reconfigure_on_crash(")
    end = core.index("\tath11k_nss_teardown(ab);", start)
    prefix = core[start:end] + "\tath11k_nss_teardown(ab);\n\treturn 0;\n}\n"
    harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
enum { ATH11K_FLAG_CE_IRQ_ENABLED, ATH11K_FLAG_EXT_IRQ_ENABLED };
struct ath11k_base {
    int core_lock;
    bool is_reset, ahb;
    unsigned long dev_flags;
    int depth, irq_calls, ce_calls, teardown_calls;
};
static int test_bit(int bit, unsigned long *flags) { return !!(*flags & (1UL << bit)); }
static void mutex_lock(int *lock) { (void)lock; }
static void ath11k_hif_irq_disable(struct ath11k_base *ab) {
    ab->irq_calls++;
    /* AHB has a test-and-clear guard; PCIC unconditionally disables each
     * multi-MSI IRQ, even when its NAPI instance was already disabled. */
    if (ab->ahb && !test_bit(ATH11K_FLAG_EXT_IRQ_ENABLED, &ab->dev_flags)) return;
    ab->dev_flags &= ~(1UL << ATH11K_FLAG_EXT_IRQ_ENABLED);
    ab->depth++;
}
static void ath11k_hif_ce_irq_disable(struct ath11k_base *ab) {
    ab->ce_calls++;
    ab->dev_flags &= ~(1UL << ATH11K_FLAG_CE_IRQ_ENABLED);
}
static void ath11k_nss_teardown(struct ath11k_base *ab) {
    /* Verify the quiesce has happened before the first teardown. */
    assert(ab->depth == 1);
    assert(ab->dev_flags == 0);
    ab->teardown_calls++;
}
'''
    harness += prefix
    harness += r'''
int main(void) {
    for (int bus = 0; bus < 2; bus++) {
        for (int reset = 0; reset < 2; reset++) {
            struct ath11k_base ab = {
                .ahb = bus, .is_reset = reset,
                .depth = reset ? 1 : 0,
                .dev_flags = reset ? 0 : 3
            };
            ath11k_core_reconfigure_on_crash(&ab);
            assert(ab.irq_calls == (reset ? 0 : 1));
            assert(ab.ce_calls == (reset ? 0 : 1));
            assert(ab.teardown_calls == 1);
            printf("PASS: bus=%s path=%s depth=%d\n",
                   bus ? "AHB" : "PCIC", reset ? "reset" : "crash", ab.depth);
        }
    }
    struct ath11k_base no_ce = { .ahb = true, .dev_flags = 2 };
    ath11k_core_reconfigure_on_crash(&no_ce);
    assert(no_ce.ce_calls == 0);
    puts("PASS: CE already quiesced; no duplicate CE disable");
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ath11k-recovery-test-") as tmp:
        binary = str(Path(tmp) / "recovery-test")
        subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-variable", "-x", "c", "-o", binary, "-"],
                       input=harness, text=True, check=True)
        subprocess.run([binary], check=True)


if __name__ == "__main__":
    main()
