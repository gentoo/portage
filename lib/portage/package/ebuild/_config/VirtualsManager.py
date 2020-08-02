# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'VirtualsManager',
)

from copy import deepcopy

from portage import os
from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.localization import _
from portage.util import grabdict, stack_dictlist, writemsg
from portage.versions import cpv_getkey

class VirtualsManager:

	def __init__(self, *args, **kwargs):
		if kwargs.get("_copy"):
			return

		assert len(args) == 1, "VirtualsManager.__init__ takes one positional argument"
		assert not kwargs, "unknown keyword argument(s) '%s' passed to VirtualsManager.__init__" % \
			", ".join(kwargs)

		profiles = args[0]
		self._virtuals = None
		self._dirVirtuals = None
		self._virts_p = None

		# Virtuals obtained from the vartree
		self._treeVirtuals = None
		# Virtuals added by the depgraph via self.add_depgraph_virtuals().
		self._depgraphVirtuals = {}

		#Initialise _dirVirtuals.
		self._read_dirVirtuals(profiles)

		#We could initialise _treeVirtuals here, but some consumers want to
		#pass their own vartree.

	def _read_dirVirtuals(self, profiles):
		"""
		Read the 'virtuals' file in all profiles.
		"""
		virtuals_list = []
		for x in profiles:
			virtuals_file = os.path.join(x, "virtuals")
			virtuals_dict = grabdict(virtuals_file)
			atoms_dict = {}
			for k, v in virtuals_dict.items():
				try:
					virt_atom = Atom(k)
				except InvalidAtom:
					virt_atom = None
				else:
					if virt_atom.blocker or \
						str(virt_atom) != str(virt_atom.cp):
						virt_atom = None
				if virt_atom is None:
					writemsg(_("--- Invalid virtuals atom in %s: %s\n") % \
						(virtuals_file, k), noiselevel=-1)
					continue
				providers = []
				for atom in v:
					atom_orig = atom
					if atom[:1] == '-':
						# allow incrementals
						atom = atom[1:]
					try:
						atom = Atom(atom)
					except InvalidAtom:
						atom = None
					else:
						if atom.blocker:
							atom = None
					if atom is None:
						writemsg(_("--- Invalid atom in %s: %s\n") % \
							(virtuals_file, atom_orig), noiselevel=-1)
					else:
						if atom_orig == str(atom):
							# normal atom, so return as Atom instance
							providers.append(atom)
						else:
							# atom has special prefix, so return as string
							providers.append(atom_orig)
				if providers:
					atoms_dict[virt_atom] = providers
			if atoms_dict:
				virtuals_list.append(atoms_dict)

		self._dirVirtuals = stack_dictlist(virtuals_list, incremental=True)

		for virt in self._dirVirtuals:
			# Preference for virtuals decreases from left to right.
			self._dirVirtuals[virt].reverse()

	def __deepcopy__(self, memo=None):
		if memo is None:
			memo = {}
		result = VirtualsManager(_copy=True)
		memo[id(self)] = result

		# immutable attributes (internal policy ensures lack of mutation)
		# _treeVirtuals is initilised by _populate_treeVirtuals().
		# Before that it's 'None'.
		result._treeVirtuals = self._treeVirtuals
		memo[id(self._treeVirtuals)] = self._treeVirtuals
		# _dirVirtuals is initilised by __init__.
		result._dirVirtuals = self._dirVirtuals
		memo[id(self._dirVirtuals)] = self._dirVirtuals

		# mutable attributes (change when add_depgraph_virtuals() is called)
		result._virtuals = deepcopy(self._virtuals, memo)
		result._depgraphVirtuals = deepcopy(self._depgraphVirtuals, memo)
		result._virts_p = deepcopy(self._virts_p, memo)

		return result

	def _compile_virtuals(self):
		"""Stack installed and profile virtuals.  Preference for virtuals
		decreases from left to right.
		Order of preference:
		1. installed and in profile
		2. installed only
		3. profile only
		"""

		assert self._treeVirtuals is not None, "_populate_treeVirtuals() must be called before " + \
			"any query about virtuals"

		# Virtuals by profile+tree preferences.
		ptVirtuals   = {}

		for virt, installed_list in self._treeVirtuals.items():
			profile_list = self._dirVirtuals.get(virt, None)
			if not profile_list:
				continue
			for cp in installed_list:
				if cp in profile_list:
					ptVirtuals.setdefault(virt, [])
					ptVirtuals[virt].append(cp)

		virtuals = stack_dictlist([ptVirtuals, self._treeVirtuals,
			self._dirVirtuals, self._depgraphVirtuals])
		self._virtuals = virtuals
		self._virts_p = None

	def getvirtuals(self):
		"""
		Computes self._virtuals if necessary and returns it.
		self._virtuals is only computed on the first call.
		"""
		if self._virtuals is None:
			self._compile_virtuals()

		return self._virtuals

	def _populate_treeVirtuals(self, vartree):
		"""
		Initialize _treeVirtuals from the given vartree.
		It must not have been initialized already, otherwise
		our assumptions about immutability don't hold.
		"""
		assert self._treeVirtuals is None, "treeVirtuals must not be reinitialized"

		self._treeVirtuals = {}

		for provide, cpv_list in vartree.get_all_provides().items():
			try:
				provide = Atom(provide)
			except InvalidAtom:
				continue
			self._treeVirtuals[provide.cp] = \
				[Atom(cpv_getkey(cpv)) for cpv in cpv_list]

	def populate_treeVirtuals_if_needed(self, vartree):
		"""
		Initialize _treeVirtuals if it hasn't been done already.
		This is a hack for consumers that already have an populated vartree.
		"""
		if self._treeVirtuals is not None:
			return

		self._populate_treeVirtuals(vartree)

	def add_depgraph_virtuals(self, mycpv, virts):
		"""This updates the preferences for old-style virtuals,
		affecting the behavior of dep_expand() and dep_check()
		calls. It can change dbapi.match() behavior since that
		calls dep_expand(). However, dbapi instances have
		internal match caches that are not invalidated when
		preferences are updated here. This can potentially
		lead to some inconsistency (relevant to bug #1343)."""

		#Ensure that self._virtuals is populated.
		if self._virtuals is None:
			self.getvirtuals()

		modified = False
		cp = Atom(cpv_getkey(mycpv))
		for virt in virts:
			try:
				virt = Atom(virt).cp
			except InvalidAtom:
				continue
			providers = self._virtuals.get(virt)
			if providers and cp in providers:
				continue
			providers = self._depgraphVirtuals.get(virt)
			if providers is None:
				providers = []
				self._depgraphVirtuals[virt] = providers
			if cp not in providers:
				providers.append(cp)
				modified = True

		if modified:
			self._compile_virtuals()

	def get_virts_p(self):
		if self._virts_p is not None:
			return self._virts_p

		virts = self.getvirtuals()
		virts_p = {}
		for x in virts:
			vkeysplit = x.split("/")
			if vkeysplit[1] not in virts_p:
				virts_p[vkeysplit[1]] = virts[x]
		self._virts_p = virts_p
		return virts_p
