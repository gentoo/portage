# -*- coding:utf-8 -*-

import logging

from _emerge.Package import Package

# import our initialized portage instance
from repoman._portage import portage

max_desc_len = 80
allowed_filename_chars = "a-zA-Z0-9._-+:"

qahelp = {
	"CVS/Entries.IO_error": (
		"Attempting to commit, and an IO error was encountered access the"
		" Entries file"),
	"ebuild.invalidname": (
		"Ebuild files with a non-parseable or syntactically incorrect name"
		" (or using 2.1 versioning extensions)"),
	"ebuild.namenomatch": (
		"Ebuild files that do not have the same name as their parent"
		" directory"),
	"changelog.ebuildadded": (
		"An ebuild was added but the ChangeLog was not modified"),
	"changelog.missing": (
		"Missing ChangeLog files"),
	"ebuild.notadded": (
		"Ebuilds that exist but have not been added to cvs"),
	"ebuild.patches": (
		"PATCHES variable should be a bash array to ensure white space safety"),
	"changelog.notadded": (
		"ChangeLogs that exist but have not been added to cvs"),
	"dependency.bad": (
		"User-visible ebuilds with unsatisfied dependencies"
		" (matched against *visible* ebuilds)"),
	"dependency.badmasked": (
		"Masked ebuilds with unsatisfied dependencies"
		" (matched against *all* ebuilds)"),
	"dependency.badindev": (
		"User-visible ebuilds with unsatisfied dependencies"
		" (matched against *visible* ebuilds) in developing arch"),
	"dependency.badmaskedindev": (
		"Masked ebuilds with unsatisfied dependencies"
		" (matched against *all* ebuilds) in developing arch"),
	"dependency.badtilde": (
		"Uses the ~ dep operator with a non-zero revision part,"
		" which is useless (the revision is ignored)"),
	"dependency.missingslot": (
		"RDEPEND matches more than one SLOT but does not specify a "
		"slot and/or use the := or :* slot operator"),
	"dependency.perlcore": (
		"This ebuild directly depends on a package in perl-core;"
		" it should use the corresponding virtual instead."),
	"dependency.syntax": (
		"Syntax error in dependency string"
		" (usually an extra/missing space/parenthesis)"),
	"dependency.unknown": (
		"Ebuild has a dependency that refers to an unknown package"
		" (which may be valid if it is a blocker for a renamed/removed package,"
		" or is an alternative choice provided by an overlay)"),
	"dependency.badslotop": (
		"RDEPEND contains ':=' slot operator under '||' dependency."),
	"file.executable": (
		"Ebuilds, digests, metadata.xml, Manifest, and ChangeLog do not need"
		" the executable bit"),
	"file.size": (
		"Files in the files directory must be under 20 KiB"),
	"file.size.fatal": (
		"Files in the files directory must be under 60 KiB"),
	"file.empty": (
		"Empty file in the files directory"),
	"file.name": (
		"File/dir name must be composed"
		" of only the following chars: %s " % allowed_filename_chars),
	"file.UTF8": (
		"File is not UTF8 compliant"),
	"inherit.deprecated": (
		"Ebuild inherits a deprecated eclass"),
	"inherit.missing": (
		"Ebuild uses functions from an eclass but does not inherit it"),
	"inherit.unused": (
		"Ebuild inherits an eclass but does not use it"),
	"java.eclassesnotused": (
		"With virtual/jdk in DEPEND you must inherit a java eclass"),
	"wxwidgets.eclassnotused": (
		"Ebuild DEPENDs on x11-libs/wxGTK without inheriting wxwidgets.eclass"),
	"KEYWORDS.dropped": (
		"Ebuilds that appear to have dropped KEYWORDS for some arch"),
	"KEYWORDS.missing": (
		"Ebuilds that have a missing or empty KEYWORDS variable"),
	"KEYWORDS.stable": (
		"Ebuilds that have been added directly with stable KEYWORDS"),
	"KEYWORDS.stupid": (
		"Ebuilds that use KEYWORDS=-* instead of package.mask"),
	"LICENSE.missing": (
		"Ebuilds that have a missing or empty LICENSE variable"),
	"LICENSE.virtual": (
		"Virtuals that have a non-empty LICENSE variable"),
	"DESCRIPTION.missing": (
		"Ebuilds that have a missing or empty DESCRIPTION variable"),
	"DESCRIPTION.toolong": (
		"DESCRIPTION is over %d characters" % max_desc_len),
	"EAPI.definition": (
		"EAPI definition does not conform to PMS section 7.3.1"
		" (first non-comment, non-blank line)"),
	"EAPI.deprecated": (
		"Ebuilds that use features that are deprecated in the current EAPI"),
	"EAPI.incompatible": (
		"Ebuilds that use features that are only available with a different"
		" EAPI"),
	"EAPI.unsupported": (
		"Ebuilds that have an unsupported EAPI version"
		" (you must upgrade portage)"),
	"SLOT.invalid": (
		"Ebuilds that have a missing or invalid SLOT variable value"),
	"HOMEPAGE.missing": (
		"Ebuilds that have a missing or empty HOMEPAGE variable"),
	"HOMEPAGE.virtual": (
		"Virtuals that have a non-empty HOMEPAGE variable"),
	"HOMEPAGE.missingurischeme": (
		"HOMEPAGE is missing an URI scheme"),
	"PDEPEND.suspect": (
		"PDEPEND contains a package that usually only belongs in DEPEND."),
	"LICENSE.syntax": (
		"Syntax error in LICENSE"
		" (usually an extra/missing space/parenthesis)"),
	"PROVIDE.syntax": (
		"Syntax error in PROVIDE"
		" (usually an extra/missing space/parenthesis)"),
	"PROPERTIES.syntax": (
		"Syntax error in PROPERTIES"
		" (usually an extra/missing space/parenthesis)"),
	"RESTRICT.syntax": (
		"Syntax error in RESTRICT"
		" (usually an extra/missing space/parenthesis)"),
	"REQUIRED_USE.syntax": (
		"Syntax error in REQUIRED_USE"
		" (usually an extra/missing space/parenthesis)"),
	"SRC_URI.syntax": (
		"Syntax error in SRC_URI"
		" (usually an extra/missing space/parenthesis)"),
	"SRC_URI.mirror": (
		"A uri listed in profiles/thirdpartymirrors is found in SRC_URI"),
	"ebuild.syntax": (
		"Error generating cache entry for ebuild;"
		" typically caused by ebuild syntax error"
		" or digest verification failure"),
	"ebuild.output": (
		"A simple sourcing of the ebuild produces output;"
		" this breaks ebuild policy."),
	"ebuild.nesteddie": (
		"Placing 'die' inside ( ) prints an error,"
		" but doesn't stop the ebuild."),
	"variable.invalidchar": (
		"A variable contains an invalid character"
		" that is not part of the ASCII character set"),
	"variable.readonly": (
		"Assigning a readonly variable"),
	"variable.usedwithhelpers": (
		"Ebuild uses D, ROOT, ED, EROOT or EPREFIX with helpers"),
	"LIVEVCS.stable": (
		"This ebuild is a live checkout from a VCS but has stable keywords."),
	"LIVEVCS.unmasked": (
		"This ebuild is a live checkout from a VCS but has keywords"
		" and is not masked in the global package.mask."),
	"IUSE.invalid": (
		"This ebuild has a variable in IUSE"
		" that is not in the use.desc or its metadata.xml file"),
	"IUSE.missing": (
		"This ebuild has a USE conditional"
		" which references a flag that is not listed in IUSE"),
	"IUSE.rubydeprecated": (
		"The ebuild has set a ruby interpreter in USE_RUBY,"
		" that is not available as a ruby target anymore"),
	"LICENSE.invalid": (
		"This ebuild is listing a license"
		" that doesnt exist in portages license/ dir."),
	"LICENSE.deprecated": (
		"This ebuild is listing a deprecated license."),
	"KEYWORDS.invalid": (
		"This ebuild contains KEYWORDS"
		" that are not listed in profiles/arch.list"
		" or for which no valid profile was found"),
	"RDEPEND.implicit": (
		"RDEPEND is unset in the ebuild"
		" which triggers implicit RDEPEND=$DEPEND assignment"
		" (prior to EAPI 4)"),
	"RDEPEND.suspect": (
		"RDEPEND contains a package that usually only belongs in DEPEND."),
	"RESTRICT.invalid": (
		"This ebuild contains invalid RESTRICT values."),
	"digest.assumed": (
		"Existing digest must be assumed correct (Package level only)"),
	"digest.missing": (
		"Some files listed in SRC_URI aren't referenced in the Manifest"),
	"digest.unused": (
		"Some files listed in the Manifest aren't referenced in SRC_URI"),
	"ebuild.absdosym": (
		"This ebuild uses absolute target to dosym where relative symlink"
		" could be used instead"),
	"ebuild.majorsyn": (
		"This ebuild has a major syntax error"
		" that may cause the ebuild to fail partially or fully"),
	"ebuild.minorsyn": (
		"This ebuild has a minor syntax error"
		" that contravenes gentoo coding style"),
	"ebuild.badheader": (
		"This ebuild has a malformed header"),
	"manifest.bad": (
		"Manifest has missing or incorrect digests"),
	"metadata.missing": (
		"Missing metadata.xml files"),
	"metadata.bad": (
		"Bad metadata.xml files"),
	"metadata.warning": (
		"Warnings in metadata.xml files"),
	"portage.internal": (
		"The ebuild uses an internal Portage function or variable"),
	"repo.eapi.banned": (
		"The ebuild uses an EAPI which is"
		" banned by the repository's metadata/layout.conf settings"),
	"repo.eapi.deprecated": (
		"The ebuild uses an EAPI which is"
		" deprecated by the repository's metadata/layout.conf settings"),
	"virtual.oldstyle": (
		"The ebuild PROVIDEs an old-style virtual (see GLEP 37)"),
	"virtual.suspect": (
		"Ebuild contains a package"
		" that usually should be pulled via virtual/, not directly."),
	"usage.obsolete": (
		"The ebuild makes use of an obsolete construct"),
	"upstream.workaround": (
		"The ebuild works around an upstream bug,"
		" an upstream bug should be filed and tracked in bugs.gentoo.org"),
	"uri.https": "URI uses http:// but should use https://",
}

