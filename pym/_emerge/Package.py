# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from itertools import chain
import portage
from portage import _encodings, _unicode_decode, _unicode_encode
from portage.cache.mappings import slot_dict_class
from portage.const import EBUILD_PHASES
from portage.dep import Atom, check_required_use, use_reduce, \
	paren_enclose, _slot_separator, _repo_separator
from portage.versions import _pkg_str, _unknown_repo
from portage.eapi import _get_eapi_attrs
from portage.exception import InvalidDependString
from portage.localization import _
from _emerge.Task import Task

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int
	_unicode = str
else:
	_unicode = unicode

class Package(Task):

	__hash__ = Task.__hash__
	__slots__ = ("built", "cpv", "depth",
		"installed", "metadata", "onlydeps", "operation",
		"root_config", "type_name",
		"category", "counter", "cp", "cpv_split",
		"inherited", "iuse", "mtime",
		"pf", "root", "slot", "sub_slot", "slot_atom", "version") + \
		("_invalid", "_raw_metadata", "_masks", "_use",
		"_validated_atoms", "_visible")

	metadata_keys = [
		"BUILD_TIME", "CHOST", "COUNTER", "DEPEND", "EAPI",
		"HDEPEND", "INHERITED", "IUSE", "KEYWORDS",
		"LICENSE", "PDEPEND", "PROVIDE", "RDEPEND",
		"repository", "PROPERTIES", "RESTRICT", "SLOT", "USE",
		"_mtime_", "DEFINED_PHASES", "REQUIRED_USE"]

	_dep_keys = ('DEPEND', 'HDEPEND', 'PDEPEND', 'RDEPEND')
	_buildtime_keys = ('DEPEND', 'HDEPEND')
	_runtime_keys = ('PDEPEND', 'RDEPEND')
	_use_conditional_misc_keys = ('LICENSE', 'PROPERTIES', 'RESTRICT')
	UNKNOWN_REPO = _unknown_repo

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		# the SlotObject constructor assigns self.root_config from keyword args
		# and is an instance of a '_emerge.RootConfig.RootConfig class
		self.root = self.root_config.root
		self._raw_metadata = _PackageMetadataWrapperBase(self.metadata)
		self.metadata = _PackageMetadataWrapper(self, self._raw_metadata)
		if not self.built:
			self.metadata['CHOST'] = self.root_config.settings.get('CHOST', '')
		eapi_attrs = _get_eapi_attrs(self.metadata["EAPI"])
		self.cpv = _pkg_str(self.cpv, metadata=self.metadata,
			settings=self.root_config.settings)
		if hasattr(self.cpv, 'slot_invalid'):
			self._invalid_metadata('SLOT.invalid',
				"SLOT: invalid value: '%s'" % self.metadata["SLOT"])
		self.cp = self.cpv.cp
		self.slot = self.cpv.slot
		self.sub_slot = self.cpv.sub_slot
		# sync metadata with validated repo (may be UNKNOWN_REPO)
		self.metadata['repository'] = self.cpv.repo

		if eapi_attrs.iuse_effective:
			implicit_match = self.root_config.settings._iuse_effective_match
		else:
			implicit_match = self.root_config.settings._iuse_implicit_match
		self.iuse = self._iuse(self.metadata["IUSE"].split(), implicit_match)

		if (self.iuse.enabled or self.iuse.disabled) and \
			not eapi_attrs.iuse_defaults:
			if not self.installed:
				self._invalid_metadata('EAPI.incompatible',
					"IUSE contains defaults, but EAPI doesn't allow them")
		self.slot_atom = Atom("%s%s%s" % (self.cp, _slot_separator, self.slot))
		self.category, self.pf = portage.catsplit(self.cpv)
		self.cpv_split = self.cpv.cpv_split
		self.version = self.cpv.version
		if self.inherited is None:
			self.inherited = frozenset()

		if self.operation is None:
			if self.onlydeps or self.installed:
				self.operation = "nomerge"
			else:
				self.operation = "merge"

		self._hash_key = Package._gen_hash_key(cpv=self.cpv,
			installed=self.installed, onlydeps=self.onlydeps,
			operation=self.operation, repo_name=self.cpv.repo,
			root_config=self.root_config,
			type_name=self.type_name)
		self._hash_value = hash(self._hash_key)

	# For consistency with _pkg_str
	@property
	def _metadata(self):
		return self.metadata

	# These are calculated on-demand, so that they are calculated
	# after FakeVartree applies its metadata tweaks.
	@property
	def invalid(self):
		if self._invalid is None:
			self._validate_deps()
			if self._invalid is None:
				self._invalid = False
		return self._invalid

	@property
	def masks(self):
		if self._masks is None:
			self._masks = self._eval_masks()
		return self._masks

	@property
	def visible(self):
		if self._visible is None:
			self._visible = self._eval_visiblity(self.masks)
		return self._visible

	@property
	def validated_atoms(self):
		"""
		Returns *all* validated atoms from the deps, regardless
		of USE conditionals, with USE conditionals inside
		atoms left unevaluated.
		"""
		if self._validated_atoms is None:
			self._validate_deps()
		return self._validated_atoms

	@property
	def stable(self):
		return self.cpv.stable

	@classmethod
	def _gen_hash_key(cls, cpv=None, installed=None, onlydeps=None,
		operation=None, repo_name=None, root_config=None,
		type_name=None, **kwargs):

		if operation is None:
			if installed or onlydeps:
				operation = "nomerge"
			else:
				operation = "merge"

		root = None
		if root_config is not None:
			root = root_config.root
		else:
			raise TypeError("root_config argument is required")

		# For installed (and binary) packages we don't care for the repo
		# when it comes to hashing, because there can only be one cpv.
		# So overwrite the repo_key with type_name.
		if type_name is None:
			raise TypeError("type_name argument is required")
		elif type_name == "ebuild":
			if repo_name is None:
				raise AssertionError(
					"Package._gen_hash_key() " + \
					"called without 'repo_name' argument")
			repo_key = repo_name
		else:
			# For installed (and binary) packages we don't care for the repo
			# when it comes to hashing, because there can only be one cpv.
			# So overwrite the repo_key with type_name.
			repo_key = type_name

		return (type_name, root, _unicode(cpv), operation, repo_key)

	def _validate_deps(self):
		"""
		Validate deps. This does not trigger USE calculation since that
		is expensive for ebuilds and therefore we want to avoid doing
		in unnecessarily (like for masked packages).
		"""
		eapi = self.metadata['EAPI']
		dep_eapi = eapi
		dep_valid_flag = self.iuse.is_valid_flag
		if self.installed:
			# Ignore EAPI.incompatible and conditionals missing
			# from IUSE for installed packages since these issues
			# aren't relevant now (re-evaluate when new EAPIs are
			# deployed).
			dep_eapi = None
			dep_valid_flag = None

		validated_atoms = []
		for k in self._dep_keys:
			v = self.metadata.get(k)
			if not v:
				continue
			try:
				atoms = use_reduce(v, eapi=dep_eapi,
					matchall=True, is_valid_flag=dep_valid_flag,
					token_class=Atom, flat=True)
			except InvalidDependString as e:
				self._metadata_exception(k, e)
			else:
				validated_atoms.extend(atoms)
				if not self.built:
					for atom in atoms:
						if not isinstance(atom, Atom):
							continue
						if atom.slot_operator_built:
							e = InvalidDependString(
								_("Improper context for slot-operator "
								"\"built\" atom syntax: %s") %
								(atom.unevaluated_atom,))
							self._metadata_exception(k, e)

		self._validated_atoms = tuple(set(atom for atom in
			validated_atoms if isinstance(atom, Atom)))

		k = 'PROVIDE'
		v = self.metadata.get(k)
		if v:
			try:
				use_reduce(v, eapi=dep_eapi, matchall=True,
					is_valid_flag=dep_valid_flag, token_class=Atom)
			except InvalidDependString as e:
				self._invalid_metadata("PROVIDE.syntax",
					_unicode_decode("%s: %s") % (k, e))

		for k in self._use_conditional_misc_keys:
			v = self.metadata.get(k)
			if not v:
				continue
			try:
				use_reduce(v, eapi=dep_eapi, matchall=True,
					is_valid_flag=dep_valid_flag)
			except InvalidDependString as e:
				self._metadata_exception(k, e)

		k = 'REQUIRED_USE'
		v = self.metadata.get(k)
		if v and not self.built:
			if not _get_eapi_attrs(eapi).required_use:
				self._invalid_metadata('EAPI.incompatible',
					"REQUIRED_USE set, but EAPI='%s' doesn't allow it" % eapi)
			else:
				try:
					check_required_use(v, (),
						self.iuse.is_valid_flag, eapi=eapi)
				except InvalidDependString as e:
					# Force unicode format string for python-2.x safety,
					# ensuring that PortageException.__unicode__() is used
					# when necessary.
					self._invalid_metadata(k + ".syntax",
						_unicode_decode("%s: %s") % (k, e))

		k = 'SRC_URI'
		v = self.metadata.get(k)
		if v:
			try:
				use_reduce(v, is_src_uri=True, eapi=eapi, matchall=True,
					is_valid_flag=self.iuse.is_valid_flag)
			except InvalidDependString as e:
				if not self.installed:
					self._metadata_exception(k, e)

	def copy(self):
		return Package(built=self.built, cpv=self.cpv, depth=self.depth,
			installed=self.installed, metadata=self._raw_metadata,
			onlydeps=self.onlydeps, operation=self.operation,
			root_config=self.root_config, type_name=self.type_name)

	def _eval_masks(self):
		masks = {}
		settings = self.root_config.settings

		if self.invalid is not False:
			masks['invalid'] = self.invalid

		if not settings._accept_chost(self.cpv, self.metadata):
			masks['CHOST'] = self.metadata['CHOST']

		eapi = self.metadata["EAPI"]
		if not portage.eapi_is_supported(eapi):
			masks['EAPI.unsupported'] = eapi
		if portage._eapi_is_deprecated(eapi):
			masks['EAPI.deprecated'] = eapi

		missing_keywords = settings._getMissingKeywords(
			self.cpv, self.metadata)
		if missing_keywords:
			masks['KEYWORDS'] = missing_keywords

		try:
			missing_properties = settings._getMissingProperties(
				self.cpv, self.metadata)
			if missing_properties:
				masks['PROPERTIES'] = missing_properties
		except InvalidDependString:
			# already recorded as 'invalid'
			pass

		mask_atom = settings._getMaskAtom(self.cpv, self.metadata)
		if mask_atom is not None:
			masks['package.mask'] = mask_atom

		try:
			missing_licenses = settings._getMissingLicenses(
				self.cpv, self.metadata)
			if missing_licenses:
				masks['LICENSE'] = missing_licenses
		except InvalidDependString:
			# already recorded as 'invalid'
			pass

		if not masks:
			masks = False

		return masks

	def _eval_visiblity(self, masks):

		if masks is not False:

			if 'EAPI.unsupported' in masks:
				return False

			if 'invalid' in masks:
				return False

			if not self.installed and ( \
				'CHOST' in masks or \
				'EAPI.deprecated' in masks or \
				'KEYWORDS' in masks or \
				'PROPERTIES' in masks):
				return False

			if 'package.mask' in masks or \
				'LICENSE' in masks:
				return False

		return True

	def get_keyword_mask(self):
		"""returns None, 'missing', or 'unstable'."""

		missing = self.root_config.settings._getRawMissingKeywords(
				self.cpv, self.metadata)

		if not missing:
			return None

		if '**' in missing:
			return 'missing'

		global_accept_keywords = frozenset(
			self.root_config.settings.get("ACCEPT_KEYWORDS", "").split())

		for keyword in missing:
			if keyword.lstrip("~") in global_accept_keywords:
				return 'unstable'

		return 'missing'

	def isHardMasked(self):
		"""returns a bool if the cpv is in the list of
		expanded pmaskdict[cp] available ebuilds"""
		pmask = self.root_config.settings._getRawMaskAtom(
			self.cpv, self.metadata)
		return pmask is not None

	def _metadata_exception(self, k, e):

		if k.endswith('DEPEND'):
			qacat = 'dependency.syntax'
		else:
			qacat = k + ".syntax"

		# For unicode safety with python-2.x we need to avoid
		# using the string format operator with a non-unicode
		# format string, since that will result in the
		# PortageException.__str__() method being invoked,
		# followed by unsafe decoding that may result in a
		# UnicodeDecodeError. Therefore, use _unicode_decode()
		# to ensure that format strings are unicode, so that
		# PortageException.__unicode__() is used when necessary
		# in python-2.x.
		if not self.installed:
			categorized_error = False
			if e.errors:
				for error in e.errors:
					if getattr(error, 'category', None) is None:
						continue
					categorized_error = True
					self._invalid_metadata(error.category,
						_unicode_decode("%s: %s") % (k, error))

			if not categorized_error:
				self._invalid_metadata(qacat,
					_unicode_decode("%s: %s") % (k, e))
		else:
			# For installed packages, show the path of the file
			# containing the invalid metadata, since the user may
			# want to fix the deps by hand.
			vardb = self.root_config.trees['vartree'].dbapi
			path = vardb.getpath(self.cpv, filename=k)
			self._invalid_metadata(qacat,
				_unicode_decode("%s: %s in '%s'") % (k, e, path))

	def _invalid_metadata(self, msg_type, msg):
		if self._invalid is None:
			self._invalid = {}
		msgs = self._invalid.get(msg_type)
		if msgs is None:
			msgs = []
			self._invalid[msg_type] = msgs
		msgs.append(msg)

	def __str__(self):
		if self.operation == "merge":
			if self.type_name == "binary":
				cpv_color = "PKG_BINARY_MERGE"
			else:
				cpv_color = "PKG_MERGE"
		elif self.operation == "uninstall":
			cpv_color = "PKG_UNINSTALL"
		else:
			cpv_color = "PKG_NOMERGE"

		s = "(%s, %s" \
			% (portage.output.colorize(cpv_color, self.cpv + _repo_separator + self.repo) , self.type_name)

		if self.type_name == "installed":
			if self.root_config.settings['ROOT'] != "/":
				s += " in '%s'" % self.root_config.settings['ROOT']
			if self.operation == "uninstall":
				s += " scheduled for uninstall"
		else:
			if self.operation == "merge":
				s += " scheduled for merge"
				if self.root_config.settings['ROOT'] != "/":
					s += " to '%s'" % self.root_config.settings['ROOT']
		s += ")"
		return s

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

	class _use_class(object):

		__slots__ = ("enabled", "_expand", "_expand_hidden",
			"_force", "_pkg", "_mask")

		# Share identical frozenset instances when available.
		_frozensets = {}

		def __init__(self, pkg, use_str):
			self._pkg = pkg
			self._expand = None
			self._expand_hidden = None
			self._force = None
			self._mask = None
			self.enabled = frozenset(use_str.split())
			if pkg.built:
				# Use IUSE to validate USE settings for built packages,
				# in case the package manager that built this package
				# failed to do that for some reason (or in case of
				# data corruption).
				missing_iuse = pkg.iuse.get_missing_iuse(self.enabled)
				if missing_iuse:
					self.enabled = self.enabled.difference(missing_iuse)

		def _init_force_mask(self):
			pkgsettings = self._pkg._get_pkgsettings()
			frozensets = self._frozensets
			s = frozenset(
				pkgsettings.get("USE_EXPAND", "").lower().split())
			self._expand = frozensets.setdefault(s, s)
			s = frozenset(
				pkgsettings.get("USE_EXPAND_HIDDEN", "").lower().split())
			self._expand_hidden = frozensets.setdefault(s, s)
			s = pkgsettings.useforce
			self._force = frozensets.setdefault(s, s)
			s = pkgsettings.usemask
			self._mask = frozensets.setdefault(s, s)

		@property
		def expand(self):
			if self._expand is None:
				self._init_force_mask()
			return self._expand

		@property
		def expand_hidden(self):
			if self._expand_hidden is None:
				self._init_force_mask()
			return self._expand_hidden

		@property
		def force(self):
			if self._force is None:
				self._init_force_mask()
			return self._force

		@property
		def mask(self):
			if self._mask is None:
				self._init_force_mask()
			return self._mask

	@property
	def repo(self):
		return self.metadata['repository']

	@property
	def repo_priority(self):
		repo_info = self.root_config.settings.repositories.prepos.get(self.repo)
		if repo_info is None:
			return None
		return repo_info.priority

	@property
	def use(self):
		if self._use is None:
			self.metadata._init_use()
		return self._use

	def _get_pkgsettings(self):
		pkgsettings = self.root_config.trees[
			'porttree'].dbapi.doebuild_settings
		pkgsettings.setcpv(self)
		return pkgsettings

	class _iuse(object):

		__slots__ = ("__weakref__", "all", "enabled", "disabled",
			"tokens") + ("_iuse_implicit_match",)

		def __init__(self, tokens, iuse_implicit_match):
			self.tokens = tuple(tokens)
			self._iuse_implicit_match = iuse_implicit_match
			enabled = []
			disabled = []
			other = []
			for x in tokens:
				prefix = x[:1]
				if prefix == "+":
					enabled.append(x[1:])
				elif prefix == "-":
					disabled.append(x[1:])
				else:
					other.append(x)
			self.enabled = frozenset(enabled)
			self.disabled = frozenset(disabled)
			self.all = frozenset(chain(enabled, disabled, other))

		def is_valid_flag(self, flags):
			"""
			@return: True if all flags are valid USE values which may
				be specified in USE dependencies, False otherwise.
			"""
			if isinstance(flags, basestring):
				flags = [flags]

			for flag in flags:
				if not flag in self.all and \
					not self._iuse_implicit_match(flag):
					return False
			return True

		def get_missing_iuse(self, flags):
			"""
			@return: A list of flags missing from IUSE.
			"""
			if isinstance(flags, basestring):
				flags = [flags]
			missing_iuse = []
			for flag in flags:
				if not flag in self.all and \
					not self._iuse_implicit_match(flag):
					missing_iuse.append(flag)
			return missing_iuse

	def __len__(self):
		return 4

	def __iter__(self):
		"""
		This is used to generate mtimedb resume mergelist entries, so we
		limit it to 4 items for backward compatibility.
		"""
		return iter(self._hash_key[:4])

	def __lt__(self, other):
		if other.cp != self.cp:
			return False
		if portage.vercmp(self.version, other.version) < 0:
			return True
		return False

	def __le__(self, other):
		if other.cp != self.cp:
			return False
		if portage.vercmp(self.version, other.version) <= 0:
			return True
		return False

	def __gt__(self, other):
		if other.cp != self.cp:
			return False
		if portage.vercmp(self.version, other.version) > 0:
			return True
		return False

	def __ge__(self, other):
		if other.cp != self.cp:
			return False
		if portage.vercmp(self.version, other.version) >= 0:
			return True
		return False

