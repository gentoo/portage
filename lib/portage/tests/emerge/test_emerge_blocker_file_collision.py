# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class BlockerFileCollisionEmergeTestCase(TestCase):

	def testBlockerFileCollision(self):

		debug = False

		install_something = """
S="${WORKDIR}"

src_install() {
	einfo "installing something..."
	insinto /usr/lib
	echo "${PN}" > "${T}/file-collision"
	doins "${T}/file-collision"
}
"""

		ebuilds = {
			"dev-libs/A-1" : {
				"EAPI": "6",
				"MISC_CONTENT": install_something,
				"RDEPEND":  "!dev-libs/B",
			},
			"dev-libs/B-1" : {
				"EAPI": "6",
				"MISC_CONTENT": install_something,
				"RDEPEND":  "!dev-libs/A",
			},
		}

		playground = ResolverPlayground(ebuilds=ebuilds, debug=debug)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
		user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

		portage_python = portage._python_interpreter
		emerge_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "emerge"))

		file_collision = os.path.join(eroot, 'usr/lib/file-collision')

		test_commands = (
			emerge_cmd + ("--oneshot", "dev-libs/A",),
			(lambda: portage.util.grablines(file_collision) == ["A\n"],),
			emerge_cmd + ("--oneshot", "dev-libs/B",),
			(lambda: portage.util.grablines(file_collision) == ["B\n"],),
			emerge_cmd + ("--oneshot", "dev-libs/A",),
			(lambda: portage.util.grablines(file_collision) == ["A\n"],),
			({"FEATURES":"parallel-install"},) + emerge_cmd + ("--oneshot", "dev-libs/B",),
			(lambda: portage.util.grablines(file_collision) == ["B\n"],),
			({"FEATURES":"parallel-install"},) + emerge_cmd + ("-Cq", "dev-libs/B",),
			(lambda: not os.path.exists(file_collision),),
		)

		fake_bin = os.path.join(eprefix, "bin")
		portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
		profile_path = settings.profile_path

		path =  os.environ.get("PATH")
		if path is not None and not path.strip():
			path = None
		if path is None:
			path = ""
		else:
			path = ":" + path
		path = fake_bin + path

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
			"PATH" : path,
			"PORTAGE_PYTHON" : portage_python,
			"PORTAGE_REPOSITORIES" : settings.repositories.config_string(),
			"PYTHONDONTWRITEBYTECODE" : os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
			"PYTHONPATH" : pythonpath,
		}

		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			env["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]

		dirs = [playground.distdir, fake_bin, portage_tmpdir,
			user_config_dir, var_cache_edb]
		true_symlinks = ["chown", "chgrp"]
		true_binary = find_binary("true")
		self.assertEqual(true_binary is None, False,
			"true command not found")
		try:
			for d in dirs:
				ensure_dirs(d)
			for x in true_symlinks:
				os.symlink(true_binary, os.path.join(fake_bin, x))
			with open(os.path.join(var_cache_edb, "counter"), 'wb') as f:
				f.write(b"100")
			# non-empty system set keeps --depclean quiet
			with open(os.path.join(profile_path, "packages"), 'w') as f:
				f.write("*dev-libs/token-system-pkg")

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for i, args in enumerate(test_commands):

				if hasattr(args[0], '__call__'):
					self.assertTrue(args[0](),
						"callable at index %s failed" % (i,))
					continue

				if isinstance(args[0], dict):
					local_env = env.copy()
					local_env.update(args[0])
					args = args[1:]
				else:
					local_env = env

				proc = subprocess.Popen(args,
					env=local_env, stdout=stdout)

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
					"emerge failed with args %s" % (args,))
		finally:
			playground.debug = False
			playground.cleanup()
