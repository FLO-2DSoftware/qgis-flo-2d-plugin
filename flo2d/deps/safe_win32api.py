# pylint: disable=W0401

import os
import sys


def get_file_path(*paths):
    temp_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(temp_dir, *paths)
    return path


def add_egg_or_wheel(name):
    dep = get_file_path("deps", name)
    sys.path.append(dep)


try:
    from win32api import *
except ImportError:

    add_egg_or_wheel("pywin32-306-cp312-cp312-win_arm64.whl")
    from win32api import *
