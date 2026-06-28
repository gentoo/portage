# Copyright 1998-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# pylint: disable=ungrouped-imports

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

from portage import installation

try:
    import asyncio
    import sys
    import errno

    if not hasattr(errno, "ESTALE"):
        # ESTALE may not be defined on some systems, such as interix.
        errno.ESTALE = -1
    import functools
    import re
    import types
    import platform

    # Temporarily delete these imports, to ensure that only the
    # wrapped versions are imported by portage internals.
    import os

    del os
    import shutil

    del shutil

except ImportError as e:
    sys.stderr.write(
        "\n\n"
        "!!! Failed to complete python imports. These are internal modules for\n"
        "!!! python and failure here indicates that you have a problem with python\n"
        "!!! itself and thus portage is not able to continue processing.\n\n"
        "!!! You might consider starting python with verbose flags to see what has\n"
        "!!! gone wrong. Here is the information we got for this exception:\n"
        f"    {e}\n\n"
    )
    raise

try:
    import portage.proxy.lazyimport
    import portage.proxy as proxy

    proxy.lazyimport.lazyimport(
        globals(),
        "portage.cache.cache_errors:CacheError",
        "portage.checksum",
        "portage.checksum:perform_checksum,perform_md5,prelink_capable",
        "portage.data",
        "portage.data:lchown,ostype,portage_gid,portage_uid,secpass,"
        + "uid,userland,userpriv_groups,wheelgid",
        "portage.dbapi",
        "portage.dbapi.bintree:bindbapi,binarytree",
        "portage.dbapi.cpv_expand:cpv_expand",
        "portage.dbapi.dep_expand:dep_expand",
        "portage.dbapi.porttree:close_portdbapi_caches,FetchlistDict,"
        + "portagetree,portdbapi",
        "portage.dbapi.vartree:dblink,merge,unmerge,vardbapi,vartree",
        "portage.dbapi.virtual:fakedbapi",
        "portage.debug",
        "portage.dep",
        "portage.dep:best_match_to_list,dep_getcpv,dep_getkey,"
        + "flatten,get_operator,isjustname,isspecific,isvalidatom,"
        + "match_from_list,match_to_list",
        "portage.dep.dep_check:dep_check,dep_eval,dep_wordreduce,dep_zapdeps",
        "portage.eclass_cache",
        "portage.elog",
        "portage.exception",
        "portage.getbinpkg",
        "portage.locks",
        "portage.locks:lockdir,lockfile,unlockdir,unlockfile",
        "portage.mail",
        "portage.manifest:Manifest",
        "portage.output",
        "portage.output:bold,colorize",
        "portage.package.ebuild.doebuild:doebuild,"
        + "doebuild_environment,spawn,spawnebuild",
        "portage.package.ebuild.config:best_from_dict,check_config_instance,config",
        "portage.package.ebuild.deprecated_profile_check:deprecated_profile_check",
        "portage.package.ebuild.digestcheck:digestcheck",
        "portage.package.ebuild.digestgen:digestgen",
        "portage.package.ebuild.fetch:fetch",
        "portage.package.ebuild.getmaskingreason:getmaskingreason",
        "portage.package.ebuild.getmaskingstatus:getmaskingstatus",
        "portage.package.ebuild.prepare_build_dirs:prepare_build_dirs",
        "portage.process",
        "portage.process:atexit_register,run_exitfuncs",
        "portage.update:dep_transform,fixdbentries,grab_updates,"
        + "parse_updates,update_config_files,update_dbentries,"
        + "update_dbentry",
        "portage.util",
        "portage.util:atomic_ofstream,apply_secpass_permissions,"
        + "apply_recursive_permissions,dump_traceback,getconfig,"
        + "grabdict,grabdict_package,grabfile,grabfile_package,"
        + "map_dictlist_vals,new_protect_filename,normalize_path,"
        + "pickle_read,pickle_write,stack_dictlist,stack_dicts,"
        + "stack_lists,unique_array,varexpand,writedict,writemsg,"
        + "writemsg_stdout,write_atomic",
        "portage.util.digraph:digraph",
        "portage.util.env_update:env_update",
        "portage.util.ExtractKernelVersion:ExtractKernelVersion",
        "portage.util.listdir:cacheddir,listdir",
        "portage.util.movefile:movefile",
        "portage.util.mtimedb:MtimeDB",
        "portage.versions",
        "portage.versions:best,catpkgsplit,catsplit,cpv_getkey,"
        + "cpv_getkey@getCPFromCPV,endversion_keys,"
        + "suffix_value@endversion,pkgcmp,pkgsplit,vercmp,ververify",
        "portage.xpak",
        "portage.gpkg",
        "subprocess",
        "time",
    )

    from collections import OrderedDict

    import portage.const
    from portage.const import (
        VDB_PATH,
        PRIVATE_PATH,
        CACHE_PATH,
        DEPCACHE_PATH,
        USER_CONFIG_PATH,
        MODULES_FILE_PATH,
        CUSTOM_PROFILE_PATH,
        PORTAGE_BASE_PATH,
        PORTAGE_BIN_PATH,
        PORTAGE_PYM_PATH,
        PROFILE_PATH,
        LOCALE_DATA_PATH,
        EBUILD_SH_BINARY,
        SANDBOX_BINARY,
        BASH_BINARY,
        MOVE_BINARY,
        PRELINK_BINARY,
        WORLD_FILE,
        MAKE_CONF_FILE,
        MAKE_DEFAULTS_FILE,
        DEPRECATED_PROFILE_FILE,
        USER_VIRTUALS_FILE,
        EBUILD_SH_ENV_FILE,
        INVALID_ENV_FILE,
        CUSTOM_MIRRORS_FILE,
        CONFIG_MEMORY_FILE,
        INCREMENTALS,
        EAPI,
        MISC_SH_BINARY,
        REPO_NAME_LOC,
        REPO_NAME_FILE,
    )

