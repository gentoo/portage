
import os
from portage.module import Modules

path = os.path.dirname(__file__)
# initial development debug info
#print("module path:", path)

module_controller = Modules(path=path, namepath="repoman.modules.vcs")

# initial development debug info
#print(module_controller.module_names)
module_names = module_controller.module_names[:]
