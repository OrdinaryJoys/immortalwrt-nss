#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
D1="$ROOT/package/qca-nss/qca-nss-dp/patches/008-edma-v1-correctness-prerequisites.patch"
D2="$ROOT/package/qca-nss/qca-nss-dp/patches/009-edma-v1-split-napi-candidate.patch"
TXMOD="$ROOT/package/qca-nss/qca-nss-dp/patches/007-fix-tx-ring-modulo.patch"

[ -f "$D1" ]
[ -f "$D2" ]
[ -f "$TXMOD" ]

for required in \
	'dma_mapping_error' \
	'tx_dma_store' \
	'Invalid Rx skb index' \
	'tx_irqs = 0, rxfill_irqs = 0, rxdesc_irqs = 0' \
	'netif_napi_del(&edma_hw.napi)'; do
	grep '^+' "$D1" | grep -Fq "$required" || {
		echo "missing EDMA correctness prerequisite: $required" >&2
		exit 1
	}
done

for forbidden in \
	'rx_napi' \
	'tx_napi' \
	'edma_handle_rx_irq' \
	'edma_handle_tx_irq' \
	'napi_gro_receive' \
	'NETIF_F_GRO'; do
	if grep '^+' "$D1" | grep -Fq "$forbidden"; then
		echo "D1 correctness patch contains D2/D3 variable: $forbidden" >&2
		exit 1
	fi
done

for required in \
	'netif_napi_add(netdev, &edma_hw.rx_napi, edma_rx_napi)' \
	'netif_napi_add_tx(netdev, &edma_hw.tx_napi, edma_tx_napi)' \
	'edma_handle_rx_irq' \
	'edma_handle_tx_irq' \
	'edma_rx_napi' \
	'edma_tx_napi'; do
	grep '^+' "$D2" | grep -Fq "$required" || {
		echo "missing split-NAPI candidate requirement: $required" >&2
		exit 1
	}
done

if grep -Fq 'NETIF_F_GRO' "$D2" || grep -Fq 'napi_gro_receive' "$D2"; then
	echo 'split-NAPI candidate must not include the separate GRO variable' >&2
	exit 1
fi

if grep -Fq 'edma_if_set_features(dpc);' "$D2"; then
	echo 'split-NAPI candidate must not add a redundant pre-registration feature call' >&2
	exit 1
fi

for forbidden in \
	'dma_mapping_error' \
	'tx_dma_store' \
	'Invalid Rx skb index' \
	'tx_irqs = 0, rxfill_irqs = 0, rxdesc_irqs = 0'; do
	if grep '^+' "$D2" | grep -Fq "$forbidden"; then
		echo "D2 split-NAPI patch duplicates D1 prerequisite: $forbidden" >&2
		exit 1
	fi
done

if grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$D1" "$D2"; then
	echo 'split-NAPI candidate duplicates the existing TX ring modulo fix' >&2
	exit 1
fi

grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$TXMOD"

echo 'test-edma-split-napi-candidate: PASS'
