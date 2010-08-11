# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class EAPITestCase(TestCase):

	def testEAPI(self):
		ebuilds = {
			#EAPI-1: IUSE-defaults
			"dev-libs/A-1.0": { "EAPI": 0, "IUSE": "+foo" }, 
			"dev-libs/A-1.1": { "EAPI": 1, "IUSE": "+foo" }, 
			"dev-libs/A-1.2": { "EAPI": 2, "IUSE": "+foo" }, 
			"dev-libs/A-1.3": { "EAPI": 3, "IUSE": "+foo" }, 
			#~ "dev-libs/A-1.4": { "EAPI": 4, "IUSE": "+foo" }, 

			#EAPI-1: slot deps
			"dev-libs/A-2.0": { "EAPI": 0, "DEPEND": "dev-libs/B:0" }, 
			"dev-libs/A-2.1": { "EAPI": 1, "DEPEND": "dev-libs/B:0" }, 
			"dev-libs/A-2.2": { "EAPI": 2, "DEPEND": "dev-libs/B:0" }, 
			"dev-libs/A-2.3": { "EAPI": 3, "DEPEND": "dev-libs/B:0" }, 
			#~ "dev-libs/A-2.4": { "EAPI": 4, "DEPEND": "dev-libs/B:0" }, 

			#EAPI-2: use deps
			"dev-libs/A-3.0": { "EAPI": 0, "DEPEND": "dev-libs/B[foo]" }, 
			"dev-libs/A-3.1": { "EAPI": 1, "DEPEND": "dev-libs/B[foo]" }, 
			"dev-libs/A-3.2": { "EAPI": 2, "DEPEND": "dev-libs/B[foo]" }, 
			"dev-libs/A-3.3": { "EAPI": 3, "DEPEND": "dev-libs/B[foo]" }, 
			#~ "dev-libs/A-3.4": { "EAPI": 4, "DEPEND": "dev-libs/B[foo]" }, 

			#EAPI-2: strong blocks
			"dev-libs/A-4.0": { "EAPI": 0, "DEPEND": "!!dev-libs/B" }, 
			"dev-libs/A-4.1": { "EAPI": 1, "DEPEND": "!!dev-libs/B" }, 
			"dev-libs/A-4.2": { "EAPI": 2, "DEPEND": "!!dev-libs/B" }, 
			"dev-libs/A-4.3": { "EAPI": 3, "DEPEND": "!!dev-libs/B" }, 
			#~ "dev-libs/A-4.4": { "EAPI": 4, "DEPEND": "!!dev-libs/B" }, 

			#EAPI-4: slot operator deps
			#~ "dev-libs/A-5.0": { "EAPI": 0, "DEPEND": "dev-libs/B:*" }, 
			#~ "dev-libs/A-5.1": { "EAPI": 1, "DEPEND": "dev-libs/B:*" }, 
			#~ "dev-libs/A-5.2": { "EAPI": 2, "DEPEND": "dev-libs/B:*" }, 
			#~ "dev-libs/A-5.3": { "EAPI": 3, "DEPEND": "dev-libs/B:*" }, 
			#~ "dev-libs/A-5.4": { "EAPI": 4, "DEPEND": "dev-libs/B:*" }, 

			#EAPI-4: slot operator deps
			#~ "dev-libs/A-6.0": { "EAPI": 0, "DEPEND": "dev-libs/B[bar(+)]" }, 
			#~ "dev-libs/A-6.1": { "EAPI": 1, "DEPEND": "dev-libs/B[bar(+)]" }, 
			#~ "dev-libs/A-6.2": { "EAPI": 2, "DEPEND": "dev-libs/B[bar(+)]" }, 
			#~ "dev-libs/A-6.3": { "EAPI": 3, "DEPEND": "dev-libs/B[bar(+)]" }, 
			#~ "dev-libs/A-6.4": { "EAPI": 4, "DEPEND": "dev-libs/B[bar(+)]" }, 

			"dev-libs/B-1": {"EAPI": 1, "IUSE": "+foo"}, 
			}

		requests = (
				(["=dev-libs/A-1.0"], {}, None, False, None),
				(["=dev-libs/A-1.1"], {}, None, True, ["dev-libs/A-1.1"]),
				(["=dev-libs/A-1.2"], {}, None, True, ["dev-libs/A-1.2"]),
				(["=dev-libs/A-1.3"], {}, None, True, ["dev-libs/A-1.3"]),
				#~ (["=dev-libs/A-1.4"], {}, None, True, ["dev-libs/A-1.4"]),

				(["=dev-libs/A-2.0"], {}, None, False, None),
				(["=dev-libs/A-2.1"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-2.1"]),
				(["=dev-libs/A-2.2"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-2.2"]),
				(["=dev-libs/A-2.3"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-2.3"]),
				#~ (["=dev-libs/A-2.4"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-2.4"]),

				(["=dev-libs/A-3.0"], {}, None, False, None),
				(["=dev-libs/A-3.1"], {}, None, False, None),
				(["=dev-libs/A-3.2"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-3.2"]),
				(["=dev-libs/A-3.3"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-3.3"]),
				#~ (["=dev-libs/A-3.4"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-3.4"]),

				(["=dev-libs/A-4.0"], {}, None, False, None),
				(["=dev-libs/A-4.1"], {}, None, False, None),
				(["=dev-libs/A-4.2"], {}, None, True, ["dev-libs/A-4.2"]),
				(["=dev-libs/A-4.3"], {}, None, True, ["dev-libs/A-4.3"]),
				#~ (["=dev-libs/A-4.4"], {}, None, True, ["dev-libs/A-4.4"]),

				#~ (["=dev-libs/A-5.0"], {}, None, False, None),
				#~ (["=dev-libs/A-5.1"], {}, None, False, None),
				#~ (["=dev-libs/A-5.2"], {}, None, False, None),
				#~ (["=dev-libs/A-5.3"], {}, None, False, None),
				#~ (["=dev-libs/A-5.4"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-5.4"]),

				#~ (["=dev-libs/A-6.0"], {}, None, False, None),
				#~ (["=dev-libs/A-6.1"], {}, None, False, None),
				#~ (["=dev-libs/A-6.2"], {}, None, False, None),
				#~ (["=dev-libs/A-6.3"], {}, None, False, None),
				#~ (["=dev-libs/A-6.4"], {}, None, True, ["dev-libs/B-1", "dev-libs/A-6.4"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for atoms, options, action, \
				expected_result, expected_mergelist in requests:
				result = playground.run(atoms, options, action)
				self.assertEqual((result.success, result.mergelist),
					(expected_result, expected_mergelist))
		finally:
			playground.cleanup()
