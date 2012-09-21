# portage: Constants
# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

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
USER_CONFIG_PATH         = "etc/portage"
MAKE_CONF_FILE           = USER_CONFIG_PATH + "/make.conf"
MODULES_FILE_PATH        = USER_CONFIG_PATH + "/modules"
CUSTOM_PROFILE_PATH      = USER_CONFIG_PATH + "/profile"
USER_VIRTUALS_FILE       = USER_CONFIG_PATH + "/virtuals"
EBUILD_SH_ENV_FILE       = USER_CONFIG_PATH + "/bashrc"
EBUILD_SH_ENV_DIR        = USER_CONFIG_PATH + "/env"
CUSTOM_MIRRORS_FILE      = USER_CONFIG_PATH + "/mirrors"
COLOR_MAP_FILE           = USER_CONFIG_PATH + "/color.map"
PROFILE_PATH             = USER_CONFIG_PATH + "/make.profile"
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
PORTAGE_BASE_PATH        = os.path.join(os.sep, os.sep.join(__file__.split(os.sep)[:-3]))
PORTAGE_BIN_PATH         = PORTAGE_BASE_PATH + "/bin"
PORTAGE_PYM_PATH         = PORTAGE_BASE_PATH + "/pym"
LOCALE_DATA_PATH         = PORTAGE_BASE_PATH + "/locale"  # FIXME: not used
EBUILD_SH_BINARY         = PORTAGE_BIN_PATH + "/ebuild.sh"
MISC_SH_BINARY           = PORTAGE_BIN_PATH + "/misc-functions.sh"
SANDBOX_BINARY           = "/usr/bin/sandbox"
FAKEROOT_BINARY          = "/usr/bin/fakeroot"
BASH_BINARY              = "/bin/bash"
MOVE_BINARY              = "/bin/mv"
PRELINK_BINARY           = "/usr/sbin/prelink"

INVALID_ENV_FILE         = "/etc/spork/is/not/valid/profile.env"
REPO_NAME_FILE           = "repo_name"
REPO_NAME_LOC            = "profiles" + "/" + REPO_NAME_FILE

PORTAGE_PACKAGE_ATOM     = "sys-apps/portage"
LIBC_PACKAGE_ATOM        = "virtual/libc"
OS_HEADERS_PACKAGE_ATOM  = "virtual/os-headers"

INCREMENTALS             = ("USE", "USE_EXPAND", "USE_EXPAND_HIDDEN",
                           "FEATURES", "ACCEPT_KEYWORDS",
                           "CONFIG_PROTECT_MASK", "CONFIG_PROTECT",
                           "IUSE_IMPLICIT",
                           "PRELINK_PATH", "PRELINK_PATH_MASK",
                           "PROFILE_ONLY_VARIABLES",
                           "USE_EXPAND_IMPLICIT", "USE_EXPAND_UNPREFIXED")
EBUILD_PHASES            = ("pretend", "setup", "unpack", "prepare", "configure",
                           "compile", "test", "install",
                           "package", "preinst", "postinst","prerm", "postrm",
                           "nofetch", "config", "info", "other")
SUPPORTED_FEATURES       = frozenset([
                           "assume-digests", "binpkg-logs", "buildpkg", "buildsyspkg", "candy",
                           "ccache", "chflags", "clean-logs",
                           "collision-protect", "compress-build-logs", "compressdebug",
                           "compress-index", "config-protect-if-modified",
                           "digest", "distcc", "distcc-pump", "distlocks",
                           "downgrade-backup", "ebuild-locks", "fakeroot",
                           "fail-clean", "force-mirror", "force-prefix", "getbinpkg",
                           "installsources", "keeptemp", "keepwork", "fixlafiles", "lmirror",
                           "merge-sync",
                           "metadata-transfer", "mirror", "multilib-strict", "news",
                           "noauto", "noclean", "nodoc", "noinfo", "noman",
                           "nostrip", "notitles", "parallel-fetch", "parallel-install",
                           "prelink-checksums", "preserve-libs",
                           "protect-owned", "python-trace", "sandbox",
                           "selinux", "sesandbox", "sfperms",
                           "sign", "skiprocheck", "split-elog", "split-log", "splitdebug",
                           "strict", "stricter", "suidctl", "test", "test-fail-continue",
                           "unknown-features-filter", "unknown-features-warn",
                           "unmerge-backup",
                           "unmerge-logs", "unmerge-orphans", "userfetch", "userpriv",
                           "usersandbox", "usersync", "webrsync-gpg", "xattr"])

EAPI                     = 5

HASHING_BLOCKSIZE        = 32768
MANIFEST1_HASH_FUNCTIONS = ("MD5", "SHA256", "RMD160")
MANIFEST1_REQUIRED_HASH  = "MD5"

# Past events:
#
# 20120704 - After WHIRLPOOL is supported in stable portage:
# - Set manifest-hashes in gentoo-x86/metadata/layout.conf as follows:
#     manifest-hashes = SHA256 SHA512 WHIRLPOOL
# - Add SHA512 and WHIRLPOOL to MANIFEST2_HASH_DEFAULTS.
# - Remove SHA1 and RMD160 from MANIFEST2_HASH_*.
#
# Future events:
#
# After WHIRLPOOL is supported in stable portage for at least 1 year:
# - Change MANIFEST2_REQUIRED_HASH to WHIRLPOOL.
# - Remove SHA256 from MANIFEST2_HASH_*.
# - Set manifest-hashes in gentoo-x86/metadata/layout.conf as follows:
#     manifest-hashes = SHA512 WHIRLPOOL
#
# After SHA-3 is approved:
# - Add new hashes to MANIFEST2_HASH_*.
#
# After SHA-3 is supported in stable portage:
# - Set manifest-hashes in gentoo-x86/metadata/layout.conf as follows:
#     manifest-hashes = SHA3 SHA512 WHIRLPOOL
#
# After layout.conf settings correspond to defaults in stable portage:
# - Remove redundant settings from gentoo-x86/metadata/layout.conf.

MANIFEST2_HASH_FUNCTIONS = ("SHA256", "SHA512", "WHIRLPOOL")
MANIFEST2_HASH_DEFAULTS = frozenset(["SHA256", "SHA512", "WHIRLPOOL"])
MANIFEST2_REQUIRED_HASH  = "SHA256"

MANIFEST2_IDENTIFIERS    = ("AUX", "MISC", "DIST", "EBUILD")

# The EPREFIX for the current install is hardcoded here, but access to this
# constant should be minimal, in favor of access via the EPREFIX setting of
# a config instance (since it's possible to contruct a config instance with
# a different EPREFIX). Therefore, the EPREFIX constant should *NOT* be used
# in the definition of any other constants within this file.
EPREFIX=""

# pick up EPREFIX from the environment if set
if "PORTAGE_OVERRIDE_EPREFIX" in os.environ:
	EPREFIX = os.environ["PORTAGE_OVERRIDE_EPREFIX"]
	if EPREFIX:
		EPREFIX = os.path.normpath(EPREFIX)

# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================

# Private constants for use in conditional code in order to minimize the diff
# between branches.
_DEPCLEAN_LIB_CHECK_DEFAULT = 'n'
_ENABLE_REPO_NAME_WARN  = False
_ENABLE_SET_CONFIG      = False
_ENABLE_INHERIT_CHECK   = False
