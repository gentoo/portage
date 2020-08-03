# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['getmaskingstatus']

import portage
from portage import eapi_is_supported, _eapi_is_deprecated
from portage.exception import InvalidDependString
from portage.localization import _
from portage.package.ebuild.config import config
from portage.versions import _pkg_str

class _UnmaskHint:

	__slots__ = ('key', 'value')

	def __init__(self, key, value):
		self.key = key
		self.value = value

class _MaskReason:

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
	if not isinstance(mycpv, str):
		# emerge passed in a Package instance
		pkg = mycpv
		mycpv = pkg.cpv
		metadata = pkg._metadata
		installed = pkg.installed

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

	try:
		mycpv.slot
	except AttributeError:
		try:
			mycpv = _pkg_str(mycpv, metadata=metadata, settings=settings)
		except portage.exception.InvalidData:
			raise ValueError(_("invalid CPV: %s") % mycpv)

	rValue = []

	# package.mask checking
	if settings._getMaskAtom(mycpv, metadata):
		rValue.append(_MaskReason("package.mask", "package.mask", _UnmaskHint("p_mask", None)))

	# keywords checking
	eapi = metadata["EAPI"]
	mygroups = settings._getKeywords(mycpv, metadata)
	licenses = metadata["LICENSE"]
	properties = metadata["PROPERTIES"]
	restrict = metadata["RESTRICT"]
	if not eapi_is_supported(eapi):
		return [_MaskReason("EAPI", "EAPI %s" % eapi)]
	if _eapi_is_deprecated(eapi) and not installed:
		return [_MaskReason("EAPI", "EAPI %s" % eapi)]
	egroups = settings.configdict["backupenv"].get(
		"ACCEPT_KEYWORDS", "").split()
	global_accept_keywords = settings.get("ACCEPT_KEYWORDS", "")
	pgroups = global_accept_keywords.split()
	myarch = settings["ARCH"]
	if pgroups and myarch not in pgroups:
		"""For operating systems other than Linux, ARCH is not necessarily a
		valid keyword."""
		myarch = pgroups[0].lstrip("~")

	# NOTE: This logic is copied from KeywordsManager.getMissingKeywords().
	unmaskgroups = settings._keywords_manager.getPKeywords(mycpv,
		metadata["SLOT"], metadata["repository"], global_accept_keywords)
	pgroups.extend(unmaskgroups)
	if unmaskgroups or egroups:
		pgroups = settings._keywords_manager._getEgroups(egroups, pgroups)
	else:
		pgroups = set(pgroups)

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
			elif gp == "~*":
				for x in pgroups:
					if x[:1] == "~":
						kmask = None
						break
				if kmask is None:
					break
			elif gp=="-"+myarch and myarch in pgroups:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch and myarch in pgroups:
				kmask="~"+myarch
				kmask_hint = _UnmaskHint("unstable keyword", kmask)
				break

	if kmask == "missing":
		kmask_hint = _UnmaskHint("unstable keyword", "**")

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

	try:
		missing_restricts = settings._getMissingRestrict(mycpv, metadata)
		if missing_restricts:
			msg = list(missing_restricts)
			msg.append("in RESTRICT")
			rValue.append(_MaskReason("RESTRICT", " ".join(msg)))
	except InvalidDependString as e:
		rValue.append(_MaskReason("invalid", "RESTRICT: %s" % (e,)))

	# Only show KEYWORDS masks for installed packages
	# if they're not masked for any other reason.
	if kmask and (not installed or not rValue):
		rValue.append(_MaskReason("KEYWORDS",
			kmask + " keyword", unmask_hint=kmask_hint))

	return rValue
