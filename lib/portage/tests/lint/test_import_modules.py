# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain

from portage.const import PORTAGE_PYM_PATH, PORTAGE_PYM_PACKAGES
from portage.tests import TestCase
from portage import os_unicode_fs


class ImportModulesTestCase(TestCase):
    def testImportModules(self):
        expected_failures = frozenset(())

        iters = (
            self._iter_modules(os_unicode_fs.path.join(PORTAGE_PYM_PATH, x))
            for x in PORTAGE_PYM_PACKAGES
        )
        for mod in chain(*iters):
            try:
                __import__(mod)
            except ImportError as e:
                if mod not in expected_failures:
                    self.assertTrue(False, "failed to import '%s': %s" % (mod, e))
                del e

    def _iter_modules(self, base_dir):
        for parent, dirs, files in os_unicode_fs.walk(base_dir):
            parent = parent.decode(encoding="utf-8", errors="strict")
            parent_mod = parent[len(PORTAGE_PYM_PATH) + 1 :]
            parent_mod = parent_mod.replace("/", ".")
            for x in files:
                x = x.decode(encoding="utf-8", errors="strict")
                if x[-3:] != ".py":
                    continue
                x = x[:-3]
                if x[-8:] == "__init__":
                    x = parent_mod
                else:
                    x = parent_mod + "." + x
                yield x
