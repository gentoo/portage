# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


import os,sys
from output import bold, turquoise, green

def shorthelp():
	print
	print
	print bold("Usage:")
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] [ "+turquoise("ebuildfile")+" | "+turquoise("tbz2file")+" | "+turquoise("dependency")+" ] [ ... ]"
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] < "+turquoise("system")+" | "+turquoise("world")+" >"
	print "   "+turquoise("emerge")+" < "+turquoise("--sync")+" | "+turquoise("--metadata")+" | "+turquoise("--info")+" >"
	print "   "+turquoise("emerge")+" "+turquoise("--resume")+" [ "+green("--pretend")+" | "+green("--ask")+" | "+green("--skipfirst")+" ]"
	print "   "+turquoise("emerge")+" "+turquoise("--help")+" [ "+green("system")+" | "+green("world")+" | "+green("config")+" | "+green("--sync")+" ] "
	print bold("Options:")+" "+green("-")+"["+green("abBcCdDefgGhikKlnNoOpqPsStuvV")+"] ["+green("--oneshot")+"] ["+green("--newuse")+"] ["+green("--noconfmem")+"]"
	print      "                                          ["+green("--columns")+"] ["+green("--nocolor")+"] ["+green("--nospinner")+"]"
	print "                                          [ "+green("--deep")+"  ] [" + green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" > ]"
	print bold("Actions:")+" [ "+green("--clean")+" | "+green("--depclean")+" | "+green("--prune")+" | "+green("--regen")+" | "+green("--search")+" | "+green("--unmerge")+" ]"
	print

