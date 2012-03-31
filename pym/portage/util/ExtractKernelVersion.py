# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ExtractKernelVersion']

import io

from portage import os, _encodings, _unicode_encode
from portage.util import getconfig, grabfile

def ExtractKernelVersion(base_dir):
	"""
	Try to figure out what kernel version we are running
	@param base_dir: Path to sources (usually /usr/src/linux)
	@type base_dir: string
	@rtype: tuple( version[string], error[string])
	@return:
	1. tuple( version[string], error[string])
	Either version or error is populated (but never both)

	"""
	lines = []
	pathname = os.path.join(base_dir, 'Makefile')
	try:
		f = io.open(_unicode_encode(pathname,
			encoding=_encodings['fs'], errors='strict'), mode='r',
			encoding=_encodings['content'], errors='replace')
	except OSError as details:
		return (None, str(details))
	except IOError as details:
		return (None, str(details))

	try:
		for i in range(4):
			lines.append(f.readline())
	except OSError as details:
		return (None, str(details))
	except IOError as details:
		return (None, str(details))
	finally:
		f.close()

	lines = [l.strip() for l in lines]

	version = ''

	#XXX: The following code relies on the ordering of vars within the Makefile
	for line in lines:
		# split on the '=' then remove annoying whitespace
		items = line.split("=")
		items = [i.strip() for i in items]
		if items[0] == 'VERSION' or \
			items[0] == 'PATCHLEVEL':
			version += items[1]
			version += "."
		elif items[0] == 'SUBLEVEL':
			version += items[1]
		elif items[0] == 'EXTRAVERSION' and \
			items[-1] != items[0]:
			version += items[1]

	# Grab a list of files named localversion* and sort them
	localversions = os.listdir(base_dir)
	for x in range(len(localversions)-1,-1,-1):
		if localversions[x][:12] != "localversion":
			del localversions[x]
	localversions.sort()

	# Append the contents of each to the version string, stripping ALL whitespace
	for lv in localversions:
		version += "".join( " ".join( grabfile( base_dir+ "/" + lv ) ).split() )

	# Check the .config for a CONFIG_LOCALVERSION and append that too, also stripping whitespace
	kernelconfig = getconfig(base_dir+"/.config")
	if kernelconfig and "CONFIG_LOCALVERSION" in kernelconfig:
		version += "".join(kernelconfig["CONFIG_LOCALVERSION"].split())

	return (version,None)
