# Core startup ownership fixture

Runs byte-preserved prepared definitions of core_stop, core_start,
core_pdev_create and core_qmi_firmware_ready. Child and Linux APIs are modeled,
not copied implementations. The model distinguishes a fresh MAC registration
from the REGISTERED no-op paths in mac_allocate, mac_register and thermal_register.
The latter thermal no-op has no new resource to unwind after reconfigure's
unregister. This does not repair that separate thermal restoration problem.

The ledger covers 768 combinations of initial/recovery, DBS/non-DBS, NSS on/off,
software/hardware crypto, raw/default frames and every modeled startup failure.
It rejects releasing borrowed MAC ownership, duplicate/skipped thermal cleanup,
leaks of acquired resources and unbalanced core_lock. A clean rollback must permit
a subsequent successful retry. Success paths retain one identical event signature
in the candidate, old source and five deliberately broken cleanup variants.

GCC and Clang ASan/UBSan compile with Wall/Wextra/Werror. Mutants must compile and
fail resource assertions, not trigger a sanitizer or compilation failure. The
first attempted negative-control build exposed an unused fixture variable; the
final variant explicitly consumes that variable without weakening Werror.

Limits: child partial-allocation self-cleanup is a modeled contract; CE pipes,
thermal restoration, NSS internals, live QMI scheduling, firmware/hardware DMA,
remove after failed recovery and actual throughput are not qualified by this test.
REGISTERED writers/callers and the stock hardware DBS condition are reviewed
separately. This is not a target-module or AX6 runtime test.
