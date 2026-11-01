/* External API substitutes around four byte-extracted EDMA functions.
 * No real MMIO, NAPI scheduling, RCU grace period or target ABI is exercised. */
struct edma_hw edma_hw;
static struct edma_rxdesc_ring host_rxdesc[1];
static struct edma_rxfill_ring host_rxfill[1];
static struct edma_txcmpl_ring host_txcmpl[1];
static struct net_device host_dummy_napi_owner;
static struct resource host_register_resource;
static unsigned host_masks, host_disables, host_graces, host_unpublishes;
static atomic_uint host_retire_calls;
static unsigned host_mask_bits;
static uint32_t host_irq_masks[4];
static char host_retire_events[128];
static unsigned host_retire_event_count;

static void retirement_check(bool ok, const char *reason)
{
    if (!ok) {
        fprintf(stderr, "DP_RETIRE %s\n", reason);
        exit(86);
    }
}

static void retirement_event(char event)
{
    retirement_check(host_retire_event_count < sizeof(host_retire_events), "event-capacity");
    host_retire_events[host_retire_event_count++] = event;
}

void edma_reg_write(uint32_t offset, uint32_t value)
{
    retirement_check(rtnl_is_locked(), "mask-rtnl");
    retirement_check(value == EDMA_MASK_INT_CLEAR, "mask-value");
    unsigned bit;
    if (offset == EDMA_REG_RXDESC_INT_MASK(host_rxdesc[0].id)) bit = 1;
    else if (offset == EDMA_REG_TX_INT_MASK(host_txcmpl[0].id)) bit = 2;
    else if (offset == EDMA_REG_RXFILL_INT_MASK(host_rxfill[0].id)) bit = 4;
    else {
        retirement_check(offset == EDMA_REG_MISC_INT_MASK, "mask-register");
        bit = 8;
    }
    host_mask_bits |= bit;
    for (unsigned i = 0; i < 4; i++)
        if (bit == (1U << i)) host_irq_masks[i] = value;
    host_masks++;
    retirement_event('M');
}

static void napi_disable(struct napi_struct *napi)
{
    retirement_check(rtnl_is_locked(), "napi-rtnl");
    retirement_check(napi == &edma_hw.napi && edma_hw.napi_enabled,
                     "napi-owner-enabled");
    retirement_check(host_mask_bits == 15, "mask-before-disable");
    host_disables++;
    retirement_event('D');
}

static void synchronize_net(void)
{
    retirement_check(rtnl_is_locked(), "grace-rtnl");
    /* This records the external wait boundary, not Linux RCU implementation. */
    bool poll_tail = host_retire_event_count &&
                     host_retire_events[host_retire_event_count - 1] == 'D';
    host_graces++;
    retirement_event('G');
    if (poll_tail) {
        /* A modeled final poll write makes the second mask observably needed. */
        for (unsigned i = 0; i < 4; i++) host_irq_masks[i] = UINT32_MAX;
        host_mask_bits = 0;
        retirement_event('R');
    }
}

static void host_edma_assign(struct net_device **slot, struct net_device *value)
{
    retirement_check(rtnl_is_locked(), "unpublish-rtnl");
    retirement_check(slot >= edma_hw.netdev_arr &&
                     slot < edma_hw.netdev_arr + EDMA_MAX_GMACS && !value,
                     "unpublish-slot");
    __atomic_store_n(slot, value, __ATOMIC_SEQ_CST);
    host_unpublishes++;
    retirement_event('U');
}

#define rcu_access_pointer(x) READ_ONCE(x)
#define rcu_assign_pointer(x, value) host_edma_assign(&(x), (value))

HOST_EDMA_FUNCTIONS

static void host_edma_setup(bool up, bool overridden)
{
    memset(&edma_hw, 0, sizeof(edma_hw));
    host_rxdesc[0].id = 3;
    host_txcmpl[0].id = 5;
    host_rxfill[0].id = 7;
    edma_hw.rxdesc_ring = host_rxdesc;
    edma_hw.txcmpl_ring = host_txcmpl;
    edma_hw.rxfill_ring = host_rxfill;
    edma_hw.rxdesc_rings = edma_hw.txcmpl_rings = edma_hw.rxfill_rings = 1;
    edma_hw.reg_base = host_irq_masks;
    edma_hw.reg_resource = &host_register_resource;
    edma_hw.napi_dev = &host_dummy_napi_owner;
    edma_hw.napi_added = 1;
    edma_hw.edma_initialized = true;
    edma_hw.tx_irqs_owned = edma_hw.rxfill_irqs_owned = edma_hw.rxdesc_irqs_owned = 1;
    edma_hw.misc_irq_owned = true;
    edma_hw.dp_override_cnt = overridden ? 1 : 0;
    /* A successful NSS takeover has already retired host membership. */
    if (!overridden) {
        edma_hw.netdev_arr[0] = &dev;
        edma_hw.host_open[0] = up;
        edma_hw.active = up;
        edma_hw.napi_enabled = up;
    }
    host_masks = host_disables = host_graces = host_unpublishes = host_mask_bits = 0;
    for (unsigned i = 0; i < 4; i++) host_irq_masks[i] = UINT32_MAX;
    host_retire_event_count = 0;
    atomic_store(&host_retire_calls, 0);
}

