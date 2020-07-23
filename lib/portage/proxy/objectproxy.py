# Copyright 2008-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


__all__ = ['ObjectProxy']

class ObjectProxy:

	"""
	Object that acts as a proxy to another object, forwarding
	attribute accesses and method calls. This can be useful
	for implementing lazy initialization.
	"""

	__slots__ = ()

	def _get_target(self):
		raise NotImplementedError(self)

	def __getattribute__(self, attr):
		result = object.__getattribute__(self, '_get_target')()
		return getattr(result, attr)

	def __setattr__(self, attr, value):
		result = object.__getattribute__(self, '_get_target')()
		setattr(result, attr, value)

	def __call__(self, *args, **kwargs):
		result = object.__getattribute__(self, '_get_target')()
		return result(*args, **kwargs)

	def __enter__(self):
		return object.__getattribute__(self, '_get_target')().__enter__()

	def __exit__(self, exc_type, exc_value, traceback):
		return object.__getattribute__(self, '_get_target')().__exit__(
			exc_type, exc_value, traceback)

	def __setitem__(self, key, value):
		object.__getattribute__(self, '_get_target')()[key] = value

	def __getitem__(self, key):
		return object.__getattribute__(self, '_get_target')()[key]

	def __delitem__(self, key):
		del object.__getattribute__(self, '_get_target')()[key]

	def __contains__(self, key):
		return key in object.__getattribute__(self, '_get_target')()

	def __iter__(self):
		return iter(object.__getattribute__(self, '_get_target')())

	def __len__(self):
		return len(object.__getattribute__(self, '_get_target')())

	def __repr__(self):
		return repr(object.__getattribute__(self, '_get_target')())

	def __str__(self):
		return str(object.__getattribute__(self, '_get_target')())

	def __add__(self, other):
		return self.__str__() + other

	def __hash__(self):
		return hash(object.__getattribute__(self, '_get_target')())

	def __ge__(self, other):
		return object.__getattribute__(self, '_get_target')() >= other

	def __gt__(self, other):
		return object.__getattribute__(self, '_get_target')() > other

	def __le__(self, other):
		return object.__getattribute__(self, '_get_target')() <= other

	def __lt__(self, other):
		return object.__getattribute__(self, '_get_target')() < other

	def __eq__(self, other):
		return object.__getattribute__(self, '_get_target')() == other

	def __ne__(self, other):
		return object.__getattribute__(self, '_get_target')() != other

	def __bool__(self):
		return bool(object.__getattribute__(self, '_get_target')())

	def __int__(self):
		return int(object.__getattribute__(self, '_get_target')())
