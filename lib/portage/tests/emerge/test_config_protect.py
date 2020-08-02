# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
from functools import partial
import shutil
import stat
import subprocess
import sys
import time

import portage
from portage import os
from portage import _encodings, _unicode_decode
from portage.const import BASH_BINARY, PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import (ensure_dirs, find_updated_config_files,
	shlex_split)

class ConfigProtectTestCase(TestCase):

	def testConfigProtect(self):
		"""
		Demonstrates many different scenarios. For example:

		 * regular file replaces regular file
		 * regular file replaces symlink
		 * regular file replaces directory
		 * symlink replaces symlink
		 * symlink replaces regular file
		 * symlink replaces directory
		 * directory replaces regular file
		 * directory replaces symlink
		"""

		debug = False

		content_A_1 = """
S="${WORKDIR}"

src_install() {
	insinto /etc/A
	keepdir /etc/A/dir_a
	keepdir /etc/A/symlink_replaces_dir
	keepdir /etc/A/regular_replaces_dir
	echo regular_a_1 > "${T}"/regular_a
	doins "${T}"/regular_a
	echo regular_b_1 > "${T}"/regular_b
	doins "${T}"/regular_b
	dosym regular_a /etc/A/regular_replaces_symlink
	dosym regular_b /etc/A/symlink_replaces_symlink
	echo regular_replaces_regular_1 > \
		"${T}"/regular_replaces_regular
	doins "${T}"/regular_replaces_regular
	echo symlink_replaces_regular > \
		"${T}"/symlink_replaces_regular
	doins "${T}"/symlink_replaces_regular
}

"""

		content_A_2 = """
S="${WORKDIR}"

src_install() {
	insinto /etc/A
	keepdir /etc/A/dir_a
	dosym dir_a /etc/A/symlink_replaces_dir
	echo regular_replaces_dir > "${T}"/regular_replaces_dir
	doins "${T}"/regular_replaces_dir
	echo regular_a_2 > "${T}"/regular_a
	doins "${T}"/regular_a
	echo regular_b_2 > "${T}"/regular_b
	doins "${T}"/regular_b
	echo regular_replaces_symlink > \
		"${T}"/regular_replaces_symlink
	doins "${T}"/regular_replaces_symlink
	dosym regular_b /etc/A/symlink_replaces_symlink
	echo regular_replaces_regular_2 > \
		"${T}"/regular_replaces_regular
	doins "${T}"/regular_replaces_regular
	dosym regular_a /etc/A/symlink_replaces_regular
}

"""

		ebuilds = {
			"dev-libs/A-1": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": content_A_1,
			},
			"dev-libs/A-2": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": content_A_2,
			},
		}

		playground = ResolverPlayground(
			ebuilds=ebuilds, debug=debug)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

		portage_python = portage._python_interpreter
		dispatch_conf_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "dispatch-conf"))
		emerge_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "emerge"))
		etc_update_cmd = (BASH_BINARY,
			os.path.join(self.sbindir, "etc-update"))
		etc_update_auto = etc_update_cmd + ("--automode", "-5",)

		config_protect = "/etc"

		def modify_files(dir_path):
			for name in os.listdir(dir_path):
				path = os.path.join(dir_path, name)
				st = os.lstat(path)
				if stat.S_ISREG(st.st_mode):
					with io.open(path, mode='a',
						encoding=_encodings["stdio"]) as f:
						f.write("modified at %d\n" % time.time())
				elif stat.S_ISLNK(st.st_mode):
					old_dest = os.readlink(path)
					os.unlink(path)
					os.symlink(old_dest +
						" modified at %d" % time.time(), path)

		def updated_config_files(count):
			self.assertEqual(count,
				sum(len(x[1]) for x in find_updated_config_files(eroot,
				shlex_split(config_protect))))

		test_commands = (
			etc_update_cmd,
			dispatch_conf_cmd,
			emerge_cmd + ("-1", "=dev-libs/A-1"),
			partial(updated_config_files, 0),
			emerge_cmd + ("-1", "=dev-libs/A-2"),
			partial(updated_config_files, 2),
			etc_update_auto,
			partial(updated_config_files, 0),
			emerge_cmd + ("-1", "=dev-libs/A-2"),
			partial(updated_config_files, 0),
			# Test bug #523684, where a file renamed or removed by the
			# admin forces replacement files to be merged with config
			# protection.
			partial(shutil.rmtree,
				os.path.join(eprefix, "etc", "A")),
			emerge_cmd + ("-1", "=dev-libs/A-2"),
			partial(updated_config_files, 8),
			etc_update_auto,
			partial(updated_config_files, 0),
			# Modify some config files, and verify that it triggers
			# config protection.
			partial(modify_files,
				os.path.join(eroot, "etc", "A")),
			emerge_cmd + ("-1", "=dev-libs/A-2"),
			partial(updated_config_files, 6),
			etc_update_auto,
			partial(updated_config_files, 0),
			# Modify some config files, downgrade to A-1, and verify
			# that config protection works properly when the file
			# types are changing.
			partial(modify_files,
				os.path.join(eroot, "etc", "A")),
			emerge_cmd + ("-1", "--noconfmem", "=dev-libs/A-1"),
			partial(updated_config_files, 6),
			etc_update_auto,
			partial(updated_config_files, 0),
		)

		distdir = playground.distdir
		fake_bin = os.path.join(eprefix, "bin")
		portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")

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
			"CLEAN_DELAY" : "0",
			"CONFIG_PROTECT": config_protect,
			"DISTDIR" : distdir,
			"EMERGE_DEFAULT_OPTS": "-v",
			"EMERGE_WARNING_DELAY" : "0",
			"INFODIR" : "",
			"INFOPATH" : "",
			"PATH" : path,
			"PORTAGE_INST_GID" : str(portage.data.portage_gid),
			"PORTAGE_INST_UID" : str(portage.data.portage_uid),
			"PORTAGE_PYTHON" : portage_python,
			"PORTAGE_REPOSITORIES" : settings.repositories.config_string(),
			"PORTAGE_TMPDIR" : portage_tmpdir,
			"PYTHONDONTWRITEBYTECODE" : os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
			"PYTHONPATH" : pythonpath,
			"__PORTAGE_TEST_PATH_OVERRIDE" : fake_bin,
		}

		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			env["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]

		dirs = [distdir, fake_bin, portage_tmpdir,
			var_cache_edb]
		etc_symlinks = ("dispatch-conf.conf", "etc-update.conf")
		# Override things that may be unavailable, or may have portability
		# issues when running tests in exotic environments.
		#   prepstrip - bug #447810 (bash read builtin EINTR problem)
		true_symlinks = ["prepstrip", "scanelf"]
		true_binary = find_binary("true")
		self.assertEqual(true_binary is None, False,
			"true command not found")
		try:
			for d in dirs:
				ensure_dirs(d)
			for x in true_symlinks:
				os.symlink(true_binary, os.path.join(fake_bin, x))
			for x in etc_symlinks:
				os.symlink(os.path.join(self.cnf_etc_path, x),
					os.path.join(eprefix, "etc", x))
			with open(os.path.join(var_cache_edb, "counter"), 'wb') as f:
				f.write(b"100")

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for args in test_commands:

				if hasattr(args, '__call__'):
					args()
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
			playground.cleanup()
