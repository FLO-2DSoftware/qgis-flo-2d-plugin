# pylint: disable=W0401

try:
    from win32api import *
except ImportError:
    from .. import utils

    utils.add_egg_or_wheel("pywin32-306-cp312-cp312-win_arm64.whl")
    from win32api import *
