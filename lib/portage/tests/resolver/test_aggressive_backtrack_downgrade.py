# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class AgressiveBacktrackDowngradeTestCase(TestCase):

	def testAgressiveBacktrackDowngrade(self):

		ebuilds = {
			'www-client/firefox-69.0' : {
				'EAPI': '7',
				'RDEPEND': '=media-libs/libvpx-1.7*:0=[postproc] media-video/ffmpeg'
			},

			'www-client/firefox-60.9.0' : {
				'EAPI': '7',
				'RDEPEND': ''
			},

			'media-libs/libvpx-1.8.0' : {
				'EAPI': '7',
				'SLOT' : '0/6',
				'IUSE': 'postproc',
			},

			'media-libs/libvpx-1.7.0' : {
				'EAPI': '7',
				'SLOT' : '0/5',
				'IUSE': '+postproc',
			},

			'media-libs/libvpx-1.6.0' : {
				'EAPI': '7',
				'SLOT' : '0/4',
				'IUSE': 'postproc',
			},

			'media-video/ffmpeg-4.2' : {
				'EAPI': '7',
				'RDEPEND': 'media-libs/libvpx:=',
			},
		}

		installed = {
			'www-client/firefox-69.0' : {
				'EAPI': '7',
				'RDEPEND': '=media-libs/libvpx-1.7*:0/5=[postproc] media-video/ffmpeg'
			},

			'media-libs/libvpx-1.7.0' : {
				'EAPI': '7',
				'SLOT' : '0/5',
				'IUSE': '+postproc',
				'USE': 'postproc',
			},

			'media-video/ffmpeg-4.2' : {
				'EAPI': '7',
				'RDEPEND': 'media-libs/libvpx:0/5=',
			},
		}

		world = ['media-video/ffmpeg', 'www-client/firefox']

		test_cases = (
			# Test bug 693836, where an attempt to upgrade libvpx lead
			# to aggressive backtracking which ultimately triggered an
			# undesirable firefox downgrade like this:
			# [ebuild     U  ] media-libs/libvpx-1.8.0 [1.7.0]
			# [ebuild     UD ] www-client/firefox-60.9.0 [69.0]
			# [ebuild  rR    ] media-video/ffmpeg-4.2
			ResolverPlaygroundTestCase(
				['@world'],
				options = {'--update': True, '--deep': True},
				success = True,
				mergelist = [],
			),
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
