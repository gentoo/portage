# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import platform
import subprocess

from portage import _unicode_decode

def get_vm_info():

	vm_info = {}

	env = os.environ.copy()
	env["LC_ALL"] = "C"

	if platform.system() == 'Linux':
		try:
			proc = subprocess.Popen(["free"],
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
		except OSError:
			pass
		else:
			output = _unicode_decode(proc.communicate()[0])
			if proc.wait() == os.EX_OK:
				for line in output.splitlines():
					line = line.split()
					if len(line) < 2:
						continue
					if line[0] == "Mem:":
						try:
							vm_info["ram.total"] = int(line[1]) * 1024
						except ValueError:
							pass
						if len(line) > 3:
							try:
								vm_info["ram.free"] = int(line[3]) * 1024
							except ValueError:
								pass
					elif line[0] == "Swap:":
						try:
							vm_info["swap.total"] = int(line[1]) * 1024
						except ValueError:
							pass
						if len(line) > 3:
							try:
								vm_info["swap.free"] = int(line[3]) * 1024
							except ValueError:
								pass

	else:

		try:
			proc = subprocess.Popen(["sysctl", "-a"],
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
		except OSError:
			pass
		else:
			output = _unicode_decode(proc.communicate()[0])
			if proc.wait() == os.EX_OK:
				for line in output.splitlines():
					line = line.split(":", 1)
					if len(line) != 2:
						continue
					line[1] = line[1].strip()
					if line[0] == "hw.physmem":
						try:
							vm_info["ram.total"] = int(line[1])
						except ValueError:
							pass
					elif line[0] == "vm.swap_total":
						try:
							vm_info["swap.total"] = int(line[1])
						except ValueError:
							pass
					elif line[0] == "Free Memory Pages":
						if line[1][-1] == "K":
							try:
								vm_info["ram.free"] = int(line[1][:-1]) * 1024
							except ValueError:
								pass

	return vm_info
