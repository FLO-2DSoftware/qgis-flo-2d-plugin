# flo2d/deps/safe_dask.py
import sys
import os
import importlib

deps_dir = os.path.dirname(__file__)
# Adjust this folder name to match where you extracte
dask_dir = os.path.join(deps_dir, 'dask')

if not os.path.isdir(dask_dir):
    raise ImportError(
        f"[FLO-2D] dask folder not found: {dask_dir}. "
        f"Extract the dask wheel contents into this directory."
    )

# Put vendored dask first on sys.path
if dask_dir in sys.path:
    sys.path.remove(dask_dir)
sys.path.insert(0, dask_dir)

# Clear any stale dask imports
for k in list(sys.modules.keys()):
    if k == "dask" or k.startswith("dask."):
        del sys.modules[k]
importlib.invalidate_caches()

import dask

# Make this module behave exactly like dask
sys.modules[__name__] = dask
