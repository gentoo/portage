# portage: Constants
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: portage_const.py 3483 2006-06-10 21:40:40Z genone $
import os

# ===========================================================================
# autotool supplied constants.
# ===========================================================================
from portage_const_autotool import *


# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

VDB_PATH                = EPREFIX+"/var/db/pkg"
PRIVATE_PATH            = EPREFIX+"/var/lib/portage"
CACHE_PATH              = EPREFIX+"/var/cache/edb"
DEPCACHE_PATH           = CACHE_PATH+"/dep"

USER_CONFIG_PATH        = EPREFIX+"/etc/portage"
MODULES_FILE_PATH       = USER_CONFIG_PATH+"/modules"
CUSTOM_PROFILE_PATH     = USER_CONFIG_PATH+"/profile"

PORTAGE_BASE_PATH       = PORTAGE_BASE
PORTAGE_BIN_PATH        = PORTAGE_BASE_PATH+"/bin"
PORTAGE_PYM_PATH        = PORTAGE_BASE_PATH+"/pym"
PROFILE_PATH            = EPREFIX+"/etc/make.profile"
LOCALE_DATA_PATH        = PORTAGE_BASE_PATH+"/locale"

EBUILD_SH_BINARY        = PORTAGE_BIN_PATH+"/ebuild.sh"
MISC_SH_BINARY          = PORTAGE_BIN_PATH + "/misc-functions.sh"
SANDBOX_BINARY          = EPREFIX+"/usr/bin/sandbox"
BASH_BINARY             = "bash"
MOVE_BINARY             = "mv"
PRELINK_BINARY          = "prelink"

WORLD_FILE              = PRIVATE_PATH + "/world"
MAKE_CONF_FILE          = EPREFIX+"/etc/make.conf"
MAKE_DEFAULTS_FILE      = PROFILE_PATH + "/make.defaults"
DEPRECATED_PROFILE_FILE = PROFILE_PATH+"/deprecated"
USER_VIRTUALS_FILE      = USER_CONFIG_PATH+"/virtuals"
EBUILD_SH_ENV_FILE      = USER_CONFIG_PATH+"/bashrc"
INVALID_ENV_FILE        = "/etc/spork/is/not/valid/profile.env"
CUSTOM_MIRRORS_FILE     = USER_CONFIG_PATH+"/mirrors"
CONFIG_MEMORY_FILE      = PRIVATE_PATH + "/config"
COLOR_MAP_FILE          = USER_CONFIG_PATH + "/color.map"

REPO_NAME_FILE         = "repo_name"
REPO_NAME_LOC          = "profiles" + "/" + REPO_NAME_FILE

INCREMENTALS=["USE","USE_EXPAND","USE_EXPAND_HIDDEN","FEATURES","ACCEPT_KEYWORDS","ACCEPT_LICENSE","CONFIG_PROTECT_MASK","CONFIG_PROTECT","PRELINK_PATH","PRELINK_PATH_MASK"]
EBUILD_PHASES           = ["setup", "unpack", "compile", "test", "install",
                          "preinst", "postinst", "prerm", "postrm", "other"]

EAPI = "prefix"

HASHING_BLOCKSIZE        = 32768
MANIFEST1_HASH_FUNCTIONS = ["MD5","SHA256","RMD160"]
MANIFEST2_HASH_FUNCTIONS = ["SHA1","SHA256","RMD160"]

MANIFEST2_IDENTIFIERS = ["AUX","MISC","DIST","EBUILD"]
# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================
