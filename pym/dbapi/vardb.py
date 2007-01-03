from dbapi import dbapi
from portage import settings, db, listdir, dblink
from portage_const import VDB_PATH
from portage_versions import pkgsplit, catpkgsplit
from portage_util import write_atomic, writemsg, writems_stdout, grabfile
from portage_dep import isjustname, isvalidatom, dep_getkey, dep_getslot, \
	match_from_list, dep_expand
from portage_update import fixdbentries

import portage_exception
import os, sys

cptot=0
class vardbapi(dbapi):
	def __init__(self, root, categories=None, settings=None, vartree=None):
		self.root       = root[:]
		#cache for category directory mtimes
		self.mtdircache = {}
		#cache for dependency checks
		self.matchcache = {}
		#cache for cp_list results
		self.cpcache    = {}
		self.blockers   = None
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings
		if categories is None:
			categories = settings.categories
		self.categories = categories[:]
		if vartree is None:
			vartree = globals()["db"][root]["vartree"]
		self.vartree = vartree

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.root+VDB_PATH+"/"+mykey)

	def cpv_counter(self,mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		cdir=self.root+VDB_PATH+"/"+mycpv
		cpath=self.root+VDB_PATH+"/"+mycpv+"/COUNTER"

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption on XFS (unexpected reboot.)
		corrupted=0
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except ValueError:
				print "portage: COUNTER for",mycpv,"was corrupted; resetting to value of 0"
				counter=long(0)
				corrupted=1
			cfile.close()
		elif os.path.exists(cdir):
			mys = pkgsplit(mycpv)
			myl = self.match(mys[0],use_cache=0)
			print mys,myl
			if len(myl) == 1:
				try:
					# Only one package... Counter doesn't matter.
					write_atomic(cpath, "1")
					counter = 1
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
						noiselevel=-1)
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n",
						noiselevel=-1)
					writemsg("!!! unmerge this exact version.\n", noiselevel=-1)
					writemsg("!!! %s\n" % e, noiselevel=-1)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
					noiselevel=-1)
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n",
					noiselevel=-1)
				writemsg("!!! remerge the package.\n", noiselevel=-1)
				sys.exit(1)
		else:
			counter=long(0)
		if corrupted:
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

	def cpv_inject(self,mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		os.makedirs(self.root+VDB_PATH+"/"+mycpv)
		counter = self.counter_tick(self.root, mycpv=mycpv)
		# write local package counter so that emerge clean does the right thing
		write_atomic(os.path.join(self.root, VDB_PATH, mycpv, "COUNTER"), str(counter))

	def isInjected(self,mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/INJECTED"):
				return True
			if not os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/CONTENTS"):
				return True
		return False

	def move_ent(self,mylist):
		origcp=mylist[1]
		newcp=mylist[2]

		# sanity check
		for cp in [origcp,newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise portage_exception.InvalidPackageName(cp)
		origmatches=self.match(origcp,use_cache=0)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			mynewcpv=newcp+"-"+mycpsplit[2]
			mynewcat=newcp.split("/")[0]
			if mycpsplit[3]!="r0":
				mynewcpv += "-"+mycpsplit[3]
			mycpsplit_new = catpkgsplit(mynewcpv)
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue
			writemsg_stdout("@")
			if not os.path.exists(self.root+VDB_PATH+"/"+mynewcat):
				#create the directory
				os.makedirs(self.root+VDB_PATH+"/"+mynewcat)
			newpath=self.root+VDB_PATH+"/"+mynewcpv
			if os.path.exists(newpath):
				#dest already exists; keep this puppy where it is.
				continue
			os.rename(origpath, newpath)

			# We need to rename the ebuild now.
			old_eb_path = newpath+"/"+mycpsplit[1]    +"-"+mycpsplit[2]
			new_eb_path = newpath+"/"+mycpsplit_new[1]+"-"+mycpsplit[2]
			if mycpsplit[3] != "r0":
				old_eb_path += "-"+mycpsplit[3]
				new_eb_path += "-"+mycpsplit[3]
			if os.path.exists(old_eb_path+".ebuild"):
				os.rename(old_eb_path+".ebuild", new_eb_path+".ebuild")

			write_atomic(os.path.join(newpath, "CATEGORY"), mynewcat+"\n")
			fixdbentries([mylist], newpath)

	def update_ents(self, update_iter):
		"""Run fixdbentries on all installed packages (time consuming).  Like
		fixpackages, this should be run from a helper script and display
		a progress indicator."""
		dbdir = os.path.join(self.root, VDB_PATH)
		for catdir in listdir(dbdir):
			catdir = dbdir+"/"+catdir
			if os.path.isdir(catdir):
				for pkgdir in listdir(catdir):
					pkgdir = catdir+"/"+pkgdir
					if os.path.isdir(pkgdir):
						fixdbentries(update_iter, pkgdir)

	def move_slot_ent(self,mylist):
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]

		if not isvalidatom(pkg):
			raise portage_exception.InvalidAtom(pkg)

		origmatches=self.match(pkg,use_cache=0)
		
		if not origmatches:
			return
		for mycpv in origmatches:
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue

			slot=grabfile(origpath+"/SLOT");
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			writemsg_stdout("s")
			write_atomic(os.path.join(origpath, "SLOT"), newslot+"\n")

	def cp_list(self,mycp,use_cache=1):
		mysplit=mycp.split("/")
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat=os.stat(self.root+VDB_PATH+"/"+mysplit[0])[stat.ST_MTIME]
		except OSError:
			mystat=0
		if use_cache and self.cpcache.has_key(mycp):
			cpc=self.cpcache[mycp]
			if cpc[0]==mystat:
				return cpc[1]
		list=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)

		if (list is None):
			return []
		returnme=[]
		for x in list:
			if x.startswith("."):
				continue
			if x[0] == '-':
				#writemsg(red("INCOMPLETE MERGE:")+str(x[len("-MERGING-"):])+"\n")
				continue
			ps=pkgsplit(x)
			if not ps:
				self.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if len(mysplit) > 1:
				if ps[0]==mysplit[1]:
					returnme.append(mysplit[0]+"/"+x)
		if use_cache:
			self.cpcache[mycp]=[mystat,returnme]
		elif self.cpcache.has_key(mycp):
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self,use_cache=1):
		returnme=[]
		basepath = self.root+VDB_PATH+"/"

		for x in self.categories:
			for y in listdir(basepath+x,EmptyOnError=1):
				if y.startswith("."):
					continue
				subpath = x+"/"+y
				# -MERGING- should never be a cpv, nor should files.
				if os.path.isdir(basepath+subpath) and (pkgsplit(y) is not None):
					returnme += [subpath]
		return returnme

	def cp_all(self,use_cache=1):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			mysplit=catpkgsplit(y)
			if not mysplit:
				self.invalidentry(self.root+VDB_PATH+"/"+y)
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return d.keys()

	def checkblockers(self,origdep):
		pass

	def match(self,origdep,use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		if not use_cache:
			if self.matchcache.has_key(mycat):
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			mymatch = match_from_list(mydep,
				self.cp_list(mykey, use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			return mymatch
		try:
			curmtime=os.stat(self.root+VDB_PATH+"/"+mycat)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except:
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat]=curmtime
			self.matchcache[mycat]={}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch=match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			self.matchcache[mycat][mydep]=mymatch
		return self.matchcache[mycat][mydep][:]

	def findname(self, mycpv):
		return self.root+VDB_PATH+"/"+str(mycpv)+"/"+mycpv.split("/")[1]+".ebuild"

	def aux_get(self, mycpv, wants):
		mydir = os.path.join(self.root, VDB_PATH, mycpv)
		if not os.path.isdir(mydir):
			raise KeyError(mycpv)
		results = []
		for x in wants:
			try:
				myf = open(os.path.join(mydir, x), "r")
				try:
					myd = myf.read()
				finally:
					myf.close()
				myd = " ".join(myd.split())
			except IOError:
				myd = ""
			if x == "EAPI" and not myd:
				results.append("0")
			else:
				results.append(myd)
		return results

	def aux_update(self, cpv, values):
		cat, pkg = cpv.split("/")
		mylink = dblink(cat, pkg, self.root, self.settings,
		treetype="vartree", vartree=self.vartree)
		if not mylink.exists():
			raise KeyError(cpv)
		for k, v in values.iteritems():
			mylink.setfile(k, v)

	def counter_tick(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,incrementing=1,mycpv=mycpv)

	def get_counter_tick_core(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,incrementing=0,mycpv=mycpv)+1

	def counter_tick_core(self,myroot,incrementing=1,mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		cpath=myroot+"var/cache/edb/counter"
		changed=0
		min_counter = 0
		if mycpv:
			mysplit = pkgsplit(mycpv)
			for x in self.match(mysplit[0],use_cache=0):
				if x==mycpv:
					continue
				try:
					old_counter = long(self.aux_get(x,["COUNTER"])[0])
					writemsg("COUNTER '%d' '%s'\n" % (old_counter, x),1)
				except SystemExit, e:
					raise
				except:
					old_counter = 0
					writemsg("!!! BAD COUNTER in '%s'\n" % (x), noiselevel=-1)
				if old_counter > min_counter:
					min_counter = old_counter

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption.
		find_counter = ("find '%s' -type f -name COUNTER | " + \
			"while read f; do echo $(<\"${f}\"); done | " + \
			"sort -n | tail -n1") % os.path.join(self.root, VDB_PATH)
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except (ValueError,OverflowError):
				try:
					counter = long(commands.getoutput(find_counter).strip())
					writemsg("!!! COUNTER was corrupted; resetting to value of %d\n" % counter,
						noiselevel=-1)
					changed=1
				except (ValueError,OverflowError):
					writemsg("!!! COUNTER data is corrupt in pkg db. The values need to be\n",
						noiselevel=-1)
					writemsg("!!! corrected/normalized so that portage can operate properly.\n",
						noiselevel=-1)
					writemsg("!!! A simple solution is not yet available so try #gentoo on IRC.\n")
					sys.exit(2)
			cfile.close()
		else:
			try:
				counter = long(commands.getoutput(find_counter).strip())
				writemsg("!!! Global counter missing. Regenerated from counter files to: %s\n" % counter,
					noiselevel=-1)
			except SystemExit, e:
				raise
			except:
				writemsg("!!! Initializing global counter.\n", noiselevel=-1)
				counter=long(0)
			changed=1

		if counter < min_counter:
			counter = min_counter+1000
			changed = 1

		if incrementing or changed:

			#increment counter
			counter += 1
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter
