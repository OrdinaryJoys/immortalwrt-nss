# NSS connection-table transaction host test

Run against a prepared NSS driver tree that includes the connection-table
change:

```sh
./tests/nss-conn-transaction/run.py --source /path/to/prepared/driver
./tests/nss-conn-transaction/run.py --source /path/to/prepared/driver --sanitize --optimization O1
./tests/nss-conn-transaction/run.py --source /path/to/prepared/driver --cc /path/to/gcc
```

The runner compiles the whole `nss_conn_table.c` after removing only include
directives. It also builds the actual outer status handler, IPv4/IPv6 RX
handlers and TX wrappers, core TX wrappers and command-copy function, and
linear command DMA helper. It extracts message headers, connection payloads,
and constants from the prepared inputs. The host uses reduced IPv4/IPv6
message unions; the full target message struct size is not verified here.
Source hashes and compiler flags are printed, and temporary build products
are deleted on exit.

Each case runs in a fresh process. Tests cover the following:

- Different CE/CME lengths and page orders, every allocation and mapping
  failure prefix, exact unmap/free tuples and order, and size/page-order
  validation of both lengths before allocating either table. DMA address 0
  is valid; a 64-bit mapping error is checked before
  narrowing, and the entire mapped range must fit in the 32-bit FW window.
- Default and invalid requests in LOW, MEDIUM, and normal profiles, IPv4-only
  and IPv6-only builds, dual-family reservation at the exact budget, and
  rollback without changing the other family's accepted count or DMA records.
- Early nested SIZE/CFG ACKs, duplicate/stale responses, wrong context, family,
  type, token, length or count, and token exhaustion. An early CFG ACK cannot
  publish a count before TX succeeds; definite TX failure rolls back even
  after an early ACK, and the next request must get its own ACK.
- Close with a SIZE sender or SIZE RX paused at explicit synchronization gates,
  including after nested CFG completion but before the original sender returns.
  Pending, rejected, malformed, and active published tables keep their
  DMA records; closing during private preparation rolls them back.
- Outer RX rejects truncated backing or payloads and wrong physical cores
  before a table reply can act. A wire-callback sentinel proves that table
  messages bypass legacy callbacks; aligned non-table traffic still follows
  those handlers. Unaligned table replies work through byte copies, while
  unaligned non-table traffic is rejected.
- Public TX entries block table commands without blocking ordinary commands.
  Private TX checks lengths and message type, copies only the declared
  payload, zeroes the tail, and clears the reuse flag. Command DMA tests
  cover zero length/address, native mapping failure and the 32-bit window.

Each negative control applies one source mutation to a temporary copy and must
compile cleanly and exit at its designated fixture assertion. A crash,
sanitizer diagnostic, timeout, warning, or different assertion fails the run.

This is a host test of the transaction unit and the extracted entry points.
The ring, statistics/logging internals, and driver lifecycle are not executed.
Mocked tokens, DMA and wait queues do not establish FW echo, DMA retirement,
module/provider lifetime, Linux locking behavior, or target validation.
No real device, firmware or network is used.
