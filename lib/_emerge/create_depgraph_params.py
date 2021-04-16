# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
from portage.util import writemsg_level

def create_depgraph_params(myopts, myaction):
	#configure emerge engine parameters
	#
	# autounmask:               enable autounmask
	# autounmask_keep_keywords: prevent autounmask changes to package.accept_keywords
	# autounmask_keep_license:  prevent autounmask changes to package.license
	# autounmask_keep_masks:    prevent autounmask changes to package.mask
	# autounmask_keep_use:      prevent autounmask changes to package.use
	# self:      include _this_ package regardless of if it is merged.
	# selective: exclude the package if it is merged
	# recurse:   go into the dependencies
	# deep:      go into the dependencies of already merged packages
	# empty:     pretend nothing is merged
	# complete:  completely account for all known dependencies
	# bdeps:     satisfy build time dependencies of packages that are
	#   already built, even though they are not strictly required
	# remove:    build graph for use in removing packages
	# rebuilt_binaries: replace installed packages with rebuilt binaries
	# rebuild_if_new_slot: rebuild or reinstall packages when
	#	slot/sub-slot := operator dependencies can be satisfied by a newer
	#	slot/sub-slot, so that older packages slots will become eligible for
	#	removal by the --depclean action as soon as possible
	# ignore_built_slot_operator_deps: ignore the slot/sub-slot := operator parts
	#	of dependencies that have been recorded when packages where built
	# ignore_soname_deps: ignore the soname dependencies of built
	#   packages, so that they do not trigger dependency resolution
	#   failures, or cause packages to be rebuilt or replaced.
	# ignore_world: ignore the @world package set and its dependencies
	# implicit_system_deps: Assume that packages may have implicit dependencies
	#   on packages which belong to the @system set.
	# with_test_deps: pull in test deps for packages matched by arguments
	# changed_deps: rebuild installed packages with outdated deps
	# changed_deps_report: report installed packages with outdated deps
	# changed_slot: rebuild installed packages with outdated SLOT metadata
	# binpkg_changed_deps: reject binary packages with outdated deps
	myparams = {"recurse" : True}

	binpkg_respect_use = myopts.get("--binpkg-respect-use")
	if binpkg_respect_use is not None:
		myparams["binpkg_respect_use"] = binpkg_respect_use
	elif "--usepkgonly" not in myopts:
		# If --binpkg-respect-use is not explicitly specified, we enable
		# the behavior automatically (like requested in bug #297549), as
		# long as it doesn't strongly conflict with other options that
		# have been specified.
		myparams["binpkg_respect_use"] = "auto"

	autounmask_keep_keywords = myopts.get("--autounmask-keep-keywords")
	autounmask_keep_masks = myopts.get("--autounmask-keep-masks")

	autounmask = myopts.get("--autounmask")
	autounmask_license = myopts.get('--autounmask-license', 'y' if autounmask is True else 'n')
	autounmask_use = 'n' if myparams.get('binpkg_respect_use') == 'y' else myopts.get('--autounmask-use')
	if autounmask == 'n':
		autounmask = False
	else:
		if autounmask is None:
			if autounmask_use in (None, 'y'):
				autounmask = True
			if autounmask_license in ('y',):
				autounmask = True

			# Do not enable package.accept_keywords or package.mask
			# changes by default.
			if autounmask_keep_keywords is None:
				autounmask_keep_keywords = True
			if autounmask_keep_masks is None:
				autounmask_keep_masks = True
		else:
			autounmask = True

	myparams['autounmask'] = autounmask
	myparams['autounmask_keep_use'] = True if autounmask_use == 'n' else False
	myparams['autounmask_keep_license'] = False if autounmask_license == 'y' else True
	myparams['autounmask_keep_keywords'] = False if autounmask_keep_keywords in (None, 'n') else True
	myparams['autounmask_keep_masks'] = False if autounmask_keep_masks in (None, 'n') else True

	bdeps = myopts.get("--with-bdeps")
	if bdeps is not None:
		myparams["bdeps"] = bdeps
	elif myaction == "remove" or (
		myopts.get("--with-bdeps-auto") != "n" and "--usepkg" not in myopts):
		myparams["bdeps"] = "auto"

	ignore_built_slot_operator_deps = myopts.get("--ignore-built-slot-operator-deps")
	if ignore_built_slot_operator_deps is not None:
		myparams["ignore_built_slot_operator_deps"] = ignore_built_slot_operator_deps

	myparams["ignore_soname_deps"] = myopts.get(
		"--ignore-soname-deps", "y")

	dynamic_deps = myopts.get("--dynamic-deps", "y") != "n" and "--nodeps" not in myopts
	if dynamic_deps:
		myparams["dynamic_deps"] = True

	myparams["implicit_system_deps"] =  myopts.get("--implicit-system-deps", "y") != "n"

	if myaction == "remove":
		myparams["remove"] = True
		myparams["complete"] = True
		myparams["selective"] = True
		return myparams

	if myopts.get('--ignore-world') is True:
		myparams['ignore_world'] = True

	rebuild_if_new_slot = myopts.get('--rebuild-if-new-slot')
	if rebuild_if_new_slot is not None:
		myparams['rebuild_if_new_slot'] = rebuild_if_new_slot

	changed_slot = myopts.get('--changed-slot') is True
	if changed_slot:
		myparams["changed_slot"] = True

	if "--update" in myopts or \
		"--newrepo" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts or \
		myopts.get("--changed-deps", "n") != "n" or \
		changed_slot or \
		myopts.get("--selective", "n") != "n":
		myparams["selective"] = True

	deep = myopts.get("--deep")
	if deep is not None and deep != 0:
		myparams["deep"] = deep

	complete_if_new_use = \
		myopts.get("--complete-graph-if-new-use")
	if complete_if_new_use is not None:
		myparams["complete_if_new_use"] = complete_if_new_use

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

	binpkg_changed_deps = myopts.get('--binpkg-changed-deps')
	if binpkg_changed_deps is not None:
		myparams['binpkg_changed_deps'] = binpkg_changed_deps
	elif '--usepkgonly' not in myopts:
		# In order to avoid dependency resolution issues due to changed
		# dependencies, enable this automatically, as long as it doesn't
		# strongly conflict with other options that have been specified.
		myparams['binpkg_changed_deps'] = 'auto'

	changed_deps = myopts.get('--changed-deps')
	if changed_deps is not None:
		myparams['changed_deps'] = changed_deps

	changed_deps_report = myopts.get('--changed-deps-report', 'n') == 'y'
	if changed_deps_report:
		myparams['changed_deps_report'] = True

	if myopts.get("--selective") == "n":
		# --selective=n can be used to remove selective
		# behavior that may have been implied by some
		# other option like --update.
		myparams.pop("selective", None)

	with_test_deps = myopts.get("--with-test-deps")
	if with_test_deps is not None:
		myparams["with_test_deps"] = with_test_deps

	if '--debug' in myopts:
		writemsg_level('\n\nmyparams %s\n\n' % myparams,
			noiselevel=-1, level=logging.DEBUG)

	return myparams
