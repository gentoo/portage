# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class SimpleResolverTestCase(TestCase):

	def testSimple(self):
		ebuilds = {
			"dev-libs/A-1": {}, 
			"dev-libs/A-2": { "KEYWORDS": "~x86" },
			"dev-libs/B-1.2": {},
			}
		installed = {
			"dev-libs/B-1.1": {},
			}

		requests = (
				(["dev-libs/A"], {}, None, True, ["dev-libs/A-1"]),
				(["=dev-libs/A-2"], {}, None, False, None),
				(["dev-libs/B"], {"--noreplace": True}, None, True, []),
				(["dev-libs/B"], {"--update": True}, None, True, ["dev-libs/B-1.2"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

		for atoms, options, action, expected_result, expected_mergelist in requests:
			success, mergelist = playground.run(atoms, options, action)
			self.assertEqual(success, expected_result)
			if success:
				self.assertEqual(mergelist, expected_mergelist)
