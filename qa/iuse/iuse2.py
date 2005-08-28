#!/usr/bin/python2.2
import portage,sys
portdir=portage.settings["PORTDIR"]
for cp in portage.portdb.cp_all():
	for cpv in portage.portdb.cp_list(cp):
		try:
			myaux=portage.portdb.aux_get(cpv,["DEPEND","RDEPEND","SRC_URI"])
		except KeyError:
			pass
		myuse={}
		for str in myaux:
			mysplit=str.split()
			for part in mysplit:
				if part[-1]=="?":
					if part[0]=="!":
						if not myuse.has_key(part[1:-1]):
							myuse[part[1:-1]]=None
					else:
						if not myuse.has_key(part[:-1]):
							myuse[part[:-1]]=None
		if not myuse:
			continue
		cpsplit=cpv.split("/")
		mypath=portdir+"/"+cp+"/.use-"+cpsplit[1]
		print mypath
		myfile=open(mypath,"r")
		for x in myfile.readlines():
			if x[:-1]:
				if not myuse.has_key(x[:-1]):
					myuse[x[:-1]]=None
		print myuse.keys()
		myfile.close()
		if not myuse.keys():
			#no IUSE to add
			continue
		myepath=portdir+"/"+cp+"/"+cpsplit[1]+".ebuild"
		myefile=open(myepath,"r")
		mylines=myefile.readlines()
		myefile.close()
		mynewlines=[]
		pos=0
		while (pos<len(mylines)) and (mylines[pos][0]=="#"):
			mynewlines.append(mylines[pos])
			pos += 1
		myuses=myuse.keys()
		iuseline="\nIUSE=\""+myuses[0]
		for x in myuses[1:]:
			iuseline=iuseline+" "+x
		iuseline=iuseline+"\"\n"
		mynewlines.append(iuseline)
		while (pos<len(mylines)):
			mynewlines.append(mylines[pos])
			pos += 1
		
		myefile=open(myepath,"w")
		for x in mynewlines:
			myefile.write(x)
		myefile.close()