except ImportError as e:
    sys.stderr.write("\n\n")
    sys.stderr.write(
        "!!! Failed to complete portage imports. There are internal modules for\n"
    )
    sys.stderr.write(
        "!!! portage and failure here indicates that you have a problem with your\n"
    )
    sys.stderr.write(
        "!!! installation of portage. Please try a rescue portage located in the ebuild\n"
    )
    sys.stderr.write(
        "!!! repository under '/var/db/repos/gentoo/sys-apps/portage/files/' (default).\n"
    )
    sys.stderr.write(
        "!!! There is a README.RESCUE file that details the steps required to perform\n"
    )
    sys.stderr.write("!!! a recovery of portage.\n")
    sys.stderr.write(f"    {e}\n\n")
    raise

import os

# Deprecated: retained for third-party compatibility.
_encodings = {
    "content": "utf_8",
    "fs": "utf_8",
    "merge": "utf_8",
    "repo.content": "utf_8",
    "stdio": "utf_8",
}


def _unicode_encode(s, encoding=_encodings["content"], errors="backslashreplace"):
    import warnings

    warnings.warn(
        "portage._unicode_encode is deprecated",
        DeprecationWarning,
        stacklevel=2,
    )
    if isinstance(s, str):
        s = s.encode(encoding, errors)
    return s


def _unicode_decode(s, encoding=_encodings["content"], errors="replace"):
    import warnings

    warnings.warn(
        "portage._unicode_decode is deprecated",
        DeprecationWarning,
        stacklevel=2,
    )
    if isinstance(s, bytes):
        s = str(s, encoding=encoding, errors=errors)
    return s


_native_string = _unicode_decode


def _decode_argv(argv):
    # With Python 3, the surrogateescape encoding error handler makes it
    # possible to access the original argv bytes, which can be useful
    # if their actual encoding does no match the filesystem encoding.
    fs_encoding = sys.getfilesystemencoding()
    return [x.encode(fs_encoding, "surrogateescape").decode() for x in argv]


try:
    __import__("selinux")
    import portage._selinux

    selinux = _selinux
