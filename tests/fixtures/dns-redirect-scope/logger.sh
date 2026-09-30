#!/bin/sh
# Keep fixture messages local, never send to the host's system logger.
printf '%s\n' "$*" >> "$DNS_SCOPE_TEST_LOG"
