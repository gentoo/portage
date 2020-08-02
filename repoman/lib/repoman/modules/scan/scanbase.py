# -*- coding:utf-8 -*-


class ScanBase:
	'''Skeleton class for performing a scan for one or more items
	to check in a pkg directory or ebuild.'''

	def __init__(self, **kwargs):
		'''Class init

		@param kwargs: an optional dictionary of common repository
						wide parameters that may be required.
		'''
		# Since no two checks are identicle as to what kwargs are needed,
		# this does not define any from it here.
		super(ScanBase, self).__init__()

	""" # sample check
	def check_foo(self, **kwargs):
		'''Class check skeleton function. Define this for a
		specific check to perform.

		@param kwargs: an optional dictionary of dynamic package and or ebuild
						specific data that may be required.  Dynamic data can
						vary depending what checks have run before it.
						So execution order can be important.
		'''
		# Insert the code for the check here
		# It should return a dictionary of at least {'continue': False}
		# The continue attribute will default to False if not returned.
		# This will allow the loop to continue with the next check in the list.
		# Include any additional dynamic data that needs to be added or updated.
		return False  # used as a continue True/False value
	"""

	@property
	def runInPkgs(self):
		'''Package level scans'''
		# default no run (False) and empty list of functions to run
		# override this method to define a function or
		# functions to run in this process loop
		# return a tuple of a boolean or boolean result and an ordered list
		# of functions to run.  ie: return (True, [self.check_foo])
		# in this way, it can be dynamically determined at run time, if
		# later stage scans are to be run.
		# This class instance is maintaned for all stages, so data can be
		# carried over from stage to stage
		# next stage is runInEbuilds
		return (False, [])

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		# default empty list of functions to run
		# override this method to define a function or
		# functions to run in this process loop
		# return a tuple of a boolean or boolean result and an ordered list
		# of functions to run.  ie: return (True, [self.check_bar])
		# in this way, it can be dynamically determined at run time, if
		# later stage scans are to be run.
		# This class instance is maintaned for all stages, so data can be
		# carried over from stage to stage
		# next stage is runInFinal
		return (False, [])

	@property
	def runInFinal(self):
		'''Final scans at the package level'''
		# default empty list of functions to run
		# override this method to define a function or
		# functions to run in this process loop
		# return a tuple of a boolean or boolean result and an ordered list
		# of functions to run.  ie: return (True, [self.check_baz])
		# in this way, it can be dynamically determined at run time, if
		# later stage scans are to be run.
		# This class instance is maintaned for all stages, so data can be
		# carried over from stage to stage
		# runInFinal is currently the last stage of scans performed.
		return (False, [])
