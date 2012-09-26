# Copyright 2011-2012 Gentoo Foundation
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

pkg_pretend() {
	einfo "called pkg_pretend for $CATEGORY/$PF"
}

src_install() {
	einfo "installing something..."
	insinto /usr/lib/${P}
	echo "blah blah blah" > "${T}"/regular-file
	doins "${T}"/regular-file
	dosym regular-file /usr/lib/${P}/symlink || die

	# Test code for bug #381629, using a copyright symbol encoded with latin-1.
	# We use $(printf "\\xa9") rather than $'\\xa9', since printf apparently
	# works in any case, while $'\\xa9' transforms to \\xef\\xbf\\xbd under
	# some conditions. TODO: Find out why it transforms to \\xef\\xbf\\xbd when
	# running tests for Python 3.2 (even though it's bash that is ultimately
	# responsible for performing the transformation).
	local latin_1_dir=/usr/lib/${P}/latin-1-$(printf "\\xa9")-directory
	insinto "${latin_1_dir}"
	echo "blah blah blah" > "${T}"/latin-1-$(printf "\\xa9")-regular-file || die
	doins "${T}"/latin-1-$(printf "\\xa9")-regular-file
	dosym latin-1-$(printf "\\xa9")-regular-file ${latin_1_dir}/latin-1-$(printf "\\xa9")-symlink || die
}

pkg_config() {
	einfo "called pkg_config for $CATEGORY/$PF"
}

pkg_info() {
	einfo "called pkg_info for $CATEGORY/$PF"
}

