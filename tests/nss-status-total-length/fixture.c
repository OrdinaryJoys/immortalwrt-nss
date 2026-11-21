/* Real transport function with explicit sequential host API substitutions. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define NSS_DRV_IPV4_ENABLE 1
#define NSS_DRV_IPV6_ENABLE 1
typedef uint32_t __be32;
/* @wire */
_Static_assert(sizeof(struct nss_cmn_msg) == 40, "LP64 common header layout");
#define PAGE_SIZE 4096U
#define min_t(type,a,b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define IS_ALIGNED(value,alignment) (!((value) & ((alignment)-1)))
static const char *name;
static unsigned warnings, ordinary_calls, table_calls;
#define nss_warning(...) ((void)++warnings)
typedef struct { unsigned char *page; unsigned offset, size; } skb_frag_t;
struct skb_shared_info { unsigned nr_frags; skb_frag_t frags[1]; };
struct sk_buff {
    unsigned char *head, *data, *end;
    unsigned len, data_len;
    struct skb_shared_info shared;
};
#define skb_shinfo(skb) (&(skb)->shared)
#define skb_frag_off(frag) ((frag)->offset)
#define skb_frag_size(frag) ((frag)->size)
#define skb_frag_address(frag) ((frag)->page + (frag)->offset)
#define skb_end_pointer(skb) ((skb)->end)
#define skb_headlen(skb) ((skb)->len - (skb)->data_len)
struct nss_ctx_instance;
typedef void (*nss_core_rx_callback_t)(struct nss_ctx_instance *, struct nss_cmn_msg *, void *);
struct nss_ctx_instance {
    struct { nss_core_rx_callback_t cb; void *app_data; } nss_rx_interface_handlers[NSS_MAX_NET_INTERFACES];
};
static void check(bool ok, const char *marker)
{
    if (!ok) { printf("RX_FAIL %s %s\n", name, marker); exit(86); }
}
/* @classifier */
static struct nss_ctx_instance *expected_context;
static void *expected_data;
/* A header-only transport witness, deliberately NOT a protocol payload parser. */
static void ordinary(struct nss_ctx_instance *ctx, struct nss_cmn_msg *message, void *data)
{
    check(ctx == expected_context, "callback-context");
    check(data == expected_data, "callback-app-data");
    check(message->version == NSS_HLOS_MESSAGE_VERSION, "callback-version");
    ordinary_calls++;
}
/* Observes entry only; request identity/side effects remain outside this suite. */
static void nss_conn_table_rx(struct nss_ctx_instance *ctx, struct nss_cmn_msg *message)
{
    check(ctx == expected_context, "table-context");
    check(nss_conn_table_message(message), "table-classification");
    table_calls++;
}
/* @status */

int main(int argc, char **argv)
{
    if (argc != 2) return 87;
    name = argv[1];
    const unsigned header = sizeof(struct nss_cmn_msg);
    unsigned payload = 24, total = header + payload, contiguous = total, expected = 1;
    bool paged = false, foreign = false, table = false;
    unsigned offset = 0;
    if (!strcmp(name,"max-exact") || !strcmp(name,"max-short")) {
        payload = UINT16_MAX; total = header + payload; contiguous = total;
    }
    if (!strcmp(name,"padded-linear")) { total++; contiguous++; }
    else if (!strcmp(name,"short-one") || !strcmp(name,"max-short")) { total--; contiguous--; expected=0; }
    else if (!strcmp(name,"payload-only")) { total=header; contiguous=header; payload=header; expected=0; }
    else if (!strcmp(name,"zero-payload")) { payload=0; total=contiguous=header; }
    else if (!strcmp(name,"header-short")) { total=contiguous=header-1; expected=0; }
    else if (!strcmp(name,"head-short")) { contiguous=header-1; expected=0; }
    else if (!strcmp(name,"invalid-version") || !strcmp(name,"invalid-interface") ||
             !strcmp(name,"unaligned") || !strcmp(name,"no-handler")) expected=0;
    else if (!strcmp(name,"page-exact")) { paged=true; offset=32; }
    else if (!strcmp(name,"page-short")) { paged=true; offset=32; total--; contiguous--; expected=0; }
    else if (!strcmp(name,"page-offset-invalid")) { paged=true; offset=PAGE_SIZE+1; expected=0; }
    else if (!strcmp(name,"page-boundary-short")) { paged=true; offset=PAGE_SIZE-header+1; expected=0; }
    else if (!strcmp(name,"ordinary-cross-core")) foreign=true;
    else if (!strcmp(name,"table-local")) table=true;
    else if (!strcmp(name,"table-cross-core")) { table=true; foreign=true; expected=0; }
    else if (!strcmp(name,"table-short-contiguous")) { table=true; contiguous=header; expected=0; }
    else if (!strcmp(name,"sg-residual")) contiguous=header;
    else if (strcmp(name,"exact-linear") && strcmp(name,"short-one") &&
             strcmp(name,"max-exact") && strcmp(name,"max-short")) return 87;

    struct nss_ctx_instance ctx={0}, peer={0};
    expected_context=&ctx; expected_data=&peer;
    struct nss_cmn_msg message={.version=NSS_HLOS_MESSAGE_VERSION, .len=(uint16_t)payload,
        .interface=table ? NSS_IPV4_RX_INTERFACE : 1,
        .type=table ? NSS_IPV4_TX_CONN_TABLE_SIZE_MSG : 0};
    if (!strcmp(name,"invalid-version")) message.version++;
    if (!strcmp(name,"invalid-interface")) message.interface=NSS_MAX_NET_INTERFACES;
    if (message.interface<NSS_MAX_NET_INTERFACES && strcmp(name,"no-handler")) {
        ctx.nss_rx_interface_handlers[message.interface].cb=ordinary;
        ctx.nss_rx_interface_handlers[message.interface].app_data=&peer;
    }
    /* Allocation capacity and active skb length are independent on purpose. */
    size_t capacity = total > PAGE_SIZE ? total+64 : 2*PAGE_SIZE;
    unsigned char *storage=calloc(1,capacity);
    check(storage!=NULL,"allocation");
    struct sk_buff skb={.head=storage,.data=storage,.end=storage+capacity,
                       .len=total,.data_len=total-contiguous};
    unsigned char *data=storage;
    if (paged) {
        /* Pinned page assembler publishes an entirely non-linear skb. */
        skb.data_len=total;
        check(skb_headlen(&skb)==0,"page-headlen-zero");
        skb.shared.nr_frags=1;
        skb.shared.frags[0]=(skb_frag_t){.page=storage,.offset=offset,.size=contiguous};
        data=storage+offset;
    } else if (!strcmp(name,"unaligned")) {
        skb.data=++data;
    }
    memcpy(data,&message,sizeof(message));
    nss_core_handle_nss_status_pkt(&ctx,&skb,foreign ? &peer : &ctx);
    check((table ? table_calls : ordinary_calls)==expected,"dispatch-count");
    check((table ? ordinary_calls : table_calls)==0,"dispatch-isolation");
    free(storage);
    printf("RX_PASS %s\n",name);
    return 0;
}
