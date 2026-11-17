"""Load h5py for FLO-2D without replacing an already loaded native module.

Windows: prefer the external, profile-local copy staged by dependency_manager.
Non-Windows: use the environment's installed h5py.
"""

import os
import sys
from pathlib import Path


if os.name != "nt":
    import h5py as _h5py
else:
    # Native extensions cannot safely be unloaded and replaced in a live QGIS
    # process. Respect any h5py that another plugin has already imported.
    _h5py = sys.modules.get("h5py")

    if _h5py is None:
        from .dependency_manager import stage_h5py

        abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
        bundled = Path(__file__).resolve().parent / "h5py" / f"h5py_{abi}"

        try:
            package_root = Path(stage_h5py())
        except (OSError, RuntimeError) as exc:
            # Staging may fail on a read-only profile or an incomplete copy.
            # The bundled package remains available during migration.
            if not (bundled / "h5py" / "__init__.py").is_file():
                raise ImportError(
                    f"[FLO-2D] Cannot stage or locate h5py for {abi}"
                ) from exc
            package_root = bundled

        package_dir = package_root / "h5py"
        if not (package_dir / "__init__.py").is_file():
            raise ImportError(f"[FLO-2D] Incomplete h5py package: {package_root}")

        # Keep this handle alive: closing it removes the directory from the
        # Windows DLL search path used by Python extension modules.
        _dll_handle = None
        if hasattr(os, "add_dll_directory"):
            try:
                _dll_handle = os.add_dll_directory(str(package_dir))
            except OSError as exc:
                raise ImportError(
                    f"[FLO-2D] Cannot register h5py DLL directory: {package_dir}"
                ) from exc

        # Use our selected package before any QGIS site-packages copy.
        root_string = str(package_root)
        if root_string in sys.path:
            sys.path.remove(root_string)
        sys.path.insert(0, root_string)

        try:
            import numpy  # noqa: F401
            import h5py as _h5py
            # The wrapper is replaced in sys.modules below, so attach the
            # handle to the long-lived h5py module itself.
            if _dll_handle is not None:
                _h5py._flo2d_dll_handle = _dll_handle
        except Exception:
            # Do not leave a broken directory at the front of sys.path.
            if root_string in sys.path:
                sys.path.remove(root_string)
            if _dll_handle is not None:
                _dll_handle.close()
            raise

# Preserve the historical import style:
#     from flo2d.deps import safe_h5py as h5py
sys.modules[__name__] = _h5py
