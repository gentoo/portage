# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['getmaskingreason']

import portage
from portage import os
from portage.const import USER_CONFIG_PATH
from portage.dep import Atom, match_from_list, _slot_separator, _repo_separator
from portage.exception import InvalidAtom
from portage.localization import _
from portage.repository.config import _gen_valid_repo
from portage.util import grablines, normalize_path
from portage.versions import catpkgsplit
from _emerge.Package import Package

def getmaskingreason(mycpv, metadata=None, settings=None,
	portdb=None, return_location=False, myrepo=None):
	"""
	If specified, the myrepo argument is assumed to be valid. This
	should be a safe assumption since portdbapi methods always
	return valid repo names and valid "repository" metadata from
	aux_get.
	"""
	if settings is None:
		settings = portage.settings
	if portdb is None:
		portdb = portage.portdb
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError(_("invalid CPV: %s") % mycpv)

	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(zip(db_keys,
				portdb.aux_get(mycpv, db_keys, myrepo=myrepo)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
		else:
			if myrepo is None:
				myrepo = _gen_valid_repo(metadata["repository"])

	elif myrepo is None:
		myrepo = metadata.get("repository")
		if myrepo is not None:
			myrepo = _gen_valid_repo(metadata["repository"])

	if metadata is not None and \
		not portage.eapi_is_supported(metadata["EAPI"]):
		# Return early since otherwise we might produce invalid
		# results given that the EAPI is not supported. Also,
		# metadata is mostly useless in this case since it doesn't
		# contain essential things like SLOT.
		if return_location:
			return (None, None)
		else:
			return None

	# Sometimes we can't access SLOT or repository due to corruption.
	pkg = mycpv
	if metadata is not None:
		pkg = "".join((mycpv, _slot_separator, metadata["SLOT"]))
	# At this point myrepo should be None, a valid name, or
	# Package.UNKNOWN_REPO which we ignore.
	if myrepo is not None and myrepo != Package.UNKNOWN_REPO:
		pkg = "".join((pkg, _repo_separator, myrepo))
	cpv_slot_list = [pkg]

	mycp=mysplit[0]+"/"+mysplit[1]

	# XXX- This is a temporary duplicate of code from the config constructor.
	locations = [os.path.join(settings["PORTDIR"], "profiles")]
	locations.extend(settings.profiles)
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(normalize_path(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH))
	locations.reverse()
	pmasklists = []
	for profile in locations:
		pmask_filename = os.path.join(profile, "package.mask")
		node = None
		for l, recursive_filename in grablines(pmask_filename,
			recursive=1, remember_source_file=True):
			if node is None or node[0] != recursive_filename:
				node = (recursive_filename, [])
				pmasklists.append(node)
			node[1].append(l)

	pmaskdict = settings._mask_manager._pmaskdict
	if mycp in pmaskdict:
		for x in pmaskdict[mycp]:
			if match_from_list(x, cpv_slot_list):
				x = x.without_repo
				for pmask in pmasklists:
					comment = ""
					comment_valid = -1
					pmask_filename = pmask[0]
					for i in range(len(pmask[1])):
						l = pmask[1][i].strip()
						try:
							l_atom = Atom(l, allow_repo=True,
								allow_wildcard=True).without_repo
						except InvalidAtom:
							l_atom = None
						if l == "":
							comment = ""
							comment_valid = -1
						elif l[0] == "#":
							comment += (l+"\n")
							comment_valid = i + 1
						elif l_atom == x:
							if comment_valid != i:
								comment = ""
							if return_location:
								return (comment, pmask_filename)
							else:
								return comment
						elif comment_valid != -1:
							# Apparently this comment applies to multiple masks, so
							# it remains valid until a blank line is encountered.
							comment_valid += 1
	if return_location:
		return (None, None)
	else:
		return None
