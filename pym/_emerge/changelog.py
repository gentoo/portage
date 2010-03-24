# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import codecs
import re

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode

def calc_changelog(ebuildpath,current,next):
	if ebuildpath == None or not os.path.exists(ebuildpath):
		return []
	current = '-'.join(portage.catpkgsplit(current)[1:])
	if current.endswith('-r0'):
		current = current[:-3]
	next = '-'.join(portage.catpkgsplit(next)[1:])
	if next.endswith('-r0'):
		next = next[:-3]
	changelogpath = os.path.join(os.path.split(ebuildpath)[0],'ChangeLog')
	try:
		changelog = codecs.open(_unicode_encode(changelogpath,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
		).read()
	except SystemExit as e:
		raise # Needed else can't exit
	except:
		return []
	divisions = _find_changelog_tags(changelog)
	#print 'XX from',current,'to',next
	#for div,text in divisions: print 'XX',div
	# skip entries for all revisions above the one we are about to emerge
	for i in range(len(divisions)):
		if divisions[i][0]==next:
			divisions = divisions[i:]
			break
	# find out how many entries we are going to display
	for i in range(len(divisions)):
		if divisions[i][0]==current:
			divisions = divisions[:i]
			break
	else:
	    # couldnt find the current revision in the list. display nothing
		return []
	return divisions

def _find_changelog_tags(changelog):
	divs = []
	release = None
	while 1:
		match = re.search(r'^\*\ ?([-a-zA-Z0-9_.+]*)(?:\ .*)?\n',changelog,re.M)
		if match is None:
			if release is not None:
				divs.append((release,changelog))
			return divs
		if release is not None:
			divs.append((release,changelog[:match.start()]))
		changelog = changelog[match.end():]
		release = match.group(1)
		if release.endswith('.ebuild'):
			release = release[:-7]
		if release.endswith('-r0'):
			release = release[:-3]