qacats = list(qahelp)
qacats.sort()

qawarnings = set((
	"changelog.missing",
	"changelog.notadded",
	"dependency.unknown",
	"digest.assumed",
	"digest.unused",
	"ebuild.notadded",
	"ebuild.nesteddie",
	"dependency.badmasked",
	"dependency.badindev",
	"dependency.badmaskedindev",
	"dependency.badtilde",
	"dependency.missingslot",
	"dependency.perlcore",
	"DESCRIPTION.toolong",
	"EAPI.deprecated",
	"HOMEPAGE.virtual",
	"LICENSE.deprecated",
	"LICENSE.virtual",
	"KEYWORDS.dropped",
	"KEYWORDS.stupid",
	"KEYWORDS.missing",
	"PDEPEND.suspect",
	"RDEPEND.implicit",
	"RDEPEND.suspect",
	"virtual.suspect",
	"RESTRICT.invalid",
	"ebuild.absdosym",
	"ebuild.minorsyn",
	"ebuild.badheader",
	"ebuild.patches",
	"file.empty",
	"file.size",
	"inherit.unused",
	"inherit.deprecated",
	"java.eclassesnotused",
	"wxwidgets.eclassnotused",
	"metadata.warning",
	"portage.internal",
	"repo.eapi.deprecated",
	"usage.obsolete",
	"upstream.workaround",
	"IUSE.rubydeprecated",
	"uri.https",
))


