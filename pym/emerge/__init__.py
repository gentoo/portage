# To emulate old behavior, import everything from the normal emerge script
import imp
emerge = imp.load_source("emerge", "/usr/bin/emerge")
from emerge import *
del emerge, imp
