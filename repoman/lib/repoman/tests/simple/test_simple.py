# Copyright 2011-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import subprocess
import sys
import time
import types

from repoman._portage import portage
from portage import os
from portage.process import find_binary
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _reader
from portage.util._async.AsyncFunction import AsyncFunction

# pylint: disable=ungrouped-imports
from repoman import REPOMAN_BASE_PATH
from repoman.copyrights import update_copyright_year
from repoman.main import _repoman_init, _repoman_scan, _handle_result
from repoman.tests import TestCase


class RepomanRun(types.SimpleNamespace):
	async def run(self):
		self.expected = getattr(self, "expected", None) or {"returncode": 0}
		if self.debug:
			fd_pipes = {}
			pr = None
			pw = None
		else:
			pr, pw = os.pipe()
			fd_pipes = {1: pw, 2: pw}
			pr = open(pr, "rb", 0)

		proc = AsyncFunction(
			scheduler=asyncio.get_event_loop(),
			target=self._subprocess,
			args=(self.args, self.cwd, self.env, self.expected, self.debug),
			fd_pipes=fd_pipes,
		)

		proc.start()
		if pw is not None:
			os.close(pw)

		await proc.async_wait()

		if pr is None:
			stdio = None
		else:
			stdio = await _reader(pr)

		self.result = {
			"stdio": stdio,
			"result": proc.result,
		}

	@staticmethod
	def _subprocess(args, cwd, env, expected, debug):
		os.chdir(cwd)
		os.environ.update(env)
		portage.const.EPREFIX = env["PORTAGE_OVERRIDE_EPREFIX"]
		if debug:
			args = ["-vvvv"] + args
		repoman_vars = _repoman_init(["repoman"] + args)
		if repoman_vars.exitcode is not None:
			return {"returncode": repoman_vars.exitcode}
		result = _repoman_scan(*repoman_vars)
		returncode = _handle_result(*repoman_vars, result)
		qawarnings = repoman_vars.vcs_settings.qatracker.qawarnings
		warns = collections.defaultdict(list)
		fails = collections.defaultdict(list)
		for qacat, issues in repoman_vars.vcs_settings.qatracker.fails.items():
			if qacat in qawarnings:
				warns[qacat].extend(issues)
			else:
				fails[qacat].extend(issues)
		result = {"returncode": returncode}
		if fails:
			result["fails"] = fails
		if warns:
			result["warns"] = warns
		return result


