# -*- coding:utf-8 -*-
# repoman: missing slot check
# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains the check used to find missing slot values
in dependencies."""

from portage.eapi import eapi_has_slot_operator

def check_missingslot(atom, mytype, eapi, portdb, qatracker, relative_path, my_aux):
	# If no slot or slot operator is specified in RDEP...
	if (not atom.blocker and not atom.slot and not atom.slot_operator
			and mytype == 'RDEPEND' and eapi_has_slot_operator(eapi)):
		# Check whether it doesn't match more than one.
		atom_matches = portdb.xmatch("match-all", atom)
		dep_slots = frozenset(
				portdb.aux_get(cpv, ['SLOT'])[0].split('/')[0]
					for cpv in atom_matches)

		if len(dep_slots) > 1:
			# See if it is a DEPEND as well. It's a very simple & dumb
			# check but should suffice for catching it.
			depend = my_aux['DEPEND'].split()
			if atom not in depend:
				return

			qatracker.add_error("dependency.missingslot", relative_path +
				": %s: '%s' matches more than one slot, please specify an explicit slot and/or use the := or :* slot operator" %
				(mytype, atom))
