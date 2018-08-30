# pylint: disable=W0401

try:
    from pyqtgraph import *
except ImportError:
    from .. import utils
    utils.add_egg('pyqtgraph-0.10.0-py3.6.egg')
    from pyqtgraph import *
