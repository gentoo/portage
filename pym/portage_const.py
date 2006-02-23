# portage: Constants
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage_const.py,v 1.3.2.3 2005/04/29 04:56:35 jstubbs Exp $
import os

# ===========================================================================
# autotool supplied constants.
# ===========================================================================
from portage_const_autotool import *


# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

VDB_PATH                = PREFIX+"/var/db/pkg"
PRIVATE_PATH            = PREFIX+"/var/lib/portage"
CACHE_PATH              = PREFIX+"/var/cache/edb"
DEPCACHE_PATH           = CACHE_PATH+"/dep"

USER_CONFIG_PATH        = PREFIX+"/etc/portage"
MODULES_FILE_PATH       = USER_CONFIG_PATH+"/modules"
CUSTOM_PROFILE_PATH     = USER_CONFIG_PATH+"/profile"

PORTAGE_BASE_PATH       = PORTAGE_BASE
PORTAGE_BIN_PATH        = PORTAGE_BASE_PATH+"/bin"
PORTAGE_PYM_PATH        = PORTAGE_BASE_PATH+"/pym"
PROFILE_PATH            = PREFIX+"/etc/make.profile"
LOCALE_DATA_PATH        = PORTAGE_BASE_PATH+"/locale"

EBUILD_SH_BINARY        = "ebuild.sh"
SANDBOX_BINARY          = PREFIX+"/usr/bin/sandbox"
BASH_BINARY             = "bash"
MOVE_BINARY             = "mv"
PRELINK_BINARY          = PREFIX+"/usr/sbin/prelink"

WORLD_FILE              = PRIVATE_PATH+"/world"
MAKE_CONF_FILE          = PREFIX+"/etc/make.conf"
MAKE_DEFAULTS_FILE      = PROFILE_PATH + "/make.defaults"
DEPRECATED_PROFILE_FILE = PROFILE_PATH+"/deprecated"
USER_VIRTUALS_FILE      = USER_CONFIG_PATH+"/virtuals"
EBUILD_SH_ENV_FILE      = USER_CONFIG_PATH+"/bashrc"
INVALID_ENV_FILE        = "/etc/spork/is/not/valid/profile.env"
CUSTOM_MIRRORS_FILE     = USER_CONFIG_PATH+"/mirrors"
CONFIG_MEMORY_FILE      = PRIVATE_PATH + "/config"

INCREMENTALS=["USE","USE_EXPAND","USE_EXPAND_HIDDEN","FEATURES","ACCEPT_KEYWORDS","ACCEPT_LICENSE","CONFIG_PROTECT_MASK","CONFIG_PROTECT","PRELINK_PATH","PRELINK_PATH_MASK"]
STICKIES=["KEYWORDS_ACCEPT","USE","CFLAGS","CXXFLAGS","MAKEOPTS","EXTRA_ECONF","EXTRA_EINSTALL","EXTRA_EMAKE"]
EBUILD_PHASES			= ["setup","unpack","compile","test","install","preinst","postinst","prerm","postrm"]

DEFAULT_PATH = ":".join(map(lambda x: os.path.normpath(os.path.join(PREFIX, x)), ["sbin", "usr/sbin", "bin", "usr/bin"]))

EAPI = "prefix"

HASHING_BLOCKSIZE		= 32768
# Disabling until behaviour when missing the relevant python module is
# corrected.  #116485
MANIFEST1_HASH_FUNCTIONS = ["MD5","SHA256","RMD160"]

# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================

