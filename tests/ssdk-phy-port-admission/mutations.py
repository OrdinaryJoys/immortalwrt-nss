"""Directed actual-body mutants; compile/sanitizer failures never earn credit."""


def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('mutation-not-unique:' + before)
    return text.replace(before, after, 1)


def variants(new, old, profile):
    result=[]
    bodies=new['bodies']

    def add(name,symbol,case,before,after,marker):
        body=bodies[symbol]
        result.append(dict(name=name,symbol=symbol,case=case,before=body,after=once(body,before,after),
                           marker=marker,classification='directed candidate source-body mutation'))

    reader='ssdk_dt_read_port_values'
    add('reader-missing-bound',reader,'id-value-16-reader','if (id >= SW_MAX_NR_PORT)','if (id > SW_MAX_NR_PORT)', 'READER_RETURN')
    add('reader-reject-zero',reader,'id-value-0-reader','if (id >= SW_MAX_NR_PORT)','if (!id || id >= SW_MAX_NR_PORT)', 'READER_RETURN')
    add('reader-reject-fifteen',reader,'id-value-15-reader','if (id >= SW_MAX_NR_PORT)','if (id >= SW_MAX_NR_PORT - 1)', 'READER_RETURN')
    add('reader-short-dac',reader,'dac-len-4-reader','"phy_dac", dac, 2','"phy_dac", dac, 1','READER_RETURN')
    add('reader-partial-output',reader,'dac-len-4-reader','if (of_find_property(port_node, "phy_dac", NULL))',
        'values->id = id;\n\tif (of_find_property(port_node, "phy_dac", NULL))','OUTPUT_ATOMIC')
    add('reader-clamp-u8',reader,'dac-values-255-256-reader','values->dac.edac = dac[1];',
        'values->dac.edac = dac[1] > 255 ? 255 : dac[1];','EXACT_MODEL_TRACE')
    add('reader-swap-dac',reader,'dac-len-8-reader','values->dac.mdac = dac[0];','values->dac.mdac = dac[1];','EXACT_MODEL_TRACE')
    add('reader-absent-flag',reader,'dac-len--1-reader','a_bool_t has_dac = A_FALSE;','a_bool_t has_dac = A_TRUE;','EXACT_MODEL_TRACE')

    validate='ssdk_dt_validate_phy_ports'
    add('validator-ignore-error',validate,'id-value-16-validate','return ret;','return 0;','VALIDATE_RETURN')
    add('validator-missing-child-put',validate,'id-value-16-validate','of_node_put(port_node);','(void)port_node;','LOCAL_CHILD_REFS')
    add('validator-missing-container-put',validate,'id-value-0-validate','of_node_put(phy_info_node);','(void)phy_info_node;','LOCAL_CONTAINER_REFS')
    prepare='ssdk_dt_prepare_nodes'
    add('caller-missing-validation',prepare,'id-value-16-topology',
        'ret = ssdk_dt_validate_phy_ports(prepared[num].node);','ret = 0;','PREFLIGHT_BEFORE_ALLOC')
    add('caller-missing-validation-direct',prepare,'later-bad-prepare',
        'ret = ssdk_dt_validate_phy_ports(prepared[num].node);','ret = 0;','PREPARE_RETURN')
    add('caller-ignore-later-error',prepare,'multi-later-invalid',
        'ret = ssdk_dt_validate_phy_ports(prepared[num].node);',
        'ret = num ? 0 : ssdk_dt_validate_phy_ports(prepared[num].node);','PREFLIGHT_BEFORE_ALLOC')
    topology='ssdk_switch_device_num_init'
    add('topology-vector-offset',topology,'same-disabled-two',
        'ssdk_dt_global.ssdk_dt_switch_nodes = nodes;','ssdk_dt_global.ssdk_dt_switch_nodes = nodes + 1;','VECTOR_OWNER_SHAPE')
    add('topology-slot-swap',topology,'same-disabled-two',
        'ssdk_dt_global.ssdk_dt_switch_nodes = nodes;',
        '{ ssdk_dt_cfg *tmp = nodes[0]; nodes[0] = nodes[1]; nodes[1] = tmp; }\n\tssdk_dt_global.ssdk_dt_switch_nodes = nodes;', 'SLOT_OWNER_SHAPE')
    add('topology-slot-alias',topology,'same-disabled-two',
        'ssdk_dt_global.ssdk_dt_switch_nodes = nodes;',
        'nodes[1] = nodes[0];\n\tssdk_dt_global.ssdk_dt_switch_nodes = nodes;','SLOT_OWNER_SHAPE')

    parser='ssdk_dt_parse_phy_info'
    add('parser-change-port',parser,'id-value-0-parse','port_id = port_values.id;','port_id = port_values.id + 1;','EXACT_MODEL_TRACE')
    add('parser-no-dac',parser,'dac-len-8-parse','if (port_values.has_dac)','if (port_values.has_dac && 0)','EXACT_MODEL_TRACE')
    body=bodies[parser]
    dac='\t\tif (port_values.has_dac)\n\t\t\thsl_port_phy_dac_set(dev_id, port_id, port_values.dac);'
    changed=once(body,dac,'')
    changed=once(changed,'\t\t/* initialize phy_addr in case of undefined dts field */',dac+'\n\t\t/* initialize phy_addr in case of undefined dts field */')
    result.append(dict(name='parser-dac-position',symbol=parser,case='rich-parse',before=body,after=changed,
                       marker='EXACT_MODEL_TRACE',classification='directed candidate source-body mutation; same values wrong setter order'))
    add('parser-no-child-put',parser,'id-value-16-parse','of_node_put(port_node);','(void)port_node;','LOCAL_CHILD_REFS')
    add('parser-no-container-put',parser,'id-value-0-parse','of_node_put(phy_info_node);','(void)phy_info_node;','LOCAL_CONTAINER_REFS')
    add('parser-new-error-direct-return',parser,'id-value-16-parse',
        'rv = SW_BAD_VALUE;\n\t\t\tgoto out;','return SW_BAD_VALUE;','LOCAL_CONTAINER_REFS')
    if 'i2c' in profile:
        add('parser-i2c-old-return',parser,'i2c-error-parse',
            'rv = SW_BAD_VALUE;\n\t\t\t\tgoto out;','return SW_BAD_VALUE;','LOCAL_CONTAINER_REFS')
    add('parser-external-old-return',parser,'external-error-parse',
        'rv = SW_NO_RESOURCE;\n\t\t\t\tgoto out;','return SW_NO_RESOURCE;','LOCAL_CONTAINER_REFS')
    return result
