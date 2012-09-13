# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys
import time

import portage
from portage import os
from portage import shutil
from portage import _unicode_decode
from portage.const import PORTAGE_BASE_PATH, PORTAGE_BIN_PATH, PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from repoman.utilities import _update_copyright_year

class SimpleRepomanTestCase(TestCase):

	def testCopyrightUpdate(self):
		test_cases = (
			(
				'2011',
				'# Copyright 1999-2008 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999-2011 Gentoo Foundation; Distributed under the GPL v2',
			),
			(
				'2011',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999-2011 Gentoo Foundation; Distributed under the GPL v2',
			),
			(
				'1999',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
			),
		)

		for year, before, after in test_cases:
			self.assertEqual(_update_copyright_year(year, before), after)

	def _must_skip(self):
		xmllint = find_binary("xmllint")
		if not xmllint:
			return "xmllint not found"

		try:
			__import__("xml.etree.ElementTree")
			__import__("xml.parsers.expat").parsers.expat.ExpatError
		except (AttributeError, ImportError):
			return "python is missing xml support"

	def testSimple(self):
		debug = False

		skip_reason = self._must_skip()
		if skip_reason:
			self.portage_skip = skip_reason
			self.assertFalse(True, skip_reason)
			return

		copyright_header = """# Copyright 1999-%s Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $
""" % time.gmtime().tm_year

		repo_configs = {
			"test_repo": {
				"layout.conf":
					(
						"update-changelog = true",
					),
			}
		}

		profiles = (
			("x86", "default/linux/x86/test_profile", "stable"),
		)

		profile = {
			"eapi": ("5_pre2",),
			"package.use.stable.mask": ("dev-libs/A flag",)
		}

		ebuilds = {
			"dev-libs/A-0": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "5_pre2",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/A-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/B-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
			},
			"dev-libs/C-0": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				# must be unstable, since dev-libs/A[flag] is stable masked
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/A[flag] )",
			},
		}
		licenses = ["GPL-2"]
		arch_list = ["x86"]
		metadata_dtd = os.path.join(PORTAGE_BASE_PATH, "cnf/metadata.dtd")
		metadata_xml_files = (
			(
				"dev-libs/A",
				{
					"herd" : "base-system",
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/B",
				{
					"herd" : "no-herd",
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/C",
				{
					"herd" : "no-herd",
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
		)

		use_desc = (
			("flag", "Description of how USE='flag' affects packages"),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			profile=profile, repo_configs=repo_configs, debug=debug)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		portdb = playground.trees[playground.eroot]["porttree"].dbapi
		homedir = os.path.join(eroot, "home")
		distdir = os.path.join(eprefix, "distdir")
		portdir = settings["PORTDIR"]
		profiles_dir = os.path.join(portdir, "profiles")
		license_dir = os.path.join(portdir, "licenses")

		repoman_cmd = (portage._python_interpreter, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "repoman"))

		git_binary = find_binary("git")
		git_cmd = (git_binary,)

		cp_binary = find_binary("cp")
		self.assertEqual(cp_binary is None, False,
			"cp command not found")
		cp_cmd = (cp_binary,)

		test_ebuild = portdb.findname("dev-libs/A-1")
		self.assertFalse(test_ebuild is None)

		committer_name = "Gentoo Dev"
		committer_email = "gentoo-dev@gentoo.org"
		
		git_test = (
			("", repoman_cmd + ("manifest",)),
			("", git_cmd + ("config", "--global", "user.name", committer_name,)),
			("", git_cmd + ("config", "--global", "user.email", committer_email,)),
			("", git_cmd + ("init-db",)),
			("", git_cmd + ("add", ".")),
			("", git_cmd + ("commit", "-a", "-m", "add whole repo")),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "2.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "2.ebuild")),
			("", repoman_cmd + ("commit", "-m", "bump to version 2")),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "3.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "3.ebuild")),
			("dev-libs", repoman_cmd + ("commit", "-m", "bump to version 3")),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "4.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "4.ebuild")),
			("dev-libs/A", repoman_cmd + ("commit", "-m", "bump to version 4")),
		)

		pythonpath =  os.environ.get("PYTHONPATH")
		if pythonpath is not None and not pythonpath.strip():
			pythonpath = None
		if pythonpath is not None and \
			pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
			pass
		else:
			if pythonpath is None:
				pythonpath = ""
			else:
				pythonpath = ":" + pythonpath
			pythonpath = PORTAGE_PYM_PATH + pythonpath

		env = {
			"PORTAGE_OVERRIDE_EPREFIX" : eprefix,
			"DISTDIR" : distdir,
			"GENTOO_COMMITTER_NAME" : committer_name,
			"GENTOO_COMMITTER_EMAIL" : committer_email,
			"HOME" : homedir,
			"PATH" : os.environ["PATH"],
			"PORTAGE_GRPNAME" : os.environ["PORTAGE_GRPNAME"],
			"PORTAGE_USERNAME" : os.environ["PORTAGE_USERNAME"],
			"PORTDIR" : portdir,
			"PYTHONPATH" : pythonpath,
		}

		if os.environ.get("SANDBOX_ON") == "1":
			# avoid problems from nested sandbox instances
			env["FEATURES"] = "-sandbox"

		dirs = [homedir, license_dir, profiles_dir, distdir]
		try:
			for d in dirs:
				ensure_dirs(d)
			with open(os.path.join(portdir, "skel.ChangeLog"), 'w') as f:
				f.write(copyright_header)
			with open(os.path.join(profiles_dir, "profiles.desc"), 'w') as f:
				for x in profiles:
					f.write("%s %s %s\n" % x)
			for x in licenses:
				open(os.path.join(license_dir, x), 'wb').close()
			with open(os.path.join(profiles_dir, "arch.list"), 'w') as f:
				for x in arch_list:
					f.write("%s\n" % x)
			with open(os.path.join(profiles_dir, "use.desc"), 'w') as f:
				for k, v in use_desc:
					f.write("%s - %s\n" % (k, v))
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(portdir, cp, "metadata.xml"), 'w') as f:
					f.write(playground.metadata_xml_template % xml_data)
			# Use a symlink to portdir, in order to trigger bugs
			# involving canonical vs. non-canonical paths.
			portdir_symlink = os.path.join(eroot, "portdir_symlink")
			os.symlink(portdir, portdir_symlink)
			# repoman checks metadata.dtd for recent CTIME, so copy the file in
			# order to ensure that the CTIME is current
			shutil.copyfile(metadata_dtd, os.path.join(distdir, "metadata.dtd"))

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for cwd in ("", "dev-libs", "dev-libs/A", "dev-libs/B"):
				abs_cwd = os.path.join(portdir_symlink, cwd)
				proc = subprocess.Popen([portage._python_interpreter, "-Wd",
					os.path.join(PORTAGE_BIN_PATH, "repoman"), "full"],
					cwd=abs_cwd, env=env, stdout=stdout)

				if debug:
					proc.wait()
				else:
					output = proc.stdout.readlines()
					proc.wait()
					proc.stdout.close()
					if proc.returncode != os.EX_OK:
						for line in output:
							sys.stderr.write(_unicode_decode(line))

				self.assertEqual(os.EX_OK, proc.returncode,
					"repoman failed in %s" % (cwd,))

			if git_binary is not None:
				for cwd, cmd in git_test:
					abs_cwd = os.path.join(portdir_symlink, cwd)
					proc = subprocess.Popen(cmd,
						cwd=abs_cwd, env=env, stdout=stdout)

					if debug:
						proc.wait()
					else:
						output = proc.stdout.readlines()
						proc.wait()
						proc.stdout.close()
						if proc.returncode != os.EX_OK:
							for line in output:
								sys.stderr.write(_unicode_decode(line))

					self.assertEqual(os.EX_OK, proc.returncode,
						"%s failed in %s" % (cmd, cwd,))
		finally:
			playground.cleanup()