except (ImportError, OSError) as e:
    if isinstance(e, OSError):
        sys.stderr.write(f"!!! SELinux not loaded: {e}\n")
    del e
    _selinux = None
    selinux_unicode_fs = None
    selinux_unicode_merge = None
    selinux = None

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================

_python_interpreter = (
    sys.executable
    if os.environ.get("VIRTUAL_ENV")
    else os.path.realpath(sys.executable)
)
_bin_path = PORTAGE_BIN_PATH
_pym_path = PORTAGE_PYM_PATH
_not_installed = os.path.isfile(
    os.path.join(PORTAGE_BASE_PATH, ".portage_not_installed")
)

# Api consumers included in portage should set this to True.
_internal_caller = False

_sync_mode = False

if sys.getfilesystemencoding().lower().replace("-", "") not in ("utf8",):
    import warnings

    warnings.warn(
        "portage requires a UTF-8 locale. "
        "Set PYTHONUTF8=1 or configure a UTF-8 locale.",
        RuntimeWarning,
        stacklevel=2,
    )

import multiprocessing

# Prefer the environment variable if set. Otherwise, change away from
# forkserver if in use.
_multiprocessing_method = os.environ.get("PORTAGE_MULTIPROCESSING_START_METHOD")
if not _multiprocessing_method:
    _multiprocessing_method = multiprocessing.get_start_method(allow_none=False)
    if _multiprocessing_method == "forkserver":
        # Undo the Python 3.14 default change on Linux from fork->forkserver
        # because of various problems (bug #973043, bug #973571).
        _multiprocessing_method = "fork"
if _multiprocessing_method:
    multiprocessing.set_start_method(_multiprocessing_method, force=True)


class _ForkWatcher:
    @staticmethod
    def hook(_ForkWatcher):
        _ForkWatcher.current_pid = None
        # Force instantiation of a new event loop policy as a workaround
        # for https://bugs.python.org/issue22087.
        if sys.version_info < (3, 12):
            asyncio.set_event_loop_policy(None)


_ForkWatcher.hook(_ForkWatcher)

os.register_at_fork(after_in_child=functools.partial(_ForkWatcher.hook, _ForkWatcher))


def getpid():
    """
    Cached version of os.getpid(). ForkProcess updates the cache.
    """
    if _ForkWatcher.current_pid is None:
        _ForkWatcher.current_pid = os.getpid()
    return _ForkWatcher.current_pid


def _get_stdin():
    """
    Buggy code in python's multiprocessing/process.py closes sys.stdin
    and reassigns it to open(os.devnull), but fails to update the
    corresponding __stdin__ reference. So, detect that case and handle
    it appropriately.
    """
    if not sys.__stdin__.closed:
        return sys.__stdin__
    return sys.stdin


bsd_chflags = None

if platform.system() in ("FreeBSD",):
    # TODO: remove this class?
    class bsd_chflags:
        chflags = os.chflags
        lchflags = os.lchflags


def load_mod(name):
    components = name.split(".")
    modname = ".".join(components[:-1])
    mod = __import__(modname)
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod


def getcwd():
    "this fixes situations where the current directory doesn't exist"
    try:
        return os.getcwd()
    except OSError:  # dir doesn't exist
        os.chdir("/")
        return "/"


getcwd()


def abssymlink(symlink, target=None):
    """
    This reads symlinks, resolving the relative symlinks,
    and returning the absolute.
    @param symlink: path of symlink (must be absolute)
    @param target: the target of the symlink (as returned
            by readlink)
    @rtype: str
    @return: the absolute path of the symlink target
    """
    if target is not None:
        mylink = target
    else:
        mylink = os.readlink(symlink)
    if mylink[0] != "/":
        mydir = os.path.dirname(symlink)
        mylink = f"{mydir}/{mylink}"
    return os.path.normpath(mylink)


_doebuild_manifest_exempt_depend = 0

_testing_eapis = frozenset(["9-pre1"])
_deprecated_eapis = frozenset(
    [
        "3_pre1",
        "3_pre2",
        "4_pre1",
        "5_pre1",
        "5_pre2",
        "6_pre1",
        "7_pre1",
    ]
)

