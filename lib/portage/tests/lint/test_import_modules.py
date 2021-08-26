# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import os

from portage.const import PORTAGE_PYM_PATH, PORTAGE_PYM_PACKAGES
from portage.tests import TestCase
from portage import _encodings
from portage import _unicode_decode

class ImportModulesTestCase(TestCase):

	def testImportModules(self):
		expected_failures = frozenset((
		))

		iters = (self._iter_modules(os.path.join(PORTAGE_PYM_PATH, x))
			for x in PORTAGE_PYM_PACKAGES)
		for mod in chain(*iters):
			try:
				__import__(mod)
			except ImportError as e:
				if mod not in expected_failures:
					self.assertTrue(False, "failed to import '%s': %s" % (mod, e))
				del e

	def _iter_modules(self, base_dir):
		for parent, dirs, files in os.walk(base_dir):
			parent_mod = parent[len(str(PORTAGE_PYM_PATH))+1:]
			parent_mod = parent_mod.replace("/", ".")
			for x in files:
				if x[-3:] != '.py':
					continue
				x = x[:-3]
				if x[-8:] == '__init__':
					x = parent_mod
				else:
					x = parent_mod + "." + x
				yield x
