# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class OrUpgradeInstalledTestCase(TestCase):

	def testOrUpgradeInstalled(self):
		ebuilds = {
			'net-misc/foo-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( sys-libs/glibc[rpc(-)]  net-libs/libtirpc )'
			},
			'net-libs/libtirpc-1': {
				'EAPI': '6',
			},
			'sys-libs/glibc-2.26': {
				'EAPI': '6',
				'IUSE': ''
			},
			'sys-libs/glibc-2.24': {
				'EAPI': '6',
				'IUSE': '+rpc'
			},
		}

		installed = {
			'sys-libs/glibc-2.24': {
				'EAPI': '6',
				'IUSE': '+rpc',
				'USE': 'rpc',
			},
		}

		world = ['sys-libs/glibc']

		test_cases = (
			# Test bug 643974, where we need to install libtirpc
			# in order to upgrade glibc.
			ResolverPlaygroundTestCase(
				['net-misc/foo', '@world'],
				options={'--update': True, '--deep': True},
				success=True,
				ambiguous_merge_order=True,
				mergelist=(
					(
						'net-libs/libtirpc-1',
						'sys-libs/glibc-2.26',
						'net-misc/foo-1',
					),
				)
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		# In some cases it's necessary to avoid upgrade due to
		# the package being masked.
		user_config = {
			"package.mask" : (
				">=sys-libs/glibc-2.26",
			),
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['net-misc/foo', '@world'],
				options={'--update': True, '--deep': True},
				success=True,
				mergelist=[
					'net-misc/foo-1',
				]
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world,
			user_config=user_config)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testVirtualRust(self):
		ebuilds = {
			'dev-lang/rust-1.19.0': {},
			'dev-lang/rust-1.23.0': {},
			'dev-lang/rust-bin-1.19.0': {},
			'virtual/rust-1.19.0': {
				'RDEPEND': '|| ( =dev-lang/rust-1.19.0* =dev-lang/rust-bin-1.19.0* )'
			},
		}

		installed = {
			'dev-lang/rust-1.19.0': {},
			'virtual/rust-1.19.0': {
				'RDEPEND': '|| ( =dev-lang/rust-1.19.0* =dev-lang/rust-bin-1.19.0* )'
			},
		}

		world = ['virtual/rust']

		test_cases = (
			# Test bug 645416, where rust-bin-1.19.0 was pulled in
			# inappropriately due to the rust-1.23.0 update being
			# available.
			ResolverPlaygroundTestCase(
				['virtual/rust'],
				options={'--update': True, '--deep': True},
				success=True,
				mergelist=[]
			),
			# Test upgrade to rust-1.23.0, which is only possible
			# if rust-bin-1.19.0 is installed in order to satisfy
			# virtual/rust-1.19.0.
			ResolverPlaygroundTestCase(
				['=dev-lang/rust-1.23.0', 'virtual/rust'],
				options={'--update': True, '--deep': True},
				all_permutations=True,
				success=True,
				ambiguous_merge_order=True,
				mergelist=(
					(
						'dev-lang/rust-1.23.0',
						'dev-lang/rust-bin-1.19.0',
					),
				),
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()


	def test_llvm_slot_operator(self):
		ebuilds = {
			'media-libs/mesa-19.2.8': {
				'EAPI': '7',
				'RDEPEND': '''|| (
					sys-devel/llvm:10
					sys-devel/llvm:9
					sys-devel/llvm:8
					sys-devel/llvm:7
				)
				sys-devel/llvm:='''
			},
			'sys-devel/llvm-10': {
				'EAPI': '7',
				'KEYWORDS': '',
				'SLOT': '10',
			},
			'sys-devel/llvm-9': {
				'EAPI': '7',
				'SLOT': '9',
			},
			'sys-devel/llvm-8': {
				'EAPI': '7',
				'SLOT': '8',
			},
		}

		installed = {
			'media-libs/mesa-19.2.8': {
				'EAPI': '7',
				'RDEPEND': '''|| (
					sys-devel/llvm:10
					sys-devel/llvm:9
					sys-devel/llvm:8
					sys-devel/llvm:7
				)
				sys-devel/llvm:8/8='''
			},
			'sys-devel/llvm-8': {
				'EAPI': '7',
				'SLOT': '8',
			},
		}

		world = ['media-libs/mesa']

		test_cases = (
			# Demonstrate bug 706278, where there is a missed slot operator
			# rebuild that prevents upgrade from llvm-8 to llvm-9.
			ResolverPlaygroundTestCase(
				['@world'],
				options={'--update': True, '--deep': True},
				success=True,
				mergelist=['sys-devel/llvm-9', 'media-libs/mesa-19.2.8'],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
