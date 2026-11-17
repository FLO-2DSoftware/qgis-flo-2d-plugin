"""FLO-2D dependency staging (phase 1: non-destructive h5py copy).

Run stage_h5py() from the QGIS Python Console. This module does not import
h5py, change sys.path, or modify an existing dependency installation.
"""

from pathlib import Path
import os
import shutil
import sys
import tempfile


def stage_h5py():
    """Copy the bundled Python-ABI-specific h5py tree outside the plugin.

    Returns the staged package root. Raises a clear exception on failure.
    Existing installations are never overwritten.
    """
    from qgis.core import QgsApplication

    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    source = Path(__file__).resolve().parent / "h5py" / f"h5py_{abi}"
    if not (source / "h5py" / "__init__.py").is_file():
        raise FileNotFoundError(f"FLO-2D bundled h5py is missing for {abi}: {source}")

    profile = Path(QgsApplication.qgisSettingsDirPath()).resolve()
    root = profile / "flo2d_dependencies" / "h5py"
    destination = root / f"h5py_{abi}"

    if destination.exists():
        if not (destination / "h5py" / "__init__.py").is_file():
            raise RuntimeError(f"Existing dependency folder is incomplete: {destination}")
        print(f"Existing external h5py directory preserved: {destination}")
        return destination

    root.mkdir(parents=True, exist_ok=True)
    # Temporary directory on the same volume so final rename is atomic.
    staging = Path(tempfile.mkdtemp(prefix=f".h5py_{abi}_", dir=root))
    try:
        shutil.copytree(source, staging / "package")
        staged_package = staging / "package"
        if not (staged_package / "h5py" / "__init__.py").is_file():
            raise RuntimeError("Staged h5py package failed verification")
        # No overwriting: fail safely if another process installed it meanwhile.
        if destination.exists():
            raise FileExistsError(f"Dependency appeared during staging: {destination}")
        staged_package.rename(destination)
        print(f"Staged bundled h5py ({abi}) at: {destination}")
        print("No imports or plugin loading paths were changed.")
        return destination
    finally:
        shutil.rmtree(staging, ignore_errors=True)
