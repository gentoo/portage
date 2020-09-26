# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'LicenseManager',
)

from portage import os
from portage.dep import ExtendedAtomDict, use_reduce
from portage.exception import InvalidDependString
from portage.localization import _
from portage.util import grabdict, grabdict_package, writemsg
from portage.versions import cpv_getkey, _pkg_str

from portage.package.ebuild._config.helper import ordered_by_atom_specificity


class LicenseManager:

	def __init__(self, license_group_locations, abs_user_config, user_config=True):

		self._accept_license_str = None
		self._accept_license = None
		self._license_groups = {}
		self._plicensedict = ExtendedAtomDict(dict)
		self._undef_lic_groups = set()

		if user_config:
			license_group_locations = list(license_group_locations) + [abs_user_config]

		self._read_license_groups(license_group_locations)

		if user_config:
			self._read_user_config(abs_user_config)

	def _read_user_config(self, abs_user_config):
		licdict = grabdict_package(os.path.join(
			abs_user_config, "package.license"), recursive=1, allow_wildcard=True, allow_repo=True, verify_eapi=False)
		for k, v in licdict.items():
			self._plicensedict.setdefault(k.cp, {})[k] = \
				self.expandLicenseTokens(v)

	def _read_license_groups(self, locations):
		for loc in locations:
			for k, v in grabdict(
				os.path.join(loc, "license_groups")).items():
				self._license_groups.setdefault(k, []).extend(v)

		for k, v in self._license_groups.items():
			self._license_groups[k] = frozenset(v)

	def extract_global_changes(self, old=""):
		ret = old
		atom_license_map = self._plicensedict.get("*/*")
		if atom_license_map is not None:
			v = atom_license_map.pop("*/*", None)
			if v is not None:
				ret = " ".join(v)
				if old:
					ret = old + " " + ret
				if not atom_license_map:
					#No tokens left in atom_license_map, remove it.
					del self._plicensedict["*/*"]
		return ret

	def expandLicenseTokens(self, tokens):
		""" Take a token from ACCEPT_LICENSE or package.license and expand it
		if it's a group token (indicated by @) or just return it if it's not a
		group.  If a group is negated then negate all group elements."""
		expanded_tokens = []
		for x in tokens:
			expanded_tokens.extend(self._expandLicenseToken(x, None))
		return expanded_tokens

	def _expandLicenseToken(self, token, traversed_groups):
		negate = False
		rValue = []
		if token.startswith("-"):
			negate = True
			license_name = token[1:]
		else:
			license_name = token
		if not license_name.startswith("@"):
			rValue.append(token)
			return rValue
		group_name = license_name[1:]
		if traversed_groups is None:
			traversed_groups = set()
		license_group = self._license_groups.get(group_name)
		if group_name in traversed_groups:
			writemsg(_("Circular license group reference"
				" detected in '%s'\n") % group_name, noiselevel=-1)
			rValue.append("@"+group_name)
		elif license_group:
			traversed_groups.add(group_name)
			for l in license_group:
				if l.startswith("-"):
					writemsg(_("Skipping invalid element %s"
						" in license group '%s'\n") % (l, group_name),
						noiselevel=-1)
				else:
					rValue.extend(self._expandLicenseToken(l, traversed_groups))
		else:
			if self._license_groups and \
				group_name not in self._undef_lic_groups:
				self._undef_lic_groups.add(group_name)
				writemsg(_("Undefined license group '%s'\n") % group_name,
					noiselevel=-1)
			rValue.append("@"+group_name)
		if negate:
			rValue = ["-" + token for token in rValue]
		return rValue

	def _getPkgAcceptLicense(self, cpv, slot, repo):
		"""
		Get an ACCEPT_LICENSE list, accounting for package.license.
		"""
		accept_license = self._accept_license
		cp = cpv_getkey(cpv)
		cpdict = self._plicensedict.get(cp)
		if cpdict:
			if not hasattr(cpv, "slot"):
				cpv = _pkg_str(cpv, slot=slot, repo=repo)
			plicence_list = ordered_by_atom_specificity(cpdict, cpv)
			if plicence_list:
				accept_license = list(self._accept_license)
				for x in plicence_list:
					accept_license.extend(x)
		return accept_license

	def get_prunned_accept_license(self, cpv, use, lic, slot, repo):
		"""
		Generate a pruned version of ACCEPT_LICENSE, by intersection with
		LICENSE. This is required since otherwise ACCEPT_LICENSE might be
		too big (bigger than ARG_MAX), causing execve() calls to fail with
		E2BIG errors as in bug #262647.
		"""
		try:
			licenses = set(use_reduce(lic, uselist=use, flat=True))
		except InvalidDependString:
			licenses = set()
		licenses.discard('||')

		accept_license = self._getPkgAcceptLicense(cpv, slot, repo)

		if accept_license:
			acceptable_licenses = set()
			for x in accept_license:
				if x == '*':
					acceptable_licenses.update(licenses)
				elif x == '-*':
					acceptable_licenses.clear()
				elif x[:1] == '-':
					acceptable_licenses.discard(x[1:])
				elif x in licenses:
					acceptable_licenses.add(x)

			licenses = acceptable_licenses
		return ' '.join(sorted(licenses))

	def getMissingLicenses(self, cpv, use, lic, slot, repo):
		"""
		Take a LICENSE string and return a list of any licenses that the user
		may need to accept for the given package.  The returned list will not
		contain any licenses that have already been accepted.  This method
		can throw an InvalidDependString exception.

		@param cpv: The package name (for package.license support)
		@type cpv: String
		@param use: "USE" from the cpv's metadata
		@type use: String
		@param lic: "LICENSE" from the cpv's metadata
		@type lic: String
		@param slot: "SLOT" from the cpv's metadata
		@type slot: String
		@rtype: List
		@return: A list of licenses that have not been accepted.
		"""

		licenses = set(use_reduce(lic, matchall=1, flat=True))
		licenses.discard('||')

		acceptable_licenses = set()
		for x in self._getPkgAcceptLicense(cpv, slot, repo):
			if x == '*':
				acceptable_licenses.update(licenses)
			elif x == '-*':
				acceptable_licenses.clear()
			elif x[:1] == '-':
				acceptable_licenses.discard(x[1:])
			else:
				acceptable_licenses.add(x)

		license_str = lic
		if "?" in license_str:
			use = use.split()
		else:
			use = []

		license_struct = use_reduce(license_str, uselist=use, opconvert=True)
		return self._getMaskedLicenses(license_struct, acceptable_licenses)

	def _getMaskedLicenses(self, license_struct, acceptable_licenses):
		if not license_struct:
			return []
		if license_struct[0] == "||":
			ret = []
			for element in license_struct[1:]:
				if isinstance(element, list):
					if element:
						tmp = self._getMaskedLicenses(element, acceptable_licenses)
						if not tmp:
							return []
						ret.extend(tmp)
				else:
					if element in acceptable_licenses:
						return []
					ret.append(element)
			# Return all masked licenses, since we don't know which combination
			# (if any) the user will decide to unmask.
			return ret

		ret = []
		for element in license_struct:
			if isinstance(element, list):
				if element:
					ret.extend(self._getMaskedLicenses(element,
						acceptable_licenses))
			else:
				if element not in acceptable_licenses:
					ret.append(element)
		return ret

	def set_accept_license_str(self, accept_license_str):
		if accept_license_str != self._accept_license_str:
			self._accept_license_str = accept_license_str
			self._accept_license = tuple(self.expandLicenseTokens(accept_license_str.split()))
