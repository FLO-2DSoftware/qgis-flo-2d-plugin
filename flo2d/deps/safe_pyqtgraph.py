"""Load pyqtgraph from QGIS if available, otherwise from external staging."""

import importlib
import sys

try:
    _pyqtgraph = importlib.import_module("pyqtgraph")
except ModuleNotFoundError as exc:
    if exc.name != "pyqtgraph":
        raise  # A dependency of pyqtgraph is missing; don't mask that failure.
    from .dependency_manager import stage_pyqtgraph

    _folder = str(stage_pyqtgraph())
    if _folder not in sys.path:
        sys.path.insert(0, _folder)
    importlib.invalidate_caches()
    _pyqtgraph = importlib.import_module("pyqtgraph")

# Preserve the previous `from pyqtgraph import *` public interface.
_names = getattr(_pyqtgraph, "__all__", None)
if _names is None:
    _names = [name for name in vars(_pyqtgraph) if not name.startswith("_")]
globals().update({name: getattr(_pyqtgraph, name) for name in _names})
__all__ = list(_names)
