# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import locale
import platform
import sys

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'logging',
	'portage.dep:Atom',
	'portage.util:writemsg_level',
	'textwrap',
	'_emerge.actions:load_emerge_config,run_action,' + \
		'validate_ebuild_environment',
	'_emerge.help:emerge_help',
	'_emerge.is_valid_package_atom:insert_category_into_atom'
)
from portage import os
from portage.sync import _SUBMODULE_PATH_MAP


options=[
"--alphabetical",
"--ask-enter-invalid",
"--buildpkgonly",
"--changed-use",
"--columns",
"--debug",
"--digest",
"--emptytree",
"--verbose-conflicts",
"--fetchonly",    "--fetch-all-uri",
"--ignore-default-opts",
"--noconfmem",
"--newrepo",
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
"n":"--noreplace", "N":"--newuse",
"o":"--onlydeps",  "O":"--nodeps",
"p":"--pretend",   "P":"--prune",
"r":"--resume",
"s":"--search",    "S":"--searchdesc",
"t":"--tree",
"u":"--update",    "U":"--changed-use",
"V":"--version"
}

COWSAY_MOO = r"""

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

	class valid_integers:
		def __contains__(self, s):
			try:
				return int(s) >= 0
			except (ValueError, OverflowError):
				return False

	valid_integers = valid_integers()

	class valid_floats:
		def __contains__(self, s):
			try:
				return float(s) >= 0
			except (ValueError, OverflowError):
				return False

	valid_floats = valid_floats()

	y_or_n = ('y', 'n',)

	new_args = []

	default_arg_opts = {
		'--alert'                : y_or_n,
		'--ask'                  : y_or_n,
		'--autounmask'           : y_or_n,
		'--autounmask-continue'  : y_or_n,
		'--autounmask-only'      : y_or_n,
		'--autounmask-keep-keywords' : y_or_n,
		'--autounmask-keep-masks': y_or_n,
		'--autounmask-unrestricted-atoms' : y_or_n,
		'--autounmask-write'     : y_or_n,
		'--binpkg-changed-deps'  : y_or_n,
		'--buildpkg'             : y_or_n,
		'--changed-deps'         : y_or_n,
		'--changed-slot'         : y_or_n,
		'--changed-deps-report'  : y_or_n,
		'--complete-graph'       : y_or_n,
		'--deep'       : valid_integers,
		'--depclean-lib-check'   : y_or_n,
		'--deselect'             : y_or_n,
		'--binpkg-respect-use'   : y_or_n,
		'--fail-clean'           : y_or_n,
		'--fuzzy-search'         : y_or_n,
		'--getbinpkg'            : y_or_n,
		'--getbinpkgonly'        : y_or_n,
		'--ignore-world'         : y_or_n,
		'--jobs'       : valid_integers,
		'--keep-going'           : y_or_n,
		'--load-average'         : valid_floats,
		'--onlydeps-with-rdeps'  : y_or_n,
		'--package-moves'        : y_or_n,
		'--quiet'                : y_or_n,
		'--quiet-build'          : y_or_n,
		'--quiet-fail'           : y_or_n,
		'--read-news'            : y_or_n,
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
		'--verbose'              : y_or_n,
		'--verbose-slot-rebuilds': y_or_n,
		'--with-test-deps'       : y_or_n,
	}

	short_arg_opts = {
		'D' : valid_integers,
		'j' : valid_integers,
		'l' : valid_floats,
	}

	# Don't make things like "-kn" expand to "-k n"
	# since existence of -n makes it too ambiguous.
	short_arg_opts_n = {
		'a' : y_or_n,
		'A' : y_or_n,
		'b' : y_or_n,
		'g' : y_or_n,
		'G' : y_or_n,
		'k' : y_or_n,
		'K' : y_or_n,
		'q' : y_or_n,
		'v' : y_or_n,
		'w' : y_or_n,
		'W' : y_or_n,
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
		atom = x
		if "/" not in x.split(":")[0]:
			x_cat = insert_category_into_atom(x, 'dummy-category')
			if x_cat is not None:
				atom = x_cat

		bad_atom = False
		try:
			atom = Atom(atom, allow_wildcard=True, allow_repo=less_strict)
		except portage.exception.InvalidAtom:
			bad_atom = True

		if bad_atom or (atom.operator and not less_strict) or atom.blocker or atom.use:
			bad_atoms.append(x)
	return bad_atoms


def parse_opts(tmpcmdline, silent=False):
	myaction=None
	myopts = {}

	actions = frozenset([
		"clean", "check-news", "config", "depclean", "help",
		"info", "list-sets", "metadata", "moo",
		"prune", "rage-clean", "regen",  "search",
		"sync",  "unmerge", "version",
	])

	longopt_aliases = {"--cols":"--columns", "--skip-first":"--skipfirst"}
	y_or_n = ("y", "n")
	true_y_or_n = ("True", "y", "n")
	true_y = ("True", "y")
	argument_options = {

		"--alert": {
			"shortopt" : "-A",
			"help"    : "alert (terminal bell) on prompts",
			"choices" : true_y_or_n
		},

		"--ask": {
			"shortopt" : "-a",
			"help"    : "prompt before performing any actions",
			"choices" : true_y_or_n
		},

		"--autounmask": {
			"help"    : "automatically unmask packages",
			"choices" : true_y_or_n
		},

		"--autounmask-backtrack": {
			"help": ("continue backtracking when there are autounmask "
				"configuration changes"),
			"choices":("y", "n")
		},

		"--autounmask-continue": {
			"help"    : "write autounmask changes and continue",
			"choices" : true_y_or_n
		},

		"--autounmask-only": {
			"help"    : "only perform --autounmask",
			"choices" : true_y_or_n
		},

		"--autounmask-license": {
			"help"    : "allow autounmask to change package.license",
			"choices" : y_or_n
		},

		"--autounmask-unrestricted-atoms": {
			"help"    : "write autounmask changes with >= atoms if possible",
			"choices" : true_y_or_n
		},

		"--autounmask-use": {
			"help"    : "allow autounmask to change package.use",
			"choices" : y_or_n
		},

		"--autounmask-keep-keywords": {
			"help"    : "don't add package.accept_keywords entries",
			"choices" : true_y_or_n
		},

		"--autounmask-keep-masks": {
			"help"    : "don't add package.unmask entries",
			"choices" : true_y_or_n
		},

		"--autounmask-write": {
			"help"    : "write changes made by --autounmask to disk",
			"choices" : true_y_or_n
		},

		"--accept-properties": {
			"help":"temporarily override ACCEPT_PROPERTIES",
			"action":"store"
		},

		"--accept-restrict": {
			"help":"temporarily override ACCEPT_RESTRICT",
			"action":"store"
		},

		"--backtrack": {

			"help"   : "Specifies how many times to backtrack if dependency " + \
				"calculation fails ",

			"action" : "store"
		},

		"--binpkg-changed-deps": {
			"help"    : ("reject binary packages with outdated "
				"dependencies"),
			"choices" : true_y_or_n
		},

		"--buildpkg": {
			"shortopt" : "-b",
			"help"     : "build binary packages",
			"choices"  : true_y_or_n
		},

		"--buildpkg-exclude": {
			"help"   :"A space separated list of package atoms for which " + \
				"no binary packages should be built. This option overrides all " + \
				"possible ways to enable building of binary packages.",

			"action" : "append"
		},

		"--changed-deps": {
			"help"    : ("replace installed packages with "
				"outdated dependencies"),
			"choices" : true_y_or_n
		},

		"--changed-deps-report": {
			"help"    : ("report installed packages with "
				"outdated dependencies"),
			"choices" : true_y_or_n
		},

		"--changed-slot": {
			"help"    : ("replace installed packages with "
				"outdated SLOT metadata"),
			"choices" : true_y_or_n
		},

		"--config-root": {
			"help":"specify the location for portage configuration files",
			"action":"store"
		},
		"--color": {
			"help":"enable or disable color output",
			"choices":("y", "n")
		},

		"--complete-graph": {
			"help"    : "completely account for all known dependencies",
			"choices" : true_y_or_n
		},

		"--complete-graph-if-new-use": {
			"help"    : "trigger --complete-graph behavior if USE or IUSE will change for an installed package",
			"choices" : y_or_n
		},

		"--complete-graph-if-new-ver": {
			"help"    : "trigger --complete-graph behavior if an installed package version will change (upgrade or downgrade)",
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
			"choices" : true_y_or_n
		},

		"--deselect": {
			"shortopt" : "-W",
			"help"    : "remove atoms/sets from the world file",
			"choices" : true_y_or_n
		},

		"--dynamic-deps": {
			"help": "substitute the dependencies of installed packages with the dependencies of unbuilt ebuilds",
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
			"choices" : true_y_or_n
		},

		"--fuzzy-search": {
			"help": "Enable or disable fuzzy search",
			"choices": true_y_or_n
		},

		"--ignore-built-slot-operator-deps": {
			"help": "Ignore the slot/sub-slot := operator parts of dependencies that have "
				"been recorded when packages where built. This option is intended "
				"only for debugging purposes, and it only affects built packages "
				"that specify slot/sub-slot := operator dependencies using the "
				"experimental \"4-slot-abi\" EAPI.",
			"choices": y_or_n
		},

		"--ignore-soname-deps": {
			"help": "Ignore the soname dependencies of binary and "
				"installed packages. This option is enabled by "
				"default, since soname dependencies are relatively "
				"new, and the required metadata is not guaranteed to "
				"exist for binary and installed packages built with "
				"older versions of portage.",
			"choices": y_or_n
		},

		"--ignore-world": {
			"help"    : "ignore the @world package set and its dependencies",
			"choices" : true_y_or_n
		},

		"--implicit-system-deps": {
			"help": "Assume that packages may have implicit dependencies on"
				"packages which belong to the @system set",
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
			"choices" : true_y_or_n
		},

		"--load-average": {
			"shortopt" : "-l",

			"help"   :"Specifies that no new builds should be started " + \
				"if there are other builds running and the load average " + \
				"is at least LOAD (a floating-point number).",

			"action" : "store"
		},

		"--misspell-suggestions": {
			"help"    : "enable package name misspell suggestions",
			"choices" : ("y", "n")
		},

		"--with-bdeps": {
			"help":"include unnecessary build time dependencies",
			"choices":("y", "n")
		},
		"--with-bdeps-auto": {
			"help":("automatically enable --with-bdeps for installation"
				" actions, unless --usepkg is enabled"),
			"choices":("y", "n")
		},
		"--reinstall": {
			"help":"specify conditions to trigger package reinstallation",
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
			"choices" : true_y_or_n
		},

		"--getbinpkg": {
			"shortopt" : "-g",
			"help"     : "fetch binary packages",
			"choices"  : true_y_or_n
		},

		"--getbinpkgonly": {
			"shortopt" : "-G",
			"help"     : "fetch binary packages only",
			"choices"  : true_y_or_n
		},

		"--usepkg-exclude": {
			"help"   :"A space separated list of package names or slot atoms. " + \
				"Emerge will ignore matching binary packages. ",

			"action" : "append",
		},

		"--onlydeps-with-rdeps": {
			"help"    : "modify interpretation of depedencies",
			"choices" : true_y_or_n
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
			"choices"  : true_y_or_n
		},

		"--prefix": {
			"help"     : "specify the installation prefix",
			"action"   : "store"
		},

		"--pkg-format": {
			"help"     : "format of result binary package",
			"action"   : "store",
		},

		"--quickpkg-direct": {
			"help": "Enable use of installed packages directly as binary packages",
			"choices": y_or_n
		},

		"--quickpkg-direct-root": {
			"help": "Specify the root to use as the --quickpkg-direct package source",
			"action" : "store"
		},

		"--quiet": {
			"shortopt" : "-q",
			"help"     : "reduced or condensed output",
			"choices"  : true_y_or_n
		},

		"--quiet-build": {
			"help"     : "redirect build output to logs",
			"choices"  : true_y_or_n,
		},

		"--quiet-fail": {
			"help"     : "suppresses display of the build log on stdout",
			"choices"  : true_y_or_n,
		},

		"--read-news": {
			"help"    : "offer to read unread news via eselect",
			"choices" : true_y_or_n
		},


		"--rebuild-if-new-slot": {
			"help"     : ("Automatically rebuild or reinstall packages when slot/sub-slot := "
				"operator dependencies can be satisfied by a newer slot, so that "
				"older packages slots will become eligible for removal by the "
				"--depclean action as soon as possible."),
			"choices"  : true_y_or_n
		},

		"--rebuild-if-new-rev": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built, " + \
				"if the dependency is not already installed with the " + \
				"same version and revision.",
			"choices"  : true_y_or_n
		},

		"--rebuild-if-new-ver": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built, " + \
				"if the dependency is not already installed with the " + \
				"same version. Revision numbers are ignored.",
			"choices"  : true_y_or_n
		},

		"--rebuild-if-unbuilt": {
			"help"     : "Rebuild packages when dependencies that are " + \
				"used at both build-time and run-time are built.",
			"choices"  : true_y_or_n
		},

		"--rebuilt-binaries": {
			"help"     : "replace installed packages with binary " + \
			             "packages that have been rebuilt",
			"choices"  : true_y_or_n
		},

		"--rebuilt-binaries-timestamp": {
			"help"   : "use only binaries that are newer than this " + \
			           "timestamp for --rebuilt-binaries",
			"action" : "store"
		},

		"--regex-search-auto": {
			"help"   : "Enable or disable automatic regular expression detection for search actions",
			"choices": y_or_n,
			"default": "y",
		},

		"--root": {
		 "help"   : "specify the target root filesystem for merging packages",
		 "action" : "store"
		},

		"--root-deps": {
			"help"    : "modify interpretation of depedencies",
			"choices" :("True", "rdeps")
		},

		"--search-index": {
			"help": "Enable or disable indexed search (enabled by default)",
			"choices": y_or_n
		},

		"--search-similarity": {
			"help": ("Set minimum similarity percentage for fuzzy seach "
				"(a floating-point number between 0 and 100)"),
			"action": "store"
		},

		"--select": {
			"shortopt" : "-w",
			"help"    : "add specified packages to the world set " + \
			            "(inverse of --oneshot)",
			"choices" : true_y_or_n
		},

		"--selective": {
			"help"    : "identical to --noreplace",
			"choices" : true_y_or_n
		},

		"--sync-submodule": {
			"help"    : ("Restrict sync to the specified submodule(s)."
				" (--sync action only)"),
			"choices" : tuple(_SUBMODULE_PATH_MAP),
			"action" : "append",
		},

		"--sysroot": {
			"help":"specify the location for build dependencies specified in DEPEND",
			"action":"store"
		},

		"--use-ebuild-visibility": {
			"help"     : "use unbuilt ebuild metadata for visibility checks on built packages",
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
			"choices"  : true_y_or_n
		},

		"--usepkgonly": {
			"shortopt" : "-K",
			"help"     : "use only binary packages",
			"choices"  : true_y_or_n
		},

		"--verbose": {
			"shortopt" : "-v",
			"help"     : "verbose output",
			"choices"  : true_y_or_n
		},
		"--verbose-slot-rebuilds": {
			"help"     : "verbose slot rebuild output",
			"choices"  : true_y_or_n
		},
		"--with-test-deps": {
			"help"     : "pull in test deps for packages " + \
				"matched by arguments",
			"choices"  : true_y_or_n
		},
	}

	parser = argparse.ArgumentParser(add_help=False)

	for action_opt in actions:
		parser.add_argument("--" + action_opt, action="store_true",
			dest=action_opt.replace("-", "_"), default=False)
	for myopt in options:
		parser.add_argument(myopt, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)
	for shortopt, longopt in shortmapping.items():
		parser.add_argument("-" + shortopt, action="store_true",
			dest=longopt.lstrip("--").replace("-", "_"), default=False)
	for myalias, myopt in longopt_aliases.items():
		parser.add_argument(myalias, action="store_true",
			dest=myopt.lstrip("--").replace("-", "_"), default=False)

	for myopt, kwargs in argument_options.items():
		shortopt = kwargs.pop("shortopt", None)
		args = [myopt]
		if shortopt is not None:
			args.append(shortopt)
		parser.add_argument(dest=myopt.lstrip("--").replace("-", "_"),
			*args, **kwargs)

	parser.add_argument('positional_args', nargs='*')

	tmpcmdline = insert_optional_args(tmpcmdline)

	myoptions = getattr(parser, "parse_intermixed_args", parser.parse_args)(args=tmpcmdline)

	if myoptions.alert in true_y:
		myoptions.alert = True
	else:
		myoptions.alert = None

	if myoptions.ask in true_y:
		myoptions.ask = True
	else:
		myoptions.ask = None

	if myoptions.autounmask in true_y:
		myoptions.autounmask = True

	if myoptions.autounmask_continue in true_y:
		myoptions.autounmask_continue = True

	if myoptions.autounmask_only in true_y:
		myoptions.autounmask_only = True
	else:
		myoptions.autounmask_only = None

	if myoptions.autounmask_unrestricted_atoms in true_y:
		myoptions.autounmask_unrestricted_atoms = True

	if myoptions.autounmask_keep_keywords in true_y:
		myoptions.autounmask_keep_keywords = True

	if myoptions.autounmask_keep_masks in true_y:
		myoptions.autounmask_keep_masks = True

	if myoptions.autounmask_write in true_y:
		myoptions.autounmask_write = True

	if myoptions.binpkg_changed_deps is not None:
		if myoptions.binpkg_changed_deps in true_y:
			myoptions.binpkg_changed_deps = 'y'
		else:
			myoptions.binpkg_changed_deps = 'n'

	if myoptions.buildpkg in true_y:
		myoptions.buildpkg = True

	if myoptions.buildpkg_exclude:
		bad_atoms = _find_bad_atoms(myoptions.buildpkg_exclude, less_strict=True)
		if bad_atoms and not silent:
			parser.error("Invalid Atom(s) in --buildpkg-exclude parameter: '%s'\n" % \
				(",".join(bad_atoms),))

	if myoptions.changed_deps is not None:
		if myoptions.changed_deps in true_y:
			myoptions.changed_deps = 'y'
		else:
			myoptions.changed_deps = 'n'

	if myoptions.changed_deps_report is not None:
		if myoptions.changed_deps_report in true_y:
			myoptions.changed_deps_report = 'y'
		else:
			myoptions.changed_deps_report = 'n'

	if myoptions.changed_slot is not None:
		if myoptions.changed_slot in true_y:
			myoptions.changed_slot = True
		else:
			myoptions.changed_slot = None

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

	if myoptions.fuzzy_search in true_y:
		myoptions.fuzzy_search = True

	if myoptions.getbinpkg in true_y:
		myoptions.getbinpkg = True
	else:
		myoptions.getbinpkg = None

	if myoptions.getbinpkgonly in true_y:
		myoptions.getbinpkgonly = True
	else:
		myoptions.getbinpkgonly = None

	if myoptions.ignore_world in true_y:
		myoptions.ignore_world = True

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

	if myoptions.quiet_fail in true_y:
		myoptions.quiet_fail = 'y'

	if myoptions.read_news in true_y:
		myoptions.read_news = True
	else:
		myoptions.read_news = None


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

	if myoptions.jobs is not None:
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

	if myoptions.search_similarity:
		try:
			search_similarity = float(myoptions.search_similarity)
		except ValueError:
			parser.error("Invalid --search-similarity parameter "
				"(not a number): '{}'\n".format(
				myoptions.search_similarity))

		if search_similarity < 0 or search_similarity > 100:
			parser.error("Invalid --search-similarity parameter "
				"(not between 0 and 100): '{}'\n".format(
				myoptions.search_similarity))

		myoptions.search_similarity = search_similarity

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

	if myoptions.verbose in true_y:
		myoptions.verbose = True
	else:
		myoptions.verbose = None

	if myoptions.with_test_deps in true_y:
		myoptions.with_test_deps = True
	else:
		myoptions.with_test_deps = None

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

	return myaction, myopts, myoptions.positional_args

def profile_check(trees, myaction):
	if myaction in ("help", "info", "search", "sync", "version"):
		return os.EX_OK
	for root_trees in trees.values():
		if (root_trees["root_config"].settings.profiles and
			'ARCH' in root_trees["root_config"].settings):
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

	args = portage._decode_argv(args)

	# Use system locale.
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error as e:
		writemsg_level("setlocale: %s\n" % e, level=logging.WARN)

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
	if "--sysroot" in myopts:
		os.environ["SYSROOT"] = myopts["--sysroot"]
	if "--root" in myopts:
		os.environ["ROOT"] = myopts["--root"]
	if "--prefix" in myopts:
		os.environ["EPREFIX"] = myopts["--prefix"]
	if "--accept-properties" in myopts:
		os.environ["ACCEPT_PROPERTIES"] = myopts["--accept-properties"]
	if "--accept-restrict" in myopts:
		os.environ["ACCEPT_RESTRICT"] = myopts["--accept-restrict"]

	# optimize --help (no need to load config / EMERGE_DEFAULT_OPTS)
	if myaction == "help":
		emerge_help()
		return os.EX_OK
	if myaction == "moo":
		print(COWSAY_MOO % platform.system())
		return os.EX_OK
	if myaction == "sync":
		# need to set this to True now in order for the repository config
		# loading to allow new repos with non-existent directories
		portage._sync_mode = True

	# Verify that /dev/null exists and is a device file as a cheap early
	# filter for obviously broken /dev/s.
	try:
		if os.stat(os.devnull).st_rdev == 0:
			writemsg_level("Failed to validate a sane '/dev'.\n"
				  "'/dev/null' is not a device file.\n",
				  level=logging.ERROR, noiselevel=-1)
			return 1
	except OSError:
		writemsg_level("Failed to validate a sane '/dev'.\n"
				 "'/dev/null' does not exist.\n",
				 level=logging.ERROR, noiselevel=-1)
		return 1

	# Verify that BASH process substitution works as another cheap early
	# filter. Process substitution uses '/dev/fd'.
	with open(os.devnull, 'r+b') as dev_null:
		fd_pipes = {
			0: dev_null.fileno(),
			1: dev_null.fileno(),
			2: dev_null.fileno(),
		}
		if portage.process.spawn_bash("[[ $(< <(echo foo) ) == foo ]]",
			fd_pipes=fd_pipes) != 0:
			writemsg_level("Failed to validate a sane '/dev'.\n"
				"bash process substitution doesn't work; this may be an "
				"indication of a broken '/dev/fd'.\n",
				level=logging.ERROR, noiselevel=-1)
			return 1

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)
	emerge_config = load_emerge_config(
		action=myaction, args=myfiles, opts=myopts)

	# Make locale variables from configuration files (make.defaults, make.conf) affect locale of emerge process.
	for locale_var_name in ("LANGUAGE", "LC_ALL", "LC_ADDRESS", "LC_COLLATE", "LC_CTYPE",
		"LC_IDENTIFICATION", "LC_MEASUREMENT", "LC_MESSAGES", "LC_MONETARY",
		"LC_NAME", "LC_NUMERIC", "LC_PAPER", "LC_TELEPHONE", "LC_TIME", "LANG"):
		locale_var_value = emerge_config.running_config.settings.get(locale_var_name)
		if locale_var_value is not None:
			os.environ.setdefault(locale_var_name, locale_var_value)
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error as e:
		writemsg_level("setlocale: %s\n" % e, level=logging.WARN)

	tmpcmdline = []
	if "--ignore-default-opts" not in myopts:
		tmpcmdline.extend(portage.util.shlex_split(
			emerge_config.target_config.settings.get(
			"EMERGE_DEFAULT_OPTS", "")))
	tmpcmdline.extend(args)
	emerge_config.action, emerge_config.opts, emerge_config.args = \
		parse_opts(tmpcmdline)

	try:
		return run_action(emerge_config)
	finally:
		# Call destructors for our portdbapi instances.
		for x in emerge_config.trees.values():
			if "porttree" in x.lazy_items:
				continue
			x["porttree"].dbapi.close_caches()
