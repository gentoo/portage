# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
class DepPriorityNormalRange:
	"""
	DepPriority properties              Index      Category

	buildtime                                      HARD
	runtime                                3       MEDIUM
	runtime_post                           2       MEDIUM_SOFT
	optional                               1       SOFT
	(none of the above)                    0       NONE
	"""
	MEDIUM      = 3
	MEDIUM_SOFT = 2
	MEDIUM_POST = 2
	SOFT        = 1
	NONE        = 0

	@classmethod
	def _ignore_optional(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.optional)

	@classmethod
	def _ignore_runtime_post(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.optional or priority.runtime_post)

	@classmethod
	def _ignore_runtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.optional or not priority.buildtime)

	ignore_medium      = _ignore_runtime
	ignore_medium_soft = _ignore_runtime_post
	ignore_medium_post = _ignore_runtime_post
	ignore_soft        = _ignore_optional

DepPriorityNormalRange.ignore_priority = (
	None,
	DepPriorityNormalRange._ignore_optional,
	DepPriorityNormalRange._ignore_runtime_post,
	DepPriorityNormalRange._ignore_runtime
)
