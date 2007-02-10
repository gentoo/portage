from portage import dep_expand, dep_getkey, match_from_list, writemsg
from portage.dep import dep_getslot
from portage.locks import unlockfile
from portage.output import red

import os, re

class dbapi(object):
	def __init__(self):
		pass

	def close_caches(self):
		pass

	def cp_list(self, cp, use_cache=1):
		return

	def cpv_all(self):
		cpv_list = []
		for cp in self.cp_all():
			cpv_list.extend(self.cp_list(cp))
		return cpv_list

	def aux_get(self, mycpv, mylist):
		"stub code for returning auxiliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		raise NotImplementedError

	def match(self, origdep, use_cache=1):
		mydep = dep_expand(origdep, mydb=self, settings=self.settings)
		mykey = dep_getkey(mydep)
		mylist = match_from_list(mydep, self.cp_list(mykey, use_cache=use_cache))
		myslot = dep_getslot(mydep)
		if myslot is not None:
			mylist = [cpv for cpv in mylist \
				if self.aux_get(cpv, ["SLOT"])[0] == myslot]
		return mylist

	def invalidentry(self, mypath):
		if re.search("portage_lockfile$", mypath):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				unlockfile((mypath, None, None))
			else:
				# Nothing we can do about it. We're probably sandboxed.
				pass
		elif re.search(".*/-MERGING-(.*)", mypath):
			if os.path.exists(mypath):
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n", noiselevel=-1)
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath, noiselevel=-1)