_all_metadata_keys = set(x for x in portage.auxdbkeys \
	if not x.startswith("UNUSED_"))
_all_metadata_keys.update(Package.metadata_keys)
_all_metadata_keys = frozenset(_all_metadata_keys)

_PackageMetadataWrapperBase = slot_dict_class(_all_metadata_keys)

class _PackageMetadataWrapper(_PackageMetadataWrapperBase):
	"""
	Detect metadata updates and synchronize Package attributes.
	"""

	__slots__ = ("_pkg",)
	_wrapped_keys = frozenset(
		["COUNTER", "INHERITED", "USE", "_mtime_"])
	_use_conditional_keys = frozenset(
		['LICENSE', 'PROPERTIES', 'PROVIDE', 'RESTRICT',])

	def __init__(self, pkg, metadata):
		_PackageMetadataWrapperBase.__init__(self)
		self._pkg = pkg
		if not pkg.built:
			# USE is lazy, but we want it to show up in self.keys().
			_PackageMetadataWrapperBase.__setitem__(self, 'USE', '')

		self.update(metadata)

	def _init_use(self):
		if self._pkg.built:
			use_str = self['USE']
			self._pkg._use = self._pkg._use_class(
				self._pkg, use_str)
		else:
			try:
				use_str = _PackageMetadataWrapperBase.__getitem__(self, 'USE')
			except KeyError:
				use_str = None
			calculated_use = False
			if not use_str:
				use_str = self._pkg._get_pkgsettings()["PORTAGE_USE"]
				calculated_use = True
			_PackageMetadataWrapperBase.__setitem__(self, 'USE', use_str)
			self._pkg._use = self._pkg._use_class(
				self._pkg, use_str)
			# Initialize these now, since USE access has just triggered
			# setcpv, and we want to cache the result of the force/mask
			# calculations that were done.
			if calculated_use:
				self._pkg._use._init_force_mask()

		return use_str

	def __getitem__(self, k):
		v = _PackageMetadataWrapperBase.__getitem__(self, k)
		if k in self._use_conditional_keys:
			if self._pkg.root_config.settings.local_config and '?' in v:
				try:
					v = paren_enclose(use_reduce(v, uselist=self._pkg.use.enabled, \
						is_valid_flag=self._pkg.iuse.is_valid_flag))
				except InvalidDependString:
					# This error should already have been registered via
					# self._pkg._invalid_metadata().
					pass
				else:
					self[k] = v

		elif k == 'USE' and not self._pkg.built:
			if not v:
				# This is lazy because it's expensive.
				v = self._init_use()

		return v

	def __setitem__(self, k, v):
		_PackageMetadataWrapperBase.__setitem__(self, k, v)
		if k in self._wrapped_keys:
			getattr(self, "_set_" + k.lower())(k, v)

	def _set_inherited(self, k, v):
		if isinstance(v, basestring):
			v = frozenset(v.split())
		self._pkg.inherited = v

	def _set_counter(self, k, v):
		if isinstance(v, basestring):
			try:
				v = long(v.strip())
			except ValueError:
				v = 0
		self._pkg.counter = v

	def _set_use(self, k, v):
		# Force regeneration of _use attribute
		self._pkg._use = None
		# Use raw metadata to restore USE conditional values
		# to unevaluated state
		raw_metadata = self._pkg._raw_metadata
		for x in self._use_conditional_keys:
			try:
				self[x] = raw_metadata[x]
			except KeyError:
				pass

	def _set__mtime_(self, k, v):
		if isinstance(v, basestring):
			try:
				v = long(v.strip())
			except ValueError:
				v = 0
		self._pkg.mtime = v

	@property
	def properties(self):
		return self['PROPERTIES'].split()

	@property
	def restrict(self):
		return self['RESTRICT'].split()

	@property
	def defined_phases(self):
		"""
		Returns tokens from DEFINED_PHASES metadata if it is defined,
		otherwise returns a tuple containing all possible phases. This
		makes it easy to do containment checks to see if it's safe to
		skip execution of a given phase.
		"""
		s = self['DEFINED_PHASES']
		if s:
			return s.split()
		return EBUILD_PHASES
