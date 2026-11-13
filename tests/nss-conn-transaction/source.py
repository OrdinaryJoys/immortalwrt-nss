"""Extract the production unit and the host's limited slice of its wire ABI."""

from pathlib import Path
import json
import re


UNIT = "nss_conn_table.c"
ABI_FILES = ("exports/nss_cmn.h", "exports/nss_ipv4.h", "exports/nss_ipv6.h",
             "exports/nss_api_if.h", "exports/nss_dynamic_interface.h", "nss_hlos_if.h",
             "nss_core.h", "nss_tx_rx_common.h")
ENTRYPOINTS = {
    "nss_core.c": ("nss_core_handle_nss_status_pkt", "nss_core_map_linear_cmd", "__nss_core_send_cmd",
                   "nss_core_send_cmd", "nss_core_send_conn_cmd"),
    "nss_ipv4.c": ("nss_ipv4_rx_msg_handler", "nss_ipv4_tx_with_size", "nss_ipv4_tx"),
    "nss_ipv6.c": ("nss_ipv6_rx_msg_handler", "nss_ipv6_tx_with_size", "nss_ipv6_tx"),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def unique(pattern, source, label):
    matches = list(re.finditer(pattern, source, re.M))
    require(len(matches) == 1, f"expected one {label}; found {len(matches)}")
    return matches[0]


def strip_includes(source):
    pattern = r"^\s*#\s*include[ \t]+(?:<[^>\n]+>|\"[^\"\n]+\")[ \t]*(?:/\*[^\n]*\*/)?[ \t]*$"
    result, count = re.subn(pattern, lambda m: "\n" * m[0].count("\n"), source, flags=re.M)
    require(count > 0, f"{UNIT}: no include directives extracted")
    require(not re.search(r"^\s*#\s*include\b", result, re.M),
            f"{UNIT}: unexpected include directive")
    return result


def declaration(source, prefix, suffix=""):
    start = unique(rf"^{re.escape(prefix)}[ \t]*\{{", source, prefix).start()
    end = re.search(rf"^\}}{re.escape(suffix)};", source[start:], re.M)
    require(end is not None, f"unterminated declaration: {prefix}{suffix}")
    return source[start:start + end.end()]


def management_abi(inputs):
    common = inputs["exports/nss_cmn.h"]
    status = unique(r"^typedef enum \{\n[ \t]*NSS_TX_SUCCESS\b[^}]+^\} nss_tx_status_t;",
                    common, "nss_tx_status_t declaration")
    abi = [status[0], declaration(common, "enum nss_cmn_response"),
           declaration(common, "struct nss_cmn_msg"),
           function(common, "nss_cmn_get_msg_len")[0]]
    for version in (4, 6):
        prefix = f"nss_ipv{version}"
        header = inputs[f"exports/{prefix}.h"]
        abi.extend(declaration(header, f"{kind} {prefix}_{name}") for kind, name in (
            ("enum", "message_types"), ("struct", "rule_conn_get_table_size_msg"),
            ("struct", "rule_conn_cfg_msg")))
        message = declaration(header, f"struct {prefix}_msg")
        # Non-management members of these unions are not read, sent or sized by the oracle.
        require(re.search(r"\bstruct nss_cmn_msg cm;", message),
                f"{prefix}_msg: unexpected common-header member")
        for member, name in (("rule_conn_get_table_size_msg", "size"),
                             ("rule_conn_cfg_msg", "rule_conn_cfg")):
            require(re.search(rf"\bstruct {prefix}_{member} {name};", message),
                    f"{prefix}_msg: unexpected management member {name}")
        for member in ("node_stats", "conn_stats", "conn_stats_many"):
            require(re.search(rf"\bstruct \w+ {member};", message),
                    f"{prefix}_msg: unexpected stats member {member}")
        abi.append(f"""struct {prefix}_msg {{
    struct nss_cmn_msg cm;
    union {{
        struct {prefix}_rule_conn_get_table_size_msg size;
        struct {prefix}_rule_conn_cfg_msg rule_conn_cfg;
        /* Only the integration stubs touch these non-management members. */
        uint32_t node_stats, conn_stats, conn_stats_many;
    }} msg;
}};""")
    api = inputs["exports/nss_api_if.h"]
    for name in ("NSS_MAX_PHYSICAL_INTERFACES", "NSS_MAX_VIRTUAL_INTERFACES",
                 "NSS_MAX_TUNNEL_INTERFACES", "NSS_PHYSICAL_IF_START", "NSS_VIRTUAL_IF_START",
                 "NSS_TUNNEL_IF_START", "NSS_DYNAMIC_IF_START", "NSS_SPECIAL_IF_START",
                 "NSS_MAX_DEVICE_INTERFACES", "NSS_MAX_SPECIAL_INTERFACES", "NSS_MAX_NET_INTERFACES",
                 "NSS_IPV4_RX_INTERFACE", "NSS_IPV6_RX_INTERFACE"):
        abi.append(unique(rf"^#define[ \t]+{name}\b[^\n]+", api, name)[0])
    dynamic = inputs["exports/nss_dynamic_interface.h"]
    abi.append(unique(r"^#define[ \t]+NSS_MAX_DYNAMIC_INTERFACES\b[^\n]+",
                      dynamic, "NSS_MAX_DYNAMIC_INTERFACES")[0])
    profile = inputs["nss_hlos_if.h"]
    start = unique(r"^#define NSS_MIN_NUM_CONN\b", profile, "connection profile start").start()
    end = unique(r"^enum \{\n\s*NSS_SUCCESS", profile, "connection profile end").start()
    require(end > start, "invalid connection profile bounds")
    abi.append(profile[start:end])
    for file, macros in (
        ("nss_core.h", ("NSS_NBUF_PAYLOAD_SIZE", "NSS_IF_H2N_CMD_QUEUE", "NSS_CORE_STATUS_SUCCESS")),
        ("nss_tx_rx_common.h", ("NSS_HLOS_MESSAGE_VERSION",)),
        ("nss_hlos_if.h", ("H2N_BUFFER_CTRL", "H2N_BIT_FLAG_BUFFER_REUSABLE")),
    ):
        for name in macros:
            abi.append(unique(rf"^#define[ \t]+{name}\b[^\n]+", inputs[file], name)[0])
    return ("\n\n".join(abi) + "\n").encode()


def function(source, name):
    tokens = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    masked = re.sub(tokens, lambda m: re.sub(r"[^\n]", " ", m[0]), source)
    pattern = rf"^[A-Za-z_]\w*[\w \t*]*\b{re.escape(name)}[ \t]*\([^;{{}}]*\)\s*\{{"
    match = unique(pattern, masked, f"definition of {name}")
    depth = 1
    for brace in re.finditer(r"[{}]", masked[match.end():]):
        depth += 1 if brace[0] == "{" else -1
        if not depth:
            end = match.end() + brace.end()
            return source[match.start():end], source.count("\n", 0, match.start()) + 1
    raise RuntimeError(f"unterminated definition of {name}")


def entrypoints(inputs, input_paths):
    bodies = []
    for name, functions in ENTRYPOINTS.items():
        for symbol in functions:
            body, line = function(inputs[name], symbol)
            bodies.append(f"#line {line} {json.dumps(str(input_paths[name]))}\n{body}\n")
    return "\n".join(bodies)


def paths(root):
    root = Path(root).resolve()
    return {name: root / name for name in (UNIT, *ABI_FILES, *ENTRYPOINTS)}
