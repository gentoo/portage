#!/usr/bin/python
#
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Portage API data connection for consumer apps.  """

import os.path

import portage
from portage import pkgsplit
from portage.api.settings import settings
from portage.dep import Atom
from portage import manifest
from portage.api.flag import get_flags
from portage.api.properties import Properties

# debug printing
# use portage.util.writemsg_level(), with level=logging.DEBUG

def xmatch(*args, **kwargs):
	"""Pass arguments on to portage's caching match function.
	xmatch('match-all',package-name) returns all ebuilds of <package-name> in a list,
	xmatch('match-visible',package-name) returns non-masked ebuilds,
	xmatch('match-list',package-name,mylist=list) checks for <package-name> in <list>
	There are more possible arguments.
	package-name may be, for example:
	   gnome-base/control-center            ebuilds for gnome-base/control-center
	   control-center                       ebuilds for gnome-base/control-center
	   >=gnome-base/control-center-2.8.2    only ebuilds with version >= 2.8.2
	"""
	#print >>stderr, "DATA_CONNECT: xmatch(); thread ident ", thread.get_ident()
	results  =  settings.portdb.xmatch(*args, **kwargs)
	#print >>stderr, type(results), str(results)
	return results


def get_versions(cp, include_masked=True):
	"""Returns all available ebuilds for the package
	
	@param cp:  cat/pkg string
	@rtype
	@return
	"""
	# Note: this is slow, especially when include_masked is false
	criterion = include_masked and 'match-all' or 'match-visible'
	results = xmatch(criterion, str(cp))
	#debug.dprint("DATA_CONNECT: get_versions(); criterion = %s, package = %s, results = %s" %(str(criterion),cp,str(results)))
	return  results


def get_hard_masked(cp):
	"""
	
	@param cp:  cat/pkg string
	@rtype tuple
	@return (hard_masked_nocheck, hardmasked)
	"""
	cp = str(cp)
	hardmasked = []
	try: # newer portage
		pmaskdict = settings.portdb.settings.pmaskdict[cp]
	except KeyError:
		pmaskdict = {}
	for x in pmaskdict:
		m = xmatch("match-all", x)
		for n in m:
			if n not in hardmasked:
				hardmasked.append(n)
	hard_masked_nocheck = hardmasked[:]
	try: # newer portage
		punmaskdict = settings.portdb.settings.punmaskdict[cp]
	except KeyError:
		punmaskdict = {}
	for x in punmaskdict:
		m = xmatch("match-all",x)
		for n in m:
			while n in hardmasked: hardmasked.remove(n)
	return hard_masked_nocheck, hardmasked


def get_installed_files(cpv):
	"""Get a list of installed files for an ebuild, assuming it has
	been installed.

	@param cpv:  cat/pkg-ver string
	@rtype list of strings
	"""
	path = "/var/db/pkg/" + cpv + "/CONTENTS"
	files = []
	try:
		# hoping some clown won't use spaces in filenames ...
		files = [line.split()[1].decode('ascii')
				 for line in open(path, "r").readlines()]
	except: pass
	files.sort()
	return files


def best(versions):
	"""returns the best version in the list of supplied versions
	
	@param versions: a list of cpv's
	@rtype str
	"""
	return portage.best(versions)


def get_best_ebuild(cp):
	"""returns the best available cpv
	
	@param cp:  cat/pkg string
	@rtype str
	"""
	return xmatch("bestmatch-visible", cp)


def get_dep_ebuild(dep):
	"""Progresively checks for available ebuilds that match the dependency.
	returns what it finds as up to three options.
	
	@param dep: a valid dependency string
	@rtype set
	@return  best_ebuild, keyworded_ebuild, masked_ebuild
	"""
	#debug.dprint("DATA_CONNECT: get_dep_ebuild(); dep = " + dep)
	best_ebuild = keyworded_ebuild = masked_ebuild = ''
	best_ebuild = xmatch("bestmatch-visible", dep)
	if best_ebuild == '':
		#debug.dprint("DATA_CONNECT: get_dep_ebuild(); checking masked packages")
		atomized_dep = Atom(dep)
		hardmasked_nocheck, hardmasked = get_hard_masked(atomized_dep.cpv)
		matches = xmatch("match-all", dep)[:]
		masked_ebuild = best(matches)
		keyworded = []
		for m in matches:
			if m not in hardmasked:
				keyworded.append(m)
		keyworded_ebuild = best(keyworded)
	#debug.dprint("DATA_CONNECT: get_dep_ebuild(); ebuilds = " + str([best_ebuild, keyworded_ebuild, masked_ebuild]))
	return best_ebuild, keyworded_ebuild, masked_ebuild


def get_virtual_dep(atom):
	"""Returns the first (prefered) resolved virtual dependency
	if there is more than 1 possible resolution
	
	@param atom: dependency string
	@rtpye: string 'cat/pkg-ver'
	"""
	return settings.settings.getvirtuals()[atom][0]


def get_masking_status(cpv):
	"""Gets the current masking status
	
	@param cpv:  cat/pkg-ver string
	@rtype str
	"""
	try:
		status = portage.getmaskingstatus(cpv)
	except KeyError:
		status = ['deprecated']
	return status


def get_masking_reason(cpv):
	"""Strips trailing \n from, and returns the masking reason given by portage
	
	@param cpv:  cat/pkg-ver string
	@rtype str
	"""
	reason, location = portage.getmaskingreason(cpv, settings=settings.settings, portdb=settings.portdb,  return_location=True)
	if not reason:
		reason = 'No masking reason given.'
		status =  get_masking_status(cpv)
		if 'profile' in status:
			reason = "Masked by the current profile."
			status.remove('profile')
		if status:
			reason += " from " + ', '.join(status)
	if location != None:
		reason += "in file: " + location
	if reason.endswith("\n"):
		reason = reason[:-1]
	return reason


def get_size(cpv, formatted_string=True):
	""" Returns size of package to fetch.
	
	@param cpv:  cat/pkg-ver string
	@param formatted_string: defaults to True
	@rtype str, or int
	"""
	#This code to calculate size of downloaded files was taken from /usr/bin/emerge - BB
	#debug.dprint( "DATA_CONNECT: get_size; cpv = " + cpv)
	total = [0,'']
	ebuild = settings.portdb.findname(cpv)
	pkgdir = os.path.dirname(ebuild)
	mf = manifest.Manifest(pkgdir, settings.settings["DISTDIR"])
	iuse, final_use = get_flags(cpv, final_setting=True)
	#debug.dprint( "DATA_CONNECT: get_size; Attempting to get fetchlist final use= " + str(final_use))
	try:
		fetchlist = settings.portdb.getFetchMap(cpv, set(final_use))
		#debug.dprint( "DATA_CONNECT: get_size; fetchlist= " +str(fetchlist))
		#debug.dprint( "DATA_CONNECT: get_size; mf.getDistfilesSize()")
		total[0] = mf.getDistfilesSize(fetchlist)
		if formatted_string:
			total_str = str(total[0]/1024)
			#debug.dprint( "DATA_CONNECT: get_size; total_str = " + total_str)
			count=len(total_str)
			while (count > 3):
				count-=3
				total_str=total_str[:count]+","+total_str[count:]
			total[1]=total_str+" kB"
	except KeyError, e:
		total[1] = "Unknown (missing digest)"
		total[0] = 0
		#debug.dprint( "DATA_CONNECT: get_size; Exception: " + str(e)  )
		#debug.dprint( "DATA_CONNECT: get_size; cpv: " + str(cpv))
		#debug.dprint( "DATA_CONNECT: get_size; fetchlist = " + str(fetchlist))
	#debug.dprint( "DATA_CONNECT: get_size; returning total[1] = " + total[1])
	if formatted_string:
		return total[1]
	return total[0]


def get_properties(cpv):
	"""Get all ebuild variables in one chunk.
	
	@param cpv:  cat/pkg-ver string
	@rtype
	@return all properties of cpv
	"""
	if settings.portdb.cpv_exists(cpv): # if in portage tree
		try:
			return Properties(dict(zip(settings.keys, settings.portdb.aux_get(cpv, portage.auxdbkeys))))
		except IOError, e: # Sync being performed may delete files
			#debug.dprint(" * DATA_CONNECT: get_properties(): IOError: %s" % str(e))
			return Properties()
		except Exception, e:
			#debug.dprint(" * DATA_CONNECT: get_properties(): Exception: %s" %str( e))
			return Properties()
	else:
		vartree = settings.trees[settings.settings["ROOT"]]["vartree"]
		if vartree.dbapi.cpv_exists(cpv): # elif in installed pkg tree
			return Properties(dict(zip(settings.keys, vartree.dbapi.aux_get(cpv, portage.auxdbkeys))))
		else: return Properties()


def is_overlay(cpv): # lifted from gentoolkit
	"""Returns true if the package is in an overlay.
	
	@param cpv:  cat/pkg-ver string
	@rtype bool
	"""
	try:
		dir,ovl = settings.portdb.findname2(cpv)
	except:
		return False
	return ovl != settings.portdir


def get_overlay(cpv):
	"""Returns a portage overlay id
	
	@param cpv:  cat/pkg-ver string
	@rtype str
	@return portage overlay id. or 'Deprecated?
	'"""
	if '/' not in cpv:
		return ''
	try:
		dir,ovl = settings.portdb.findname2(cpv)
	except:
		ovl = 'Deprecated?'
	return ovl


