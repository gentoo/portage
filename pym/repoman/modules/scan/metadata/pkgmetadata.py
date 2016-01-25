# -*- coding:utf-8 -*-

'''Package Metadata Checks operations'''

import sys

from itertools import chain

try:
	from lxml import etree
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# http://bugs.python.org/issue14988
	msg = ["Please enable python's \"xml\" USE flag in order to use repoman."]
	from portage.output import EOutput
	out = EOutput()
	for line in msg:
		out.eerror(line)
	sys.exit(1)

# import our initialized portage instance
from repoman._portage import portage
from repoman.metadata import metadata_dtd_uri
from repoman.checks.herds.herdbase import get_herd_base
from repoman._xml import _XMLParser, _MetadataTreeBuilder, XmlLint
from repoman.modules.scan.scanbase import ScanBase

from portage.exception import InvalidAtom
from portage import os
from portage import _encodings, _unicode_encode
from portage.dep import Atom


metadata_xml_encoding = 'UTF-8'
metadata_xml_declaration = '<?xml version="1.0" encoding="%s"?>' \
	% (metadata_xml_encoding,)
metadata_doctype_name = 'pkgmetadata'


class UnknownHerdsError(ValueError):
	def __init__(self, herd_names):
		_plural = len(herd_names) != 1
		super(UnknownHerdsError, self).__init__(
			'Unknown %s %s' % (
				_plural and 'herds' or 'herd',
				','.join('"%s"' % e for e in herd_names)))


def check_metadata_herds(xml_tree, herd_base):
	herd_nodes = xml_tree.findall('herd')
	unknown_herds = [
		name for name in (
			e.text.strip() for e in herd_nodes if e.text is not None)
		if not herd_base.known_herd(name)]

	if unknown_herds:
		raise UnknownHerdsError(unknown_herds)


def check_metadata(xml_tree, herd_base):
	if herd_base is not None:
		check_metadata_herds(xml_tree, herd_base)


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

	# It's possible to have multiple 'use' elements.
	for usetag in usetags:
		flags = usetag.findall("flag")
		if not flags:
			# DTD allows use elements containing no flag elements.
			continue

		for flag in flags:
			pkg_flag = flag.get("name")
			if pkg_flag is None:
				raise exception.ParseError("missing 'name' attribute for 'flag' tag")
			flag_restrict = flag.get("restrict")

			# emulate the Element.itertext() method from python-2.7
			inner_text = []
			stack = []
			stack.append(flag)
			while stack:
				obj = stack.pop()
				if isinstance(obj, basestring):
					inner_text.append(obj)
					continue
				if isinstance(obj.text, basestring):
					inner_text.append(obj.text)
				if isinstance(obj.tail, basestring):
					stack.append(obj.tail)
				stack.extend(reversed(obj))

			if pkg_flag not in uselist:
				uselist[pkg_flag] = {}

			# (flag_restrict can be None)
			uselist[pkg_flag][flag_restrict] = " ".join("".join(inner_text).split())

	return uselist


