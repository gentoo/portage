# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import platform
import sys

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'logging',
	'portage.util:writemsg_level',
	'textwrap',
	'_emerge.actions:load_emerge_config,run_action,' + \
		'validate_ebuild_environment',
	'_emerge.help:help@emerge_help',
)
from portage import os

if sys.hexversion >= 0x3000000:
	long = int

options=[
"--alphabetical",
"--ask-enter-invalid",
"--buildpkgonly",
"--changed-use",
"--changelog",    "--columns",
"--debug",
"--digest",
"--emptytree",
"--fetchonly",    "--fetch-all-uri",
"--ignore-default-opts",
"--noconfmem",
"--newuse",
"--nodeps",       "--noreplace",
"--nospinner",    "--oneshot",
"--onlydeps",     "--pretend",
"--quiet-repo-display",
"--quiet-unmerge-warn",
"--resume",
"--searchdesc",
"--skipfirst",
"--tree",
"--unordered-display",
"--update",
"--verbose",
"--verbose-main-repo-display",
]

shortmapping={
"1":"--oneshot",
"B":"--buildpkgonly",
"c":"--depclean",
"C":"--unmerge",
"d":"--debug",
"e":"--emptytree",
"f":"--fetchonly", "F":"--fetch-all-uri",
"h":"--help",
"l":"--changelog",
"n":"--noreplace", "N":"--newuse",
"o":"--onlydeps",  "O":"--nodeps",
"p":"--pretend",   "P":"--prune",
"r":"--resume",
"s":"--search",    "S":"--searchdesc",
"t":"--tree",
"u":"--update",
"v":"--verbose",   "V":"--version"
}

COWSAY_MOO = """

  Larry loves Gentoo (%s)

 _______________________
< Have you mooed today? >
 -----------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\ 
                ||----w |
                ||     ||

"""

def multiple_actions(action1, action2):
	sys.stderr.write("\n!!! Multiple actions requested... Please choose one only.\n")
	sys.stderr.write("!!! '%s' or '%s'\n\n" % (action1, action2))
	sys.exit(1)

def insert_optional_args(args):
	"""
	Parse optional arguments and insert a value if one has
	not been provided. This is done before feeding the args
	to the optparse parser since that parser does not support
	this feature natively.
	"""

	class valid_integers(object):
		def __contains__(self, s):
			try:
				return int(s) >= 0
			except (ValueError, OverflowError):
				return False

	valid_integers = valid_integers()

	class valid_floats(object):
		def __contains__(self, s):
			try:
				return float(s) >= 0
			except (ValueError, OverflowError):
				return False

	valid_floats = valid_floats()

	y_or_n = ('y', 'n',)

	new_args = []

	default_arg_opts = {
		'--ask'                  : y_or_n,
		'--autounmask'           : y_or_n,
		'--autounmask-keep-masks': y_or_n,
		'--autounmask-unrestricted-atoms' : y_or_n,
		'--autounmask-write'     : y_or_n,
		'--buildpkg'             : y_or_n,
		'--complete-graph'       : y_or_n,
		'--deep'       : valid_integers,
		'--depclean-lib-check'   : y_or_n,
		'--deselect'             : y_or_n,
		'--binpkg-respect-use'   : y_or_n,
		'--fail-clean'           : y_or_n,
		'--getbinpkg'            : y_or_n,
		'--getbinpkgonly'        : y_or_n,
		'--jobs'       : valid_integers,
		'--keep-going'           : y_or_n,
		'--load-average'         : valid_floats,
		'--package-moves'        : y_or_n,
		'--quiet'                : y_or_n,
		'--quiet-build'          : y_or_n,
		'--rebuild-if-new-slot': y_or_n,
		'--rebuild-if-new-rev'   : y_or_n,
		'--rebuild-if-new-ver'   : y_or_n,
		'--rebuild-if-unbuilt'   : y_or_n,
		'--rebuilt-binaries'     : y_or_n,
		'--root-deps'  : ('rdeps',),
		'--select'               : y_or_n,
		'--selective'            : y_or_n,
		"--use-ebuild-visibility": y_or_n,
		'--usepkg'               : y_or_n,
		'--usepkgonly'           : y_or_n,
	}

	short_arg_opts = {
		'D' : valid_integers,
		'j' : valid_integers,
	}

	# Don't make things like "-kn" expand to "-k n"
	# since existence of -n makes it too ambiguous.
	short_arg_opts_n = {
		'a' : y_or_n,
		'b' : y_or_n,
		'g' : y_or_n,
		'G' : y_or_n,
		'k' : y_or_n,
		'K' : y_or_n,
		'q' : y_or_n,
	}

	arg_stack = args[:]
	arg_stack.reverse()
	while arg_stack:
		arg = arg_stack.pop()

		default_arg_choices = default_arg_opts.get(arg)
		if default_arg_choices is not None:
			new_args.append(arg)
			if arg_stack and arg_stack[-1] in default_arg_choices:
				new_args.append(arg_stack.pop())
			else:
				# insert default argument
				new_args.append('True')
			continue

		if arg[:1] != "-" or arg[:2] == "--":
			new_args.append(arg)
			continue

		match = None
		for k, arg_choices in short_arg_opts.items():
			if k in arg:
				match = k
				break

		if match is None:
			for k, arg_choices in short_arg_opts_n.items():
				if k in arg:
					match = k
					break

		if match is None:
			new_args.append(arg)
			continue

		if len(arg) == 2:
			new_args.append(arg)
			if arg_stack and arg_stack[-1] in arg_choices:
				new_args.append(arg_stack.pop())
			else:
				# insert default argument
				new_args.append('True')
			continue

		# Insert an empty placeholder in order to
		# satisfy the requirements of optparse.

		new_args.append("-" + match)
		opt_arg = None
		saved_opts = None

		if arg[1:2] == match:
			if match not in short_arg_opts_n and arg[2:] in arg_choices:
				opt_arg = arg[2:]
			else:
				saved_opts = arg[2:]
				opt_arg = "True"
		else:
			saved_opts = arg[1:].replace(match, "")
			opt_arg = "True"

		if opt_arg is None and arg_stack and \
			arg_stack[-1] in arg_choices:
			opt_arg = arg_stack.pop()

		if opt_arg is None:
			new_args.append("True")
		else:
			new_args.append(opt_arg)

		if saved_opts is not None:
			# Recycle these on arg_stack since they
			# might contain another match.
			arg_stack.append("-" + saved_opts)

	return new_args

