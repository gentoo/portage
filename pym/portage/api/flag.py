#!/usr/bin/python
#
# Copyright(c) 2010, Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#


"""Provides support functions for USE flag settings and analysis"""


__all__ = (
	'get_iuse',
	'get_installed_use',
	'reduce_flag',
	'reduce_flags',
	'filter_flags',
	'get_all_cpv_use',
	'get_flags'
)


import sys

from portage.api.settings import settings

import portage


def get_iuse(cpv, root=settings.settings["ROOT"]):
	"""Gets the current IUSE flags from the tree

	To be used when a gentoolkit package object is not needed
	@type: cpv: string
	@param cpv: cat/pkg-ver
	@rtype list
	@returns [] or the list of IUSE flags
	"""
	try:
		return settings.portdb[root].aux_get(cpv, ["IUSE"])[0].split()
	except:
		return []


def get_installed_use(cpv, use="USE", root=settings.settings["ROOT"]):
	"""Gets the installed USE flags from the VARDB

	To be used when a gentoolkit package object is not needed
	@type: cpv: string
	@param cpv: cat/pkg-ver
	@type use: string
	@param use: 1 of ["USE", "PKGUSE"]
	@rtype list
	@returns [] or the list of IUSE flags
	"""
	return settings.vardb[root].aux_get(cpv,[use])[0].split()


def reduce_flag(flag):
	"""Absolute value function for a USE flag

	@type flag: string
	@param flag: the use flag to absolute.
	@rtype: string
	@return absolute USE flag
	"""
	if flag[0] in ["+","-"]:
		return flag[1:]
	else:
		return flag


def reduce_flags(the_list):
	"""Absolute value function for a USE flag list

	@type the_list: list
	@param the_list: the use flags to absolute.
	@rtype: list
	@return absolute USE flags
	"""
	r=[]
	for member in the_list:
		r.append(reduce_flag(member))
	return r


def filter_flags(use, use_expand_hidden, usemasked, useforced):
	"""Filter function to remove hidden or otherwise not normally
	visible USE flags from a list.

	@type use: list
	@param use: the USE flag list to be filtered.
	@type use_expand_hidden: list
	@param  use_expand_hidden: list of flags hidden.
	@type usemasked: list
	@param usemasked: list of masked USE flags.
	@type useforced: list
	@param useforced: the forced USE flags.
	@rtype: list
	@return the filtered USE flags.
	"""
	# clean out some environment flags, since they will most probably
	# be confusing for the user
	for f in use_expand_hidden:
		f=f.lower() + "_"
		for x in use:
			if f in x:
				use.remove(x)
	# clean out any arch's
	archlist = settings.settings["PORTAGE_ARCHLIST"].split()
	for a in use[:]:
		if a in archlist:
			use.remove(a)
	# dbl check if any from usemasked  or useforced are still there
	masked = usemasked + useforced
	for a in use[:]:
		if a in masked:
			use.remove(a)
	return use


def get_all_cpv_use(cpv, root=settings.settings["ROOT"]):
	"""Uses portage to determine final USE flags and settings for an emerge

	@type cpv: string
	@param cpv: eg cat/pkg-ver
	@rtype: lists
	@return  use, use_expand_hidden, usemask, useforce
	"""
	use = None
	settings.portdb[root].settings.unlock()
	try:
		settings.portdb[root].settings.setcpv(cpv, use_cache=True, mydb=settings.portdb[root])
		use = settings.settings['PORTAGE_USE'].split()
		use_expand_hidden = settings.settings["USE_EXPAND_HIDDEN"].split()
		usemask = list(settings.portdb[root].settings.usemask)
		useforce =  list(settings.portdb[root].settings.useforce)
	except KeyError:
		settings.portdb[root].settings.reset()
		settings.portdb[root].settings.lock()
		return [], [], [], []
	# reset cpv filter
	settings.portdb[root].settings.reset()
	settings.portdb[root].settings.lock()
	return use, use_expand_hidden, usemask, useforce


def get_flags(cpv, final_setting=False, root=settings.settings["ROOT"]):
	"""Retrieves all information needed to filter out hidden, masked, etc.
	USE flags for a given package.

	@type cpv: string
	@param cpv: eg. cat/pkg-ver
	@type final_setting: boolean
	@param final_setting: used to also determine the final
		enviroment USE flag settings and return them as well.
	@rtype: list or list, list
	@return IUSE or IUSE, final_flags
	"""
	final_use, use_expand_hidden, usemasked, useforced = get_all_cpv_use(cpv, root)
	iuse_flags = filter_flags(get_iuse(cpv), use_expand_hidden, usemasked, useforced)
	#flags = filter_flags(use_flags, use_expand_hidden, usemasked, useforced)
	if final_setting:
		final_flags = filter_flags(final_use,  use_expand_hidden, usemasked, useforced)
		return iuse_flags, final_flags
	return iuse_flags


def get_use_flag_dict(portdir):
	""" Get all the use flags and return them as a dictionary
	
	@param portdir: the path to the repository
	@rtype dictionary of:
		key = use flag forced to lowercase
		data = list[0] = 'local' or 'global'
			   list[1] = 'package-name'
			   list[2] = description of flag
	"""
	use_dict = {}

	# process standard use flags

	List = portage.grabfile(portdir + '/profiles/use.desc')
	for item in List:
		index = item.find(' - ')
		use_dict[item[:index].strip().lower()] = ['global', '', item[index+3:]]

	# process local (package specific) use flags

	List = portage.grabfile(portdir + '/profiles/use.local.desc')
	for item in List:
		index = item.find(' - ')
		data = item[:index].lower().split(':')
		try: # got an error once starting porthole==> added code to catch it, but it works again???
			use_dict[data[1].strip()] = ['local', data[0].strip(), item[index+3:]]
		except:
			pass
			#debug.dprint("FLAG: get_use_flag_dict(); error in index??? data[0].strip, item[index:]")
			#debug.dprint(data[0].strip())
			#debug.dprint(item[index:])
	return use_dict