class PkgMetadata(ScanBase):
	'''Package metadata.xml checks'''

	def __init__(self, **kwargs):
		'''PkgMetadata init function

		@param repo_settings: settings instance
		@param qatracker: QATracker instance
		@param options: argparse options instance
		@param metadata_dtd: path of metadata.dtd
		'''
		super(PkgMetadata, self).__init__(**kwargs)
		repo_settings = kwargs.get('repo_settings')
		self.qatracker = kwargs.get('qatracker')
		self.options = kwargs.get('options')
		metadata_dtd = kwargs.get('metadata_dtd')
		self.repoman_settings = repo_settings.repoman_settings
		self.musedict = {}
		self.xmllint = XmlLint(self.options, self.repoman_settings,
			metadata_dtd=metadata_dtd)

	def check(self, **kwargs):
		'''Performs the checks on the metadata.xml for the package
		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdirlist: list of checkdir's
		@param repolevel: integer
		'''
		xpkg = kwargs.get('xpkg')
		checkdir = kwargs.get('checkdir')
		checkdirlist = kwargs.get('checkdirlist')
		repolevel = kwargs.get('repolevel')

		self.musedict = {}
		if self.options.mode in ['manifest']:
			return {'continue': False, 'muselist': frozenset(self.musedict)}

		# metadata.xml file check
		if "metadata.xml" not in checkdirlist:
			self.qatracker.add_error("metadata.missing", xpkg + "/metadata.xml")
			return {'continue': False, 'muselist': frozenset(self.musedict)}

		# metadata.xml parse check
		metadata_bad = False

		# read metadata.xml into memory
		try:
			_metadata_xml = etree.parse(os.path.join(checkdir, 'metadata.xml'))
		except (ExpatError, SyntaxError, EnvironmentError) as e:
			metadata_bad = True
			self.qatracker.add_error("metadata.bad", "%s/metadata.xml: %s" % (xpkg, e))
			del e
			return {'continue': False, 'muselist': frozenset(self.musedict)}

        xml_encoding = _metadata_xml.docinfo.encoding
		if xml_encoding.upper() != metadata_xml_encoding:
			self.qatracker.add_error(
				"metadata.bad", "%s/metadata.xml: "
				"xml declaration encoding should be '%s', not '%s'" %
				(xpkg, metadata_xml_encoding, xml_encoding))

		if not _metadata_xml.docinfo:
			metadata_bad = True
			self.qatracker.add_error(
				"metadata.bad",
				"%s/metadata.xml: %s" % (xpkg, "DOCTYPE is missing"))
		else:
			doctype_system = _metadata_xml.docinfo.system_url
			if doctype_system != metadata_dtd_uri:
				if doctype_system is None:
					system_problem = "but it is undefined"
				else:
					system_problem = "not '%s'" % doctype_system
				self.qatracker.add_error(
					"metadata.bad", "%s/metadata.xml: "
					"DOCTYPE: SYSTEM should refer to '%s', %s" %
					(xpkg, metadata_dtd_uri, system_problem))
			doctype_name = _metadata_xml.docinfo.doctype.split(' ')[1]
			if doctype_name != metadata_doctype_name:
				self.qatracker.add_error(
					"metadata.bad", "%s/metadata.xml: "
					"DOCTYPE: name should be '%s', not '%s'" %
					(xpkg, metadata_doctype_name, doctype_name))

		# load USE flags from metadata.xml
		try:
			self.musedict = parse_metadata_use(_metadata_xml)
		except portage.exception.ParseError as e:
			metadata_bad = True
			self.qatracker.add_error(
				"metadata.bad", "%s/metadata.xml: %s" % (xpkg, e))
		else:
			for atom in chain(*self.musedict.values()):
				if atom is None:
					continue
				try:
					atom = Atom(atom)
				except InvalidAtom as e:
					self.qatracker.add_error(
						"metadata.bad",
						"%s/metadata.xml: Invalid atom: %s" % (xpkg, e))
				else:
					if atom.cp != xpkg:
						self.qatracker.add_error(
							"metadata.bad",
							"%s/metadata.xml: Atom contains "
							"unexpected cat/pn: %s" % (xpkg, atom))

		# Run other metadata.xml checkers
		try:
			check_metadata(_metadata_xml, get_herd_base(
				self.repoman_settings))
		except (UnknownHerdsError, ) as e:
			metadata_bad = True
			self.qatracker.add_error(
				"metadata.bad", "%s/metadata.xml: %s" % (xpkg, e))
			del e

		# Only carry out if in package directory or check forced
		if not metadata_bad:
			if not self.xmllint.check(checkdir, repolevel):
				self.qatracker.add_error("metadata.bad", xpkg + "/metadata.xml")
		del metadata_bad
		return {'continue': False, 'muselist': frozenset(self.musedict)}

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])