class SimpleRepomanTestCase(TestCase):

	def testCopyrightUpdate(self):
		test_cases = (
			(
				'2011',
				'# Copyright 1999-2008 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999-2011 Gentoo Authors; Distributed under the GPL v2',
			),
			(
				'2011',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999-2011 Gentoo Authors; Distributed under the GPL v2',
			),
			(
				'1999',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
				'# Copyright 1999 Gentoo Foundation; Distributed under the GPL v2',
			),
			(
				'2018',
				'# Copyright 1999-2008 Gentoo Authors; Distributed under the GPL v2',
				'# Copyright 1999-2018 Gentoo Authors; Distributed under the GPL v2',
			),
			(
				'2018',
				'# Copyright 2017 Gentoo Authors; Distributed under the GPL v2',
				'# Copyright 2017-2018 Gentoo Authors; Distributed under the GPL v2',
			),
		)

		for year, before, after in test_cases:
			self.assertEqual(update_copyright_year(year, before), after)

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

		copyright_header = """# Copyright 1999-%s Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

""" % time.gmtime().tm_year

		pkg_preinst_references_forbidden_var = """
pkg_preinst() {
	echo "This ${A} reference is not allowed. Neither is this $BROOT reference."
}
"""

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
			("x86", "default/linux/x86/test_dev", "dev"),
			("x86", "default/linux/x86/test_exp", "exp"),
		)

		profile = {
			"eapi": ("5",),
			"package.use.stable.mask": ("dev-libs/A flag",)
		}

		ebuilds = {
			"dev-libs/A-0": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "5",
				"HOMEPAGE" : "https://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/A-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "https://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/B-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "https://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
			},
			"dev-libs/C-0": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "7",
				"HOMEPAGE" : "https://example.com",
				"IUSE" : "flag",
				# must be unstable, since dev-libs/A[flag] is stable masked
				"KEYWORDS": "~x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/A[flag] )",
				"MISC_CONTENT": pkg_preinst_references_forbidden_var,
			},
		}
		licenses = ["GPL-2"]
		arch_list = ["x86"]
		metadata_xsd = os.path.join(REPOMAN_BASE_PATH, "cnf/metadata.xsd")
		metadata_xml_files = (
			(
				"dev-libs/A",
				{
					"flags" : "<flag name='flag' restrict='&gt;=dev-libs/A-0'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/B",
				{
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/C",
				{
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
		)

		use_desc = (
			("flag", "Description of how USE='flag' affects packages"),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			profile=profile, repo_configs=repo_configs, debug=debug)

		loop = asyncio._wrap_loop()
		loop.run_until_complete(
			asyncio.ensure_future(
				self._async_test_simple(
					playground,
					metadata_xml_files,
					profiles,
					profile,
					licenses,
					arch_list,
					use_desc,
					metadata_xsd,
					copyright_header,
					debug,
				),
				loop=loop,
			)
		)

	async def _async_test_simple(
		self,
		playground,
		metadata_xml_files,
		profiles,
		profile,
		licenses,
		arch_list,
		use_desc,
		metadata_xsd,
		copyright_header,
		debug,
	):
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		portdb = playground.trees[playground.eroot]["porttree"].dbapi
		homedir = os.path.join(eroot, "home")
		distdir = os.path.join(eprefix, "distdir")
		test_repo_location = settings.repositories["test_repo"].location
		profiles_dir = os.path.join(test_repo_location, "profiles")
		license_dir = os.path.join(test_repo_location, "licenses")

		repoman_cmd = (portage._python_interpreter, "-b", "-Wd",
			os.path.join(self.bindir, "repoman"))

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
		expected_warnings = {
			"returncode": 0,
			"warns": {
				"variable.phase": [
					"dev-libs/C/C-0.ebuild: line 15: phase pkg_preinst: EAPI 7: variable A: Forbidden reference to variable specified by PMS",
					"dev-libs/C/C-0.ebuild: line 15: phase pkg_preinst: EAPI 7: variable BROOT: Forbidden reference to variable specified by PMS",
				]
			},
		}

		git_test = (
			("", RepomanRun(args=["--version"])),
			("", RepomanRun(args=["manifest"])),
			("", git_cmd + ("config", "--global", "user.name", committer_name,)),
			("", git_cmd + ("config", "--global", "user.email", committer_email,)),
			("", git_cmd + ("init-db",)),
			("", git_cmd + ("add", ".")),
			("", git_cmd + ("commit", "-a", "-m", "add whole repo")),
			("", RepomanRun(args=["full", "-d"], expected=expected_warnings)),
			("", RepomanRun(args=["full", "--include-profiles", "default/linux/x86/test_profile"], expected=expected_warnings)),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "2.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "2.ebuild")),
			("", RepomanRun(args=["commit", "-m", "cat/pkg: bump to version 2"], expected=expected_warnings)),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "3.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "3.ebuild")),
			("dev-libs", RepomanRun(args=["commit", "-m", "cat/pkg: bump to version 3"], expected=expected_warnings)),
			("", cp_cmd + (test_ebuild, test_ebuild[:-8] + "4.ebuild")),
			("", git_cmd + ("add", test_ebuild[:-8] + "4.ebuild")),
			("dev-libs/A", RepomanRun(args=["commit", "-m", "cat/pkg: bump to version 4"])),
		)

		env = {
			"PORTAGE_OVERRIDE_EPREFIX" : eprefix,
			"DISTDIR" : distdir,
			"GENTOO_COMMITTER_NAME" : committer_name,
			"GENTOO_COMMITTER_EMAIL" : committer_email,
			"HOME" : homedir,
			"PATH" : os.environ["PATH"],
			"PORTAGE_GRPNAME" : os.environ["PORTAGE_GRPNAME"],
			"PORTAGE_USERNAME" : os.environ["PORTAGE_USERNAME"],
			"PORTAGE_REPOSITORIES" : settings.repositories.config_string(),
			"PYTHONDONTWRITEBYTECODE" : os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
		}

		if os.environ.get("SANDBOX_ON") == "1":
			# avoid problems from nested sandbox instances
			env["FEATURES"] = "-sandbox -usersandbox"

		dirs = [homedir, license_dir, profiles_dir, distdir]
		try:
			for d in dirs:
				ensure_dirs(d)
			with open(os.path.join(test_repo_location, "skel.ChangeLog"), 'w') as f:
				f.write(copyright_header)
			with open(os.path.join(profiles_dir, "profiles.desc"), 'w') as f:
				for x in profiles:
					f.write("%s %s %s\n" % x)

			# ResolverPlayground only created the first profile,
			# so create the remaining ones.
			for x in profiles[1:]:
				sub_profile_dir = os.path.join(profiles_dir, x[1])
				ensure_dirs(sub_profile_dir)
				for config_file, lines in profile.items():
					file_name = os.path.join(sub_profile_dir, config_file)
					with open(file_name, "w") as f:
						for line in lines:
							f.write("%s\n" % line)

			for x in licenses:
				open(os.path.join(license_dir, x), 'wb').close()
			with open(os.path.join(profiles_dir, "arch.list"), 'w') as f:
				for x in arch_list:
					f.write("%s\n" % x)
			with open(os.path.join(profiles_dir, "use.desc"), 'w') as f:
				for k, v in use_desc:
					f.write("%s - %s\n" % (k, v))
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(test_repo_location, cp, "metadata.xml"), 'w') as f:
					f.write(playground.metadata_xml_template % xml_data)
			# Use a symlink to test_repo, in order to trigger bugs
			# involving canonical vs. non-canonical paths.
			test_repo_symlink = os.path.join(eroot, "test_repo_symlink")
			os.symlink(test_repo_location, test_repo_symlink)
			metadata_xsd_dest = os.path.join(test_repo_location, 'metadata/xml-schema/metadata.xsd')
			os.makedirs(os.path.dirname(metadata_xsd_dest))
			os.symlink(metadata_xsd, metadata_xsd_dest)

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for cwd in ("", "dev-libs", "dev-libs/A", "dev-libs/B", "dev-libs/C"):
				abs_cwd = os.path.join(test_repo_symlink, cwd)

				proc = await asyncio.create_subprocess_exec(
					*(repoman_cmd + ("full",)),
					env=env,
					stderr=None,
					stdout=stdout,
					cwd=abs_cwd
				)

				if debug:
					await proc.wait()
				else:
					output, _err = await proc.communicate()
					await proc.wait()
					if proc.returncode != os.EX_OK:
						portage.writemsg(output)

				self.assertEqual(
					os.EX_OK, proc.returncode, "repoman failed in %s" % (cwd,)
				)

			if git_binary is not None:
				for cwd, cmd in git_test:
					abs_cwd = os.path.join(test_repo_symlink, cwd)
					if isinstance(cmd, RepomanRun):
						cmd.cwd = abs_cwd
						cmd.env = env
						cmd.debug = debug
						await cmd.run()
						if cmd.result["result"] != cmd.expected and cmd.result.get("stdio"):
							portage.writemsg(cmd.result["stdio"])
						try:
							self.assertEqual(cmd.result["result"], cmd.expected)
						except Exception:
							print(cmd.result["result"], file=sys.stderr, flush=True)
							raise
						continue

					proc = await asyncio.create_subprocess_exec(
						*cmd, env=env, stderr=None, stdout=stdout, cwd=abs_cwd
					)

					if debug:
						await proc.wait()
					else:
						output, _err = await proc.communicate()
						await proc.wait()
						if proc.returncode != os.EX_OK:
							portage.writemsg(output)

					self.assertEqual(
						os.EX_OK,
						proc.returncode,
						"%s failed in %s"
						% (
							cmd,
							cwd,
						),
					)
		finally:
			playground.cleanup()
