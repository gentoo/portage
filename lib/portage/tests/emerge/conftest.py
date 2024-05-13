# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import shlex
from typing import Optional, Callable  # ,  Self

from portage.const import (
    SUPPORTED_GENTOO_BINPKG_FORMATS,
    BASH_BINARY,
    BINREPOS_CONF_FILE,
)
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.cache.mappings import Mapping
from portage.tests.util.test_socks5 import AsyncHTTPServer
from portage import os
from portage import shutil
from portage.util.futures import asyncio
from portage.tests import cnf_bindir, cnf_sbindir
from portage.process import find_binary
from portage.util import find_updated_config_files
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


_BASELINE_COMMAND_SEQUENCE = [
    "emerge -1 dev-libs/A -v dev-libs/B",
    "emerge with quickpkg direct",
    "env-update",
    "portageq envvar",
    "etc-update",
    "dispatch-conf",
    "emerge --version",
    "emerge --info",
    "emerge --info --verbose",
    "emerge --list-sets",
    "emerge --check-news",
    "emerge --regen/--metadata",
    "misc package operations",
    "binhost emerge",
]

PORTAGE_PYTHON = portage._python_interpreter
NOOP = lambda: ...


class PortageCommand:
    """A class that represents a baseline test case command,
    including handling of environment and one-use arguments.
    """

    command = None
    name = None

    def __init__(
        self,
        *args: tuple[str],
        env_mod: Optional[dict[str, str]] = None,
        preparation: Optional[Callable[[], None]] = None,
        post_command: Optional[Callable[[], None]] = None,
    ) -> None:
        self.args = args
        self.env_mod = env_mod
        self.preparation = preparation
        self.post_command = post_command

    def __iter__(self):
        """To be able to call a function with ``*command`` as argument."""
        yield self

    @property
    def env(self) -> dict[str, str]:
        """This property returns the environment intended to be used
        with the current test command, including possible modifications.
        """
        try:
            base_environment = self.base_environment
        except AttributeError:
            base_environment = {}
        else:
            base_environment = base_environment.copy()
        if self.env_mod:
            base_environment.update(self.env_mod)
        return base_environment

    def __call__(self):  #  -> Self:
        if self.preparation:
            self.preparation()
        try:
            tuple_command = self.command + self.args
        except TypeError:
            # In case self.command is a string:
            tuple_command = (self.command,) + self.args
        return tuple_command

    def __bool__(self) -> bool:
        return bool(self.command)

    def check_command_result(self) -> None:
        if self.post_command:
            self.post_command()


class PortageCommandSequence:
    def __init__(self, *commands):
        self.commands = commands

    def __iter__(self):
        yield from self.commands


class Emerge(PortageCommand):
    name = "emerge"
    command = (PORTAGE_PYTHON, "-b", "-Wd", os.path.join(str(cnf_bindir), name))


class Noop(PortageCommand):
    name = "No-op"


class EnvUpdate(PortageCommand):
    name = "env-update"
    command = (PORTAGE_PYTHON, "-b", "-Wd", os.path.join(str(cnf_sbindir), name))


class DispatchConf(PortageCommand):
    name = "dispatch-conf"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_sbindir), name),
    )


class Ebuild(PortageCommand):
    name = "ebuild"
    command = (PORTAGE_PYTHON, "-b", "-Wd", os.path.join(str(cnf_bindir), name))


class Egencache(PortageCommand):
    name = "egencache"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_bindir), name),
    )


class Emaint(PortageCommand):
    name = "emaint"
    command = (PORTAGE_PYTHON, "-b", "-Wd", os.path.join(str(cnf_sbindir), name))


class EtcUpdate(PortageCommand):
    name = "etc-update"
    command = (BASH_BINARY, os.path.join(str(cnf_sbindir), name))


class Fixpackages(PortageCommand):
    name = "fixpackages"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_sbindir), name),
    )


class Portageq(PortageCommand):
    name = "portageq"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_bindir), name),
    )


class Quickpkg(PortageCommand):
    name = "quickpkg"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_bindir), name),
    )


class Regenworld(PortageCommand):
    name = "regenworld"
    command = (
        PORTAGE_PYTHON,
        "-b",
        "-Wd",
        os.path.join(str(cnf_sbindir), name),
    )


def pytest_generate_tests(metafunc):
    if "baseline_command" in metafunc.fixturenames:
        metafunc.parametrize(
            "baseline_command", _BASELINE_COMMAND_SEQUENCE, indirect=True
        )


