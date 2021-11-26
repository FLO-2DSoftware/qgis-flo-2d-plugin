# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


BC_BORDER = None  # Static variable used to hold BC for type 5 outflow.
MIN_ELEVS = 0
MAX_ELEVS = 0

grid_index = {}

from heapq import nsmallest
from itertools import filterfalse
import os.path
import io
import csv
from math import ceil
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QApplication

def get_BC_Border():
    global BC_BORDER
    return BC_BORDER

def set_BC_Border(val):
    global BC_BORDER
    BC_BORDER = val

def get_min_max_elevs():
    global MIN_ELEVS, MAX_ELEVS
    return MIN_ELEVS, MAX_ELEVS

def set_min_max_elevs(mini, maxi):
    global MIN_ELEVS, MAX_ELEVS
    MIN_ELEVS, MAX_ELEVS = mini, maxi

def is_grid_index():
    global grid_index
    if grid_index:
        return True
    else:
        return False
    
def get_grid_index():
    global grid_index
    return grid_index

def set_grid_index(val):
    global grid_index
    grid_index = val
    
def clear_grid_index():  
    global grid_index
    for key, value in grid_index.items():
        grid_index[key][1] = 0.0
        grid_index[key][2] = 0

def get_file_path(*paths):
    temp_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(temp_dir, *paths)
    return path


def add_egg_or_wheel(name):
    import sys

    dep = get_file_path("deps", name)
    sys.path.append(dep)


def is_number(s):
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def m_fdata(model, i, j):
    """
    Return float of model data at index i, j. If the data cannot be converted to float, return NaN.
    """
    d = model.data(model.index(i, j), Qt.DisplayRole)
    if is_number(d):
        return float(d)
    else:
        return float("NaN")


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
        indices = (i for i in range(0, int((stop - start) / step)))
        # yield results
        for i in indices:
            yield start + step * i


def is_true(s):
    s = str(s).lower().strip()
    return s in [
        "true",
        "1",
        "t",
        "y",
        "yes",
        "yeah",
        "yup",
        "certainly",
        "uh-huh",
    ]


def float_or_zero(value):
    try:
        if value is None:
            return 0
        if type(value) is float:
            return value
        if type(value) is int:
            return float(value)
        if type(value) is str:
            if value == "":
                return 0
            elif value == "None":
                return 0
            else:
                return float(value)
        if value.text() == "":
            return 0.0
        else:
            return float(value.text())
    except Exception:
        return 0.0

def second_smallest(numbers):
    s = set()
    sa = s.add
    un = (sa(n) or n for n in filterfalse(s.__contains__, numbers))
    return nsmallest(2, un)[-1]  

def int_or_zero(value):
    #     if value is None:
    #         return 0
    #     elif value.text() == "":
    #         return 0
    #     else:
    #         return int(value.text())

    if value is None:
        return 0
    if type(value) is int:
        return value
    if type(value) is str:
        if value == "":
            return 0
        elif value == "None":
            return 0
        else:
            return int(value)
    elif value.text() == "":
        return 0
    else:
        return int(value.text())

def time_taken(ini, fin):  
    time_passed = round((fin - ini)/60.0 , 2)
    hours, rem = divmod(fin - ini, 3600)
    minutes, seconds = divmod(rem, 60)            
    time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))
    return time_passed  

def Msge(msg_string, icon):
    msgBox = QMessageBox()
    msgBox.setWindowTitle("FLO-2D")
    if icon == "Info":
        msgBox.setIcon(QMessageBox.Information)
    elif icon == "Error":
        msgBox.setIcon(QMessageBox.Critical)
    elif icon == "Warning":
        msgBox.setIcon(QMessageBox.Warning)
    msgBox.setText(msg_string)
    msgBox.exec_()


def copy_tablewidget_selection(tablewidget):
    selection = tablewidget.selectedIndexes()
    if selection:
        rows = sorted(index.row() for index in selection)
        columns = sorted(index.column() for index in selection)
        rowcount = rows[-1] - rows[0] + 1
        colcount = columns[-1] - columns[0] + 1
        table = [[""] * colcount for _ in range(rowcount)]
        for index in selection:
            row = index.row() - rows[0]
            column = index.column() - columns[0]
            table[row][column] = str(index.data())
        stream = io.StringIO()
        csv.writer(stream, delimiter="\t").writerows(table)
        QApplication.clipboard().setText(stream.getvalue())

 