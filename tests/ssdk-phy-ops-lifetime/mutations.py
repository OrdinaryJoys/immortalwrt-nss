"""Each source mutant must compile and fail one named runtime contract."""


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('mutation anchor is not unique: ' + old)
    return text.replace(old, new, 1)


def variants(data):
    rows = []

    def add(name, function, old, new, case, marker):
        funcs = dict(data['funcs'])
        funcs[function] = once(funcs[function], old, new)
        rows.append((name, funcs, data['table'], case, marker))

    add('overwrite-foreign', 'hsl_phy_api_ops_register',
        'rv = SW_BUSY;', 'ssdk_phy_driver[phy_type].phy_ops = phy_api_ops;',
        'registration', 'register-no-replace')
    add('same-object-not-idempotent', 'hsl_phy_api_ops_register',
        'else\n\t\tssdk_phy_driver[phy_type].phy_ops = phy_api_ops;',
        'else if (ssdk_phy_driver[phy_type].phy_ops == phy_api_ops)\n\t\trv = SW_BUSY;\n'
        '\telse\n\t\tssdk_phy_driver[phy_type].phy_ops = phy_api_ops;',
        'registration', 'register-idempotent')
    add('unregister-matching-live', 'hsl_phy_api_ops_unregister',
        'SW_BUSY : SW_NOT_FOUND;', 'SW_OK : SW_NOT_FOUND;', 'unregister-live', 'unregister-live')
    add('unregister-ignores-identity', 'hsl_phy_api_ops_unregister',
        'SW_BUSY : SW_NOT_FOUND;', 'SW_BUSY : SW_BUSY;', 'unregister-live', 'unregister-stale')
    add('prepare-clears-borrowed', 'phy_api_ops_init',
        'rv = ssdk_phy_driver[phy_type].phy_ops ? SW_BUSY : SW_OK;',
        'rv = SW_OK; ssdk_phy_driver[phy_type].phy_ops = NULL;', 'prepare-slot', 'prepare-occupied')
    add('prepare-frees-borrowed', 'phy_api_ops_init',
        'spin_lock_irqsave(&ssdk_phy_ops_lock, flags);',
        'if (ssdk_phy_driver[phy_type].phy_ops) kfree(ssdk_phy_driver[phy_type].phy_ops);\n'
        '\tspin_lock_irqsave(&ssdk_phy_ops_lock, flags);', 'prepare-slot', 'ops-not-owned')
    add('cleanup-clears-global', 'ssdk_phy_driver_cleanup',
        'ssdk_phy_driver[i].port_bmp[dev_id] = 0;',
        'ssdk_phy_driver[i].phy_ops = NULL;\n\t\tssdk_phy_driver[i].port_bmp[dev_id] = 0;',
        'old-phy-no-own', 'peer-visible')
    add('cleanup-frees-global', 'ssdk_phy_driver_cleanup',
        'ssdk_phy_driver[i].port_bmp[dev_id] = 0;',
        'if (ssdk_phy_driver[i].phy_ops) kfree(ssdk_phy_driver[i].phy_ops);\n'
        '\t\tssdk_phy_driver[i].port_bmp[dev_id] = 0;', 'borrowed-heap', 'ops-not-owned')
    add('cleanup-clears-peer', 'ssdk_phy_driver_cleanup',
        'ssdk_phy_driver[i].port_bmp[dev_id] = 0;',
        'memset(ssdk_phy_driver[i].port_bmp, 0, sizeof(ssdk_phy_driver[i].port_bmp));',
        'old-phy-own', 'peer-state')
    add('cleanup-keeps-local-bitmap', 'ssdk_phy_driver_cleanup',
        '\n\tport_bmp[dev_id] = 0;', '\n\t(void)port_bmp;', 'old-phy-own', 'local-state')
    add('cleanup-clears-before-exit', 'ssdk_phy_driver_cleanup',
        'ssdk_phy_driver[i].exit(dev_id,',
        'ssdk_phy_driver[i].port_bmp[dev_id] = 0;\n\t\t\tssdk_phy_driver[i].exit(dev_id,',
        'callback-exit', 'exit-local')
    for name, function, case, marker in [
        ('register-without-lock', 'hsl_phy_api_ops_register', 'registration', 'register-locked'),
        ('getter-without-lock', 'hsl_phy_api_ops_get', 'getters', 'getter-locked'),
        ('prepare-without-lock', 'phy_api_ops_init', 'prepare-slot', 'prepare-locked'),
        ('unregister-without-lock', 'hsl_phy_api_ops_unregister', 'unregister-live', 'unregister-locked'),
    ]:
        funcs = dict(data['funcs'])
        funcs[function] = once(funcs[function], 'spin_lock_irqsave(&ssdk_phy_ops_lock, flags);', 'flags = 0;')
        funcs[function] = once(funcs[function], 'spin_unlock_irqrestore(&ssdk_phy_ops_lock, flags);', '(void)flags;')
        rows.append((name, funcs, data['table'], case, marker))
    add('getter-rejects-last-port', 'hsl_phy_api_ops_get',
        'port_id >= SW_MAX_NR_PORT', 'port_id >= SW_MAX_NR_PORT - 1', 'getters', 'getter-valid')
    add('ignore-registration-error', 'aquantia_phy_init',
        'if (ret)\n\t\treturn ret;', '(void)ret;', 'aqua-retry', 'hw-after-registration')
    add('discard-hw-error', 'aquantia_phy_init',
        'return aquantia_phy_hw_init(dev_id, port_bmp);',
        'aquantia_phy_hw_init(dev_id, port_bmp); return 0;', 'aqua-hw-error', 'hw-first-error')
    add('failed-once-latch', 'aquantia_phy_init',
        'ret = aquantia_phy_api_ops_init();',
        'static int attempted; ret = attempted ? SW_OK : aquantia_phy_api_ops_init(); attempted = 1;',
        'aqua-retry', 'hw-after-registration')
    rows.append(('wrong-field-mapping', dict(data['funcs']),
                 once(data['table'], '.phy_speed_get = aquantia_phy_get_speed,', '.phy_speed_get = NULL,'),
                 'aqua-repeated', 'mapping'))
    return rows
