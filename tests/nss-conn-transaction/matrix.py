"""Profile case lists and exact-check mutations of the extracted C."""

from source import require


DUAL = (
    "profile", "alloc-ce", "alloc-cme", "map-ce", "map-cme", "high-ce", "high-cme",
    "dma-crossing", "zero-dma-rollback", "cfg-tx-failure", "early-cfg-tx-failure",
    "nested-ack", "size-failure",
    "size-identity", "wrong-size-count", "empty-ce", "empty-cme", "oversize-map",
    "oversize-page-order", "token-exhaustion",
    "cfg-identity", "cfg-nack-retained", "cfg-wrong-count", "close-published",
    "close-pending", "close-inflight", "close-preparing", "close-nested", "dual-budget",
)
V4 = "-DNSS_DRV_IPV4_ENABLE"
V6 = "-DNSS_DRV_IPV6_ENABLE"
INTEGRATION = (
    "rx-malformed4", "rx-malformed6", "rx-non-table", "tx-public", "tx-private",
    "cmd-map-empty", "cmd-map-zero", "cmd-map-boundary", "cmd-map-error", "cmd-map-high",
    "cmd-map-crossing",
)


def profiles():
    yield "normal-dual", [V4, V6], DUAL
    yield "medium-dual", [V4, V6, "-DNSS_MEM_PROFILE_MEDIUM"], ("profile",)
    yield "low-dual", [V4, V6, "-DNSS_MEM_PROFILE_LOW"], ("profile",)
    yield "normal-ipv4", [V4], ("profile", "single-family")
    yield "normal-ipv6", [V6], ("profile", "single-family")
    yield "low-ipv4", [V4, "-DNSS_MEM_PROFILE_LOW"], ("profile",)


def replace_once(source, old, new):
    require(source.count(old) == 1, f"expected one mutation anchor: {old!r}")
    return source.replace(old, new, 1)


def mutants(source):
    unmap = ("dma_unmap_single(dma[i].dev, dma[i].dma,\n"
             "\t\t\t\t\t dma[i].len, dma[i].direction);")
    rows = (
        ("omit-ce-unmap", "if (dma[i].mapped)", "if (dma[i].mapped && i != 0)",
         "map-cme", "free-while-mapped"),
        ("zero-as-unmapped", "if (dma[i].mapped)", "if (dma[i].mapped && dma[i].dma)",
         "zero-dma-rollback", "free-while-mapped"),
        ("narrow-error-check", "dma_mapping_error(record->dev, record->dma)",
         "dma_mapping_error(record->dev, (u32)record->dma)", "map-ce", "map-error-native-width"),
        ("narrow-unmap", unmap, unmap.replace("dma[i].dma", "(u32)dma[i].dma"),
         "high-ce", "unmap-address"),
        ("wrong-unmap-device", unmap, unmap.replace("dma[i].dev", "NULL"),
         "map-cme", "unmap-device"),
        ("wrong-unmap-direction", unmap, unmap.replace("dma[i].direction", "DMA_FROM_DEVICE"),
         "map-cme", "unmap-direction"),
        ("wrong-unmap-length", unmap, unmap.replace("dma[i].len", "dma[i].len + 1"),
         "map-cme", "unmap-length"),
        ("wrong-free-order", "free_pages(dma[i].cpu, dma[i].order);",
         "free_pages(dma[i].cpu, dma[i].order + 1);", "map-cme", "free-order"),
        ("late-cme-validation", " || !nss_conn_valid_len(ctx->dev, cme_len)", "",
         "empty-cme", "reject-size-before-allocation"),
        ("allow-crossing-window", " || record->len - 1 > U32_MAX - record->dma", "",
         "dma-crossing", "prefix-tx-count"),
        ("ignore-rx-context", " || req->ctx != ctx", "",
         "size-identity", "tx-context"),
        ("ignore-rx-token", " || !ncm->app_data ||\n\t    req->token != ncm->app_data", "",
         "size-identity", "size-wrong-token"),
        ("ignore-rx-length", "if (ack && ncm->len <",
         "if (false && ack && ncm->len <", "size-identity", "size-short"),
        ("allow-token-exhaustion", "if (nss_conn_token == U32_MAX)",
         "if (false && nss_conn_token == U32_MAX)", "token-exhaustion", "tx-token"),
        ("restale-outer-size", "\n\tnss_conn_put();\n\tif (ret == NSS_TX_SUCCESS)",
         "\n\tif (ret == NSS_TX_SUCCESS)\n\t\treq->phase = NSS_CONN_SIZE;\n"
         "\tnss_conn_put();\n\tif (ret == NSS_TX_SUCCESS)", "nested-ack", "nested-duplicate"),
        ("commit-before-ack", "\treq->phase = NSS_CONN_CFG_SENDING;\n",
         "\tWRITE_ONCE(req->accepted, count);\n\treq->phase = NSS_CONN_CFG_SENDING;\n",
         "cfg-identity", "unconfirmed-count"),
        ("commit-early-ack-before-tx-result",
         "req->early_cfg_accepted = ack && count == req->requested;",
         "req->early_cfg_accepted = ack && count == req->requested;\n"
         "\t\t\tif (req->early_cfg_accepted)\n\t\t\t\tWRITE_ONCE(req->accepted, count);",
         "nested-ack", "early-cfg-before-tx-success"),
        ("early-ack-masks-tx-failure",
         "spin_lock_bh(&nss_conn_lock);\n\tif (ret == NSS_TX_SUCCESS) {",
         "spin_lock_bh(&nss_conn_lock);\n\tif (ret == NSS_TX_SUCCESS || req->early_cfg_reply) {",
         "early-cfg-tx-failure", "dma-prefix"),
        ("stale-early-ack-on-retry", "\treq->early_cfg_reply = false;\n",
         "", "early-cfg-tx-failure", "retry-confirmed-count"),
        ("released-on-nack", "/* Neither a NACK nor a malformed ACK retires FW DMA. */\n"
         "\t\t\treq->phase = NSS_CONN_UNCERTAIN;\n",
         "\t\t\treq->phase = NSS_CONN_UNCERTAIN;\n"
         "\t\t\tspin_unlock_bh(&nss_conn_lock);\n\t\t\tnss_conn_undo(req->dma);\n"
         "\t\t\treturn;\n",
         "cfg-nack-retained", "dma-retention"),
        ("released-on-close", "\tif (retained)\n",
         "\tif (retained)\n\t\tnss_conn_undo(nss_conn_tables[0].dma);\n\tif (retained)\n",
         "close-published", "dma-retention"),
        ("no-close-join", "wait_event(nss_conn_idle, !READ_ONCE(nss_conn_users));",
         "wait_event(nss_conn_idle, true);", "close-inflight", "close-joins-sender"),
        ("untracked-preparation", "req->phase = NSS_CONN_PREPARING;\n\tnss_conn_users++;",
         "req->phase = NSS_CONN_PREPARING;", "close-preparing", "close-joins-rx"),
        ("untracked-sender", "req->phase = NSS_CONN_SIZE;\n\tnss_conn_users++;",
         "req->phase = NSS_CONN_SIZE;", "close-nested", "close-joins-sender"),
        ("ignore-reservation", "reserved = max(other->accepted, other->requested);",
         "reserved = other->accepted;", "dual-budget", "pending-reservation"),
    )
    for name, old, new, case, assertion in rows:
        mutated = replace_once(source, old, new)
        if name == "late-cme-validation":
            mutated = replace_once(mutated, "ret = nss_conn_alloc(&dma[1], ctx->dev, cme_len);",
                                   "if (!nss_conn_valid_len(ctx->dev, cme_len)) {\n"
                                   "\t\tret = -EINVAL;\n\t\tgoto undo;\n\t}\n"
                                   "\tret = nss_conn_alloc(&dma[1], ctx->dev, cme_len);")
        yield name, mutated, case, assertion


