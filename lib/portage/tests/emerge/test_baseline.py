# Copyright 2011-2021, 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""This module defines a baseline for portage's functionality.

Multiple portage commands are executed in a sequence in a playground
(see the ``baseline_command`` fixture in ``conftest.py``).

All the commands are triggered from the ``test_portage_baseline`` test.
That test is marked with::

  @pytest.mark.ft

so that it can selected with that marker, i.e.::

  pytest -m ft

``ft`` stands for *functional test*, since that's what it is, a
functional or end-to-end test, ensuring some functionality of portage.

The test also works with pytest-xdist, e.g.::

  pytest -m ft -n 8

"""

import subprocess

import pytest

import portage
from portage import os
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.process import find_binary
from portage.tests import cnf_etc_path
from portage.util import ensure_dirs
from portage.util.futures import asyncio


_METADATA_XML_FILES = (
    (
        "dev-libs/A",
        {
            "flags": "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
        },
    ),
    (
        "dev-libs/B",
        {
            "flags": "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
        },
    ),
)

_1Q_2010_UPDATE = """
slotmove =app-doc/pms-3 2 3
move dev-util/git dev-vcs/git
"""


@pytest.mark.ft
def test_portage_baseline(async_loop, playground, binhost, baseline_command):
    async_loop.run_until_complete(
        asyncio.ensure_future(
            _async_test_baseline(
                playground,
                binhost,
                baseline_command,
            ),
            loop=async_loop,
        )
    )


async def _async_test_baseline(playground, binhost, commands):
    debug = playground.debug
    settings = playground.settings
    trees = playground.trees
    eprefix = settings["EPREFIX"]

    test_repo_location = settings.repositories["test_repo"].location
    var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
    cachedir = os.path.join(var_cache_edb, "dep")
    cachedir_pregen = os.path.join(test_repo_location, "metadata", "md5-cache")

    cross_prefix = os.path.join(eprefix, "cross_prefix")
    cross_root = os.path.join(eprefix, "cross_root")
    cross_eroot = os.path.join(cross_root, eprefix.lstrip(os.sep))

    distdir = playground.distdir
    pkgdir = playground.pkgdir
    fake_bin = os.path.join(eprefix, "bin")
    portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
    profile_path = settings.profile_path
    user_config_dir = os.path.join(os.sep, eprefix, USER_CONFIG_PATH)

    path = settings.get("PATH")
    if path is not None and not path.strip():
        path = None
    if path is None:
        path = ""
    else:
        path = ":" + path
    path = fake_bin + path

    pythonpath = os.environ.get("PYTHONPATH")
    if pythonpath is not None and not pythonpath.strip():
        pythonpath = None
    if pythonpath is not None and pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
        pass
    else:
        if pythonpath is None:
            pythonpath = ""
        else:
            pythonpath = ":" + pythonpath
        pythonpath = PORTAGE_PYM_PATH + pythonpath

    env = {
        "PORTAGE_OVERRIDE_EPREFIX": eprefix,
        "CLEAN_DELAY": "0",
        "DISTDIR": distdir,
        "EMERGE_WARNING_DELAY": "0",
        "INFODIR": "",
        "INFOPATH": "",
        "PATH": path,
        "PKGDIR": pkgdir,
        "PORTAGE_INST_GID": str(os.getgid()),  # str(portage.data.portage_gid),
        "PORTAGE_INST_UID": str(os.getuid()),  # str(portage.data.portage_uid),
        "PORTAGE_PYTHON": portage._python_interpreter,
        "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
        "PORTAGE_TMPDIR": portage_tmpdir,
        "PORTAGE_LOGDIR": portage_tmpdir,
        "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
        "PYTHONPATH": pythonpath,
        "__PORTAGE_TEST_PATH_OVERRIDE": fake_bin,
    }

    if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
        env["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
            "__PORTAGE_TEST_HARDLINK_LOCKS"
        ]

    updates_dir = os.path.join(test_repo_location, "profiles", "updates")
    dirs = [
        cachedir,
        cachedir_pregen,
        cross_eroot,
        cross_prefix,
        distdir,
        fake_bin,
        portage_tmpdir,
        updates_dir,
        user_config_dir,
        var_cache_edb,
    ]
    etc_symlinks = ("dispatch-conf.conf", "etc-update.conf")
    # Override things that may be unavailable, or may have portability
    # issues when running tests in exotic environments.
    #   prepstrip - bug #447810 (bash read builtin EINTR problem)
    true_symlinks = ["find", "prepstrip", "sed", "scanelf"]
    true_binary = find_binary("true")
    assert true_binary is not None, "true command not found"

    for d in dirs:
        ensure_dirs(d)
    for x in true_symlinks:
        try:
            os.symlink(true_binary, os.path.join(fake_bin, x))
        except FileExistsError:
            pass
    for x in etc_symlinks:
        try:
            os.symlink(
                os.path.join(str(cnf_etc_path), x), os.path.join(eprefix, "etc", x)
            )
        except FileExistsError:
            pass
    with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
        f.write(b"100")
    # non-empty system set keeps --depclean quiet
    with open(os.path.join(profile_path, "packages"), "w") as f:
        f.write("*dev-libs/token-system-pkg")
    for cp, xml_data in _METADATA_XML_FILES:
        with open(os.path.join(test_repo_location, cp, "metadata.xml"), "w") as f:
            f.write(playground.metadata_xml_template % xml_data)
        with open(os.path.join(updates_dir, "1Q-2010"), "w") as f:
            f.write(_1Q_2010_UPDATE)
    if debug:
        # The subprocess inherits both stdout and stderr, for
        # debugging purposes.
        stdout = None
    else:
        # The subprocess inherits stderr so that any warnings
        # triggered by python -Wd will be visible.
        stdout = subprocess.PIPE

    for command in commands:
        if command:
            command.base_environment = env

            proc = await asyncio.create_subprocess_exec(
                *command(), env=command.env, stderr=None, stdout=stdout
            )

            if debug:
                await proc.wait()
            else:
                output, _err = await proc.communicate()
                await proc.wait()
                if proc.returncode != os.EX_OK:
                    portage.writemsg(output)

            real_command = command.name
            args = command.args
            assert (
                os.EX_OK == proc.returncode
            ), f"'{real_command}' failed with args '{args}'"
            command.check_command_result()
