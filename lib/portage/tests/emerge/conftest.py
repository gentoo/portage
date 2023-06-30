# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse

from portage.const import (
    SUPPORTED_GENTOO_BINPKG_FORMATS,
    BASH_BINARY,
    BINREPOS_CONF_FILE,
)
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.cache.mappings import Mapping
from portage.tests.util.test_socks5 import AsyncHTTPServer
from portage import os
from portage.util.futures import asyncio
from portage.tests import cnf_bindir, cnf_sbindir
from portage.process import find_binary
import portage

import pytest


_INSTALL_SOMETHING = """
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

_AVAILABLE_EBUILDS = {
    "dev-libs/A-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "MISC_CONTENT": _INSTALL_SOMETHING,
        "RDEPEND": "flag? ( dev-libs/B[flag] )",
    },
    "dev-libs/B-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "dev-libs/C-1": {
        "EAPI": "7",
        "KEYWORDS": "~x86",
        "RDEPEND": "dev-libs/D[flag]",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "dev-libs/D-1": {
        "EAPI": "7",
        "KEYWORDS": "~x86",
        "IUSE": "flag",
        "MISC_CONTENT": _INSTALL_SOMETHING,
    },
    "virtual/foo-0": {
        "EAPI": "5",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
    },
}

_INSTALLED_EBUILDS = {
    "dev-libs/A-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "RDEPEND": "flag? ( dev-libs/B[flag] )",
        "USE": "flag",
    },
    "dev-libs/B-1": {
        "EAPI": "5",
        "IUSE": "+flag",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "USE": "flag",
    },
    "dev-libs/depclean-me-1": {
        "EAPI": "5",
        "IUSE": "",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "USE": "",
    },
    "app-misc/depclean-me-1": {
        "EAPI": "5",
        "IUSE": "",
        "KEYWORDS": "x86",
        "LICENSE": "GPL-2",
        "RDEPEND": "dev-libs/depclean-me",
        "USE": "",
    },
}


_TEST_COMMAND_NAMES = [
    "emerge_w_parse_intermixed_args",
    "emerge --root --quickpkg-direct-root",
    "emerge --quickpkg-direct-root",
    "env-update",
    "portageq envvar",
    "etc-update",
    "dispatch-conf",
    "emerge --version",
    "emerge --info",
    "emerge --info --verbose",
    "emerge --list-sets",
    "emerge --check-news",
    "rm -rf {cachedir}",
    "rm -rf {cachedir_pregen}",
    "emerge --regen",
    "rm -rf {cachedir} (2)",
    "FEATURES=metadata-transfer emerge --regen",
    "rm -rf {cachedir} (3)",
    "FEATURES=metadata-transfer emerge --regen (2)",
    "rm -rf {cachedir} (4)",
    "egencache --update",
    "FEATURES=metadata-transfer emerge --metadata",
    "rm -rf {cachedir} (5)",
    "FEATURES=metadata-transfer emerge --metadata (2)",
    "emerge --metadata",
    "rm -rf {cachedir} (6)",
    "emerge --oneshot virtual/foo",
]


def pytest_generate_tests(metafunc):
    if "simple_command" in metafunc.fixturenames:
        metafunc.parametrize("simple_command", _TEST_COMMAND_NAMES, indirect=True)


def _have_python_xml():
    try:
        __import__("xml.etree.ElementTree")
        __import__("xml.parsers.expat").parsers.expat.ExpatError
    except (AttributeError, ImportError):
        return False
    return True


class BinhostContentMap(Mapping):
    def __init__(self, remote_path, local_path):
        self._remote_path = remote_path
        self._local_path = local_path

    def __getitem__(self, request_path):
        safe_path = os.path.normpath(request_path)
        if not safe_path.startswith(self._remote_path + "/"):
            raise KeyError(request_path)
        local_path = os.path.join(
            self._local_path, safe_path[len(self._remote_path) + 1 :]
        )
        try:
            with open(local_path, "rb") as f:
                return f.read()
        except OSError:
            raise KeyError(request_path)


@pytest.fixture()
def async_loop():
    yield asyncio._wrap_loop()


@pytest.fixture(params=SUPPORTED_GENTOO_BINPKG_FORMATS)
def playground(request):
    """Fixture that provides instances of ``ResolverPlayground``
    each one with one supported value for ``BINPKG_FORMAT``."""
    binpkg_format = request.param
    playground = ResolverPlayground(
        ebuilds=_AVAILABLE_EBUILDS,
        installed=_INSTALLED_EBUILDS,
        debug=False,
        user_config={
            "make.conf": (f'BINPKG_FORMAT="{binpkg_format}"',),
        },
    )
    yield playground
    playground.cleanup()


@pytest.fixture()
def binhost(playground, async_loop):
    settings = playground.settings
    eprefix = settings["EPREFIX"]
    binhost_dir = os.path.join(eprefix, "binhost")
    binhost_address = "127.0.0.1"
    binhost_remote_path = "/binhost"
    binhost_server = AsyncHTTPServer(
        binhost_address, BinhostContentMap(binhost_remote_path, binhost_dir), async_loop
    ).__enter__()
    binhost_uri = "http://{address}:{port}{path}".format(
        address=binhost_address,
        port=binhost_server.server_port,
        path=binhost_remote_path,
    )
    yield {"server": binhost_server, "uri": binhost_uri, "dir": binhost_dir}
    binhost_server.__exit__(None, None, None)


@pytest.fixture()
def simple_command(playground, binhost, request):
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
    dispatch_conf_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_sbindir, "dispatch-conf"),
    )
    ebuild_cmd = (portage_python, "-b", "-Wd", os.path.join(cnf_bindir, "ebuild"))
    egencache_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_bindir, "egencache"),
        "--repo",
        "test_repo",
        "--repositories-configuration",
        settings.repositories.config_string(),
    )
    emerge_cmd = (portage_python, "-b", "-Wd", os.path.join(cnf_bindir, "emerge"))
    emaint_cmd = (portage_python, "-b", "-Wd", os.path.join(cnf_sbindir, "emaint"))
    env_update_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_sbindir, "env-update"),
    )
    etc_update_cmd = (BASH_BINARY, os.path.join(cnf_sbindir, "etc-update"))
    fixpackages_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_sbindir, "fixpackages"),
    )
    portageq_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_bindir, "portageq"),
    )
    quickpkg_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_bindir, "quickpkg"),
    )
    regenworld_cmd = (
        portage_python,
        "-b",
        "-Wd",
        os.path.join(cnf_sbindir, "regenworld"),
    )

    rm_binary = find_binary("rm")
    assert rm_binary is not None, "rm command not found"
    rm_cmd = (rm_binary,)

    egencache_extra_args = []
    if _have_python_xml():
        egencache_extra_args.append("--update-use-local-desc")

    test_ebuild = portdb.findname("dev-libs/A-1")
    assert test_ebuild is not None

    cross_prefix = os.path.join(eprefix, "cross_prefix")
    cross_root = os.path.join(eprefix, "cross_root")
    cross_eroot = os.path.join(cross_root, eprefix.lstrip(os.sep))

    binpkg_format = settings.get("BINPKG_FORMAT", SUPPORTED_GENTOO_BINPKG_FORMATS[0])
    assert binpkg_format in ("xpak", "gpkg")
    if binpkg_format == "xpak":
        foo_filename = "foo-0-1.xpak"
    elif binpkg_format == "gpkg":
        foo_filename = "foo-0-1.gpkg.tar"

    test_commands = {}

    if hasattr(argparse.ArgumentParser, "parse_intermixed_args"):
        test_commands["emerge_w_parse_intermixed_args"] = emerge_cmd + (
            "--oneshot",
            "dev-libs/A",
            "-v",
            "dev-libs/A",
        )

    test_commands["emerge --root --quickpkg-direct-root"] = emerge_cmd + (
        "--usepkgonly",
        "--root",
        cross_root,
        "--quickpkg-direct=y",
        "--quickpkg-direct-root",
        "/",
        "dev-libs/A",
    )
    test_commands["emerge --quickpkg-direct-root"] = emerge_cmd + (
        "--usepkgonly",
        "--quickpkg-direct=y",
        "--quickpkg-direct-root",
        cross_root,
        "dev-libs/A",
    )
    test_commands["env-update"] = env_update_cmd
    test_commands["portageq envvar"] = portageq_cmd + (
        "envvar",
        "-v",
        "CONFIG_PROTECT",
        "EROOT",
        "PORTAGE_CONFIGROOT",
        "PORTAGE_TMPDIR",
        "USERLAND",
    )
    test_commands["etc-update"] = etc_update_cmd
    test_commands["dispatch-conf"] = dispatch_conf_cmd
    test_commands["emerge --version"] = emerge_cmd + ("--version",)
    test_commands["emerge --info"] = emerge_cmd + ("--info",)
    test_commands["emerge --info --verbose"] = emerge_cmd + ("--info", "--verbose")
    test_commands["emerge --list-sets"] = emerge_cmd + ("--list-sets",)
    test_commands["emerge --check-news"] = emerge_cmd + ("--check-news",)
    test_commands["rm -rf {cachedir}"] = rm_cmd + ("-rf", cachedir)
    test_commands["rm -rf {cachedir_pregen}"] = rm_cmd + ("-rf", cachedir_pregen)
    test_commands["emerge --regen"] = emerge_cmd + ("--regen",)
    test_commands["rm -rf {cachedir} (2)"] = rm_cmd + ("-rf", cachedir)
    test_commands["FEATURES=metadata-transfer emerge --regen"] = (
        ({"FEATURES": "metadata-transfer"},) + emerge_cmd + ("--regen",)
    )
    test_commands["rm -rf {cachedir} (3)"] = rm_cmd + ("-rf", cachedir)
    test_commands["FEATURES=metadata-transfer emerge --regen (2)"] = (
        ({"FEATURES": "metadata-transfer"},) + emerge_cmd + ("--regen",)
    )
    test_commands["rm -rf {cachedir} (4)"] = rm_cmd + ("-rf", cachedir)
    test_commands["egencache --update"] = (
        egencache_cmd + ("--update",) + tuple(egencache_extra_args)
    )
    test_commands["FEATURES=metadata-transfer emerge --metadata"] = (
        ({"FEATURES": "metadata-transfer"},) + emerge_cmd + ("--metadata",)
    )
    test_commands["rm -rf {cachedir} (5)"] = rm_cmd + ("-rf", cachedir)
    test_commands["FEATURES=metadata-transfer emerge --metadata (2)"] = (
        ({"FEATURES": "metadata-transfer"},) + emerge_cmd + ("--metadata",)
    )
    test_commands["emerge --metadata"] = emerge_cmd + ("--metadata",)
    test_commands["rm -rf {cachedir} (6)"] = rm_cmd + ("-rf", cachedir)
    test_commands["emerge --oneshot virtual/foo"] = emerge_cmd + (
        "--oneshot",
        "virtual/foo",
    )
    # test_commands["virtual/foo exists"] = (
    #     lambda: self.assertFalse(
    #         os.path.exists(os.path.join(pkgdir, "virtual", "foo", foo_filename))
    #     )
    # )
    #     ({"FEATURES": "unmerge-backup"},) + emerge_cmd + ("--unmerge", "virtual/foo"),
    #     lambda: self.assertTrue(
    #         os.path.exists(os.path.join(pkgdir, "virtual", "foo", foo_filename))
    #     ),
    #     emerge_cmd + ("--pretend", "dev-libs/A"),
    #     ebuild_cmd + (test_ebuild, "manifest", "clean", "package", "merge"),
    #     emerge_cmd + ("--pretend", "--tree", "--complete-graph", "dev-libs/A"),
    #     emerge_cmd + ("-p", "dev-libs/B"),
    #     emerge_cmd + ("-p", "--newrepo", "dev-libs/B"),
    #     emerge_cmd
    #     + (
    #         "-B",
    #         "dev-libs/B",
    #     ),
    #     emerge_cmd
    #     + (
    #         "--oneshot",
    #         "--usepkg",
    #         "dev-libs/B",
    #     ),
    #     # trigger clean prior to pkg_pretend as in bug #390711
    #     ebuild_cmd + (test_ebuild, "unpack"),
    #     emerge_cmd
    #     + (
    #         "--oneshot",
    #         "dev-libs/A",
    #     ),
    #     emerge_cmd
    #     + (
    #         "--noreplace",
    #         "dev-libs/A",
    #     ),
    #     emerge_cmd
    #     + (
    #         "--config",
    #         "dev-libs/A",
    #     ),
    #     emerge_cmd + ("--info", "dev-libs/A", "dev-libs/B"),
    #     emerge_cmd + ("--pretend", "--depclean", "--verbose", "dev-libs/B"),
    #     emerge_cmd
    #     + (
    #         "--pretend",
    #         "--depclean",
    #     ),
    #     emerge_cmd + ("--depclean",),
    #     quickpkg_cmd
    #     + (
    #         "--include-config",
    #         "y",
    #         "dev-libs/A",
    #     ),
    #     # Test bug #523684, where a file renamed or removed by the
    #     # admin forces replacement files to be merged with config
    #     # protection.
    #     lambda: self.assertEqual(
    #         0,
    #         len(
    #             list(
    #                 find_updated_config_files(
    #                     eroot, shlex_split(settings["CONFIG_PROTECT"])
    #                 )
    #             )
    #         ),
    #     ),
    #     lambda: os.unlink(os.path.join(eprefix, "etc", "A-0")),
    #     emerge_cmd + ("--usepkgonly", "dev-libs/A"),
    #     lambda: self.assertEqual(
    #         1,
    #         len(
    #             list(
    #                 find_updated_config_files(
    #                     eroot, shlex_split(settings["CONFIG_PROTECT"])
    #                 )
    #             )
    #         ),
    #     ),
    #     emaint_cmd + ("--check", "all"),
    #     emaint_cmd + ("--fix", "all"),
    #     fixpackages_cmd,
    #     regenworld_cmd,
    #     portageq_cmd + ("match", eroot, "dev-libs/A"),
    #     portageq_cmd + ("best_visible", eroot, "dev-libs/A"),
    #     portageq_cmd + ("best_visible", eroot, "binary", "dev-libs/A"),
    #     portageq_cmd + ("contents", eroot, "dev-libs/A-1"),
    #     portageq_cmd
    #     + ("metadata", eroot, "ebuild", "dev-libs/A-1", "EAPI", "IUSE", "RDEPEND"),
    #     portageq_cmd
    #     + ("metadata", eroot, "binary", "dev-libs/A-1", "EAPI", "USE", "RDEPEND"),
    #     portageq_cmd
    #     + (
    #         "metadata",
    #         eroot,
    #         "installed",
    #         "dev-libs/A-1",
    #         "EAPI",
    #         "USE",
    #         "RDEPEND",
    #     ),
    #     portageq_cmd + ("owners", eroot, eroot + "usr"),
    #     emerge_cmd + ("-p", eroot + "usr"),
    #     emerge_cmd + ("-p", "--unmerge", "-q", eroot + "usr"),
    #     emerge_cmd + ("--unmerge", "--quiet", "dev-libs/A"),
    #     emerge_cmd + ("-C", "--quiet", "dev-libs/B"),
    #     # If EMERGE_DEFAULT_OPTS contains --autounmask=n, then --autounmask
    #     # must be specified with --autounmask-continue.
    #     ({"EMERGE_DEFAULT_OPTS": "--autounmask=n"},)
    #     + emerge_cmd
    #     + (
    #         "--autounmask",
    #         "--autounmask-continue",
    #         "dev-libs/C",
    #     ),
    #     # Verify that the above --autounmask-continue command caused
    #     # USE=flag to be applied correctly to dev-libs/D.
    #     portageq_cmd + ("match", eroot, "dev-libs/D[flag]"),
    #     # Test cross-prefix usage, including chpathtool for binpkgs.
    #     # EAPI 7
    #     ({"EPREFIX": cross_prefix},) + emerge_cmd + ("dev-libs/C",),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/C"),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/D"),
    #     ({"ROOT": cross_root},) + emerge_cmd + ("dev-libs/D",),
    #     portageq_cmd + ("has_version", cross_eroot, "dev-libs/D"),
    #     # EAPI 5
    #     ({"EPREFIX": cross_prefix},) + emerge_cmd + ("--usepkgonly", "dev-libs/A"),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/A"),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/B"),
    #     ({"EPREFIX": cross_prefix},) + emerge_cmd + ("-C", "--quiet", "dev-libs/B"),
    #     ({"EPREFIX": cross_prefix},) + emerge_cmd + ("-C", "--quiet", "dev-libs/A"),
    #     ({"EPREFIX": cross_prefix},) + emerge_cmd + ("dev-libs/A",),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/A"),
    #     ({"EPREFIX": cross_prefix},)
    #     + portageq_cmd
    #     + ("has_version", cross_prefix, "dev-libs/B"),
    #     # Test ROOT support
    #     ({"ROOT": cross_root},) + emerge_cmd + ("dev-libs/B",),
    #     portageq_cmd + ("has_version", cross_eroot, "dev-libs/B"),
    # )

    # # Test binhost support if FETCHCOMMAND is available.
    # binrepos_conf_file = os.path.join(os.sep, eprefix, BINREPOS_CONF_FILE)
    # binhost_uri = binhost["uri"]
    # binhost_dir = binhost["dir"]
    # with open(binrepos_conf_file, "w") as f:
    #     f.write("[test-binhost]\n")
    #     f.write(f"sync-uri = {binhost_uri}\n")
    # fetchcommand = portage.util.shlex_split(settings["FETCHCOMMAND"])
    # fetch_bin = portage.process.find_binary(fetchcommand[0])
    # if fetch_bin is not None:
    #     test_commands = test_commands + (
    #         lambda: os.rename(pkgdir, binhost_dir),
    #         emerge_cmd + ("-e", "--getbinpkgonly", "dev-libs/A"),
    #         lambda: shutil.rmtree(pkgdir),
    #         lambda: os.rename(binhost_dir, pkgdir),
    #         # Remove binrepos.conf and test PORTAGE_BINHOST.
    #         lambda: os.unlink(binrepos_conf_file),
    #         lambda: os.rename(pkgdir, binhost_dir),
    #         ({"PORTAGE_BINHOST": binhost_uri},)
    #         + emerge_cmd
    #         + ("-fe", "--getbinpkgonly", "dev-libs/A"),
    #         lambda: shutil.rmtree(pkgdir),
    #         lambda: os.rename(binhost_dir, pkgdir),
    #     )
    return test_commands[request.param]
