# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class SlotObject(object):
	__slots__ = ("__weakref__",)

	def __init__(self, **kwargs):
		classes = [self.__class__]
		while classes:
			c = classes.pop()
			if c is SlotObject:
				continue
			classes.extend(c.__bases__)
			slots = getattr(c, "__slots__", None)
			if not slots:
				continue
			for myattr in slots:
				myvalue = kwargs.get(myattr, None)
				setattr(self, myattr, myvalue)

	def copy(self):
		"""
		Create a new instance and copy all attributes
		defined from __slots__ (including those from
		inherited classes).
		"""
		obj = self.__class__()

		classes = [self.__class__]
		while classes:
			c = classes.pop()
			if c is SlotObject:
				continue
			classes.extend(c.__bases__)
			slots = getattr(c, "__slots__", None)
			if not slots:
				continue
			for myattr in slots:
				setattr(obj, myattr, getattr(self, myattr))

		return obj

