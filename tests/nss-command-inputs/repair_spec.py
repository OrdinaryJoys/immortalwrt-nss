"""Exact old->new leaf edits used to emit reviewable additive patches."""
import argparse
import difflib
from pathlib import Path


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("REPAIR_PREIMAGE: " + old)
    return text.replace(old, new, 1)


def edits(label, relative, text):
    if relative == "nss_hal/nss_hal.c":
        return once(text, "{\n\tfor (size_t i = 0; i <= buffer_size - sequence_size; i++) {",
                    "{\n\tif (!buffer || !sequence || !sequence_size || sequence_size > buffer_size) {\n\t\treturn NULL;\n\t}\n\n\tfor (size_t i = 0; i <= buffer_size - sequence_size; i++) {")
    if relative == "nss_ppe_vp.c":
        text = once(text, "\tint ret = proc_dostring(ctl, write, buffer, lenp, ppos);\n\n\tif (!write) {",
                    "\tsize_t count = *lenp;\n\tint ret;\n\n\tif (write && *ppos) {\n\t\treturn -EINVAL;\n\t}\n\tif (write && (!count || count >= sizeof(cmd_buf))) {\n\t\treturn -E2BIG;\n\t}\n\tret = proc_dostring(ctl, write, buffer, lenp, ppos);\n\tif (ret) {\n\t\treturn ret;\n\t}\n\n\tif (!write) {")
        text = once(text, "\t/* proc_dostring has already copied the data to nss_ppe_vp_cmd */",
                    "\t/* The sysctl kernel buffer belongs to this request; ctl->data is shared. */\n\tmemcpy(cmd_buf, buffer, count);")
        text = once(text, '\tif (sscanf(cmd_buf, "%s %u", dev_name, &dynamic_if_type) < 0) {',
                    '\tpos = strim(cmd_buf);\n\tif (strscpy(dev_name, strsep(&pos, " \\t"), IFNAMSIZ) < 0 || !dev_name[0]) {\n\t\treturn -EINVAL;\n\t}\n\tif (pos && *strim(pos) && kstrtou32(strim(pos), 10, &dynamic_if_type)) {')
        text = once(text, "if ((dynamic_if_type < NSS_DYNAMIC_INTERFACE_TYPE_NONE) || (dynamic_if_type >= NSS_DYNAMIC_INTERFACE_TYPE_MAX))",
                    "if (dynamic_if_type >= NSS_DYNAMIC_INTERFACE_TYPE_MAX)")
        anchor = "\tif_num = nss_ppe_vp_parse_vp_cmd(ctl, write, buffer, lenp, ppos);\n\tif (if_num < 0) {"
        if text.count(anchor) != 2:
            raise ValueError("PPE_CALLERS")
        text = text.replace(anchor, "\tif_num = nss_ppe_vp_parse_vp_cmd(ctl, write, buffer, lenp, ppos);\n\tif (!write) {\n\t\treturn if_num;\n\t}\n\tif (if_num < 0) {")
        anchor = '\t\tnss_warning("%px: Invalid interface number: %d", nss_ctx, if_num);\n\t\treturn -EFAULT;'
        if text.count(anchor) != 2:
            raise ValueError("PPE_ERROR_CALLERS")
        return text.replace(anchor, '\t\tnss_warning("%px: Invalid interface number: %d", nss_ctx, if_num);\n\t\treturn if_num;')
    if relative == "mirror/nss_mirror_ctl.c":
        text = once(text, "\tchar dev_name[IFNAMSIZ] = {0};\n\n\tstrscpy(dev_name, name, IFNAMSIZ);",
                    "\tchar dev_name[IFNAMSIZ] = {0};\n\n\tif (!name || !*name) {\n\t\treturn -1;\n\t}\n\n\tstrscpy(dev_name, name, IFNAMSIZ);")
        text = once(text, "\tsize_t count = *lenp;\n\n\t/*", "\tsize_t count = *lenp;\n\n\tif (write && (!count || ctl->maxlen <= 0 || count > (size_t)ctl->maxlen)) {\n\t\treturn -E2BIG;\n\t}\n\n\t/*")
        text = once(text, "\tif (copy_from_user(buffer, buf, count)) {\n\t\tvfree(pfree);\n\t\treturn -EFAULT;\n\t}",
                    "\t/* Sysctl supplies kernel memory on Linux6.18. */\n\tmemcpy(buffer, buf, count);")
        return once(text, "\tif (!nextarg) {\n\t\tgoto err;", "\tif (!nextarg || !*nextarg) {\n\t\tgoto err;")
    if relative == "tunipip6/nss_connmgr_tunipip6_sysctl.c":
        text = once(text, "#include <linux/sysctl.h>", "#include <linux/sysctl.h>\n#include <linux/string.h>")
        text = once(text, "\tint count;", "\tsize_t count = *lenp;")
        text = once(text, "        if (!write) {", "\t/* This write-only parser uses the request, not ctl storage or offsets. */\n\t(void)ctl;\n\t(void)ppos;\n\n        if (!write) {")
        text = once(text, "\tbuf = kzalloc(MAX_PROC_SIZE, GFP_KERNEL);", "\tif (!count || count > MAX_PROC_SIZE) {\n\t\treturn -E2BIG;\n\t}\n\n\tbuf = kzalloc(MAX_PROC_SIZE + 1, GFP_KERNEL);")
        text = once(text, "\tcount = *lenp;\n\tif (count > MAX_PROC_SIZE) {\n\t\tcount = MAX_PROC_SIZE;\n\t}\n\n\tif (copy_from_user(buf, buffer, count)) {\n\t\tkfree(pfree);\n\t\treturn -EFAULT;\n\t}",
                    "\t/* Keep a terminator even for a full MAX_PROC_SIZE kernel input. */\n\tmemcpy(buf, buffer, count);")
        text = once(text, "if (!(rule_type_valid && ipv6_prefix_valid && ipv6_prefix_len_valid && ipv6_suffix_valid &&",
                    "if (!(rule_type_valid && ipv6_prefix_valid && ipv6_prefix_len_valid && ipv6_suffix_valid && ipv6_suffix_len_valid &&")
        return text
    raise ValueError((label, relative))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("label", choices=("driver", "clients"))
    args = parser.parse_args()
    files = ("nss_hal/nss_hal.c", "nss_ppe_vp.c") if args.label == "driver" else (
        "mirror/nss_mirror_ctl.c", "tunipip6/nss_connmgr_tunipip6_sysctl.c")
    print("From: AX6 NSS input repair\nSubject: [PATCH] Parse bounded kernel commands and guard sequence searches\n")
    for relative in files:
        old = (args.baseline / relative).read_text()
        new = edits(args.label, relative, old)
        print("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
              fromfile="a/" + relative, tofile="b/" + relative)), end="")


if __name__ == "__main__":
    main()
