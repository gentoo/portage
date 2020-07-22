# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class DummyTree:
	"""
	Most internal code only accesses the "dbapi" attribute of the
	binarytree, portagetree, and vartree classes. DummyTree is useful
	in cases where alternative dbapi implementations (or wrappers that
	modify or extend behavior of existing dbapi implementations) are
	needed, since it allows these implementations to be exposed through
	an interface which is minimally compatible with the *tree classes.
	"""
	__slots__ = ("dbapi",)

	def __init__(self, dbapi):
		self.dbapi = dbapi
