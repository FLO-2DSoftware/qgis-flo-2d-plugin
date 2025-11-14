# flo2d/deps/safe_h5py.py
# Always use the plugin's own h5py build
import sys, os, importlib

abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
deps_dir = os.path.dirname(__file__)
h5py_dir = os.path.join(deps_dir, f"h5py_{abi}")       # e.g. deps/h5py_cp312
dll_dir  = os.path.join(h5py_dir, "h5py")     # vendored HDF5 DLLs from the PyPI wheel

if not os.path.isdir(h5py_dir):
    raise ImportError(f"[FLO-2D] h5py folder not found for {abi}: {h5py_dir}")
if not os.path.isdir(dll_dir):
    raise ImportError(f"[FLO-2D] Missing HDF5 DLLs: {dll_dir}")

# Put our extracted package first on sys.path
if h5py_dir in sys.path:
    sys.path.remove(h5py_dir)
sys.path.insert(0, h5py_dir)

# Clear any stale/namespace h5py
for k in list(sys.modules.keys()):
    if k == "h5py" or k.startswith("h5py."):
        del sys.modules[k]
importlib.invalidate_caches()

# Temporarily sandbox PATH so OSGeo4W\bin can't hijack DLLs during import
old_path = os.environ.get("PATH", "")
os.environ["PATH"] = dll_dir

try:
    # Prefer add_dll_directory on Win (Python 3.8+)
    try:
        os.add_dll_directory(dll_dir)  # type: ignore[attr-defined]
    except Exception:
        pass

    # QGIS ships NumPy natively
    import numpy  # noqa: F401

    # Import our h5py; loader now resolves against dll_dir first
    import h5py

finally:
    # Restore PATH no matter what
    os.environ["PATH"] = old_path

# Make this module behave exactly like h5py
sys.modules[__name__] = h5py
