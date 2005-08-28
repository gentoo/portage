#!/usr/bin/python -O

import profile,time,sys,os
sys.path = ["/usr/lib/portage/bin","/usr/lib/portage/pym"]+sys.path

def clock():
	return time.time()
profile.time.clock = clock

profile.run("import emerge", os.getcwd()+"/prof")

class StatsProcesser:
	def __init__(self, stats):
		self.output = []
		self.last = ""
		import sys
		sys.stdout = self
		stats.print_stats()
		sys.stdout = sys.__stdout__
		funcs = ["?"]
		for line in self.output:
			spline = line.split()
			if len(spline) == 6 and spline[0][0].isdigit():
				func = spline[5][spline[5].index("(")+1:-1]
				print line
				if func not in funcs:
					funcs.append(func)
					func = "\\(" + func + "\\)"
					stats.print_callers(func)

	def write(self, text):
		new = self.last + text
		new = new.split("\n")
		if len(new) > 1:
			self.output += new[:-1]
		self.last = new[-1]

import pstats
p = pstats.Stats("prof")
dir(p)
p.sort_stats("time")
p.print_stats()

sp = StatsProcesser(p)
