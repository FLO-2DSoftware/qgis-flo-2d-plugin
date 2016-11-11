# pylint: disable=W0401

try:
    from pyqtgraph import *
except ImportError:
    from .. import utils
    utils.add_egg('pyqtgraph-0.9.10-py2.7.egg')
    from pyqtgraph import *
