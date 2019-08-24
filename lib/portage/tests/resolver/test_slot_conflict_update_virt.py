# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictUpdateVirtTestCase(TestCase):

	def testSlotConflictUpdateVirt(self):

		ebuilds = {
			"dev-db/mysql-connector-c-6.1.11-r2" : {
				"EAPI": "7",
				"SLOT" : "0/18"
			},

			"dev-db/mysql-connector-c-8.0.17-r3" : {
				"EAPI": "7",
				"SLOT" : "0/21"
			},

			"virtual/libmysqlclient-18-r1" : {
				"EAPI": "7",
				"SLOT" : "0/18",
				"RDEPEND": "dev-db/mysql-connector-c:0/18",
			},

			"virtual/libmysqlclient-21" : {
				"EAPI": "7",
				"SLOT" : "0/21",
				"RDEPEND": "dev-db/mysql-connector-c:0/21",
			},

			"dev-perl/DBD-mysql-4.44.0" : {
				"EAPI": "7",
				"RDEPEND": "virtual/libmysqlclient:=",
			},
		}

		installed = {
			"dev-db/mysql-connector-c-6.1.11-r2" : {
				"EAPI": "7",
				"SLOT" : "0/18"
			},

			"virtual/libmysqlclient-18-r1" : {
				"EAPI": "7",
				"SLOT" : "0/18",
				"RDEPEND": "dev-db/mysql-connector-c:0/18",
			},

			"dev-perl/DBD-mysql-4.44.0" : {
				"EAPI": "7",
				"RDEPEND": "virtual/libmysqlclient:0/18=",
			},
		}

		world = ["dev-db/mysql-connector-c", "dev-perl/DBD-mysql"]

		test_cases = (
			# In order to avoid missed updates for bug 692746, consider
			# masking a package matched by all parent atoms.
			ResolverPlaygroundTestCase(
				['@world'],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['dev-db/mysql-connector-c-8.0.17-r3', 'virtual/libmysqlclient-21', 'dev-perl/DBD-mysql-4.44.0']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
