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


class UnshareNetTestCase(TestCase):
    def setUp(self):
        """
        Initialize ABILITY_TO_UNSHARE in setUp so that _unshare_validate
        uses the correct PORTAGE_MULTIPROCESSING_START_METHOD setup
        from super().setUp().
        """
        super().setUp()
        self.ABILITY_TO_UNSHARE = portage.process._unshare_validate(CLONE_NEWNET)

    @pytest.mark.skipif(
        portage.process.find_binary("ping") is None, reason="ping not found"
    )
    @pytest.mark.skipif(platform.system() != "Linux", reason="not Linux")
    def testUnshareNet(self):
        if self.ABILITY_TO_UNSHARE != 0:
            pytest.skip(
                f"Unable to unshare: {errno.errorcode.get(self.ABILITY_TO_UNSHARE, '?')}"
            )
        env = os.environ.copy()
        env["IPV6"] = "1" if portage.process.has_ipv6() else ""
        self.assertEqual(
            portage.process.spawn(
                [BASH_BINARY, "-c", UNSHARE_NET_TEST_SCRIPT], unshare_net=True, env=env
            ),
            0,
        )
