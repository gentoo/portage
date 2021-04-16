# Copyright 2013-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import logging
import sys

import portage
from portage import os
from portage.package.ebuild.fetch import ContentHashLayout
from portage.util import normalize_path, _recursive_file_list
from portage.util._async.run_main_scheduler import run_main_scheduler
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop
from .Config import Config
from .MirrorDistTask import MirrorDistTask


seconds_per_day = 24 * 60 * 60

common_options = (
	{
		"longopt"  : "--dry-run",
		"help"     : "perform a trial run with no changes made (usually combined "
			"with --verbose)",
		"action"   : "store_true"
	},
	{
		"longopt"  : "--verbose",
		"shortopt" : "-v",
		"help"     : "display extra information on stderr "
			"(multiple occurences increase verbosity)",
		"action"   : "count",
		"default"  : 0,
	},
	{
		"longopt"  : "--ignore-default-opts",
		"help"     : "do not use the EMIRRORDIST_DEFAULT_OPTS environment variable",
		"action"   : "store_true"
	},
	{
		"longopt"  : "--distfiles",
		"help"     : "distfiles directory to use (required)",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--jobs",
		"shortopt" : "-j",
		"help"     : "number of concurrent jobs to run",
		"type"     : int
	},
	{
		"longopt"  : "--load-average",
		"shortopt" : "-l",
		"help"     : "load average limit for spawning of new concurrent jobs",
		"metavar"  : "LOAD",
		"type"     : float
	},
	{
		"longopt"  : "--tries",
		"help"     : "maximum number of tries per file, 0 means unlimited (default is 10)",
		"default"  : 10,
		"type"     : int
	},
	{
		"longopt"  : "--repo",
		"help"     : "name of repo to operate on"
	},
	{
		"longopt"  : "--config-root",
		"help"     : "location of portage config files",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--repositories-configuration",
		"help"     : "override configuration of repositories (in format of repos.conf)"
	},
	{
		"longopt"  : "--strict-manifests",
		"help"     : "manually override \"strict\" FEATURES setting",
		"choices"  : ("y", "n"),
		"metavar"  : "<y|n>",
	},
	{
		"longopt"  : "--failure-log",
		"help"     : "log file for fetch failures, with tab-delimited "
			"output, for reporting purposes",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--success-log",
		"help"     : "log file for fetch successes, with tab-delimited "
			"output, for reporting purposes",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--scheduled-deletion-log",
		"help"     : "log file for scheduled deletions, with tab-delimited "
			"output, for reporting purposes",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--delete",
		"help"     : "enable deletion of unused distfiles",
		"action"   : "store_true"
	},
	{
		"longopt"  : "--deletion-db",
		"help"     : "database file used to track lifetime of files "
			"scheduled for delayed deletion",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--deletion-delay",
		"help"     : "delay time for deletion, measured in seconds",
		"metavar"  : "SECONDS"
	},
	{
		"longopt"  : "--temp-dir",
		"help"     : "temporary directory for downloads",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--mirror-overrides",
		"help"     : "file holding a list of mirror overrides",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--mirror-skip",
		"help"     : "comma delimited list of mirror targets to skip "
			"when fetching"
	},
	{
		"longopt"  : "--restrict-mirror-exemptions",
		"help"     : "comma delimited list of mirror targets for which to "
			"ignore RESTRICT=\"mirror\""
	},
	{
		"longopt"  : "--verify-existing-digest",
		"help"     : "use digest as a verification of whether existing "
			"distfiles are valid",
		"action"   : "store_true"
	},
	{
		"longopt"  : "--distfiles-local",
		"help"     : "distfiles-local directory to use",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--distfiles-db",
		"help"     : "database file used to track which ebuilds a "
			"distfile belongs to",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--content-db",
		"help"     : "database file used to map content digests to"
			"distfiles names (required for content-hash layout)",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--recycle-dir",
		"help"     : "directory for extended retention of files that "
			"are removed from distdir with the --delete option",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--recycle-db",
		"help"     : "database file used to track lifetime of files "
			"in recycle dir",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--recycle-deletion-delay",
		"help"     : "delay time for deletion of unused files from "
			"recycle dir, measured in seconds (defaults to "
			"the equivalent of 60 days)",
		"default"  : 60 * seconds_per_day,
		"metavar"  : "SECONDS",
		"type"     : int
	},
	{
		"longopt"  : "--fetch-log-dir",
		"help"     : "directory for individual fetch logs",
		"metavar"  : "DIR"
	},
	{
		"longopt"  : "--whitelist-from",
		"help"     : "specifies a file containing a list of files to "
			"whitelist, one per line, # prefixed lines ignored",
		"action"   : "append",
		"metavar"  : "FILE"
	},
	{
		"longopt"  : "--symlinks",
		"help"     : "use symlinks rather than hardlinks for linking "
			"distfiles between layouts",
		"action"   : "store_true"
	},
	{
		"longopt"  : "--layout-conf",
		"help"     : "specifies layout.conf file to use instead of "
			"the one present in the distfiles directory",
		"metavar"  : "FILE"
	},
)

