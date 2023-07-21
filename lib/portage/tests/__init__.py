# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import sys
import time
import unittest
from pathlib import Path

from unittest.runner import TextTestResult as _TextTestResult

import portage
from portage import os
from portage.util import no_color
from portage import _encodings
from portage import _unicode_decode
from portage.output import colorize
from portage.proxy.objectproxy import ObjectProxy


# This remains constant when the real value is a mock.
EPREFIX_ORIG = portage.const.EPREFIX


class lazy_value(ObjectProxy):
    __slots__ = ("_func",)

    def __init__(self, func):
        ObjectProxy.__init__(self)
        object.__setattr__(self, "_func", func)

    def _get_target(self):
        return object.__getattribute__(self, "_func")()


@lazy_value
def cnf_path():
    if portage._not_installed:
        return os.path.join(portage.const.PORTAGE_BASE_PATH, "cnf")
    return os.path.join(
        EPREFIX_ORIG or "/", portage.const.GLOBAL_CONFIG_PATH.lstrip(os.sep)
    )


@lazy_value
def cnf_etc_path():
    if portage._not_installed:
        return str(cnf_path)
    return os.path.join(EPREFIX_ORIG or "/", "etc")


@lazy_value
def cnf_bindir():
    if portage._not_installed:
        return portage.const.PORTAGE_BIN_PATH
    return os.path.join(portage.const.EPREFIX or "/", "usr", "bin")


@lazy_value
def cnf_sbindir():
    if portage._not_installed:
        return str(cnf_bindir)
    return os.path.join(portage.const.EPREFIX or "/", "usr", "sbin")


class TestCase(unittest.TestCase):
    """
    We need a way to mark a unit test as "ok to fail"
    This way someone can add a broken test and mark it as failed
    and then fix the code later.  This may not be a great approach
    (broken code!!??!11oneone) but it does happen at times.
    """

    def __init__(self, *pargs, **kwargs):
        unittest.TestCase.__init__(self, *pargs, **kwargs)
        self.cnf_path = cnf_path
        self.cnf_etc_path = cnf_etc_path
        self.bindir = cnf_bindir
        self.sbindir = cnf_sbindir

    def assertRaisesMsg(self, msg, excClass, callableObj, *args, **kwargs):
        """Fail unless an exception of class excClass is thrown
        by callableObj when invoked with arguments args and keyword
        arguments kwargs. If a different type of exception is
        thrown, it will not be caught, and the test case will be
        deemed to have suffered an error, exactly as for an
        unexpected exception.
        """
        try:
            callableObj(*args, **kwargs)
        except excClass:
            return
        else:
            if hasattr(excClass, "__name__"):
                excName = excClass.__name__
            else:
                excName = str(excClass)
            raise self.failureException(f"{excName} not raised: {msg}")

    def assertNotExists(self, path):
        """Make sure |path| does not exist"""
        path = Path(path)
        if path.exists():
            raise self.failureException(f"path exists when it should not: {path}")


test_cps = ["sys-apps/portage", "virtual/portage"]
test_versions = ["1.0", "1.0-r1", "2.3_p4", "1.0_alpha57"]
test_slots = [None, "1", "gentoo-sources-2.6.17", "spankywashere"]
test_usedeps = ["foo", "-bar", ("foo", "bar"), ("foo", "-bar"), ("foo?", "!bar?")]
