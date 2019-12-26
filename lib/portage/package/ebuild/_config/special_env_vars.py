# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'case_insensitive_vars', 'default_globals', 'env_blacklist', \
	'environ_filter', 'environ_whitelist', 'environ_whitelist_re',
)

import re

# Blacklisted variables are internal variables that are never allowed
# to enter the config instance from the external environment or
# configuration files.
env_blacklist = frozenset((
	"A", "AA", "BASH_FUNC____in_portage_iuse%%", "BDEPEND", "BROOT",
	"CATEGORY", "DEPEND", "DESCRIPTION", "DOCS", "EAPI",
	"EBUILD_FORCE_TEST", "EBUILD_PHASE",
	"EBUILD_PHASE_FUNC", "EBUILD_SKIP_MANIFEST",
	"ED", "EMERGE_FROM", "EPREFIX", "EROOT",
	"GREP_OPTIONS", "HOMEPAGE",
	"IDEPEND", "INHERITED", "IUSE", "IUSE_EFFECTIVE",
	"KEYWORDS", "LICENSE", "MERGE_TYPE",
	"PDEPEND", "PF", "PKGUSE", "PORTAGE_BACKGROUND",
	"PORTAGE_BACKGROUND_UNMERGE", "PORTAGE_BUILDDIR_LOCKED",
	"PORTAGE_BUILT_USE", "PORTAGE_CONFIGROOT",
	"PORTAGE_INTERNAL_CALLER", "PORTAGE_IUSE",
	"PORTAGE_NONFATAL", "PORTAGE_PIPE_FD", "PORTAGE_REPO_NAME",
	"PORTAGE_USE", "PROPERTIES", "RDEPEND", "REPOSITORY",
	"REQUIRED_USE", "RESTRICT", "ROOT", "SANDBOX_LOG", "SLOT", "SRC_URI", "_"
))

environ_whitelist = []

# Whitelisted variables are always allowed to enter the ebuild
# environment. Generally, this only includes special portage
# variables. Ebuilds can unset variables that are not whitelisted
# and rely on them remaining unset for future phases, without them
# leaking back in from various locations (bug #189417). It's very
# important to set our special BASH_ENV variable in the ebuild
# environment in order to prevent sandbox from sourcing /etc/profile
# in it's bashrc (causing major leakage).
environ_whitelist += [
	"ACCEPT_LICENSE", "BASH_ENV", "BASH_FUNC____in_portage_iuse%%",
	"BROOT", "BUILD_PREFIX", "COLUMNS", "D",
	"DISTDIR", "DOC_SYMLINKS_DIR", "EAPI", "EBUILD",
	"EBUILD_FORCE_TEST",
	"EBUILD_PHASE", "EBUILD_PHASE_FUNC", "ECLASSDIR", "ECLASS_DEPTH", "ED",
	"EMERGE_FROM", "ENV_UNSET", "EPREFIX", "EROOT", "ESYSROOT",
	"FEATURES", "FILESDIR", "HOME", "MERGE_TYPE", "NOCOLOR", "PATH",
	"PKGDIR",
	"PKGUSE", "PKG_LOGDIR", "PKG_TMPDIR",
	"PORTAGE_ACTUAL_DISTDIR", "PORTAGE_ARCHLIST", "PORTAGE_BASHRC_FILES",
	"PORTAGE_BASHRC", "PM_EBUILD_HOOK_DIR",
	"PORTAGE_BINPKG_FILE", "PORTAGE_BINPKG_TAR_OPTS",
	"PORTAGE_BINPKG_TMPFILE",
	"PORTAGE_BIN_PATH",
	"PORTAGE_BUILDDIR", "PORTAGE_BUILD_GROUP", "PORTAGE_BUILD_USER",
	"PORTAGE_BUNZIP2_COMMAND", "PORTAGE_BZIP2_COMMAND",
	"PORTAGE_COLORMAP", "PORTAGE_COMPRESS", "PORTAGE_COMPRESSION_COMMAND",
	"PORTAGE_COMPRESS_EXCLUDE_SUFFIXES",
	"PORTAGE_CONFIGROOT", "PORTAGE_DEBUG", "PORTAGE_DEPCACHEDIR",
	"PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS",
	"PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES",
	"PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES",
	"PORTAGE_EBUILD_EXIT_FILE", "PORTAGE_FEATURES",
	"PORTAGE_GID", "PORTAGE_GRPNAME",
	"PORTAGE_INTERNAL_CALLER",
	"PORTAGE_INST_GID", "PORTAGE_INST_UID",
	"PORTAGE_IPC_DAEMON", "PORTAGE_IUSE", "PORTAGE_ECLASS_LOCATIONS",
	"PORTAGE_LOG_FILE", "PORTAGE_OVERRIDE_EPREFIX", "PORTAGE_PIPE_FD",
	"PORTAGE_PROPERTIES",
	"PORTAGE_PYM_PATH", "PORTAGE_PYTHON",
	"PORTAGE_PYTHONPATH", "PORTAGE_QUIET",
	"PORTAGE_REPO_NAME", "PORTAGE_REPOSITORIES", "PORTAGE_RESTRICT",
	"PORTAGE_SIGPIPE_STATUS", "PORTAGE_SOCKS5_PROXY",
	"PORTAGE_TMPDIR", "PORTAGE_UPDATE_ENV", "PORTAGE_USERNAME",
	"PORTAGE_VERBOSE", "PORTAGE_WORKDIR_MODE", "PORTAGE_XATTR_EXCLUDE",
	"PORTDIR", "PORTDIR_OVERLAY", "PREROOTPATH", "PYTHONDONTWRITEBYTECODE",
	"REPLACING_VERSIONS", "REPLACED_BY_VERSION",
	"ROOT", "ROOTPATH", "SANDBOX_LOG", "SYSROOT", "T", "TMP", "TMPDIR",
	"USE_EXPAND", "USE_ORDER", "WORKDIR",
	"XARGS", "__PORTAGE_TEST_HARDLINK_LOCKS",
]

