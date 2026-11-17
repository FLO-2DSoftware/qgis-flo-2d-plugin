"""Load netCDF4 from QGIS if available, otherwise from FLO-2D's external wheel."""

import importlib
import importlib.util
import os
from pathlib import Path
import sys

# netCDF4 imports cftime; establish the selected cftime module first.
from . import safe_cftime as cftime  # noqa: F401

# Keep DLL directory handles alive for the lifetime of the Python process.
# Store them outside this shim because its sys.modules entry is replaced below.
_DLL_HANDLES_KEY = "_flo2d_netcdf4_dll_handles"

if os.name == "nt" and "netCDF4" not in sys.modules and importlib.util.find_spec("netCDF4") is None:
    from .dependency_manager import stage_netcdf4

    package_root = Path(stage_netcdf4())
    libs_dir = package_root / "netCDF4.libs"
    if not libs_dir.is_dir():
        # Case-insensitive filesystem names are common on Windows, but do not assume them.
        libs_dir = next((p for p in package_root.iterdir()
                         if p.is_dir() and p.name.casefold() == "netcdf4.libs"), None)
    if libs_dir is not None and hasattr(os, "add_dll_directory"):
        handles = getattr(sys, _DLL_HANDLES_KEY, None)
        if handles is None:
            handles = []
            setattr(sys, _DLL_HANDLES_KEY, handles)
        handles.append(os.add_dll_directory(str(libs_dir)))

    package_path = str(package_root)
    if package_path not in sys.path:
        sys.path.insert(0, package_path)
    importlib.invalidate_caches()

# An installed package is not necessarily compatible. If import fails, report it
# instead of switching native extensions in a partially initialized process.
try:
    importlib.import_module("numpy")
    _module = importlib.import_module("netCDF4")
except ImportError as exc:
    raise ImportError("[FLO-2D] Unable to load netCDF4; check QGIS and FLO-2D dependencies") from exc

sys.modules[__name__] = _module
