#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PATCH="$ROOT/package/qca-nss/qca-nss-dp/patches/008-edma-v1-split-napi-candidate.patch"
TXMOD="$ROOT/package/qca-nss/qca-nss-dp/patches/007-fix-tx-ring-modulo.patch"

[ -f "$PATCH" ]
[ -f "$TXMOD" ]

for required in \
	'netif_napi_add(netdev, &edma_hw.rx_napi, edma_rx_napi)' \
	'netif_napi_add_tx(netdev, &edma_hw.tx_napi, edma_tx_napi)' \
	'edma_handle_rx_irq' \
	'edma_handle_tx_irq' \
	'edma_rx_napi' \
	'edma_tx_napi' \
	'napi_gro_receive(&ehw->rx_napi, skb)'; do
	grep -Fq "$required" "$PATCH" || {
		echo "missing split-NAPI candidate requirement: $required" >&2
		exit 1
	}
done

if grep -Fq 'netdev->hw_features |= NETIF_F_GRO' "$PATCH"; then
	echo 'split-NAPI candidate must not enable GRO by default' >&2
	exit 1
fi

if grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$PATCH"; then
	echo 'split-NAPI candidate duplicates the existing TX ring modulo fix' >&2
	exit 1
fi

grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$TXMOD"

echo 'test-edma-split-napi-candidate: PASS'
