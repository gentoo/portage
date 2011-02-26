# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

from portage.const import _ENABLE_DYN_LINK_MAP
from portage.output import bold, turquoise, green

def shorthelp():
	print(bold("emerge:")+" the other white meat (command-line interface to the Portage system)")
	print(bold("Usage:"))
	print("   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] [ "+turquoise("ebuild")+" | "+turquoise("tbz2")+" | "+turquoise("file")+" | "+turquoise("@set")+" | "+turquoise("atom")+" ] [ ... ]")
	print("   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] < "+turquoise("system")+" | "+turquoise("world")+" >")
	print("   "+turquoise("emerge")+" < "+turquoise("--sync")+" | "+turquoise("--metadata")+" | "+turquoise("--info")+" >")
	print("   "+turquoise("emerge")+" "+turquoise("--resume")+" [ "+green("--pretend")+" | "+green("--ask")+" | "+green("--skipfirst")+" ]")
	print("   "+turquoise("emerge")+" "+turquoise("--help")+" [ "+green("--verbose")+" ] ")
	print(bold("Options:")+" "+green("-")+"["+green("abBcCdDefgGhjkKlnNoOpPqrsStuvV")+"]")
	print("          [ " + green("--color")+" < " + turquoise("y") + " | "+ turquoise("n")+" >            ] [ "+green("--columns")+"    ]")
	print("          [ "+green("--complete-graph")+"             ] [ "+green("--deep")+"       ]")
	print("          [ "+green("--jobs") + " " + turquoise("JOBS")+" ] [ "+green("--keep-going")+" ] [ " + green("--load-average")+" " + turquoise("LOAD") + "            ]")
	print("          [ "+green("--newuse")+"    ] [ "+green("--noconfmem")+"  ] [ "+green("--nospinner")+"  ]")
	print("          [ "+green("--oneshot")+"   ] [ "+green("--onlydeps")+"   ]")
	print("          [ "+green("--reinstall ")+turquoise("changed-use")+"      ] [ " + green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >         ]")
	print(bold("Actions:")+"  [ "+green("--depclean")+" | "+green("--list-sets")+" | "+green("--search")+" | "+green("--sync")+" | "+green("--version")+"        ]")

