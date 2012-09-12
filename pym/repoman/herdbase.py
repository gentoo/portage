# -*- coding: utf-8 -*-
# repoman: Herd database analysis
# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2 or later

import errno
import xml.etree.ElementTree
try:
	from xml.parsers.expat import ExpatError
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# http://bugs.python.org/issue14988
	# This means that python is built without xml support.
	# We tolerate global scope import failures for optional
	# modules, so that ImportModulesTestCase can succeed (or
	# possibly alert us about unexpected import failures).
	pass

from portage import _encodings, _unicode_encode
from portage.exception import FileNotFound, ParseError, PermissionDenied

__all__ = [
	"make_herd_base"
]

def _make_email(nick_name):
	if not nick_name.endswith('@gentoo.org'):
		nick_name = nick_name + '@gentoo.org'
	return nick_name


class HerdBase(object):
	def __init__(self, herd_to_emails, all_emails):
		self.herd_to_emails = herd_to_emails
		self.all_emails = all_emails

	def known_herd(self, herd_name):
		return herd_name in self.herd_to_emails

	def known_maintainer(self, nick_name):
		return _make_email(nick_name) in self.all_emails

	def maintainer_in_herd(self, nick_name, herd_name):
		return _make_email(nick_name) in self.herd_to_emails[herd_name]

class _HerdsTreeBuilder(xml.etree.ElementTree.TreeBuilder):
	"""
	Implements doctype() as required to avoid deprecation warnings with
	>=python-2.7.
	"""
	def doctype(self, name, pubid, system):
		pass

def make_herd_base(filename):
	herd_to_emails = dict()
	all_emails = set()

	try:
		xml_tree = xml.etree.ElementTree.parse(_unicode_encode(filename,
				encoding=_encodings['fs'], errors='strict'),
			parser=xml.etree.ElementTree.XMLParser(
				target=_HerdsTreeBuilder()))
	except ExpatError as e:
		raise ParseError("metadata.xml: " + str(e))
	except EnvironmentError as e:
		func_call = "open('%s')" % filename
		if e.errno == errno.EACCES:
			raise PermissionDenied(func_call)
		elif e.errno == errno.ENOENT:
			raise FileNotFound(filename)
		raise

	herds = xml_tree.findall('herd')
	for h in herds:
		_herd_name = h.find('name')
		if _herd_name is None:
			continue
		herd_name = _herd_name.text.strip()
		del _herd_name

		maintainers = h.findall('maintainer')
		herd_emails = set()
		for m in maintainers:
			_m_email = m.find('email')
			if _m_email is None:
				continue
			m_email = _m_email.text.strip()

			herd_emails.add(m_email)
			all_emails.add(m_email)

		herd_to_emails[herd_name] = herd_emails

	return HerdBase(herd_to_emails, all_emails)


if __name__ == '__main__':
	h = make_herd_base('/usr/portage/metadata/herds.xml')

	assert(h.known_herd('sound'))
	assert(not h.known_herd('media-sound'))

	assert(h.known_maintainer('sping'))
	assert(h.known_maintainer('sping@gentoo.org'))
	assert(not h.known_maintainer('portage'))

	assert(h.maintainer_in_herd('zmedico@gentoo.org', 'tools-portage'))
	assert(not h.maintainer_in_herd('pva@gentoo.org', 'tools-portage'))

	import pprint
	pprint.pprint(h.herd_to_emails)