def _have_python_xml():
    try:
        __import__("xml.etree.ElementTree")
        __import__("xml.parsers.expat").parsers.expat.ExpatError
    except (AttributeError, ImportError):
        return False
    return True


def _check_foo_file(pkgdir, filename, must_exist) -> None:
    assert (
        os.path.exists(os.path.join(pkgdir, "virtual", "foo", filename)) == must_exist
    )


def _check_number_of_protected_files(must_have, eroot, config_protect) -> None:
    assert must_have == len(
        list(find_updated_config_files(eroot, shlex.split(config_protect)))
    )


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


@pytest.fixture(scope="module")
def async_loop():
    yield asyncio._wrap_loop()


@pytest.fixture(params=SUPPORTED_GENTOO_BINPKG_FORMATS, scope="function")
def playground(request, tmp_path_factory):
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
        eprefix=str(tmp_path_factory.mktemp("eprefix", numbered=True)),
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
def _generate_all_baseline_commands(playground, binhost):
    """This fixture generates all the commands that
    ``test_portage_baseline`` will use.

    But, don't use this fixture directly, instead, use the
    ``baseline_command`` fixture. That improves performance a bit due to
    pytest caching (?).

    .. note::

       To add a new command, define it in the local ``test_commands``
       dict, if not yet defined, and add its key at the correct position
       in the ``_BASELINE_COMMAND_SEQUENCE`` list.
    """
    settings = playground.settings
    eprefix = settings["EPREFIX"]
    eroot = settings["EROOT"]
    trees = playground.trees
    pkgdir = playground.pkgdir
    portdb = trees[eroot]["porttree"].dbapi
    test_repo_location = settings.repositories["test_repo"].location
    var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
    cachedir = os.path.join(var_cache_edb, "dep")
    cachedir_pregen = os.path.join(test_repo_location, "metadata", "md5-cache")

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
        parse_intermixed_command = Emerge(
            "--oneshot",
            "dev-libs/A",
            "-v",
            "dev-libs/A",
        )
    else:
        parse_intermixed_command = Noop()
    test_commands["emerge -1 dev-libs/A -v dev-libs/B"] = parse_intermixed_command

    quickpkg_direct_seq = [
        Emerge(
            "--usepkgonly",
            "--root",
            cross_root,
            "--quickpkg-direct=y",
            "--quickpkg-direct-root",
            "/",
            "dev-libs/A",
        ),
        # v needs ^
        Emerge(
            "--usepkgonly",
            "--quickpkg-direct=y",
            "--quickpkg-direct-root",
            cross_root,
            "dev-libs/A",
        ),
    ]
    test_commands["emerge with quickpkg direct"] = PortageCommandSequence(
        *quickpkg_direct_seq
    )

    test_commands["env-update"] = EnvUpdate()
    test_commands["portageq envvar"] = Portageq(
        "envvar",
        "-v",
        "CONFIG_PROTECT",
        "EROOT",
        "PORTAGE_CONFIGROOT",
        "PORTAGE_TMPDIR",
        "USERLAND",
    )
    test_commands["etc-update"] = EtcUpdate()
    test_commands["dispatch-conf"] = DispatchConf()
    test_commands["emerge --version"] = Emerge("--version")
    test_commands["emerge --info"] = Emerge("--info")
    test_commands["emerge --info --verbose"] = Emerge("--info", "--verbose")
    test_commands["emerge --list-sets"] = Emerge("--list-sets")
    test_commands["emerge --check-news"] = Emerge("--check-news")

    def _rm_cachedir():
        shutil.rmtree(cachedir)

    def _rm_cachedir_and_pregen():
        _rm_cachedir()
        shutil.rmtree(cachedir_pregen)

    regen_seq = [
        Emerge("--regen", preparation=_rm_cachedir_and_pregen),
        Emerge(
            "--regen",
            env_mod={"FEATURES": "metadata-transfer"},
            preparation=_rm_cachedir,
        ),
        Egencache(
            "--repo",
            "test_repo",
            "--repositories-configuration",
            playground.settings.repositories.config_string(),
            "--update",
            *egencache_extra_args,
            preparation=_rm_cachedir,
        ),
        Emerge("--metadata", env_mod={"FEATURES": "metadata-transfer"}),
        Emerge(
            "--metadata",
            env_mod={"FEATURES": "metadata-transfer"},
            preparation=_rm_cachedir,
        ),
        Emerge("--metadata"),
        Emerge("--oneshot", "virtual/foo", preparation=_rm_cachedir),
        Emerge(
            "--unmerge",
            "virtual/foo",
            env_mod={"FEATURES": "unmerge-backup"},
            preparation=lambda: _check_foo_file(pkgdir, foo_filename, must_exist=False),
        ),
        Emerge(
            "--pretend",
            "dev-libs/A",
            preparation=lambda: _check_foo_file(pkgdir, foo_filename, must_exist=True),
        ),
    ]
    test_commands["emerge --regen/--metadata"] = PortageCommandSequence(*regen_seq)

    abcd_seq = [
        Ebuild(
            test_ebuild,
            "manifest",
            "clean",
            "package",
            "merge",
        ),
        Emerge(
            "--pretend",
            "--tree",
            "--complete-graph",
            "dev-libs/A",
        ),
        Emerge("-p", "dev-libs/B"),
        Emerge(
            "-p",
            "--newrepo",
            "dev-libs/B",
        ),
        Emerge("-B", "dev-libs/B"),
        Emerge(
            "--oneshot",
            "--usepkg",
            "dev-libs/B",
        ),
        # trigger clean prior to pkg_pretend as in bug #390711
        Ebuild(test_ebuild, "unpack"),
        Emerge("--oneshot", "dev-libs/A"),
        Emerge("--noreplace", "dev-libs/A"),
        Emerge(
            "--config",
            "dev-libs/A",
        ),
        Emerge(
            "--info",
            "dev-libs/A",
            "dev-libs/B",
        ),
        Emerge(
            "--pretend",
            "--depclean",
            "--verbose",
            "dev-libs/B",
        ),
        Emerge("--pretend", "--depclean"),
        Emerge(
            "--depclean",
        ),
        # Test bug #523684, where a file renamed or removed by the
        # admin forces replacement files to be merged with config
        # protection.
        Quickpkg(
            "--include-config",
            "y",
            "dev-libs/A",
            post_command=lambda: _check_number_of_protected_files(
                0, eroot, settings["CONFIG_PROTECT"]
            ),
        ),
        Emerge("--noreplace", "dev-libs/A"),
        Emerge(
            "--usepkgonly",
            "dev-libs/A",
            preparation=lambda: os.unlink(os.path.join(eprefix, "etc", "A-0")),
            post_command=lambda: _check_number_of_protected_files(
                1, eroot, settings["CONFIG_PROTECT"]
            ),
        ),
        Emaint("--check", "all"),
        Emaint("--fix", "all"),
        Fixpackages(),
        Regenworld(),
        Portageq(
            "match",
            eroot,
            "dev-libs/A",
        ),
        Portageq(
            "best_visible",
            eroot,
            "dev-libs/A",
        ),
        Portageq(
            "best_visible",
            eroot,
            "binary",
            "dev-libs/A",
        ),
        Portageq(
            "contents",
            eroot,
            "dev-libs/A-1",
        ),
        Portageq(
            "metadata",
            eroot,
            "ebuild",
            "dev-libs/A-1",
            "EAPI",
            "IUSE",
            "RDEPEND",
        ),
        Portageq(
            "metadata",
            eroot,
            "binary",
            "dev-libs/A-1",
            "EAPI",
            "USE",
            "RDEPEND",
        ),
        Portageq(
            "metadata",
            eroot,
            "installed",
            "dev-libs/A-1",
            "EAPI",
            "USE",
            "RDEPEND",
        ),
        Portageq(
            "owners",
            eroot,
            eroot + "usr",
        ),
        Emerge("-p", eroot + "usr"),
        Emerge(
            "-p",
            "--unmerge",
            "-q",
            eroot + "usr",
        ),
        Emerge(
            "--unmerge",
            "--quiet",
            "dev-libs/A",
        ),
        Emerge(
            "-C",
            "--quiet",
            "dev-libs/B",
        ),
        # autounmask:
        # If EMERGE_DEFAULT_OPTS contains --autounmask=n, then --autounmask
        # must be specified with --autounmask-continue.
        Emerge(
            "--autounmask",
            "--autounmask-continue",
            "dev-libs/C",
            env_mod={"EMERGE_DEFAULT_OPTS": "--autounmask=n"},
        ),
        # Verify that the above --autounmask-continue command caused
        # USE=flag to be applied correctly to dev-libs/D.
        Portageq(
            "match",
            eroot,
            "dev-libs/D[flag]",
        ),
    ]
    test_commands["misc package operations"] = PortageCommandSequence(*abcd_seq)

    cross_prefix_seq = [
        # Test cross-prefix usage, including chpathtool for binpkgs.
        # EAPI 7
        Emerge("dev-libs/C", env_mod={"EPREFIX": cross_prefix}),
        Portageq(
            "has_version", cross_prefix, "dev-libs/C", env_mod={"EPREFIX": cross_prefix}
        ),
        Portageq(
            "has_version", cross_prefix, "dev-libs/D", env_mod={"EPREFIX": cross_prefix}
        ),
        Emerge("dev-libs/D", env_mod={"ROOT": cross_root}),
        Portageq(
            "has_version",
            cross_eroot,
            "dev-libs/D",
        ),
        # EAPI 5
        Emerge("--usepkgonly", "dev-libs/A", env_mod={"EPREFIX": cross_prefix}),
        Portageq(
            "has_version", cross_prefix, "dev-libs/A", env_mod={"EPREFIX": cross_prefix}
        ),
        Portageq(
            "has_version", cross_prefix, "dev-libs/B", env_mod={"EPREFIX": cross_prefix}
        ),
        Emerge("-C", "--quiet", "dev-libs/B", env_mod={"EPREFIX": cross_prefix}),
        Emerge("-C", "--quiet", "dev-libs/A", env_mod={"EPREFIX": cross_prefix}),
        Emerge("dev-libs/A", env_mod={"EPREFIX": cross_prefix}),
        # Test ROOT support
        Emerge("dev-libs/B", env_mod={"ROOT": cross_root}),
        Portageq(
            "has_version",
            cross_eroot,
            "dev-libs/B",
        ),
    ]
    test_commands["misc operations with eprefix"] = PortageCommandSequence(
        *cross_prefix_seq
    )

    # Test binhost support if FETCHCOMMAND is available.
    binrepos_conf_file = os.path.join(os.sep, eprefix, BINREPOS_CONF_FILE)
    binhost_uri = binhost["uri"]
    binhost_dir = binhost["dir"]
    with open(binrepos_conf_file, "w") as f:
        f.write("[test-binhost]\n")
        f.write(f"sync-uri = {binhost_uri}\n")
    fetchcommand = shlex.split(settings["FETCHCOMMAND"])
    fetch_bin = portage.process.find_binary(fetchcommand[0])

    if fetch_bin is None:
        test_commands["binhost emerge"] = Noop()
    else:
        # The next emerge has been added to split this test from the rest:
        make_package = Emerge("-e", "--buildpkg", "dev-libs/A")
        getbinpkgonly = Emerge(
            "-e",
            "--getbinpkgonly",
            "dev-libs/A",
            preparation=lambda: os.rename(pkgdir, binhost_dir),
        )

        # Remove binrepos.conf and test PORTAGE_BINHOST.
        def _rm_pkgdir_and_rm_binrepos_conf_file():
            shutil.rmtree(pkgdir)
            os.unlink(binrepos_conf_file)

        getbinpkgonly_fetchonly = Emerge(
            "-fe",
            "--getbinpkgonly",
            "dev-libs/A",
            env_mod={"PORTAGE_BINHOST": binhost_uri},
            preparation=_rm_pkgdir_and_rm_binrepos_conf_file,
        )

        # Test bug 920537 binrepos.conf with local file src-uri.
        def _rm_pkgdir_and_create_binrepos_conf_with_file_uri():
            shutil.rmtree(pkgdir)
            with open(binrepos_conf_file, "w") as f:
                f.write("[test-binhost]\n")
                f.write(f"sync-uri = file://{binhost_dir}\n")

        getbinpkgonly_file_uri = Emerge(
            "-fe",
            "--getbinpkgonly",
            "dev-libs/A",
            preparation=_rm_pkgdir_and_create_binrepos_conf_with_file_uri,
        )

        fetch_sequence = PortageCommandSequence(
            make_package, getbinpkgonly, getbinpkgonly_fetchonly, getbinpkgonly_file_uri
        )
        test_commands["binhost emerge"] = fetch_sequence
    yield test_commands


@pytest.fixture()
def baseline_command(request, _generate_all_baseline_commands):
    """A fixture that provides the commands to perform a baseline
    functional test of portage. It uses another fixture, namely
    ``_generate_all_baseline_commands``.
    Pytest caches the fixtures and there is a little performance
    improvement if the commands are generated only once..
    """
    return _generate_all_baseline_commands[request.param]
