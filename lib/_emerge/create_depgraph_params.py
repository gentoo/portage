# Copyright 1999-2018 Gentoo Foundation
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
	# with_test_deps: pull in test deps for packages matched by arguments
	# changed_deps: rebuild installed packages with outdated deps
	# changed_deps_report: report installed packages with outdated deps
	# changed_slot: rebuild installed packages with outdated SLOT metadata
	# binpkg_changed_deps: reject binary packages with outdated deps
	myparams = {"recurse" : True}

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

	binpkg_respect_use = myopts.get('--binpkg-respect-use')
	if binpkg_respect_use is not None:
		myparams['binpkg_respect_use'] = binpkg_respect_use
	elif '--usepkgonly' not in myopts:
		# If --binpkg-respect-use is not explicitly specified, we enable
		# the behavior automatically (like requested in bug #297549), as
		# long as it doesn't strongly conflict with other options that
		# have been specified.
		myparams['binpkg_respect_use'] = 'auto'

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