def integration_mutants(source):
    rows = (
        ("wire-callback-fallthrough", "if (nss_conn_table_message(&header)) {",
         "if (false && nss_conn_table_message(&header)) {",
         "rx-malformed4", "unexpected-wire-callback"),
        ("no-fragment-page-bound", "min_t(unsigned int, skb_frag_size(frag), PAGE_SIZE - offset)",
         "skb_frag_size(frag)", "rx-malformed4", "rx-truncated-dispatch"),
        ("no-linear-end-bound", "min_t(unsigned int, skb_headlen(nbuf), end - nbuf->data)",
         "skb_headlen(nbuf)", "rx-malformed4", "rx-truncated-dispatch"),
        ("no-physical-core-check", "if (rx_ctx != nss_ctx || len > contiguous || len > nbuf->len)",
         "if ((false && rx_ctx != nss_ctx) || len > contiguous || len > nbuf->len)",
         "rx-malformed4", "rx-wrong-physical-core"),
        ("drop-ordinary-rx", "cb(nss_ctx, ncm, app_data);",
         "if (false)\n\t\tcb(nss_ctx, ncm, app_data);", "rx-non-table", "ordinary-notify-route"),
        ("allow-public-table", "if (nss_conn_table_message(msg))",
         "if (false && nss_conn_table_message(msg))", "tx-public", "public-v4-table"),
        ("skip-public-header-size", "size < (int)sizeof(struct nss_cmn_msg) || size > buf_size",
         "size > buf_size", "tx-private", "public-declared-short-header"),
        ("skip-private-payload-size", "!nss_conn_table_message(msg) || nss_cmn_get_msg_len(msg) > size",
         "!nss_conn_table_message(msg)", "tx-private", "private-short-payload"),
        ("reusable-table-command", "zero_tail ? 0 : H2N_BIT_FLAG_BUFFER_REUSABLE",
         "H2N_BIT_FLAG_BUFFER_REUSABLE", "tx-private", "private-non-reusable"),
        ("uninitialized-command-tail", "skb_put_zero(nbuf, buf_size - size);",
         "if (false)\n\t\t\tskb_put_zero(nbuf, buf_size - size);\n\t\telse\n"
         "\t\t\tskb_put(nbuf, buf_size - size);", "tx-private", "private-zero-tail"),
        ("narrow-command-dma-check", "dma_mapping_error(dev, dma)",
         "dma_mapping_error(dev, (u32)dma)", "cmd-map-error", "command-native-check"),
        ("ignore-command-dma-crossing", " || len - 1 > U32_MAX - dma", "",
         "cmd-map-crossing", "command-map-result"),
        ("command-high-no-unmap", "dma_unmap_single(dev, dma, len, DMA_TO_DEVICE);",
         "if (false)\n\t\t\tdma_unmap_single(dev, dma, len, DMA_TO_DEVICE);",
         "cmd-map-high", "command-map-unmaps"),
    )
    for name, old, new, case, assertion in rows:
        yield name, replace_once(source, old, new), case, assertion