def _find_bad_atoms(atoms, less_strict=False):
	"""
	Declares all atoms as invalid that have an operator,
	a use dependency, a blocker or a repo spec.
	It accepts atoms with wildcards.
	In less_strict mode it accepts operators and repo specs.
	"""
	bad_atoms = []
	for x in ' '.join(atoms).split():
		bad_atom = False
		try:
			atom = portage.dep.Atom(x, allow_wildcard=True, allow_repo=less_strict)
		except portage.exception.InvalidAtom:
			try:
				atom = portage.dep.Atom("*/"+x, allow_wildcard=True, allow_repo=less_strict)
			except portage.exception.InvalidAtom:
				bad_atom = True

		if bad_atom or (atom.operator and not less_strict) or atom.blocker or atom.use:
			bad_atoms.append(x)
	return bad_atoms


def parse_opts(tmpcmdline, silent=False):
	myaction=None
	myopts = {}
	myfiles=[]

	actions = frozenset([
		"clean", "check-news", "config", "depclean", "help",
		"info", "list-sets", "metadata", "moo",
		"prune", "regen",  "search",
		"sync",  "unmerge", "version",
	])

	longopt_aliases = {"--cols":"--columns", "--skip-first":"--skipfirst"}
	y_or_n = ("y", "n")
	true_y_or_n = ("True", "y", "n")
	true_y = ("True", "y")
	argument_options = {

		"--ask": {
			"shortopt" : "-a",
			"help"    : "prompt before performing any actions",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--autounmask": {
			"help"    : "automatically unmask packages",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--autounmask-unrestricted-atoms": {
			"help"    : "write autounmask changes with >= atoms if possible",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--autounmask-keep-masks": {
			"help"    : "don't add package.unmask entries",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--autounmask-write": {
			"help"    : "write changes made by --autounmask to disk",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--accept-properties": {
			"help":"temporarily override ACCEPT_PROPERTIES",
			"action":"store"
		},

		"--backtrack": {

			"help"   : "Specifies how many times to backtrack if dependency " + \
				"calculation fails ",

			"action" : "store"
		},

		"--buildpkg": {
			"shortopt" : "-b",
			"help"     : "build binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--buildpkg-exclude": {
			"help"   :"A space separated list of package atoms for which " + \
				"no binary packages should be built. This option overrides all " + \
				"possible ways to enable building of binary packages.",

			"action" : "append"
		},

		"--config-root": {
			"help":"specify the location for portage configuration files",
			"action":"store"
		},
		"--color": {
			"help":"enable or disable color output",
			"type":"choice",
			"choices":("y", "n")
		},

		"--complete-graph": {
			"help"    : "completely account for all known dependencies",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--complete-graph-if-new-use": {
			"help"    : "trigger --complete-graph behavior if USE or IUSE will change for an installed package",
			"type"    : "choice",
			"choices" : y_or_n
		},

		"--complete-graph-if-new-ver": {
			"help"    : "trigger --complete-graph behavior if an installed package version will change (upgrade or downgrade)",
			"type"    : "choice",
			"choices" : y_or_n
		},

		"--deep": {

			"shortopt" : "-D",

			"help"   : "Specifies how deep to recurse into dependencies " + \
				"of packages given as arguments. If no argument is given, " + \
				"depth is unlimited. Default behavior is to skip " + \
				"dependencies of installed packages.",

			"action" : "store"
		},

		"--depclean-lib-check": {
			"help"    : "check for consumers of libraries before removing them",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--deselect": {
			"help"    : "remove atoms/sets from the world file",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--dynamic-deps": {
			"help": "substitute the dependencies of installed packages with the dependencies of unbuilt ebuilds",
			"type": "choice",
			"choices": y_or_n
		},

		"--exclude": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge won't  install any ebuild or binary package that " + \
				"matches any of the given package atoms.",

			"action" : "append"
		},

		"--fail-clean": {
			"help"    : "clean temp files after build failure",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--ignore-built-slot-operator-deps": {
			"help": "Ignore the slot/sub-slot := operator parts of dependencies that have "
				"been recorded when packages where built. This option is intended "
				"only for debugging purposes, and it only affects built packages "
				"that specify slot/sub-slot := operator dependencies using the "
				"experimental \"4-slot-abi\" EAPI.",
			"type": "choice",
			"choices": y_or_n
		},

		"--jobs": {

			"shortopt" : "-j",

			"help"   : "Specifies the number of packages to build " + \
				"simultaneously.",

			"action" : "store"
		},

		"--keep-going": {
			"help"    : "continue as much as possible after an error",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--load-average": {

			"help"   :"Specifies that no new builds should be started " + \
				"if there are other builds running and the load average " + \
				"is at least LOAD (a floating-point number).",

			"action" : "store"
		},

		"--misspell-suggestions": {
			"help"    : "enable package name misspell suggestions",
			"type"    : "choice",
			"choices" : ("y", "n")
		},

		"--with-bdeps": {
			"help":"include unnecessary build time dependencies",
			"type":"choice",
			"choices":("y", "n")
		},
		"--reinstall": {
			"help":"specify conditions to trigger package reinstallation",
			"type":"choice",
			"choices":["changed-use"]
		},

		"--reinstall-atoms": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will treat matching packages as if they are not " + \
				"installed, and reinstall them if necessary. Implies --deep.",

			"action" : "append",
		},

		"--binpkg-respect-use": {
			"help"    : "discard binary packages if their use flags \
				don't match the current configuration",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--getbinpkg": {
			"shortopt" : "-g",
			"help"     : "fetch binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--getbinpkgonly": {
			"shortopt" : "-G",
			"help"     : "fetch binary packages only",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--usepkg-exclude": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will ignore matching binary packages. ",

			"action" : "append",
		},

		"--rebuild-exclude": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will not rebuild these packages due to the " + \
				"--rebuild flag. ",

			"action" : "append",
		},

		"--rebuild-ignore": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will not rebuild packages that depend on matching " + \
				"packages due to the --rebuild flag. ",

			"action" : "append",
		},

		"--package-moves": {
			"help"     : "perform package moves when necessary",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--quiet": {
			"shortopt" : "-q",
			"help"     : "reduced or condensed output",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--quiet-build": {
			"help"     : "redirect build output to logs",
			"type"     : "choice",
			"choices"  : true_y_or_n,
		},

		"--rebuild-if-new-slot": {
			"help"     : ("Automatically rebuild or reinstall packages when slot/sub-slot := "
				"operator dependencies can be satisfied by a newer slot, so that "
				"older packages slots will become eligible for removal by the "
				"--depclean action as soon as possible."),
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--rebuild-if-new-rev": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built, " + \
				"if the dependency is not already installed with the " + \
				"same version and revision.",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--rebuild-if-new-ver": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built, " + \
				"if the dependency is not already installed with the " + \
				"same version. Revision numbers are ignored.",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--rebuild-if-unbuilt": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built.",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--rebuilt-binaries": {
			"help"     : "replace installed packages with binary " + \
			             "packages that have been rebuilt",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},
		
		"--rebuilt-binaries-timestamp": {
			"help"   : "use only binaries that are newer than this " + \
			           "timestamp for --rebuilt-binaries",
			"action" : "store"
		},

		"--root": {
		 "help"   : "specify the target root filesystem for merging packages",
		 "action" : "store"
		},

		"--root-deps": {
			"help"    : "modify interpretation of depedencies",
			"type"    : "choice",
			"choices" :("True", "rdeps")
		},

		"--select": {
			"help"    : "add specified packages to the world set " + \
			            "(inverse of --oneshot)",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--selective": {
			"help"    : "identical to --noreplace",
			"type"    : "choice",
			"choices" : true_y_or_n
		},

		"--use-ebuild-visibility": {
			"help"     : "use unbuilt ebuild metadata for visibility checks on built packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--useoldpkg-atoms": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will prefer matching binary packages over newer unbuilt packages. ",

			"action" : "append",
		},

		"--usepkg": {
			"shortopt" : "-k",
			"help"     : "use binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},

		"--usepkgonly": {
			"shortopt" : "-K",
			"help"     : "use only binary packages",
			"type"     : "choice",
			"choices"  : true_y_or_n
		},
	}

	from optparse import OptionParser
	parser = OptionParser()
	if parser.has_option("--help"):
		parser.remove_option("--help")

	for action_opt in actions:
		parser.add_option("--" + action_opt, action="store_true",
			dest=action_opt.replace("-", "_"), default=False)
	for myopt in options:
		parser.add_option(myopt, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)
	for shortopt, longopt in shortmapping.items():
		parser.add_option("-" + shortopt, action="store_true",
			dest=longopt.lstrip("--").replace("-", "_"), default=False)
	for myalias, myopt in longopt_aliases.items():
		parser.add_option(myalias, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)

	for myopt, kwargs in argument_options.items():
		shortopt = kwargs.pop("shortopt", None)
		args = [myopt]
		if shortopt is not None:
			args.append(shortopt)
		parser.add_option(dest=myopt.lstrip("--").replace("-", "_"),
			*args, **kwargs)

	tmpcmdline = insert_optional_args(tmpcmdline)

	myoptions, myargs = parser.parse_args(args=tmpcmdline)

	if myoptions.ask in true_y:
		myoptions.ask = True
	else:
		myoptions.ask = None

	if myoptions.autounmask in true_y:
		myoptions.autounmask = True

	if myoptions.autounmask_unrestricted_atoms in true_y:
		myoptions.autounmask_unrestricted_atoms = True

	if myoptions.autounmask_keep_masks in true_y:
		myoptions.autounmask_keep_masks = True

	if myoptions.autounmask_write in true_y:
		myoptions.autounmask_write = True

	if myoptions.buildpkg in true_y:
		myoptions.buildpkg = True

	if myoptions.buildpkg_exclude:
		bad_atoms = _find_bad_atoms(myoptions.buildpkg_exclude, less_strict=True)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --buildpkg-exclude parameter: '%s'\n" % \
				(",".join(bad_atoms),))

	if myoptions.changed_use is not False:
		myoptions.reinstall = "changed-use"
		myoptions.changed_use = False

	if myoptions.deselect in true_y:
		myoptions.deselect = True

	if myoptions.binpkg_respect_use is not None:
		if myoptions.binpkg_respect_use in true_y:
			myoptions.binpkg_respect_use = 'y'
		else:
			myoptions.binpkg_respect_use = 'n'

	if myoptions.complete_graph in true_y:
		myoptions.complete_graph = True
	else:
		myoptions.complete_graph = None

	if myoptions.depclean_lib_check in true_y:
		myoptions.depclean_lib_check = True

	if myoptions.exclude:
		bad_atoms = _find_bad_atoms(myoptions.exclude)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --exclude parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.reinstall_atoms:
		bad_atoms = _find_bad_atoms(myoptions.reinstall_atoms)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --reinstall-atoms parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.rebuild_exclude:
		bad_atoms = _find_bad_atoms(myoptions.rebuild_exclude)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --rebuild-exclude parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.rebuild_ignore:
		bad_atoms = _find_bad_atoms(myoptions.rebuild_ignore)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --rebuild-ignore parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.usepkg_exclude:
		bad_atoms = _find_bad_atoms(myoptions.usepkg_exclude)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --usepkg-exclude parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.useoldpkg_atoms:
		bad_atoms = _find_bad_atoms(myoptions.useoldpkg_atoms)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --useoldpkg-atoms parameter: '%s' (only package names and slot atoms (with wildcards) allowed)\n" % \
				(",".join(bad_atoms),))

	if myoptions.fail_clean in true_y:
		myoptions.fail_clean = True

	if myoptions.getbinpkg in true_y:
		myoptions.getbinpkg = True
	else:
		myoptions.getbinpkg = None

	if myoptions.getbinpkgonly in true_y:
		myoptions.getbinpkgonly = True
	else:
		myoptions.getbinpkgonly = None

	if myoptions.keep_going in true_y:
		myoptions.keep_going = True
	else:
		myoptions.keep_going = None

	if myoptions.package_moves in true_y:
		myoptions.package_moves = True

	if myoptions.quiet in true_y:
		myoptions.quiet = True
	else:
		myoptions.quiet = None

	if myoptions.quiet_build in true_y:
		myoptions.quiet_build = 'y'

	if myoptions.rebuild_if_new_slot in true_y:
		myoptions.rebuild_if_new_slot = 'y'

	if myoptions.rebuild_if_new_ver in true_y:
		myoptions.rebuild_if_new_ver = True
	else:
		myoptions.rebuild_if_new_ver = None

	if myoptions.rebuild_if_new_rev in true_y:
		myoptions.rebuild_if_new_rev = True
		myoptions.rebuild_if_new_ver = None
	else:
		myoptions.rebuild_if_new_rev = None

	if myoptions.rebuild_if_unbuilt in true_y:
		myoptions.rebuild_if_unbuilt = True
		myoptions.rebuild_if_new_rev = None
		myoptions.rebuild_if_new_ver = None
	else:
		myoptions.rebuild_if_unbuilt = None

	if myoptions.rebuilt_binaries in true_y:
		myoptions.rebuilt_binaries = True

	if myoptions.root_deps in true_y:
		myoptions.root_deps = True

	if myoptions.select in true_y:
		myoptions.select = True
		myoptions.oneshot = False
	elif myoptions.select == "n":
		myoptions.oneshot = True

	if myoptions.selective in true_y:
		myoptions.selective = True

	if myoptions.backtrack is not None:

		try:
			backtrack = int(myoptions.backtrack)
		except (OverflowError, ValueError):
			backtrack = -1

		if backtrack < 0:
			backtrack = None
			if not silent:
				parser.error("Invalid --backtrack parameter: '%s'\n" % \
					(myoptions.backtrack,))

		myoptions.backtrack = backtrack

	if myoptions.deep is not None:
		deep = None
		if myoptions.deep == "True":
			deep = True
		else:
			try:
				deep = int(myoptions.deep)
			except (OverflowError, ValueError):
				deep = -1

		if deep is not True and deep < 0:
			deep = None
			if not silent:
				parser.error("Invalid --deep parameter: '%s'\n" % \
					(myoptions.deep,))

		myoptions.deep = deep

	if myoptions.jobs:
		jobs = None
		if myoptions.jobs == "True":
			jobs = True
		else:
			try:
				jobs = int(myoptions.jobs)
			except ValueError:
				jobs = -1

		if jobs is not True and \
			jobs < 1:
			jobs = None
			if not silent:
				parser.error("Invalid --jobs parameter: '%s'\n" % \
					(myoptions.jobs,))

		myoptions.jobs = jobs

	if myoptions.load_average == "True":
		myoptions.load_average = None

	if myoptions.load_average:
		try:
			load_average = float(myoptions.load_average)
		except ValueError:
			load_average = 0.0

		if load_average <= 0.0:
			load_average = None
			if not silent:
				parser.error("Invalid --load-average parameter: '%s'\n" % \
					(myoptions.load_average,))

		myoptions.load_average = load_average
	
	if myoptions.rebuilt_binaries_timestamp:
		try:
			rebuilt_binaries_timestamp = int(myoptions.rebuilt_binaries_timestamp)
		except ValueError:
			rebuilt_binaries_timestamp = -1

		if rebuilt_binaries_timestamp < 0:
			rebuilt_binaries_timestamp = 0
			if not silent:
				parser.error("Invalid --rebuilt-binaries-timestamp parameter: '%s'\n" % \
					(myoptions.rebuilt_binaries_timestamp,))

		myoptions.rebuilt_binaries_timestamp = rebuilt_binaries_timestamp

	if myoptions.use_ebuild_visibility in true_y:
		myoptions.use_ebuild_visibility = True
	else:
		# None or "n"
		pass

	if myoptions.usepkg in true_y:
		myoptions.usepkg = True
	else:
		myoptions.usepkg = None

	if myoptions.usepkgonly in true_y:
		myoptions.usepkgonly = True
	else:
		myoptions.usepkgonly = None

	for myopt in options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"))
		if v:
			myopts[myopt] = True

	for myopt in argument_options:
		v = getattr(myoptions, myopt.lstrip("--").replace("-", "_"), None)
		if v is not None:
			myopts[myopt] = v

	if myoptions.searchdesc:
		myoptions.search = True

	for action_opt in actions:
		v = getattr(myoptions, action_opt.replace("-", "_"))
		if v:
			if myaction:
				multiple_actions(myaction, action_opt)
				sys.exit(1)
			myaction = action_opt

	if myaction is None and myoptions.deselect is True:
		myaction = 'deselect'

	if myargs and isinstance(myargs[0], bytes):
		for i in range(len(myargs)):
			myargs[i] = portage._unicode_decode(myargs[i])

	myfiles += myargs

	return myaction, myopts, myfiles

