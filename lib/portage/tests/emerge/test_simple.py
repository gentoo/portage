# Copyright 2011-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import subprocess

import portage
from portage import shutil, os
from portage.const import (BASH_BINARY, BINREPOS_CONF_FILE, PORTAGE_PYM_PATH, USER_CONFIG_PATH)
from portage.cache.mappings import Mapping
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.tests.util.test_socks5 import AsyncHTTPServer
from portage.util import (ensure_dirs, find_updated_config_files,
	shlex_split)
from portage.util.futures import asyncio


class BinhostContentMap(Mapping):
	def __init__(self, remote_path, local_path):
		self._remote_path = remote_path
		self._local_path = local_path

	def __getitem__(self, request_path):
		safe_path = os.path.normpath(request_path)
		if not safe_path.startswith(self._remote_path + '/'):
			raise KeyError(request_path)
		local_path = os.path.join(self._local_path, safe_path[len(self._remote_path)+1:])
		try:
			with open(local_path, 'rb') as f:
				return f.read()
		except EnvironmentError:
			raise KeyError(request_path)


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

	# Test CONFIG_PROTECT
	insinto /etc
	newins "${T}"/regular-file ${PN}-${SLOT%/*}

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

	call_has_and_best_version
}

pkg_config() {
	einfo "called pkg_config for $CATEGORY/$PF"
}

pkg_info() {
	einfo "called pkg_info for $CATEGORY/$PF"
}

pkg_preinst() {
	if ! ___eapi_best_version_and_has_version_support_-b_-d_-r; then
		# The BROOT variable is unset during pkg_* phases for EAPI 7,
		# therefore best/has_version -b is expected to fail if we attempt
		# to call it for EAPI 7 here.
		call_has_and_best_version
	fi
}

call_has_and_best_version() {
	local root_arg
	if ___eapi_best_version_and_has_version_support_-b_-d_-r; then
		root_arg="-b"
	else
		root_arg="--host-root"
	fi
	einfo "called ${EBUILD_PHASE_FUNC} for $CATEGORY/$PF"
	einfo "EPREFIX=${EPREFIX}"
	einfo "PORTAGE_OVERRIDE_EPREFIX=${PORTAGE_OVERRIDE_EPREFIX}"
	einfo "ROOT=${ROOT}"
	einfo "EROOT=${EROOT}"
	einfo "SYSROOT=${SYSROOT}"
	einfo "ESYSROOT=${ESYSROOT}"
	einfo "BROOT=${BROOT}"
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
	if [[ ${EPREFIX} != ${PORTAGE_OVERRIDE_EPREFIX} ]] ; then
		if has_version ${root_arg} $CATEGORY/$PN:$SLOT ; then
			einfo "has_version ${root_arg} detects an installed instance of $CATEGORY/$PN:$SLOT"
			einfo "best_version ${root_arg} reports that the installed instance is $(best_version ${root_arg} $CATEGORY/$PN:$SLOT)"
		else
			einfo "has_version ${root_arg} does not detect an installed instance of $CATEGORY/$PN:$SLOT"
		fi
	fi
}

"""

		ebuilds = {
			"dev-libs/A-1": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": install_something,
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/B-1": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"MISC_CONTENT": install_something,
			},
			"dev-libs/C-1": {
				"EAPI" : "7",
				"KEYWORDS": "~x86",
				"RDEPEND": "dev-libs/D[flag]",
				"MISC_CONTENT": install_something,
			},
			"dev-libs/D-1": {
				"EAPI" : "7",
				"KEYWORDS": "~x86",
				"IUSE" : "flag",
				"MISC_CONTENT": install_something,
			},
			"virtual/foo-0": {
				"EAPI" : "5",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
			},
		}

		installed = {
			"dev-libs/A-1": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
				"USE": "flag",
			},
			"dev-libs/B-1": {
				"EAPI" : "5",
				"IUSE" : "+flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"USE": "flag",
			},
			"dev-libs/depclean-me-1": {
				"EAPI" : "5",
				"IUSE" : "",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"USE": "",
			},
			"app-misc/depclean-me-1": {
				"EAPI" : "5",
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
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/B",
				{
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, debug=debug)

		loop = asyncio._wrap_loop()
		loop.run_until_complete(asyncio.ensure_future(
			self._async_test_simple(playground, metadata_xml_files, loop=loop), loop=loop))

	async def _async_test_simple(self, playground, metadata_xml_files, loop):

		debug = playground.debug
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		trees = playground.trees
		portdb = trees[eroot]["porttree"].dbapi
		test_repo_location = settings.repositories["test_repo"].location
		var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
		cachedir = os.path.join(var_cache_edb, "dep")
		cachedir_pregen = os.path.join(test_repo_location, "metadata", "md5-cache")

		portage_python = portage._python_interpreter
		dispatch_conf_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "dispatch-conf"))
		ebuild_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "ebuild"))
		egencache_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "egencache"),
			"--repo", "test_repo",
			"--repositories-configuration", settings.repositories.config_string())
		emerge_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "emerge"))
		emaint_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "emaint"))
		env_update_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "env-update"))
		etc_update_cmd = (BASH_BINARY,
			os.path.join(self.sbindir, "etc-update"))
		fixpackages_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "fixpackages"))
		portageq_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "portageq"))
		quickpkg_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.bindir, "quickpkg"))
		regenworld_cmd = (portage_python, "-b", "-Wd",
			os.path.join(self.sbindir, "regenworld"))

		rm_binary = find_binary("rm")
		self.assertEqual(rm_binary is None, False,
			"rm command not found")
		rm_cmd = (rm_binary,)

		egencache_extra_args = []
		if self._have_python_xml():
			egencache_extra_args.append("--update-use-local-desc")

		test_ebuild = portdb.findname("dev-libs/A-1")
		self.assertFalse(test_ebuild is None)

		cross_prefix = os.path.join(eprefix, "cross_prefix")
		cross_root = os.path.join(eprefix, "cross_root")
		cross_eroot = os.path.join(cross_root, eprefix.lstrip(os.sep))

		binhost_dir = os.path.join(eprefix, "binhost")
		binhost_address = '127.0.0.1'
		binhost_remote_path = '/binhost'
		binhost_server = AsyncHTTPServer(binhost_address,
			BinhostContentMap(binhost_remote_path, binhost_dir), loop).__enter__()
		binhost_uri = 'http://{address}:{port}{path}'.format(
			address=binhost_address,
			port=binhost_server.server_port,
			path=binhost_remote_path)

		test_commands = ()

		if hasattr(argparse.ArgumentParser, "parse_intermixed_args"):
			test_commands += (
				emerge_cmd + ("--oneshot", "dev-libs/A", "-v", "dev-libs/A"),
			)

		test_commands += (
			emerge_cmd + ("--usepkgonly", "--root", cross_root, "--quickpkg-direct=y", "--quickpkg-direct-root", "/", "dev-libs/A"),
			emerge_cmd + ("--usepkgonly", "--quickpkg-direct=y", "--quickpkg-direct-root", cross_root, "dev-libs/A"),
			env_update_cmd,
			portageq_cmd + ("envvar", "-v", "CONFIG_PROTECT", "EROOT",
				"PORTAGE_CONFIGROOT", "PORTAGE_TMPDIR", "USERLAND"),
			etc_update_cmd,
			dispatch_conf_cmd,
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
			lambda: self.assertFalse(os.path.exists(
				os.path.join(pkgdir, "virtual", "foo", "foo-0-1.xpak"))),
			({"FEATURES" : "unmerge-backup"},) + \
				emerge_cmd + ("--unmerge", "virtual/foo"),
			lambda: self.assertTrue(os.path.exists(
				os.path.join(pkgdir, "virtual", "foo", "foo-0-1.xpak"))),
			emerge_cmd + ("--pretend", "dev-libs/A"),
			ebuild_cmd + (test_ebuild, "manifest", "clean", "package", "merge"),
			emerge_cmd + ("--pretend", "--tree", "--complete-graph", "dev-libs/A"),
			emerge_cmd + ("-p", "dev-libs/B"),
			emerge_cmd + ("-p", "--newrepo", "dev-libs/B"),
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
			quickpkg_cmd + ("--include-config", "y", "dev-libs/A",),
			# Test bug #523684, where a file renamed or removed by the
			# admin forces replacement files to be merged with config
			# protection.
			lambda: self.assertEqual(0,
				len(list(find_updated_config_files(eroot,
				shlex_split(settings["CONFIG_PROTECT"]))))),
			lambda: os.unlink(os.path.join(eprefix, "etc", "A-0")),
			emerge_cmd + ("--usepkgonly", "dev-libs/A"),
			lambda: self.assertEqual(1,
				len(list(find_updated_config_files(eroot,
				shlex_split(settings["CONFIG_PROTECT"]))))),
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

			# If EMERGE_DEFAULT_OPTS contains --autounmask=n, then --autounmask
			# must be specified with --autounmask-continue.
			({"EMERGE_DEFAULT_OPTS" : "--autounmask=n"},) + \
				emerge_cmd + ("--autounmask", "--autounmask-continue", "dev-libs/C",),
			# Verify that the above --autounmask-continue command caused
			# USE=flag to be applied correctly to dev-libs/D.
			portageq_cmd + ("match", eroot, "dev-libs/D[flag]"),

			# Test cross-prefix usage, including chpathtool for binpkgs.
			# EAPI 7
			({"EPREFIX" : cross_prefix},) + \
				emerge_cmd + ("dev-libs/C",),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/C"),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/D"),
			({"ROOT": cross_root},) + emerge_cmd + ("dev-libs/D",),
			portageq_cmd + ("has_version", cross_eroot, "dev-libs/D"),
			# EAPI 5
			({"EPREFIX" : cross_prefix},) + \
				emerge_cmd + ("--usepkgonly", "dev-libs/A"),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/A"),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/B"),
			({"EPREFIX" : cross_prefix},) + \
				emerge_cmd + ("-C", "--quiet", "dev-libs/B"),
			({"EPREFIX" : cross_prefix},) + \
				emerge_cmd + ("-C", "--quiet", "dev-libs/A"),
			({"EPREFIX" : cross_prefix},) + \
				emerge_cmd + ("dev-libs/A",),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/A"),
			({"EPREFIX" : cross_prefix},) + \
				portageq_cmd + ("has_version", cross_prefix, "dev-libs/B"),

			# Test ROOT support
			({"ROOT": cross_root},) + emerge_cmd + ("dev-libs/B",),
			portageq_cmd + ("has_version", cross_eroot, "dev-libs/B"),
		)

		# Test binhost support if FETCHCOMMAND is available.
		binrepos_conf_file = os.path.join(os.sep, eprefix, BINREPOS_CONF_FILE)
		with open(binrepos_conf_file, 'wt') as f:
			f.write('[test-binhost]\n')
			f.write('sync-uri = {}\n'.format(binhost_uri))
		fetchcommand = portage.util.shlex_split(playground.settings['FETCHCOMMAND'])
		fetch_bin = portage.process.find_binary(fetchcommand[0])
		if fetch_bin is not None:
			test_commands = test_commands + (
				lambda: os.rename(pkgdir, binhost_dir),
				emerge_cmd + ("-e", "--getbinpkgonly", "dev-libs/A"),
				lambda: shutil.rmtree(pkgdir),
				lambda: os.rename(binhost_dir, pkgdir),
				# Remove binrepos.conf and test PORTAGE_BINHOST.
				lambda: os.unlink(binrepos_conf_file),
				lambda: os.rename(pkgdir, binhost_dir),
				({"PORTAGE_BINHOST": binhost_uri},) + \
					emerge_cmd + ("-fe", "--getbinpkgonly", "dev-libs/A"),
				lambda: shutil.rmtree(pkgdir),
				lambda: os.rename(binhost_dir, pkgdir),
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
			"PORTAGE_REPOSITORIES" : settings.repositories.config_string(),
			"PORTAGE_TMPDIR" : portage_tmpdir,
			"PORTAGE_LOGDIR" : portage_tmpdir,
			"PYTHONDONTWRITEBYTECODE" : os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
			"PYTHONPATH" : pythonpath,
			"__PORTAGE_TEST_PATH_OVERRIDE" : fake_bin,
		}

		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			env["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]

		updates_dir = os.path.join(test_repo_location, "profiles", "updates")
		dirs = [cachedir, cachedir_pregen, cross_eroot, cross_prefix,
			distdir, fake_bin, portage_tmpdir, updates_dir,
			user_config_dir, var_cache_edb]
		etc_symlinks = ("dispatch-conf.conf", "etc-update.conf")
		# Override things that may be unavailable, or may have portability
		# issues when running tests in exotic environments.
		#   prepstrip - bug #447810 (bash read builtin EINTR problem)
		true_symlinks = ["find", "prepstrip", "sed", "scanelf"]
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
			# non-empty system set keeps --depclean quiet
			with open(os.path.join(profile_path, "packages"), 'w') as f:
				f.write("*dev-libs/token-system-pkg")
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(test_repo_location, cp, "metadata.xml"), 'w') as f:
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

				if hasattr(args, '__call__'):
					args()
					continue

				if isinstance(args[0], dict):
					local_env = env.copy()
					local_env.update(args[0])
					args = args[1:]
				else:
					local_env = env

				proc = await asyncio.create_subprocess_exec(*args,
					env=local_env, stderr=None, stdout=stdout)

				if debug:
					await proc.wait()
				else:
					output, _err = await proc.communicate()
					await proc.wait()
					if proc.returncode != os.EX_OK:
						portage.writemsg(output)

				self.assertEqual(os.EX_OK, proc.returncode,
					"emerge failed with args %s" % (args,))
		finally:
			binhost_server.__exit__(None, None, None)
			playground.cleanup()
