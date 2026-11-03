"""Edits only the actual function bodies, never the test's expected outputs."""

EDITS = {
    "sequence-short": ("scan", "search_sequence", " || sequence_size > buffer_size", ""),
    "sequence-first": ("scan", "search_sequence", "size_t i = 0", "size_t i = 1"),
    "sequence-last": ("scan", "search_sequence", "i <= buffer_size - sequence_size", "i < buffer_size - sequence_size"),
    "sequence-match": ("scan", "search_sequence", "memcmp(buffer + i, sequence, sequence_size) == 0", "memcmp(buffer + i, sequence, sequence_size) != 0"),
    "firmware-offset": ("scan", "nss_hal_firmware_info", "start_pos += sizeof(start_sequence);", "start_pos += 0;"),
    "ppe-copy": ("ppe", "nss_ppe_vp_parse_vp_cmd", "memcpy(cmd_buf, buffer, count);", "cmd_buf[0] = 0;"),
    "ppe-proc": ("ppe", "nss_ppe_vp_parse_vp_cmd", "\tif (ret) {\n\t\treturn ret;\n\t}\n", ""),
    "ppe-type": ("ppe", "nss_ppe_vp_parse_vp_cmd", "kstrtou32(strim(pos), 10, &dynamic_if_type)", "(dynamic_if_type = NSS_DYNAMIC_INTERFACE_TYPE_NONE, 0)"),
    "ppe-read": ("ppe", "nss_ppe_vp_create_handler", "\tif (!write) {\n\t\treturn if_num;\n\t}\n", ""),
    "ppe-put": ("ppe", "nss_ppe_vp_parse_vp_cmd", "\tdev_put(dev);\n\n\treturn if_num;", "\treturn if_num;"),
    "ppe-shared-request": ("ppe", "nss_ppe_vp_parse_vp_cmd", "memcpy(cmd_buf, buffer, count);", "strscpy(cmd_buf, ctl->data, sizeof(cmd_buf));"),
    "ppe-position": ("ppe", "nss_ppe_vp_parse_vp_cmd", "\tif (write && *ppos) {\n\t\treturn -EINVAL;\n\t}\n", ""),
    "mirror-copy": ("mirror", "nss_mirror_ctl_config_handler", "memcpy(buffer, buf, count);", "if (copy_from_user(buffer, buf, count)) { vfree(pfree); return -EFAULT; }"),
    "mirror-limit": ("mirror", "nss_mirror_ctl_config_handler", "\tif (write && (!count || ctl->maxlen <= 0 || count > (size_t)ctl->maxlen)) {\n\t\treturn -E2BIG;\n\t}\n", ""),
    "mirror-proc": ("mirror", "nss_mirror_ctl_config_handler", "\tif (ret || !write) {\n\t\treturn ret;\n\t}\n", ""),
    "mirror-empty-name": ("mirror", "nss_mirror_ctl_get_netdev_by_name", "\tif (!name || !*name) {\n\t\treturn -1;\n\t}\n", ""),
    "mirror-display-empty": ("mirror", "nss_mirror_ctl_parse_display_cmd", "!param || !value || !*value", "!param || !value"),
    "mirror-next-empty": ("mirror", "nss_mirror_ctl_parse_set_nexthop_cmd", "if (*value && value[strlen(value) - 1] == '\\n')", "if (value[strlen(value) - 1] == '\\n')"),
    "tunip-copy": ("tunip", "nss_tunipip6_data_parser", "memcpy(buf, buffer, count);", "if (copy_from_user(buf, buffer, count)) { kfree(pfree); return -EFAULT; }"),
    "tunip-limit": ("tunip", "nss_tunipip6_data_parser", "\tif (!count || count > MAX_PROC_SIZE) {\n\t\treturn -E2BIG;\n\t}\n", ""),
    "tunip-size": ("tunip", "nss_tunipip6_data_parser", "kzalloc(MAX_PROC_SIZE + 1, GFP_KERNEL)", "kzalloc(MAX_PROC_SIZE, GFP_KERNEL)"),
    "tunip-suffix-length": ("tunip", "nss_tunipip6_data_parser", " && ipv6_suffix_len_valid &&", " && (ipv6_suffix_len_valid || 1) &&"),
}


def changed(bodies, name):
    group, function, before, after = EDITS[name]
    text = bodies[group][function]
    if text.count(before) != 1:
        raise ValueError("UNIQUE_MUTATION: " + name)
    new = {g: dict(v) for g,v in bodies.items()}
    new[group][function] = text.replace(before,after,1)
    if name == "tunip-suffix-length":
        # Safe regression witness: do not execute the old uninitialized read.
        anchor="ipv6_suffix_len, ipv4_prefix"
        if new[group][function].count(anchor)!=1:
            raise ValueError("SUFFIX_SAFE_INITIALIZATION")
        new[group][function]=new[group][function].replace(anchor,"ipv6_suffix_len = 0, ipv4_prefix",1)
    return new
