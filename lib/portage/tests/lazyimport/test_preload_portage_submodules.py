# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.tests import TestCase

class PreloadPortageSubmodulesTestCase(TestCase):

	def testPreloadPortageSubmodules(self):
		"""
		Verify that _preload_portage_submodules() doesn't leave any
		remaining proxies that refer to the portage.* namespace.
		"""
		portage.proxy.lazyimport._preload_portage_submodules()
		for name in portage.proxy.lazyimport._module_proxies:
			self.assertEqual(name.startswith('portage.'), False)
