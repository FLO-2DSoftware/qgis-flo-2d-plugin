"""Stage FLO-2D binary dependencies outside the QGIS plugin directory.

Windows x64, CPython 3.9 and 3.12. The manager does not import the packages,
modify sys.path, or install anything into QGIS/Program Files. Wheel archives
must be supplied in the sibling packages/ directory.
"""

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from zipfile import ZipFile, BadZipFile

SUPPORTED_ABIS = frozenset({"cp39", "cp312"})
VERSIONS = {"h5py": "3.11.0", "cftime": "1.6.4.post1", "netCDF4": "1.7.2", "pyqtgraph": "0.13.7"}
MAX_ENTRIES = 10000
MAX_UNCOMPRESSED = 500 * 1024 * 1024


def _abi():
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def _wheel_path(name, version, abi):
    if name == "pyqtgraph":
        filename = f"pyqtgraph-{version}-py3-none-any.whl"
    else:
        filename = f"{name}-{version}-{abi}-{abi}-win_amd64.whl"
    return Path(__file__).resolve().parent / "packages" / filename


def _valid_install(folder, name, version, abi):
    package = folder / name
    metadata = folder / f"{name}-{version}.dist-info" / "METADATA"
    # netCDF4 metadata directories may differ in capitalization between builds.
    if not metadata.is_file():
        metadata = next((p / "METADATA" for p in folder.glob("*.dist-info")
                         if p.name.casefold() == f"{name}-{version}.dist-info".casefold()), metadata)
    return (package.joinpath("__init__.py").is_file()
            and metadata.is_file()
            and (name == "pyqtgraph" or any(p.name.endswith(f".{abi}-win_amd64.pyd") for p in package.rglob("*.pyd"))))


def _validate_wheel(wheel, name, version, abi):
    with ZipFile(wheel) as archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ValueError(f"Unexpected wheel entry count: {wheel}")
        seen = set()
        files = set()
        total = 0
        for info in infos:
            raw = info.filename
            parts = PurePosixPath(raw).parts
            if (not raw or raw.startswith("/") or "\\" in raw or ":" in raw
                    or not parts or any(p in ("..", ".", "") for p in parts)):
                raise ValueError(f"Unsafe wheel path: {raw!r}")
            # Reject symlinks and nonregular entries, even when encoded in ZIP metadata.
            mode = info.external_attr >> 16
            if info.create_system == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported wheel entry type: {raw!r}")
            key = "/".join(parts).rstrip("/").casefold()
            if key in seen:
                raise ValueError(f"Duplicate wheel entry: {raw!r}")
            seen.add(key)
            if not info.is_dir():
                files.add(raw)
                total += info.file_size
                if total > MAX_UNCOMPRESSED:
                    raise ValueError("Wheel exceeds uncompressed size limit")
        if f"{name}/__init__.py" not in files:
            raise ValueError(f"Missing {name}/__init__.py in {wheel.name}")
        metadata_name = f"{name}-{version}.dist-info/METADATA".casefold()
        if metadata_name not in {p.casefold() for p in files}:
            raise ValueError(f"Missing package metadata in {wheel.name}")
        if name != "pyqtgraph" and not any(p.startswith(f"{name}/") and p.endswith(f".{abi}-win_amd64.pyd") for p in files):
            raise ValueError(f"No {abi} compiled extension found in {wheel.name}")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise BadZipFile(f"CRC check failed for {corrupt}")
        return [info for info in infos if not info.is_dir()]


def stage_dependency(name):
    """Return the external package root, staging its bundled wheel if needed.

    This function does not select or import an already-installed system package.
    Loader wrappers should make that decision before calling this function.
    """
    from qgis.core import QgsApplication

    if name not in VERSIONS:
        raise ValueError(f"Unknown FLO-2D dependency: {name}")
    abi = _abi()
    if name != "pyqtgraph" and (os.name != "nt" or sys.maxsize <= 2**32 or abi not in SUPPORTED_ABIS):
        raise RuntimeError(f"No bundled {name} wheel for this platform / Python ABI: {abi}")
    version = VERSIONS[name]
    profile = Path(QgsApplication.qgisSettingsDirPath()).resolve()
    root = profile / "flo2d_dependencies" / name / version
    destination = root / ("py3" if name == "pyqtgraph" else abi)

    if destination.exists():
        if not _valid_install(destination, name, version, abi):
            raise RuntimeError(f"Existing {name} installation is incomplete: {destination}")
        print(f"Existing external {name} preserved: {destination}")
        return destination

    wheel = _wheel_path(name, version, abi)
    if not wheel.is_file():
        raise FileNotFoundError(f"Missing bundled wheel: {wheel}")
    members = _validate_wheel(wheel, name, version, abi)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}_{abi}_", dir=root))
    try:
        with ZipFile(wheel) as archive:
            for info in members:
                target = staging.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not _valid_install(staging, name, version, abi):
            raise RuntimeError(f"Extracted {name} wheel failed validation: {wheel}")
        try:
            staging.rename(destination)
        except OSError:
            # Another QGIS process may have finished staging the same wheel.
            if not _valid_install(destination, name, version, abi):
                raise
        print(f"{name} {version} ({abi}) available at: {destination}")
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def stage_h5py():
    return stage_dependency("h5py")


def stage_cftime():
    return stage_dependency("cftime")


def stage_netcdf4():
    return stage_dependency("netCDF4")


def stage_pyqtgraph():
    return stage_dependency("pyqtgraph")