missingvars = ["KEYWORDS", "LICENSE", "DESCRIPTION", "HOMEPAGE"]
allvars = set(x for x in portage.auxdbkeys if not x.startswith("UNUSED_"))
allvars.update(Package.metadata_keys)
allvars = sorted(allvars)

for x in missingvars:
	x += ".missing"
	if x not in qacats:
		logging.warning('* missingvars values need to be added to qahelp ("%s")' % x)
		qacats.append(x)
		qawarnings.add(x)

valid_restrict = frozenset([
	"binchecks", "bindist", "fetch", "installsources", "mirror",
	"preserve-libs", "primaryuri", "splitdebug", "strip", "test", "userpriv"])


suspect_rdepend = frozenset([
	"app-arch/cabextract",
	"app-arch/rpm2targz",
	"app-doc/doxygen",
	"dev-lang/nasm",
	"dev-lang/swig",
	"dev-lang/yasm",
	"dev-perl/extutils-pkgconfig",
	"dev-qt/linguist-tools",
	"dev-util/byacc",
	"dev-util/cmake",
	"dev-util/ftjam",
	"dev-util/gperf",
	"dev-util/gtk-doc",
	"dev-util/gtk-doc-am",
	"dev-util/intltool",
	"dev-util/jam",
	"dev-util/pkg-config-lite",
	"dev-util/pkgconf",
	"dev-util/pkgconfig",
	"dev-util/pkgconfig-openbsd",
	"dev-util/scons",
	"dev-util/unifdef",
	"dev-util/yacc",
	"media-gfx/ebdftopcf",
	"sys-apps/help2man",
	"sys-devel/autoconf",
	"sys-devel/automake",
	"sys-devel/bin86",
	"sys-devel/bison",
	"sys-devel/dev86",
	"sys-devel/flex",
	"sys-devel/m4",
	"sys-devel/pmake",
	"virtual/linux-sources",
	"virtual/linuxtv-dvb-headers",
	"virtual/os-headers",
	"virtual/pkgconfig",
	"x11-misc/bdftopcf",
	"x11-misc/imake",
])

