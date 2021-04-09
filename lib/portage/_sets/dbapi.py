# Copyright 2007-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import glob
import time

from portage import os
from portage.exception import PortageKeyError
from portage.versions import best, catsplit, vercmp
from portage.dep import Atom, use_reduce
from portage.dep._slot_operator import strip_slots
from portage.localization import _
from portage._sets.base import PackageSet
from portage._sets import SetConfigError, get_boolean
import portage

__all__ = ["CategorySet", "ChangedDepsSet", "DowngradeSet",
	"EverythingSet", "OwnerSet", "SubslotChangedSet", "VariableSet"]

class EverythingSet(PackageSet):
	_operations = ["merge"]
	description = "Package set which contains SLOT " + \
		"atoms to match all installed packages"
	_filter = None

	def __init__(self, vdbapi, **kwargs):
		super(EverythingSet, self).__init__()
		self._db = vdbapi

	def load(self):
		myatoms = []
		pkg_str = self._db._pkg_str
		cp_list = self._db.cp_list

		for cp in self._db.cp_all():
			for cpv in cp_list(cp):
				# NOTE: Create SLOT atoms even when there is only one
				# SLOT installed, in order to avoid the possibility
				# of unwanted upgrades as reported in bug #338959.
				pkg = pkg_str(cpv, None)
				atom = Atom("%s:%s" % (pkg.cp, pkg.slot))
				if self._filter:
					if self._filter(atom):
						myatoms.append(atom)
				else:
					myatoms.append(atom)

		self._setAtoms(myatoms)

	def singleBuilder(self, options, settings, trees):
		return EverythingSet(trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)

class OwnerSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"that own one or more files."

	def __init__(self, vardb=None, exclude_files=None, files=None):
		super(OwnerSet, self).__init__()
		self._db = vardb
		self._exclude_files = exclude_files
		self._files = files

	def mapPathsToAtoms(self, paths, exclude_paths=None):
		"""
		All paths must begin with a slash, and must not include EROOT.
		Supports globs.
		"""
		rValue = set()
		vardb = self._db

		eroot = vardb.settings['EROOT']
		expanded_paths = []
		for p in paths:
			expanded_paths.extend(expanded_p[len(eroot)-1:] for expanded_p in
				glob.iglob(os.path.join(eroot, p.lstrip(os.sep))))
		paths = expanded_paths

		expanded_exclude_paths = []
		for p in exclude_paths:
			expanded_exclude_paths.extend(expanded_exc_p[len(eroot)-1:] for expanded_exc_p in
				glob.iglob(os.path.join(eroot, p.lstrip(os.sep))))
		exclude_paths = expanded_exclude_paths

		pkg_str = vardb._pkg_str
		if exclude_paths is None:
			for link, p in vardb._owners.iter_owners(paths):
				pkg = pkg_str(link.mycpv, None)
				rValue.add("%s:%s" % (pkg.cp, pkg.slot))
		else:
			all_paths = set()
			all_paths.update(paths)
			all_paths.update(exclude_paths)
			exclude_atoms = set()
			for link, p in vardb._owners.iter_owners(all_paths):
				pkg = pkg_str(link.mycpv, None)
				atom = "%s:%s" % (pkg.cp, pkg.slot)
				rValue.add(atom)
				# Returned paths are relative to ROOT and do not have
				# a leading slash.
				if '/' + p in exclude_paths:
					exclude_atoms.add(atom)
			rValue.difference_update(exclude_atoms)

		return rValue

	def load(self):
		self._setAtoms(self.mapPathsToAtoms(self._files,
			exclude_paths=self._exclude_files))

	def singleBuilder(cls, options, settings, trees):
		if not "files" in options:
			raise SetConfigError(_("no files given"))

		exclude_files = options.get("exclude-files")
		if exclude_files is not None:
			exclude_files = frozenset(portage.util.shlex_split(exclude_files))
		return cls(vardb=trees["vartree"].dbapi, exclude_files=exclude_files,
			files=frozenset(portage.util.shlex_split(options["files"])))

	singleBuilder = classmethod(singleBuilder)

