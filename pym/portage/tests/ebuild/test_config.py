# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.dep import Atom
from portage.package.ebuild.config import config
from portage.package.ebuild._config.LicenseManager import LicenseManager
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class ConfigTestCase(TestCase):

	def testClone(self):
		"""
		Test the clone via constructor.
		"""

		ebuilds = {
			"dev-libs/A-1": { },
		}

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			settings = config(clone=playground.settings)
			result = playground.run(["=dev-libs/A-1"])
			pkg, existing_node = result.depgraph._select_package(
				playground.eroot, Atom("=dev-libs/A-1"))
			settings.setcpv(pkg)

			# clone after setcpv tests deepcopy of LazyItemsDict
			settings2 = config(clone=settings)
		finally:
			playground.cleanup()

	def testFeaturesMutation(self):
		"""
		Test whether mutation of config.features updates the FEATURES
		variable and persists through config.regenerate() calls. Also
		verify that features_set._prune_overrides() works correctly.
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

			# before: ['noclean', '-noclean', 'noclean']
			settings.features._prune_overrides()
			#  after: ['noclean']
			self.assertEqual(settings._features_overrides.count('noclean'), 1)
			self.assertEqual(settings._features_overrides.count('-noclean'), 0)

			settings.features.remove('noclean')

			# before: ['noclean', '-noclean']
			settings.features._prune_overrides()
			#  after: ['-noclean']
			self.assertEqual(settings._features_overrides.count('noclean'), 0)
			self.assertEqual(settings._features_overrides.count('-noclean'), 1)
		finally:
			playground.cleanup()

	def testLicenseManager(self):

		user_config = {
			"package.license":
				(
					"dev-libs/* TEST",
					"dev-libs/A -TEST2", 
					"=dev-libs/A-2 TEST3 @TEST",
					"*/* @EULA TEST2",
					"=dev-libs/C-1 *",
					"=dev-libs/C-2 -*",
				),
		}

		playground = ResolverPlayground(user_config=user_config)
		try:
			portage.util.noiselimit = -2

			license_group_locations = (os.path.join(playground.portdir, "profiles"),)
			pkg_license = os.path.join(playground.eroot, "etc", "portage")

			lic_man = LicenseManager(license_group_locations, pkg_license)

			self.assertEqual(lic_man._accept_license_str, None)
			self.assertEqual(lic_man._accept_license, None)
			self.assertEqual(lic_man._license_groups, {"EULA": frozenset(["TEST"])})
			self.assertEqual(lic_man._undef_lic_groups, set(["TEST"]))

			self.assertEqual(lic_man.extract_global_changes(), "TEST TEST2")
			self.assertEqual(lic_man.extract_global_changes(), "")

			lic_man.set_accept_license_str("TEST TEST2")
			self.assertEqual(lic_man._getPkgAcceptLicense("dev-libs/B-1", "0", None), ["TEST", "TEST2", "TEST"])
			self.assertEqual(lic_man._getPkgAcceptLicense("dev-libs/A-1", "0", None), ["TEST", "TEST2", "TEST", "-TEST2"])
			self.assertEqual(lic_man._getPkgAcceptLicense("dev-libs/A-2", "0", None), ["TEST", "TEST2", "TEST", "-TEST2", "TEST3", "@TEST"])

			self.assertEqual(lic_man.get_prunned_accept_license("dev-libs/B-1", [], "TEST", "0", None), "TEST")
			self.assertEqual(lic_man.get_prunned_accept_license("dev-libs/A-1", [], "-TEST2", "0", None), "")
			self.assertEqual(lic_man.get_prunned_accept_license("dev-libs/A-2", [], "|| ( TEST TEST2 )", "0", None), "TEST")
			self.assertEqual(lic_man.get_prunned_accept_license("dev-libs/C-1", [], "TEST5", "0", None), "TEST5")
			self.assertEqual(lic_man.get_prunned_accept_license("dev-libs/C-2", [], "TEST2", "0", None), "")

			self.assertEqual(lic_man.getMissingLicenses("dev-libs/B-1", [], "TEST", "0", None), [])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/A-1", [], "-TEST2", "0", None), ["-TEST2"])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/A-2", [], "|| ( TEST TEST2 )", "0", None), [])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/A-3", [], "|| ( TEST2 || ( TEST3 TEST4 ) )", "0", None), ["TEST2", "TEST3", "TEST4"])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/C-1", [], "TEST5", "0", None), [])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/C-2", [], "TEST2", "0", None), ["TEST2"])
			self.assertEqual(lic_man.getMissingLicenses("dev-libs/D-1", [], "", "0", None), [])
		finally:
			portage.util.noiselimit = 0
			playground.cleanup()

	def testPackageMaskOrder(self):

		ebuilds = {
			"dev-libs/A-1": { },
			"dev-libs/B-1": { },
			"dev-libs/C-1": { },
			"dev-libs/D-1": { },
			"dev-libs/E-1": { },
		}

		repo_configs = {
			"test_repo": {
				"package.mask":
					(
						"dev-libs/A",
						"dev-libs/C",
					),
			}
		}

		profile = {
			"package.mask":
				(
					"-dev-libs/A",
					"dev-libs/B",
					"-dev-libs/B",
					"dev-libs/D",
				),
		}

		user_config = {
			"package.mask":
				(
					"-dev-libs/C",
					"-dev-libs/D",
					"dev-libs/E",
				),
		}

		test_cases = (
				ResolverPlaygroundTestCase(
					["dev-libs/A"],
					options = { "--autounmask": 'n' },
					success = False),
				ResolverPlaygroundTestCase(
					["dev-libs/B"],
					success = True,
					mergelist = ["dev-libs/B-1"]),
				ResolverPlaygroundTestCase(
					["dev-libs/C"],
					success = True,
					mergelist = ["dev-libs/C-1"]),
				ResolverPlaygroundTestCase(
					["dev-libs/D"],
					success = True,
					mergelist = ["dev-libs/D-1"]),
				ResolverPlaygroundTestCase(
					["dev-libs/E"],
					options = { "--autounmask": 'n' },
					success = False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, repo_configs=repo_configs, \
			profile=profile, user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testManifest(self):

		distfiles = {
			'B-2.tar.bz2': b'binary\0content',
			'C-2.zip': b'binary\0content',
			'C-2.tar.bz2': b'binary\0content',
		}

		ebuilds = {
			"dev-libs/A-1::old_repo": { },
			"dev-libs/A-2::new_repo": { },
			"dev-libs/B-2::new_repo": {"SRC_URI" : "B-2.tar.bz2"},
			"dev-libs/C-2::new_repo": {"SRC_URI" : "C-2.zip C-2.tar.bz2"},
		}

		repo_configs = {
			"new_repo": {
				"layout.conf":
					(
						"profile-formats = pms",
						"thin-manifests = true",
						"manifest-hashes = SHA256 SHA512 WHIRLPOOL",
					),
			}
		}

		test_cases = (
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					mergelist= ["dev-libs/A-1"],
					success = True),

				ResolverPlaygroundTestCase(
					["=dev-libs/A-2"],
					mergelist= ["dev-libs/A-2"],
					success = True),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			repo_configs=repo_configs, distfiles=distfiles)

		new_repo_config = playground.settings.repositories.prepos['new_repo']
		self.assertTrue(len(new_repo_config.masters) > 0, "new_repo has no default master")
		self.assertEqual(new_repo_config.masters[0].user_location, playground.portdir,
			"new_repo default master is not PORTDIR")
		self.assertEqual(new_repo_config.thin_manifest, True,
			"new_repo_config.thin_manifest != True")

		new_manifest_file = os.path.join(playground.repo_dirs["new_repo"], "dev-libs", "A", "Manifest")
		self.assertEqual(os.path.exists(new_manifest_file), False)

		new_manifest_file = os.path.join(playground.repo_dirs["new_repo"], "dev-libs", "B", "Manifest")
		f = open(new_manifest_file)
		self.assertEqual(len(list(f)), 1)
		f.close()

		new_manifest_file = os.path.join(playground.repo_dirs["new_repo"], "dev-libs", "C", "Manifest")
		f = open(new_manifest_file)
		self.assertEqual(len(list(f)), 2)
		f.close()

		old_manifest_file = os.path.join(playground.repo_dirs["old_repo"], "dev-libs", "A", "Manifest")
		f = open(old_manifest_file)
		self.assertEqual(len(list(f)), 1)
		f.close()

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