from itertools import chain

_supported_eapis = frozenset(
    chain(
        (str(x) for x in range(portage.const.EAPI + 1)),
        _testing_eapis,
        _deprecated_eapis,
    )
)


def _eapi_is_deprecated(eapi):
    return eapi in _deprecated_eapis


def eapi_is_supported(eapi):
    eapi = str(eapi).strip()
    return eapi in _supported_eapis


# This pattern is specified by PMS section 7.3.1.
_pms_eapi_re = re.compile(r"^[ \t]*EAPI=(['\"]?)([A-Za-z0-9+_.-]*)\1[ \t]*([ \t]#.*)?$")
_comment_or_blank_line = re.compile(r"^\s*(#.*)?$")


def _parse_eapi_ebuild_head(f):
    eapi = None
    eapi_lineno = None
    lineno = 0
    for line in f:
        lineno += 1
        m = _comment_or_blank_line.match(line)
        if m is None:
            eapi_lineno = lineno
            m = _pms_eapi_re.match(line)
            if m is not None:
                eapi = m.group(2)
            break

    return (eapi, eapi_lineno)


def _movefile(src, dest, **kwargs):
    """Calls movefile and raises a PortageException if an error occurs."""
    if movefile(src, dest, **kwargs) is None:
        raise portage.exception.PortageException(f"mv '{src}' '{dest}'")


auxdbkeys = (
    "DEPEND",
    "RDEPEND",
    "SLOT",
    "SRC_URI",
    "RESTRICT",
    "HOMEPAGE",
    "LICENSE",
    "DESCRIPTION",
    "KEYWORDS",
    "INHERITED",
    "IUSE",
    "REQUIRED_USE",
    "PDEPEND",
    "BDEPEND",
    "EAPI",
    "PROPERTIES",
    "DEFINED_PHASES",
    "IDEPEND",
    "INHERIT",
)


def portageexit():
    pass


class _trees_dict(dict):
    __slots__ = (
        "_running_eroot",
        "_target_eroot",
    )

    def __init__(self, *pargs, **kargs):
        dict.__init__(self, *pargs, **kargs)
        self._running_eroot = None
        self._target_eroot = None


def create_trees(
    config_root=None, target_root=None, trees=None, env=None, sysroot=None, eprefix=None
):
    config_root = (
        os.fsdecode(config_root) if isinstance(config_root, bytes) else config_root
    )
    target_root = (
        os.fsdecode(target_root) if isinstance(target_root, bytes) else target_root
    )
    sysroot = os.fsdecode(sysroot) if isinstance(sysroot, bytes) else sysroot
    eprefix = os.fsdecode(eprefix) if isinstance(eprefix, bytes) else eprefix

    if trees is None:
        trees = _trees_dict()
    elif not isinstance(trees, _trees_dict):
        # caller passed a normal dict or something,
        # but we need a _trees_dict instance
        trees = _trees_dict(trees)

    if env is None:
        env = os.environ

    settings = config(
        config_root=config_root,
        target_root=target_root,
        env=env,
        sysroot=sysroot,
        eprefix=eprefix,
    )
    settings.lock()

    depcachedir = settings.get("PORTAGE_DEPCACHEDIR")
    trees._target_eroot = settings["EROOT"]
    myroots = [(settings["EROOT"], settings)]
    if settings["ROOT"] == "/" and settings["EPREFIX"] == const.EPREFIX:
        trees._running_eroot = trees._target_eroot
    else:
        # When ROOT != "/" we only want overrides from the calling
        # environment to apply to the config that's associated
        # with ROOT != "/", so pass a nearly empty dict for the env parameter.
        env_sequence = (
            "MAKEFLAGS",
            "PATH",
            "PORTAGE_GRPNAME",
            "PORTAGE_REPOSITORIES",
            "PORTAGE_USERNAME",
            "PYTHONPATH",
            "SSH_AGENT_PID",
            "SSH_AUTH_SOCK",
            "TERM",
            "ftp_proxy",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "__PORTAGE_TEST_HARDLINK_LOCKS",
        )
        env = ((k, settings.get(k)) for k in env_sequence)
        clean_env = {k: v for k, v in env if v is not None}

        if depcachedir is not None:
            clean_env["PORTAGE_DEPCACHEDIR"] = depcachedir
        mysettings = config(
            config_root=None, target_root="/", env=clean_env, sysroot="/", eprefix=None
        )
        mysettings.lock()
        trees._running_eroot = mysettings["EROOT"]
        myroots.append((mysettings["EROOT"], mysettings))

        if settings["SYSROOT"] != "/" and settings["SYSROOT"] != settings["ROOT"]:
            mysettings = config(
                config_root=settings["SYSROOT"],
                target_root=settings["SYSROOT"],
                env=clean_env,
                sysroot=settings["SYSROOT"],
                eprefix="",
            )
            mysettings.lock()
            myroots.append((mysettings["EROOT"], mysettings))

    for myroot, mysettings in myroots:
        trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, {}))
        trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals)
        trees[myroot].addLazySingleton(
            "vartree", vartree, categories=mysettings.categories, settings=mysettings
        )
        trees[myroot].addLazySingleton("porttree", portagetree, settings=mysettings)
        trees[myroot].addLazySingleton(
            "bintree", binarytree, pkgdir=mysettings["PKGDIR"], settings=mysettings
        )
    return trees


