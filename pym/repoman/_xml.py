# -*- coding:utf-8 -*-

from __future__ import print_function, unicode_literals

import sys
import xml

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage.output import red
from portage.process import find_binary

from repoman.metadata import fetch_metadata_xsd
from repoman._subprocess import repoman_getstatusoutput


class _XMLParser(xml.etree.ElementTree.XMLParser):

	def __init__(self, data, **kwargs):
		xml.etree.ElementTree.XMLParser.__init__(self, **kwargs)
		self._portage_data = data
		if hasattr(self, 'parser'):
			self._base_XmlDeclHandler = self.parser.XmlDeclHandler
			self.parser.XmlDeclHandler = self._portage_XmlDeclHandler
			self._base_StartDoctypeDeclHandler = \
				self.parser.StartDoctypeDeclHandler
			self.parser.StartDoctypeDeclHandler = \
				self._portage_StartDoctypeDeclHandler

	def _portage_XmlDeclHandler(self, version, encoding, standalone):
		if self._base_XmlDeclHandler is not None:
			self._base_XmlDeclHandler(version, encoding, standalone)
		self._portage_data["XML_DECLARATION"] = (version, encoding, standalone)

	def _portage_StartDoctypeDeclHandler(
		self, doctypeName, systemId, publicId, has_internal_subset):
		if self._base_StartDoctypeDeclHandler is not None:
			self._base_StartDoctypeDeclHandler(
				doctypeName, systemId, publicId, has_internal_subset)
		self._portage_data["DOCTYPE"] = (doctypeName, systemId, publicId)


class _MetadataTreeBuilder(xml.etree.ElementTree.TreeBuilder):
	"""
	Implements doctype() as required to avoid deprecation warnings with
	>=python-2.7.
	"""
	def doctype(self, name, pubid, system):
		pass


class XmlLint(object):

	def __init__(self, options, repoman_settings, metadata_xsd=None):
		self.metadata_xsd = (metadata_xsd or
			os.path.join(repoman_settings["DISTDIR"], 'metadata.xsd'))
		self.options = options
		self.repoman_settings = repoman_settings
		self._is_capable = metadata_xsd is not None
		self.binary = None
		self._check_capable()

	def _check_capable(self):
		if self.options.mode == "manifest":
			return
		self.binary = find_binary('xmllint')
		if not self.binary:
			print(red("!!! xmllint not found. Can't check metadata.xml.\n"))
		elif not self._is_capable:
			if not fetch_metadata_xsd(self.metadata_xsd, self.repoman_settings):
				sys.exit(1)
			# this can be problematic if xmllint changes their output
			self._is_capable = True

	@property
	def capable(self):
		return self._is_capable

	def check(self, checkdir, repolevel):
		'''Runs checks on the package metadata.xml file

		@param checkdir: string, path
		@param repolevel: integer
		@return boolean, False == bad metadata
		'''
		if not self.capable:
			if self.options.xml_parse or repolevel == 3:
				print("%s sorry, xmllint is needed.  failing\n" % red("!!!"))
				sys.exit(1)
			return True
		# xmlint can produce garbage output even on success, so only dump
		# the ouput when it fails.
		st, out = repoman_getstatusoutput(
			self.binary + " --nonet --noout --schema %s %s" % (
				portage._shell_quote(self.metadata_xsd),
				portage._shell_quote(
					os.path.join(checkdir, "metadata.xml"))))
		if st != os.EX_OK:
			print(red("!!!") + " metadata.xml is invalid:")
			for z in out.splitlines():
				print(red("!!! ") + z)
			return False
		return True
