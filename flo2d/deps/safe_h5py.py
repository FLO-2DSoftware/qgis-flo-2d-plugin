"""Load h5py for FLO-2D, preferring the QGIS Python environment.

Reuse an already imported h5py; otherwise use the installed package if
available. On Windows, stage the bundled wheel in the QGIS profile only when
h5py is not installed. Never replace an already loaded native extension.
"""

import importlib.util
import os
import sys
from pathlib import Path


_h5py = sys.modules.get("h5py")

if _h5py is None:
    # A discoverable installation is authoritative. If its import fails (for
    # example due to a missing DLL), surface that error rather than mixing
    # another HDF5 build into the same QGIS process.
    if importlib.util.find_spec("h5py") is not None:
        import h5py as _h5py
    elif os.name != "nt":
        raise ImportError("[FLO-2D] h5py is not installed in this Python environment")
    else:
        from .dependency_manager import stage_h5py

        package_root = Path(stage_h5py())
        package_dir = package_root / "h5py"
        if not (package_dir / "__init__.py").is_file():
            raise ImportError(f"[FLO-2D] Incomplete staged h5py package: {package_root}")

        dll_handles = []
        if hasattr(os, "add_dll_directory"):
            for directory in (package_dir, package_root / "h5py.libs"):
                if directory.is_dir():
                    dll_handles.append(os.add_dll_directory(str(directory)))

        root_string = str(package_root)
        sys.path.insert(0, root_string)
        try:
            import numpy  # noqa: F401
            import h5py as _h5py
        except Exception:
            # Remove only the path entry we inserted.
            sys.path.remove(root_string)
            for handle in dll_handles:
                handle.close()
            raise
        else:
            # Keep Windows DLL directories registered while h5py is in use.
            _h5py._flo2d_dll_handles = dll_handles

# Preserve: from flo2d.deps import safe_h5py as h5py
sys.modules[__name__] = _h5py
