# portage: Constants
# Copyright 1998-2021 Gentoo Authors
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
BINREPOS_CONF_FILE       = USER_CONFIG_PATH + "/binrepos.conf"
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
# NOTE: Use realpath(__file__) so that python module symlinks in site-packages
# are followed back to the real location of the whole portage installation.
# NOTE: Please keep PORTAGE_BASE_PATH in one line to help substitutions.
PORTAGE_BASE_PATH        = os.path.join(os.sep, os.sep.join(os.path.realpath(__file__.rstrip("co")).split(os.sep)[:-3]))
PORTAGE_BIN_PATH         = PORTAGE_BASE_PATH + "/bin"
PORTAGE_PYM_PATH         = os.path.realpath(os.path.join(__file__, '../..'))
LOCALE_DATA_PATH         = PORTAGE_BASE_PATH + "/locale"  # FIXME: not used
EBUILD_SH_BINARY         = PORTAGE_BIN_PATH + "/ebuild.sh"
MISC_SH_BINARY           = PORTAGE_BIN_PATH + "/misc-functions.sh"
SANDBOX_BINARY           = "/usr/bin/sandbox"
FAKEROOT_BINARY          = "/usr/bin/fakeroot"
BASH_BINARY              = "/bin/bash"
MOVE_BINARY              = "/bin/mv"
PRELINK_BINARY           = "/usr/sbin/prelink"

INVALID_ENV_FILE         = "/etc/spork/is/not/valid/profile.env"
MERGING_IDENTIFIER       = "-MERGING-"
REPO_NAME_FILE           = "repo_name"
REPO_NAME_LOC            = "profiles" + "/" + REPO_NAME_FILE

PORTAGE_PACKAGE_ATOM     = "sys-apps/portage"
LIBC_PACKAGE_ATOM        = "virtual/libc"
OS_HEADERS_PACKAGE_ATOM  = "virtual/os-headers"
CVS_PACKAGE_ATOM         = "dev-vcs/cvs"
GIT_PACKAGE_ATOM         = "dev-vcs/git"
HG_PACKAGE_ATOM          = "dev-vcs/mercurial"
RSYNC_PACKAGE_ATOM       = "net-misc/rsync"

INCREMENTALS             = (
	"ACCEPT_KEYWORDS",
	"CONFIG_PROTECT",
	"CONFIG_PROTECT_MASK",
	"ENV_UNSET",
	"FEATURES",
	"IUSE_IMPLICIT",
	"PRELINK_PATH",
	"PRELINK_PATH_MASK",
	"PROFILE_ONLY_VARIABLES",
	"USE",
	"USE_EXPAND",
	"USE_EXPAND_HIDDEN",
	"USE_EXPAND_IMPLICIT",
	"USE_EXPAND_UNPREFIXED",
)
EBUILD_PHASES            = (
	"pretend",
	"setup",
	"unpack",
	"prepare",
	"configure",
	"compile",
	"test",
	"install",
	"package",
	"instprep",
	"preinst",
	"postinst",
	"prerm",
	"postrm",
	"nofetch",
	"config",
	"info",
	"other",
)
SUPPORTED_FEATURES       = frozenset([
	"assume-digests",
	"binpkg-docompress",
	"binpkg-dostrip",
	"binpkg-logs",
	"binpkg-multi-instance",
	"buildpkg",
	"buildsyspkg",
	"candy",
	"case-insensitive-fs",
	"ccache",
	"cgroup",
	"chflags",
	"clean-logs",
	"collision-protect",
	"compress-build-logs",
	"compressdebug",
	"compress-index",
	"config-protect-if-modified",
	"digest",
	"distcc",
	"distlocks",
	"downgrade-backup",
	"ebuild-locks",
	"fail-clean",
	"fakeroot",
	"fixlafiles",
	"force-mirror",
	"force-prefix",
	"getbinpkg",
	"icecream",
	"installsources",
	"ipc-sandbox",
	"keeptemp",
	"keepwork",
	"lmirror",
	"merge-sync",
	"metadata-transfer",
	"mirror",
	"mount-sandbox",
	"multilib-strict",
	"network-sandbox",
	"network-sandbox-proxy",
	"news",
	"noauto",
	"noclean",
	"nodoc",
	"noinfo",
	"noman",
	"nostrip",
	"notitles",
	"parallel-fetch",
	"parallel-install",
	"pid-sandbox",
	"pkgdir-index-trusted",
	"prelink-checksums",
	"preserve-libs",
	"protect-owned",
	"python-trace",
	"qa-unresolved-soname-deps",
	"sandbox",
	"selinux",
	"sesandbox",
	"sfperms",
	"sign",
	"skiprocheck",
	"splitdebug",
	"split-elog",
	"split-log",
	"strict",
	"strict-keepdir",
	"stricter",
	"suidctl",
	"test",
	"test-fail-continue",
	"unknown-features-filter",
	"unknown-features-warn",
	"unmerge-backup",
	"unmerge-logs",
	"unmerge-orphans",
	"unprivileged",
	"userfetch",
	"userpriv",
	"usersandbox",
	"usersync",
	"webrsync-gpg",
	"xattr",
])

EAPI                     = 8

HASHING_BLOCKSIZE        = 32768

MANIFEST2_HASH_DEFAULTS = frozenset(["BLAKE2B", "SHA512"])
MANIFEST2_HASH_DEFAULT  = "BLAKE2B"

MANIFEST2_IDENTIFIERS    = ("AUX", "MISC", "DIST", "EBUILD")

# The EPREFIX for the current install is hardcoded here, but access to this
# constant should be minimal, in favor of access via the EPREFIX setting of
# a config instance (since it's possible to contruct a config instance with
# a different EPREFIX). Therefore, the EPREFIX constant should *NOT* be used
# in the definition of any other constants within this file.
EPREFIX = ""

# pick up EPREFIX from the environment if set
if "PORTAGE_OVERRIDE_EPREFIX" in os.environ:
	EPREFIX = os.environ["PORTAGE_OVERRIDE_EPREFIX"]
	if EPREFIX:
		EPREFIX = os.path.normpath(EPREFIX)
		if EPREFIX == os.sep:
			EPREFIX = ""

VCS_DIRS = ("CVS", "RCS", "SCCS", ".bzr", ".git", ".hg", ".svn")

# List of known live eclasses. Keep it in sync with cnf/sets/portage.conf
LIVE_ECLASSES = frozenset([
	"bzr",
	"cvs",
	"darcs",
	"git-2",
	"git-r3",
	"golang-vcs",
	"mercurial",
	"subversion",
])

SUPPORTED_BINPKG_FORMATS = ("tar", "rpm")
SUPPORTED_XPAK_EXTENSIONS = (".tbz2", ".xpak")

# Time formats used in various places like metadata.chk.
TIMESTAMP_FORMAT = "%a, %d %b %Y %H:%M:%S +0000"	# to be used with time.gmtime()

# Top-level names of Python packages installed by Portage.
PORTAGE_PYM_PACKAGES = ("_emerge", "portage")

RETURNCODE_POSTINST_FAILURE = 5

# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================

# Private constants for use in conditional code in order to minimize the diff
# between branches.
_DEPCLEAN_LIB_CHECK_DEFAULT = True
_ENABLE_SET_CONFIG      = True
