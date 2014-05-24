
import xml


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
