/* Actual exact-IPQ HAL functions compiled without GENERIC. Generic callbacks
 * must not run, and these cases do not assert generic registry retirement. */
static void nongeneric_setup(void) {
    setup(); nss_hal_receive_group_closing=nss_hal_receive_group_stopped=false;
    memset(nss_hal_core_removed,0,sizeof(nss_hal_core_removed));
}
int main(void) {
    struct platform_device dev0={.id=0},dev1={.id=1};
    nongeneric_setup(); assert(nss_hal_remove(&dev0)==0);
    for(int core=0;core<NSS_MAX_CORES;core++) assert(!nss_top_main.nss[core].int_ctx[0].irq && nss_top_main.nss[core].int_ctx[0].napi.deleted);
    assert(nss_hal_receive_group_stopped && override_calls==0 && restore_calls==0 && hal_unregister_calls==0 && event_index(HOST_CANCEL_WAIT,-1)<0);
    passed("candidate_nongeneric_all_core_receive_cleanup_without_generic_callbacks");
    assert(nss_hal_remove(&dev1)==0); int before=event_count; unsigned stats=stats_clean_calls;
    assert(nss_hal_remove(&dev0)==0 && nss_hal_remove(&dev1)==0 && event_count==before && stats_clean_calls==stats);
    assert(napi_devices[0].host_frees==1 && napi_devices[1].host_frees==1);
    passed("candidate_nongeneric_repeated_remove_idempotent");
    assert(nss_hal_probe(&dev1)==-ESHUTDOWN && probe_calls==0);
    passed("candidate_nongeneric_late_probe_refused_after_receive_group_close");
    return 0;
}
