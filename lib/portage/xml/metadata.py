# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""Provides an easy-to-use python interface to Gentoo's metadata.xml file.

	Example usage:
		>>> from portage.xml.metadata import MetaDataXML
		>>> pkg_md = MetaDataXML('/var/db/repos/gentoo/app-misc/gourmet/metadata.xml')
		>>> pkg_md
		<MetaDataXML '/var/db/repos/gentoo/app-misc/gourmet/metadata.xml'>
		>>> pkg_md.herds()
		['no-herd']
		>>> for maint in pkg_md.maintainers():
		...     print "{0} ({1})".format(maint.email, maint.name)
		...
		nixphoeni@gentoo.org (Joe Sapp)
		>>> for flag in pkg_md.use():
		...     print flag.name, "->", flag.description
		...
		rtf -> Enable export to RTF
		gnome-print -> Enable printing support using gnome-print
		>>> upstream = pkg_md.upstream()
		>>> upstream
		[<_Upstream {'docs': [], 'remoteid': [], 'maintainer':
		 [<_Maintainer 'Thomas_Hinkle@alumni.brown.edu'>], 'bugtracker': [],
		 'changelog': []}>]
		>>> upstream[0].maintainer[0].name
		'Thomas Mills Hinkle'
"""

__all__ = ('MetaDataXML', 'parse_metadata_use')


import re
import xml.etree.ElementTree as etree

try:
	from xml.parsers.expat import ExpatError
except Exception:
	ExpatError = SyntaxError

from portage import _encodings, _unicode_encode
from portage.util import cmp_sort_key, unique_everseen


class _MetadataTreeBuilder(etree.TreeBuilder):
	"""
	Implements doctype() as required to avoid deprecation warnings with
	Python >=2.7.
	"""
	def doctype(self, name, pubid, system):
		pass

class _Maintainer:
	"""An object for representing one maintainer.

	@type email: str or None
	@ivar email: Maintainer's email address. Used for both Gentoo and upstream.
	@type name: str or None
	@ivar name: Maintainer's name. Used for both Gentoo and upstream.
	@type description: str or None
	@ivar description: Description of what a maintainer does. Gentoo only.
	@type maint_type: str or None
	@ivar maint_type: GLEP67 maintainer type (project or person). Gentoo only.
	@type restrict: str or None
	@ivar restrict: e.g. &gt;=portage-2.2 means only maintains versions
		of Portage greater than 2.2. Should be DEPEND string with < and >
		converted to &lt; and &gt; respectively.
	@type status: str or None
	@ivar status: If set, either 'active' or 'inactive'. Upstream only.
	"""

	def __init__(self, node):
		self.email = None
		self.name = None
		self.description = None
		self.maint_type = node.get('type')
		self.restrict = node.get('restrict')
		self.status = node.get('status')
		for attr in node:
			setattr(self, attr.tag, attr.text)

	def __repr__(self):
		return "<%s %r>" % (self.__class__.__name__, self.email)


class _Useflag:
	"""An object for representing one USE flag.

	@todo: Is there any way to have a keyword option to leave in
		<pkg> and <cat> for later processing?
	@type name: str or None
	@ivar name: USE flag
	@type restrict: str or None
	@ivar restrict: e.g. &gt;=portage-2.2 means flag is only available in
		versions greater than 2.2
	@type description: str
	@ivar description: description of the USE flag
	"""

	def __init__(self, node):
		self.name = node.get('name')
		self.restrict = node.get('restrict')
		_desc = ''
		if node.text:
			_desc = node.text
		for child in node.getchildren():
			_desc += child.text if child.text else ''
			_desc += child.tail if child.tail else ''
		# This takes care of tabs and newlines left from the file
		self.description = re.sub(r'\s+', ' ', _desc)

	def __repr__(self):
		return "<%s %r>" % (self.__class__.__name__, self.name)


class _Upstream:
	"""An object for representing one package's upstream.

	@type maintainers: list
	@ivar maintainers: L{_Maintainer} objects for each upstream maintainer
	@type changelogs: list
	@ivar changelogs: URLs to upstream's ChangeLog file in str format
	@type docs: list
	@ivar docs: Sequence of tuples containing URLs to upstream documentation
		in the first slot and 'lang' attribute in the second, e.g.,
		[('http.../docs/en/tut.html', None), ('http.../doc/fr/tut.html', 'fr')]
	@type bugtrackers: list
	@ivar bugtrackers: URLs to upstream's bugtracker. May also contain an email
		address if prepended with 'mailto:'
	@type remoteids: list
	@ivar remoteids: Sequence of tuples containing the project's hosting site
		name in the first slot and the project's ID name or number for that
		site in the second, e.g., [('sourceforge', 'systemrescuecd')]
	"""

	def __init__(self, node):
		self.node = node
		self.maintainers = self.upstream_maintainers()
		self.changelogs = self.upstream_changelogs()
		self.docs = self.upstream_documentation()
		self.bugtrackers = self.upstream_bugtrackers()
		self.remoteids = self.upstream_remoteids()

	def __repr__(self):
		return "<%s %r>" % (self.__class__.__name__, self.__dict__)

	def upstream_bugtrackers(self):
		"""Retrieve upstream bugtracker location from xml node."""
		return [e.text for e in self.node.findall('bugs-to') if e.text]

	def upstream_changelogs(self):
		"""Retrieve upstream changelog location from xml node."""
		return [e.text for e in self.node.findall('changelog') if e.text]

	def upstream_documentation(self):
		"""Retrieve upstream documentation location from xml node."""
		result = []
		for elem in (e for e in self.node.findall('doc') if e.text):
			lang = elem.get('lang')
			result.append((elem.text, lang))
		return result

	def upstream_maintainers(self):
		"""Retrieve upstream maintainer information from xml node."""
		return [_Maintainer(m) for m in self.node.findall('maintainer')]

	def upstream_remoteids(self):
		"""Retrieve upstream remote ID from xml node."""
		return [(e.text, e.get('type')) for e in self.node.findall('remote-id') if e.text]


class MetaDataXML:
	"""Access metadata.xml"""

	def __init__(self, metadata_xml_path, herds):
		"""Parse a valid metadata.xml file.

		@type metadata_xml_path: str
		@param metadata_xml_path: path to a valid metadata.xml file
		@type herds: str or ElementTree
		@param herds: path to a herds.xml, or a pre-parsed ElementTree
		@raise IOError: if C{metadata_xml_path} can not be read
		"""

		self.metadata_xml_path = metadata_xml_path
		self._xml_tree = None

		try:
			self._xml_tree = etree.parse(_unicode_encode(metadata_xml_path,
				encoding = _encodings['fs'], errors='strict'),
				parser = etree.XMLParser(target=_MetadataTreeBuilder()))
		except ImportError:
			pass
		except ExpatError as e:
			raise SyntaxError("%s" % (e,))

		if isinstance(herds, etree.ElementTree):
			herds_etree = herds
			herds_path = None
		else:
			herds_etree = None
			herds_path = herds

		# Used for caching
		self._herdstree = herds_etree
		self._herds_path = herds_path
		self._descriptions = None
		self._maintainers = None
		self._herds = None
		self._useflags = None
		self._upstream = None

	def __repr__(self):
		return "<%s %r>" % (self.__class__.__name__, self.metadata_xml_path)

	def _get_herd_email(self, herd):
		"""Get a herd's email address.

		@type herd: str
		@param herd: herd whose email you want
		@rtype: str or None
		@return: email address or None if herd is not in herds.xml
		@raise IOError: if $PORTDIR/metadata/herds.xml can not be read
		"""

		if self._herdstree is None:
			try:
				self._herdstree = etree.parse(_unicode_encode(self._herds_path,
					encoding=_encodings['fs'], errors='strict'),
					parser = etree.XMLParser(target=_MetadataTreeBuilder()))
			except (ImportError, IOError, SyntaxError):
				return None

		# Some special herds are not listed in herds.xml
		if herd in ('no-herd', 'maintainer-wanted', 'maintainer-needed'):
			return None

		try:
			# Python 2.7 or >=3.2
			iterate = self._herdstree.iter
		except AttributeError:
			iterate = self._herdstree.getiterator

		for node in iterate('herd'):
			if node.findtext('name') == herd:
				return node.findtext('email')

	def herds(self, include_email=False):
		"""Return a list of text nodes for <herd>.

		@type include_email: bool
		@keyword include_email: if True, also look up the herd's email
		@rtype: tuple
		@return: if include_email is False, return a list of strings;
		         if include_email is True, return a list of tuples containing:
					 [('herd1', 'herd1@gentoo.org'), ('no-herd', None);
		"""
		if self._herds is None:
			if self._xml_tree is None:
				self._herds = tuple()
			else:
				herds = []
				for elem in self._xml_tree.findall('herd'):
					text = elem.text
					if text is None:
						text = ''
					if include_email:
						herd_mail = self._get_herd_email(text)
						herds.append((text, herd_mail))
					else:
						herds.append(text)
				self._herds = tuple(herds)

		return self._herds

	def descriptions(self):
		"""Return a list of text nodes for <longdescription>.

		@rtype: list
		@return: package description in string format
		@todo: Support the C{lang} attribute
		"""
		if self._descriptions is None:
			if self._xml_tree is None:
				self._descriptions = tuple()
			else:
				self._descriptions = tuple(e.text \
					for e in self._xml_tree.findall("longdescription") if e.text)

		return self._descriptions

	def maintainers(self):
		"""Get maintainers' name, email and description.

		@rtype: list
		@return: a sequence of L{_Maintainer} objects in document order.
		"""

		if self._maintainers is None:
			if self._xml_tree is None:
				self._maintainers = tuple()
			else:
				self._maintainers = tuple(_Maintainer(node) \
					for node in self._xml_tree.findall('maintainer'))

		return self._maintainers

	def use(self):
		"""Get names and descriptions for USE flags defined in metadata.

		@rtype: list
		@return: a sequence of L{_Useflag} objects in document order.
		"""

		if self._useflags is None:
			if self._xml_tree is None:
				self._useflags = tuple()
			else:
				try:
					# Python 2.7 or >=3.2
					iterate = self._xml_tree.iter
				except AttributeError:
					iterate = self._xml_tree.getiterator
				self._useflags = tuple(_Useflag(node) \
					for node in iterate('flag'))

		return self._useflags

	def upstream(self):
		"""Get upstream contact information.

		@rtype: list
		@return: a sequence of L{_Upstream} objects in document order.
		"""

		if self._upstream is None:
			if self._xml_tree is None:
				self._upstream = tuple()
			else:
				self._upstream = tuple(_Upstream(node) \
					for node in self._xml_tree.findall('upstream'))

		return self._upstream

	def format_maintainer_string(self):
		"""Format string containing maintainers and herds (emails if possible).
		Used by emerge to display maintainer information.
		Entries are sorted according to the rules stated on the bug wranglers page.

		@rtype: String
		@return: a string containing maintainers and herds
		"""
		maintainers = []
		for maintainer in self.maintainers():
			if maintainer.email is None or not maintainer.email.strip():
				if maintainer.name and maintainer.name.strip():
					maintainers.append(maintainer.name)
			else:
				maintainers.append(maintainer.email)

		for herd, email in self.herds(include_email=True):
			if herd == "no-herd":
				continue
			if email is None or not email.strip():
				if herd and herd.strip():
					maintainers.append(herd)
			else:
				maintainers.append(email)

		maintainers = list(unique_everseen(maintainers))

		maint_str = ""
		if maintainers:
			maint_str = maintainers[0]
			maintainers = maintainers[1:]
		if maintainers:
			maint_str += " " + ",".join(maintainers)

		return maint_str

	def format_upstream_string(self):
		"""Format string containing upstream maintainers and bugtrackers.
		Used by emerge to display upstream information.

		@rtype: String
		@return: a string containing upstream maintainers and bugtrackers
		"""
		maintainers = []
		for upstream in self.upstream():
			for maintainer in upstream.maintainers:
				if maintainer.email is None or not maintainer.email.strip():
					if maintainer.name and maintainer.name.strip():
						maintainers.append(maintainer.name)
				else:
					maintainers.append(maintainer.email)

			for bugtracker in upstream.bugtrackers:
				if bugtracker.startswith("mailto:"):
					bugtracker = bugtracker[7:]
				maintainers.append(bugtracker)


		maintainers = list(unique_everseen(maintainers))
		maint_str = " ".join(maintainers)
		return maint_str

# lang with higher value is preferred
_lang_pref = {
	""  :  0,
	"en":  1,
}


def _cmp_lang(a, b):
	a_score = _lang_pref.get(a.get("lang", ""), -1)
	b_score = _lang_pref.get(b.get("lang", ""), -1)

	return a_score - b_score


def parse_metadata_use(xml_tree):
	"""
	Records are wrapped in XML as per GLEP 56
	returns a dict with keys constisting of USE flag names and values
	containing their respective descriptions
	"""
	uselist = {}

	usetags = xml_tree.findall("use")
	if not usetags:
		return uselist

	# Sort by language preference in descending order.
	usetags.sort(key=cmp_sort_key(_cmp_lang), reverse=True)

	# It's possible to have multiple 'use' elements.
	for usetag in usetags:
		flags = usetag.findall("flag")
		if not flags:
			# DTD allows use elements containing no flag elements.
			continue

		for flag in flags:
			pkg_flag = flag.get("name")
			if pkg_flag is not None:
				flag_restrict = flag.get("restrict")

				# Descriptions may exist for multiple languages, so
				# ignore all except the first description found for a
				# particular value of restrict (see bug 599060).
				try:
					uselist[pkg_flag][flag_restrict]
				except KeyError:
					pass
				else:
					continue

				# emulate the Element.itertext() method from python-2.7
				inner_text = []
				stack = []
				stack.append(flag)
				while stack:
					obj = stack.pop()
					if isinstance(obj, str):
						inner_text.append(obj)
						continue
					if isinstance(obj.text, str):
						inner_text.append(obj.text)
					if isinstance(obj.tail, str):
						stack.append(obj.tail)
					stack.extend(reversed(obj))

				if flag.get("name") not in uselist:
					uselist[flag.get("name")] = {}

				# (flag_restrict can be None)
				uselist[flag.get("name")][flag_restrict] = " ".join("".join(inner_text).split())
	return uselist
