"""Stage FLO-2D's bundled h5py ZIP outside the QGIS plugin directory.

This module does not import h5py or change sys.path. It preserves an existing
external installation, including one created by the earlier copy-based manager.
"""

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZipFile


# Guard against unexpectedly large or malformed dependency archives.
_MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
_MAX_ENTRIES = 5000


def _validate_archive(archive, abi):
    """Validate ZIP contents and return its file entries for safe extraction."""
    prefix = f"h5py_{abi}/"
    entries = []
    total = 0
    with ZipFile(archive) as zf:
        infos = zf.infolist()
        if not infos or len(infos) > _MAX_ENTRIES:
            raise ValueError(f"Invalid number of ZIP entries: {archive}")
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (
                "\\" in name
                or name.startswith("/")
                or not name.startswith(prefix)
                or ".." in path.parts
                or any(part in ("", ".") for part in path.parts)
                or ":" in name
            ):
                raise ValueError(f"Unsafe ZIP member: {name!r}")
            # Reject Unix symlinks (and other special file types).
            mode = info.external_attr >> 16
            if info.create_system == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported ZIP member type: {name!r}")
            if info.is_dir():
                continue
            total += info.file_size
            if total > _MAX_UNCOMPRESSED_BYTES:
                raise ValueError(f"ZIP exceeds size limit: {archive}")
            entries.append(info)

        names = {info.filename for info in entries}
        if prefix + "h5py/__init__.py" not in names:
            raise ValueError(f"ZIP lacks h5py/__init__.py: {archive}")
        pyds = [n for n in names if n.lower().endswith(".pyd")]
        if os.name == "nt" and not pyds:
            raise ValueError(f"ZIP lacks compiled .pyd extensions: {archive}")
        if os.name == "nt" and not any(f".{abi}-" in n for n in pyds):
            raise ValueError(f"ZIP has no extensions for {abi}: {archive}")
        if zf.testzip() is not None:
            raise BadZipFile(f"ZIP CRC verification failed: {archive}")
    return entries


def stage_h5py():
    """Stage h5py from its ABI-specific ZIP; return the external package root.

    Existing external installations are never overwritten. A fresh ZIP is
    extracted into a temporary directory and then renamed into place.
    """
    from qgis.core import QgsApplication

    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    profile = Path(QgsApplication.qgisSettingsDirPath()).resolve()
    root = profile / "flo2d_dependencies" / "h5py"
    destination = root / f"h5py_{abi}"

    if destination.exists():
        if not (destination / "h5py" / "__init__.py").is_file():
            raise RuntimeError(f"Existing dependency directory is incomplete: {destination}")
        print(f"Existing external h5py directory preserved: {destination}")
        return destination

    archive = Path(__file__).resolve().parent / "packages" / f"h5py_{abi}.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"Missing bundled h5py archive for {abi}: {archive}")

    # Validate before creating any destination directories.
    entries = _validate_archive(archive, abi)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".h5py_{abi}_", dir=root))
    try:
        package = staging / f"h5py_{abi}"
        with ZipFile(archive) as zf:
            for info in entries:
                relative = PurePosixPath(info.filename)
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        if not (package / "h5py" / "__init__.py").is_file():
            raise RuntimeError(f"Extracted h5py package is incomplete: {package}")
        if not list((package / "h5py").glob("*.pyd")):
            raise RuntimeError(f"Extracted h5py package has no compiled extensions: {package}")

        # Do not overwrite a package installed by another QGIS process.
        if destination.exists():
            raise FileExistsError(f"External dependency appeared during staging: {destination}")
        package.rename(destination)
        print(f"Staged h5py ({abi}) from ZIP at: {destination}")
        print("No imports or plugin loading paths were changed.")
        return destination
    finally:
        shutil.rmtree(staging, ignore_errors=True)
