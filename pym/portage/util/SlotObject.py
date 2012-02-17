# Copyright 1999-2012 Gentoo Foundation
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
				myvalue = kwargs.pop(myattr, None)
				if myvalue is None and getattr(self, myattr, None) is not None:
					raise AssertionError(
						"class '%s' duplicates '%s' value in __slots__ of base class '%s'" %
						(self.__class__.__name__, myattr, c.__name__))
				setattr(self, myattr, myvalue)

		if kwargs:
			raise TypeError(
				"'%s' is an invalid keyword argument for this constructor" %
				(next(iter(kwargs)),))

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

