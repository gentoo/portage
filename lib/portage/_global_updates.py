# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import stat

from portage import best, os
from portage.const import WORLD_FILE
from portage.data import secpass
from portage.exception import DirectoryNotFound
from portage.localization import _
from portage.output import bold, colorize
from portage.update import grab_updates, parse_updates, update_config_files, update_dbentry
from portage.util import grabfile, shlex_split, \
	writemsg, writemsg_stdout, write_atomic

def _global_updates(trees, prev_mtimes, quiet=False, if_mtime_changed=True):
	"""
	Perform new global updates if they exist in 'profiles/updates/'
	subdirectories of all active repositories (PORTDIR + PORTDIR_OVERLAY).
	This simply returns if ROOT != "/" (when len(trees) != 1). If ROOT != "/"
	then the user should instead use emaint --fix movebin and/or moveinst.

	@param trees: A dictionary containing package databases.
	@type trees: dict
	@param prev_mtimes: A dictionary containing mtimes of files located in
		$PORTDIR/profiles/updates/.
	@type prev_mtimes: dict
	@rtype: bool
	@return: True if update commands have been performed, otherwise False
	"""
	# only do this if we're root and not running repoman/ebuild digest

	if secpass < 2 or \
		"SANDBOX_ACTIVE" in os.environ or \
		len(trees) != 1:
		return False

	return _do_global_updates(trees, prev_mtimes,
		quiet=quiet, if_mtime_changed=if_mtime_changed)