def help(myaction,myopts,havecolor=1):
	if not havecolor:
		nocolor()
	if not myaction and ("--help" not in myopts):
		shorthelp()
		print
		print "   For more help try 'emerge --help' or consult the man page."
		print
	elif not myaction:
		shorthelp()
		print
		print turquoise("Help (this screen):")
		print "       "+green("--help")+" ("+green("-h")+" short option)"
		print "              Displays this help; an additional argument (see above) will tell"
		print "              emerge to display detailed help."
		print
		print turquoise("Actions:")
		print "       "+green("--clean")+" ("+green("-c")+" short option)"
		print "              Cleans the system by removing outdated packages which will not"
		print "              remove functionalities or prevent your system from working."
		print "              The arguments can be in several different formats :"
		print "              * world "
		print "              * system or"
		print "              * 'dependency specification' (in single quotes is best.)"
		print "              Here are a few examples of the dependency specification format:"
		print "              "+bold("binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("sys-devel/binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">=sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("<=sys-devel/binutils-2.11.92.0.12.3-r1")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print
		print "       "+green("--config")
		print "              Runs package-specific operations that must be executed after an"
		print "              emerge process has completed.  This usually entails configuration"
		print "              file setup or other similar setups that the user may wish to run."
		print
		print "       "+green("--depclean")
		print "              Cleans the system by removing packages that are not associated"
		print "              with explicitly merged packages. Depclean works by creating the"
		print "              full dependency tree from the system list and the world file,"
		print "              then comparing it to installed packages. Packages installed, but"
		print "              not associated with an explicit merge are listed as candidates"
		print "              for unmerging."+turquoise(" WARNING: This can seriously affect your system by")
		print "              "+turquoise("removing packages that may have been linked against, but due to")
		print "              "+turquoise("changes in USE flags may no longer be part of the dep tree. Use")
		print "              "+turquoise("caution when employing this feature.")
		print
		print "       "+green("--info")
		print "              Displays important portage variables that will be exported to"
		print "              ebuild.sh when performing merges. This information is useful"
		print "              for bug reports and verification of settings. All settings in"
		print "              make.{conf,globals,defaults} and the environment show up if"
		print "              run with the '--verbose' flag."
		print
		print "       "+green("--metadata")
		print "              Causes portage to process all the metacache files as is normally "
		print "              done on the tail end of an rsync update using "+bold("emerge --sync")+"."
		print "              This processing creates the cache database that portage uses for"
		print "              pre-parsed lookups of package data."
		print
		print "       "+green("--prune")+" ("+green("-P")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all but the most recently installed version of a package"
		print "              from your system. This action doesn't verify the possible binary"
		print "              compatibility between versions and can thus remove essential"
		print "              dependencies from your system."
		print "              The argument format is the same as for the "+bold("--clean")+" action."
		print
		print "       "+green("--regen")
		print "              Causes portage to check and update the dependency cache of all"
		print "              ebuilds in the portage tree. This is not recommended for rsync"
		print "              users as rsync updates the cache using server-side caches."
		print "              Rsync users should simply 'emerge --sync' to regenerate."
		print
		print "       "+green("--resume")
		print "              Resumes the last merge operation. It can be treated just like a"
		print "              regular emerge: --pretend and other options work alongside it."
		print "              'emerge --resume' only returns an error on failure. When there is"
		print "              nothing to do, it exits with a message and a success condition."
		print
		print "       "+green("--search")+" ("+green("-s")+" short option)"
		print "              Searches for matches of the supplied string in the current local"
		print "              portage tree. By default emerge uses a case-insensitive simple "
		print "              search, but you can enable a regular expression search by "
		print "              prefixing the search string with %%."
		print "              Prepending the expression with a '@' will cause the category to"
		print "              be included in the search."
		print "              A few examples:"
		print "              "+bold("emerge --search libc")
		print "                  list all packages that contain libc in their name"
		print "              "+bold("emerge --search '%^kde'")
		print "                  list all packages starting with kde"
		print "              "+bold("emerge --search '%gcc$'")
		print "                  list all packages ending with gcc"
		print "              "+bold("emerge --search '%@^dev-java.*jdk'")
		print "                  list all available Java JDKs"
		print
		print "       "+green("--searchdesc")+" ("+green("-S")+" short option)"
		print "              Matches the search string against the description field as well"
		print "              the package's name. Take caution as the descriptions are also"
		print "              matched as regular expressions."
		print "                emerge -S html"
		print "                emerge -S applet"
		print "                emerge -S 'perl.*module'"
		print
		print "       "+green("--unmerge")+" ("+green("-C")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all matching packages "+bold("completely")+" from"
		print "              your system. Specify arguments using the dependency specification"
		print "              format described in the "+bold("--clean")+" action above."
		print
		print "       "+green("--update")+" ("+green("-u")+" short option)"
		print "              Updates packages to the best version available, which may not"
		print "              always be the highest version number due to masking for testing"
		print "              and development. This will also update direct dependencies which"
		print "              may not what you want. In general use this option only in combi-"
		print "              nation with the world or system target."
		print
		print "       "+green("--version")+" ("+green("-V")+" short option)"
		print "              Displays the currently installed version of portage along with"
		print "              other information useful for quick reference on a system. See"
		print "              "+bold("emerge info")+" for more advanced information."
		print
		print turquoise("Options:")
		print "       "+green("--alphabetical")
		print "              When displaying USE and other flag output, combines the enabled"
		print "              and disabled flags into a single list and sorts it alphabetically."
		print "              With this option, output such as USE=\"dar -bar -foo\" will instead"
		print "              be displayed as USE=\"-bar dar -foo\""
		print
		print "       "+green("--ask")+" ("+green("-a")+" short option)"
		print "              before performing the merge, display what ebuilds and tbz2s will"
		print "              be installed, in the same format as when using --pretend; then"
		print "              ask whether to continue with the merge or abort. Using --ask is"
		print "              more efficient than using --pretend and then executing the same"
		print "              command without --pretend, as dependencies will only need to be"
		print "              calculated once. WARNING: If the \"Enter\" key is pressed at the"
		print "              prompt (with no other input), it is interpreted as acceptance of"
		print "              the first choice.  Note that the input buffer is not cleared prior"
		print "              to the prompt, so an accidental press of the \"Enter\" key at any"
		print "              time prior to the prompt will be interpreted as a choice!"
		print
		print "       "+green("--buildpkg")+" ("+green("-b")+" short option)"
		print "              Tell emerge to build binary packages for all ebuilds processed"
		print "              (in addition to actually merging the packages.  Useful for"
		print "              maintainers or if you administrate multiple Gentoo Linux"
		print "              systems (build once, emerge tbz2s everywhere) as well as disaster"
		print "              recovery."
		print
		print "       "+green("--buildpkgonly")+" ("+green("-B")+" short option)"
		print "              Creates a binary package, but does not merge it to the"
		print "              system. This has the restriction that unsatisfied dependencies"
		print "              must not exist for the desired package as they cannot be used if"
		print "              they do not exist on the system."
		print
		print "       "+green("--changelog")+" ("+green("-l")+" short option)"
		print "              When pretending, also display the ChangeLog entries for packages"
		print "              that will be upgraded."
		print
		print "       "+green("--columns")
		print "              Display the pretend output in a tabular form. Versions are"
		print "              aligned vertically."
		print
		print "       "+green("--debug")+" ("+green("-d")+" short option)"
		print "              Tell emerge to run the ebuild command in --debug mode. In this"
		print "              mode, the bash build environment will run with the -x option,"
		print "              causing it to output verbose debug information print to stdout."
		print "              --debug is great for finding bash syntax errors as providing"
		print "              very verbose information about the dependency and build process."
		print
		print "       "+green("--deep")+" ("+green("-D")+" short option)"
		print "              This flag forces emerge to consider the entire dependency tree of"
		print "              packages, instead of checking only the immediate dependencies of"
		print "              the packages. As an example, this catches updates in libraries"
		print "              that are not directly listed in the dependencies of a package."
		print "              Also see --with-bdeps for behavior with respect to build time"
		print "              dependencies that are not strictly required."
		print 
		print "       "+green("--emptytree")+" ("+green("-e")+" short option)"
		print "              Virtually tweaks the tree of installed packages to contain"
		print "              nothing. This is great to use together with --pretend. This makes"
		print "              it possible for developers to get a complete overview of the"
		print "              complete dependency tree of a certain package."
		print
		print "       "+green("--fetchonly")+" ("+green("-f")+" short option)"
		print "              Instead of doing any package building, just perform fetches for"
		print "              all packages (main package as well as all dependencies.) When"
		print "              used in combination with --pretend all the SRC_URIs will be"
		print "              displayed multiple mirrors per line, one line per file."
		print
		print "       "+green("--fetch-all-uri")+" ("+green("-F")+" short option)"
		print "              Same as --fetchonly except that all package files, including those"
		print "              not required to build the package, will be processed."
		print
		print "       "+green("--getbinpkg")+" ("+green("-g")+" short option)"
		print "              Using the server and location defined in PORTAGE_BINHOST, portage"
		print "              will download the information from each binary file there and it"
		print "              will use that information to help build the dependency list. This"
		print "              option implies '-k'. (Use -gK for binary-only merging.)"
		print
		print "       "+green("--getbinpkgonly")+" ("+green("-G")+" short option)"
		print "              This option is identical to -g, as above, except it will not use"
		print "              ANY information from the local machine. All binaries will be"
		print "              downloaded from the remote server without consulting packages"
		print "              existing in the packages directory."
		print
		print "       "+green("--newuse")+" ("+green("-N")+" short option)"
		print "              Tells emerge to include installed packages where USE flags have "
		print "              changed since installation."
		print
		print "       "+green("--nocolor")
		print "              Suppresses color in the output."
		print
		print "       "+green("--noconfmem")
		print "              Portage keeps track of files that have been placed into"
		print "              CONFIG_PROTECT directories, and normally it will not merge the"
		print "              same file more than once, as that would become annoying. This"
		print "              can lead to problems when the user wants the file in the case"
		print "              of accidental deletion. With this option, files will always be"
		print "              merged to the live fs instead of silently dropped."
		print
		print "       "+green("--nodeps")+" ("+green("-O")+" short option)"
		print "              Merge specified packages, but don't merge any dependencies."
		print "              Note that the build may fail if deps aren't satisfied."
		print 
		print "       "+green("--noreplace")+" ("+green("-n")+" short option)"
		print "              Skip the packages specified on the command-line that have"
		print "              already been installed.  Without this option, any packages,"
		print "              ebuilds, or deps you specify on the command-line *will* cause"
		print "              Portage to remerge the package, even if it is already installed."
		print "              Note that Portage won't remerge dependencies by default."
		print 
		print "       "+green("--nospinner")
		print "              Disables the spinner regardless of terminal type."
		print
		print "       "+green("--oneshot")+" ("+green("-1")+" short option)"
		print "              Emerge as normal, but don't add packages to the world profile."
		print "              This package will only be updated if it is depended upon by"
		print "              another package."
		print
		print "       "+green("--onlydeps")+" ("+green("-o")+" short option)"
		print "              Only merge (or pretend to merge) the dependencies of the"
		print "              specified packages, not the packages themselves."
		print
		print "       "+green("--pretend")+" ("+green("-p")+" short option)"
		print "              Instead of actually performing the merge, simply display what"
		print "              ebuilds and tbz2s *would* have been installed if --pretend"
		print "              weren't used.  Using --pretend is strongly recommended before"
		print "              installing an unfamiliar package.  In the printout, N = new,"
		print "              U = updating, R = replacing, F = fetch  restricted, B = blocked"
		print "              by an already installed package, D = possible downgrading,"
		print "              S = slotted install. --verbose causes affecting use flags to be"
		print "              printed out accompanied by a '+' for enabled and a '-' for"
		print "              disabled USE flags."
		print
		print "       "+green("--quiet")+" ("+green("-q")+" short option)"
		print "              Effects vary, but the general outcome is a reduced or condensed"
		print "              output from portage's displays."
		print
		print "       "+green("--skipfirst")
		print "              This option is only valid in a resume situation. It removes the"
		print "              first package in the resume list so that a merge may continue in"
		print "              the presence of an uncorrectable or inconsequential error. This"
		print "              should only be used in cases where skipping the package will not"
		print "              result in failed dependencies."
		print
		print "       "+green("--tree")+" ("+green("-t")+" short option)"
		print "              Shows the dependency tree using indentation for dependencies."
		print "              The packages are also listed in reverse merge order so that"
		print "              a package's dependencies follow the package. Only really useful"
		print "              in combination with --emptytree, --update or --deep."
		print
		print "       "+green("--usepkg")+" ("+green("-k")+" short option)"
		print "              Tell emerge to use binary packages (from $PKGDIR) if they are"
		print "              available, thus possibly avoiding some time-consuming compiles."
		print "              This option is useful for CD installs; you can export"
		print "              PKGDIR=/mnt/cdrom/packages and then use this option to have"
		print "              emerge \"pull\" binary packages from the CD in order to satisfy" 
		print "              dependencies."
		print
		print "       "+green("--usepkgonly")+" ("+green("-K")+" short option)"
		print "              Like --usepkg above, except this only allows the use of binary"
		print "              packages, and it will abort the emerge if the package is not"
		print "              available at the time of dependency calculation."
		print
		print "       "+green("--verbose")+" ("+green("-v")+" short option)"
		print "              Effects vary, but the general outcome is an increased or expanded"
		print "              display of content in portage's displays."
		print
		print "       "+green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >"
		print "              In dependency calculations, pull in build time dependencies that"
		print "              are not strictly required. This defaults to 'n' for installation"
		print "              actions and 'y' for the --depclean action. This setting can be"
		print "              added to EMERGE_DEFAULT_OPTS (see make.conf(5)) and later"
		print "              overridden via the command line."
		print
	elif myaction == "sync":
		print
		print bold("Usage: ")+turquoise("emerge")+" "+turquoise("--sync")
		print
		print "       'emerge --sync' tells emerge to update the Portage tree as specified in"
		print "       The SYNC variable found in /etc/make.conf.  By default, SYNC instructs"
		print "       emerge to perform an rsync-style update with rsync.gentoo.org."
		print
		print "       'emerge-webrsync' exists as a helper app to emerge --sync, providing a"
		print "       method to receive the entire portage tree as a tarball that can be"
		print "       extracted and used. First time syncs would benefit greatly from this."
		print
		print "       "+turquoise("WARNING:")
		print "       If using our rsync server, emerge will clean out all files that do not"
		print "       exist on it, including ones that you may have created. The exceptions"
		print "       to this are the distfiles, local and packages directories."
		print
	elif myaction=="system":
		print
		print bold("Usage: ")+turquoise("emerge")+" [ "+green("options")+" ] "+turquoise("system")
		print
		print "       \"emerge system\" is the Portage system update command.  When run, it"
		print "       will scan the etc/make.profile/packages file and determine what"
		print "       packages need to be installed so that your system meets the minimum"
		print "       requirements of your current system profile.  Note that this doesn't"
		print "       necessarily bring your system up-to-date at all; instead, it just"
		print "       ensures that you have no missing parts.  For example, if your system"
		print "       profile specifies that you should have sys-apps/iptables installed"
		print "       and you don't, then \"emerge system\" will install it (the most"
		print "       recent version that matches the profile spec) for you.  It's always a"
		print "       good idea to do an \"emerge --pretend system\" before an \"emerge"
		print "       system\", just so you know what emerge is planning to do."
		print
	elif myaction=="world":
		print
		print bold("Usage: ")+turquoise("emerge")+" [ "+green("options")+" ] "+turquoise("world")
		print
		print "       'emerge world' is the Portage command for completely updating your"
		print "       system.  The normal procedure is to first do an 'emerge --sync' and"
		print "       then an 'emerge --update --deep world'.  The first command brings your"
		print "       local Portage tree up-to-date with the latest version information and"
		print "       ebuilds.  The second command then rebuilds all packages for which newer"
		print "       versions or newer ebuilds have become available since you last did a"
		print "       sync and update."
		print
	elif myaction=="config":
		outstuff=green("Config file management support (preliminary)")+"""

Portage has a special feature called "config file protection".  The purpose of
this feature is to prevent new package installs from clobbering existing
configuration files.  By default, config file protection is turned on for /etc
and the KDE configuration dirs; more may be added in the future.

When Portage installs a file into a protected directory tree like /etc, any
existing files will not be overwritten.  If a file of the same name already
exists, Portage will change the name of the to-be-installed file from 'foo' to
'._cfg0000_foo'.  If '._cfg0000_foo' already exists, this name becomes
'._cfg0001_foo', etc.  In this way, existing files are not overwritten,
allowing the administrator to manually merge the new config files and avoid any
unexpected changes.

In addition to protecting overwritten files, Portage will not delete any files
from a protected directory when a package is unmerged.  While this may be a
little bit untidy, it does prevent potentially valuable config files from being
deleted, which is of paramount importance.

Protected directories are set using the CONFIG_PROTECT variable, normally
defined in /etc/make.globals.  Directory exceptions to the CONFIG_PROTECTed
directories can be specified using the CONFIG_PROTECT_MASK variable.  To find
files that need to be updated in /etc, type:

# find /etc -iname '._cfg????_*'

You can disable this feature by setting CONFIG_PROTECT="-*" in /etc/make.conf.
Then, Portage will mercilessly auto-update your config files.  Alternatively,
you can leave Config File Protection on but tell Portage that it can overwrite
files in certain specific /etc subdirectories.  For example, if you wanted
Portage to automatically update your rc scripts and your wget configuration,
but didn't want any other changes made without your explicit approval, you'd
add this to /etc/make.conf:

CONFIG_PROTECT_MASK="/etc/wget /etc/rc.d"

Tools such as dispatch-conf, cfg-update, and etc-update are also available to
aid in the merging of these files. They provide interactive merging and can
auto-merge trivial changes.

"""
		print outstuff

