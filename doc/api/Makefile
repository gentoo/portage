# Makefile for Sphinx documentation
#

SPHINX_APIDOC_OPTIONS = members,private-members,undoc-members,show-inheritance,ignore-module-all,inherited-members
export SPHINX_APIDOC_OPTIONS

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SOURCEDIR     = .
BUILDDIR      = build
TOPDIR        = ../..

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

clean:
	rm -rf $(BUILDDIR) $(SOURCEDIR)/api

$(BUILDDIR)/_sources/portage.rst:
	mkdir -p "$(BUILDDIR)/_sources"
	cp -pPR "$(SOURCEDIR)/conf.py" "$(SOURCEDIR)/index.rst" "$(BUILDDIR)/_sources"
	sphinx-apidoc -TPef -o  "$(BUILDDIR)/_sources" $(TOPDIR)/lib/_emerge
	sphinx-apidoc -TPef -o  "$(BUILDDIR)/_sources" $(TOPDIR)/lib/portage $(TOPDIR)/lib/portage/tests

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile $(BUILDDIR)/_sources/portage.rst
	@$(SPHINXBUILD) -M $@ "$(BUILDDIR)/_sources" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
