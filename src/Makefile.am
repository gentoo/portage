SUBDIRS 	=

bin_PROGRAMS	=
bindir = @PORTAGE_BASE@/bin
if BUILD_TBZ2TOOL
bin_PROGRAMS += tbz2tool
endif

if BUILD_MISSINGOS
SUBDIRS += python-missingos
endif

tbz2tool_SOURCES = tbz2tool.c

MAINTAINERCLEANFILES = Makefile.in
