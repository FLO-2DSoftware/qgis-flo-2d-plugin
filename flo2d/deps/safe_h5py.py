# flo2d/deps/safe_h5py.py
import sys, os, importlib

# Linux path: use system h5py for CI
if os.name != "nt":
    import h5py
    sys.modules[__name__] = h5py
else:
    # Windows path: always use the plugin bundled build
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    deps_dir = os.path.dirname(__file__)
    h5py_dir = os.path.join(deps_dir, 'h5py', f"h5py_{abi}")     # e.g. deps/h5py_cp312
    dll_dir  = os.path.join(h5py_dir, 'h5py')            # your working layout

    if not os.path.isdir(h5py_dir):
        raise ImportError(f"[FLO-2D] h5py folder not found for {abi}: {h5py_dir}")
    if not os.path.isdir(dll_dir):
        raise ImportError(f"[FLO-2D] Missing HDF5 DLLs: {dll_dir}")

    if h5py_dir in sys.path:
        sys.path.remove(h5py_dir)
    sys.path.insert(0, h5py_dir)

    for k in list(sys.modules.keys()):
        if k == "h5py" or k.startswith("h5py."):
            del sys.modules[k]
    importlib.invalidate_caches()

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = dll_dir
    try:
        try:
            os.add_dll_directory(dll_dir)  # on Py 3.8+
        except Exception:
            pass

        import numpy  # noqa: F401
        import h5py
    finally:
        os.environ["PATH"] = old_path

    sys.modules[__name__] = h5py
