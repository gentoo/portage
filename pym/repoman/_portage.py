
'''repoman/_portage.py
Central location for the portage import.
There were problems when portage was imported by submodules
due to the portage instance was somehow different that the
initial portage import in main.py.  The later portage imports
did not contain the repo it was working on.  That repo was my cvs tree
and not listed in those subsequent portage imports.

All modules should import portage from this one

from repoman._portage import portage

Then continue to import the remaining portage modules needed
'''

import sys

from os import path as osp
pym_path = osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))))
sys.path.insert(0, pym_path)

import portage
portage._internal_caller = True
portage._disable_legacy_globals()
