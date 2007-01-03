from dbapi.fake import fakedbapi
from portage import settings
import xpak, os

class bindbapi(fakedbapi):
	def __init__(self, mybintree=None, settings=None):
		self.bintree = mybintree
		self.cpvdict={}
		self.cpdict={}
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings
		self._match_cache = {}

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def aux_get(self,mycpv,wants):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		mysplit = mycpv.split("/")
		mylist  = []
		tbz2name = mysplit[1]+".tbz2"
		if self.bintree and not self.bintree.isremote(mycpv):
			tbz2 = xpak.tbz2(self.bintree.getname(mycpv))
		for x in wants:
			if self.bintree and self.bintree.isremote(mycpv):
				# We use the cache for remote packages
				mylist.append(" ".join(
					self.bintree.remotepkgs[tbz2name].get(x,"").split()))
			else:
				myval = tbz2.getfile(x)
				if myval is None:
					myval = ""
				else:
					myval = " ".join(myval.split())
				mylist.append(myval)
		if "EAPI" in wants:
			idx = wants.index("EAPI")
			if not mylist[idx]:
				mylist[idx] = "0"
		return mylist

	def aux_update(self, cpv, values):
		if not self.bintree.populated:
			self.bintree.populate()
		tbz2path = self.bintree.getname(cpv)
		if not os.path.exists(tbz2path):
			raise KeyError(cpv)
		mytbz2 = xpak.tbz2(tbz2path)
		mydata = mytbz2.get_data()
		mydata.update(values)
		mytbz2.recompose_mem(xpak.xpak_mem(mydata))

	def cp_list(self, *pargs, **kwargs):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_list(self, *pargs, **kwargs)

	def cpv_all(self):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cpv_all(self)
