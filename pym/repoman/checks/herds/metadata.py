

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
