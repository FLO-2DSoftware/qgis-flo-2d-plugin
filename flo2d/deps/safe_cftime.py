# flo2d/deps/safe_cftime.py
import sys, os, importlib

# --- Linux: use system cftime (for CI) ---
if os.name != "nt":
    import cftime
    sys.modules[__name__] = cftime

# --- Windows: use vendored extracted cftime_cpXXX ---
else:
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    deps_dir = os.path.dirname(__file__)
    cftime_dir = os.path.join(deps_dir, 'cftime', f"cftime_{abi}")   # e.g. deps/cftime_cp312

    if not os.path.isdir(cftime_dir):
        raise ImportError(
            f"[FLO-2D] cftime folder not found for {abi}: {cftime_dir}\n"
            "Extract the cftime wheel into this directory."
        )

    # Put cftime_cpXXX first on sys.path
    if cftime_dir in sys.path:
        sys.path.remove(cftime_dir)
    sys.path.insert(0, cftime_dir)

    # Clear stale imports
    for k in list(sys.modules.keys()):
        if k == "cftime" or k.startswith("cftime."):
            del sys.modules[k]
    importlib.invalidate_caches()

    import cftime

    # Alias shim to real module
    sys.modules[__name__] = cftime
