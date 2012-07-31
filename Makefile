SHELL = /bin/sh
PN ?= portage
PF ?= portage
HOMEPAGE ?= http://www.gentoo.org/proj/en/portage/index.xml
PWD ?= $(shell pwd)
S ?= $(PWD)
WORKDIR ?= $(PWD)
DESTDIR = $(PWD)/image/
srcdir = $(S)
prefix = /usr
sysconfdir = /etc
exec_prefix = $(prefix)
bindir = $(exec_prefix)/bin
sbindir = $(exec_prefix)/sbin
libdir = $(exec_prefix)/lib
datarootdir = $(prefix)/share
datadir = $(datarootdir)
mandir = $(datarootdir)/man
docdir = $(datarootdir)/doc/$(PF)
htmldir = $(docdir)/html
portage_datadir = $(datarootdir)/$(PN)
portage_confdir = $(portage_datadir)/config
portage_setsdir = $(portage_confdir)/sets
portage_base = $(libdir)/$(PN)
EPYDOC_OPTS = -qqqqq --no-frames --show-imports
INSMODE = 0644
EXEMODE = 0755
DIRMODE = 0755
SYSCONFDIR_FILES = etc-update.conf dispatch-conf.conf
PORTAGE_CONFDIR_FILES = make.globals
LOGROTATE_FILES = elog-save-summary
BINDIR_FILES = ebuild egencache emerge emerge-webrsync \
	portageq quickpkg repoman
SBINDIR_FILES = archive-conf dispatch-conf emaint \
	env-update etc-update fixpackages regenworld
DOCS = ChangeLog NEWS RELEASE-NOTES

ifdef PYTHONPATH
	PYTHONPATH := $(srcdir)/pym:$(PYTHONPATH)
else
	PYTHONPATH := $(srcdir)/pym
endif

all: docbook epydoc

docbook:
	set -e; \
	touch "$(srcdir)/doc/fragment/date"; \
	$(MAKE) -C "$(srcdir)/doc" xhtml xhtml-nochunks

epydoc:
	set -e; \
	# workaround for bug 282760 \
	touch "$(srcdir)/pym/pysqlite2.py"; \
	env PYTHONPATH="$(PYTHONPATH)" epydoc \
		-o "$(WORKDIR)/epydoc" \
		--name $(PN) \
		--url "$(HOMEPAGE)" \
		$(EPYDOC_OPTS) \
		$$(cd "$(srcdir)" && find pym -name '*.py' | sed \
		-e s:/__init__.py$$:: \
		-e s:\.py$$:: \
		-e s:^pym/:: \
		-e s:/:.:g \
		| sort); \
	rm -f "$(srcdir)/pym/pysqlite2.py"* \
		"$(WORKDIR)/epydoc/pysqlite2-"* \
		"$(WORKDIR)/epydoc/api-objects.txt"; \

test:
	set -e; \
	"$(srcdir)/pym/portage/tests/runTests"; \