pkg_preinst() {
	einfo "called pkg_preinst for $CATEGORY/$PF"

	# Test that has_version and best_version work correctly with
	# prefix (involves internal ROOT -> EROOT calculation in order
	# to support ROOT override via the environment with EAPIs 3
	# and later which support prefix).
	if has_version $CATEGORY/$PN:$SLOT ; then
		einfo "has_version detects an installed instance of $CATEGORY/$PN:$SLOT"
		einfo "best_version reports that the installed instance is $(best_version $CATEGORY/$PN:$SLOT)"
	else
		einfo "has_version does not detect an installed instance of $CATEGORY/$PN:$SLOT"
	fi
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
			"virtual/foo-0": {
				"EAPI" : "4",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
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
		trees = playground.trees
		portdb = trees[eroot]["porttree"].dbapi
		portdir = settings["PORTDIR"]
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
		cachedir = os.path.join(var_cache_edb, "dep")
		cachedir_pregen = os.path.join(portdir, "metadata", "cache")

		portage_python = portage._python_interpreter
		ebuild_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "ebuild"))
		egencache_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "egencache"))
		emerge_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "emerge"))
		emaint_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "emaint"))
		env_update_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "env-update"))
		fixpackages_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "fixpackages"))
		portageq_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "portageq"))
		quickpkg_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "quickpkg"))
		regenworld_cmd = (portage_python, "-Wd",
			os.path.join(PORTAGE_BIN_PATH, "regenworld"))

		rm_binary = find_binary("rm")
		self.assertEqual(rm_binary is None, False,
			"rm command not found")
		rm_cmd = (rm_binary,)

		egencache_extra_args = []
		if self._have_python_xml():
			egencache_extra_args.append("--update-use-local-desc")

		test_ebuild = portdb.findname("dev-libs/A-1")
		self.assertFalse(test_ebuild is None)

		test_commands = (
			env_update_cmd,
			emerge_cmd + ("--version",),
			emerge_cmd + ("--info",),
			emerge_cmd + ("--info", "--verbose"),
			emerge_cmd + ("--list-sets",),
			emerge_cmd + ("--check-news",),
			rm_cmd + ("-rf", cachedir),
			rm_cmd + ("-rf", cachedir_pregen),
			emerge_cmd + ("--regen",),
			rm_cmd + ("-rf", cachedir),
			({"FEATURES" : "metadata-transfer"},) + \
				emerge_cmd + ("--regen",),
			rm_cmd + ("-rf", cachedir),
			({"FEATURES" : "metadata-transfer"},) + \
				emerge_cmd + ("--regen",),
			rm_cmd + ("-rf", cachedir),
			egencache_cmd + ("--update",) + tuple(egencache_extra_args),
			({"FEATURES" : "metadata-transfer"},) + \
				emerge_cmd + ("--metadata",),
			rm_cmd + ("-rf", cachedir),
			({"FEATURES" : "metadata-transfer"},) + \
				emerge_cmd + ("--metadata",),
			emerge_cmd + ("--metadata",),
			rm_cmd + ("-rf", cachedir),
			emerge_cmd + ("--oneshot", "virtual/foo"),
			emerge_cmd + ("--pretend", "dev-libs/A"),
			ebuild_cmd + (test_ebuild, "manifest", "clean", "package", "merge"),
			emerge_cmd + ("--pretend", "--tree", "--complete-graph", "dev-libs/A"),
			emerge_cmd + ("-p", "dev-libs/B"),
			emerge_cmd + ("-B", "dev-libs/B",),
			emerge_cmd + ("--oneshot", "--usepkg", "dev-libs/B",),

			# trigger clean prior to pkg_pretend as in bug #390711
			ebuild_cmd + (test_ebuild, "unpack"), 
			emerge_cmd + ("--oneshot", "dev-libs/A",),

			emerge_cmd + ("--noreplace", "dev-libs/A",),
			emerge_cmd + ("--config", "dev-libs/A",),
			emerge_cmd + ("--info", "dev-libs/A", "dev-libs/B"),
			emerge_cmd + ("--pretend", "--depclean", "--verbose", "dev-libs/B"),
			emerge_cmd + ("--pretend", "--depclean",),
			emerge_cmd + ("--depclean",),
			quickpkg_cmd + ("dev-libs/A",),
			emerge_cmd + ("--usepkgonly", "dev-libs/A"),
			emaint_cmd + ("--check", "all"),
			emaint_cmd + ("--fix", "all"),
			fixpackages_cmd,
			regenworld_cmd,
			portageq_cmd + ("match", eroot, "dev-libs/A"),
			portageq_cmd + ("best_visible", eroot, "dev-libs/A"),
			portageq_cmd + ("best_visible", eroot, "binary", "dev-libs/A"),
			portageq_cmd + ("contents", eroot, "dev-libs/A-1"),
			portageq_cmd + ("metadata", eroot, "ebuild", "dev-libs/A-1", "EAPI", "IUSE", "RDEPEND"),
			portageq_cmd + ("metadata", eroot, "binary", "dev-libs/A-1", "EAPI", "USE", "RDEPEND"),
			portageq_cmd + ("metadata", eroot, "installed", "dev-libs/A-1", "EAPI", "USE", "RDEPEND"),
			portageq_cmd + ("owners", eroot, eroot + "usr"),
			emerge_cmd + ("-p", eroot + "usr"),
			emerge_cmd + ("-p", "--unmerge", "-q", eroot + "usr"),
			emerge_cmd + ("--unmerge", "--quiet", "dev-libs/A"),
			emerge_cmd + ("-C", "--quiet", "dev-libs/B"),
		)

		distdir = playground.distdir
		pkgdir = playground.pkgdir
		fake_bin = os.path.join(eprefix, "bin")
		portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
		profile_path = settings.profile_path
		user_config_dir = os.path.join(os.sep, eprefix, USER_CONFIG_PATH)

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
			"DISTDIR" : distdir,
			"EMERGE_WARNING_DELAY" : "0",
			"INFODIR" : "",
			"INFOPATH" : "",
			"PATH" : path,
			"PKGDIR" : pkgdir,
			"PORTAGE_INST_GID" : str(portage.data.portage_gid),
			"PORTAGE_INST_UID" : str(portage.data.portage_uid),
			"PORTAGE_PYTHON" : portage_python,
			"PORTAGE_TMPDIR" : portage_tmpdir,
			"PYTHONPATH" : pythonpath,
		}

		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			env["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]

		updates_dir = os.path.join(portdir, "profiles", "updates")
		dirs = [cachedir, cachedir_pregen, distdir, fake_bin,
			portage_tmpdir, updates_dir,
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
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(portdir, cp, "metadata.xml"), 'w') as f:
					f.write(playground.metadata_xml_template % xml_data)
			with open(os.path.join(updates_dir, "1Q-2010"), 'w') as f:
				f.write("""
slotmove =app-doc/pms-3 2 3
move dev-util/git dev-vcs/git
""")

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for args in test_commands:

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