class VariableSet(EverythingSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"that match specified values of a specified variable."

	def __init__(self, vardb, metadatadb=None, variable=None, includes=None, excludes=None):
		super(VariableSet, self).__init__(vardb)
		self._metadatadb = metadatadb
		self._variable = variable
		self._includes = includes
		self._excludes = excludes

	def _filter(self, atom):
		ebuild = best(self._metadatadb.match(atom))
		if not ebuild:
			return False
		values, = self._metadatadb.aux_get(ebuild, [self._variable])
		values = values.split()
		if self._includes and not self._includes.intersection(values):
			return False
		if self._excludes and self._excludes.intersection(values):
			return False
		return True

	def singleBuilder(cls, options, settings, trees):

		variable = options.get("variable")
		if variable is None:
			raise SetConfigError(_("missing required attribute: 'variable'"))

		includes = options.get("includes", "")
		excludes = options.get("excludes", "")

		if not (includes or excludes):
			raise SetConfigError(_("no includes or excludes given"))

		metadatadb = options.get("metadata-source", "vartree")
		if not metadatadb in trees:
			raise SetConfigError(_("invalid value '%s' for option metadata-source") % metadatadb)

		return cls(trees["vartree"].dbapi,
			metadatadb=trees[metadatadb].dbapi,
			excludes=frozenset(excludes.split()),
			includes=frozenset(includes.split()),
			variable=variable)

	singleBuilder = classmethod(singleBuilder)

class SubslotChangedSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"for which the subslot of the highest visible ebuild is " + \
		"different than the currently installed version."

	def __init__(self, portdb=None, vardb=None):
		super(SubslotChangedSet, self).__init__()
		self._portdb = portdb
		self._vardb = vardb

	def load(self):
		atoms = []
		xmatch = self._portdb.xmatch
		xmatch_level = "bestmatch-visible"
		cp_list = self._vardb.cp_list
		for cp in self._vardb.cp_all():
			for pkg in cp_list(cp):
				slot_atom = "%s:%s" % (pkg.cp, pkg.slot)
				ebuild = xmatch(xmatch_level, slot_atom)
				if not ebuild:
					continue
				if pkg.sub_slot != ebuild.sub_slot:
					atoms.append(slot_atom)

		self._setAtoms(atoms)

	def singleBuilder(cls, options, settings, trees):
		return cls(portdb=trees["porttree"].dbapi,
			vardb=trees["vartree"].dbapi)

	singleBuilder = classmethod(singleBuilder)

class DowngradeSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"for which the highest visible ebuild version is lower than " + \
		"the currently installed version."

	def __init__(self, portdb=None, vardb=None):
		super(DowngradeSet, self).__init__()
		self._portdb = portdb
		self._vardb = vardb

	def load(self):
		atoms = []
		xmatch = self._portdb.xmatch
		xmatch_level = "bestmatch-visible"
		cp_list = self._vardb.cp_list
		pkg_str = self._vardb._pkg_str
		for cp in self._vardb.cp_all():
			for cpv in cp_list(cp):
				pkg = pkg_str(cpv, None)
				slot_atom = "%s:%s" % (pkg.cp, pkg.slot)
				ebuild = xmatch(xmatch_level, slot_atom)
				if not ebuild:
					continue
				if vercmp(cpv.version, ebuild.version) > 0:
					atoms.append(slot_atom)

		self._setAtoms(atoms)

	def singleBuilder(cls, options, settings, trees):
		return cls(portdb=trees["porttree"].dbapi,
			vardb=trees["vartree"].dbapi)

	singleBuilder = classmethod(singleBuilder)

class UnavailableSet(EverythingSet):

	_operations = ["unmerge"]

	description = "Package set which contains all installed " + \
		"packages for which there are no visible ebuilds " + \
		"corresponding to the same $CATEGORY/$PN:$SLOT."

	def __init__(self, vardb, metadatadb=None):
		super(UnavailableSet, self).__init__(vardb)
		self._metadatadb = metadatadb

	def _filter(self, atom):
		return not self._metadatadb.match(atom)

	def singleBuilder(cls, options, settings, trees):

		metadatadb = options.get("metadata-source", "porttree")
		if not metadatadb in trees:
			raise SetConfigError(_("invalid value '%s' for option "
				"metadata-source") % (metadatadb,))

		return cls(trees["vartree"].dbapi,
			metadatadb=trees[metadatadb].dbapi)

	singleBuilder = classmethod(singleBuilder)

class UnavailableBinaries(EverythingSet):

	_operations = ('merge', 'unmerge',)

	description = "Package set which contains all installed " + \
		"packages for which corresponding binary packages " + \
		"are not available."

	def __init__(self, vardb, metadatadb=None):
		super(UnavailableBinaries, self).__init__(vardb)
		self._metadatadb = metadatadb

	def _filter(self, atom):
		inst_pkg = self._db.match(atom)
		if not inst_pkg:
			return False
		inst_cpv = inst_pkg[0]
		return not self._metadatadb.cpv_exists(inst_cpv)

	def singleBuilder(cls, options, settings, trees):

		metadatadb = options.get("metadata-source", "bintree")
		if not metadatadb in trees:
			raise SetConfigError(_("invalid value '%s' for option "
				"metadata-source") % (metadatadb,))

		return cls(trees["vartree"].dbapi,
			metadatadb=trees[metadatadb].dbapi)

	singleBuilder = classmethod(singleBuilder)

class CategorySet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, category, dbapi, only_visible=True):
		super(CategorySet, self).__init__()
		self._db = dbapi
		self._category = category
		self._check = only_visible
		if only_visible:
			s="visible"
		else:
			s="all"
		self.description = "Package set containing %s packages of category %s" % (s, self._category)

	def load(self):
		myatoms = []
		for cp in self._db.cp_all():
			if catsplit(cp)[0] == self._category:
				if (not self._check) or len(self._db.match(cp)) > 0:
					myatoms.append(cp)
		self._setAtoms(myatoms)

	def _builderGetRepository(cls, options, repositories):
		repository = options.get("repository", "porttree")
		if not repository in repositories:
			raise SetConfigError(_("invalid repository class '%s'") % repository)
		return repository
	_builderGetRepository = classmethod(_builderGetRepository)

	def _builderGetVisible(cls, options):
		return get_boolean(options, "only_visible", True)
	_builderGetVisible = classmethod(_builderGetVisible)

	def singleBuilder(cls, options, settings, trees):
		if not "category" in options:
			raise SetConfigError(_("no category given"))

		category = options["category"]
		if not category in settings.categories:
			raise SetConfigError(_("invalid category name '%s'") % category)

		repository = cls._builderGetRepository(options, trees.keys())
		visible = cls._builderGetVisible(options)

		return CategorySet(category, dbapi=trees[repository].dbapi, only_visible=visible)
	singleBuilder = classmethod(singleBuilder)

	def multiBuilder(cls, options, settings, trees):
		rValue = {}

		if "categories" in options:
			categories = options["categories"].split()
			invalid = set(categories).difference(settings.categories)
			if invalid:
				raise SetConfigError(_("invalid categories: %s") % ", ".join(list(invalid)))
		else:
			categories = settings.categories

		repository = cls._builderGetRepository(options, trees.keys())
		visible = cls._builderGetVisible(options)
		name_pattern = options.get("name_pattern", "$category/*")

		if not "$category" in name_pattern and not "${category}" in name_pattern:
			raise SetConfigError(_("name_pattern doesn't include $category placeholder"))

		for cat in categories:
			myset = CategorySet(cat, trees[repository].dbapi, only_visible=visible)
			myname = name_pattern.replace("$category", cat)
			myname = myname.replace("${category}", cat)
			rValue[myname] = myset
		return rValue
	multiBuilder = classmethod(multiBuilder)

