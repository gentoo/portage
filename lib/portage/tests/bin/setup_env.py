# setup_env.py -- Make sure bin subdir has sane env for testing
# Copyright 2007-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

import portage
from portage import os_unicode_fs
from portage import shutil_unicode_fs
from portage.const import PORTAGE_BIN_PATH
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.process import spawn

bindir = PORTAGE_BIN_PATH
basedir = None
env = None


def binTestsCleanup():
    global basedir
    if basedir is None:
        return
    if os_unicode_fs.access(basedir, os_unicode_fs.W_OK):
        shutil_unicode_fs.rmtree(basedir)
        basedir = None


def binTestsInit():
    binTestsCleanup()
    global basedir, env
    basedir = tempfile.mkdtemp()
    env = {}
    env["EAPI"] = "0"
    env["D"] = os_unicode_fs.path.join(basedir, "image")
    env["T"] = os_unicode_fs.path.join(basedir, "temp")
    env["S"] = os_unicode_fs.path.join(basedir, "workdir")
    env["PF"] = "portage-tests-0.09-r1"
    env["PATH"] = bindir + ":" + os_unicode_fs.environ["PATH"]
    env["PORTAGE_BIN_PATH"] = bindir
    env["PORTAGE_PYM_PATH"] = PORTAGE_PYM_PATH
    env["PORTAGE_PYTHON"] = portage._python_interpreter
    env["PORTAGE_INST_UID"] = str(os_unicode_fs.getuid())
    env["PORTAGE_INST_GID"] = str(os_unicode_fs.getgid())
    env["DESTTREE"] = "/usr"
    os_unicode_fs.mkdir(env["D"])
    os_unicode_fs.mkdir(env["T"])
    os_unicode_fs.mkdir(env["S"])


class BinTestCase(TestCase):
    def init(self):
        binTestsInit()

    def cleanup(self):
        binTestsCleanup()


def _exists_in_D(path):
    # Note: do not use os_unicode_fs.path.join() here, we assume D to end in /
    return os_unicode_fs.access(env["D"] + path, os_unicode_fs.W_OK)


def exists_in_D(path):
    if not _exists_in_D(path):
        raise TestCase.failureException


def xexists_in_D(path):
    if _exists_in_D(path):
        raise TestCase.failureException


def portage_func(func, args, exit_status=0):
    # we don't care about the output of the programs,
    # just their exit value and the state of $D
    global env
    f = open("/dev/null", "wb")
    fd_pipes = {0: 0, 1: f.fileno(), 2: f.fileno()}

    def pre_exec():
        os_unicode_fs.chdir(env["S"])

    spawn([func] + args.split(), env=env, fd_pipes=fd_pipes, pre_exec=pre_exec)
    f.close()


def create_portage_wrapper(f):
    def derived_func(*args):
        newargs = list(args)
        newargs.insert(0, f)
        return portage_func(*newargs)

    return derived_func


for f in os_unicode_fs.listdir(os_unicode_fs.path.join(bindir, "ebuild-helpers")):
    if (
        f.startswith("do")
        or f.startswith("new")
        or f.startswith("prep")
        or f in ("fowners", "fperms")
    ):
        globals()[f] = create_portage_wrapper(
            os_unicode_fs.path.join(bindir, "ebuild-helpers", f)
        )