def _do_global_updates(trees, prev_mtimes, quiet=False, if_mtime_changed=True):
	root = trees._running_eroot
	mysettings = trees[root]["vartree"].settings
	portdb = trees[root]["porttree"].dbapi
	vardb = trees[root]["vartree"].dbapi
	bindb = trees[root]["bintree"].dbapi

	world_file = os.path.join(mysettings['EROOT'], WORLD_FILE)
	world_list = grabfile(world_file)
	world_modified = False
	world_warnings = set()
	updpath_map = {}
	# Maps repo_name to list of updates. If a given repo has no updates
	# directory, it will be omitted. If a repo has an updates directory
	# but none need to be applied (according to timestamp logic), the
	# value in the dict will be an empty list.
	repo_map = {}
	timestamps = {}

	retupd = False
	update_notice_printed = False
	for repo_name in portdb.getRepositories():
		repo = portdb.getRepositoryPath(repo_name)
		updpath = os.path.join(repo, "profiles", "updates")
		if not os.path.isdir(updpath):
			continue

		if updpath in updpath_map:
			repo_map[repo_name] = updpath_map[updpath]
			continue

		try:
			if if_mtime_changed:
				update_data = grab_updates(updpath, prev_mtimes=prev_mtimes)
			else:
				update_data = grab_updates(updpath)
		except DirectoryNotFound:
			continue
		myupd = []
		updpath_map[updpath] = myupd
		repo_map[repo_name] = myupd
		if len(update_data) > 0:
			for mykey, mystat, mycontent in update_data:
				if not update_notice_printed:
					update_notice_printed = True
					writemsg_stdout("\n")
					writemsg_stdout(colorize("GOOD",
						_("Performing Global Updates\n")))
					writemsg_stdout(_("(Could take a couple of minutes if you have a lot of binary packages.)\n"))
					if not quiet:
						writemsg_stdout(_("  %s='update pass'  %s='binary update'  "
							"%s='/var/db update'  %s='/var/db move'\n"
							"  %s='/var/db SLOT move'  %s='binary move'  "
							"%s='binary SLOT move'\n  %s='update /etc/portage/package.*'\n") % \
							(bold("."), bold("*"), bold("#"), bold("@"), bold("s"), bold("%"), bold("S"), bold("p")))
				valid_updates, errors = parse_updates(mycontent)
				myupd.extend(valid_updates)
				if not quiet:
					writemsg_stdout(bold(mykey))
					writemsg_stdout(len(valid_updates) * "." + "\n")
				if len(errors) == 0:
					# Update our internal mtime since we
					# processed all of our directives.
					timestamps[mykey] = mystat[stat.ST_MTIME]
				else:
					for msg in errors:
						writemsg("%s\n" % msg, noiselevel=-1)
			if myupd:
				retupd = True

	if retupd:
		if os.access(bindb.bintree.pkgdir, os.W_OK):
			# Call binarytree.populate(), since we want to make sure it's
			# only populated with local packages here (getbinpkgs=0).
			bindb.bintree.populate()
		else:
			bindb = None

	master_repo = portdb.repositories.mainRepo()
	if master_repo is not None:
		master_repo = master_repo.name
	if master_repo in repo_map:
		repo_map['DEFAULT'] = repo_map[master_repo]

	for repo_name, myupd in repo_map.items():
		if repo_name == 'DEFAULT':
			continue
		if not myupd:
			continue

		def repo_match(repository):
			return repository == repo_name or \
				(repo_name == master_repo and repository not in repo_map)

		def _world_repo_match(atoma, atomb):
			"""
			Check whether to perform a world change from atoma to atomb.
			If best vardb match for atoma comes from the same repository
			as the update file, allow that. Additionally, if portdb still
			can find a match for old atom name, warn about that.
			"""
			matches = vardb.match(atoma)
			if not matches:
				matches = vardb.match(atomb)
			if matches and \
				repo_match(vardb.aux_get(best(matches), ['repository'])[0]):
				if portdb.match(atoma):
					world_warnings.add((atoma, atomb))
				return True
			return False

		for update_cmd in myupd:
			for pos, atom in enumerate(world_list):
				new_atom = update_dbentry(update_cmd, atom)
				if atom != new_atom:
					if _world_repo_match(atom, new_atom):
						world_list[pos] = new_atom
						world_modified = True

		for update_cmd in myupd:
			if update_cmd[0] == "move":
				moves = vardb.move_ent(update_cmd, repo_match=repo_match)
				if moves:
					writemsg_stdout(moves * "@")
				if bindb:
					moves = bindb.move_ent(update_cmd, repo_match=repo_match)
					if moves:
						writemsg_stdout(moves * "%")
			elif update_cmd[0] == "slotmove":
				moves = vardb.move_slot_ent(update_cmd, repo_match=repo_match)
				if moves:
					writemsg_stdout(moves * "s")
				if bindb:
					moves = bindb.move_slot_ent(update_cmd, repo_match=repo_match)
					if moves:
						writemsg_stdout(moves * "S")

	if world_modified:
		world_list.sort()
		write_atomic(world_file,
			"".join("%s\n" % (x,) for x in world_list))
		if world_warnings:
			# XXX: print warning that we've updated world entries
			# and the old name still matches something (from an overlay)?
			pass

	if retupd:

		def _config_repo_match(repo_name, atoma, atomb):
			"""
			Check whether to perform a world change from atoma to atomb.
			If best vardb match for atoma comes from the same repository
			as the update file, allow that. Additionally, if portdb still
			can find a match for old atom name, warn about that.
			"""
			matches = vardb.match(atoma)
			if not matches:
				matches = vardb.match(atomb)
				if not matches:
					return False
			repository = vardb.aux_get(best(matches), ['repository'])[0]
			return repository == repo_name or \
				(repo_name == master_repo and repository not in repo_map)

		update_config_files(root,
			shlex_split(mysettings.get("CONFIG_PROTECT", "")),
			shlex_split(mysettings.get("CONFIG_PROTECT_MASK", "")),
			repo_map, match_callback=_config_repo_match,
			case_insensitive="case-insensitive-fs"
			in mysettings.features)

		# The above global updates proceed quickly, so they
		# are considered a single mtimedb transaction.
		if timestamps:
			# We do not update the mtime in the mtimedb
			# until after _all_ of the above updates have
			# been processed because the mtimedb will
			# automatically commit when killed by ctrl C.
			for mykey, mtime in timestamps.items():
				prev_mtimes[mykey] = mtime

		do_upgrade_packagesmessage = False
		# We gotta do the brute force updates for these now.
		if True:
			def onUpdate(_maxval, curval):
				if curval > 0:
					writemsg_stdout("#")
			if quiet:
				onUpdate = None
			vardb.update_ents(repo_map, onUpdate=onUpdate)
			if bindb:
				def onUpdate(_maxval, curval):
					if curval > 0:
						writemsg_stdout("*")
				if quiet:
					onUpdate = None
				bindb.update_ents(repo_map, onUpdate=onUpdate)
		else:
			do_upgrade_packagesmessage = 1

		# Update progress above is indicated by characters written to stdout so
		# we print a couple new lines here to separate the progress output from
		# what follows.
		writemsg_stdout("\n\n")

		if do_upgrade_packagesmessage and bindb and \
			bindb.cpv_all():
			writemsg_stdout(_(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the tbz2's in the packages directory.\n"))
			writemsg_stdout(bold(_("Note: This can take a very long time.")))
			writemsg_stdout("\n")

	return retupd
