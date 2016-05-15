
import os.path

REPOMAN_BASE_PATH = os.path.join(os.sep, os.sep.join(os.path.realpath(__file__.rstrip("co")).split(os.sep)[:-3]))

_not_installed = os.path.isfile(os.path.join(REPOMAN_BASE_PATH, ".repoman_not_installed"))
