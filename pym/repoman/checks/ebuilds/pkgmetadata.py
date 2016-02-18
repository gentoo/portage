# -*- coding:utf-8 -*-

'''Package Metadata Checks operations'''

import sys

from itertools import chain

try:
	import xml.etree.ElementTree
	from xml.parsers.expat import ExpatError
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

from portage.exception import InvalidAtom
from portage import os
from portage import _encodings, _unicode_encode
from portage.dep import Atom

from repoman.metadata import (
	metadata_xml_encoding, metadata_doctype_name,
	metadata_dtd_uri, metadata_xml_declaration, parse_metadata_use)
from repoman.checks.herds.herdbase import get_herd_base
from repoman.checks.herds.metadata import check_metadata, UnknownHerdsError
from repoman._xml import _XMLParser, _MetadataTreeBuilder, XmlLint


class PkgMetadata(object):
	'''Package metadata.xml checks'''

	def __init__(self, options, qatracker, repoman_settings, metadata_dtd=None):
		'''PkgMetadata init function

		@param options: ArgumentParser.parse_known_args(argv[1:]) options
		@param qatracker: QATracker instance
		@param repoman_settings: settings instance
		@param metadata_dtd: path of metadata.dtd
		'''
		self.options = options
		self.qatracker = qatracker
		self.repoman_settings = repoman_settings
		self.musedict = {}
		self.xmllint = XmlLint(self.options, self.repoman_settings,
			metadata_dtd=metadata_dtd)

	def check(self, xpkg, checkdir, checkdirlist, repolevel):
		'''Performs the checks on the metadata.xml for the package

		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdirlist: list of checkdir's
		@param repolevel: integer
		'''

		self.musedict = {}
		# metadata.xml file check
		if "metadata.xml" not in checkdirlist:
			self.qatracker.add_error("metadata.missing", xpkg + "/metadata.xml")
		# metadata.xml parse check
		else:
			metadata_bad = False
			xml_info = {}
			xml_parser = _XMLParser(xml_info, target=_MetadataTreeBuilder())

			# read metadata.xml into memory
			try:
				_metadata_xml = xml.etree.ElementTree.parse(
					_unicode_encode(
						os.path.join(checkdir, "metadata.xml"),
						encoding=_encodings['fs'], errors='strict'),
					parser=xml_parser)
			except (ExpatError, SyntaxError, EnvironmentError) as e:
				metadata_bad = True
				self.qatracker.add_error("metadata.bad", "%s/metadata.xml: %s" % (xpkg, e))
				del e
			else:
				if not hasattr(xml_parser, 'parser') or \
					sys.hexversion < 0x2070000 or \
					(sys.hexversion > 0x3000000 and sys.hexversion < 0x3020000):
					# doctype is not parsed with python 2.6 or 3.1
					pass
				else:
					if "XML_DECLARATION" not in xml_info:
						self.qatracker.add_error(
							"metadata.bad", "%s/metadata.xml: "
							"xml declaration is missing on first line, "
							"should be '%s'" % (xpkg, metadata_xml_declaration))
					else:
						xml_version, xml_encoding, xml_standalone = \
							xml_info["XML_DECLARATION"]
						if xml_encoding is None or \
							xml_encoding.upper() != metadata_xml_encoding:
							if xml_encoding is None:
								encoding_problem = "but it is undefined"
							else:
								encoding_problem = "not '%s'" % xml_encoding
							self.qatracker.add_error(
								"metadata.bad", "%s/metadata.xml: "
								"xml declaration encoding should be '%s', %s" %
								(xpkg, metadata_xml_encoding, encoding_problem))

					if "DOCTYPE" not in xml_info:
						metadata_bad = True
						self.qatracker.add_error(
							"metadata.bad",
							"%s/metadata.xml: %s" % (xpkg, "DOCTYPE is missing"))
					else:
						doctype_name, doctype_system, doctype_pubid = \
							xml_info["DOCTYPE"]
						if doctype_system != metadata_dtd_uri:
							if doctype_system is None:
								system_problem = "but it is undefined"
							else:
								system_problem = "not '%s'" % doctype_system
							self.qatracker.add_error(
								"metadata.bad", "%s/metadata.xml: "
								"DOCTYPE: SYSTEM should refer to '%s', %s" %
								(xpkg, metadata_dtd_uri, system_problem))

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
		return
