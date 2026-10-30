"""Single-anchor executable source negatives; never count a compile failure."""
from source import once, mask


def variants(bodies):
    result = []

    def add(name, function, body, case, marker):
        changed = dict(bodies);changed[function] = body
        result.append((name, changed, case, marker))

    init = bodies['nss_dp_init']
    n = '''\tret = register_netdevice_notifier(&nss_dp_netdev_notifier);
\tif (ret) {
\t\tpr_warn("NSS DP netdevice notifier register failed: ret=%d\\n", ret);
\t\tgoto fail;
\t}
\tnss_dp_netdev_owned = true;'''
    late = once(init, n, '')
    late = once(late, '\tnss_dp_platform_owned = true;',
                '\tnss_dp_platform_owned = true;\n#ifdef CONFIG_NET_SWITCHDEV\n'+n+'\n#endif')
    add('P-before-N', 'nss_dp_init', late, 'late-P', 'published-without-N')
    add('ignore-ready', 'nss_dp_init', once(init, 'if (!ssdk_netdev_cache_ready())',
        'if (false && !ssdk_netdev_cache_ready())'), 'ready-false', 'ready-before-H')
    add('lose-first-errno', 'nss_dp_init', once(init,
        'fail:\n\tnss_dp_release_stages();\n\treturn ret;',
        'fail:\n\tnss_dp_release_stages();\n\treturn 0;'), 'fail-4', 'first-error')
    probe = bodies['nss_dp_probe']
    add('restore-per-probe-reset', 'nss_dp_probe', once(probe,
        '#ifndef NSS_DP_NATIVE_INIT_STAGES\n\tdp_global_ctx.slowproto_acl_bm = 0;\n#endif',
        '\tdp_global_ctx.slowproto_acl_bm = 0;'), 'two-actor', 'probe-clobbered-accepted-bit')
    mark = bodies['ssdk_netdev_cache_mark_native_port']
    add('always-success-bridge', 'ssdk_netdev_cache_mark_native_port',
        mark[:mask(mark).index('{')+1]+'\n\treturn true;\n}', 'mark-false', 'mark-before-context')
    add('mark-no-bit', 'ssdk_netdev_cache_mark_native_port', once(mark,
        'ssdk_netdev_managed[dev_id][port_id] = true;',
        'ssdk_netdev_managed[dev_id][port_id] = false;'), 'normal', 'mark-before-context')
    s = bodies['nss_dp_switchdev_init']
    add('failed-Sb-owned', 'nss_dp_switchdev_init', once(s,
        '\tif (ret)\n\t\treturn ret;',
        '\tif (ret) { switchdev_blocking_owned = true; return ret; }'), 'fail-2', 'blocking-owner')
    release = bodies['nss_dp_release_stages']
    early_s = once(release, '\tnss_dp_switchdev_exit();', '')
    early_s = once(early_s, 'static void nss_dp_release_stages(void)\n{',
        'static void nss_dp_release_stages(void)\n{\n#ifdef CONFIG_NET_SWITCHDEV\n\tnss_dp_switchdev_exit();\n#endif')
    add('S-before-P', 'nss_dp_release_stages', early_s, 'actor', 'callbacks-through-P')
    for field, marker in [('nss_dp_hal_owned','implementation-hal-owner'),
                          ('nss_dp_platform_owned','implementation-platform-owner'),
                          ('nss_dp_netdev_owned','implementation-netdev-owner'),
                          ('dp_global_ctx.common_init_done','implementation-common-init')]:
        add('retain-'+field.split('.')[-1], 'nss_dp_release_stages',
            once(release,field+' = false;','(void)0;'), 'normal', marker)
    for field,marker in [('switchdev_atomic_owned','implementation-atomic-owner'),
                         ('switchdev_blocking_owned','implementation-blocking-owner')]:
        add('retain-'+field,'nss_dp_switchdev_exit',once(bodies['nss_dp_switchdev_exit'],
            field+' = false;','(void)0;'),'normal',marker)
    event = bodies['nss_dp_netdev_event']
    add('N-foreign-filter', 'nss_dp_netdev_event', once(event,
        'if (!dev || !nss_dp_is_phy_dev(dev))', 'if (!dev)'), 'zero', 'callback-services')
    add('N-linking-filter', 'nss_dp_netdev_event', once(event,
        'if (info && info->linking)', 'if (false && info && info->linking)'),
        'actor', 'linking-no-sideeffect')
    g3 = bodies['ssdk_ifname_to_port']
    early_put = once(g3, '\tdev_put(eth_dev);', '')
    early_put = once(early_put, '\tif (eth_dev->phydev)', '\tdev_put(eth_dev);\n\tif (eth_dev->phydev)')
    add('G3-early-put', 'ssdk_ifname_to_port', early_put, 'g3-zero', 'mapper-after-put')
    add('G3-missing-put', 'ssdk_ifname_to_port', once(g3, '\tdev_put(eth_dev);', ''),
        'g3-reader', 'g3-put-ledger')
    remove = bodies['nss_dp_remove']
    add('retain-port-slot','nss_dp_remove',once(remove,
        'dp_global_ctx.nss_dp[i] = NULL;', '(void)i;'), 'normal','implementation-port-slot')
    for label,call,marker in [
        ('clear-wrong-port','fal_port_vsi_set(0, dp_priv->macid + 1, 0xFFFF);','vsi-clear-identity'),
        ('clear-wrong-device','fal_port_vsi_set(1, dp_priv->macid, 0xFFFF);','vsi-clear-identity'),
        ('clear-wrong-vsi','fal_port_vsi_set(0, dp_priv->macid, 0xFFFE);','vsi-clear-value')]:
        add(label,'nss_dp_remove',once(remove,'fal_port_vsi_set(0, dp_priv->macid, 0xFFFF);',call),
            'two',marker)
    add('missing-success-remove-clear','nss_dp_remove',once(remove,
        'fal_port_vsi_set(0, dp_priv->macid, 0xFFFF);', '(void)dp_priv->macid;'),
        'two','vsi-success-remove')
    add('wrong-abort-invalid','nss_dp_probe',once(probe,
        '\tnss_dp_phy_disconnect(dp_priv);',
        '\tnss_dp_phy_disconnect(dp_priv);\n\tfal_port_vsi_set(0, dp_priv->macid, FAL_VSI_INVALID);'),
        'prelist','vsi-abort-prestate')
    add('assign-wrong-vsi','nss_dp_probe',once(probe,
        'fal_port_vsi_set(0, port_id, vsi_id)', 'fal_port_vsi_set(0, port_id, vsi_id + 1)'),
        'normal','vsi-assign-value')
    add('assign-wrong-device','nss_dp_probe',once(probe,
        'fal_port_vsi_set(0, port_id, vsi_id)', 'fal_port_vsi_set(1, port_id, vsi_id)'),
        'normal','vsi-assign-identity')
    add('omit-required-same-value-set','nss_dp_probe',once(probe,
        'fal_port_vsi_set(0, port_id, vsi_id)', 'SW_OK'), 'prelist','vsi-required-assign-phase')
    mapping=bodies['qca_ssdk_phy_addr_to_port']
    add('identity-mapper','qca_ssdk_phy_addr_to_port',mapping[:mask(mapping).index('{')+1]+
        '\n return TO_PHY_ADDR(phy_addr);\n}', 'g3-reader','g3-result')
    add('ignore-provider-bitmap','qca_ssdk_phy_addr_to_port',once(mapping,
        'if (!(BIT(i) & qca_ssdk_port_bmp_get(dev_id)))',
        'if (false && !(BIT(i) & qca_ssdk_port_bmp_get(dev_id)))'),
        'g3-unmapped','g3-result')
    add('detach-before-refwait', 'nss_dp_remove', remove.replace(
        '\t\tunregister_netdev(dp_priv->netdev);',
        '\t\tnss_dp_phy_disconnect(dp_priv);\n\t\tunregister_netdev(dp_priv->netdev);', 1),
        'g3-reader', 'disconnect-after-refwait')
    return result
