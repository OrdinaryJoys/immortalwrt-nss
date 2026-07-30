#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
D1="$ROOT/package/qca-nss/qca-nss-dp/patches/008-edma-v1-correctness-prerequisites.patch"
TXMOD="$ROOT/package/qca-nss/qca-nss-dp/patches/007-fix-tx-ring-modulo.patch"

[ -f "$D1" ]
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
	'NETIF_F_GRO' \
	'edma_if_set_features(dpc);'; do
	if grep '^+' "$D1" | grep -Fq "$forbidden"; then
		echo "D1 correctness patch contains D2/D3 variable: $forbidden" >&2
		exit 1
	fi
done

if grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$D1"; then
	echo 'EDMA correctness patch duplicates the existing TX ring modulo fix' >&2
	exit 1
fi

grep -Fq 'tx_ring = skbq % edma_hw.txdesc_rings' "$TXMOD"

echo 'test-edma-correctness-prerequisites: PASS'
