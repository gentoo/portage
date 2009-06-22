from _emerge.SlotObject import SlotObject
class AbstractDepPriority(SlotObject):
	__slots__ = ("buildtime", "runtime", "runtime_post")

	def __lt__(self, other):
		return self.__int__() < other

	def __le__(self, other):
		return self.__int__() <= other

	def __eq__(self, other):
		return self.__int__() == other

	def __ne__(self, other):
		return self.__int__() != other

	def __gt__(self, other):
		return self.__int__() > other

	def __ge__(self, other):
		return self.__int__() >= other

	def copy(self):
		import copy
		return copy.copy(self)