if installation.TYPE == installation.TYPES.SOURCE:

    class _LazyVersion(proxy.objectproxy.ObjectProxy):
        def _get_target(self):
            global VERSION
            if VERSION is not self:
                return VERSION
            VERSION = "HEAD"
            if os.path.isdir(os.path.join(PORTAGE_BASE_PATH, ".git")):
                try:
                    result = subprocess.run(
                        [
                            "git",
                            "describe",
                            "--dirty",
                            "--long",
                            "--match",
                            "portage-*",
                        ],
                        capture_output=True,
                        cwd=PORTAGE_BASE_PATH,
                        encoding="utf-8",
                    )
                    if result.returncode == 0:
                        # https://peps.python.org/pep-0440/
                        VERSION, commits_since_tag, commit, dirty = re.fullmatch(
                            "portage-([0-9.]*)-([0-9]*)-(g[0-9a-z]*)(-dirty)?",
                            result.stdout.strip(),
                        ).groups()
                        if commits_since_tag != "0":
                            VERSION += f".dev{commits_since_tag}+{commit}"
                            if dirty is not None:
                                VERSION += "-dirty"
                        elif dirty is not None:
                            VERSION += "+dirty"
                except OSError:
                    pass
            return VERSION

    VERSION = _LazyVersion()

else:
    VERSION = "@VERSION@"

_legacy_global_var_names = (
    "archlist",
    "db",
    "features",
    "groups",
    "mtimedb",
    "mtimedbfile",
    "pkglines",
    "portdb",
    "profiledir",
    "root",
    "selinux_enabled",
    "settings",
    "thirdpartymirrors",
)


def _reset_legacy_globals():
    global _legacy_globals_constructed
    _legacy_globals_constructed = set()
    for k in _legacy_global_var_names:
        globals()[k] = _LegacyGlobalProxy(k)


class _LegacyGlobalProxy(proxy.objectproxy.ObjectProxy):
    __slots__ = ("_name",)

    def __init__(self, name):
        proxy.objectproxy.ObjectProxy.__init__(self)
        object.__setattr__(self, "_name", name)

    def _get_target(self):
        name = object.__getattribute__(self, "_name")
        from portage._legacy_globals import _get_legacy_global

        return _get_legacy_global(name)


_reset_legacy_globals()


def _disable_legacy_globals():
    """
    This deletes the ObjectProxy instances that are used
    for lazy initialization of legacy global variables.
    The purpose of deleting them is to prevent new code
    from referencing these deprecated variables.
    """
    global _legacy_global_var_names
    for k in _legacy_global_var_names:
        globals().pop(k, None)
    portage.data._initialized_globals.clear()
