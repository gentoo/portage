# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

import os
from os import path as osp
import sys

if osp.isfile(osp.abspath(osp.join(osp.dirname(__file__), "../../../../.portage_not_installed"))):
	sys.path.insert(0, osp.abspath(osp.join(osp.dirname(__file__), "../../../../lib")))
import portage

# -- Project information -----------------------------------------------------

project = 'portage'
copyright = '2020, Gentoo Authors' # pylint: disable=redefined-builtin
author = 'Gentoo Authors'

# The full version, including alpha/beta/rc tags
release = str(portage.VERSION)

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
	'sphinx.ext.autodoc',
	'sphinx_epytext',
]

# Add any paths that contain templates here, relative to this directory.
# templates_path = []

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
# exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_show_sourcelink = False
html_theme = 'sphinxdoc'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = []

autodoc_default_options = dict((opt, True) for opt in
	filter(None, os.environ.get('SPHINX_APIDOC_OPTIONS', '').split(',')))
