# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["cpv_expand"]

import portage
from portage.exception import AmbiguousPackageName
from portage.versions import _pkgsplit

def cpv_expand(mycpv, mydb=None, use_cache=1, settings=None):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit = _pkgsplit(myslash[-1])
	if settings is None:
		try:
			settings = mydb.settings
		except AttributeError:
			settings = portage.settings
	if len(myslash)>2:
		# this is illegal case.
		mysplit=[]
		mykey=mycpv
	elif len(myslash)==2:
		if mysplit:
			mykey=myslash[0]+"/"+mysplit[0]
		else:
			mykey=mycpv

		# Since Gentoo stopped using old-style virtuals in
		# 2011, typically it's possible to avoid getvirtuals()
		# calls entirely. Therefore, only call getvirtuals()
		# if the atom category is "virtual" and cp_list()
		# returns nothing.
		if mykey.startswith("virtual/") and \
			hasattr(mydb, "cp_list") and \
			not mydb.cp_list(mykey, use_cache=use_cache):
				if hasattr(mydb, "vartree"):
					settings._populate_treeVirtuals_if_needed(mydb.vartree)
				virts = settings.getvirtuals().get(mykey)
				if virts:
					mykey_orig = mykey
					for vkey in virts:
						# The virtuals file can contain a versioned atom, so
						# it may be necessary to remove the operator and
						# version from the atom before it is passed into
						# dbapi.cp_list().
						if mydb.cp_list(vkey.cp):
							mykey = str(vkey)
							break
					if mykey == mykey_orig:
						mykey = str(virts[0])
			#we only perform virtual expansion if we are passed a dbapi
	else:
		#specific cpv, no category, ie. "foo-1.0"
		if mysplit:
			myp=mysplit[0]
		else:
			# "foo" ?
			myp=mycpv
		mykey=None
		matches=[]
		if mydb and hasattr(mydb, "categories"):
			for x in mydb.categories:
				if mydb.cp_list(x+"/"+myp,use_cache=use_cache):
					matches.append(x+"/"+myp)
		if len(matches) > 1:
			virtual_name_collision = False
			if len(matches) > 1:
				for x in matches:
					if not x.startswith(("acct-group/", "acct-user/", "virtual/")):
						# Assume that the non-virtual is desired.  This helps
						# avoid the ValueError for invalid deps that come from
						# installed packages (during reverse blocker detection,
						# for example).
						mykey = x
					else:
						virtual_name_collision = True
			if not virtual_name_collision:
				# AmbiguousPackageName inherits from ValueError,
				# for backward compatibility with calling code
				# that already handles ValueError.
				raise AmbiguousPackageName(matches)
		elif matches:
			mykey=matches[0]

		if not mykey and not isinstance(mydb, list):
			if hasattr(mydb, "vartree"):
				settings._populate_treeVirtuals_if_needed(mydb.vartree)
			virts_p = settings.get_virts_p().get(myp)
			if virts_p:
				mykey = virts_p[0]
			#again, we only perform virtual expansion if we have a dbapi (not a list)
		if not mykey:
			mykey="null/"+myp
	if mysplit:
		if mysplit[2]=="r0":
			return mykey+"-"+mysplit[1]
		return mykey+"-"+mysplit[1]+"-"+mysplit[2]
	return mykey