def parse_args(args):
	description = "emirrordist - a fetch tool for mirroring " \
		"of package distfiles"
	usage = "emirrordist [options] <action>"
	parser = argparse.ArgumentParser(description=description, usage=usage)

	actions = parser.add_argument_group('Actions')
	actions.add_argument("--version",
		action="store_true",
		help="display portage version and exit")
	actions.add_argument("--mirror",
		action="store_true",
		help="mirror distfiles for the selected repository")

	common = parser.add_argument_group('Common options')
	for opt_info in common_options:
		opt_pargs = [opt_info["longopt"]]
		if opt_info.get("shortopt"):
			opt_pargs.append(opt_info["shortopt"])
		opt_kwargs = {"help" : opt_info["help"]}
		for k in ("action", "choices", "default", "metavar", "type"):
			if k in opt_info:
				opt_kwargs[k] = opt_info[k]
		common.add_argument(*opt_pargs, **opt_kwargs)

	options, args = parser.parse_known_args(args)

	return (parser, options, args)

def emirrordist_main(args):

	# The calling environment is ignored, so the program is
	# completely controlled by commandline arguments.
	env = {}

	if not sys.stdout.isatty():
		portage.output.nocolor()
		env['NOCOLOR'] = 'true'

	parser, options, args = parse_args(args)

	if options.version:
		sys.stdout.write("Portage %s\n" % portage.VERSION)
		return os.EX_OK

	config_root = options.config_root

	if options.repositories_configuration is not None:
		env['PORTAGE_REPOSITORIES'] = options.repositories_configuration

	settings = portage.config(config_root=config_root,
		local_config=False, env=env)

	default_opts = None
	if not options.ignore_default_opts:
		default_opts = settings.get('EMIRRORDIST_DEFAULT_OPTS', '').split()

	if default_opts:
		parser, options, args = parse_args(default_opts + args)

		settings = portage.config(config_root=config_root,
			local_config=False, env=env)

	if options.repo is None:
		if len(settings.repositories.prepos) == 2:
			for repo in settings.repositories:
				if repo.name != "DEFAULT":
					options.repo = repo.name
					break

		if options.repo is None:
			parser.error("--repo option is required")

	repo_path = settings.repositories.treemap.get(options.repo)
	if repo_path is None:
		parser.error("Unable to locate repository named '%s'" % (options.repo,))

	if options.jobs is not None:
		options.jobs = int(options.jobs)

	if options.load_average is not None:
		options.load_average = float(options.load_average)

	if options.failure_log is not None:
		options.failure_log = normalize_path(
			os.path.abspath(options.failure_log))

		parent_dir = os.path.dirname(options.failure_log)
		if not (os.path.isdir(parent_dir) and
			os.access(parent_dir, os.W_OK|os.X_OK)):
			parser.error(("--failure-log '%s' parent is not a "
				"writable directory") % options.failure_log)

	if options.success_log is not None:
		options.success_log = normalize_path(
			os.path.abspath(options.success_log))

		parent_dir = os.path.dirname(options.success_log)
		if not (os.path.isdir(parent_dir) and
			os.access(parent_dir, os.W_OK|os.X_OK)):
			parser.error(("--success-log '%s' parent is not a "
				"writable directory") % options.success_log)

	if options.scheduled_deletion_log is not None:
		options.scheduled_deletion_log = normalize_path(
			os.path.abspath(options.scheduled_deletion_log))

		parent_dir = os.path.dirname(options.scheduled_deletion_log)
		if not (os.path.isdir(parent_dir) and
			os.access(parent_dir, os.W_OK|os.X_OK)):
			parser.error(("--scheduled-deletion-log '%s' parent is not a "
				"writable directory") % options.scheduled_deletion_log)

		if options.deletion_db is None:
			parser.error("--scheduled-deletion-log requires --deletion-db")

	if options.deletion_delay is not None:
		options.deletion_delay = int(options.deletion_delay)
		if options.deletion_db is None:
			parser.error("--deletion-delay requires --deletion-db")

	if options.deletion_db is not None:
		if options.deletion_delay is None:
			parser.error("--deletion-db requires --deletion-delay")
		options.deletion_db = normalize_path(
			os.path.abspath(options.deletion_db))

	if options.temp_dir is not None:
		options.temp_dir = normalize_path(
			os.path.abspath(options.temp_dir))

		if not (os.path.isdir(options.temp_dir) and
			os.access(options.temp_dir, os.W_OK|os.X_OK)):
			parser.error(("--temp-dir '%s' is not a "
				"writable directory") % options.temp_dir)

	if options.distfiles is not None:
		options.distfiles = normalize_path(
			os.path.abspath(options.distfiles))

		if not (os.path.isdir(options.distfiles) and
			os.access(options.distfiles, os.W_OK|os.X_OK)):
			parser.error(("--distfiles '%s' is not a "
				"writable directory") % options.distfiles)
	else:
		parser.error("missing required --distfiles parameter")

	if options.mirror_overrides is not None:
		options.mirror_overrides = normalize_path(
			os.path.abspath(options.mirror_overrides))

		if not (os.access(options.mirror_overrides, os.R_OK) and
			os.path.isfile(options.mirror_overrides)):
			parser.error(
				"--mirror-overrides-file '%s' is not a readable file" %
				options.mirror_overrides)

	if options.distfiles_local is not None:
		options.distfiles_local = normalize_path(
			os.path.abspath(options.distfiles_local))

		if not (os.path.isdir(options.distfiles_local) and
			os.access(options.distfiles_local, os.W_OK|os.X_OK)):
			parser.error(("--distfiles-local '%s' is not a "
				"writable directory") % options.distfiles_local)

	if options.distfiles_db is not None:
		options.distfiles_db = normalize_path(
			os.path.abspath(options.distfiles_db))

	if options.tries is not None:
		options.tries = int(options.tries)

	if options.recycle_dir is not None:
		options.recycle_dir = normalize_path(
			os.path.abspath(options.recycle_dir))
		if not (os.path.isdir(options.recycle_dir) and
			os.access(options.recycle_dir, os.W_OK|os.X_OK)):
			parser.error(("--recycle-dir '%s' is not a "
				"writable directory") % options.recycle_dir)

	if options.recycle_db is not None:
		if options.recycle_dir is None:
			parser.error("--recycle-db requires "
				"--recycle-dir to be specified")
		options.recycle_db = normalize_path(
			os.path.abspath(options.recycle_db))

	if options.recycle_deletion_delay is not None:
		options.recycle_deletion_delay = \
			int(options.recycle_deletion_delay)

	if options.fetch_log_dir is not None:
		options.fetch_log_dir = normalize_path(
			os.path.abspath(options.fetch_log_dir))

		if not (os.path.isdir(options.fetch_log_dir) and
			os.access(options.fetch_log_dir, os.W_OK|os.X_OK)):
			parser.error(("--fetch-log-dir '%s' is not a "
				"writable directory") % options.fetch_log_dir)

	if options.whitelist_from:
		normalized_paths = []
		for x in options.whitelist_from:
			path = normalize_path(os.path.abspath(x))
			if not os.access(path, os.R_OK):
				parser.error("--whitelist-from '%s' is not readable" % x)
			if os.path.isfile(path):
				normalized_paths.append(path)
			elif os.path.isdir(path):
				for file in _recursive_file_list(path):
					if not os.access(file, os.R_OK):
						parser.error("--whitelist-from '%s' directory contains not readable file '%s'" % (x, file))
					normalized_paths.append(file)
			else:
				parser.error("--whitelist-from '%s' is not a regular file or a directory" % x)
		options.whitelist_from = normalized_paths

	if options.strict_manifests is not None:
		if options.strict_manifests == "y":
			settings.features.add("strict")
		else:
			settings.features.discard("strict")

	settings.lock()

	portdb = portage.portdbapi(mysettings=settings)

	# Limit ebuilds to the specified repo.
	portdb.porttrees = [repo_path]

	portage.util.initialize_logger()

	if options.verbose > 0:
		l = logging.getLogger()
		l.setLevel(l.getEffectiveLevel() - 10 * options.verbose)

	with Config(options, portdb,
		SchedulerInterface(global_event_loop())) as config:

		if not options.mirror:
			parser.error('No action specified')

		if options.delete and config.content_db is None:
			for layout in config.layouts:
				if isinstance(layout, ContentHashLayout):
					parser.error("content-hash layout requires "
						"--content-db to be specified")

		returncode = os.EX_OK

		if options.mirror:
			signum = run_main_scheduler(MirrorDistTask(config))
			if signum is not None:
				sys.exit(128 + signum)

	return returncode
