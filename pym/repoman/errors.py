# repoman: Error Messages
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

COPYRIGHT_ERROR = 'Invalid Gentoo Copyright on line: %d'
LICENSE_ERROR = 'Invalid Gentoo/GPL License on line: %d'
CVS_HEADER_ERROR = 'Malformed CVS Header on line: %d'
LEADING_SPACES_ERROR = 'Ebuild contains leading spaces on line: %d'
TRAILING_WHITESPACE_ERROR = 'Trailing whitespace error on line: %d'
READONLY_ASSIGNMENT_ERROR = 'Ebuild contains assignment to read-only variable on line: %d'
MISSING_QUOTES_ERROR = 'Unquoted Variable on line: %d'
NESTED_DIE_ERROR = 'Ebuild calls die in a subshell on line: %d'
REDUNDANT_CD_S_ERROR = 'Ebuild has redundant cd ${S} statement on line: %d'
