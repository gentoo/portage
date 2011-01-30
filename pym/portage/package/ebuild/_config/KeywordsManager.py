# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'KeywordsManager',
)

from portage import os
from portage.dep import ExtendedAtomDict, _repo_separator, _slot_separator
from portage.localization import _
from portage.package.ebuild._config.helper import ordered_by_atom_specificity
from portage.util import grabdict_package, stack_lists, writemsg
from portage.versions import cpv_getkey

class KeywordsManager(object):

	def __init__(self, profiles, abs_user_config, user_config=True, global_accept_keywords=""):
		self._pkeywords_list = []
		rawpkeywords = [grabdict_package(
			os.path.join(x, "package.keywords"), recursive=1, verify_eapi=True) \
			for x in profiles]
		for pkeyworddict in rawpkeywords:
			if not pkeyworddict:
				# Omit non-existent files from the stack.
				continue
			cpdict = {}
			for k, v in pkeyworddict.items():
				cpdict.setdefault(k.cp, {})[k] = v
			self._pkeywords_list.append(cpdict)
		self._pkeywords_list = tuple(self._pkeywords_list)

		self._p_accept_keywords = []
		raw_p_accept_keywords = [grabdict_package(
			os.path.join(x, "package.accept_keywords"), recursive=1, verify_eapi=True) \
			for x in profiles]
		for d in raw_p_accept_keywords:
			if not d:
				# Omit non-existent files from the stack.
				continue
			cpdict = {}
			for k, v in d.items():
				cpdict.setdefault(k.cp, {})[k] = tuple(v)
			self._p_accept_keywords.append(cpdict)
		self._p_accept_keywords = tuple(self._p_accept_keywords)

		self.pkeywordsdict = ExtendedAtomDict(dict)

		if user_config:
			pkgdict = grabdict_package(
				os.path.join(abs_user_config, "package.keywords"),
				recursive=1, allow_wildcard=True, allow_repo=True, verify_eapi=False)

			for k, v in grabdict_package(
				os.path.join(abs_user_config, "package.accept_keywords"),
				recursive=1, allow_wildcard=True, allow_repo=True, verify_eapi=False).items():
				pkgdict.setdefault(k, []).extend(v)

			accept_keywords_defaults = global_accept_keywords.split()
			accept_keywords_defaults = tuple('~' + keyword for keyword in \
				accept_keywords_defaults if keyword[:1] not in "~-")
			for k, v in pkgdict.items():
				# default to ~arch if no specific keyword is given
				if not v:
					v = accept_keywords_defaults
				else:
					v = tuple(v)
				self.pkeywordsdict.setdefault(k.cp, {})[k] = v

	def getKeywords(self, cpv, slot, keywords, repo):
		cp = cpv_getkey(cpv)
		pkg = "".join((cpv, _slot_separator, slot))
		if repo:
			pkg = "".join((pkg, _repo_separator, repo))
		keywords = [[x for x in keywords.split() if x != "-*"]]
		for pkeywords_dict in self._pkeywords_list:
			cpdict = pkeywords_dict.get(cp)
			if cpdict:
				pkg_keywords = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_keywords:
					keywords.extend(pkg_keywords)
		return stack_lists(keywords, incremental=True)

	def getMissingKeywords(self, cpv, slot, keywords, repo, global_accept_keywords, backuped_accept_keywords):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		need to accept for the given package. If the KEYWORDS are empty
		and the the ** keyword has not been accepted, the returned list will
		contain ** alone (in order to distinguish from the case of "none
		missing").

		@param cpv: The package name (for package.keywords support)
		@type cpv: String
		@param slot: The 'SLOT' key from the raw package metadata
		@type slot: String
		@param keywords: The 'KEYWORDS' key from the raw package metadata
		@type keywords: String
		@param global_accept_keywords: The current value of ACCEPT_KEYWORDS
		@type global_accept_keywords: String
		@param backuped_accept_keywords: ACCEPT_KEYWORDS from the backup env
		@type backuped_accept_keywords: String
		@rtype: List
		@return: A list of KEYWORDS that have not been accepted.
		"""

		# Hack: Need to check the env directly here as otherwise stacking
		# doesn't work properly as negative values are lost in the config
		# object (bug #139600)
		egroups = backuped_accept_keywords.split()
		mygroups = self.getKeywords(cpv, slot, keywords, repo)
		# Repoman may modify this attribute as necessary.
		pgroups = global_accept_keywords.split()
		matches = False
		cp = cpv_getkey(cpv)

		if self._p_accept_keywords:
			cpv_slot = "%s:%s" % (cpv, slot)
			accept_keywords_defaults = tuple('~' + keyword for keyword in \
				pgroups if keyword[:1] not in "~-")
			for d in self._p_accept_keywords:
				cpdict = d.get(cp)
				if cpdict:
					pkg_accept_keywords = \
						ordered_by_atom_specificity(cpdict, cpv_slot)
					if pkg_accept_keywords:
						for x in pkg_accept_keywords:
							if not x:
								x = accept_keywords_defaults
							pgroups.extend(x)
						matches = True

		pkgdict = self.pkeywordsdict.get(cp)
		if pkgdict:
			cpv_slot = "%s:%s" % (cpv, slot)
			pkg_accept_keywords = \
				ordered_by_atom_specificity(pkgdict, cpv_slot, repo=repo)
			if pkg_accept_keywords:
				for x in pkg_accept_keywords:
					pgroups.extend(x)
				matches = True

		if matches or egroups:
			pgroups.extend(egroups)
			inc_pgroups = set()
			for x in pgroups:
				if x.startswith("-"):
					if x == "-*":
						inc_pgroups.clear()
					else:
						inc_pgroups.discard(x[1:])
				else:
					inc_pgroups.add(x)
			pgroups = inc_pgroups
			del inc_pgroups

		match = False
		hasstable = False
		hastesting = False
		for gp in mygroups:
			if gp == "*" or (gp == "-*" and len(mygroups) == 1):
				writemsg(_("--- WARNING: Package '%(cpv)s' uses"
					" '%(keyword)s' keyword.\n") % {"cpv": cpv, "keyword": gp}, noiselevel=-1)
				if gp == "*":
					match = 1
					break
			elif gp in pgroups:
				match=1
				break
			elif gp.startswith("~"):
				hastesting = True
			elif not gp.startswith("-"):
				hasstable = True
		if not match and \
			((hastesting and "~*" in pgroups) or \
			(hasstable and "*" in pgroups) or "**" in pgroups):
			match=1
		if match:
			missing = []
		else:
			if not mygroups:
				# If KEYWORDS is empty then we still have to return something
				# in order to distinguish from the case of "none missing".
				mygroups.append("**")
			missing = mygroups
		return missing

	def getRawMissingKeywords(self, cpv, slot, keywords, repo, global_accept_keywords, backuped_accept_keywords):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		need to accept for the given package. If the KEYWORDS are empty,
		the returned list will contain ** alone (in order to distinguish
		from the case of "none missing").  This DOES NOT apply any user config
		keywording acceptance.

		@param cpv: The package name (for package.keywords support)
		@type cpv: String
		@param slot: The 'SLOT' key from the raw package metadata
		@type slot: String
		@param keywords: The 'KEYWORDS' key from the raw package metadata
		@type keywords: String
		@param global_accept_keywords: The current value of ACCEPT_KEYWORDS
		@type global_accept_keywords: String
		@param backuped_accept_keywords: ACCEPT_KEYWORDS from the backup env
		@type backuped_accept_keywords: String
		@rtype: List
		@return: lists of KEYWORDS that have not been accepted
		and the keywords it looked for.
		"""

		# Hack: Need to check the env directly here as otherwise stacking
		# doesn't work properly as negative values are lost in the config
		# object (bug #139600)
		egroups = backuped_accept_keywords.split()
		mygroups = self.getKeywords(cpv, slot, keywords, repo)
		# Repoman may modify this attribute as necessary.
		pgroups = global_accept_keywords.split()
		matches = False

		## we want to use the environment keywords here,
		## but stripped to it's base arch
		## we want the raw keywords needed to be accepted from the ebuild
		if egroups:
			pgroups.extend(egroups)
			inc_pgroups = set()
			for x in pgroups:
				if x.startswith("-"):
					if x == "-*":
						inc_pgroups.clear()
					else:
						inc_pgroups.discard(x[1:])
				else:
					inc_pgroups.add(x.lstrip('~'))
			pgroups = inc_pgroups
			del inc_pgroups

		match = False
		hasstable = False
		hastesting = False
		for gp in mygroups:
			if gp == "*" or (gp == "-*" and len(mygroups) == 1):
				writemsg(_("--- WARNING: Package '%(cpv)s' uses"
					" '%(keyword)s' keyword.\n") % {"cpv": cpv, "keyword": gp}, noiselevel=-1)
				if gp == "*":
					match = 1
					break
			elif gp in pgroups:
				match=1
				break
			elif gp.startswith("~"):
				hastesting = True
			elif not gp.startswith("-"):
				hasstable = True
		if not match and \
			((hastesting and "~*" in pgroups) or \
			(hasstable and "*" in pgroups) or "**" in pgroups):
			match=1
		if match:
			missing = []
		else:
			if not mygroups:
				# If KEYWORDS is empty then we still have to return something
				# in order to distinguish from the case of "none missing".
				mygroups.append("**")
			missing = mygroups
		return missing, pgroups
