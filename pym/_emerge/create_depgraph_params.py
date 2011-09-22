# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
from portage.util import writemsg_level

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
	# rebuilt_binaries: replace installed packages with rebuilt binaries
	myparams = {"recurse" : True}

	bdeps = myopts.get("--with-bdeps")
	if bdeps is not None:
		myparams["bdeps"] = bdeps

	if myaction == "remove":
		myparams["remove"] = True
		myparams["complete"] = True
		myparams["selective"] = True
		return myparams

	if "--update" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts or \
		myopts.get("--selective", "n") != "n":
		myparams["selective"] = True

	deep = myopts.get("--deep")
	if deep is not None and deep != 0:
		myparams["deep"] = deep

	complete_if_new_ver = \
		myopts.get("--complete-graph-if-new-ver")
	if complete_if_new_ver is not None:
		myparams["complete_if_new_ver"] = complete_if_new_ver

	if ("--complete-graph" in myopts or "--rebuild-if-new-rev" in myopts or
		"--rebuild-if-new-ver" in myopts or "--rebuild-if-unbuilt" in myopts):
		myparams["complete"] = True
	if "--emptytree" in myopts:
		myparams["empty"] = True
		myparams["deep"] = True
		myparams.pop("selective", None)

	if "--nodeps" in myopts:
		myparams.pop("recurse", None)
		myparams.pop("deep", None)
		myparams.pop("complete", None)

	rebuilt_binaries = myopts.get('--rebuilt-binaries')
	if rebuilt_binaries is True or \
		rebuilt_binaries != 'n' and \
		'--usepkgonly' in myopts and \
		myopts.get('--deep') is True and \
		'--update' in myopts:
		myparams['rebuilt_binaries'] = True

	binpkg_respect_use = myopts.get('--binpkg-respect-use')
	if binpkg_respect_use is not None:
		myparams['binpkg_respect_use'] = binpkg_respect_use
	elif '--usepkgonly' not in myopts and \
		myopts.get('--rebuilt-binaries') is not True:
		# If --binpkg-respect-use is not explicitly specified, we enable
		# the behavior automatically (like requested in bug #297549), as
		# long as it doesn't strongly conflict with other options that
		# have been specified.
		myparams['binpkg_respect_use'] = 'auto'

	if myopts.get("--selective") == "n":
		# --selective=n can be used to remove selective
		# behavior that may have been implied by some
		# other option like --update.
		myparams.pop("selective", None)

	if '--debug' in myopts:
		writemsg_level('\n\nmyparams %s\n\n' % myparams,
			noiselevel=-1, level=logging.DEBUG)

	return myparams

