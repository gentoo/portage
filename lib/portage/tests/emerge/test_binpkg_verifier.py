# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from _emerge.BinpkgVerifier import BinpkgVerifier

from portage.tests import TestCase
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop


class _FakeBintree:
    def __init__(self, digests):
        self.settings = {}
        self._digests = digests

    def _get_digests(self, pkg):
        return self._digests


class _FakeRootConfig:
    def __init__(self, bintree):
        self.trees = {"bintree": bintree}


class _FakePkg:
    def __init__(self, digests, remote, cpv="dev-libs/A-1"):
        self.root_config = _FakeRootConfig(_FakeBintree(digests))
        self.cpv = cpv
        self.remote = remote


class BinpkgVerifierMissingDigestTestCase(TestCase):
    """
    Verify we need both SIZE and digests for remote packages.
    """

    def _verify(self, digests, remote):
        scheduler = SchedulerInterface(global_event_loop())
        verifier = BinpkgVerifier(
            pkg=_FakePkg(digests, remote),
            scheduler=scheduler,
            _pkg_path="/nonexistent",
        )
        verifier.start()
        return verifier.wait()

    def testRemoteWithNoDigests(self):
        self.assertNotEqual(self._verify({}, remote=True), os.EX_OK)

    def testRemoteWithSizeOnly(self):
        self.assertNotEqual(self._verify({"size": 123}, remote=True), os.EX_OK)

    def testRemoteWithChecksumOnly(self):
        # Without a size the verifier returned EX_OK without hashing
        # anything, so a missing SIZE skipped verification too.
        self.assertNotEqual(self._verify({"SHA512": "0" * 128}, remote=True), os.EX_OK)

    def testLocalWithNoDigests(self):
        # PKGDIR is under the administrator's control, so a missing
        # index entry there is a configuration problem, not a refusal.
        self.assertEqual(self._verify({}, remote=False), os.EX_OK)
