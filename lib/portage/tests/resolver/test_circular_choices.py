# Copyright 2011-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CircularJsoncppCmakeBootstrapTestCase(TestCase):

	def testCircularJsoncppCmakeBootstrapOrDeps(self):

		ebuilds = {
			'dev-libs/jsoncpp-1.9.2': {
				'EAPI': '7',
				'BDEPEND': '|| ( dev-util/cmake-bootstrap dev-util/cmake )'
			},
			'dev-util/cmake-bootstrap-3.16.2': {
				'EAPI': '7',
			},
			'dev-util/cmake-3.16.2': {
				'EAPI': '7',
				'BDEPEND': '>=dev-libs/jsoncpp-0.6.0_rc2:0=',
			},
		}

		test_cases = (
			# Demonstrate bug 703440. It ignores cmake-bootstrap in order to eliminate redundant packages.
			#
			#  * Error: circular dependencies:
			#
			# (dev-libs/jsoncpp-1.9.2:0/0::test_repo, ebuild scheduled for merge) depends on
			#  (dev-util/cmake-3.16.2:0/0::test_repo, ebuild scheduled for merge) (buildtime)
			#    (dev-libs/jsoncpp-1.9.2:0/0::test_repo, ebuild scheduled for merge) (buildtime_slot_op)
			ResolverPlaygroundTestCase(
				['dev-util/cmake'],
				options = {"--backtrack": 0},
				circular_dependency_solutions = {},
				success = False,
			),
			# Demonstrate that backtracking adjusts || preferences in order to solve bug 703440.
			ResolverPlaygroundTestCase(
				['dev-util/cmake'],
				mergelist = ['dev-util/cmake-bootstrap-3.16.2', 'dev-libs/jsoncpp-1.9.2', 'dev-util/cmake-3.16.2'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

		test_cases = (
			# Demonstrate elimination of cmake-bootstrap via --depclean.
			ResolverPlaygroundTestCase(
				[],
				options = {'--depclean': True},
				success = True,
				cleanlist = ['dev-util/cmake-bootstrap-3.16.2'],
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=ebuilds, world=['dev-util/cmake'])
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testVirtualCmakeBootstrapUseConditional(self):

		ebuilds = {
			'dev-libs/jsoncpp-1.9.2': {
				'EAPI': '7',
				'BDEPEND': 'virtual/cmake'
			},
			'dev-util/cmake-bootstrap-3.16.2': {
				'EAPI': '7',
			},
			'dev-util/cmake-3.16.2': {
				'EAPI': '7',
				'BDEPEND': '>=dev-libs/jsoncpp-0.6.0_rc2:0=',
			},
			'virtual/cmake-0': {
				'EAPI': '7',
				'IUSE': '+bootstrap',
				'RDEPEND': 'bootstrap? ( dev-util/cmake-bootstrap ) !bootstrap? ( dev-util/cmake )'
			},
		}

		test_cases = (
			# Solve bug 703440 with a dependency conditional on the bootstrap USE flag.
			ResolverPlaygroundTestCase(
				['dev-util/cmake'],
				mergelist = ['dev-util/cmake-bootstrap-3.16.2', 'virtual/cmake-0', 'dev-libs/jsoncpp-1.9.2', 'dev-util/cmake-3.16.2'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class CircularChoicesTestCase(TestCase):

	def testDirectCircularDependency(self):

		ebuilds = {
			"dev-lang/gwydion-dylan-2.4.0": {"DEPEND": "|| ( dev-lang/gwydion-dylan dev-lang/gwydion-dylan-bin )" },
			"dev-lang/gwydion-dylan-bin-2.4.0": {},
		}

		test_cases = (
			# Automatically pull in gwydion-dylan-bin to solve a circular dep
			ResolverPlaygroundTestCase(
				["dev-lang/gwydion-dylan"],
				mergelist = ['dev-lang/gwydion-dylan-bin-2.4.0', 'dev-lang/gwydion-dylan-2.4.0'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class VirtualCircularChoicesTestCase(TestCase):
	def testDirectVirtualCircularDependency(self):

		ebuilds = {
			"dev-java/icedtea-6.1.10.3": { "SLOT" : "6", "DEPEND": "virtual/jdk" },
			"dev-java/icedtea6-bin-1.10.3": {},
			"virtual/jdk-1.6.0": { "SLOT" : "1.6", "RDEPEND": "|| ( dev-java/icedtea6-bin =dev-java/icedtea-6* )" },
		}

		test_cases = (
			# Automatically pull in icedtea6-bin to solve a circular dep
			ResolverPlaygroundTestCase(
				["dev-java/icedtea"],
				mergelist = ["dev-java/icedtea6-bin-1.10.3", "virtual/jdk-1.6.0", "dev-java/icedtea-6.1.10.3"],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


class CircularPypyExeTestCase(TestCase):
	def testCircularPypyExe(self):

		ebuilds = {
			'dev-python/pypy-7.3.0': {
				'EAPI': '7',
				'SLOT' : '0/73',
				'DEPEND': '|| ( dev-python/pypy-exe dev-python/pypy-exe-bin )'
			},
			'dev-python/pypy-exe-7.3.0': {
				'EAPI': '7',
				'IUSE': 'low-memory',
				'SLOT' : '7.3.0',
				'BDEPEND': '!low-memory? ( dev-python/pypy )'
			},
			'dev-python/pypy-exe-bin-7.3.0': {
				'EAPI': '7',
				'SLOT' : '7.3.0',
			},
		}

		test_cases = (
			# Demonstrate bug 705986, where a USE change suggestion was given
			# even though an || preference adjustment would solve the problem
			# by pulling in pypy-exe-bin instead of pypy-exe.
			ResolverPlaygroundTestCase(
				['dev-python/pypy'],
				mergelist=['dev-python/pypy-exe-bin-7.3.0', 'dev-python/pypy-7.3.0'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
