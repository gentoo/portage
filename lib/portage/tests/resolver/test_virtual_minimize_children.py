# Copyright 2017-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class VirtualMinimizeChildrenTestCase(TestCase):

	def testVirtualMinimizeChildren(self):
		ebuilds = {
			'app-misc/bar-1': {
				'EAPI': '6',
				'RDEPEND': 'virtual/foo'
			},
			'virtual/foo-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( app-misc/A app-misc/B ) || ( app-misc/B app-misc/C )'
			},
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/B-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			# Test bug 632026, where we want to minimize the number of
			# packages chosen to satisfy overlapping || deps like
			# "|| ( foo bar ) || ( bar baz )".
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				mergelist=[
					'app-misc/B-1',
					'virtual/foo-1',
					'app-misc/bar-1',
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		# If app-misc/A and app-misc/C are installed then
		# that choice should be preferred over app-misc/B.
		installed = {
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				mergelist=[
					'virtual/foo-1',
					'app-misc/bar-1',
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testOverlapSlotConflict(self):
		ebuilds = {
			'app-misc/bar-1': {
				'EAPI': '6',
				'RDEPEND': 'virtual/foo'
			},
			'virtual/foo-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( app-misc/A >=app-misc/B-2 ) || ( <app-misc/B-2 app-misc/C )'
			},
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/B-2': {
				'EAPI': '6',
			},
			'app-misc/B-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			# Here the ( >=app-misc/B-2 <app-misc/B-2 ) choice is not satisfiable.
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				ambiguous_merge_order=True,
				mergelist=[
					(
						'app-misc/C-1',
						'app-misc/A-1',
					),
					'virtual/foo-1',
					'app-misc/bar-1',
				]
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testVirtualPackageManager(self):
		ebuilds = {
			'app-admin/perl-cleaner-2.25': {
				'RDEPEND': '''
					|| (
						( sys-apps/portage app-portage/portage-utils )
						sys-apps/pkgcore
						sys-apps/paludis
					)'''
			},
			'app-portage/portage-utils-0.64': {},
			'sys-apps/paludis-2.6.0': {},
			'sys-apps/portage-2.3.19-r1': {},
			'virtual/package-manager-0': {
				'RDEPEND': '''
					|| (
						sys-apps/portage
						sys-apps/paludis
						sys-apps/pkgcore
					)'''
			},
		}

		test_cases = (
			# Test bug 645002, where paludis was selected to satisfy a
			# perl-cleaner dependency because that choice contained fewer
			# packages than the ( portage portage-utils ) choice which
			# should have been preferred according to the order of
			# choices specified in the ebuild.
			ResolverPlaygroundTestCase(
				[
					'app-admin/perl-cleaner',
					'virtual/package-manager',
				],
				all_permutations=True,
				success=True,
				ambiguous_merge_order=True,
				mergelist=(
					(
						'sys-apps/portage-2.3.19-r1',
						'app-portage/portage-utils-0.64',
						'app-admin/perl-cleaner-2.25',
						'virtual/package-manager-0',
					),
				)
			),
			# Test paludis preference. In this case, if paludis is not
			# included in the argument atoms then the result varies
			# depending on whether the app-admin/perl-cleaner or
			# virtual/package-manager dependencies are evaluated first!
			# Therefore, include paludis in the argument atoms.
			ResolverPlaygroundTestCase(
				[
					'app-admin/perl-cleaner',
					'virtual/package-manager',
					'sys-apps/paludis',
				],
				all_permutations=True,
				success=True,
				ambiguous_merge_order=True,
				mergelist=(
					'sys-apps/paludis-2.6.0',
					(
						'app-admin/perl-cleaner-2.25',
						'virtual/package-manager-0',
					),
				)
			),
		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testVirtualDevManager(self):
		ebuilds = {
			'sys-fs/eudev-3.1.5': {},
			'sys-fs/static-dev-0.1': {},
			'sys-fs/udev-233': {},
			'virtual/dev-manager-0': {
				'RDEPEND': '''
					|| (
						virtual/udev
						sys-fs/static-dev
					)'''
			},
			'virtual/udev-0': {
				'RDEPEND': '''
					|| (
						>=sys-fs/eudev-2.1.1
						>=sys-fs/udev-217
					)'''
			},
		}

		test_cases = (
			# Test bug 645190, where static-dev was pulled in instead
			# of eudev.
			ResolverPlaygroundTestCase(
				[
					'virtual/dev-manager',
				],
				success=True,
				mergelist=(
					'sys-fs/eudev-3.1.5',
					'virtual/udev-0',
					'virtual/dev-manager-0',
				),
			),
			# Test static-dev preference.
			ResolverPlaygroundTestCase(
				[
					'sys-fs/static-dev',
					'virtual/dev-manager',
				],
				all_permutations=True,
				success=True,
				mergelist=(
					'sys-fs/static-dev-0.1',
					'virtual/dev-manager-0',
				),
			),
		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


	def testVirtualWine(self):
		ebuilds = {
			'virtual/wine-0-r6': {
				'RDEPEND': '|| ( app-emulation/wine-staging app-emulation/wine-any ) '
					'|| ( app-emulation/wine-vanilla app-emulation/wine-staging app-emulation/wine-any )'
			},
			'app-emulation/wine-staging-4': {},
			'app-emulation/wine-any-4': {},
			'app-emulation/wine-vanilla-4': {},
		}

		test_cases = (
			# Test bug 701996, where separate disjunctions where not
			# converted to DNF, causing both wine-vanilla and
			# wine-staging to be pulled in.
			ResolverPlaygroundTestCase(
				[
					'virtual/wine',
				],
				success=True,
				mergelist=(
					'app-emulation/wine-staging-4',
					'virtual/wine-0-r6',
				),
			),
		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
