"""Stage FLO-2D's Windows h5py wheel outside the QGIS plugin directory.

No h5py import or sys.path modification occurs here. The current safe_h5py
wrapper can continue calling stage_h5py() unchanged.
"""

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZipFile

H5PY_VERSION = "3.11.0"
SUPPORTED_ABIS = {"cp39", "cp312"}
MAX_ENTRIES = 5000
MAX_UNCOMPRESSED = 300 * 1024 * 1024


def _abi():
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def _wheel_path(abi):
    filename = f"h5py-{H5PY_VERSION}-{abi}-{abi}-win_amd64.whl"
    return Path(__file__).resolve().parent / "packages" / filename


def _valid_install(folder, abi):
    package = folder / "h5py"
    metadata = folder / f"h5py-{H5PY_VERSION}.dist-info" / "METADATA"
    return (
        (package / "__init__.py").is_file()
        and metadata.is_file()
        and any(f".{abi}-win_amd64.pyd" in p.name for p in package.glob("*.pyd"))
    )


def _validated_members(wheel, abi):
    """Validate expected wheel layout and all member paths before extraction."""
    with ZipFile(wheel) as zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ValueError(f"Unexpected wheel entry count: {wheel}")
        names = set()
        total = 0
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (not name or name.startswith("/") or "\\" in name or ":" in name
                    or ".." in path.parts or any(p in ("", ".") for p in path.parts)):
                raise ValueError(f"Unsafe wheel path: {name!r}")
            mode = info.external_attr >> 16
            if info.create_system == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported wheel member type: {name!r}")
            if not info.is_dir():
                if name in names:
                    raise ValueError(f"Duplicate wheel member: {name!r}")
                names.add(name)
                total += info.file_size
                if total > MAX_UNCOMPRESSED:
                    raise ValueError("Wheel exceeds extraction size limit")
        required = {"h5py/__init__.py", f"h5py-{H5PY_VERSION}.dist-info/METADATA"}
        if not required.issubset(names):
            raise ValueError(f"Missing required h5py wheel files: {required - names}")
        if not any(n.startswith("h5py/") and n.endswith(f".{abi}-win_amd64.pyd") for n in names):
            raise ValueError(f"Wheel lacks {abi} Windows extensions: {wheel}")
        if zf.testzip() is not None:
            raise BadZipFile(f"Wheel CRC check failed: {wheel}")
        return [i for i in infos if not i.is_dir()]


def stage_h5py():
    """Return external h5py package root, staging the wheel when necessary.

    Does not overwrite existing installations or import h5py. Requires a
    writable QGIS user profile on Windows x64 and a supported CPython ABI.
    """
    from qgis.core import QgsApplication

    abi = _abi()
    if os.name != "nt" or sys.maxsize <= 2**32 or abi not in SUPPORTED_ABIS:
        raise RuntimeError(f"No bundled h5py wheel for this platform / Python ABI: {abi}")

    profile = Path(QgsApplication.qgisSettingsDirPath()).resolve()
    root = profile / "flo2d_dependencies" / "h5py" / H5PY_VERSION
    destination = root / abi

    if destination.exists():
        if not _valid_install(destination, abi):
            raise RuntimeError(f"Existing external h5py installation is incomplete: {destination}")
        print(f"Existing external h5py preserved: {destination}")
        return destination

    wheel = _wheel_path(abi)
    if not wheel.is_file():
        raise FileNotFoundError(f"Missing bundled h5py wheel: {wheel}")
    members = _validated_members(wheel, abi)

    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".h5py_{abi}_", dir=root))
    try:
        with ZipFile(wheel) as zf:
            for info in members:
                target = staging.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not _valid_install(staging, abi):
            raise RuntimeError(f"Extracted h5py wheel failed validation: {wheel}")
        try:
            staging.rename(destination)
        except FileExistsError:
            # A concurrent QGIS process may have installed the same wheel.
            if not _valid_install(destination, abi):
                raise RuntimeError(f"Concurrent installation is incomplete: {destination}")
        print(f"h5py {H5PY_VERSION} ({abi}) available at: {destination}")
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
