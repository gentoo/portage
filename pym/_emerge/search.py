# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import re
import portage
from portage import os
from portage.dbapi.porttree import _parse_uri_map
from portage.output import  bold, bold as white, darkgreen, green, red
from portage.util import writemsg_stdout

from _emerge.Package import Package

class search(object):

	#
	# class constants
	#
	VERSION_SHORT=1
	VERSION_RELEASE=2

	#
	# public interface
	#
	def __init__(self, root_config, spinner, searchdesc,
		verbose, usepkg, usepkgonly):
		"""Searches the available and installed packages for the supplied search key.
		The list of available and installed packages is created at object instantiation.
		This makes successive searches faster."""
		self.settings = root_config.settings
		self.vartree = root_config.trees["vartree"]
		self.spinner = spinner
		self.verbose = verbose
		self.searchdesc = searchdesc
		self.root_config = root_config
		self.setconfig = root_config.setconfig
		self.matches = {"pkg" : []}
		self.mlen = 0

		self._dbs = []

		portdb = root_config.trees["porttree"].dbapi
		bindb = root_config.trees["bintree"].dbapi
		vardb = root_config.trees["vartree"].dbapi

		if not usepkgonly and portdb._have_root_eclass_dir:
			self._dbs.append(portdb)

		if (usepkg or usepkgonly) and bindb.cp_all():
			self._dbs.append(bindb)

		self._dbs.append(vardb)
		self._portdb = portdb

	def _spinner_update(self):
		if self.spinner:
			self.spinner.update()

	def _cp_all(self):
		cp_all = set()
		for db in self._dbs:
			cp_all.update(db.cp_all())
		return list(sorted(cp_all))

	def _aux_get(self, *args, **kwargs):
		for db in self._dbs:
			try:
				return db.aux_get(*args, **kwargs)
			except KeyError:
				pass
		raise

	def _findname(self, *args, **kwargs):
		for db in self._dbs:
			if db is not self._portdb:
				# We don't want findname to return anything
				# unless it's an ebuild in a portage tree.
				# Otherwise, it's already built and we don't
				# care about it.
				continue
			func = getattr(db, "findname", None)
			if func:
				value = func(*args, **kwargs)
				if value:
					return value
		return None

	def _getFetchMap(self, *args, **kwargs):
		for db in self._dbs:
			func = getattr(db, "getFetchMap", None)
			if func:
				value = func(*args, **kwargs)
				if value:
					return value
		return {}

	def _visible(self, db, cpv, metadata):
		installed = db is self.vartree.dbapi
		built = installed or db is not self._portdb
		pkg_type = "ebuild"
		if installed:
			pkg_type = "installed"
		elif built:
			pkg_type = "binary"
		return Package(type_name=pkg_type,
			root_config=self.root_config,
			cpv=cpv, built=built, installed=installed,
			metadata=metadata).visible

	def _xmatch(self, level, atom):
		"""
		This method does not expand old-style virtuals because it
		is restricted to returning matches for a single ${CATEGORY}/${PN}
		and old-style virual matches unreliable for that when querying
		multiple package databases. If necessary, old-style virtuals
		can be performed on atoms prior to calling this method.
		"""
		cp = portage.dep_getkey(atom)
		if level == "match-all":
			matches = set()
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					matches.update(db.xmatch(level, atom))
				else:
					matches.update(db.match(atom))
			result = list(x for x in matches if portage.cpv_getkey(x) == cp)
			db._cpv_sort_ascending(result)
		elif level == "match-visible":
			matches = set()
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					matches.update(db.xmatch(level, atom))
				else:
					db_keys = list(db._aux_cache_keys)
					for cpv in db.match(atom):
						metadata = zip(db_keys,
							db.aux_get(cpv, db_keys))
						if not self._visible(db, cpv, metadata):
							continue
						matches.add(cpv)
			result = list(x for x in matches if portage.cpv_getkey(x) == cp)
			db._cpv_sort_ascending(result)
		elif level == "bestmatch-visible":
			result = None
			for db in self._dbs:
				if hasattr(db, "xmatch"):
					cpv = db.xmatch("bestmatch-visible", atom)
					if not cpv or portage.cpv_getkey(cpv) != cp:
						continue
					if not result or cpv == portage.best([cpv, result]):
						result = cpv
				else:
					db_keys = list(db._aux_cache_keys)
					# break out of this loop with highest visible
					# match, checked in descending order
					for cpv in reversed(db.match(atom)):
						if portage.cpv_getkey(cpv) != cp:
							continue
						metadata = zip(db_keys,
							db.aux_get(cpv, db_keys))
						if not self._visible(db, cpv, metadata):
							continue
						if not result or cpv == portage.best([cpv, result]):
							result = cpv
						break
		else:
			raise NotImplementedError(level)
		return result

	def execute(self,searchkey):
		"""Performs the search for the supplied search key"""
		match_category = 0
		self.searchkey=searchkey
		self.packagematches = []
		if self.searchdesc:
			self.searchdesc=1
			self.matches = {"pkg":[], "desc":[], "set":[]}
		else:
			self.searchdesc=0
			self.matches = {"pkg":[], "set":[]}
		print("Searching...   ", end=' ')

		regexsearch = False
		if self.searchkey.startswith('%'):
			regexsearch = True
			self.searchkey = self.searchkey[1:]
		if self.searchkey.startswith('@'):
			match_category = 1
			self.searchkey = self.searchkey[1:]
		if regexsearch:
			self.searchre=re.compile(self.searchkey,re.I)
		else:
			self.searchre=re.compile(re.escape(self.searchkey), re.I)

		for package in self._cp_all():
			self._spinner_update()

			if match_category:
				match_string  = package[:]
			else:
				match_string  = package.split("/")[-1]

			masked=0
			if self.searchre.search(match_string):
				if not self._xmatch("match-visible", package):
					masked=1
				self.matches["pkg"].append([package,masked])
			elif self.searchdesc: # DESCRIPTION searching
				full_package = self._xmatch("bestmatch-visible", package)
				if not full_package:
					#no match found; we don't want to query description
					full_package = portage.best(
						self._xmatch("match-all", package))
					if not full_package:
						continue
					else:
						masked=1
				try:
					full_desc = self._aux_get(
						full_package, ["DESCRIPTION"])[0]
				except KeyError:
					print("emerge: search: aux_get() failed, skipping")
					continue
				if self.searchre.search(full_desc):
					self.matches["desc"].append([full_package,masked])

		self.sdict = self.setconfig.getSets()
		for setname in self.sdict:
			self._spinner_update()
			if match_category:
				match_string = setname
			else:
				match_string = setname.split("/")[-1]
			
			if self.searchre.search(match_string):
				self.matches["set"].append([setname, False])
			elif self.searchdesc:
				if self.searchre.search(
					self.sdict[setname].getMetadata("DESCRIPTION")):
					self.matches["set"].append([setname, False])
			
		self.mlen=0
		for mtype in self.matches:
			self.matches[mtype].sort()
			self.mlen += len(self.matches[mtype])

	def addCP(self, cp):
		if not self._xmatch("match-all", cp):
			return
		masked = 0
		if not self._xmatch("bestmatch-visible", cp):
			masked = 1
		self.matches["pkg"].append([cp, masked])
		self.mlen += 1

	def output(self):
		"""Outputs the results of the search."""
		msg = []
		msg.append("\b\b  \n[ Results for search key : " + \
			bold(self.searchkey) + " ]\n")
		msg.append("[ Applications found : " + \
			bold(str(self.mlen)) + " ]\n\n")
		vardb = self.vartree.dbapi
		metadata_keys = set(Package.metadata_keys)
		metadata_keys.update(["DESCRIPTION", "HOMEPAGE", "LICENSE", "SRC_URI"])
		metadata_keys = tuple(metadata_keys)
		for mtype in self.matches:
			for match,masked in self.matches[mtype]:
				full_package = None
				if mtype == "pkg":
					full_package = self._xmatch(
						"bestmatch-visible", match)
					if not full_package:
						#no match found; we don't want to query description
						masked=1
						full_package = portage.best(
							self._xmatch("match-all",match))
				elif mtype == "desc":
					full_package = match
					match        = portage.cpv_getkey(match)
				elif mtype == "set":
					msg.append(green("*") + "  " + bold(match) + "\n")
					if self.verbose:
						msg.append("      " + darkgreen("Description:") + \
							"   " + \
							self.sdict[match].getMetadata("DESCRIPTION") \
							+ "\n\n")
				if full_package:
					try:
						metadata = dict(zip(metadata_keys,
							self._aux_get(full_package, metadata_keys)))
					except KeyError:
						msg.append("emerge: search: aux_get() failed, skipping\n")
						continue

					desc = metadata["DESCRIPTION"]
					homepage = metadata["HOMEPAGE"]
					license = metadata["LICENSE"]

					if masked:
						msg.append(green("*") + "  " + \
							white(match) + " " + red("[ Masked ]") + "\n")
					else:
						msg.append(green("*") + "  " + bold(match) + "\n")
					myversion = self.getVersion(full_package, search.VERSION_RELEASE)

					mysum = [0,0]
					file_size_str = None
					mycat = match.split("/")[0]
					mypkg = match.split("/")[1]
					mycpv = match + "-" + myversion
					myebuild = self._findname(mycpv)
					if myebuild:
						pkg = Package(built=False, cpv=mycpv,
							installed=False, metadata=metadata,
							root_config=self.root_config, type_name="ebuild")
						pkgdir = os.path.dirname(myebuild)
						mf = self.settings.repositories.get_repo_for_location(
							os.path.dirname(os.path.dirname(pkgdir)))
						mf = mf.load_manifest(
							pkgdir, self.settings["DISTDIR"])
						try:
							uri_map = _parse_uri_map(mycpv, metadata,
								use=pkg.use.enabled)
						except portage.exception.InvalidDependString as e:
							file_size_str = "Unknown (%s)" % (e,)
							del e
						else:
							try:
								mysum[0] = mf.getDistfilesSize(uri_map)
							except KeyError as e:
								file_size_str = "Unknown (missing " + \
									"digest for %s)" % (e,)
								del e

					available = False
					for db in self._dbs:
						if db is not vardb and \
							db.cpv_exists(mycpv):
							available = True
							if not myebuild and hasattr(db, "bintree"):
								myebuild = db.bintree.getname(mycpv)
								try:
									mysum[0] = os.stat(myebuild).st_size
								except OSError:
									myebuild = None
							break

					if myebuild and file_size_str is None:
						mystr = str(mysum[0] // 1024)
						mycount = len(mystr)
						while (mycount > 3):
							mycount -= 3
							mystr = mystr[:mycount] + "," + mystr[mycount:]
						file_size_str = mystr + " kB"

					if self.verbose:
						if available:
							msg.append("      %s %s\n" % \
								(darkgreen("Latest version available:"),
								myversion))
						msg.append("      %s\n" % \
							self.getInstallationStatus(mycat+'/'+mypkg))
						if myebuild:
							msg.append("      %s %s\n" % \
								(darkgreen("Size of files:"), file_size_str))
						msg.append("      " + darkgreen("Homepage:") + \
							"      " + homepage + "\n")
						msg.append("      " + darkgreen("Description:") \
							+ "   " + desc + "\n")
						msg.append("      " + darkgreen("License:") + \
							"       " + license + "\n\n")
		writemsg_stdout(''.join(msg), noiselevel=-1)
	#
	# private interface
	#
	def getInstallationStatus(self,package):
		installed_package = self.vartree.dep_bestmatch(package)
		result = ""
		version = self.getVersion(installed_package,search.VERSION_RELEASE)
		if len(version) > 0:
			result = darkgreen("Latest version installed:")+" "+version
		else:
			result = darkgreen("Latest version installed:")+" [ Not Installed ]"
		return result

	def getVersion(self,full_package,detail):
		if len(full_package) > 1:
			package_parts = portage.catpkgsplit(full_package)
			if detail == search.VERSION_RELEASE and package_parts[3] != 'r0':
				result = package_parts[2]+ "-" + package_parts[3]
			else:
				result = package_parts[2]
		else:
			result = ""
		return result

