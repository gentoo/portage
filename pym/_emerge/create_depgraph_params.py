# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

def create_depgraph_params(myopts, myaction):
	#configure emerge engine parameters
	#
	# self:      include _this_ package regardless of if it is merged.
	# selective: exclude the package if it is merged
	# recurse:   go into the dependencies
	# deep:      go into the dependencies of already merged packages
	# empty:     pretend nothing is merged
	# complete:  completely account for all known dependencies
	# remove:    build graph for use in removing packages
	myparams = set(["recurse"])

	if myaction == "remove":
		myparams.add("remove")
		myparams.add("complete")
		return myparams

	if "--update" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts:
		myparams.add("selective")
	if "--emptytree" in myopts:
		myparams.add("empty")
		myparams.discard("selective")
	if "--nodeps" in myopts:
		myparams.discard("recurse")
	if "--deep" in myopts:
		myparams.add("deep")
	if "--complete-graph" in myopts:
		myparams.add("complete")
	return myparams

