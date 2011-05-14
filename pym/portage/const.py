# portage: Constants
# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# ===========================================================================
# autotool supplied constants.
# ===========================================================================
from portage.const_autotool import *

import os

# save the original prefix
BPREFIX = EPREFIX
# pick up EPREFIX from the environment if set
if "EPREFIX" in os.environ:
	if os.environ["EPREFIX"] != "":
		EPREFIX = os.path.normpath(os.environ["EPREFIX"])
	else:
		EPREFIX = os.environ["EPREFIX"]

# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

EPREFIX_LSTRIP          = EPREFIX.lstrip(os.path.sep)

# There are two types of variables here which can easily be confused,
# resulting in arbitrary bugs, mainly exposed with an offset
# installation (Prefix).  The two types relate to the usage of
# config_root or target_root.
# The first, config_root (PORTAGE_CONFIGROOT), can be a path somewhere,
# from which all derived paths need to be relative (e.g.
# USER_CONFIG_PATH) without EPREFIX prepended in Prefix.  This means
# config_root can for instance be set to "$HOME/my/config".  Obviously,
# in such case it is not appropriate to prepend EPREFIX to derived
# constants.  The default value of config_root is EPREFIX (in non-Prefix
# the empty string) -- overriding the value loses the EPREFIX as one
# would expect.
# Second there is target_root (ROOT) which is used to install somewhere
# completely else, in Prefix of limited use.  Because this is an offset
# always given, the EPREFIX should always be applied in it, hence the
# code always prefixes them with EROOT.
# The variables in this file are grouped by config_root, target_root.

# variables used with config_root (these need to be relative)
MAKE_CONF_FILE           = "etc/make.conf"
USER_CONFIG_PATH         = "etc/portage"
MODULES_FILE_PATH        = USER_CONFIG_PATH + "/modules"
CUSTOM_PROFILE_PATH      = USER_CONFIG_PATH + "/profile"
USER_VIRTUALS_FILE       = USER_CONFIG_PATH + "/virtuals"
EBUILD_SH_ENV_FILE       = USER_CONFIG_PATH + "/bashrc"
EBUILD_SH_ENV_DIR        = USER_CONFIG_PATH + "/env"
CUSTOM_MIRRORS_FILE      = USER_CONFIG_PATH + "/mirrors"
COLOR_MAP_FILE           = USER_CONFIG_PATH + "/color.map"
PROFILE_PATH             = "etc/make.profile"
MAKE_DEFAULTS_FILE       = PROFILE_PATH + "/make.defaults"  # FIXME: not used
DEPRECATED_PROFILE_FILE  = PROFILE_PATH + "/deprecated"

# variables used with targetroot (these need to be absolute, but not
# have a leading '/' since they are used directly with os.path.join on EROOT)
VDB_PATH                 = "var/db/pkg"
CACHE_PATH               = "var/cache/edb"
PRIVATE_PATH             = "var/lib/portage"
WORLD_FILE               = PRIVATE_PATH + "/world"
WORLD_SETS_FILE          = PRIVATE_PATH + "/world_sets"
CONFIG_MEMORY_FILE       = PRIVATE_PATH + "/config"
NEWS_LIB_PATH            = "var/lib/gentoo"

# these variables get EPREFIX prepended automagically when they are
# translated into their lowercase variants
DEPCACHE_PATH            = "/var/cache/edb/dep"
GLOBAL_CONFIG_PATH       = "/usr/share/portage/config"

# these variables are not used with target_root or config_root
PORTAGE_BASE_PATH        = PORTAGE_BASE
PORTAGE_BIN_PATH         = PORTAGE_BASE_PATH + "/bin"
PORTAGE_PYM_PATH         = PORTAGE_BASE_PATH + "/pym"
LOCALE_DATA_PATH         = PORTAGE_BASE_PATH + "/locale"  # FIXME: not used
EBUILD_SH_BINARY         = PORTAGE_BIN_PATH + "/ebuild.sh"
MISC_SH_BINARY           = PORTAGE_BIN_PATH + "/misc-functions.sh"
SANDBOX_BINARY           = BPREFIX + "/usr/bin/sandbox"
FAKEROOT_BINARY          = BPREFIX + "/usr/bin/fakeroot"
BASH_BINARY              = PORTAGE_BASH
MOVE_BINARY              = PORTAGE_MV
PRELINK_BINARY           = "/usr/sbin/prelink"
MACOSSANDBOX_BINARY      = "/usr/bin/sandbox-exec"
MACOSSANDBOX_PROFILE     = '''(version 1)

(allow default)

(deny file-write*)

(allow file-read* file-write*
  (literal
    #"@@WRITEABLE_PREFIX@@"
  )

  (regex
    #"^@@WRITEABLE_PREFIX_RE@@/"
    #"^(/private)?/var/tmp"
    #"^(/private)?/tmp"
  )
)

(allow file-read-data file-write-data
  (regex
    #"^/dev/null$"
    #"^(/private)?/var/run/syslog$"
  )
)'''

