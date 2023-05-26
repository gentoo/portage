# Copyright 2019, 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import platform

import pytest

import portage.process
from portage.const import BASH_BINARY
from portage.tests import TestCase


CLONE_NEWNET = 0x40000000
UNSHARE_NET_TEST_SCRIPT = """
ping -c 1 -W 1 127.0.0.1 || exit 1
ping -c 1 -W 1 10.0.0.1 || exit 1
[[ -n ${IPV6} ]] || exit 0
ping -c 1 -W 1 ::1 || exit 1
ping -c 1 -W 1 fd::1 || exit 1
"""
ABILITY_TO_UNSHARE = portage.process._unshare_validate(CLONE_NEWNET)


class UnshareNetTestCase(TestCase):
    @pytest.mark.skipif(
        ABILITY_TO_UNSHARE != 0,
        reason=f"Unable to unshare: {errno.errorcode.get(ABILITY_TO_UNSHARE, '?')}",
    )
    @pytest.mark.skipif(
        portage.process.find_binary("ping") is None, reason="ping not found"
    )
    @pytest.mark.skipif(platform.system() != "Linux", reason="not Linux")
    def testUnshareNet(self):
        AM_I_UNDER_PYTEST = "PYTEST_CURRENT_TEST" in os.environ
        if not AM_I_UNDER_PYTEST:
            if platform.system() != "Linux":
                self.skipTest("not Linux")
            if portage.process.find_binary("ping") is None:
                self.skipTest("ping not found")

            errno_value = portage.process._unshare_validate(CLONE_NEWNET)
            if errno_value != 0:
                self.skipTest(
                    f"Unable to unshare: {errno.errorcode.get(errno_value, '?')}"
                )

        env = os.environ.copy()
        env["IPV6"] = "1" if portage.process._has_ipv6() else ""
        self.assertEqual(
            portage.process.spawn(
                [BASH_BINARY, "-c", UNSHARE_NET_TEST_SCRIPT], unshare_net=True, env=env
            ),
            0,
        )
