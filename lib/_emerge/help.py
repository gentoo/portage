# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.output import bold, turquoise, green

def emerge_help():
	print(bold("emerge:")+" command-line interface to the Portage system")
	print(bold("Usage:"))
	print("   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] [ "+turquoise("ebuild")+" | "+turquoise("tbz2")+" | "+turquoise("file")+" | "+turquoise("@set")+" | "+turquoise("atom")+" ] [ ... ]")
	print("   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] < "+turquoise("@system")+" | "+turquoise("@world")+" >")
	print("   "+turquoise("emerge")+" < "+turquoise("--sync")+" | "+turquoise("--metadata")+" | "+turquoise("--info")+" >")
	print("   "+turquoise("emerge")+" "+turquoise("--resume")+" [ "+green("--pretend")+" | "+green("--ask")+" | "+green("--skipfirst")+" ]")
	print("   "+turquoise("emerge")+" "+turquoise("--help"))
	print(bold("Options:")+" "+green("-")+"["+green("abBcCdDefgGhjkKlnNoOpPqrsStuUvVwW")+"]")
	print("          [ " + green("--color")+" < " + turquoise("y") + " | "+ turquoise("n")+" >            ] [ "+green("--columns")+"    ]")
	print("          [ "+green("--complete-graph")+"             ] [ "+green("--deep")+"       ]")
	print("          [ "+green("--jobs") + " " + turquoise("JOBS")+" ] [ "+green("--keep-going")+" ] [ " + green("--load-average")+" " + turquoise("LOAD") + "            ]")
	print("          [ "+green("--newrepo")+"   ] [ "+green("--newuse")+"     ] [ "+green("--noconfmem")+"  ] [ "+green("--nospinner")+"   ]")
	print("          [ "+green("--oneshot")+"   ] [ "+green("--onlydeps")+"   ] [ "+ green("--quiet-build")+" [ " + turquoise("y") + " | "+ turquoise("n")+" ]        ]")
	print("          [ "+green("--reinstall ")+turquoise("changed-use")+"      ] [ " + green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >         ]")
	print(bold("Actions:")+"  [ "+green("--depclean")+" | "+green("--list-sets")+" | "+green("--search")+" | "+green("--sync")+" | "+green("--version")+"        ]")
	print()
	print("   For more help consult the man page.")