# user config variables
environ_whitelist += [
	"DOC_SYMLINKS_DIR", "INSTALL_MASK", "PKG_INSTALL_MASK"
]

environ_whitelist += [
	"A", "AA", "CATEGORY", "P", "PF", "PN", "PR", "PV", "PVR"
]

# misc variables inherited from the calling environment
environ_whitelist += [
	"COLORTERM", "DISPLAY", "EDITOR", "LESS",
	"LESSOPEN", "LOGNAME", "LS_COLORS", "PAGER",
	"TERM", "TERMCAP", "USER",
	'ftp_proxy', 'http_proxy', 'no_proxy',
]

# tempdir settings
environ_whitelist += [
	"TMPDIR", "TEMP", "TMP",
]

# localization settings
environ_whitelist += [
	"LANG", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES",
	"LC_MONETARY", "LC_NUMERIC", "LC_TIME", "LC_PAPER",
	"LC_ALL",
]

# other variables inherited from the calling environment
environ_whitelist += [
	"CVS_RSH", "ECHANGELOG_USER",
	"GPG_AGENT_INFO",
	"SSH_AGENT_PID", "SSH_AUTH_SOCK",
	"STY", "WINDOW", "XAUTHORITY",
]

environ_whitelist = frozenset(environ_whitelist)

environ_whitelist_re = re.compile(r'^(CCACHE_|DISTCC_).*')

# Filter selected variables in the config.environ() method so that
# they don't needlessly propagate down into the ebuild environment.
environ_filter = []

# Exclude anything that could be extremely long here (like SRC_URI)
# since that could cause execve() calls to fail with E2BIG errors. For
# example, see bug #262647.
environ_filter += [
	'DEPEND', 'RDEPEND', 'PDEPEND', 'SRC_URI', 'BDEPEND', 'IDEPEND',
]

# misc variables inherited from the calling environment
environ_filter += [
	"INFOPATH", "MANPATH", "USER",
]

