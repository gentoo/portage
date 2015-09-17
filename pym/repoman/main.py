#!/usr/bin/python -bO
# Copyright 1999-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function, unicode_literals

import errno
import io
import logging
import re
import signal
import subprocess
import sys
import tempfile
import platform
from itertools import chain

from os import path as osp
if osp.isfile(osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), ".portage_not_installed")):
	pym_path = osp.join(osp.dirname(osp.dirname(osp.realpath(__file__)))) #, "pym")
	sys.path.insert(0, pym_path)
# import our centrally initialized portage instance
from repoman._portage import portage
portage._internal_caller = True
portage._disable_legacy_globals()


from portage import os
from portage import _encodings
from portage import _unicode_encode
from _emerge.UserQuery import UserQuery
import portage.checksum
import portage.const
import portage.repository.config
from portage import cvstree
from portage import util
from portage.process import find_binary, spawn
from portage.output import (
	bold, create_color_func, green, nocolor, red)
from portage.output import ConsoleStyleFile, StyleWriter
from portage.util import formatter
from portage.util import writemsg_level
from portage.package.ebuild.digestgen import digestgen

from repoman.argparser import parse_args
from repoman.checks.ebuilds.checks import checks_init
from repoman.errors import err
from repoman.gpg import gpgsign, need_signature
from repoman.qa_data import (
	format_qa_output, format_qa_output_column, qahelp,
	qawarnings, qacats)
from repoman.repos import RepoSettings
from repoman.scanner import Scanner
from repoman._subprocess import repoman_popen, repoman_getstatusoutput
from repoman import utilities
from repoman.vcs.vcs import (
	git_supports_gpg_sign, vcs_files_to_cps, VCSSettings)


if sys.hexversion >= 0x3000000:
	basestring = str

util.initialize_logger()

bad = create_color_func("BAD")

