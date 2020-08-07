# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import textwrap

import portage
from portage import os
from portage.emaint.modules.logs.logs import CleanLogs
from portage.news import count_unread_news, display_news_notifications
from portage.output import colorize
from portage.util._dyn_libs.display_preserved_libs import \
	display_preserved_libs
from portage.util._info_files import chk_updated_info_files

from .chk_updated_cfg_files import chk_updated_cfg_files
from .emergelog import emergelog
from ._flush_elog_mod_echo import _flush_elog_mod_echo

def clean_logs(settings):

	if "clean-logs" not in settings.features:
		return

	logdir = settings.get("PORTAGE_LOGDIR")
	if logdir is None or not os.path.isdir(logdir):
		return

	cleanlogs = CleanLogs()
	returncode, msgs = cleanlogs.clean(settings=settings)
	if not returncode:
		out = portage.output.EOutput()
		for msg in msgs:
			out.eerror(msg)

def display_news_notification(root_config, myopts):
	if "news" not in root_config.settings.features:
		return False
	portdb = root_config.trees["porttree"].dbapi
	vardb = root_config.trees["vartree"].dbapi
	news_counts = count_unread_news(portdb, vardb)
	if all(v == 0 for v in news_counts.values()):
		return False
	display_news_notifications(news_counts)
	return True

def show_depclean_suggestion():
	out = portage.output.EOutput()
	msg = "After world updates, it is important to remove " + \
		"obsolete packages with emerge --depclean. Refer " + \
		"to `man emerge` for more information."
	for line in textwrap.wrap(msg, 72):
		out.ewarn(line)

def post_emerge(myaction, myopts, myfiles,
	target_root, trees, mtimedb, retval):
	"""
	Misc. things to run at the end of a merge session.

	Update Info Files
	Update Config Files
	Update News Items
	Commit mtimeDB
	Display preserved libs warnings

	@param myaction: The action returned from parse_opts()
	@type myaction: String
	@param myopts: emerge options
	@type myopts: dict
	@param myfiles: emerge arguments
	@type myfiles: list
	@param target_root: The target EROOT for myaction
	@type target_root: String
	@param trees: A dictionary mapping each ROOT to it's package databases
	@type trees: dict
	@param mtimedb: The mtimeDB to store data needed across merge invocations
	@type mtimedb: MtimeDB class instance
	@param retval: Emerge's return value
	@type retval: Int
	"""

	root_config = trees[target_root]["root_config"]
	vardbapi = trees[target_root]['vartree'].dbapi
	settings = vardbapi.settings
	info_mtimes = mtimedb["info"]

	# Load the most current variables from ${ROOT}/etc/profile.env
	settings.unlock()
	settings.reload()
	settings.regenerate()
	settings.lock()

	config_protect = portage.util.shlex_split(
		settings.get("CONFIG_PROTECT", ""))
	infodirs = settings.get("INFOPATH","").split(":") + \
		settings.get("INFODIR","").split(":")

	os.chdir("/")

	if retval == os.EX_OK:
		exit_msg = " *** exiting successfully."
	else:
		exit_msg = " *** exiting unsuccessfully with status '%s'." % retval
	emergelog("notitles" not in settings.features, exit_msg)

	_flush_elog_mod_echo()

	if not vardbapi._pkgs_changed:
		# GLEP 42 says to display news *after* an emerge --pretend
		if "--pretend" in myopts:
			display_news_notification(root_config, myopts)
		# If vdb state has not changed then there's nothing else to do.
		return

	vdb_path = os.path.join(root_config.settings['EROOT'], portage.VDB_PATH)
	portage.util.ensure_dirs(vdb_path)
	vdb_lock = None
	if os.access(vdb_path, os.W_OK) and not "--pretend" in myopts:
		vardbapi.lock()
		vdb_lock = True

	if vdb_lock:
		try:
			if "noinfo" not in settings.features:
				chk_updated_info_files(target_root,
					infodirs, info_mtimes)
			mtimedb.commit()
		finally:
			if vdb_lock:
				vardbapi.unlock()

	# Explicitly load and prune the PreservedLibsRegistry in order
	# to ensure that we do not display stale data.
	vardbapi._plib_registry.load()

	if vardbapi._plib_registry.hasEntries():
		if "--quiet" in myopts:
			print()
			print(colorize("WARN", "!!!") + " existing preserved libs found")
		else:
			print()
			print(colorize("WARN", "!!!") + " existing preserved libs:")
			display_preserved_libs(vardbapi)
			print("Use " + colorize("GOOD", "emerge @preserved-rebuild") +
				" to rebuild packages using these libraries")

	chk_updated_cfg_files(settings['EROOT'], config_protect)

	display_news_notification(root_config, myopts)

	postemerge = os.path.join(settings["PORTAGE_CONFIGROOT"],
		portage.USER_CONFIG_PATH, "bin", "post_emerge")
	if os.access(postemerge, os.X_OK):
		hook_retval = portage.process.spawn(
						[postemerge], env=settings.environ())
		if hook_retval != os.EX_OK:
			portage.util.writemsg_level(
				" %s spawn failed of %s\n" %
				(colorize("BAD", "*"), postemerge,),
				level=logging.ERROR, noiselevel=-1)

	clean_logs(settings)

	if "--quiet" not in myopts and \
		myaction is None and "@world" in myfiles:
		show_depclean_suggestion()