def help(myopts, havecolor=1):
	# TODO: Implement a wrap() that accounts for console color escape codes.
	from textwrap import wrap
	desc_left_margin = 14
	desc_indent = desc_left_margin * " "
	desc_width = 80 - desc_left_margin - 5
	if "--verbose" not in myopts:
		shorthelp()
		print()
		print("   For more help try 'emerge --help --verbose' or consult the man page.")
	else:
		shorthelp()
		print()
		print(turquoise("Help (this screen):"))
		print("       "+green("--help")+" ("+green("-h")+" short option)")
		print("              Displays this help; an additional argument (see above) will tell")
		print("              emerge to display detailed help.")
		print()
		print(turquoise("Actions:"))
		print("       "+green("--clean"))
		print("              Cleans the system by removing outdated packages which will not")
		print("              remove functionalities or prevent your system from working.")
		print("              The arguments can be in several different formats :")
		print("              * world ")
		print("              * system or")
		print("              * 'dependency specification' (in single quotes is best.)")
		print("              Here are a few examples of the dependency specification format:")
		print("              "+bold("binutils")+" matches")
		print("                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1")
		print("              "+bold("sys-devel/binutils")+" matches")
		print("                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1")
		print("              "+bold(">sys-devel/binutils-2.11.90.0.7")+" matches")
		print("                  binutils-2.11.92.0.12.3-r1")
		print("              "+bold(">=sys-devel/binutils-2.11.90.0.7")+" matches")
		print("                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1")
		print("              "+bold("<=sys-devel/binutils-2.11.92.0.12.3-r1")+" matches")
		print("                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1")
		print()
		print("       "+green("--config"))
		print("              Runs package-specific operations that must be executed after an")
		print("              emerge process has completed.  This usually entails configuration")
		print("              file setup or other similar setups that the user may wish to run.")
		print()
		print("       "+green("--depclean")+" ("+green("-c")+" short option)")

		paragraph = "Cleans the system by removing packages that are " + \
		"not associated with explicitly merged packages. Depclean works " + \
		"by creating the full dependency tree from the " + \
		"@world set, then comparing it to installed packages. Packages " + \
		"installed, but not part of the dependency tree, will be " + \
		"uninstalled by depclean. See --with-bdeps for behavior with " + \
		"respect to build time dependencies that are not strictly " + \
		"required. Packages that are part of the world set will " + \
		"always be kept. They can be manually added to this set with " + \
		"emerge --noreplace <atom>. As a safety measure, depclean " + \
		"will not remove any packages unless *all* required dependencies " + \
		"have been resolved. As a consequence, it is often necessary to " + \
		"run emerge --update --newuse --deep @world " + \
		"prior to depclean."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()

		paragraph =  "WARNING: Inexperienced users are advised to use " + \
		"--pretend with this option in order to see a preview of which " + \
		"packages will be uninstalled. Always study the list of packages " + \
		"to be cleaned for any obvious mistakes. Note that packages " + \
		"listed in package.provided (see portage(5)) may be removed by " + \
		"depclean, even if they are part of the world set."

		paragraph += " Also note that " + \
			"depclean may break link level dependencies"

		if _ENABLE_DYN_LINK_MAP:
			paragraph += ", especially when the " + \
				"--depclean-lib-check option is disabled"

		paragraph += ". Thus, it is " + \
			"recommended to use a tool such as revdep-rebuild(1) " + \
			"in order to detect such breakage."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()

		paragraph = "Depclean serves as a dependency aware version of " + \
			"--unmerge. When given one or more atoms, it will unmerge " + \
			"matched packages that have no reverse dependencies. Use " + \
			"--depclean together with --verbose to show reverse dependencies."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--deselect") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))

		paragraph = \
			"Remove atoms and/or sets from the world file. This action is implied " + \
			"by uninstall actions, including --depclean, " + \
			"--prune and --unmerge. Use --deselect=n " + \
			"in order to prevent uninstall actions from removing " + \
			"atoms from the world file."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--ignore-default-opts"))

		paragraph = \
			"Causes EMERGE_DEFAULT_OPTS (see make.conf(5)) to be ignored."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--info"))
		print("              Displays important portage variables that will be exported to")
		print("              ebuild.sh when performing merges. This information is useful")
		print("              for bug reports and verification of settings. All settings in")
		print("              make.{conf,globals,defaults} and the environment show up if")
		print("              run with the '--verbose' flag.")
		print()
		print("       " + green("--list-sets"))
		paragraph = "Displays a list of available package sets."

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--metadata"))
		print("              Transfers metadata cache from ${PORTDIR}/metadata/cache/ to")
		print("              /var/cache/edb/dep/ as is normally done on the tail end of an")
		print("              rsync update using " + bold("emerge --sync") + ". This process populates the")
		print("              cache database that portage uses for pre-parsed lookups of")
		print("              package data.  It does not populate cache for the overlays")
		print("              listed in PORTDIR_OVERLAY.  In order to generate cache for")
		print("              overlays, use " + bold("--regen") + ".")
		print()
		print("       "+green("--prune")+" ("+green("-P")+" short option)")
		print("              "+turquoise("WARNING: This action can remove important packages!"))
		paragraph = "Removes all but the highest installed version of a " + \
			"package from your system. Use --prune together with " + \
			"--verbose to show reverse dependencies or with --nodeps " + \
			"to ignore all dependencies. "

		for line in wrap(paragraph, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--regen"))
		print("              Causes portage to check and update the dependency cache of all")
		print("              ebuilds in the portage tree. This is not recommended for rsync")
		print("              users as rsync updates the cache using server-side caches.")
		print("              Rsync users should simply 'emerge --sync' to regenerate.")
		desc = "In order to specify parallel --regen behavior, use "+ \
			"the ---jobs and --load-average options. If you would like to " + \
			"generate and distribute cache for use by others, use egencache(1)."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--resume")+" ("+green("-r")+" short option)")
		print("              Resumes the most recent merge list that has been aborted due to an")
		print("              error. Please note that this operation will only return an error")
		print("              on failure. If there is nothing for portage to do, then portage")
		print("              will exit with a message and a success condition. A resume list")
		print("              will persist until it has been completed in entirety or until")
		print("              another aborted merge list replaces it. The resume history is")
		print("              capable of storing two merge lists. After one resume list")
		print("              completes, it is possible to invoke --resume once again in order")
		print("              to resume an older list.")
		print()
		print("       "+green("--search")+" ("+green("-s")+" short option)")
		print("              Searches for matches of the supplied string in the current local")
		print("              portage tree. By default emerge uses a case-insensitive simple ")
		print("              search, but you can enable a regular expression search by ")
		print("              prefixing the search string with %.")
		print("              Prepending the expression with a '@' will cause the category to")
		print("              be included in the search.")
		print("              A few examples:")
		print("              "+bold("emerge --search libc"))
		print("                  list all packages that contain libc in their name")
		print("              "+bold("emerge --search '%^kde'"))
		print("                  list all packages starting with kde")
		print("              "+bold("emerge --search '%gcc$'"))
		print("                  list all packages ending with gcc")
		print("              "+bold("emerge --search '%@^dev-java.*jdk'"))
		print("                  list all available Java JDKs")
		print()
		print("       "+green("--searchdesc")+" ("+green("-S")+" short option)")
		print("              Matches the search string against the description field as well")
		print("              the package's name. Take caution as the descriptions are also")
		print("              matched as regular expressions.")
		print("                emerge -S html")
		print("                emerge -S applet")
		print("                emerge -S 'perl.*module'")
		print()
		print("       "+green("--sync"))
		desc = "This updates the portage tree that is located in the " + \
			"directory that the PORTDIR variable refers to (default " + \
			"location is /usr/portage). The SYNC variable specifies " + \
			"the remote URI from which files will be synchronized. " + \
			"The PORTAGE_SYNC_STALE variable configures " + \
			"warnings that are shown when emerge --sync has not " + \
			"been executed recently."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print(desc_indent + turquoise("WARNING:"))
		desc = "The emerge --sync action will modify and/or delete " + \
			"files located inside the directory that the PORTDIR " + \
			"variable refers to (default location is /usr/portage). " + \
			"For more information, see the PORTDIR documentation in " + \
			"the make.conf(5) man page."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print(desc_indent + green("NOTE:"))
		desc = "The emerge-webrsync program will download the entire " + \
			"portage tree as a tarball, which is much faster than emerge " + \
			"--sync for first time syncs."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--unmerge")+" ("+green("-C")+" short option)")
		print("              "+turquoise("WARNING: This action can remove important packages!"))
		print("              Removes all matching packages. This does no checking of")
		print("              dependencies, so it may remove packages necessary for the proper")
		print("              operation of your system. Its arguments can be atoms or")
		print("              ebuilds. For a dependency aware version of --unmerge, use")
		print("              --depclean or --prune.")
		print()
		print("       "+green("--version")+" ("+green("-V")+" short option)")
		print("              Displays the currently installed version of portage along with")
		print("              other information useful for quick reference on a system. See")
		print("              "+bold("emerge info")+" for more advanced information.")
		print()
		print(turquoise("Options:"))
		print("       "+green("--accept-properties=ACCEPT_PROPERTIES"))
		desc = "This option temporarily overrides the ACCEPT_PROPERTIES " + \
			"variable. The ACCEPT_PROPERTIES variable is incremental, " + \
			"which means that the specified setting is appended to the " + \
			"existing value from your configuration. The special -* " + \
			"token can be used to discard the existing configuration " + \
			"value and start fresh. See the MASKED PACKAGES section " + \
			"and make.conf(5) for more information about " + \
			"ACCEPT_PROPERTIES. A typical usage example for this option " + \
			"would be to use --accept-properties=-interactive to " + \
			"temporarily mask interactive packages. With default " + \
			"configuration, this would result in an effective " + \
			"ACCEPT_PROPERTIES value of \"* -interactive\"."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--alphabetical"))
		print("              When displaying USE and other flag output, combines the enabled")
		print("              and disabled flags into a single list and sorts it alphabetically.")
		print("              With this option, output such as USE=\"dar -bar -foo\" will instead")
		print("              be displayed as USE=\"-bar dar -foo\"")
		print()
		print("       "+green("--ask")+" ("+green("-a")+" short option)")
		desc = "Before performing the action, display what will take place (server info for " + \
			"--sync, --pretend output for merge, and so forth), then ask " + \
			"whether to proceed with the action or abort.  Using --ask is more " + \
			"efficient than using --pretend and then executing the same command " + \
			"without --pretend, as dependencies will only need to be calculated once. " + \
			"WARNING: If the \"Enter\" key is pressed at the prompt (with no other input), " + \
			"it is interpreted as acceptance of the first choice.  Note that the input " + \
			"buffer is not cleared prior to the prompt, so an accidental press of the " + \
			"\"Enter\" key at any time prior to the prompt will be interpreted as a choice! " + \
			"Use the --ask-enter-invalid option if you want a single \"Enter\" key " + \
			"press to be interpreted as invalid input."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("        " + green("--ask-enter-invalid"))
		desc = "When used together with the --ask option, " + \
			"interpret a single \"Enter\" key press as " + \
			"invalid input. This helps prevent accidental " + \
			"acceptance of the first choice. This option is " + \
			"intended to be set in the make.conf(5) " + \
			"EMERGE_DEFAULT_OPTS variable."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print() 
		print("       " + green("--autounmask") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Automatically unmask packages. If any configuration " + \
			"changes are required, then they will be displayed " + \
			"after the merge list and emerge will immediately " + \
			"abort. If the displayed configuration changes are " + \
			"satisfactory, you should copy and paste them into " + \
			"the specified configuration file(s). Currently, " + \
			"this only works for unstable KEYWORDS masks, " + \
			"LICENSE masks, and package.use settings."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--backtrack") + " " + turquoise("COUNT"))
		desc = "Specifies an integer number of times to backtrack if " + \
			"dependency calculation fails due to a conflict or an " + \
			"unsatisfied dependency (default: '10')."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("        " + green("--binpkg-respect-use") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Tells emerge to ignore binary packages if their use flags" + \
			" don't match the current configuration. (default: 'n')"
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--buildpkg") + \
			" [ %s | %s ] (%s short option)" % \
			(turquoise("y"), turquoise("n"), green("-b")))
		desc = "Tells emerge to build binary packages for all ebuilds processed in" + \
			" addition to actually merging the packages. Useful for maintainers" + \
			" or if you administrate multiple Gentoo Linux systems (build once," + \
			" emerge tbz2s everywhere) as well as disaster recovery. The package" + \
			" will be created in the" + \
			" ${PKGDIR}/All directory. An alternative for already-merged" + \
			" packages is to use quickpkg(1) which creates a tbz2 from the" + \
			" live filesystem."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--buildpkgonly")+" ("+green("-B")+" short option)")
		print("              Creates a binary package, but does not merge it to the")
		print("              system. This has the restriction that unsatisfied dependencies")
		print("              must not exist for the desired package as they cannot be used if")
		print("              they do not exist on the system.")
		print()
		print("       " + green("--changed-use"))
		desc = "This is an alias for --reinstall=changed-use."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--changelog")+" ("+green("-l")+" short option)")
		print("              When pretending, also display the ChangeLog entries for packages")
		print("              that will be upgraded.")
		print()
		print("       "+green("--color") + " < " + turquoise("y") + " | "+ turquoise("n")+" >")
		print("              Enable or disable color output. This option will override NOCOLOR")
		print("              (see make.conf(5)) and may also be used to force color output when")
		print("              stdout is not a tty (by default, color is disabled unless stdout")
		print("              is a tty).")
		print()
		print("       "+green("--columns"))
		print("              Display the pretend output in a tabular form. Versions are")
		print("              aligned vertically.")
		print()
		print("       "+green("--complete-graph") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "This causes emerge to consider the deep dependencies of all" + \
			" packages from the world set. With this option enabled," + \
			" emerge will bail out if it determines that the given operation will" + \
			" break any dependencies of the packages that have been added to the" + \
			" graph. Like the --deep option, the --complete-graph" + \
			" option will significantly increase the time taken for dependency" + \
			" calculations. Note that, unlike the --deep option, the" + \
			" --complete-graph option does not cause any more packages to" + \
			" be updated than would have otherwise been updated with the option disabled."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--config-root=DIR"))
		desc = "Set the PORTAGE_CONFIGROOT environment variable " + \
			"which is documented in the emerge(1) man page."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--debug")+" ("+green("-d")+" short option)")
		print("              Tell emerge to run the ebuild command in --debug mode. In this")
		print("              mode, the bash build environment will run with the -x option,")
		print("              causing it to output verbose debug information print to stdout.")
		print("              --debug is great for finding bash syntax errors as providing")
		print("              very verbose information about the dependency and build process.")
		print()
		print("       "+green("--deep") + " " + turquoise("[DEPTH]") + \
			" (" + green("-D") + " short option)")
		print("              This flag forces emerge to consider the entire dependency tree of")
		print("              packages, instead of checking only the immediate dependencies of")
		print("              the packages. As an example, this catches updates in libraries")
		print("              that are not directly listed in the dependencies of a package.")
		print("              Also see --with-bdeps for behavior with respect to build time")
		print("              dependencies that are not strictly required.")
		print()

		if _ENABLE_DYN_LINK_MAP:
			print("       " + green("--depclean-lib-check") + " [ %s | %s ]" % \
				(turquoise("y"), turquoise("n")))
			desc = "Account for library link-level dependencies during " + \
				"--depclean and --prune actions. This " + \
				"option is enabled by default. In some cases this can " + \
				"be somewhat time-consuming."
			for line in wrap(desc, desc_width):
				print(desc_indent + line)
			print()

		print("       "+green("--emptytree")+" ("+green("-e")+" short option)")
		desc = "Reinstalls target atoms and their entire deep " + \
			"dependency tree, as though no packages are currently " + \
			"installed. You should run this with --pretend " + \
			"first to make sure the result is what you expect."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--exclude") + " " + turquoise("ATOMS"))
		desc = "A space separated list of package names or slot atoms. " + \
			"Emerge won't  install any ebuild or binary package that " + \
			"matches any of the given package atoms."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--fail-clean") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Clean up temporary files after a build failure. This is " + \
			"particularly useful if you have PORTAGE_TMPDIR on " + \
			"tmpfs. If this option is enabled, you probably also want " + \
			"to enable PORT_LOGDIR (see make.conf(5)) in " + \
			"order to save the build log."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--fetchonly")+" ("+green("-f")+" short option)")
		print("              Instead of doing any package building, just perform fetches for")
		print("              all packages (main package as well as all dependencies.) When")
		print("              used in combination with --pretend all the SRC_URIs will be")
		print("              displayed multiple mirrors per line, one line per file.")
		print()
		print("       "+green("--fetch-all-uri")+" ("+green("-F")+" short option)")
		print("              Same as --fetchonly except that all package files, including those")
		print("              not required to build the package, will be processed.")
		print()
		print("       " + green("--getbinpkg") + \
			" [ %s | %s ] (%s short option)" % \
			(turquoise("y"), turquoise("n"), green("-g")))
		print("              Using the server and location defined in PORTAGE_BINHOST, portage")
		print("              will download the information from each binary file there and it")
		print("              will use that information to help build the dependency list. This")
		print("              option implies '-k'. (Use -gK for binary-only merging.)")
		print()
		print("       " + green("--getbinpkgonly") + \
			" [ %s | %s ] (%s short option)" % \
			(turquoise("y"), turquoise("n"), green("-G")))
		print("              This option is identical to -g, as above, except it will not use")
		print("              ANY information from the local machine. All binaries will be")
		print("              downloaded from the remote server without consulting packages")
		print("              existing in the packages directory.")
		print()
		print("       " + green("--jobs") + " " + turquoise("[JOBS]") + " ("+green("-j")+" short option)")
		desc = "Specifies the number of packages " + \
			"to build simultaneously. If this option is " + \
			"given without an argument, emerge will not " + \
			"limit the number of jobs that " + \
			"can run simultaneously. Also see " + \
			"the related --load-average option. " + \
			"Note that interactive packages currently force a setting " + \
			"of --jobs=1. This issue can be temporarily avoided " + \
			"by specifying --accept-properties=-interactive."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--keep-going") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Continue as much as possible after " + \
			"an error. When an error occurs, " + \
			"dependencies are recalculated for " + \
			"remaining packages and any with " + \
			"unsatisfied dependencies are " + \
			"automatically dropped. Also see " + \
			"the related --skipfirst option."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--load-average") + " " + turquoise("LOAD"))
		desc = "Specifies that no new builds should " + \
			"be started if there are other builds " + \
			"running and the load average is at " + \
			"least LOAD (a floating-point number). " + \
			"This option is recommended for use " + \
			"in combination with --jobs in " + \
			"order to avoid excess load. See " + \
			"make(1) for information about " + \
			"analogous options that should be " + \
			"configured via MAKEOPTS in " + \
			"make.conf(5)."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--newuse")+" ("+green("-N")+" short option)")
		desc = "Tells emerge to include installed packages where USE " + \
			"flags have changed since compilation. This option " + \
			"also implies the --selective option. If you would " + \
			"like to skip rebuilds for which disabled flags have " + \
			"been added to or removed from IUSE, see the related " + \
			"--reinstall=changed-use option."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--noconfmem"))
		print("              Portage keeps track of files that have been placed into")
		print("              CONFIG_PROTECT directories, and normally it will not merge the")
		print("              same file more than once, as that would become annoying. This")
		print("              can lead to problems when the user wants the file in the case")
		print("              of accidental deletion. With this option, files will always be")
		print("              merged to the live fs instead of silently dropped.")
		print()
		print("       "+green("--nodeps")+" ("+green("-O")+" short option)")
		print("              Merge specified packages, but don't merge any dependencies.")
		print("              Note that the build may fail if deps aren't satisfied.")
		print() 
		print("       "+green("--noreplace")+" ("+green("-n")+" short option)")
		print("              Skip the packages specified on the command-line that have")
		print("              already been installed.  Without this option, any packages,")
		print("              ebuilds, or deps you specify on the command-line *will* cause")
		print("              Portage to remerge the package, even if it is already installed.")
		print("              Note that Portage won't remerge dependencies by default.")
		desc = "Also note that this option takes " + \
			"precedence over options such as --newuse, preventing a package " + \
			"from being reinstalled even though the corresponding USE flag settings " + \
			"may have changed."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print() 
		print("       "+green("--nospinner"))
		print("              Disables the spinner regardless of terminal type.")
		print()
		print("       "+green("--oneshot")+" ("+green("-1")+" short option)")
		print("              Emerge as normal, but don't add packages to the world profile.")
		print("              This package will only be updated if it is depended upon by")
		print("              another package.")
		print()
		print("       "+green("--onlydeps")+" ("+green("-o")+" short option)")
		print("              Only merge (or pretend to merge) the dependencies of the")
		print("              specified packages, not the packages themselves.")
		print()
		print("       " + green("--package-moves") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Perform package moves when necessary. This option " + \
			"is enabled by default. WARNING: This option " + \
			"should remain enabled under normal circumstances. " + \
			"Do not disable it unless you know what you are " + \
			"doing."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--pretend")+" ("+green("-p")+" short option)")
		print("              Instead of actually performing the merge, simply display what")
		print("              ebuilds and tbz2s *would* have been installed if --pretend")
		print("              weren't used.  Using --pretend is strongly recommended before")
		print("              installing an unfamiliar package.  In the printout, N = new,")
		print("              U = updating, R = replacing, F = fetch  restricted, B = blocked")
		print("              by an already installed package, D = possible downgrading,")
		print("              S = slotted install. --verbose causes affecting use flags to be")
		print("              printed out accompanied by a '+' for enabled and a '-' for")
		print("              disabled USE flags.")
		print()
		print("       "+green("--quiet")+" ("+green("-q")+" short option)")
		print("              Effects vary, but the general outcome is a reduced or condensed")
		print("              output from portage's displays.")
		print()
		print("       "+green("--quiet-build"))
		desc = "Redirect all build output to logs alone, and do not " + \
			"display it on stdout."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--quiet-unmerge-warn"))
		desc = "Disable the warning message that's shown prior to " + \
			"--unmerge actions. This option is intended " + \
			"to be set in the make.conf(5) " + \
			"EMERGE_DEFAULT_OPTS variable."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--rebuilt-binaries") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Replace installed packages with binary packages that have " + \
			"been rebuilt. Rebuilds are detected by comparison of " + \
			"BUILD_TIME package metadata. This option is enabled " + \
			"automatically when using binary packages " + \
			"(--usepkgonly or --getbinpkgonly) together with " + \
			"--update and --deep."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--rebuilt-binaries-timestamp") + "=%s" % turquoise("TIMESTAMP"))
		desc = "This option modifies emerge's behaviour only if " + \
			"--rebuilt-binaries is given. Only binaries that " + \
			"have a BUILD_TIME that is larger than the given TIMESTAMP " + \
			"and that is larger than that of the installed package will " + \
			"be considered by the rebuilt-binaries logic."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--reinstall ") + turquoise("changed-use"))
		print("              Tells emerge to include installed packages where USE flags have")
		print("              changed since installation.  Unlike --newuse, this option does")
		print("              not trigger reinstallation when flags that the user has not")
		print("              enabled are added or removed.")
		print()
		print("       "+green("--root=DIR"))
		desc = "Set the ROOT environment variable " + \
			"which is documented in the emerge(1) man page."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--root-deps[=rdeps]"))
		desc = "If no argument is given then build-time dependencies of packages for " + \
			"ROOT are installed to " + \
			"ROOT instead of /. If the rdeps argument is given then discard " + \
			"all build-time dependencies of packages for ROOT. This option is " + \
			"only meaningful when used together with ROOT and it should not " + \
			"be enabled under normal circumstances. For currently supported " + \
			"EAPI values, the build-time dependencies are specified in the " + \
			"DEPEND variable. However, behavior may change for new " + \
			"EAPIs when related extensions are added in the future."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--select") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Add specified packages to the world set (inverse of " + \
			"--oneshot). This is useful if you want to " + \
			"use EMERGE_DEFAULT_OPTS to make " + \
			"--oneshot behavior default."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--selective") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "This is similar to the --noreplace option, except that it " + \
			"does not take precedence over options such as --newuse. " + \
			"Some options, such as --update, imply --selective. " + \
			"Use --selective=n if you want to forcefully disable " + \
			"--selective, regardless of options like --update."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--skipfirst"))
		desc = "This option is only valid when " + \
			"used with --resume.  It removes the " + \
			"first package in the resume list. " + \
			"Dependencies are recalculated for " + \
			"remaining packages and any that " + \
			"have unsatisfied dependencies or are " + \
			"masked will be automatically dropped. " + \
			"Also see the related " + \
			"--keep-going option."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--tree")+" ("+green("-t")+" short option)")
		print("              Shows the dependency tree using indentation for dependencies.")
		print("              The packages are also listed in reverse merge order so that")
		print("              a package's dependencies follow the package. Only really useful")
		print("              in combination with --emptytree, --update or --deep.")
		print()
		print("       " + green("--unordered-display"))
		desc = "By default the displayed merge list is sorted using the " + \
			"order in which the packages will be merged. When " + \
			"--tree is used together with this option, this " + \
			"constraint is removed, hopefully leading to a more " + \
			"readable dependency tree."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       "+green("--update")+" ("+green("-u")+" short option)")
		desc = "Updates packages to the best version available, which may " + \
			"not always be the  highest version number due to masking " + \
			"for testing and development. Package atoms specified on " + \
			"the command line are greedy, meaning that unspecific " + \
			"atoms may match multiple versions of slotted packages."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--use-ebuild-visibility") + " [ %s | %s ]" % \
			(turquoise("y"), turquoise("n")))
		desc = "Use unbuilt ebuild metadata for visibility " + \
			"checks on built packages."
		for line in wrap(desc, desc_width):
			print(desc_indent + line)
		print()
		print("       " + green("--usepkg") + \
			" [ %s | %s ] (%s short option)" % \
			(turquoise("y"), turquoise("n"), green("-k")))
		print("              Tell emerge to use binary packages (from $PKGDIR) if they are")
		print("              available, thus possibly avoiding some time-consuming compiles.")
		print("              This option is useful for CD installs; you can export")
		print("              PKGDIR=/mnt/cdrom/packages and then use this option to have")
		print("              emerge \"pull\" binary packages from the CD in order to satisfy") 
		print("              dependencies.")
		print()
		print("       " + green("--usepkgonly") + \
			" [ %s | %s ] (%s short option)" % \
			(turquoise("y"), turquoise("n"), green("-K")))
		print("              Like --usepkg above, except this only allows the use of binary")
		print("              packages, and it will abort the emerge if the package is not")
		print("              available at the time of dependency calculation.")
		print()
		print("       "+green("--verbose")+" ("+green("-v")+" short option)")
		print("              Effects vary, but the general outcome is an increased or expanded")
		print("              display of content in portage's displays.")
		print()
		print("       "+green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >")
		print("              In dependency calculations, pull in build time dependencies that")
		print("              are not strictly required. This defaults to 'n' for installation")
		print("              actions and 'y' for the --depclean action. This setting can be")
		print("              added to EMERGE_DEFAULT_OPTS (see make.conf(5)) and later")
		print("              overridden via the command line.")
		print()
