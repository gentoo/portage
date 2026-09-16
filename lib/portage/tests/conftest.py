#!/usr/bin/env python
# Copyright 2006-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import grp
import importlib
import math
import os
import os.path as osp
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile

import pytest

import portage
from portage.const import PORTAGE_BIN_PATH
from portage.util._eventloop.global_event_loop import global_event_loop


def debug_signal(signum, frame):
    import pdb

    pdb.set_trace()


signal.signal(signal.SIGUSR1, debug_signal)


_GOLDEN_RATIO_CONJUGATE = (math.sqrt(5) - 1) / 2


def pytest_collection_modifyitems(config, items):
    """
    Under pytest-xdist, spread the tests of each module evenly across the
    collection, so that the expensive tests, which are clustered in a few
    modules, do not end up queued back to back on one worker.
    """
    if not hasattr(config, "workerinput"):
        return

    by_module = {}
    for item in items:
        by_module.setdefault(item.nodeid.partition("::")[0], []).append(item)

    keyed = []
    for m, module_items in enumerate(by_module.values()):
        # Offset modules by multiples of the golden ratio, so that those
        # with only a few tests do not all land at the same positions.
        offset = (m * _GOLDEN_RATIO_CONJUGATE) % 1.0
        n = len(module_items)
        for i, item in enumerate(module_items):
            keyed.append(((i + offset) / n, item))

    # Every worker must compute the same order, as xdist requires.
    keyed.sort(key=lambda k: k[0])
    items[:] = [item for _, item in keyed]


@pytest.fixture(autouse=True, scope="session")
def prepare_environment():
    # Pretend that the current user's uid/gid are the 'portage' uid/gid,
    # so things go smoothly regardless of the current user and global
    # user/group configuration.
    os.environ["PORTAGE_USERNAME"] = pwd.getpwuid(os.getuid()).pw_name
    os.environ["PORTAGE_GRPNAME"] = grp.getgrgid(os.getgid()).gr_name
    if "portage.data" in sys.modules:
        importlib.reload(portage.data)

    # Insert our parent dir so we can do shiny import "tests"
    # This line courtesy of Marienz and Pkgcore ;)
    sys.path.insert(0, osp.dirname(osp.dirname(osp.dirname(osp.realpath(__file__)))))

    portage._internal_caller = True

    # Ensure that we don't instantiate portage.settings, so that tests should
    # work the same regardless of global configuration file state/existence.
    portage._disable_legacy_globals()

    if portage.util.no_color(os.environ):
        portage.output.nocolor()

    # import portage.tests as tests

    path = os.environ.get("PATH", "").split(":")
    path = [x for x in path if x]

    insert_bin_path = True
    try:
        insert_bin_path = not path or not os.path.samefile(path[0], PORTAGE_BIN_PATH)
    except OSError:
        pass

    if insert_bin_path:
        path.insert(0, PORTAGE_BIN_PATH)
        os.environ["PATH"] = ":".join(path)

    # Copy GnuPG test keys to temporary directory
    gpg_path = tempfile.mkdtemp(prefix="gpg_")

    try:
        shutil.copytree(
            os.path.join(os.path.dirname(os.path.realpath(__file__)), ".gnupg"),
            gpg_path,
            dirs_exist_ok=True,
        )

        os.chmod(gpg_path, 0o700)
        os.environ["PORTAGE_GNUPGHOME"] = gpg_path

        yield

    finally:
        global_event_loop().close()
        # Signing spawns a gpg-agent and scdaemon which daemonize, so they
        # outlive the test session unless they are shut down here.
        try:
            subprocess.run(
                ["gpgconf", "--homedir", gpg_path, "--kill", "all"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            # No gpgconf, so no agent can have been started either.
            pass
        shutil.rmtree(gpg_path, ignore_errors=True)


# if __name__ == "__main__":
#     try:
#         sys.exit(tests.main())
#     finally:
#         global_event_loop().close()
#         shutil.rmtree(gpg_path, ignore_errors=True)
