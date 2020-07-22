# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class IndexStreamIterator:

	def __init__(self, f, parser):

		self.parser = parser
		self._file = f

	def close(self):

		if self._file is not None:
			self._file.close()
			self._file = None

	def __iter__(self):

		try:

			for line in self._file:
				node = self.parser(line)
				if node is not None:
					yield node

		finally:
			self.close()
