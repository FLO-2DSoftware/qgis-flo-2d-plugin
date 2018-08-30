# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os.path
from math import ceil
from qgis.PyQt.QtCore import Qt


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


def m_fdata(model, i, j):
    """
    Return float of model data at index i, j. If the data cannot be converted to float, return NaN.
    """
    d = model.data(model.index(i, j), Qt.DisplayRole)
    if is_number(d):
        return float(d)
    else:
        return float('NaN')


def frange(start, stop=None, step=1):
    """
    frange generates a set of floating point values over the
    range [start, stop) with step size step
    frange([start,] stop [, step ])
    """

    if stop is None:
        for x in range(int(ceil(start))):
            yield x
    else:
        # create a generator expression for the index values
        indices = (i for i in range(0, int((stop-start)/step)))
        # yield results
        for i in indices:
            yield start + step * i


def is_true(s):
    return s in ['True', 'true', '1', 'T', 't', 'y', 'yes', 'yeah', 'yup', 'certainly', 'uh-huh']
