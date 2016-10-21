# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os.path


def get_file_path(*paths):
    temp_dir = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(temp_dir, *paths)
    return path


def add_egg(name):
    import sys
    dep = get_file_path('deps', name)
    sys.path.append(dep)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
    except TypeError:
        return False