PORTAGE_GROUPNAME        = portagegroup
PORTAGE_USERNAME         = portageuser

INVALID_ENV_FILE         = "/etc/spork/is/not/valid/profile.env"
REPO_NAME_FILE           = "repo_name"
REPO_NAME_LOC            = "profiles" + "/" + REPO_NAME_FILE

PORTAGE_PACKAGE_ATOM     = "sys-apps/portage"
LIBC_PACKAGE_ATOM        = "virtual/libc"
OS_HEADERS_PACKAGE_ATOM  = "virtual/os-headers"

INCREMENTALS             = ("USE", "USE_EXPAND", "USE_EXPAND_HIDDEN",
                           "FEATURES", "ACCEPT_KEYWORDS",
                           "CONFIG_PROTECT_MASK", "CONFIG_PROTECT",
                           "PRELINK_PATH", "PRELINK_PATH_MASK",
                           "PROFILE_ONLY_VARIABLES")
EBUILD_PHASES            = ("pretend", "setup", "unpack", "prepare", "configure",
                           "compile", "test", "install",
                           "package", "preinst", "postinst","prerm", "postrm",
                           "nofetch", "config", "info", "other")
SUPPORTED_FEATURES       = frozenset([
                           "assume-digests", "binpkg-logs", "buildpkg", "buildsyspkg", "candy",
                           "ccache", "chflags", "collision-protect", "compress-build-logs",
                           "digest", "distcc", "distlocks", "ebuild-locks", "fakeroot",
                           "fail-clean", "fixpackages", "force-mirror", "getbinpkg",
                           "installsources", "keeptemp", "keepwork", "fixlafiles", "lmirror",
                            "macossandbox", "macosprefixsandbox", "macosusersandbox",
                           "metadata-transfer", "mirror", "multilib-strict", "news",
                           "noauto", "noclean", "nodoc", "noinfo", "noman",
                           "nostrip", "notitles", "parallel-fetch", "parallel-install",
                           "parse-eapi-ebuild-head",
                           "prelink-checksums", "preserve-libs",
                           "protect-owned", "python-trace", "sandbox",
                           "selinux", "sesandbox", "severe", "sfperms",
                           "sign", "skiprocheck", "split-elog", "split-log", "splitdebug",
                           "strict", "stricter", "suidctl", "test", "test-fail-continue",
                           "unknown-features-filter", "unknown-features-warn",
                           "unmerge-logs", "unmerge-orphans", "userfetch", "userpriv",
                           "usersandbox", "usersync", "webrsync-gpg"])

EAPI                     = 4

HASHING_BLOCKSIZE        = 32768
MANIFEST1_HASH_FUNCTIONS = ("MD5", "SHA256", "RMD160")
MANIFEST2_HASH_FUNCTIONS = ("SHA1", "SHA256", "RMD160")

MANIFEST1_REQUIRED_HASH  = "MD5"
MANIFEST2_REQUIRED_HASH  = "SHA1"

MANIFEST2_IDENTIFIERS    = ("AUX", "MISC", "DIST", "EBUILD")
# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================

# Private constants for use in conditional code in order to minimize the diff
# between branches.
_ENABLE_DYN_LINK_MAP    = True
_ENABLE_PRESERVE_LIBS   = True
_ENABLE_REPO_NAME_WARN  = True
_ENABLE_SET_CONFIG      = True
_SANDBOX_COMPAT_LEVEL   = "22"


# The definitions above will differ between branches, so it's useful to have
# common lines of diff context here in order to avoid merge conflicts.

if not _ENABLE_PRESERVE_LIBS:
	SUPPORTED_FEATURES = set(SUPPORTED_FEATURES)
	SUPPORTED_FEATURES.remove("preserve-libs")
	SUPPORTED_FEATURES = frozenset(SUPPORTED_FEATURES)

if not _ENABLE_SET_CONFIG:
	WORLD_SETS_FILE = '/dev/null'
