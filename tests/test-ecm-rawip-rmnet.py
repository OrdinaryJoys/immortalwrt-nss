#!/usr/bin/env python3
"""Evaluate ECM's actual GNU make options without an OpenWrt build tree."""

import os
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "package/qca-nss/qca-nss-ecm/Makefile"


def evaluate(qmi, rmnet):
    # Only infrastructure includes are stubbed; keep package conditionals and
    # option expressions intact so regressions exercise the production code.
    source = re.sub(r"^include .*\n", "", PACKAGE.read_text(), flags=re.MULTILINE)
    source += "\n.PHONY: audit\naudit:\n\t@echo '$(ECM_MAKE_OPTS)'\n"
    source += "\t@echo '$(PKG_CONFIG_DEPENDS)'\n"
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("CONFIG_") or key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
            del env[key]
    result = subprocess.run(
        ["make", "--no-print-directory", "-f", "-", "audit",
         "CONFIG_TARGET_qualcommax=y", "CONFIG_PACKAGE_kmod-qca-nss-drv=y",
         "CONFIG_PACKAGE_kmod-pppoe=y",
         f"CONFIG_PACKAGE_kmod-qmi_wwan_q={qmi}",
         f"CONFIG_NSS_DRV_RMNET_ENABLE={rmnet}"],
        input=source, text=True, capture_output=True, check=True, env=env,
    )
    options, dependencies = result.stdout.strip().splitlines()
    return options.split(), dependencies.split()


class RawipRmnetTest(unittest.TestCase):
    def test_matrix_and_unrelated_frontends(self):
        # OpenWrt package selections are unset, built-in (y), or module (m).
        # NSS feature selections are booleans (unset or y).
        for qmi in ("", "y", "m"):
            for rmnet in ("", "y"):
                with self.subTest(qmi=qmi, rmnet=rmnet):
                    options, dependencies = evaluate(qmi, rmnet)
                    rawip = [v for v in options if v.startswith("ECM_INTERFACE_RAWIP_ENABLE=")]
                    expected = "y" if qmi and rmnet else "n"
                    self.assertEqual(rawip, [f"ECM_INTERFACE_RAWIP_ENABLE={expected}"])
                    self.assertIn("CONFIG_NSS_DRV_RMNET_ENABLE", dependencies)
                    self.assertIn("CONFIG_PACKAGE_kmod-qmi_wwan_q", dependencies)
                    self.assertIn("ECM_FRONT_END_NSS_ENABLE=y", options)
                    self.assertIn("ECM_INTERFACE_VLAN_ENABLE=y", options)
                    self.assertIn("ECM_INTERFACE_PPPOE_ENABLE=y", options)
                    self.assertIn("ECM_INTERFACE_IPSEC_ENABLE=n", options)


if __name__ == "__main__":
    unittest.main()
