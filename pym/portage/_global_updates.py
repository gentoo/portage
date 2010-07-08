# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import stat

from portage import best, os
from portage.const import WORLD_FILE
from portage.data import secpass
from portage.exception import DirectoryNotFound
from portage.localization import _
from portage.output import bold, colorize
from portage.update import grab_updates, parse_updates, update_config_files, update_dbentry
from portage.util import grabfile, writemsg, writemsg_stdout, write_atomic

def _global_updates(trees, prev_mtimes):
	"""
	Perform new global updates if they exist in 'profiles/updates/'
	subdirectories of all active repositories (PORTDIR + PORTDIR_OVERLAY).
	This simply returns if ROOT != "/" (when len(trees) != 1). If ROOT != "/"
	then the user should instead use emaint --fix movebin and/or moveinst.

	@param trees: A dictionary containing portage trees.
	@type trees: dict
	@param prev_mtimes: A dictionary containing mtimes of files located in
		$PORTDIR/profiles/updates/.
	@type prev_mtimes: dict
	@rtype: None or List
	@return: None if no were no updates, otherwise a list of update commands
		that have been performed.
	"""
	# only do this if we're root and not running repoman/ebuild digest

	if secpass < 2 or \
		"SANDBOX_ACTIVE" in os.environ or \
		len(trees) != 1:
		return 0
	root = "/"
	mysettings = trees["/"]["vartree"].settings
	retupd = []

	portdb = trees[root]["porttree"].dbapi
	vardb = trees[root]["vartree"].dbapi
	bindb = trees[root]["bintree"].dbapi
	if not os.access(bindb.bintree.pkgdir, os.W_OK):
		bindb = None
	else:
		# Call binarytree.populate(), since we want to make sure it's
		# only populated with local packages here (getbinpkgs=0).
		bindb.bintree.populate()

	world_file = os.path.join(root, WORLD_FILE)
	world_list = grabfile(world_file)
	world_modified = False
	world_warnings = set()

	for repo_name in portdb.getRepositories():
		repo = portdb.getRepositoryPath(repo_name)
		updpath = os.path.join(repo, "profiles", "updates")

		try:
			if mysettings.get("PORTAGE_CALLER") == "fixpackages":
				update_data = grab_updates(updpath)
			else:
				update_data = grab_updates(updpath, prev_mtimes)
		except DirectoryNotFound:
			continue
		myupd = None
		if len(update_data) > 0:
			do_upgrade_packagesmessage = 0
			myupd = []
			timestamps = {}
			for mykey, mystat, mycontent in update_data:
				writemsg_stdout("\n\n")
				writemsg_stdout(colorize("GOOD",
					_("Performing Global Updates: "))+bold(mykey)+"\n")
				writemsg_stdout(_("(Could take a couple of minutes if you have a lot of binary packages.)\n"))
				writemsg_stdout(_("  %s='update pass'  %s='binary update'  "
					"%s='/var/db update'  %s='/var/db move'\n"
					"  %s='/var/db SLOT move'  %s='binary move'  "
					"%s='binary SLOT move'\n  %s='update /etc/portage/package.*'\n") % \
					(bold("."), bold("*"), bold("#"), bold("@"), bold("s"), bold("%"), bold("S"), bold("p")))
				valid_updates, errors = parse_updates(mycontent)
				myupd.extend(valid_updates)
				writemsg_stdout(len(valid_updates) * "." + "\n")
				if len(errors) == 0:
					# Update our internal mtime since we
					# processed all of our directives.
					timestamps[mykey] = mystat[stat.ST_MTIME]
				else:
					for msg in errors:
						writemsg("%s\n" % msg, noiselevel=-1)
			retupd.extend(myupd)

			def _world_repo_match(atoma, atomb):
				"""
				Check whether to perform a world change from atoma to atomb.
				If best vardb match for atoma comes from the same repository
				as the update file, allow that. Additionally, if portdb still
				can find a match for old atom name, warn about that.
				"""
				matches = vardb.match(atoma)
				if matches and vardb.aux_get(best(matches), ['repository'])[0] == repo_name:
					if portdb.match(atoma):
						world_warnings.add((atoma, atomb))
					return True
				else:
					return False

			for update_cmd in myupd:
				for pos, atom in enumerate(world_list):
					new_atom = update_dbentry(update_cmd, atom)
					if atom != new_atom:
						if _world_repo_match(atom, new_atom):
							world_list[pos] = new_atom
							world_modified = True
			update_config_files(root,
				mysettings.get("CONFIG_PROTECT","").split(),
				mysettings.get("CONFIG_PROTECT_MASK","").split(),
				myupd, match_callback=_world_repo_match)

			for update_cmd in myupd:
				if update_cmd[0] == "move":
					moves = vardb.move_ent(update_cmd, repo_name=repo_name)
					if moves:
						writemsg_stdout(moves * "@")
					if bindb:
						moves = bindb.move_ent(update_cmd, repo_name=repo_name)
						if moves:
							writemsg_stdout(moves * "%")
				elif update_cmd[0] == "slotmove":
					moves = vardb.move_slot_ent(update_cmd, repo_name=repo_name)
					if moves:
						writemsg_stdout(moves * "s")
					if bindb:
						moves = bindb.move_slot_ent(update_cmd, repo_name=repo_name)
						if moves:
							writemsg_stdout(moves * "S")

			# The above global updates proceed quickly, so they
			# are considered a single mtimedb transaction.
			if len(timestamps) > 0:
				# We do not update the mtime in the mtimedb
				# until after _all_ of the above updates have
				# been processed because the mtimedb will
				# automatically commit when killed by ctrl C.
				for mykey, mtime in timestamps.items():
					prev_mtimes[mykey] = mtime

			# We gotta do the brute force updates for these now.
			if mysettings.get("PORTAGE_CALLER") == "fixpackages" or \
			"fixpackages" in mysettings.features:
				def onUpdate(maxval, curval):
					if curval > 0:
						writemsg_stdout("#")
				vardb.update_ents(myupd, onUpdate=onUpdate, repo=repo_name)
				if bindb:
					def onUpdate(maxval, curval):
						if curval > 0:
							writemsg_stdout("*")
					bindb.update_ents(myupd, onUpdate=onUpdate, repo=repo_name)
			else:
				do_upgrade_packagesmessage = 1

			# Update progress above is indicated by characters written to stdout so
			# we print a couple new lines here to separate the progress output from
			# what follows.
			print()
			print()

			if do_upgrade_packagesmessage and bindb and \
				bindb.cpv_all():
				writemsg_stdout(_(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the tbz2's in the packages directory.\n"))
				writemsg_stdout(bold(_("Note: This can take a very long time.")))
				writemsg_stdout("\n")

	if world_modified:
		world_list.sort()
		write_atomic(world_file,
			"".join("%s\n" % (x,) for x in world_list))
		if world_warnings:
			# XXX: print warning that we've updated world entries
			# and the old name still matches something (from an overlay)?
			pass

	if retupd:
		return retupd
