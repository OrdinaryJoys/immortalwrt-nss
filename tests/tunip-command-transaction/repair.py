"""Explicit source-data edits for the additive post026 tunip patch."""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("UNIQUE_REPAIR_PREIMAGE: " + old)
    return text.replace(old, new, 1)


def repaired(text):
    text = once(text, '#include <linux/sysctl.h>', '#include <linux/sysctl.h>\n#include <linux/errno.h>')
    entry = 'static int nss_tunipip6_data_parser('
    helper = '''/* Translate client status, not its positive enum value, to sysctl errno. */
static int nss_tunipip6_sysctl_errno(enum nss_connmgr_tunipip6_err_codes status)
{
\tswitch (status) {
\tcase NSS_CONNMGR_TUNIPIP6_SUCCESS:
\t\treturn 0;
\tcase NSS_CONNMGR_TUNIPIP6_INVALID_PARAM:
\tcase NSS_CONNMGR_TUNIPIP6_INVALID_RULE_TYPE:
\t\treturn -EINVAL;
\tcase NSS_CONNMGR_TUNIPIP6_NO_DEV:
\t\treturn -ENODEV;
\tdefault:
\t\treturn -EIO;
\t}
}

'''
    text = once(text, entry, helper + entry)
    text = once(text, '\tint rule_type = 0, frag_id = 0;',
                '\tint rule_type = 0, frag_id = 0;\n\tbool frag_id_valid = false;')
    text = once(text, '\tint ret;\n\tsize_t count = *lenp;',
                '\tint ret;\n\tint error = -EINVAL;\n\tsize_t count;')
    text = once(text, '        if (!write) {\n                return -EINVAL;\n        }',
                '\tif (!write || !buffer || !lenp) {\n\t\treturn -EINVAL;\n\t}\n\tcount = *lenp;')
    old = '''\t\tif (!strcmp(param, "netdev")) {
\t\t\tstrscpy(dev_name, value, 30);
\t\t\tdev = dev_get_by_name(&init_net, dev_name);
\t\t\tif (!dev) {
\t\t\t\tkfree(pfree);
\t\t\t\tgoto fail;
\t\t\t}
'''
    new = '''\t\tif (!strcmp(param, "netdev")) {
\t\t\tstruct net_device *next_dev;

\t\t\tstrscpy(dev_name, value, 30);
\t\t\tnext_dev = dev_get_by_name(&init_net, dev_name);
\t\t\tif (!next_dev) {
\t\t\t\terror = -ENODEV;
\t\t\t\tgoto fail;
\t\t\t}
\t\t\tif (dev) {
\t\t\t\tdev_put(dev);
\t\t\t}
\t\t\tdev = next_dev;
'''
    text = once(text, old, new)
    # Every parsed-error path has one local-buffer/ref exit, including replacement
    # lookup failure. Do not invoke global cleanup or provider compensation.
    text = text.replace('\t\t\tkfree(pfree);\n\t\t\tgoto fail;', '\t\t\tgoto fail;')
    text = text.replace('\t\t\t\tkfree(pfree);\n\t\t\t\tgoto fail;', '\t\t\t\tgoto fail;')
    text = once(text, '\t\t\tif (frag_id != 0 && frag_id != 1) {\n\t\t\t\tgoto fail;\n\t\t\t}\n\t\t\tcontinue;',
                '\t\t\tif (frag_id != 0 && frag_id != 1) {\n\t\t\t\tgoto fail;\n\t\t\t}\n\t\t\tfrag_id_valid = true;\n\t\t\tcontinue;')
    text = once(text, '\tkfree(pfree);\n\n\t/*\n\t * Netdev param',
                '\tkfree(pfree);\n\tpfree = NULL;\n\n\t/*\n\t * Netdev param')
    text = once(text, '\tcase NSS_TUNIPIP6_SYSCTL_FRAG_ID:\n\t\tif ((netdev_valid',
                '\tcase NSS_TUNIPIP6_SYSCTL_FRAG_ID:\n\t\tif (!frag_id_valid || (netdev_valid')
    old = '''\t\treturn 0;
\t}

\tdev_put(dev);
\treturn 0;

fail:
\tif (dev) {
\t\tdev_put(dev);
\t}

\tpr_info("Wrong input, check help. (cat /proc/sys/dev/nss/ipip6/help)\\n");
\treturn 0;
}'''
    new = '''\t\terror = 0;
\t\tgoto out;
\tdefault:
\t\tgoto fail;
\t}

\terror = nss_tunipip6_sysctl_errno(status);
\tgoto out;

fail:
\tpr_info("Wrong input, check help. (cat /proc/sys/dev/nss/ipip6/help)\\n");
out:
\tif (dev) {
\t\tdev_put(dev);
\t}
\tkfree(pfree);
\treturn error;
}'''
    return once(text, old, new)