def profile_check(trees, myaction):
	if myaction in ("help", "info", "search", "sync", "version"):
		return os.EX_OK
	for root_trees in trees.values():
		if root_trees["root_config"].settings.profiles:
			continue
		# generate some profile related warning messages
		validate_ebuild_environment(trees)
		msg = ("Your current profile is invalid. If you have just changed "
			"your profile configuration, you should revert back to the "
			"previous configuration. Allowed actions are limited to "
			"--help, --info, --search, --sync, and --version.")
		writemsg_level("".join("!!! %s\n" % l for l in textwrap.wrap(msg, 70)),
			level=logging.ERROR, noiselevel=-1)
		return 1
	return os.EX_OK

def emerge_main(args=None):
	"""
	@param args: command arguments (default: sys.argv[1:])
	@type args: list
	"""
	if args is None:
		args = sys.argv[1:]

	portage._disable_legacy_globals()
	portage._internal_warnings = True
	# Disable color until we're sure that it should be enabled (after
	# EMERGE_DEFAULT_OPTS has been parsed).
	portage.output.havecolor = 0

	# This first pass is just for options that need to be known as early as
	# possible, such as --config-root.  They will be parsed again later,
	# together with EMERGE_DEFAULT_OPTS (which may vary depending on the
	# the value of --config-root).
	myaction, myopts, myfiles = parse_opts(args, silent=True)
	if "--debug" in myopts:
		os.environ["PORTAGE_DEBUG"] = "1"
	if "--config-root" in myopts:
		os.environ["PORTAGE_CONFIGROOT"] = myopts["--config-root"]
	if "--root" in myopts:
		os.environ["ROOT"] = myopts["--root"]
	if "--accept-properties" in myopts:
		os.environ["ACCEPT_PROPERTIES"] = myopts["--accept-properties"]

	# optimize --help (no need to load config / EMERGE_DEFAULT_OPTS)
	if myaction == "help":
		emerge_help()
		return os.EX_OK
	elif myaction == "moo":
		print(COWSAY_MOO % platform.system())
		return os.EX_OK

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)
	if myaction == "sync":
		portage._sync_disabled_warnings = True
	settings, trees, mtimedb = load_emerge_config()
	rval = profile_check(trees, myaction)
	if rval != os.EX_OK:
		return rval

	tmpcmdline = []
	if "--ignore-default-opts" not in myopts:
		tmpcmdline.extend(settings["EMERGE_DEFAULT_OPTS"].split())
	tmpcmdline.extend(args)
	myaction, myopts, myfiles = parse_opts(tmpcmdline)

	return run_action(settings, trees, mtimedb, myaction, myopts, myfiles,
		gc_locals=locals().clear)
