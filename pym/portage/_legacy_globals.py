# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage
from portage import os
from portage.const import CACHE_PATH, PROFILE_PATH

_legacy_globals = {}

def _get_legacy_global(name):
	global _legacy_globals
	target = _legacy_globals.get(name, _legacy_globals)
	if target is not _legacy_globals:
		return target

	if name == 'portdb':
		portage.portdb = portage.db[portage.root]["porttree"].dbapi
		_legacy_globals[name] = portage.portdb
		return _legacy_globals[name]
	elif name in ('mtimedb', 'mtimedbfile'):
		portage.mtimedbfile = os.path.join(portage.root,
			CACHE_PATH, "mtimedb")
		_legacy_globals['mtimedbfile'] = portage.mtimedbfile
		portage.mtimedb = portage.MtimeDB(portage.mtimedbfile)
		_legacy_globals['mtimedb'] = portage.mtimedb
		return _legacy_globals[name]

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, "/")

	portage._initializing_globals = True
	portage.db = portage.create_trees(**kwargs)
	_legacy_globals['db'] = portage.db
	del portage._initializing_globals

	settings = portage.db["/"]["vartree"].settings

	for root in portage.db:
		if root != "/":
			settings = portage.db[root]["vartree"].settings
			break

	portage.output._init(config_root=settings['PORTAGE_CONFIGROOT'])

	portage.settings = settings
	_legacy_globals['settings'] = settings

	portage.root = root
	_legacy_globals['root'] = root

	# COMPATIBILITY
	# These attributes should not be used within
	# Portage under any circumstances.

	portage.archlist = settings.archlist()
	_legacy_globals['archlist'] = portage.archlist

	portage.features = settings.features
	_legacy_globals['features'] = portage.features

	portage.groups = settings["ACCEPT_KEYWORDS"].split()
	_legacy_globals['groups'] = portage.groups

	portage.pkglines = settings.packages
	_legacy_globals['pkglines'] = portage.pkglines

	portage.selinux_enabled = settings.selinux_enabled()
	_legacy_globals['selinux_enabled'] = portage.selinux_enabled

	portage.thirdpartymirrors = settings.thirdpartymirrors()
	_legacy_globals['thirdpartymirrors'] = portage.thirdpartymirrors

	portage.usedefaults = settings.use_defs
	_legacy_globals['usedefaults'] = portage.usedefaults

	profiledir = os.path.join(settings["PORTAGE_CONFIGROOT"], PROFILE_PATH)
	if not os.path.isdir(profiledir):
		profiledir = None
	portage.profiledir = profiledir
	_legacy_globals['profiledir'] = portage.profiledir

	return _legacy_globals[name]
