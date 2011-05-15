# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['getmaskingstatus']

import sys

import portage
from portage import eapi_is_supported, _eapi_is_deprecated
from portage.dep import match_from_list, _slot_separator, _repo_separator
from portage.localization import _
from portage.package.ebuild.config import config
from portage.versions import catpkgsplit, cpv_getkey

if sys.hexversion >= 0x3000000:
	basestring = str

class _UnmaskHint(object):

	__slots__ = ('key', 'value')

	def __init__(self, key, value):
		self.key = key
		self.value = value

class _MaskReason(object):

	__slots__ = ('category', 'message', 'unmask_hint')

	def __init__(self, category, message, unmask_hint=None):
		self.category = category
		self.message = message
		self.unmask_hint = unmask_hint

def getmaskingstatus(mycpv, settings=None, portdb=None, myrepo=None):
	if settings is None:
		settings = config(clone=portage.settings)
	if portdb is None:
		portdb = portage.portdb

	return [mreason.message for \
		mreason in _getmaskingstatus(mycpv, settings, portdb,myrepo)]

def _getmaskingstatus(mycpv, settings, portdb, myrepo=None):

	metadata = None
	installed = False
	if not isinstance(mycpv, basestring):
		# emerge passed in a Package instance
		pkg = mycpv
		mycpv = pkg.cpv
		metadata = pkg.metadata
		installed = pkg.installed

	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError(_("invalid CPV: %s") % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(zip(db_keys, portdb.aux_get(mycpv, db_keys, myrepo=myrepo)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
			return [_MaskReason("corruption", "corruption")]
		if "?" in metadata["LICENSE"]:
			settings.setcpv(mycpv, mydb=metadata)
			metadata["USE"] = settings["PORTAGE_USE"]
		else:
			metadata["USE"] = ""

	rValue = []

	# profile checking
	if settings._getProfileMaskAtom(mycpv, metadata):
		rValue.append(_MaskReason("profile", "profile"))

	# package.mask checking
	if settings._getMaskAtom(mycpv, metadata):
		rValue.append(_MaskReason("package.mask", "package.mask", _UnmaskHint("p_mask", None)))

	# keywords checking
	eapi = metadata["EAPI"]
	mygroups = settings._getKeywords(mycpv, metadata)
	licenses = metadata["LICENSE"]
	properties = metadata["PROPERTIES"]
	if eapi.startswith("-"):
		eapi = eapi[1:]
	if not eapi_is_supported(eapi):
		return [_MaskReason("EAPI", "EAPI %s" % eapi)]
	elif _eapi_is_deprecated(eapi) and not installed:
		return [_MaskReason("EAPI", "EAPI %s" % eapi)]
	egroups = settings.configdict["backupenv"].get(
		"ACCEPT_KEYWORDS", "").split()
	pgroups = settings["ACCEPT_KEYWORDS"].split()
	myarch = settings["ARCH"]
	if pgroups and myarch not in pgroups:
		"""For operating systems other than Linux, ARCH is not necessarily a
		valid keyword."""
		myarch = pgroups[0].lstrip("~")

	cp = cpv_getkey(mycpv)
	pkgdict = settings._keywords_manager.pkeywordsdict.get(cp)
	matches = False
	if pkgdict:
		pkg = "".join((mycpv, _slot_separator, metadata["SLOT"]))
		if 'repository' in metadata:
			pkg = "".join((pkg, _repo_separator, metadata['repository']))
		cpv_slot_list = [pkg]
		for atom, pkgkeywords in pkgdict.items():
			if match_from_list(atom, cpv_slot_list):
				matches = True
				pgroups.extend(pkgkeywords)
	if matches or egroups:
		pgroups.extend(egroups)
		inc_pgroups = set()
		for x in pgroups:
			if x.startswith("-"):
				if x == "-*":
					inc_pgroups.clear()
				else:
					inc_pgroups.discard(x[1:])
			else:
				inc_pgroups.add(x)
		pgroups = inc_pgroups
		del inc_pgroups

	kmask = "missing"
	kmask_hint = None

	if '**' in pgroups:
		kmask = None
	else:
		for keyword in pgroups:
			if keyword in mygroups:
				kmask = None
				break

	if kmask:
		for gp in mygroups:
			if gp=="*":
				kmask=None
				break
			elif gp=="-"+myarch and myarch in pgroups:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch and myarch in pgroups:
				kmask="~"+myarch
				kmask_hint = _UnmaskHint("unstable keyword", kmask)
				break

	try:
		missing_licenses = settings._getMissingLicenses(mycpv, metadata)
		if missing_licenses:
			allowed_tokens = set(["||", "(", ")"])
			allowed_tokens.update(missing_licenses)
			license_split = licenses.split()
			license_split = [x for x in license_split \
				if x in allowed_tokens]
			msg = license_split[:]
			msg.append("license(s)")
			rValue.append(_MaskReason("LICENSE", " ".join(msg), _UnmaskHint("license", set(missing_licenses))))
	except portage.exception.InvalidDependString as e:
		rValue.append(_MaskReason("invalid", "LICENSE: "+str(e)))

	try:
		missing_properties = settings._getMissingProperties(mycpv, metadata)
		if missing_properties:
			allowed_tokens = set(["||", "(", ")"])
			allowed_tokens.update(missing_properties)
			properties_split = properties.split()
			properties_split = [x for x in properties_split \
					if x in allowed_tokens]
			msg = properties_split[:]
			msg.append("properties")
			rValue.append(_MaskReason("PROPERTIES", " ".join(msg)))
	except portage.exception.InvalidDependString as e:
		rValue.append(_MaskReason("invalid", "PROPERTIES: "+str(e)))

	# Only show KEYWORDS masks for installed packages
	# if they're not masked for any other reason.
	if kmask and (not installed or not rValue):
		rValue.append(_MaskReason("KEYWORDS",
			kmask + " keyword", unmask_hint=kmask_hint))

	return rValue