static bool host_observed_retire(struct net_device *netdev, uint32_t macid)
{
    retirement_check(rtnl_is_locked(), "retire-rtnl");
    retirement_check(netdev == dp.netdev && macid == dp.macid &&
                     macid >= EDMA_START_GMACS && macid <= EDMA_MAX_GMACS, "retire-identity");
    retirement_check(dp.plane_readers == 0 && dp.plane_blocked &&
                     !dev.queue_started && !dev.carrier && !dev.device_present,
                     "retire-after-plane-drain");
    atomic_fetch_add(&host_retire_calls, 1);
    bool owned = rcu_access_pointer(edma_hw.netdev_arr[macid - 1]) == netdev;
    bool opened = owned && edma_hw.host_open[macid - 1];
    int active = edma_hw.active;
    unsigned masks = host_masks, disables = host_disables;
    unsigned graces = host_graces, unpublishes = host_unpublishes;
    unsigned events = host_retire_event_count;
    struct edma_hw expected_hw;
    memcpy(&expected_hw, &edma_hw, sizeof(expected_hw));
    struct nss_dp_data_plane_ctx host_contexts[NSS_DP_MAX_PORTS];
    memcpy(host_contexts, dp_global_data_plane_ctx, sizeof(host_contexts));
    bool retired = edma_retire_port(netdev, macid);
    retirement_check(retired == owned, "retire-result");
    retirement_check(edma_hw.active == active - (opened ? 1 : 0), "retire-active");
    if (owned) {
        retirement_check(!rcu_access_pointer(edma_hw.netdev_arr[macid - 1]),
                         "retire-unpublish");
        retirement_check(!edma_hw.host_open[macid - 1], "retire-close-member");
        retirement_check(host_unpublishes == unpublishes + 1, "retire-unpublish-count");
        retirement_check(host_graces == graces + ((opened && active == 1) ? 2 : 1),
                         "retire-grace");
    } else {
        retirement_check(host_unpublishes == unpublishes && host_graces == graces &&
                         host_masks == masks && host_disables == disables,
                         "foreign-or-repeat-no-effects");
    }
    if (opened && active == 1) {
        retirement_check(!edma_hw.napi_enabled && host_disables == disables + 1,
                         "last-member-stops-napi");
        retirement_check(host_masks == masks + 8, "last-member-masks-twice");
        for (unsigned i = 0; i < 4; i++)
            retirement_check(host_irq_masks[i] == EDMA_MASK_INT_CLEAR, "poll-tail-final-mask");
    } else {
        retirement_check(host_masks == masks && host_disables == disables,
                         "peer-or-closed-no-napi-stop");
    }
    if (owned) {
        expected_hw.netdev_arr[macid - 1] = NULL;
        expected_hw.host_open[macid - 1] = false;
        expected_hw.active -= opened ? 1 : 0;
        if (opened && active == 1) expected_hw.napi_enabled = false;
    }
    retirement_check(!memcmp(&edma_hw, &expected_hw, sizeof(expected_hw)) &&
                     !memcmp(dp_global_data_plane_ctx, host_contexts, sizeof(host_contexts)),
                     "only-owned-membership-state-changed");
    const char *expected = !owned ? "" : (opened && active == 1) ? "MMMMDGRMMMMUG" : "UG";
    retirement_check(host_retire_event_count - events == strlen(expected) &&
                     !memcmp(host_retire_events + events, expected, strlen(expected)),
                     "retirement-event-order");
    return retired;
}

static void host_edma_isolated(void)
{
    retirement_check(atomic_load(&host_retire_calls) > 0, "quarantine-must-retire");
    retirement_check(!edma_hw.netdev_arr[dp.macid - 1] &&
                     !edma_hw.host_open[dp.macid - 1], "isolated-member");
}