# A sane umask is needed for files that portage creates.
os.umask(0o22)


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

	if options.experimental_inherit == 'y':
		# This is experimental, so it's non-fatal.
		qawarnings.add("inherit.missing")
		checks_init(experimental_inherit=True)

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
	portdb = repo_settings.portdb

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
	qatracker, can_force = scanner.scan_pkgs(can_force)

	commitmessage = None

	if options.if_modified == "y" and len(scanner.effective_scanlist) < 1:
		logging.warning("--if-modified is enabled, but no modified packages were found!")

	# dofail will be true if we have failed in at least one non-warning category
	dofail = 0
	# dowarn will be true if we tripped any warnings
	dowarn = 0
	# dofull will be true if we should print a "repoman full" informational message
	dofull = options.mode != 'full'

	# early out for manifest generation
	if options.mode == "manifest":
		sys.exit(dofail)

	for x in qacats:
		if x not in qatracker.fails:
			continue
		dowarn = 1
		if x not in qawarnings:
			dofail = 1

	if dofail or \
		(dowarn and not (options.quiet or options.mode == "scan")):
		dofull = 0

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
	format_output(f, qatracker.fails, dofull, dofail, options, qawarnings)

	style_file.flush()
	del console_writer, f, style_file
	qa_output = qa_output.getvalue()
	qa_output = qa_output.splitlines(True)

	suggest_ignore_masked = False
	suggest_include_dev = False

	if scanner.have['pmasked'] and not (options.without_mask or options.ignore_masked):
		suggest_ignore_masked = True
	if scanner.have['dev_keywords'] and not options.include_dev:
		suggest_include_dev = True

	if suggest_ignore_masked or suggest_include_dev:
		print()
		if suggest_ignore_masked:
			print(bold(
				"Note: use --without-mask to check "
				"KEYWORDS on dependencies of masked packages"))

		if suggest_include_dev:
			print(bold(
				"Note: use --include-dev (-d) to check "
				"dependencies for 'dev' profiles"))
		print()

	if options.mode != 'commit':
		if dofull:
			print(bold("Note: type \"repoman full\" for a complete listing."))
		if dowarn and not dofail:
			utilities.repoman_sez(
				"\"You're only giving me a partial QA payment?\n"
				"              I'll take it this time, but I'm not happy.\"")
		elif not dofail:
			utilities.repoman_sez(
				"\"If everyone were like you, I'd be out of business!\"")
		elif dofail:
			print(bad("Please fix these important QA issues first."))
			utilities.repoman_sez(
				"\"Make your QA payment on time"
				" and you'll never see the likes of me.\"\n")
			sys.exit(1)
	else:
		if dofail and can_force and options.force and not options.pretend:
			utilities.repoman_sez(
				" \"You want to commit even with these QA issues?\n"
				"              I'll take it this time, but I'm not happy.\"\n")
		elif dofail:
			if options.force and not can_force:
				print(bad(
					"The --force option has been disabled"
					" due to extraordinary issues."))
			print(bad("Please fix these important QA issues first."))
			utilities.repoman_sez(
				"\"Make your QA payment on time"
				" and you'll never see the likes of me.\"\n")
			sys.exit(1)

		if options.pretend:
			utilities.repoman_sez(
				"\"So, you want to play it safe. Good call.\"\n")

		myunadded = []
		if vcs_settings.vcs == "cvs":
			try:
				myvcstree = portage.cvstree.getentries("./", recursive=1)
				myunadded = portage.cvstree.findunadded(
					myvcstree, recursive=1, basedir="./")
			except SystemExit as e:
				raise  # TODO propagate this
			except:
				err("Error retrieving CVS tree; exiting.")
		if vcs_settings.vcs == "svn":
			try:
				with repoman_popen("svn status --no-ignore") as f:
					svnstatus = f.readlines()
				myunadded = [
					"./" + elem.rstrip().split()[1]
					for elem in svnstatus
					if elem.startswith("?") or elem.startswith("I")]
			except SystemExit as e:
				raise  # TODO propagate this
			except:
				err("Error retrieving SVN info; exiting.")
		if vcs_settings.vcs == "git":
			# get list of files not under version control or missing
			myf = repoman_popen("git ls-files --others")
			myunadded = ["./" + elem[:-1] for elem in myf]
			myf.close()
		if vcs_settings.vcs == "bzr":
			try:
				with repoman_popen("bzr status -S .") as f:
					bzrstatus = f.readlines()
				myunadded = [
					"./" + elem.rstrip().split()[1].split('/')[-1:][0]
					for elem in bzrstatus
					if elem.startswith("?") or elem[0:2] == " D"]
			except SystemExit as e:
				raise  # TODO propagate this
			except:
				err("Error retrieving bzr info; exiting.")
		if vcs_settings.vcs == "hg":
			with repoman_popen("hg status --no-status --unknown .") as f:
				myunadded = f.readlines()
			myunadded = ["./" + elem.rstrip() for elem in myunadded]

			# Mercurial doesn't handle manually deleted files as removed from
			# the repository, so the user need to remove them before commit,
			# using "hg remove [FILES]"
			with repoman_popen("hg status --no-status --deleted .") as f:
				mydeleted = f.readlines()
			mydeleted = ["./" + elem.rstrip() for elem in mydeleted]

		myautoadd = []
		if myunadded:
			for x in range(len(myunadded) - 1, -1, -1):
				xs = myunadded[x].split("/")
				if repo_settings.repo_config.find_invalid_path_char(myunadded[x]) != -1:
					# The Manifest excludes this file,
					# so it's safe to ignore.
					del myunadded[x]
				elif xs[-1] == "files":
					print("!!! files dir is not added! Please correct this.")
					sys.exit(-1)
				elif xs[-1] == "Manifest":
					# It's a manifest... auto add
					myautoadd += [myunadded[x]]
					del myunadded[x]

		if myunadded:
			print(red(
				"!!! The following files are in your local tree"
				" but are not added to the master"))
			print(red(
				"!!! tree. Please remove them from the local tree"
				" or add them to the master tree."))
			for x in myunadded:
				print("   ", x)
			print()
			print()
			sys.exit(1)

		if vcs_settings.vcs == "hg" and mydeleted:
			print(red(
				"!!! The following files are removed manually"
				" from your local tree but are not"))
			print(red(
				"!!! removed from the repository."
				" Please remove them, using \"hg remove [FILES]\"."))
			for x in mydeleted:
				print("   ", x)
			print()
			print()
			sys.exit(1)

		if vcs_settings.vcs == "cvs":
			mycvstree = cvstree.getentries("./", recursive=1)
			mychanged = cvstree.findchanged(mycvstree, recursive=1, basedir="./")
			mynew = cvstree.findnew(mycvstree, recursive=1, basedir="./")
			myremoved = portage.cvstree.findremoved(mycvstree, recursive=1, basedir="./")
			bin_blob_pattern = re.compile("^-kb$")
			no_expansion = set(portage.cvstree.findoption(
				mycvstree, bin_blob_pattern, recursive=1, basedir="./"))

		if vcs_settings.vcs == "svn":
			with repoman_popen("svn status") as f:
				svnstatus = f.readlines()
			mychanged = [
				"./" + elem.split()[-1:][0]
				for elem in svnstatus
				if (elem[:1] in "MR" or elem[1:2] in "M")]
			mynew = [
				"./" + elem.split()[-1:][0]
				for elem in svnstatus
				if elem.startswith("A")]
			myremoved = [
				"./" + elem.split()[-1:][0]
				for elem in svnstatus
				if elem.startswith("D")]

			# Subversion expands keywords specified in svn:keywords properties.
			with repoman_popen("svn propget -R svn:keywords") as f:
				props = f.readlines()
			expansion = dict(
				("./" + prop.split(" - ")[0], prop.split(" - ")[1].split())
				for prop in props if " - " in prop)

		elif vcs_settings.vcs == "git":
			with repoman_popen(
				"git diff-index --name-only "
				"--relative --diff-filter=M HEAD") as f:
				mychanged = f.readlines()
			mychanged = ["./" + elem[:-1] for elem in mychanged]

			with repoman_popen(
				"git diff-index --name-only "
				"--relative --diff-filter=A HEAD") as f:
				mynew = f.readlines()
			mynew = ["./" + elem[:-1] for elem in mynew]

			with repoman_popen(
				"git diff-index --name-only "
				"--relative --diff-filter=D HEAD") as f:
				myremoved = f.readlines()
			myremoved = ["./" + elem[:-1] for elem in myremoved]

		if vcs_settings.vcs == "bzr":
			with repoman_popen("bzr status -S .") as f:
				bzrstatus = f.readlines()
			mychanged = [
				"./" + elem.split()[-1:][0].split('/')[-1:][0]
				for elem in bzrstatus
				if elem and elem[1:2] == "M"]
			mynew = [
				"./" + elem.split()[-1:][0].split('/')[-1:][0]
				for elem in bzrstatus
				if elem and (elem[1:2] in "NK" or elem[0:1] == "R")]
			myremoved = [
				"./" + elem.split()[-1:][0].split('/')[-1:][0]
				for elem in bzrstatus
				if elem.startswith("-")]
			myremoved = [
				"./" + elem.split()[-3:-2][0].split('/')[-1:][0]
				for elem in bzrstatus
				if elem and (elem[1:2] == "K" or elem[0:1] == "R")]
			# Bazaar expands nothing.

		if vcs_settings.vcs == "hg":
			with repoman_popen("hg status --no-status --modified .") as f:
				mychanged = f.readlines()
			mychanged = ["./" + elem.rstrip() for elem in mychanged]

			with repoman_popen("hg status --no-status --added .") as f:
				mynew = f.readlines()
			mynew = ["./" + elem.rstrip() for elem in mynew]

			with repoman_popen("hg status --no-status --removed .") as f:
				myremoved = f.readlines()
			myremoved = ["./" + elem.rstrip() for elem in myremoved]

		if vcs_settings.vcs:
			a_file_is_changed = mychanged or mynew or myremoved
			a_file_is_deleted_hg = vcs_settings.vcs == "hg" and mydeleted

			if not (a_file_is_changed or a_file_is_deleted_hg):
				utilities.repoman_sez(
					"\"Doing nothing is not always good for QA.\"")
				print()
				print("(Didn't find any changed files...)")
				print()
				sys.exit(1)

		# Manifests need to be regenerated after all other commits, so don't commit
		# them now even if they have changed.
		mymanifests = set()
		myupdates = set()
		for f in mychanged + mynew:
			if "Manifest" == os.path.basename(f):
				mymanifests.add(f)
			else:
				myupdates.add(f)
		myupdates.difference_update(myremoved)
		myupdates = list(myupdates)
		mymanifests = list(mymanifests)
		myheaders = []

		commitmessage = options.commitmsg
		if options.commitmsgfile:
			try:
				f = io.open(
					_unicode_encode(
						options.commitmsgfile,
						encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['content'], errors='replace')
				commitmessage = f.read()
				f.close()
				del f
			except (IOError, OSError) as e:
				if e.errno == errno.ENOENT:
					portage.writemsg(
						"!!! File Not Found:"
						" --commitmsgfile='%s'\n" % options.commitmsgfile)
				else:
					raise
			# We've read the content so the file is no longer needed.
			commitmessagefile = None
		if not commitmessage or not commitmessage.strip():
			msg_prefix = ""
			if scanner.repolevel > 1:
				msg_prefix = "/".join(scanner.reposplit[1:]) + ": "

			try:
				editor = os.environ.get("EDITOR")
				if editor and utilities.editor_is_executable(editor):
					commitmessage = utilities.get_commit_message_with_editor(
						editor, message=qa_output, prefix=msg_prefix)
				else:
					commitmessage = utilities.get_commit_message_with_stdin()
			except KeyboardInterrupt:
				logging.fatal("Interrupted; exiting...")
				sys.exit(1)
			if (not commitmessage or not commitmessage.strip()
					or commitmessage.strip() == msg_prefix):
				print("* no commit message?  aborting commit.")
				sys.exit(1)
		commitmessage = commitmessage.rstrip()
		changelog_msg = commitmessage
		portage_version = getattr(portage, "VERSION", None)
		gpg_key = repoman_settings.get("PORTAGE_GPG_KEY", "")
		dco_sob = repoman_settings.get("DCO_SIGNED_OFF_BY", "")
		if portage_version is None:
			sys.stderr.write("Failed to insert portage version in message!\n")
			sys.stderr.flush()
			portage_version = "Unknown"

		report_options = []
		if options.force:
			report_options.append("--force")
		if options.ignore_arches:
			report_options.append("--ignore-arches")
		if scanner.include_arches is not None:
			report_options.append(
				"--include-arches=\"%s\"" %
				" ".join(sorted(scanner.include_arches)))

		if vcs_settings.vcs == "git":
			# Use new footer only for git (see bug #438364).
			commit_footer = "\n\nPackage-Manager: portage-%s" % portage_version
			if report_options:
				commit_footer += "\nRepoMan-Options: " + " ".join(report_options)
			if repo_settings.sign_manifests:
				commit_footer += "\nManifest-Sign-Key: %s" % (gpg_key, )
			if dco_sob:
				commit_footer += "\nSigned-off-by: %s" % (dco_sob, )
		else:
			unameout = platform.system() + " "
			if platform.system() in ["Darwin", "SunOS"]:
				unameout += platform.processor()
			else:
				unameout += platform.machine()
			commit_footer = "\n\n"
			if dco_sob:
				commit_footer += "Signed-off-by: %s\n" % (dco_sob, )
			commit_footer += "(Portage version: %s/%s/%s" % \
				(portage_version, vcs_settings.vcs, unameout)
			if report_options:
				commit_footer += ", RepoMan options: " + " ".join(report_options)
			if repo_settings.sign_manifests:
				commit_footer += ", signed Manifest commit with key %s" % \
					(gpg_key, )
			else:
				commit_footer += ", unsigned Manifest commit"
			commit_footer += ")"

		commitmessage += commit_footer

		broken_changelog_manifests = []
		if options.echangelog in ('y', 'force'):
			logging.info("checking for unmodified ChangeLog files")
			committer_name = utilities.get_committer_name(env=repoman_settings)
			for x in sorted(vcs_files_to_cps(
				chain(myupdates, mymanifests, myremoved),
				scanner.repolevel, scanner.reposplit, scanner.categories)):
				catdir, pkgdir = x.split("/")
				checkdir = repo_settings.repodir + "/" + x
				checkdir_relative = ""
				if scanner.repolevel < 3:
					checkdir_relative = os.path.join(pkgdir, checkdir_relative)
				if scanner.repolevel < 2:
					checkdir_relative = os.path.join(catdir, checkdir_relative)
				checkdir_relative = os.path.join(".", checkdir_relative)

				changelog_path = os.path.join(checkdir_relative, "ChangeLog")
				changelog_modified = changelog_path in scanner.changed.changelogs
				if changelog_modified and options.echangelog != 'force':
					continue

				# get changes for this package
				cdrlen = len(checkdir_relative)
				check_relative = lambda e: e.startswith(checkdir_relative)
				split_relative = lambda e: e[cdrlen:]
				clnew = list(map(split_relative, filter(check_relative, mynew)))
				clremoved = list(map(split_relative, filter(check_relative, myremoved)))
				clchanged = list(map(split_relative, filter(check_relative, mychanged)))

				# Skip ChangeLog generation if only the Manifest was modified,
				# as discussed in bug #398009.
				nontrivial_cl_files = set()
				nontrivial_cl_files.update(clnew, clremoved, clchanged)
				nontrivial_cl_files.difference_update(['Manifest'])
				if not nontrivial_cl_files and options.echangelog != 'force':
					continue

				new_changelog = utilities.UpdateChangeLog(
					checkdir_relative, committer_name, changelog_msg,
					os.path.join(repo_settings.repodir, 'skel.ChangeLog'),
					catdir, pkgdir,
					new=clnew, removed=clremoved, changed=clchanged,
					pretend=options.pretend)
				if new_changelog is None:
					writemsg_level(
						"!!! Updating the ChangeLog failed\n",
						level=logging.ERROR, noiselevel=-1)
					sys.exit(1)

				# if the ChangeLog was just created, add it to vcs
				if new_changelog:
					myautoadd.append(changelog_path)
					# myautoadd is appended to myupdates below
				else:
					myupdates.append(changelog_path)

				if options.ask and not options.pretend:
					# regenerate Manifest for modified ChangeLog (bug #420735)
					repoman_settings["O"] = checkdir
					digestgen(mysettings=repoman_settings, myportdb=portdb)
				else:
					broken_changelog_manifests.append(x)

		if myautoadd:
			print(">>> Auto-Adding missing Manifest/ChangeLog file(s)...")
			add_cmd = [vcs_settings.vcs, "add"]
			add_cmd += myautoadd
			if options.pretend:
				portage.writemsg_stdout(
					"(%s)\n" % " ".join(add_cmd),
					noiselevel=-1)
			else:

				if sys.hexversion < 0x3020000 and sys.hexversion >= 0x3000000 and \
					not os.path.isabs(add_cmd[0]):
					# Python 3.1 _execvp throws TypeError for non-absolute executable
					# path passed as bytes (see http://bugs.python.org/issue8513).
					fullname = find_binary(add_cmd[0])
					if fullname is None:
						raise portage.exception.CommandNotFound(add_cmd[0])
					add_cmd[0] = fullname

				add_cmd = [_unicode_encode(arg) for arg in add_cmd]
				retcode = subprocess.call(add_cmd)
				if retcode != os.EX_OK:
					logging.error(
						"Exiting on %s error code: %s\n" % (vcs_settings.vcs, retcode))
					sys.exit(retcode)

			myupdates += myautoadd

		print("* %s files being committed..." % green(str(len(myupdates))), end=' ')

		if vcs_settings.vcs not in ('cvs', 'svn'):
			# With git, bzr and hg, there's never any keyword expansion, so
			# there's no need to regenerate manifests and all files will be
			# committed in one big commit at the end.
			print()
		elif not repo_settings.repo_config.thin_manifest:
			if vcs_settings.vcs == 'cvs':
				headerstring = "'\$(Header|Id).*\$'"
			elif vcs_settings.vcs == "svn":
				svn_keywords = dict((k.lower(), k) for k in [
					"Rev",
					"Revision",
					"LastChangedRevision",
					"Date",
					"LastChangedDate",
					"Author",
					"LastChangedBy",
					"URL",
					"HeadURL",
					"Id",
					"Header",
				])

			for myfile in myupdates:

				# for CVS, no_expansion contains files that are excluded from expansion
				if vcs_settings.vcs == "cvs":
					if myfile in no_expansion:
						continue

				# for SVN, expansion contains files that are included in expansion
				elif vcs_settings.vcs == "svn":
					if myfile not in expansion:
						continue

					# Subversion keywords are case-insensitive
					# in svn:keywords properties,
					# but case-sensitive in contents of files.
					enabled_keywords = []
					for k in expansion[myfile]:
						keyword = svn_keywords.get(k.lower())
						if keyword is not None:
							enabled_keywords.append(keyword)

					headerstring = "'\$(%s).*\$'" % "|".join(enabled_keywords)

				myout = repoman_getstatusoutput(
					"egrep -q %s %s" % (headerstring, portage._shell_quote(myfile)))
				if myout[0] == 0:
					myheaders.append(myfile)

			print("%s have headers that will change." % green(str(len(myheaders))))
			print(
				"* Files with headers will"
				" cause the manifests to be changed and committed separately.")

		logging.info("myupdates: %s", myupdates)
		logging.info("myheaders: %s", myheaders)

		uq = UserQuery(options)
		if options.ask and uq.query('Commit changes?', True) != 'Yes':
			print("* aborting commit.")
			sys.exit(128 + signal.SIGINT)

		# Handle the case where committed files have keywords which
		# will change and need a priming commit before the Manifest
		# can be committed.
		if (myupdates or myremoved) and myheaders:
			myfiles = myupdates + myremoved
			fd, commitmessagefile = tempfile.mkstemp(".repoman.msg")
			mymsg = os.fdopen(fd, "wb")
			mymsg.write(_unicode_encode(commitmessage))
			mymsg.close()

			separator = '-' * 78

			print()
			print(green("Using commit message:"))
			print(green(separator))
			print(commitmessage)
			print(green(separator))
			print()

			# Having a leading ./ prefix on file paths can trigger a bug in
			# the cvs server when committing files to multiple directories,
			# so strip the prefix.
			myfiles = [f.lstrip("./") for f in myfiles]

			commit_cmd = [vcs_settings.vcs]
			commit_cmd.extend(vcs_settings.vcs_global_opts)
			commit_cmd.append("commit")
			commit_cmd.extend(vcs_settings.vcs_local_opts)
			commit_cmd.extend(["-F", commitmessagefile])
			commit_cmd.extend(myfiles)

			try:
				if options.pretend:
					print("(%s)" % (" ".join(commit_cmd),))
				else:
					retval = spawn(commit_cmd, env=repo_settings.commit_env)
					if retval != os.EX_OK:
						writemsg_level(
							"!!! Exiting on %s (shell) "
							"error code: %s\n" % (vcs_settings.vcs, retval),
							level=logging.ERROR, noiselevel=-1)
						sys.exit(retval)
			finally:
				try:
					os.unlink(commitmessagefile)
				except OSError:
					pass

		# When files are removed and re-added, the cvs server will put /Attic/
		# inside the $Header path. This code detects the problem and corrects it
		# so that the Manifest will generate correctly. See bug #169500.
		# Use binary mode in order to avoid potential character encoding issues.
		cvs_header_re = re.compile(br'^#\s*\$Header.*\$$')
		attic_str = b'/Attic/'
		attic_replace = b'/'
		for x in myheaders:
			f = open(
				_unicode_encode(x, encoding=_encodings['fs'], errors='strict'),
				mode='rb')
			mylines = f.readlines()
			f.close()
			modified = False
			for i, line in enumerate(mylines):
				if cvs_header_re.match(line) is not None and \
					attic_str in line:
					mylines[i] = line.replace(attic_str, attic_replace)
					modified = True
			if modified:
				portage.util.write_atomic(x, b''.join(mylines), mode='wb')

		if scanner.repolevel == 1:
			utilities.repoman_sez(
				"\"You're rather crazy... "
				"doing the entire repository.\"\n")

		if vcs_settings.vcs in ('cvs', 'svn') and (myupdates or myremoved):
			for x in sorted(vcs_files_to_cps(
				chain(myupdates, myremoved, mymanifests),
				scanner.repolevel, scanner.reposplit, scanner.categories)):
				repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
				digestgen(mysettings=repoman_settings, myportdb=portdb)

		elif broken_changelog_manifests:
			for x in broken_changelog_manifests:
				repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
				digestgen(mysettings=repoman_settings, myportdb=portdb)

		if repo_settings.sign_manifests:
			try:
				for x in sorted(vcs_files_to_cps(
					chain(myupdates, myremoved, mymanifests),
					scanner.repolevel, scanner.reposplit, scanner.categories)):
					repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
					manifest_path = os.path.join(repoman_settings["O"], "Manifest")
					if not need_signature(manifest_path):
						continue
					gpgsign(manifest_path, repoman_settings, options)
			except portage.exception.PortageException as e:
				portage.writemsg("!!! %s\n" % str(e))
				portage.writemsg("!!! Disabled FEATURES='sign'\n")
				repo_settings.sign_manifests = False

		if vcs_settings.vcs == 'git':
			# It's not safe to use the git commit -a option since there might
			# be some modified files elsewhere in the working tree that the
			# user doesn't want to commit. Therefore, call git update-index
			# in order to ensure that the index is updated with the latest
			# versions of all new and modified files in the relevant portion
			# of the working tree.
			myfiles = mymanifests + myupdates
			myfiles.sort()
			update_index_cmd = ["git", "update-index"]
			update_index_cmd.extend(f.lstrip("./") for f in myfiles)
			if options.pretend:
				print("(%s)" % (" ".join(update_index_cmd),))
			else:
				retval = spawn(update_index_cmd, env=os.environ)
				if retval != os.EX_OK:
					writemsg_level(
						"!!! Exiting on %s (shell) "
						"error code: %s\n" % (vcs_settings.vcs, retval),
						level=logging.ERROR, noiselevel=-1)
					sys.exit(retval)

		if True:
			myfiles = mymanifests[:]
			# If there are no header (SVN/CVS keywords) changes in
			# the files, this Manifest commit must include the
			# other (yet uncommitted) files.
			if not myheaders:
				myfiles += myupdates
				myfiles += myremoved
			myfiles.sort()

			fd, commitmessagefile = tempfile.mkstemp(".repoman.msg")
			mymsg = os.fdopen(fd, "wb")
			mymsg.write(_unicode_encode(commitmessage))
			mymsg.close()

			commit_cmd = []
			if options.pretend and vcs_settings.vcs is None:
				# substitute a bogus value for pretend output
				commit_cmd.append("cvs")
			else:
				commit_cmd.append(vcs_settings.vcs)
			commit_cmd.extend(vcs_settings.vcs_global_opts)
			commit_cmd.append("commit")
			commit_cmd.extend(vcs_settings.vcs_local_opts)
			if vcs_settings.vcs == "hg":
				commit_cmd.extend(["--logfile", commitmessagefile])
				commit_cmd.extend(myfiles)
			else:
				commit_cmd.extend(["-F", commitmessagefile])
				commit_cmd.extend(f.lstrip("./") for f in myfiles)

			try:
				if options.pretend:
					print("(%s)" % (" ".join(commit_cmd),))
				else:
					retval = spawn(commit_cmd, env=repo_settings.commit_env)
					if retval != os.EX_OK:
						if repo_settings.repo_config.sign_commit and vcs_settings.vcs == 'git' and \
							not git_supports_gpg_sign():
							# Inform user that newer git is needed (bug #403323).
							logging.error(
								"Git >=1.7.9 is required for signed commits!")

						writemsg_level(
							"!!! Exiting on %s (shell) "
							"error code: %s\n" % (vcs_settings.vcs, retval),
							level=logging.ERROR, noiselevel=-1)
						sys.exit(retval)
			finally:
				try:
					os.unlink(commitmessagefile)
				except OSError:
					pass

		print()
		if vcs_settings.vcs:
			print("Commit complete.")
		else:
			print(
				"repoman was too scared"
				" by not seeing any familiar version control file"
				" that he forgot to commit anything")
		utilities.repoman_sez(
			"\"If everyone were like you, I'd be out of business!\"\n")
	sys.exit(0)
