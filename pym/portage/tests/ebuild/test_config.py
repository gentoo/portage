# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.package.ebuild.config import config
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class ConfigTestCase(TestCase):

	def testFeaturesMutation(self):
		"""
		Test whether mutation of config.features updates the FEATURES
		variable and persists through config.regenerate() calls.
		"""
		playground = ResolverPlayground()
		try:
			settings = config(clone=playground.settings)

			settings.features.add('noclean')
			self.assertEqual('noclean' in settings['FEATURES'].split(), True)
			settings.regenerate()
			self.assertEqual('noclean' in settings['FEATURES'].split(),True)

			settings.features.discard('noclean')
			self.assertEqual('noclean' in settings['FEATURES'].split(), False)
			settings.regenerate()
			self.assertEqual('noclean' in settings['FEATURES'].split(), False)

			settings.features.add('noclean')
			self.assertEqual('noclean' in settings['FEATURES'].split(), True)
			settings.regenerate()
			self.assertEqual('noclean' in settings['FEATURES'].split(),True)
		finally:
			playground.cleanup()
