# flo2d/deps/safe_h5py.py
import sys, os, importlib

abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
deps_dir = os.path.dirname(__file__)
h5py_dir = os.path.join(deps_dir, f"h5py_{abi}")   # e.g. deps/h5py_cp312 or deps/h5py_cp310
dll_dir  = os.path.join(h5py_dir, "h5py") # Windows vendored DLLs; on Linux, .so may live directly under h5py/

def _purge():
    for k in list(sys.modules.keys()):
        if k == "h5py" or k.startswith("h5py."):
            del sys.modules[k]
    importlib.invalidate_caches()

def _try_plugin():
    if not os.path.isdir(h5py_dir):
        return False
    # Prefer our extracted package
    if h5py_dir in sys.path:
        sys.path.remove(h5py_dir)
    sys.path.insert(0, h5py_dir)
    _purge()

    # Linux: some wheels rely on rpath ($ORIGIN/.libs), which “just works”;
    # if your wheel expects LD_LIBRARY_PATH, you can temporarily set it:
    if os.name != "nt" and os.path.isdir(dll_dir):
        old_ld = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = f"{dll_dir}:{old_ld}" if old_ld else dll_dir

    # Windows: prefer the vendored .libs if present
    if os.name == "nt" and os.path.isdir(dll_dir):
        try:
            os.add_dll_directory(dll_dir)  # Python 3.8+
        except Exception:
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

    import numpy  # required first
    import h5py as _h5py  # try our vendored copy

    sys.modules[__name__] = _h5py
    return True

def _try_system():
    _purge()
    import numpy  # ensure present
    import h5py as _h5py
    sys.modules[__name__] = _h5py
    return True

# 1) Try plugin vendor first
try:
    if _try_plugin():
        pass
    else:
        raise ImportError("Plugin h5py folder not found")
except Exception:
    # 2) Fallback for CI/dev runners: use system h5py if available
    try:
        _try_system()
    except Exception as e:
        raise ImportError(
            f"[FLO-2D] Could not import vendored h5py from {h5py_dir} "
            f"and no system h5py is available.\nOriginal error: {e}"
        )
