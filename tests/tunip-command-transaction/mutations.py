"""Source-compatible directed edits; expectations live independently in runner."""
PARSER = 'nss_tunipip6_data_parser'
MAPPER = 'nss_tunipip6_sysctl_errno'
EDITS = {
    'replace-leaks-old': (PARSER, '\t\t\tif (dev) {\n\t\t\t\tdev_put(dev);\n\t\t\t}\n\t\t\tdev = next_dev;', '\t\t\tdev = next_dev;'),
    'replace-puts-new': (PARSER, '\t\t\t\tdev_put(dev);', '\t\t\t\tdev_put(next_dev);'),
    'missing-loses-old': (PARSER, '\t\t\tif (!next_dev) {', '\t\t\tif (!next_dev) {\n\t\t\t\tdev = NULL;'),
    'exit-leaks-ref': (PARSER, 'out:\n\tif (dev) {\n\t\tdev_put(dev);\n\t}', 'out:\n\tif (dev) {\n\t\t(void)dev;\n\t}'),
    'missing-errno': (PARSER, 'error = -ENODEV;', 'error = -EINVAL;'),
    'semantic-success': (PARSER, 'int error = -EINVAL;', 'int error = 0;'),
    'swallow-final-error': (PARSER, '\treturn error;', '\t(void)error;\n\treturn 0;'),
    'ignore-frag-presence': (PARSER, '!frag_id_valid ||', '(!frag_id_valid && 0) ||'),
    'never-frag-present': (PARSER, '\t\t\tfrag_id_valid = true;', '\t\t\tfrag_id_valid = false;'),
    'wrong-frag-value': (PARSER, 'frag_id_update = true;', 'frag_id_update = false;'),
    'skip-provider-error': (PARSER, 'error = nss_tunipip6_sysctl_errno(status);', 'error = (nss_tunipip6_sysctl_errno(status), 0);'),
    'invalid-map-error': (MAPPER, '\t\treturn -EINVAL;', '\t\treturn -EIO;'),
    'node-map-error': (MAPPER, '\t\treturn -ENODEV;', '\t\treturn -EIO;'),
    'io-map-success': (MAPPER, '\t\treturn -EIO;', '\t\treturn 0;'),
    'success-map-error': (MAPPER, '\t\treturn 0;', '\t\treturn -EIO;'),
    'exit-leaks-buffer': (PARSER, '\tkfree(pfree);\n\treturn error;', '\treturn error;'),
    'double-free-buffer': (PARSER, '\tpfree = NULL;', '\t/* Removed ownership consumption. */'),
    'no-publish-device': (PARSER, '\t\t\tdev = next_dev;', '\t\t\t(void)next_dev;'),
}
for short, function, mode in (
        ('add', 'nss_tunipip6_cmd_procfs_add_maprule', 'NSS_TUNIPIP6_SYSCTL_ADD_MAPRULE'),
        ('del', 'nss_tunipip6_cmd_procfs_del_maprule', 'NSS_TUNIPIP6_SYSCTL_DEL_MAPRULE'),
        ('flush', 'nss_tunipip6_cmd_procfs_flush_fmr_rule', 'NSS_TUNIPIP6_SYSCTL_FLUSH_FMR_RULE'),
        ('frag', 'nss_tunipip6_cmd_procfs_enable_frag_id', 'NSS_TUNIPIP6_SYSCTL_FRAG_ID')):
    call = 'nss_tunipip6_data_parser(ctl, write, buffer, lenp, ppos, '+mode+')'
    EDITS['wrapper-'+short] = (function, 'return '+call+';', 'return ('+call+', 0);')


def changed(bodies, name):
    function, old, new = EDITS[name]
    if bodies[function].count(old) != 1:
        raise ValueError('UNIQUE_SOURCE_MUTATION: '+name)
    result = dict(bodies)
    result[function] = result[function].replace(old, new, 1)
    return result