# variables that break bash
environ_filter += [
	"HISTFILE", "POSIXLY_CORRECT",
]

# portage config variables and variables set directly by portage
environ_filter += [
	"ACCEPT_CHOSTS", "ACCEPT_KEYWORDS", "ACCEPT_PROPERTIES",
	"ACCEPT_RESTRICT", "AUTOCLEAN",
	"BINPKG_COMPRESS", "BINPKG_COMPRESS_FLAGS",
	"CLEAN_DELAY", "COLLISION_IGNORE",
	"CONFIG_PROTECT", "CONFIG_PROTECT_MASK",
	"EGENCACHE_DEFAULT_OPTS", "EMERGE_DEFAULT_OPTS",
	"EMERGE_LOG_DIR",
	"EMERGE_WARNING_DELAY",
	"FETCHCOMMAND", "FETCHCOMMAND_FTP",
	"FETCHCOMMAND_HTTP", "FETCHCOMMAND_HTTPS",
	"FETCHCOMMAND_RSYNC", "FETCHCOMMAND_SFTP",
	"GENTOO_MIRRORS", "NOCONFMEM", "O",
	"PORTAGE_BACKGROUND", "PORTAGE_BACKGROUND_UNMERGE",
	"PORTAGE_BINHOST", "PORTAGE_BINPKG_FORMAT",
	"PORTAGE_BUILDDIR_LOCKED",
	"PORTAGE_CHECKSUM_FILTER",
	"PORTAGE_ELOG_CLASSES",
	"PORTAGE_ELOG_MAILFROM", "PORTAGE_ELOG_MAILSUBJECT",
	"PORTAGE_ELOG_MAILURI", "PORTAGE_ELOG_SYSTEM",
	"PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS", "PORTAGE_FETCH_RESUME_MIN_SIZE",
	"PORTAGE_GPG_DIR",
	"PORTAGE_GPG_KEY", "PORTAGE_GPG_SIGNING_COMMAND",
	"PORTAGE_IONICE_COMMAND",
	"PORTAGE_PACKAGE_EMPTY_ABORT",
	"PORTAGE_REPO_DUPLICATE_WARN",
	"PORTAGE_RO_DISTDIRS",
	"PORTAGE_RSYNC_EXTRA_OPTS", "PORTAGE_RSYNC_OPTS",
	"PORTAGE_RSYNC_RETRIES", "PORTAGE_SSH_OPTS", "PORTAGE_SYNC_STALE",
	"PORTAGE_USE", "PORTAGE_LOG_FILTER_FILE_CMD",
	"PORTAGE_LOGDIR", "PORTAGE_LOGDIR_CLEAN",
	"QUICKPKG_DEFAULT_OPTS", "REPOMAN_DEFAULT_OPTS",
	"RESUMECOMMAND", "RESUMECOMMAND_FTP",
	"RESUMECOMMAND_HTTP", "RESUMECOMMAND_HTTPS",
	"RESUMECOMMAND_RSYNC", "RESUMECOMMAND_SFTP",
	"SIGNED_OFF_BY",
	"UNINSTALL_IGNORE", "USE_EXPAND_HIDDEN", "USE_ORDER",
	"__PORTAGE_HELPER"
]

# No longer supported variables
environ_filter += [
	"SYNC"
]

environ_filter = frozenset(environ_filter)

# Variables that are not allowed to have per-repo or per-package
# settings.
global_only_vars = frozenset([
	"CONFIG_PROTECT",
])

default_globals = {
	'ACCEPT_PROPERTIES':        '*',
	'PORTAGE_BZIP2_COMMAND':    'bzip2',
}

validate_commands = ('PORTAGE_BZIP2_COMMAND', 'PORTAGE_BUNZIP2_COMMAND',
	'PORTAGE_LOG_FILTER_FILE_CMD',
)

# To enhance usability, make some vars case insensitive
# by forcing them to lower case.
case_insensitive_vars = ('AUTOCLEAN', 'NOCOLOR',)
