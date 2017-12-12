# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class DisjunctiveDependOrderTestCase(TestCase):

	def testDisjunctiveDependOrderTestCase(self):
		ebuilds = {
			'virtual/jre-1.8': {
				'EAPI': '6',
				'SLOT' : '1.8',
				'RDEPEND' : '|| ( dev-java/oracle-jre-bin:1.8 virtual/jdk:1.8 )',
			},
			'virtual/jdk-1.8': {
				'EAPI': '6',
				'SLOT' : '1.8',
				'RDEPEND' : '|| ( dev-java/icedtea:8 dev-java/oracle-jdk-bin:1.8 )',
			},
			'dev-java/icedtea-3.6': {
				'SLOT' : '8',
			},
			'dev-java/oracle-jdk-bin-1.8': {
				'SLOT' : '1.8',
			},
			'dev-java/oracle-jre-bin-1.8': {
				'SLOT' : '1.8',
			},
			'dev-db/hsqldb-1.8'       : {
				'DEPEND' : 'virtual/jdk',
				'RDEPEND' : 'virtual/jre',
			},
		}

		binpkgs = {
			'dev-db/hsqldb-1.8'       : {
				'DEPEND' : 'virtual/jdk',
				'RDEPEND' : 'virtual/jre',
			},
		}

		test_cases = (
			# Test bug 639346, where a redundant jre implementation
			# was pulled in because DEPEND was evaluated after
			# RDEPEND.
			ResolverPlaygroundTestCase(
				['dev-db/hsqldb'],
				success=True,
				mergelist=[
					'dev-java/icedtea-3.6',
					'virtual/jdk-1.8',
					'virtual/jre-1.8',
					'dev-db/hsqldb-1.8',
				],
			),

			# The jdk is not needed with --usepkg, so the jre should
			# be preferred in this case.
			ResolverPlaygroundTestCase(
				['dev-db/hsqldb'],
				options = {
					'--usepkg': True
				},
				success=True,
				mergelist=[
					'dev-java/oracle-jre-bin-1.8',
					'virtual/jre-1.8',
					'[binary]dev-db/hsqldb-1.8',
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			binpkgs=binpkgs, ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
