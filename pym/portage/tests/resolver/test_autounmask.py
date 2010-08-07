# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class AutounmaskTestCase(TestCase):

	def testAutounmask(self):
		ebuilds = {
			#ebuilds to test use changes
			"dev-libs/A-1": { "SLOT": 1, "DEPEND": "dev-libs/B[foo]", "EAPI": 2}, 
			"dev-libs/A-2": { "SLOT": 2, "DEPEND": "dev-libs/B[bar]", "EAPI": 2}, 
			"dev-libs/B-1": { "DEPEND": "foo? ( dev-libs/C ) bar? ( dev-libs/D )", "IUSE": "foo bar"}, 
			"dev-libs/C-1": {},
			"dev-libs/D-1": {},

			#ebuilds to test keyword changes
			"app-misc/Z-1": { "KEYWORDS": "~x86", "DEPEND": "app-misc/Y" },
			"app-misc/Y-1": { "KEYWORDS": "~x86" },
			"app-misc/W-1": {},
			"app-misc/W-2": { "KEYWORDS": "~x86" },
			"app-misc/V-1": { "KEYWORDS": "~x86", "DEPEND": ">=app-misc/W-2"},

			#ebuilds for mixed test for || dep handling
			"sci-libs/K-1": { "DEPEND": " || ( sci-libs/L[bar] || ( sci-libs/M sci-libs/P ) )", "EAPI": 2},
			"sci-libs/K-2": { "DEPEND": " || ( sci-libs/L[bar] || ( sci-libs/P sci-libs/M ) )", "EAPI": 2},
			"sci-libs/K-3": { "DEPEND": " || ( sci-libs/M || ( sci-libs/L[bar] sci-libs/P ) )", "EAPI": 2},
			"sci-libs/K-4": { "DEPEND": " || ( sci-libs/M || ( sci-libs/P sci-libs/L[bar] ) )", "EAPI": 2},
			"sci-libs/K-5": { "DEPEND": " || ( sci-libs/P || ( sci-libs/L[bar] sci-libs/M ) )", "EAPI": 2},
			"sci-libs/K-6": { "DEPEND": " || ( sci-libs/P || ( sci-libs/M sci-libs/L[bar] ) )", "EAPI": 2},
			"sci-libs/K-7": { "DEPEND": " || ( sci-libs/M sci-libs/L[bar] )", "EAPI": 2},
			"sci-libs/K-8": { "DEPEND": " || ( sci-libs/L[bar] sci-libs/M )", "EAPI": 2},

			"sci-libs/L-1": { "IUSE": "bar" },
			"sci-libs/M-1": { "KEYWORDS": "~x86" },
			"sci-libs/P-1": { },
			}

		requests = (
				#Test USE changes.
				#The simple case.

				(["dev-libs/A:1"], {"--autounmask": "n"}, None, False, None, None),
				(["dev-libs/A:1"], {"--autounmask": True}, None, False, \
					["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"], { "dev-libs/B-1": {"foo": True} }),

				#Make sure we restart if needed.
				(["dev-libs/B", "dev-libs/A:1"], {"--autounmask": True}, None, False, \
					["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"], { "dev-libs/B-1": {"foo": True} }),
				(["dev-libs/A:1", "dev-libs/B"], {"--autounmask": True}, None, False, \
					["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"], { "dev-libs/B-1": {"foo": True} }),
				(["dev-libs/A:1", "dev-libs/A:2"], {"--autounmask": True}, None, False, \
					["dev-libs/D-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1", "dev-libs/A-2"], { "dev-libs/B-1": {"foo": True, "bar": True} }),
				(["dev-libs/B", "dev-libs/A:1", "dev-libs/A:2"], {"--autounmask": True}, None, False, \
					["dev-libs/D-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1", "dev-libs/A-2"], { "dev-libs/B-1": {"foo": True, "bar": True} }),
				(["dev-libs/A:1", "dev-libs/B", "dev-libs/A:2"], {"--autounmask": True}, None, False, \
					["dev-libs/D-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1", "dev-libs/A-2"], { "dev-libs/B-1": {"foo": True, "bar": True} }),
				(["dev-libs/A:1", "dev-libs/A:2", "dev-libs/B"], {"--autounmask": True}, None, False, \
					["dev-libs/D-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1", "dev-libs/A-2"], { "dev-libs/B-1": {"foo": True, "bar": True} }),

				#Test keywording.
				#The simple case.

				(["app-misc/Z"], {"--autounmask": "n"}, None, False, None, None),
				(["app-misc/Z"], {"--autounmask": True}, None, False, \
					["app-misc/Y-1", "app-misc/Z-1"], None),

				#Make sure that the backtracking for slot conflicts handles our mess.

				(["=app-misc/V-1", "app-misc/W"], {"--autounmask": True}, None, False, \
					["app-misc/W-2", "app-misc/V-1"], None),
				(["app-misc/W", "=app-misc/V-1"], {"--autounmask": True}, None, False, \
					["app-misc/W-2", "app-misc/V-1"], None),

				#Mixed testing
				#Make sure we don't change use for something in a || dep if there is another choice
				#that needs no change.

				(["=sci-libs/K-1"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-1"], None),
				(["=sci-libs/K-2"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-2"], None),
				(["=sci-libs/K-3"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-3"], None),
				(["=sci-libs/K-4"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-4"], None),
				(["=sci-libs/K-5"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-5"], None),
				(["=sci-libs/K-6"], {"--autounmask": True}, None, True, \
					["sci-libs/P-1", "sci-libs/K-6"], None),

				#Make sure we prefer use changes over keyword changes.
				(["=sci-libs/K-7"], {"--autounmask": True}, None, False, \
					["sci-libs/L-1", "sci-libs/K-7"], { "sci-libs/L-1": { "bar": True } }),
				(["=sci-libs/K-8"], {"--autounmask": True}, None, False, \
					["sci-libs/L-1", "sci-libs/K-8"], { "sci-libs/L-1": { "bar": True } }),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for atoms, options, action, \
				expected_result, expected_mergelist, expected_use_changes in requests:
				result = playground.run(atoms, options, action)
				self.assertEqual((result.success, result.mergelist, result.use_changes),
					(expected_result, expected_mergelist, expected_use_changes))
		finally:
			playground.cleanup()
