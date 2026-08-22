# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shelve
import tempfile

from portage._emirrordist.Config import Config
from portage.tests import TestCase


def _binunicode(s):
    b = s.encode()
    return b"X" + len(b).to_bytes(4, "little") + b


def _unreadable_pickle():
    """
    A pickle that names a class portage does not have, which is the shape
    of failure a stored object graph takes once its classes have drifted
    (bug 981223). The real damaged rows hold pickled _pkg_str graphs, but
    reproducing one exactly relies on how a given pickle implementation
    restores instance state, and PyPy and CPython do not agree on that, so
    craft a value that no implementation can load instead.
    """
    return b"".join(
        (
            b"\x80\x02",
            b"cportage.dep\n_NoSuchClassForTesting\n",
            _binunicode("dev-libs/foo"),
            b"\x85\x81",  # TUPLE1, NEWOBJ
            b".",
        )
    )


def _config(distfiles_db):
    """
    A Config with just enough set up to call lookup_cpv. Config.__init__
    needs a portdb and an on-disk layout.conf, neither of which this
    exercises.
    """
    config = Config.__new__(Config)
    config.distfiles_db = distfiles_db
    config.distfiles_db_unreadable = False
    return config


class LookupCpvTestCase(TestCase):
    def testNoDatabase(self):
        self.assertEqual(_config(None).lookup_cpv("foo-1.tar.xz"), "unknown")

    def testMissingKey(self):
        self.assertEqual(_config({}).lookup_cpv("foo-1.tar.xz"), "unknown")

    def testPresentKey(self):
        config = _config({"foo-1.tar.xz": "dev-libs/foo-1"})
        self.assertEqual(config.lookup_cpv("foo-1.tar.xz"), "dev-libs/foo-1")

    def testUnpicklingFailure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "distfiles.db")
            try:
                db = shelve.open(db_path, flag="c")
            except ImportError:
                self.skipTest("no dbm implementation available")

            with db:
                db["good-1.tar.xz"] = "dev-libs/good-1"
                # Bypass the Shelf pickling layer to plant a raw value.
                db.dict[b"bad-1.tar.xz"] = _unreadable_pickle()

            with shelve.open(db_path, flag="r") as db:
                # Guard against the crafted pickle loading after all, which
                # would leave nothing testing the real bug. Which exception
                # it raises is up to the pickle implementation, so do not
                # pin one down.
                self.assertRaises(Exception, db.__getitem__, "bad-1.tar.xz")

                config = _config(db)
                self.assertEqual(config.lookup_cpv("bad-1.tar.xz"), "unknown")
                self.assertTrue(config.distfiles_db_unreadable)
                self.assertEqual(config.lookup_cpv("good-1.tar.xz"), "dev-libs/good-1")
                self.assertEqual(config.lookup_cpv("absent-1.tar.xz"), "unknown")
