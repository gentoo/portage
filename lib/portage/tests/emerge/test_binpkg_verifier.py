# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import tempfile
from unittest.mock import patch

from _emerge import BinpkgVerifier as _BinpkgVerifier
from _emerge.BinpkgVerifier import BinpkgVerifier
from portage.checksum import perform_multiple_checksums

from portage.tests import TestCase
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop


class _FakeBintree:
    def __init__(self, digests):
        self.settings = {}
        self._digests = digests
        self._verified_pkgs = {}

    def _get_digests(self, pkg):
        return self._digests


class _FakeRootConfig:
    def __init__(self, bintree):
        self.settings = {"PORTAGE_QUIET": "1"}
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


class BinpkgVerifierCacheTestCase(TestCase):
    """
    A file that has been verified is not hashed again until it changes.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "A-1.gpkg.tar")
        with open(self.path, "wb") as f:
            f.write(b"binpkg" * 1000)
        digests = perform_multiple_checksums(self.path, ["SHA512"])
        digests["size"] = os.stat(self.path).st_size
        self.pkg = _FakePkg(digests, remote=False)
        self.hashed = 0

    def tearDown(self):
        self.tmpdir.cleanup()

    def _verify(self):
        orig = _BinpkgVerifier.FileDigester

        def digester(**kwargs):
            self.hashed += 1
            return orig(**kwargs)

        with patch.object(_BinpkgVerifier, "FileDigester", digester):
            verifier = BinpkgVerifier(
                pkg=self.pkg,
                scheduler=SchedulerInterface(global_event_loop()),
                _pkg_path=self.path,
            )
            verifier.start()
            return verifier.wait()

    def testVerifiedOnce(self):
        self.assertEqual(self._verify(), os.EX_OK)
        self.assertEqual(self._verify(), os.EX_OK)
        self.assertEqual(self.hashed, 1)

    def testRenamed(self):
        self.assertEqual(self._verify(), os.EX_OK)
        renamed = self.path + ".moved"
        os.rename(self.path, renamed)
        self.path = renamed
        self.assertEqual(self._verify(), os.EX_OK)
        self.assertEqual(self.hashed, 1)

    def testChanged(self):
        self.assertEqual(self._verify(), os.EX_OK)
        st = os.stat(self.path)
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
        self.assertEqual(self._verify(), os.EX_OK)
        self.assertEqual(self.hashed, 2)
