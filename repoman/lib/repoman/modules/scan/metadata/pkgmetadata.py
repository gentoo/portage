# -*- coding:utf-8 -*-

'''Package Metadata Checks operations'''

import sys
import re

from itertools import chain
from collections import Counter

try:
	from lxml import etree
	from lxml.etree import ParserError
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# https://bugs.python.org/issue14988
	msg = ["Please emerge dev-python/lxml in order to use repoman."]
	from portage.output import EOutput
	out = EOutput()
	for line in msg:
		out.eerror(line)
	sys.exit(1)

# import our initialized portage instance
from repoman._portage import portage # pylint: disable=unused-import
from repoman.metadata import metadata_dtd_uri
from repoman.modules.scan.scanbase import ScanBase

# pylint: disable=ungrouped-imports
from portage.exception import InvalidAtom
from portage import os
from portage.dep import Atom
from portage.xml.metadata import parse_metadata_use

from .use_flags import USEFlagChecks

metadata_xml_encoding = 'UTF-8'
metadata_xml_declaration = '<?xml version="1.0" encoding="%s"?>' \
	% (metadata_xml_encoding,)
metadata_doctype_name = 'pkgmetadata'


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
		self.metadata_xsd = kwargs.get('metadata_xsd')
		self.globalUseFlags = kwargs.get('uselist')
		self.repoman_settings = repo_settings.repoman_settings
		self.musedict = {}
		self.muselist = set()

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

		indentation_chars = Counter()
		for l in etree.tostring(_metadata_xml).splitlines():
			indentation_chars.update(re.match(rb"\s*", l).group(0))
		if len(indentation_chars) > 1:
			self.qatracker.add_error("metadata.warning", "%s/metadata.xml: %s" %
				(xpkg, "inconsistent use of tabs and spaces in indentation")
			)

		xml_encoding = _metadata_xml.docinfo.encoding
		if xml_encoding.upper() != metadata_xml_encoding:
			self.qatracker.add_error(
				"metadata.bad", "%s/metadata.xml: "
				"xml declaration encoding should be '%s', not '%s'" %
				(xpkg, metadata_xml_encoding, xml_encoding))

		if not _metadata_xml.docinfo.doctype:
			metadata_bad = True
			self.qatracker.add_error(
				"metadata.bad",
				"%s/metadata.xml: %s" % (xpkg, "DOCTYPE is missing"))
		else:
			doctype_system = _metadata_xml.docinfo.system_url
			if doctype_system.replace('http://', 'https://') != metadata_dtd_uri:
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
		self.musedict = parse_metadata_use(_metadata_xml)
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

		# Only carry out if in package directory or check forced
		if not metadata_bad:
			validator = etree.XMLSchema(file=self.metadata_xsd)
			if not validator.validate(_metadata_xml):
				self._add_validate_errors(xpkg, validator.error_log)
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
					"metadata.bad",
					"%s/metadata.xml: unused local USE-description: '%s'"
					% (xpkg, myflag))
		return False

	def _add_validate_errors(self, xpkg, log):
		listed = set()
		for error in log:
			msg_prefix = error.message.split(":",1)[0]
			info = "%s %s" % (error.line, msg_prefix)
			if info not in listed:
				listed.add(info)
				self.qatracker.add_error(
					"metadata.bad",
					"%s/metadata.xml: line: %s, %s"
					% (xpkg, error.line, error.message))

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
