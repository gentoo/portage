# -*- coding:utf-8 -*-

'''Package Metadata Checks operations'''

import sys

from itertools import chain

try:
	from lxml import etree
	from lxml.etree import ParserError
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# http://bugs.python.org/issue14988
	msg = ["Please emerge dev-python/lxml in order to use repoman."]
	from portage.output import EOutput
	out = EOutput()
	for line in msg:
		out.eerror(line)
	sys.exit(1)

# import our initialized portage instance
from repoman._portage import portage
from repoman.metadata import metadata_dtd_uri
from repoman.checks.herds.herdbase import get_herd_base
from repoman.checks.herds.metadata import check_metadata, UnknownHerdsError
from repoman._xml import XmlLint
from repoman.modules.scan.scanbase import ScanBase

from portage.exception import InvalidAtom
from portage import os
from portage import exception
from portage.dep import Atom

from .use_flags import USEFlagChecks

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	basestring = str

metadata_xml_encoding = 'UTF-8'
metadata_xml_declaration = '<?xml version="1.0" encoding="%s"?>' \
	% (metadata_xml_encoding,)
metadata_doctype_name = 'pkgmetadata'


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


class PkgMetadata(ScanBase, USEFlagChecks):
	'''Package metadata.xml checks'''

	def __init__(self, **kwargs):
		'''PkgMetadata init function

		@param repo_settings: settings instance
		@param qatracker: QATracker instance
		@param options: argparse options instance
		@param metadata_xsd: path of metadata.xsd
		'''
		super(PkgMetadata, self).__init__(**kwargs)
		repo_settings = kwargs.get('repo_settings')
		self.qatracker = kwargs.get('qatracker')
		self.options = kwargs.get('options')
		metadata_xsd = kwargs.get('metadata_xsd')
		self.globalUseFlags = kwargs.get('uselist')
		self.repoman_settings = repo_settings.repoman_settings
		self.musedict = {}
		self.muselist = set()
		self.xmllint = XmlLint(self.options, self.repoman_settings,
			metadata_xsd=metadata_xsd)

	def check(self, **kwargs):
		'''Performs the checks on the metadata.xml for the package
		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdirlist: list of checkdir's
		@param repolevel: integer
		@returns: boolean
		'''
		xpkg = kwargs.get('xpkg')
		checkdir = kwargs.get('checkdir')
		checkdirlist = kwargs.get('checkdirlist').get()
		repolevel = kwargs.get('repolevel')

		self.musedict = {}
		if self.options.mode in ['manifest']:
			self.muselist = frozenset(self.musedict)
			return False

		# metadata.xml file check
		if "metadata.xml" not in checkdirlist:
			self.qatracker.add_error("metadata.missing", xpkg + "/metadata.xml")
			self.muselist = frozenset(self.musedict)
			return False

		# metadata.xml parse check
		metadata_bad = False

		# read metadata.xml into memory
		try:
			_metadata_xml = etree.parse(os.path.join(checkdir, 'metadata.xml'))
		except (ParserError, SyntaxError, EnvironmentError) as e:
			metadata_bad = True
			self.qatracker.add_error("metadata.bad", "%s/metadata.xml: %s" % (xpkg, e))
			del e
			self.muselist = frozenset(self.musedict)
			return False

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
		self.muselist = frozenset(self.musedict)
		return False

	def check_unused(self, **kwargs):
		'''Reports on any unused metadata.xml use descriptions

		@param xpkg: the pacakge being checked
		@param used_useflags: use flag list
		@param validity_future: Future instance
		'''
		xpkg = kwargs.get('xpkg')
		valid_state = kwargs.get('validity_future').get()
		# check if there are unused local USE-descriptions in metadata.xml
		# (unless there are any invalids, to avoid noise)
		if valid_state:
			for myflag in self.muselist.difference(self.usedUseFlags):
				self.qatracker.add_error(
					"metadata.warning",
					"%s/metadata.xml: unused local USE-description: '%s'"
					% (xpkg, myflag))
		return False

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])

	@property
	def runInEbuilds(self):
		return (True, [self.check_useflags])

	@property
	def runInFinal(self):
		'''Final scans at the package level'''
		return (True, [self.check_unused])
