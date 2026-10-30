"""Single faults applied to complete actual COUNT definitions."""


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('mutation-anchor:' + old)
    return text.replace(old, new, 1)


def variants():
    guard = '\tif (dev_num > SW_MAX_NR_DEV)\n\t\treturn -EINVAL;'
    return [
        ('omit-capacity', 'ssdk_switch_device_num_init', guard, '', 'over-four', 'count-admitted-to-allocator'),
        ('reject-capacity-three', 'ssdk_switch_device_num_init', 'dev_num > SW_MAX_NR_DEV',
         'dev_num >= SW_MAX_NR_DEV', 'three', 'return-value'),
        ('allow-four', 'ssdk_switch_device_num_init', 'dev_num > SW_MAX_NR_DEV',
         'dev_num > SW_MAX_NR_DEV + 1', 'over-four', 'count-admitted-to-allocator'),
        ('signed-count-comparison', 'ssdk_switch_device_num_init', 'dev_num > SW_MAX_NR_DEV',
         '(int32_t)dev_num > SW_MAX_NR_DEV', 'over-uint32-max', 'count-admitted-to-allocator'),
        ('wrong-capacity-errno', 'ssdk_switch_device_num_init', 'return -EINVAL;',
         'return -ENOMEM;', 'over-seven', 'return-value'),
        ('reject-zero', 'ssdk_switch_device_num_init', 'dev_num > SW_MAX_NR_DEV',
         '!dev_num || dev_num > SW_MAX_NR_DEV', 'zero', 'return-value'),
        ('leak-rejected-of-reference', 'ssdk_switch_device_num_init',
         '\t\tof_node_put(switch_instance);',
         '\t\tif (dev_num <= SW_MAX_NR_DEV) of_node_put(switch_instance);',
         'over-four', 'of-reference-balance'),
        ('capacity-before-malformed', 'ssdk_switch_device_num_init',
         '\t\tif (ret)\n\t\t\treturn ret;', '\t\tif (ret)\n\t\t\treturn -EINVAL;',
         'malformed-short-over', 'return-value'),
        ('capacity-before-foreign', 'ssdk_switch_device_num_init', '\t\treturn -EBUSY;',
         '\t\treturn -EINVAL;', 'foreign-over', 'return-value'),
        ('ignore-root-preparation-error', 'regi_init', '\tif (rv)\n\t\treturn rv;', '',
         'root-over-four', 'root-entered-private'),
        ('root-cleanup-unacquired', 'regi_init', '\tif (rv)\n\t\treturn rv;',
         '\tif (rv) { ssdk_free_priv(); return rv; }', 'root-over-four', 'root-controls'),
        ('revert-default', 'ssdk_switch_device_num_init', 'dev_num = 1, dev_id = 0',
         'dev_num = 2, dev_id = 0', 'default-no-node', 'topology-values'),
        ('leak-local-array', 'ssdk_switch_device_num_init', '\tkfree(nodes);', '',
         'three-fault-2', 'allocation-leak'),
        ('leak-prior-child', 'ssdk_switch_device_num_init',
         '\twhile (dev_id)\n\t\tkfree(nodes[--dev_id]);', '', 'three-fault-4', 'allocation-leak'),
        ('publish-before-complete', 'ssdk_switch_device_num_init',
         '\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {',
         '\tssdk_dt_global.ssdk_dt_switch_nodes = nodes;\n\tfor (dev_id = 0; dev_id < dev_num; dev_id++) {',
         'three', 'premature-publication'),
        ('null-private-leaks-topology', 'ssdk_free_priv', '\t\tgoto free_topology;',
         '\t\tif (!qca_phy_priv_global) return;\n\t\tgoto free_topology;',
         'null-private-three', 'null-private-topology'),
        ('getter-wrong-count', 'ssdk_switch_device_num_get',
         'return ssdk_dt_global.num_devices;', 'return ssdk_dt_global.num_devices + 1;',
         'three', 'actual-get-count'),
    ]
