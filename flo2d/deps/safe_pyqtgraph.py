# pylint: disable=W0401

try:
    from pyqtgraph import *
except ImportError:
    from .. import utils

    utils.add_egg_or_wheel("pyqtgraph-0.13.7-py3-none-any.whl")
    from pyqtgraph import *
