# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class SimpleEmergeTestCase(TestCase):

	def _have_python_xml(self):
		try:
			__import__("xml.etree.ElementTree")
			__import__("xml.parsers.expat").parsers.expat.ExpatError
		except (AttributeError, ImportError):
			return False
		return True

	def testSimple(self):

		debug = False

		install_something = """
S="${WORKDIR}"
src_install() {
	einfo "installing something..."
	# TODO: Add prefix support to shell code/helpers, so we
	#       can use things like dodir and doins here.
	mkdir -p "${ED}"/usr/lib/${P} || die
	echo "blah blah blah" > "${ED}"/usr/lib/${P}/regular-file || die
	ln -s regular-file "${ED}"/usr/lib/${P}/symlink || die

	# Test code for bug #381629, using a copyright symbol encoded with latin-1.
	# We use $(printf "\\xa9") rather than $'\\xa9', since printf apparently
	# works in any case, while $'\\xa9' transforms to \\xef\\xbf\\xbd under
	# some conditions. TODO: Find out why it transforms to \\xef\\xbf\\xbd when
	# running tests for Python 3.2 (even though it's bash that is ultimately
	# responsible for performing the transformation).
	local latin_1_dir=${ED}/usr/lib/${P}/latin-1-$(printf "\\xa9")-directory
	mkdir "${latin_1_dir}"
	echo "blah blah blah" > ${latin_1_dir}/latin-1-$(printf "\\xa9")-regular-file || die
	ln -s latin-1-$(printf "\\xa9")-regular-file ${latin_1_dir}/latin-1-$(printf "\\xa9")-symlink || die
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
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, debug=debug)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]

		portage_python = portage._python_interpreter
		egencache_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "egencache"))
		emerge_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "emerge"))
		emaint_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "emaint"))
		portageq_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "portageq"))
		quickpkg_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "quickpkg"))

		egencache_extra_args = []
		if self._have_python_xml():
			egencache_extra_args.append("--update-use-local-desc")

		test_commands = (
			egencache_cmd + ("--update",) + tuple(egencache_extra_args),
			emerge_cmd + ("--version",),
			emerge_cmd + ("--info",),
			emerge_cmd + ("--info", "--verbose"),
			emerge_cmd + ("--pretend", "dev-libs/A"),
			emerge_cmd + ("--pretend", "--tree", "--complete-graph", "dev-libs/A"),
			emerge_cmd + ("-p", "dev-libs/B"),
			emerge_cmd + ("-B", "dev-libs/B",),
			emerge_cmd + ("--oneshot", "--usepkg", "dev-libs/B",),
			emerge_cmd + ("--oneshot", "dev-libs/A",),
			emerge_cmd + ("--noreplace", "dev-libs/A",),
			emerge_cmd + ("--pretend", "--depclean", "--verbose", "dev-libs/B"),
			emerge_cmd + ("--pretend", "--depclean",),
			emerge_cmd + ("--depclean",),
			quickpkg_cmd + ("dev-libs/A",),
			emerge_cmd + ("--usepkgonly", "dev-libs/A"),
			emaint_cmd + ("--check", "all"),
			emaint_cmd + ("--fix", "all"),
			portageq_cmd + ("match", "/", "dev-libs/A"),
			portageq_cmd + ("best_visible", "/", "dev-libs/A"),
			portageq_cmd + ("best_visible", "/", "binary", "dev-libs/A"),
			portageq_cmd + ("contents", "/", "dev-libs/A-1"),
			portageq_cmd + ("metadata", "/", "ebuild", "dev-libs/A-1", "EAPI", "IUSE", "RDEPEND"),
			portageq_cmd + ("metadata", "/", "binary", "dev-libs/A-1", "EAPI", "USE", "RDEPEND"),
			portageq_cmd + ("metadata", "/", "installed", "dev-libs/A-1", "EAPI", "USE", "RDEPEND"),
			portageq_cmd + ("owners", "/", eroot + "usr"),
			emerge_cmd + ("--unmerge", "--quiet", "dev-libs/A"),
			emerge_cmd + ("-C", "--quiet", "dev-libs/B"),
		)

		distdir = os.path.join(eprefix, "distdir")
		pkgdir = os.path.join(eprefix, "pkgdir")
		fake_bin = os.path.join(eprefix, "bin")
		portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
		portdir = settings["PORTDIR"]
		profile_path = settings.profile_path
		user_config_dir = os.path.join(os.sep, eprefix, USER_CONFIG_PATH)
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

		features = []
		features.append("metadata-transfer")
		if not portage.process.sandbox_capable:
			features.append("-sandbox")

		# Since egencache ignores settings from the calling environment,
		# configure it via make.conf.
		make_conf = (
			"FEATURES=\"%s\"\n" % (" ".join(features),),
			"PORTDIR=\"%s\"\n" % (portdir,),
		)

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
			"CLEAN_DELAY" : "0",
			"DISTDIR" : distdir,
			"EMERGE_WARNING_DELAY" : "0",
			"INFODIR" : "",
			"INFOPATH" : "",
			"PATH" : path,
			"PKGDIR" : pkgdir,
			"PORTAGE_GRPNAME" : os.environ["PORTAGE_GRPNAME"],
			"PORTAGE_INST_GID" : str(portage.data.portage_gid),
			"PORTAGE_INST_UID" : str(portage.data.portage_uid),
			"PORTAGE_PYTHON" : portage_python,
			"PORTAGE_TMPDIR" : portage_tmpdir,
			"PORTAGE_USERNAME" : os.environ["PORTAGE_USERNAME"],
			"PYTHONPATH" : pythonpath,
		}

		dirs = [distdir, fake_bin, portage_tmpdir,
			user_config_dir, var_cache_edb]
		true_symlinks = ["chown", "chgrp"]
		true_binary = find_binary("true")
		self.assertEqual(true_binary is None, False,
			"true command not found")
		try:
			for d in dirs:
				ensure_dirs(d)
			with open(os.path.join(user_config_dir, "make.conf"), 'w') as f:
				for line in make_conf:
					f.write(line)
			for x in true_symlinks:
				os.symlink(true_binary, os.path.join(fake_bin, x))
			with open(os.path.join(var_cache_edb, "counter"), 'wb') as f:
				f.write(b"100")
			# non-empty system set keeps --depclean quiet
			with open(os.path.join(profile_path, "packages"), 'w') as f:
				f.write("*dev-libs/token-system-pkg")
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(portdir, cp, "metadata.xml"), 'w') as f:
					f.write(playground.metadata_xml_template % xml_data)

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for args in test_commands:

				proc = subprocess.Popen(args,
					env=env, stdout=stdout)

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
