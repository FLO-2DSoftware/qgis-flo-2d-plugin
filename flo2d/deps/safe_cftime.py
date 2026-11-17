"""Load cftime from QGIS if available, otherwise from FLO-2D's external wheel."""

import importlib
import importlib.util
import os
import sys

if os.name == "nt" and "cftime" not in sys.modules and importlib.util.find_spec("cftime") is None:
    from .dependency_manager import stage_cftime

    package_root = str(stage_cftime())
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    importlib.invalidate_caches()

# Do not clear an existing cftime module: compiled extensions cannot be safely reloaded.
try:
    _module = importlib.import_module("cftime")
except ImportError as exc:
    raise ImportError("[FLO-2D] Unable to load cftime; check QGIS and FLO-2D dependencies") from exc

sys.modules[__name__] = _module