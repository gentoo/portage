# test_match_from_list.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import match_from_list

class Test_match_from_list(TestCase):

	def testMatch_from_list(self):
		tests = [ ("=sys-apps/portage-45*", ["sys-apps/portage-045"], ["sys-apps/portage-045"] ),
					("=sys-fs/udev-1*", ["sys-fs/udev-123"], ["sys-fs/udev-123"]),
					("=sys-fs/udev-4*", ["sys-fs/udev-456"], ["sys-fs/udev-456"] ),
					("*/*", ["sys-fs/udev-456"], ["sys-fs/udev-456"] ),
					("sys-fs/*", ["sys-fs/udev-456"], ["sys-fs/udev-456"] ),
					("*/udev", ["sys-fs/udev-456"], ["sys-fs/udev-456"] ),
					("=sys-apps/portage-2*", ["sys-apps/portage-2.1"], ["sys-apps/portage-2.1"] ),
					("=sys-apps/portage-2.1*", ["sys-apps/portage-2.1.2"], ["sys-apps/portage-2.1.2"] ),
					("dev-libs/*", ["sys-apps/portage-2.1.2"], [] ),
					("*/tar", ["sys-apps/portage-2.1.2"], [] ),
					("*/*", ["dev-libs/A-1", "dev-libs/B-1"], ["dev-libs/A-1", "dev-libs/B-1"] ),
					("dev-libs/*", ["dev-libs/A-1", "sci-libs/B-1"], ["dev-libs/A-1"] )
				]

		for atom, cpv_list, result in tests:
			self.assertEqual( match_from_list( atom, cpv_list ), result )