def get_overlay_name(ovl_path=None, cpv=None):
	"""Returns the overlay name for either the overlay path or the cpv of a pkg
	
	@param ovl_path: optional portage overlay path
	@param cpv: optional cat/pkg-ver string
	@rtype str
	"""
	if not ovl_path and cpv:
		ovl_path= get_overlay(cpv)
	name = None
	name = settings.portdb.getRepositoryName(ovl_path)
	return name or "????"


def get_path(cpv, vardb=True):
	"""Returns a path to the specified category/package-version in 
	either the vardb or portdb
	
	@param cpv: optional cat/pkg-ver string
	@param installed: bool, defaults to  True
	"""
	if vardb:
		return settings.trees[settings.settings["ROOT"]]["vartree"].getebuildpath(cpv)
	else:
		if '/' not in cpv:
			return ''
		try:
			dir,ovl = settings.portdb.findname2(cpv)
		except:
			dir = ''
		return dir


def get_system_pkgs(): # lifted from gentoolkit
	"""Returns a tuple of lists, first list is resolved system packages,
	second is a list of unresolved packages."""
	pkglist = settings.settings.packages
	resolved = []
	unresolved = []
	for x in pkglist:
		cpv = x.strip()
		pkg = get_best_ebuild(cpv)
		if pkg:
			try:
				resolved.append(Atom(pkg).cp)
			except:
				resolved.append(pkgsplit(pkg)[0])
		else:
			unresolved.append(pkgsplit(cpv)[0])
	return (resolved, unresolved)


def get_allnodes():
	"""Returns a list of all availabe cat/pkg's available from the tree
	and configured overlays.
	
	@rtpye: list
	@return: ['cat/pkg1', 'cat/pkg2',...]
	"""
	return settings.trees[settings.settings["ROOT"]]['porttree'].getallnodes()[:] # copy


def get_installed_list():
	"""Returns a list of all installed cat/pkg-ver available from the tree
	and configured overlays.
	
	@rtpye: list
	@return: ['cat/pkg1-ver', 'cat/pkg2-ver',...]
	"""
	return settings.trees[settings.settings["ROOT"]]["vartree"].getallnodes()[:] # copy

