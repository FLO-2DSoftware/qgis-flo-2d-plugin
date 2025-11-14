# pylint: disable=W0401

import sys
import importlib

try:
    import dask
except ImportError:
    from .. import utils
    utils.add_egg_or_wheel("dask-2025.11.0-py3-none-any.whl")
    dask = importlib.import_module("dask")

# Replace this module with the real dask module
sys.modules[__name__] = dask
