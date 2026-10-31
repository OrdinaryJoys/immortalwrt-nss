"""Semantic edits to actual source, not edits to the native models."""


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("MUTANT_ANCHOR: " + before)
    return text.replace(before, after, 1)


EDITS = {
    "premature-ready": ("uk_state = UK_STARTING;", "uk_state = UK_READY;"),
    "register-under-api-lock": (
        "    mutex_unlock(&api_ioctl_lock);\n\n    /* misc_register/deregister",
        "\n    /* misc_register/deregister"),
    "failed-register-deregisters-foreign": (
        "if (misc_register(&switch_device)) {",
        "if (misc_register(&switch_device)) {\n        misc_deregister(&switch_device);"),
    "ignore-file-epoch": ("context->epoch == uk_epoch;", "context->epoch != 0;"),
    "close-keeps-context": ("    file->private_data = NULL;", "    /* omitted close consume */"),
    "cleanup-resets-epoch": (
        "    uk_state = UK_OFF;\nunlock:", "    uk_state = UK_OFF;\n    uk_epoch = 0;\nunlock:"),
    "commit-no-epoch-increment": ("    ++uk_epoch;", "    /* omitted successful epoch */"),
    "no-epoch-cap": ("if (uk_epoch == (a_uint64_t)-1)", "if (0)"),
    "cleanup-blocks-on-command": (
        "sw_uk_cleanup(void)\n{", "sw_uk_cleanup(void)\n{"),
    "accept-conflicting-protocol": (
        "rv = protocol == uk_protocol ? SW_OK : SW_BAD_PARAM;", "rv = SW_OK;"),
    "wrong-context-oom": ("        return -ENOMEM;", "        return -ENODEV;"),
    "compat-output-native-rounding": (
        "a_uint32_t offset = args ? sizeof(unsigned long):sizeof(a_uint32_t);\n    a_uint32_t credit = args ? (sizeof(unsigned long) - 1):(sizeof(a_uint32_t) - 1);",
        "a_uint32_t offset = sizeof(unsigned long);\n    a_uint32_t credit = sizeof(unsigned long) - 1;"),
    "swap-dispatch-two-arguments": ("rv = (func) (p[0], p[1]);", "rv = (func) (p[1], p[0]);"),
    "publish-buffer-before-register": (
        "    uk_state = UK_STARTING;", "    cmd_buf = buffer;\n    uk_state = UK_STARTING;"),
}


def variants(text):
    result = {}
    for name, (before, after) in EDITS.items():
        if name == "cleanup-blocks-on-command":
            start = text.index("sw_uk_cleanup(void)\n{")
            head, tail = text[:start], text[start:]
            tail = once(tail, "if (!mutex_trylock(&api_ioctl_lock))",
                        "if ((mutex_lock(&api_ioctl_lock), 0))")
            result[name] = head + tail
        else:
            result[name] = once(text, before, after)
        if result[name] == text:
            raise ValueError("UNCHANGED_MUTANT: " + name)
    return result
