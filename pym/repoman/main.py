#!/usr/bin/python -bO
# -*- coding:utf-8 -*-
# Copyright 1999-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function, unicode_literals

import io
import logging
import sys

# import our centrally initialized portage instance
from repoman._portage import portage
portage._internal_caller = True
portage._disable_legacy_globals()


from portage import os
import portage.checksum
import portage.const
import portage.repository.config
from portage.output import create_color_func, nocolor
from portage.output import ConsoleStyleFile, StyleWriter
from portage.util import formatter

from repoman.actions import Actions
from repoman.argparser import parse_args
from repoman.qa_data import (
	format_qa_output, format_qa_output_column, qahelp,
	qawarnings, qacats)
from repoman.repos import RepoSettings
from repoman.scanner import Scanner
from repoman import utilities
from repoman.modules.vcs.settings import VCSSettings

if sys.hexversion >= 0x3000000:
	basestring = str

bad = create_color_func("BAD")

# A sane umask is needed for files that portage creates.
os.umask(0o22)

LOGLEVEL = logging.WARNING
portage.util.initialize_logger(LOGLEVEL)


def repoman_main(argv):
	config_root = os.environ.get("PORTAGE_CONFIGROOT")
	repoman_settings = portage.config(config_root=config_root, local_config=False)

	if repoman_settings.get("NOCOLOR", "").lower() in ("yes", "true") or \
		repoman_settings.get('TERM') == 'dumb' or \
		not sys.stdout.isatty():
		nocolor()

	options, arguments = parse_args(
		sys.argv, qahelp, repoman_settings.get("REPOMAN_DEFAULT_OPTS", ""))

	if options.version:
		print("Portage", portage.VERSION)
		sys.exit(0)

	logger = logging.getLogger()

	if options.verbosity > 0:
		logger.setLevel(LOGLEVEL - 10 * options.verbosity)
	else:
		logger.setLevel(LOGLEVEL)

	if options.experimental_inherit == 'y':
		# This is experimental, so it's non-fatal.
		qawarnings.add("inherit.missing")

	# Set this to False when an extraordinary issue (generally
	# something other than a QA issue) makes it impossible to
	# commit (like if Manifest generation fails).
	can_force = True

	portdir, portdir_overlay, mydir = utilities.FindPortdir(repoman_settings)
	if portdir is None:
		sys.exit(1)

	myreporoot = os.path.basename(portdir_overlay)
	myreporoot += mydir[len(portdir_overlay):]

	vcs_settings = VCSSettings(options, repoman_settings)

	repo_settings = RepoSettings(
		config_root, portdir, portdir_overlay,
		repoman_settings, vcs_settings, options, qawarnings)
	repoman_settings = repo_settings.repoman_settings

	if 'digest' in repoman_settings.features and options.digest != 'n':
		options.digest = 'y'

	logging.debug("vcs: %s" % (vcs_settings.vcs,))
	logging.debug("repo config: %s" % (repo_settings.repo_config,))
	logging.debug("options: %s" % (options,))

	# It's confusing if these warnings are displayed without the user
	# being told which profile they come from, so disable them.
	env = os.environ.copy()
	env['FEATURES'] = env.get('FEATURES', '') + ' -unknown-features-warn'

	# Perform the main checks
	scanner = Scanner(repo_settings, myreporoot, config_root, options,
					vcs_settings, mydir, env)
	can_force = scanner.scan_pkgs(can_force)

	commitmessage = None

	if options.if_modified == "y" and len(scanner.effective_scanlist) < 1:
		logging.warning("--if-modified is enabled, but no modified packages were found!")

	result = {
		# fail will be true if we have failed in at least one non-warning category
		'fail': 0,
		# warn will be true if we tripped any warnings
		'warn': 0,
		# full will be true if we should print a "repoman full" informational message
		'full': options.mode != 'full',
	}

	# early out for manifest generation
	if options.mode == "manifest":
		sys.exit(result['fail'])

	for x in qacats:
		if x not in vcs_settings.qatracker.fails:
			continue
		result['warn'] = 1
		if x not in qawarnings:
			result['fail'] = 1

	if result['fail'] or \
		(result['warn'] and not (options.quiet or options.mode == "scan")):
		result['full'] = 0

	# Save QA output so that it can be conveniently displayed
	# in $EDITOR while the user creates a commit message.
	# Otherwise, the user would not be able to see this output
	# once the editor has taken over the screen.
	qa_output = io.StringIO()
	style_file = ConsoleStyleFile(sys.stdout)
	if options.mode == 'commit' and \
		(not commitmessage or not commitmessage.strip()):
		style_file.write_listener = qa_output
	console_writer = StyleWriter(file=style_file, maxcol=9999)
	console_writer.style_listener = style_file.new_styles

	f = formatter.AbstractFormatter(console_writer)

	format_outputs = {
		'column': format_qa_output_column,
		'default': format_qa_output
	}

	format_output = format_outputs.get(
		options.output_style, format_outputs['default'])
	format_output(f, vcs_settings.qatracker.fails, result['full'],
		result['fail'], options, qawarnings)

	style_file.flush()
	del console_writer, f, style_file
	qa_output = qa_output.getvalue()
	qa_output = qa_output.splitlines(True)

	# output the results
	actions = Actions(repo_settings, options, scanner, vcs_settings)
	if actions.inform(can_force, result):
		# perform any other actions
		actions.perform(qa_output)

	sys.exit(0)