install:
	set -e; \
	cd "$(srcdir)/cnf"; \
	install -d -m$(DIRMODE) "$(DESTDIR)$(sysconfdir)"; \
	install -m$(INSMODE) $(SYSCONFDIR_FILES) "$(DESTDIR)$(sysconfdir)"; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(portage_confdir)"; \
	cd "$(srcdir)/cnf"; \
	install -m$(INSMODE) $(PORTAGE_CONFDIR_FILES) \
		"$(DESTDIR)$(portage_confdir)"; \
	install -m$(INSMODE) "$(srcdir)/cnf/make.conf" \
		"$(DESTDIR)$(portage_confdir)/make.conf.example"; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(portage_setsdir)"; \
	cd "$(S)/cnf/sets"; \
	install -m$(INSMODE) *.conf "$(DESTDIR)$(portage_setsdir)"; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(sysconfdir)/logrotate.d"; \
	cd "$(srcdir)/cnf/logrotate.d"; \
	install -m$(INSMODE) $(LOGROTATE_FILES) \
		"$(DESTDIR)$(sysconfdir)/logrotate.d"; \
	\
	for x in $$(cd "$(srcdir)" && find bin -type d) ; do \
		cd "$(srcdir)/$$x"; \
		install -d -m$(DIRMODE) "$(DESTDIR)$(portage_base)/$$x"; \
		files=$$(find . -mindepth 1 -maxdepth 1 -type f ! -type l); \
		if [ -n "$$files" ] ; then \
			install -m$(EXEMODE) $$files \
				"$(DESTDIR)$(portage_base)/$$x"; \
		fi; \
		symlinks=$$(find . -mindepth 1 -maxdepth 1 -type l); \
		if [ -n "$$symlinks" ] ; then \
			cp -P $$symlinks "$(DESTDIR)$(portage_base)/$$x"; \
		fi; \
	done; \
	\
	for x in $$(cd "$(srcdir)" && find pym/* -type d \
		! -path "pym/portage/tests*") ; do \
		cd "$(srcdir)/$$x"; \
		files=$$(echo *.py); \
		if [ -z "$$files" ] || [ "$$files" = "*.py" ]; then \
			# __pycache__ directories contain no py files \
			continue; \
		fi; \
		install -d -m$(DIRMODE) "$(DESTDIR)$(portage_base)/$$x"; \
		install -m$(INSMODE) $$files "$(DESTDIR)$(portage_base)/$$x"; \
	done; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(bindir)"; \
	relative_path=".."; \
	x=$(bindir) ; \
	y="$(portage_base)"; \
	if [ "$${x#$(prefix)}" != "$$x" ] && \
		[ "$${y#$(prefix)}" != "$$y" ]; then \
		x=$${x#$(prefix)}; \
		y=$${y#$(prefix)}; \
	fi; \
	x=$${x%/*}; \
	while [ -n "$$x" ] ; do \
		relative_path=$${relative_path}/..; \
		x=$${x%/*}; \
	done; \
	relative_path=$$relative_path$$y; \
	for x in $(BINDIR_FILES) ; do \
		ln -sf "$$relative_path/bin/$$x" \
			"$(DESTDIR)$(bindir)/$$x"; \
	done; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(sbindir)"; \
	relative_path=".."; \
	x=$(sbindir) ; \
	y="$(portage_base)"; \
	if [ "$${x#$(prefix)}" != "$$x" ] && \
		[ "$${y#$(prefix)}" != "$$y" ]; then \
		x=$${x#$(prefix)}; \
		y=$${y#$(prefix)}; \
	fi; \
	x=$${x%/*}; \
	while [ -n "$$x" ] ; do \
		relative_path=$${relative_path}/..; \
		x=$${x%/*}; \
	done; \
	relative_path=$$relative_path$$y; \
	for x in $(SBINDIR_FILES) ; do \
		ln -sf "$$relative_path/bin/$$x" \
			"$(DESTDIR)$(sbindir)/$$x"; \
	done; \
	\
	ln -sf "$$relative_path/bin/env-update" \
		"$(DESTDIR)$(sbindir)/update-env"; \
	ln -sf "$$relative_path/bin/etc-update" \
		"$(DESTDIR)$(sbindir)/update-etc"; \
	\
	# We install some minimal tests for use as a preinst sanity check. \
	# These tests must be able to run without a full source tree and \
	# without relying on a previous portage instance being installed. \
	install -d -m$(DIRMODE) \
		"$(DESTDIR)$(portage_base)/pym/portage/tests"; \
	install -m$(EXEMODE) "$(srcdir)/pym/portage/tests/runTests" \
		"$(DESTDIR)$(portage_base)/pym/portage/tests"; \
	cd "$(srcdir)/pym/portage/tests"; \
	install -m$(INSMODE) *.py \
		"$(DESTDIR)$(portage_base)/pym/portage/tests"; \
	install -d -m$(DIRMODE) \
		"$(DESTDIR)$(portage_base)/pym/portage/tests/lint"; \
	cd "$(srcdir)/pym/portage/tests/lint"; \
	install -m$(INSMODE) *.py __test__ \
		"$(DESTDIR)$(portage_base)/pym/portage/tests/lint"; \
	\
	install -d -m$(DIRMODE) "$(DESTDIR)$(docdir)"; \
	cd "$(srcdir)"; \
	install -m $(INSMODE) $(DOCS) "$(DESTDIR)$(docdir)"; \
	\
	for x in 1 5 ; do \
		install -d -m$(DIRMODE) "$(DESTDIR)$(mandir)/man$$x"; \
		cd "$(srcdir)/man"; \
		install -m$(INSMODE) *.$$x "$(DESTDIR)$(mandir)/man$$x"; \
	done; \
	\
	if [ -f "$(srcdir)/doc/portage.html" ] ; then \
		install -d -m$(DIRMODE) "$(DESTDIR)$(htmldir)"; \
		cd "$(srcdir)/doc"; \
		install -m$(INSMODE) *.html "$(DESTDIR)$(htmldir)"; \
	fi; \
	\
	if [ -d "$(WORKDIR)/epydoc" ] ; then \
		install -d -m$(DIRMODE) "$(DESTDIR)$(htmldir)"; \
		cp -pPR "$(WORKDIR)/epydoc" \
			"$(DESTDIR)$(htmldir)/api"; \
		cd "$(DESTDIR)$(htmldir)/api"; \
		find . -type d | xargs chmod $(DIRMODE); \
		find . -type f | xargs chmod $(INSMODE); \
	fi; \

clean:
	set -e; \
	$(MAKE) -C "$(srcdir)/doc" clean; \
	rm -rf "$(srcdir)/pym/pysqlite2.py"* \
		"$(WORKDIR)/epydoc"; \

.PHONY: all clean docbook epydoc install test
