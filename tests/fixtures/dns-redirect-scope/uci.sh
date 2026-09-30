#!/bin/sh
# Offline fixture: never invoke a real UCI process.
case "$*" in
	'-q export network')
		[ "${DNS_SCOPE_TEST_STATE:-absent}" != unreadable ] || exit 1
		printf 'package network\n'
		;;
	'-q get network.globals.dns_redirect_networks')
		case "${DNS_SCOPE_TEST_STATE:-absent}" in
			# Real uci_set("") deletes the option, so GET then returns not-found.
			# Verified against locked UCI 66127cd, list.c uci_set()/cli.c CMD_GET.
			absent|unreadable|deleted-empty) exit 1 ;;
			empty) printf '\n' ;;
			custom) printf '%s\n' "${DNS_SCOPE_TEST_NETWORKS:-}" ;;
			*) exit 2 ;;
		esac
		;;
	*) exit 2 ;;
esac