static void host_rejects_retirement(struct net_device *netdev, uint32_t macid)
{
    struct edma_hw before;
    struct nss_dp_data_plane_ctx contexts[NSS_DP_MAX_PORTS];
    uint32_t masks[4];
    char events[sizeof(host_retire_events)];
    unsigned counters[] = {host_masks, host_disables, host_graces, host_unpublishes,
                           host_mask_bits, host_retire_event_count, atomic_load(&host_retire_calls)};
    memcpy(&before, &edma_hw, sizeof(before));
    memcpy(contexts, dp_global_data_plane_ctx, sizeof(contexts));
    memcpy(masks, host_irq_masks, sizeof(masks));
    memcpy(events, host_retire_events, sizeof(events));
    retirement_check(!edma_retire_port(netdev, macid), "reject-invalid-or-foreign");
    unsigned after[] = {host_masks, host_disables, host_graces, host_unpublishes,
                        host_mask_bits, host_retire_event_count, atomic_load(&host_retire_calls)};
    retirement_check(!memcmp(&before, &edma_hw, sizeof(before)) &&
                     !memcmp(contexts, dp_global_data_plane_ctx, sizeof(contexts)) &&
                     !memcmp(masks, host_irq_masks, sizeof(masks)) &&
                     !memcmp(events, host_retire_events, sizeof(events)) &&
                     !memcmp(counters, after, sizeof(counters)),
                     "rejected-retirement-keeps-complete-state");
}

static void host_retirement_boundaries(void)
{
    struct net_device foreign = {0};
    setup(true, false);
    rtnl_lock();
    /* Native helper rejects invalid/foreign instances without mutating state. */
    host_rejects_retirement(NULL, 1);
    host_rejects_retirement(&dev, 0);
    host_rejects_retirement(&dev, EDMA_MAX_GMACS + 1);
    host_rejects_retirement(&dev, UINT32_MAX);
    host_rejects_retirement(&foreign, 1);
    retirement_check(edma_hw.netdev_arr[0] == &dev && edma_hw.host_open[0] &&
                     edma_hw.active == 1 && edma_hw.napi_enabled &&
                     !host_masks && !host_disables && !host_graces && !host_unpublishes,
                     "invalid-or-foreign-preserves-owner");
    rtnl_unlock();
    detach(); isolated();
    retirement_check(edma_hw.active == 0 && !edma_hw.napi_enabled, "owned-member-retired");
    passed("actual_edma_rejects_invalid_and_foreign_owner_without_effects");

    setup(true, false);
    edma_hw.netdev_arr[1] = &foreign;
    edma_hw.host_open[1] = true;
    edma_hw.active = 2;
    detach(); isolated();
    retirement_check(edma_hw.active == 1 && edma_hw.napi_enabled &&
                     edma_hw.netdev_arr[1] == &foreign && edma_hw.host_open[1],
                     "peer-membership-preserved");
    unsigned graces = host_graces, unpublishes = host_unpublishes;
    detach(); isolated();
    retirement_check(edma_hw.active == 1 && host_graces == graces &&
                     host_unpublishes == unpublishes && !host_disables,
                     "repeated-retirement-no-double-decrement");
    passed("actual_edma_retirement_preserves_peer_and_repeated_retirement_is_inert");

    setup(false, false);
    detach(); isolated();
    retirement_check(edma_hw.active == 0 && host_graces == 1 && !host_disables &&
                     !host_masks && host_unpublishes == 1, "closed-member-unpublishes");
    passed("actual_edma_closed_member_unpublishes_without_active_underflow");

    setup(true, false);
    edma_hw.netdev_arr[0] = &foreign;
    detach();
    retirement_check(atomic_load(&host_retire_calls) == 1 &&
                     edma_hw.netdev_arr[0] == &foreign && edma_hw.host_open[0] &&
                     edma_hw.active == 1 && edma_hw.napi_enabled,
                     "quarantine-keeps-foreign-owner");
    passed("quarantine_does_not_retire_foreign_edma_instance");

    setup(true, false);
    dp.macid = EDMA_MAX_GMACS;
    edma_hw.netdev_arr[0] = NULL;
    edma_hw.host_open[0] = false;
    edma_hw.netdev_arr[EDMA_MAX_GMACS - 1] = &dev;
    edma_hw.host_open[EDMA_MAX_GMACS - 1] = true;
    dp_global_data_plane_ctx[0].dev = NULL;
    dp_global_data_plane_ctx[EDMA_MAX_GMACS - 1].dev = &dev;
    detach(); isolated();
    retirement_check(!edma_hw.active && !edma_hw.napi_enabled, "last-valid-macid-retired");
    passed("actual_edma_last_valid_macid_retires_only_its_slot");
}
