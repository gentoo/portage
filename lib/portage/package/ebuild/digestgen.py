# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['digestgen']

import errno

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild._spawn_nofetch:spawn_nofetch',
)

from portage import os
from portage.const import MANIFEST2_HASH_DEFAULTS
from portage.dbapi.porttree import FetchlistDict
from portage.dep import use_reduce
from portage.exception import InvalidDependString, FileNotFound, \
	PermissionDenied, PortagePackageException
from portage.localization import _
from portage.output import colorize
from portage.package.ebuild.fetch import fetch
from portage.util import writemsg, writemsg_stdout
from portage.versions import catsplit

def digestgen(myarchives=None, mysettings=None, myportdb=None):
	"""
	Generates a digest file if missing. Fetches files if necessary.
	NOTE: myarchives and mysettings used to be positional arguments,
		so their order must be preserved for backward compatibility.
	@param mysettings: the ebuild config (mysettings["O"] must correspond
		to the ebuild's parent directory)
	@type mysettings: config
	@param myportdb: a portdbapi instance
	@type myportdb: portdbapi
	@rtype: int
	@return: 1 on success and 0 on failure
	"""
	if mysettings is None or myportdb is None:
		raise TypeError("portage.digestgen(): 'mysettings' and 'myportdb' parameter are required.")

	try:
		portage._doebuild_manifest_exempt_depend += 1
		distfiles_map = {}
		fetchlist_dict = FetchlistDict(mysettings["O"], mysettings, myportdb)
		for cpv in fetchlist_dict:
			try:
				for myfile in fetchlist_dict[cpv]:
					distfiles_map.setdefault(myfile, []).append(cpv)
			except InvalidDependString as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				del e
				return 0
		mytree = os.path.dirname(os.path.dirname(mysettings["O"]))
		try:
			mf = mysettings.repositories.get_repo_for_location(mytree)
		except KeyError:
			# backward compatibility
			mytree = os.path.realpath(mytree)
			mf = mysettings.repositories.get_repo_for_location(mytree)

		repo_required_hashes = mf.manifest_required_hashes
		if repo_required_hashes is None:
			repo_required_hashes = MANIFEST2_HASH_DEFAULTS
		mf = mf.load_manifest(mysettings["O"], mysettings["DISTDIR"],
			fetchlist_dict=fetchlist_dict)

		if not mf.allow_create:
			writemsg_stdout(_(">>> Skipping creating Manifest for %s; "
				"repository is configured to not use them\n") % mysettings["O"])
			return 1

		# Don't require all hashes since that can trigger excessive
		# fetches when sufficient digests already exist.  To ease transition
		# while Manifest 1 is being removed, only require hashes that will
		# exist before and after the transition.
		required_hash_types = set()
		required_hash_types.add("size")
		required_hash_types.update(repo_required_hashes)
		dist_hashes = mf.fhashdict.get("DIST", {})

		# To avoid accidental regeneration of digests with the incorrect
		# files (such as partially downloaded files), trigger the fetch
		# code if the file exists and it's size doesn't match the current
		# manifest entry. If there really is a legitimate reason for the
		# digest to change, `ebuild --force digest` can be used to avoid
		# triggering this code (or else the old digests can be manually
		# removed from the Manifest).
		missing_files = []
		for myfile in distfiles_map:
			myhashes = dist_hashes.get(myfile)
			if not myhashes:
				try:
					st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
				except OSError:
					st = None
				if st is None or st.st_size == 0:
					missing_files.append(myfile)
				continue
			size = myhashes.get("size")

			try:
				st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				if size == 0:
					missing_files.append(myfile)
					continue
				if required_hash_types.difference(myhashes):
					missing_files.append(myfile)
					continue
			else:
				if st.st_size == 0 or size is not None and size != st.st_size:
					missing_files.append(myfile)
					continue

		for myfile in missing_files:
			uris = set()
			all_restrict = set()
			for cpv in distfiles_map[myfile]:
				uris.update(myportdb.getFetchMap(
					cpv, mytree=mytree)[myfile])
				restrict = myportdb.aux_get(cpv, ['RESTRICT'], mytree=mytree)[0]
				# Here we ignore conditional parts of RESTRICT since
				# they don't apply unconditionally. Assume such
				# conditionals only apply on the client side where
				# digestgen() does not need to be called.
				all_restrict.update(use_reduce(restrict,
					flat=True, matchnone=True))

				# fetch() uses CATEGORY and PF to display a message
				# when fetch restriction is triggered.
				cat, pf = catsplit(cpv)
				mysettings["CATEGORY"] = cat
				mysettings["PF"] = pf

			# fetch() uses PORTAGE_RESTRICT to control fetch
			# restriction, which is only applied to files that
			# are not fetchable via a mirror:// URI.
			mysettings["PORTAGE_RESTRICT"] = " ".join(all_restrict)

			try:
				st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
			except OSError:
				st = None

			if not fetch({myfile : uris}, mysettings):
				myebuild = os.path.join(mysettings["O"],
					catsplit(cpv)[1] + ".ebuild")
				spawn_nofetch(myportdb, myebuild)
				writemsg(_("!!! Fetch failed for %s, can't update Manifest\n")
					% myfile, noiselevel=-1)
				if myfile in dist_hashes and \
					st is not None and st.st_size > 0:
					# stat result is obtained before calling fetch(),
					# since fetch may rename the existing file if the
					# digest does not match.
					cmd = colorize("INFORM", "ebuild --force %s manifest" %
						os.path.basename(myebuild))
					writemsg((_(
						"!!! If you would like to forcefully replace the existing Manifest entry\n"
						"!!! for %s, use the following command:\n") % myfile) +
						"!!!    %s\n" % cmd,
						noiselevel=-1)
				return 0

		writemsg_stdout(_(">>> Creating Manifest for %s\n") % mysettings["O"])
		try:
			mf.create(assumeDistHashesSometimes=True,
				assumeDistHashesAlways=(
				"assume-digests" in mysettings.features))
		except FileNotFound as e:
			writemsg(_("!!! File %s doesn't exist, can't update Manifest\n")
				% e, noiselevel=-1)
			return 0
		except PortagePackageException as e:
			writemsg(("!!! %s\n") % (e,), noiselevel=-1)
			return 0
		try:
			mf.write(sign=False)
		except PermissionDenied as e:
			writemsg(_("!!! Permission Denied: %s\n") % (e,), noiselevel=-1)
			return 0
		if "assume-digests" not in mysettings.features:
			distlist = list(mf.fhashdict.get("DIST", {}))
			distlist.sort()
			auto_assumed = []
			for filename in distlist:
				if not os.path.exists(
					os.path.join(mysettings["DISTDIR"], filename)):
					auto_assumed.append(filename)
			if auto_assumed:
				cp = os.path.sep.join(mysettings["O"].split(os.path.sep)[-2:])
				pkgs = myportdb.cp_list(cp, mytree=mytree)
				pkgs.sort()
				writemsg_stdout("  digest.assumed" + colorize("WARN",
					str(len(auto_assumed)).rjust(18)) + "\n")
				for pkg_key in pkgs:
					fetchlist = myportdb.getFetchMap(pkg_key, mytree=mytree)
					pv = pkg_key.split("/")[1]
					for filename in auto_assumed:
						if filename in fetchlist:
							writemsg_stdout(
								"   %s::%s\n" % (pv, filename))
		return 1
	finally:
		portage._doebuild_manifest_exempt_depend -= 1