suspect_virtual = {
	"dev-util/pkg-config-lite": "virtual/pkgconfig",
	"dev-util/pkgconf": "virtual/pkgconfig",
	"dev-util/pkgconfig": "virtual/pkgconfig",
	"dev-util/pkgconfig-openbsd": "virtual/pkgconfig",
	"dev-libs/libusb": "virtual/libusb",
	"dev-libs/libusbx": "virtual/libusb",
	"dev-libs/libusb-compat": "virtual/libusb",
}

ruby_deprecated = frozenset([
	"ruby_targets_ree18",
	"ruby_targets_ruby18",
	"ruby_targets_ruby19",
	"ruby_targets_ruby20",
])


# file.executable
no_exec = frozenset(["Manifest", "ChangeLog", "metadata.xml"])


def format_qa_output(
	formatter, fails, dofull, dofail, options, qawarnings):
	"""Helper function that formats output properly

	@param formatter: an instance of Formatter
	@type formatter: Formatter
	@param fails: dict of qa status failures
	@type fails: dict
	@param dofull: Whether to print full results or a summary
	@type dofull: boolean
	@param dofail: Whether failure was hard or soft
	@type dofail: boolean
	@param options: The command-line options provided to repoman
	@type options: Namespace
	@param qawarnings: the set of warning types
	@type qawarnings: set
	@return: None (modifies formatter)
	"""
	full = options.mode == 'full'
	# we only want key value pairs where value > 0
	for category in sorted(fails):
		number = len(fails[category])
		formatter.add_literal_data("  " + category)
		spacing_width = 30 - len(category)
		if category in qawarnings:
			formatter.push_style("WARN")
		else:
			formatter.push_style("BAD")
			formatter.add_literal_data(" [fatal]")
			spacing_width -= 8

		formatter.add_literal_data(" " * spacing_width)
		formatter.add_literal_data("%s" % number)
		formatter.pop_style()
		formatter.add_line_break()
		if not dofull:
			if not full and dofail and category in qawarnings:
				# warnings are considered noise when there are failures
				continue
			fails_list = fails[category]
			if not full and len(fails_list) > 12:
				fails_list = fails_list[:12]
			for failure in fails_list:
				formatter.add_literal_data("   " + failure)
				formatter.add_line_break()


def format_qa_output_column(
	formatter, fails, dofull, dofail, options, qawarnings):
	"""Helper function that formats output in a machine-parseable column format

	@param formatter: an instance of Formatter
	@type formatter: Formatter
	@param fails: dict of qa status failures
	@type fails: dict
	@param dofull: Whether to print full results or a summary
	@type dofull: boolean
	@param dofail: Whether failure was hard or soft
	@type dofail: boolean
	@param options: The command-line options provided to repoman
	@type options: Namespace
	@param qawarnings: the set of warning types
	@type qawarnings: set
	@return: None (modifies formatter)
	"""
	full = options.mode == 'full'
	for category in sorted(fails):
		number = len(fails[category])
		formatter.add_literal_data("NumberOf " + category + " ")
		if category in qawarnings:
			formatter.push_style("WARN")
		else:
			formatter.push_style("BAD")
		formatter.add_literal_data("%s" % number)
		formatter.pop_style()
		formatter.add_line_break()
		if not dofull:
			if not full and dofail and category in qawarnings:
				# warnings are considered noise when there are failures
				continue
			fails_list = fails[category]
			if not full and len(fails_list) > 12:
				fails_list = fails_list[:12]
			for failure in fails_list:
				formatter.add_literal_data(category + " " + failure)
				formatter.add_line_break()
