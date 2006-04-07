# getbinpkg.py -- Portage binary-package helper functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/getbinpkg.py,v 1.12.2.3 2005/01/16 02:35:33 carpaski Exp $


from output import *
import htmllib,HTMLParser,string,formatter,sys,os,xpak,time,tempfile,base64

try:
	import cPickle
except ImportError:
	import pickle as cPickle

try:
	import ftplib
except SystemExit, e:
	raise
except Exception, e:
	sys.stderr.write(red("!!! CANNOT IMPORT FTPLIB: ")+str(e)+"\n")

try:
	import httplib
except SystemExit, e:
	raise
except Exception, e:
	sys.stderr.write(red("!!! CANNOT IMPORT HTTPLIB: ")+str(e)+"\n")

def make_metadata_dict(data):
	myid,myglob = data
	
	mydict = {}
	for x in xpak.getindex_mem(myid):
		mydict[x] = xpak.getitem(data,x)

	return mydict

class ParseLinks(HTMLParser.HTMLParser):
	"""Parser class that overrides HTMLParser to grab all anchors from an html
	page and provide suffix and prefix limitors"""
	def __init__(self):
		self.PL_anchors = []
		HTMLParser.HTMLParser.__init__(self)

	def get_anchors(self):
		return self.PL_anchors
		
	def get_anchors_by_prefix(self,prefix):
		newlist = []
		for x in self.PL_anchors:
			if (len(x) >= len(prefix)) and (x[:len(suffix)] == prefix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist
		
	def get_anchors_by_suffix(self,suffix):
		newlist = []
		for x in self.PL_anchors:
			if (len(x) >= len(suffix)) and (x[-len(suffix):] == suffix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist
		
	def	handle_endtag(self,tag):
		pass

	def	handle_starttag(self,tag,attrs):
		if tag == "a":
			for x in attrs:
				if x[0] == 'href':
					if x[1] not in self.PL_anchors:
						self.PL_anchors.append(x[1])


def create_conn(baseurl,conn=None):
	"""(baseurl,conn) --- Takes a protocol://site:port/address url, and an
	optional connection. If connection is already active, it is passed on.
	baseurl is reduced to address and is returned in tuple (conn,address)"""
	parts = string.split(baseurl, "://", 1)
	if len(parts) != 2:
		raise ValueError, "Provided URL does not contain protocol identifier. '%s'" % baseurl
	protocol,url_parts = parts
	del parts
	host,address = string.split(url_parts, "/", 1)
	del url_parts
	address = "/"+address

	userpass_host = string.split(host, "@", 1)
	if len(userpass_host) == 1:
		host = userpass_host[0]
		userpass = ["anonymous"]
	else:
		host = userpass_host[1]
		userpass = string.split(userpass_host[0], ":")
	del userpass_host

	if len(userpass) > 2:
		raise ValueError, "Unable to interpret username/password provided."
	elif len(userpass) == 2:
		username = userpass[0]
		password = userpass[1]
	elif len(userpass) == 1:
		username = userpass[0]
		password = None
	del userpass

	http_headers = {}
	http_params = {}
	if username and password:
		http_headers = {
			"Authorization": "Basic %s" %
			  string.replace(
			    base64.encodestring("%s:%s" % (username, password)),
			    "\012",
			    ""
			  ),
		}

	if not conn:
		if protocol == "https":
			conn = httplib.HTTPSConnection(host)
		elif protocol == "http":
			conn = httplib.HTTPConnection(host)
		elif protocol == "ftp":
			passive = 1
			if(host[-1] == "*"):
				passive = 0
				host = host[:-1]
			conn = ftplib.FTP(host)
			if password:
				conn.login(username,password)
			else:
				sys.stderr.write(yellow(" * No password provided for username")+" '"+str(username)+"'\n\n")
				conn.login(username)
			conn.set_pasv(passive)
			conn.set_debuglevel(0)
		else:
			raise NotImplementedError, "%s is not a supported protocol." % protocol

	return (conn,protocol,address, http_params, http_headers)

def make_ftp_request(conn, address, rest=None, dest=None):
	"""(conn,address,rest) --- uses the conn object to request the data
	from address and issuing a rest if it is passed."""
	try:
	
		if dest:
			fstart_pos = dest.tell()
	
		conn.voidcmd("TYPE I")
		fsize = conn.size(address)

		if (rest != None) and (rest < 0):
			rest = fsize+int(rest)
		if rest < 0:
			rest = 0

		if rest != None:
			mysocket = conn.transfercmd("RETR "+str(address), rest)
		else:
			mysocket = conn.transfercmd("RETR "+str(address))

		mydata = ""
		while 1:
			somedata = mysocket.recv(8192)
			if somedata:
				if dest:
					dest.write(somedata)
				else:
					mydata = mydata + somedata
			else:
				break

		if dest:
			data_size = fstart_pos - dest.tell()
		else:
			data_size = len(mydata)

		mysocket.close()
		conn.voidresp()
		conn.voidcmd("TYPE A")

		return mydata,not (fsize==data_size),""

	except ValueError, e:
		return None,int(str(e)[:4]),str(e)
	

def make_http_request(conn, address, params={}, headers={}, dest=None):
	"""(conn,address,params,headers) --- uses the conn object to request
	the data from address, performing Location forwarding and using the
	optional params and headers."""

	rc = 0
	response = None
	while (rc == 0) or (rc == 301) or (rc == 302):
		try:
			if (rc != 0):
				conn,ignore,ignore,ignore,ignore = create_conn(address)
			conn.request("GET", address, params, headers)
		except SystemExit, e:
			raise
		except Exception, e:
			return None,None,"Server request failed: "+str(e)
		response = conn.getresponse()
		rc = response.status

		# 301 means that the page address is wrong.
		if ((rc == 301) or (rc == 302)):
			ignored_data = response.read()
			del ignored_data
			for x in string.split(str(response.msg), "\n"):
				parts = string.split(x, ": ", 1)
				if parts[0] == "Location":
					if (rc == 301):
						sys.stderr.write(red("Location has moved: ")+str(parts[1])+"\n")
					if (rc == 302):
						sys.stderr.write(red("Location has temporarily moved: ")+str(parts[1])+"\n")
					address = parts[1]
					break
	
	if (rc != 200) and (rc != 206):
		sys.stderr.write(str(response.msg)+"\n")
		sys.stderr.write(response.read()+"\n")
		sys.stderr.write("address: "+address+"\n")
		return None,rc,"Server did not respond successfully ("+str(response.status)+": "+str(response.reason)+")"

	if dest:
		dest.write(response.read())
		return "",0,""

	return response.read(),0,""


def match_in_array(array, prefix="", suffix="", match_both=1, allow_overlap=0):
	myarray = []
	
	if not (prefix and suffix):
		match_both = 0
		
	for x in array:
		add_p = 0
		if prefix and (len(x) >= len(prefix)) and (x[:len(prefix)] == prefix):
			add_p = 1

		if match_both:
			if prefix and not add_p: # Require both, but don't have first one.
				continue
		else:
			if add_p:     # Only need one, and we have it.
				myarray.append(x[:])
				continue

		if not allow_overlap: # Not allow to overlap prefix and suffix
			if len(x) >= (len(prefix)+len(suffix)):
				y = x[len(prefix):]
			else:
				continue          # Too short to match.
		else:
			y = x               # Do whatever... We're overlapping.
		
		if suffix and (len(x) >= len(suffix)) and (x[-len(suffix):] == suffix):
			myarray.append(x)   # It matches
		else:
			continue            # Doesn't match.

	return myarray
			


def dir_get_list(baseurl,conn=None):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	listing = None
	if protocol in ["http","https"]:
		page,rc,msg = make_http_request(conn,address,params,headers)
		
		if page:
			parser = ParseLinks()
			parser.feed(page)
			del page
			listing = parser.get_anchors()
		else:
			raise Exception, "Unable to get listing: %s %s" % (rc,msg)
	elif protocol in ["ftp"]:
		if address[-1] == '/':
			olddir = conn.pwd()
			conn.cwd(address)
			listing = conn.nlst()
			conn.cwd(olddir)
			del olddir
		else:
			listing = conn.nlst(address)
	else:
		raise TypeError, "Unknown protocol. '%s'" % protocol

	if not keepconnection:
		conn.close()

	return listing

def file_get_metadata(baseurl,conn=None, chunk_size=3000):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	if protocol in ["http","https"]:
		headers["Range"] = "bytes=-"+str(chunk_size)
		data,rc,msg = make_http_request(conn, address, params, headers)
	elif protocol in ["ftp"]:
		data,rc,msg = make_ftp_request(conn, address, -chunk_size)
	else:
		raise TypeError, "Unknown protocol. '%s'" % protocol
	
	if data:
		xpaksize = xpak.decodeint(data[-8:-4])
		if (xpaksize+8) > chunk_size:
			myid = file_get_metadata(baseurl, conn, (xpaksize+8))
			if not keepconnection:
				conn.close()
			return myid
		else:
			xpak_data = data[len(data)-(xpaksize+8):-8]
		del data

		myid = xpak.xsplit_mem(xpak_data)
		if not myid:
			myid = None,None
		del xpak_data
	else:
		myid = None,None

	if not keepconnection:
		conn.close()

	return myid


def file_get(baseurl,dest,conn=None,fcmd=None):
	"""(baseurl,dest,fcmd=) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://[user[:pass]@]<site>[:port]<path>"""

	if not fcmd:
		return file_get_lib(baseurl,dest,conn)

	fcmd = string.replace(fcmd, "${DISTDIR}", dest)
	fcmd = string.replace(fcmd, "${URI}", baseurl)
	fcmd = string.replace(fcmd, "${FILE}", os.path.basename(baseurl))
	mysplit = string.split(fcmd)
	mycmd   = mysplit[0]
	myargs  = [os.path.basename(mycmd)]+mysplit[1:]
	mypid=os.fork()
	if mypid == 0:
		try:
			os.execv(mycmd,myargs)
		except OSError:
			pass
		sys.stderr.write("!!! Failed to spawn fetcher.\n")
		sys.exit(1)
	retval=os.waitpid(mypid,0)[1]
	if (retval & 0xff) == 0:
		retval = retval >> 8
	else:
		sys.stderr.write("Spawned processes caught a signal.\n")
		sys.exit(1)
	if retval != 0:
		sys.stderr.write("Fetcher exited with a failure condition.\n")
		return 0
	return 1

def file_get_lib(baseurl,dest,conn=None):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	sys.stderr.write("Fetching '"+str(os.path.basename(address)+"'\n"))
	if protocol in ["http","https"]:
		data,rc,msg = make_http_request(conn, address, params, headers, dest=dest)
	elif protocol in ["ftp"]:
		data,rc,msg = make_ftp_request(conn, address, dest=dest)
	else:
		raise TypeError, "Unknown protocol. '%s'" % protocol
	
	if not keepconnection:
		conn.close()

	return rc


def dir_get_metadata(baseurl, conn=None, chunk_size=3000, verbose=1, usingcache=1, makepickle=None):
	"""(baseurl,conn,chunk_size,verbose) -- 
	"""
	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	if makepickle is None:
		makepickle = "/var/cache/edb/metadata.idx.most_recent"

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	filedict = {}

	try:
		metadatafile = open("/var/cache/edb/remote_metadata.pickle")
		metadata = cPickle.load(metadatafile)
		sys.stderr.write("Loaded metadata pickle.\n")
		metadatafile.close()
	except SystemExit, e:
		raise
	except:
		metadata = {}
	if not metadata.has_key(baseurl):
		metadata[baseurl]={}
	if not metadata[baseurl].has_key("indexname"):
		metadata[baseurl]["indexname"]=""
	if not metadata[baseurl].has_key("timestamp"):
		metadata[baseurl]["timestamp"]=0
	if not metadata[baseurl].has_key("unmodified"):
		metadata[baseurl]["unmodified"]=0
	if not metadata[baseurl].has_key("data"):
		metadata[baseurl]["data"]={}

	filelist = dir_get_list(baseurl, conn)
	tbz2list = match_in_array(filelist, suffix=".tbz2")
	metalist = match_in_array(filelist, prefix="metadata.idx")
	del filelist
	
	# Determine if our metadata file is current.
	metalist.sort()
	metalist.reverse() # makes the order new-to-old.
	havecache=0
	for mfile in metalist:
		if usingcache and \
		   ((metadata[baseurl]["indexname"] != mfile) or \
			  (metadata[baseurl]["timestamp"] < int(time.time()-(60*60*24)))):
			# Try to download new cache until we succeed on one.
			data=""
			for trynum in [1,2,3]:
				mytempfile = tempfile.TemporaryFile()
				try:
					file_get(baseurl+"/"+mfile, mytempfile, conn)
					if mytempfile.tell() > len(data):
						mytempfile.seek(0)
						data = mytempfile.read()
				except ValueError, e:
					sys.stderr.write("--- "+str(e)+"\n")
					if trynum < 3:
						sys.stderr.write("Retrying...\n")
					mytempfile.close()
					continue
				if match_in_array([mfile],suffix=".gz"):
					sys.stderr.write("gzip'd\n")
					try:
						import gzip
						mytempfile.seek(0)
						gzindex = gzip.GzipFile(mfile[:-3],'rb',9,mytempfile)
						data = gzindex.read()
					except SystemExit, e:
						raise
					except Exception, e:
						mytempfile.close()
						sys.stderr.write("!!! Failed to use gzip: "+str(e)+"\n")
					mytempfile.close()
				try:
					metadata[baseurl]["data"] = cPickle.loads(data)
					del data
					metadata[baseurl]["indexname"] = mfile
					metadata[baseurl]["timestamp"] = int(time.time())
					metadata[baseurl]["modified"]  = 0 # It's not, right after download.
					sys.stderr.write("Pickle loaded.\n")
					break
				except SystemExit, e:
					raise
				except Exception, e:
					sys.stderr.write("!!! Failed to read data from index: "+str(mfile)+"\n")
					sys.stderr.write("!!! "+str(e)+"\n")
			try:
				metadatafile = open("/var/cache/edb/remote_metadata.pickle", "w+")
				cPickle.dump(metadata,metadatafile)
				metadatafile.close()
			except SystemExit, e:
				raise
			except Exception, e:
				sys.stderr.write("!!! Failed to write binary metadata to disk!\n")
				sys.stderr.write("!!! "+str(e)+"\n")
			break
	# We may have metadata... now we run through the tbz2 list and check.
	sys.stderr.write(yellow("cache miss: 'x'")+" --- "+green("cache hit: 'o'")+"\n")
	for x in tbz2list:
		x = os.path.basename(x)
		if ((not metadata[baseurl]["data"].has_key(x)) or \
		    (x not in metadata[baseurl]["data"].keys())):
			sys.stderr.write(yellow("x"))
			metadata[baseurl]["modified"] = 1
			myid = file_get_metadata(baseurl+"/"+x, conn, chunk_size)
		
			if myid[0]:
				metadata[baseurl]["data"][x] = make_metadata_dict(myid)
			elif verbose:
				sys.stderr.write(red("!!! Failed to retrieve metadata on: ")+str(x)+"\n")
		else:
			sys.stderr.write(green("o"))
	sys.stderr.write("\n")
	
	try:
		if metadata[baseurl].has_key("modified") and metadata[baseurl]["modified"]:
			metadata[baseurl]["timestamp"] = int(time.time())
			metadatafile = open("/var/cache/edb/remote_metadata.pickle", "w+")
			cPickle.dump(metadata,metadatafile)
			metadatafile.close()
		if makepickle:
			metadatafile = open(makepickle, "w")
			cPickle.dump(metadata[baseurl]["data"],metadatafile)
			metadatafile.close()
	except SystemExit, e:
		raise
	except Exception, e:
		sys.stderr.write("!!! Failed to write binary metadata to disk!\n")
		sys.stderr.write("!!! "+str(e)+"\n")

	if not keepconnection:
		conn.close()
	
	return metadata[baseurl]["data"]