class AgeSet(EverythingSet):
	_operations = ["merge", "unmerge"]
	_aux_keys = ('BUILD_TIME',)

	def __init__(self, vardb, mode="older", age=7):
		super(AgeSet, self).__init__(vardb)
		self._mode = mode
		self._age = age

	def _filter(self, atom):

		cpv = self._db.match(atom)[0]
		try:
			date, = self._db.aux_get(cpv, self._aux_keys)
			date = int(date)
		except (KeyError, ValueError):
			return bool(self._mode == "older")
		age = (time.time() - date) / (3600 * 24)
		if ((self._mode == "older" and age <= self._age) \
			or (self._mode == "newer" and age >= self._age)):
			return False
		return True

	def singleBuilder(cls, options, settings, trees):
		mode = options.get("mode", "older")
		if str(mode).lower() not in ["newer", "older"]:
			raise SetConfigError(_("invalid 'mode' value %s (use either 'newer' or 'older')") % mode)
		try:
			age = int(options.get("age", "7"))
		except ValueError as e:
			raise SetConfigError(_("value of option 'age' is not an integer"))
		return AgeSet(vardb=trees["vartree"].dbapi, mode=mode, age=age)

	singleBuilder = classmethod(singleBuilder)

class DateSet(EverythingSet):
	_operations = ["merge", "unmerge"]
	_aux_keys = ('BUILD_TIME',)

	def __init__(self, vardb, date, mode="older"):
		super(DateSet, self).__init__(vardb)
		self._mode = mode
		self._date = date

	def _filter(self, atom):

		cpv = self._db.match(atom)[0]
		try:
			date, = self._db.aux_get(cpv, self._aux_keys)
			date = int(date)
		except (KeyError, ValueError):
			return bool(self._mode == "older")
		# Make sure inequality is _strict_ to exclude tested package
		if ((self._mode == "older" and date < self._date) \
			or (self._mode == "newer" and date > self._date)):
			return True
		return False

	def singleBuilder(cls, options, settings, trees):
		vardbapi = trees["vartree"].dbapi
		mode = options.get("mode", "older")
		if str(mode).lower() not in ["newer", "older"]:
			raise SetConfigError(_("invalid 'mode' value %s (use either 'newer' or 'older')") % mode)

		formats = []
		if options.get("package") is not None:
			formats.append("package")
		if options.get("filestamp") is not None:
			formats.append("filestamp")
		if options.get("seconds") is not None:
			formats.append("seconds")
		if options.get("date") is not None:
			formats.append("date")

		if not formats:
			raise SetConfigError(_("none of these options specified: 'package', 'filestamp', 'seconds', 'date'"))
		elif len(formats) > 1:
			raise SetConfigError(_("no more than one of these options is allowed: 'package', 'filestamp', 'seconds', 'date'"))

		setformat = formats[0]

		if setformat == "package":
			package = options.get("package")
			try:
				cpv = vardbapi.match(package)[0]
				date, = vardbapi.aux_get(cpv, ('BUILD_TIME',))
				date = int(date)
			except (KeyError, ValueError):
				raise SetConfigError(_("cannot determine installation date of package %s") % package)
		elif setformat == "filestamp":
			filestamp = options.get("filestamp")
			try:
				date = int(os.stat(filestamp).st_mtime)
			except (OSError, ValueError):
				raise SetConfigError(_("cannot determine 'filestamp' of '%s'") % filestamp)
		elif setformat == "seconds":
			try:
				date = int(options.get("seconds"))
			except ValueError:
				raise SetConfigError(_("option 'seconds' must be an integer"))
		else:
			dateopt = options.get("date")
			try:
				dateformat = options.get("dateformat", "%x %X")
				date = int(time.mktime(time.strptime(dateopt, dateformat)))
			except ValueError:
				raise SetConfigError(_("'date=%s' does not match 'dateformat=%s'") % (dateopt, dateformat))
		return DateSet(vardb=vardbapi, date=date, mode=mode)

	singleBuilder = classmethod(singleBuilder)

class RebuiltBinaries(EverythingSet):
	_operations = ('merge',)
	_aux_keys = ('BUILD_TIME',)

	def __init__(self, vardb, bindb=None):
		super(RebuiltBinaries, self).__init__(vardb, bindb=bindb)
		self._bindb = bindb

	def _filter(self, atom):
		cpv = self._db.match(atom)[0]
		inst_build_time, = self._db.aux_get(cpv, self._aux_keys)
		try:
			bin_build_time, = self._bindb.aux_get(cpv, self._aux_keys)
		except KeyError:
			return False
		return bool(bin_build_time and (inst_build_time != bin_build_time))

	def singleBuilder(cls, options, settings, trees):
		return RebuiltBinaries(trees["vartree"].dbapi,
			bindb=trees["bintree"].dbapi)

	singleBuilder = classmethod(singleBuilder)

class ChangedDepsSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all installed " + \
		"packages for which the vdb *DEPEND entries are outdated " + \
		"compared to corresponding portdb entries."

	def __init__(self, portdb=None, vardb=None):
		super(ChangedDepsSet, self).__init__()
		self._portdb = portdb
		self._vardb = vardb

	def load(self):
		depvars = ('RDEPEND', 'PDEPEND')
		ebuild_vars = depvars + ('EAPI',)
		installed_vars = depvars + ('USE', 'EAPI')

		atoms = []
		for cpv in self._vardb.cpv_all():
			# no ebuild, no update :).
			try:
				ebuild_metadata = dict(zip(ebuild_vars, self._portdb.aux_get(cpv, ebuild_vars)))
			except PortageKeyError:
				continue

			# USE flags used to build the ebuild and EAPI
			# (needed for Atom & use_reduce())
			installed_metadata = dict(zip(installed_vars, self._vardb.aux_get(cpv, installed_vars)))
			usel = frozenset(installed_metadata['USE'].split())

			# get all *DEPEND variables from vdb & portdb and compare them.
			# we need to do some cleaning up & expansion to make matching
			# meaningful since vdb dependencies are conditional-free.
			vdbvars = [strip_slots(use_reduce(installed_metadata[k],
				uselist=usel, eapi=installed_metadata['EAPI'], token_class=Atom))
				for k in depvars]
			pdbvars = [strip_slots(use_reduce(ebuild_metadata[k],
				uselist=usel, eapi=ebuild_metadata['EAPI'], token_class=Atom))
				for k in depvars]

			# if dependencies don't match, trigger the rebuild.
			if vdbvars != pdbvars:
				atoms.append('=%s' % cpv)

		self._setAtoms(atoms)

	def singleBuilder(cls, options, settings, trees):
		return cls(portdb=trees["porttree"].dbapi,
			vardb=trees["vartree"].dbapi)

	singleBuilder = classmethod(singleBuilder)
