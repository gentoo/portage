# Copyright 2015-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Function to check whether the current used LC_CTYPE handles case
transformations of ASCII characters in a way compatible with the POSIX
locale.
"""

import locale
import logging
import multiprocessing
import sys
import textwrap
import traceback

import portage
from portage.util import _unicode_decode, writemsg_level
from portage.util._ctypes import load_libc
from portage.util.futures import asyncio


locale_categories = (
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_MONETARY",
    "LC_MESSAGES",
    "LC_NUMERIC",
    "LC_TIME",
    # GNU extensions
    "LC_ADDRESS",
    "LC_IDENTIFICATION",
    "LC_MEASUREMENT",
    "LC_NAME",
    "LC_PAPER",
    "LC_TELEPHONE",
)

_check_locale_cache = {}


def _check_locale(silent):
    """
    The inner locale check function.
    """
    (libc, _) = load_libc()
    if libc is None:
        return None

    lc = list(range(ord("a"), ord("z") + 1))
    uc = list(range(ord("A"), ord("Z") + 1))
    rlc = [libc.tolower(c) for c in uc]
    ruc = [libc.toupper(c) for c in lc]

    if lc != rlc or uc != ruc:
        if silent:
            return False

        msg = (
            "WARNING: The LC_CTYPE variable is set to a locale "
            + "that specifies transformation between lowercase "
            + "and uppercase ASCII characters that is different than "
            + "the one specified by POSIX locale. This can break "
            + "ebuilds and cause issues in programs that rely on "
            + "the common character conversion scheme. "
            + "Please consider enabling another locale (such as "
            + "en_US.UTF-8) in /etc/locale.gen and setting it "
            + "as LC_CTYPE in make.conf."
        )
        msg = [l for l in textwrap.wrap(msg, 70)]
        msg.append("")
        chars = lambda l: "".join(_unicode_decode(chr(x)) for x in l)
        if uc != ruc:
            msg.extend(
                [
                    f"  {chars(lc)} -> {chars(ruc)}",
                    "  %28s: %s" % ("expected", chars(uc)),
                ]
            )
        if lc != rlc:
            msg.extend(
                [
                    f"  {chars(uc)} -> {chars(rlc)}",
                    "  %28s: %s" % ("expected", chars(lc)),
                ]
            )
        writemsg_level(
            "".join([f"!!! {l}\n" for l in msg]), level=logging.ERROR, noiselevel=-1
        )
        return False

    return True


def _set_and_check_locale(silent, env, mylocale):
    try:
        if env is not None:
            try:
                locale.setlocale(locale.LC_CTYPE, mylocale)
            except locale.Error:
                sys.exit(2)

        ret = _check_locale(silent)
        if ret is None:
            sys.exit(2)
        else:
            sys.exit(0 if ret else 1)
    except Exception:
        traceback.print_exc()
        sys.exit(2)


def check_locale(silent=False, env=None):
    """
    Check whether the locale is sane. Returns True if it is, prints
    warning and returns False if it is not. Returns None if the check
    can not be executed due to platform limitations.
    """
    return asyncio.run(async_check_locale(silent=silent, env=env))


async def async_check_locale(silent=False, env=None):
    if env is not None:
        for v in ("LC_ALL", "LC_CTYPE", "LANG"):
            if v in env:
                mylocale = env[v]
                break
        else:
            mylocale = "C"

        try:
            return _check_locale_cache[mylocale]
        except KeyError:
            pass

    proc = multiprocessing.Process(
        target=_set_and_check_locale,
        args=(silent, env, None if env is None else portage._native_string(mylocale)),
    )
    proc.start()
    proc = portage.process.MultiprocessingProcess(proc)
    await proc.wait()

    pyret = None
    if proc.returncode >= 0:
        ret = proc.returncode
        if ret != 2:
            pyret = ret == 0

    if env is not None:
        _check_locale_cache[mylocale] = pyret
    return pyret


async_check_locale.__doc__ = check_locale.__doc__
async_check_locale.__doc__ += """
    This function is a coroutine.
"""


def split_LC_ALL(env):
    """
    Replace LC_ALL with split-up LC_* variables if it is defined.
    Works on the passed environment (or settings instance).
    """
    lc_all = env.get("LC_ALL")
    if lc_all:
        for c in locale_categories:
            env[c] = lc_all
        # Set empty so that config.reset() can restore LC_ALL state,
        # since del can permanently delete variables which are not
        # stored in the config's backupenv.
        env["LC_ALL"] = ""
