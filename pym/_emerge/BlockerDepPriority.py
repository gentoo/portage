from _emerge.DepPriority import DepPriority
class BlockerDepPriority(DepPriority):
	__slots__ = ()
	def __int__(self):
		return 0

	def __str__(self):
		return 'blocker'

BlockerDepPriority.instance = BlockerDepPriority()
