# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from PyQt4 import uic
from PyQt4.QtGui import QIcon
from qgis.core import QgsRectangle

month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def load_ui(name):
    ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           '..', 'ui',
                           name + '.ui')
    return uic.loadUiType(ui_file)


def center_canvas(iface, x, y):
    mc = iface.mapCanvas()
    cur_ext = mc.extent()
    center = cur_ext.center()
    dx = x - center.x()
    dy = y - center.y()
    x_min = cur_ext.xMinimum() + dx
    x_max = cur_ext.xMaximum() + dx
    y_min = cur_ext.yMinimum() + dy
    y_max = cur_ext.yMaximum() + dy
    rect = QgsRectangle(x_min, y_min, x_max, y_max)
    mc.setExtent(rect)
    mc.refresh()


def try_disconnect(signal, met):
    try:
        signal.disconnect(met)
    except TypeError:
        pass


def set_icon(btn, icon_file):
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    idir = os.path.join(os.path.dirname(parent_dir), 'img')
    btn.setIcon(QIcon(os.path.join(idir, icon_file)))


def switch_to_selected(vlayer, combo_box, field='name'):
    if vlayer.selectedFeatureCount() == 1:
        feat = vlayer.selectedFeatures()[0]
        text = feat[field]
        idx = combo_box.findText(text)
        combo_box.setCurrentIndex(idx)
