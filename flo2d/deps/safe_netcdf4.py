# flo2d/deps/safe_netcdf4.py
import sys, os, importlib

# --- Linux: use system netCDF4 for GitHub Actions ---
if os.name != "nt":
    import numpy  # ensure dependencies are ready
    import netCDF4
    sys.modules[__name__] = netCDF4

# --- Windows: load vendored wheel inside plugin ---
else:
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    deps_dir = os.path.dirname(__file__)
    netcdf_dir = os.path.join(deps_dir, f"netcdf4_{abi}")   # e.g. deps/netcdf4_cp312
    dll_dir    = os.path.join(netcdf_dir, "netCDF4")        # where DLLs usually are

    if not os.path.isdir(netcdf_dir):
        raise ImportError(f"[FLO-2D] netCDF4 folder not found for {abi}: {netcdf_dir}")
    if not os.path.isdir(dll_dir):
        raise ImportError(f"[FLO-2D] Missing DLLs: {dll_dir}")

    # Prepend to sys.path
    if netcdf_dir in sys.path:
        sys.path.remove(netcdf_dir)
    sys.path.insert(0, netcdf_dir)

    # Clear stale partial imports
    for k in list(sys.modules.keys()):
        if k == "netCDF4" or k.startswith("netCDF4."):
            del sys.modules[k]
    importlib.invalidate_caches()

    # Sandbox PATH so OSGeo4W doesn’t override DLLs
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = dll_dir
    try:
        try:
            os.add_dll_directory(dll_dir)  # Python 3.8+
        except Exception:
            pass

        import numpy  # ABI compatibility
        import netCDF4

    finally:
        os.environ["PATH"] = old_path

    sys.modules[__name__] = netCDF4
