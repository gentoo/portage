
'''
fuse.py

A tiny one-time-fuse class that uses a boolean to mimic the property of
an electrical fuse.  IT's good (True) until it is popped (bad, False).
It is not resetable.
'''


class Fuse(object):
	'''A One time fuse style boolean instance'''

	__slots__ = ('_state')

	def __init__(self):
		self._state = True

	def pop(self):
		'''Blow's the fuse state (makes it False)'''
		self._state = False

	def __repr__(self):
		'''x.__repr__() <==> repr(x)'''
		return repr(self._state>0)

	def __str__(self):
		'''x.__str__() <==> str(x)'''
		return ['False', 'True'][self._state]

	def __bool__(self):
		'''self != 0'''
		return self._state != 0

	def __nonzero__(self):
		'''self != 0'''
		return self._state != 0

	def __abs__(self):
		'''x.__abs__() <==> abs(x)'''
		return [0, 1] [self._state]

	def __int__(self):
		'''int(self)'''
		return [0, 1][self._state]

	def __eq__(self, value):
		'''Return self==value.'''
		return self._state == value

	def __ne__(self, value):
		'''Return self!=value.'''
		return self._state != value

	def __ge__(self, value):
		'''Return self>=value.'''
		return self._state >= value

	def __gt__(self, value):
		return self._state > value

	def __le__(self, value):
		'''Return self<=value.'''
		return self._state <= value

	def __lt__(self, value):
		'''Return self<value.'''
		return self._state < value
