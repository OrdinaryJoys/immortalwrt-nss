# IGS Interface Lookup Errors

`014-igs-preserve-interface-lookup-errors.patch` retains the signed return from
the NSS device lookup APIs until the existing negative checks. The fill helper
keeps its existing bool convention: zero succeeds, nonzero fails. Both tx
callers still return failure, and the driver's range backstop is unchanged.

The source regression extracts complete current fill/init/async/sync functions,
driver common initializer, lookup functions, and send/range functions. Actual
status/config/message enums, common header, selected payload structures and
interface-limit macros come from the supplied prepared trees.

```sh
python3 -B tests/test-nss-igs-interface-errors.py CLIENTS_PREPARED \
  --driver DRIVER_PREPARED --baseline OLD_CLIENTS_PREPARED \
  --mutations --output NEW_OUTPUT --cc gcc
python3 -B tests/test-nss-igs-interface-errors.py CLIENTS_PREPARED \
  --driver DRIVER_PREPARED --baseline OLD_CLIENTS_PREPARED \
  --mutations --sanitize --output OTHER_NEW_OUTPUT --cc clang
```

The normal cases check interface/type/version/length, callback/app-data and all
payload fields used by the six selectors, including cleared OPEN/CLOSE payloads.
Registered interface boundary values are distinct from invalid direct-message
values. Negative lookup is produced by the actual driver's registration search,
not by a replacement signedness expression. Fill must leave its output untouched;
both callers must fail before entering the driver, semaphore or waiting paths.
Normal command failures, modeled timeout/NACK, semaphore balance and the driver's
independent invalid-interface rejection are retained. The old source must fail
while preserving the normal field signature. Six compiled runtime negatives
exercise both missing checks, unsigned/narrow types, interface and callback data.

This is an isolated host contract, not a full ABI or module test. The context,
net_device, reduced message union, synchronization/wait, callbacks and actual
command send are substitutes. NSS_NBUF_PAYLOAD_SIZE is a model value; common
message version is the current contract value. The full NSS payload union,
callback execution, wait scheduling, late ACK, device lifetime, firmware, DMA,
kernel concurrency, target compile and performance are not qualified. No real
network, module, device, init or performance command is executed.

`-Wno-type-limits` lets the extracted existing unsigned lower-bound driver check
and deliberately unsigned old/mutated client compile under `-Werror`, so negative
controls must fail at runtime rather than merely by compiler warning.
