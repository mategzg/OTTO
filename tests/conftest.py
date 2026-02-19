import os
import sys
from importlib import util as importlib_util

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SCRIPTS_INIT = os.path.join(ROOT, "scripts", "__init__.py")
if os.path.isfile(SCRIPTS_INIT):
    spec = importlib_util.spec_from_file_location(
        "scripts",
        SCRIPTS_INIT,
        submodule_search_locations=[os.path.join(ROOT, "scripts")],
    )
    if spec and spec.loader:
        module = importlib_util.module_from_spec(spec)
        sys.modules["scripts"] = module
        spec.loader.exec_module(module)
