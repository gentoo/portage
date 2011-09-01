# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_BIN_PATH, PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class SimpleEmergeTestCase(TestCase):

	def testSimple(self):

		install_something = """
S="${WORKDIR}"
src_install() {
	einfo "installing something..."
	# TODO: Add prefix support to shell code/helpers, so we
	#       can use things like dodir and doins here.
	mkdir -p "${ED}"/usr/lib/${P}
	echo "blah blah blah" > "${ED}"/usr/lib/${P}/regular-file
}
"""

		ebuilds = {
			"dev-libs/A-1": {
				"EAPI" : "4",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": install_something,
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/B-1": {
				"EAPI" : "4",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": install_something,
			},
		}

		installed = {
			"dev-libs/A-1": {
				"EAPI" : "4",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
				"USE": "flag",
			},
			"dev-libs/B-1": {
				"EAPI" : "4",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"USE": "flag",
			},
			"dev-libs/depclean-me-1": {
				"EAPI" : "4",
				"IUSE" : "",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"USE": "",
			},
			"app-misc/depclean-me-1": {
				"EAPI" : "4",
				"IUSE" : "",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "dev-libs/depclean-me",
				"USE": "",
			},
		}

		test_args = (
			("--version",),
			("--info",),
			("--info", "--verbose"),
			("--pretend", "dev-libs/A"),
			("--pretend", "--tree", "--complete-graph", "dev-libs/A"),
			("-p", "dev-libs/B"),
			("--oneshot", "dev-libs/B",),
			("--oneshot", "dev-libs/A",),
			("--noreplace", "dev-libs/A",),
			("--pretend", "--depclean", "--verbose", "dev-libs/B"),
			("--pretend", "--depclean",),
			("--depclean",),
			("--unmerge", "--quiet", "dev-libs/A"),
			("-C", "--quiet", "dev-libs/B"),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		distdir = os.path.join(eprefix, "distdir")
		fake_bin = os.path.join(eprefix, "bin")
		portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
		portdir = settings["PORTDIR"]
		profile_path = settings.profile_path
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

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
			"__PORTAGE_TEST_EPREFIX" : eprefix,
			"DISTDIR" : distdir,
			"INFODIR" : "",
			"INFOPATH" : "",
			"PATH" : path,
			"PORTAGE_GRPNAME" : os.environ["PORTAGE_GRPNAME"],
			"PORTAGE_INST_GID" : str(portage.data.portage_gid),
			"PORTAGE_INST_UID" : str(portage.data.portage_uid),
			"PORTAGE_TMPDIR" : portage_tmpdir,
			"PORTAGE_USERNAME" : os.environ["PORTAGE_USERNAME"],
			"PORTDIR" : portdir,
			"PYTHONPATH" : pythonpath,
		}

		dirs = [distdir, fake_bin, portage_tmpdir, var_cache_edb]
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
			for args in test_args:
				proc = subprocess.Popen([portage._python_interpreter, "-Wd",
					os.path.join(PORTAGE_BIN_PATH, "emerge")] + list(args),
					env=env, stdout=subprocess.PIPE)
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
