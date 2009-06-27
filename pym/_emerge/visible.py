# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage

def visible(pkgsettings, pkg):
	"""
	Check if a package is visible. This can raise an InvalidDependString
	exception if LICENSE is invalid.
	TODO: optionally generate a list of masking reasons
	@rtype: Boolean
	@returns: True if the package is visible, False otherwise.
	"""
	if not pkg.metadata["SLOT"]:
		return False
	if not pkg.installed:
		if not pkgsettings._accept_chost(pkg.cpv, pkg.metadata):
			return False
	if pkg.built and not pkg.installed:
		# we can have an old binary which has no EPREFIX information
		if "EPREFIX" not in pkg.metadata or not pkg.metadata["EPREFIX"]:
			return False
		if len(pkg.metadata["EPREFIX"].strip()) < len(pkgsettings["EPREFIX"]):
			return False
	eapi = pkg.metadata["EAPI"]
	if not portage.eapi_is_supported(eapi):
		return False
	if not pkg.installed:
		if portage._eapi_is_deprecated(eapi):
			return False
		if pkgsettings._getMissingKeywords(pkg.cpv, pkg.metadata):
			return False
	if pkgsettings._getMaskAtom(pkg.cpv, pkg.metadata):
		return False
	if pkgsettings._getProfileMaskAtom(pkg.cpv, pkg.metadata):
		return False
	try:
		if pkgsettings._getMissingLicenses(pkg.cpv, pkg.metadata):
			return False
	except portage.exception.InvalidDependString:
		return False
	return True

