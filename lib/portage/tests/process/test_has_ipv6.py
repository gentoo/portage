# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import socket
from unittest.mock import MagicMock, patch

import portage.process
from portage.tests import TestCase


class HasIpv6TestCase(TestCase):
    def _has_ipv6(self):
        """
        Call has_ipv6() with a cleared cache, and restore the cached
        value afterwards.
        """
        cache = portage.process.__dict__["__has_ipv6"]
        portage.process.__dict__["__has_ipv6"] = None
        try:
            return portage.process.has_ipv6()
        finally:
            portage.process.__dict__["__has_ipv6"] = cache

    def testHasIpv6Supported(self):
        with (
            patch.object(portage.process.socket, "has_ipv6", True),
            patch.object(portage.process.socket, "socket") as mock_socket,
        ):
            self.assertTrue(self._has_ipv6())

        mock_socket.assert_called_once_with(socket.AF_INET6, socket.SOCK_DGRAM)
        mock_socket.return_value.__enter__.return_value.bind.assert_called_once_with(
            ("::1", 0)
        )

    def testHasIpv6BindFailure(self):
        # With ipv6.disable=0 and ipv6.disable_ipv6=1, socket creation
        # succeeds, but the bind call fails.
        sock = MagicMock()
        sock.__enter__.return_value.bind.side_effect = OSError(
            errno.EADDRNOTAVAIL, "Cannot assign requested address"
        )
        with (
            patch.object(portage.process.socket, "has_ipv6", True),
            patch.object(portage.process.socket, "socket", return_value=sock),
        ):
            self.assertFalse(self._has_ipv6())

    def testHasIpv6SocketFailure(self):
        # Socket creation itself fails, e.g. with ipv6.disable=1.
        with (
            patch.object(portage.process.socket, "has_ipv6", True),
            patch.object(
                portage.process.socket,
                "socket",
                side_effect=OSError(errno.EAFNOSUPPORT, "Address family not supported"),
            ),
        ):
            self.assertFalse(self._has_ipv6())

    def testHasIpv6Unsupported(self):
        with patch.object(portage.process.socket, "has_ipv6", False):
            self.assertFalse(self._has_ipv6())

    def testHasIpv6Cached(self):
        # The probe runs once per process, and later calls return the
        # cached value without creating another socket.
        cache = portage.process.__dict__["__has_ipv6"]
        portage.process.__dict__["__has_ipv6"] = None
        try:
            with (
                patch.object(portage.process.socket, "has_ipv6", True),
                patch.object(portage.process.socket, "socket") as mock_socket,
            ):
                self.assertTrue(portage.process.has_ipv6())
                self.assertTrue(portage.process.has_ipv6())
                mock_socket.assert_called_once()
        finally:
            portage.process.__dict__["__has_ipv6"] = cache

    def testHasIpv6CachedFalse(self):
        # A cached False result is returned as-is, rather than being
        # mistaken for an unprobed cache.
        cache = portage.process.__dict__["__has_ipv6"]
        portage.process.__dict__["__has_ipv6"] = False
        try:
            with patch.object(portage.process.socket, "socket") as mock_socket:
                self.assertFalse(portage.process.has_ipv6())
                mock_socket.assert_not_called()
        finally:
            portage.process.__dict__["__has_ipv6"] = cache
