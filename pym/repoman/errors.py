# repoman: Error Messages
# Copyright 2007-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

COPYRIGHT_ERROR = 'Invalid Gentoo Copyright on line: %d'
LICENSE_ERROR = 'Invalid Gentoo/GPL License on line: %d'
CVS_HEADER_ERROR = 'Malformed CVS Header on line: %d'
LEADING_SPACES_ERROR = 'Ebuild contains leading spaces on line: %d'
TRAILING_WHITESPACE_ERROR = 'Trailing whitespace error on line: %d'
READONLY_ASSIGNMENT_ERROR = 'Ebuild contains assignment to read-only variable on line: %d'
MISSING_QUOTES_ERROR = 'Unquoted Variable on line: %d'
NESTED_DIE_ERROR = 'Ebuild calls die in a subshell on line: %d'
PATCHES_ERROR = 'PATCHES is not a bash array on line: %d'
REDUNDANT_CD_S_ERROR = 'Ebuild has redundant cd ${S} statement on line: %d'
EMAKE_PARALLEL_DISABLED = 'Upstream parallel compilation bug (ebuild calls emake -j1 on line: %d)'
EMAKE_PARALLEL_DISABLED_VIA_MAKEOPTS = 'Upstream parallel compilation bug (MAKEOPTS=-j1 on line: %d)'
DEPRECATED_BINDNOW_FLAGS = 'Deprecated bindnow-flags call on line: %d'
EAPI_DEFINED_AFTER_INHERIT = 'EAPI defined after inherit on line: %d'
NO_AS_NEEDED = 'Upstream asneeded linking bug (no-as-needed on line: %d)'
PRESERVE_OLD_LIB = 'Upstream ABI change workaround on line: %d'
BUILT_WITH_USE = 'built_with_use on line: %d'
NO_OFFSET_WITH_HELPERS = "Helper function is used with D, ROOT, ED, EROOT or EPREFIX on line :%d"
SANDBOX_ADDPREDICT = 'Ebuild calls addpredict on line: %d'
USEQ_ERROR = 'Ebuild calls deprecated useq function on line: %d'
HASQ_ERROR = 'Ebuild calls deprecated hasq function on line: %d'
