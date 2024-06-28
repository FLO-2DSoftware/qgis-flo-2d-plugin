# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os

from qgis.core import NULL, QgsRectangle
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QIcon

# month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
#                "November", "December"]


def load_ui(name):
    ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "ui", name + ".ui")
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


def zoom(iface, porcentage):
    canvas = iface.mapCanvas()
    extend = canvas.extent()
    xMin = extend.xMinimum()
    xMax = extend.xMaximum()
    yMin = extend.yMinimum()
    yMax = extend.yMaximum()

    width = abs(xMin - xMax)
    height = abs(yMin - yMax)

    xMin = xMin + width * porcentage
    xMax = xMax - width * porcentage
    yMin = yMin + height * porcentage
    yMax = yMax - height * porcentage

    rect = QgsRectangle(xMin, yMin, xMax, yMax)
    canvas.setExtent(rect)
    canvas.refresh()

def center_feature(iface, feat, factor=4):
    iface.mapCanvas().setExtent(feat.geometry().boundingBox())
    iface.mapCanvas().zoomByFactor(factor)
    # iface.mapCanvas().zoomScale(1000)  
    
    
def zoom_show_n_cells(iface, cell_size, nCells):
    canvas = iface.mapCanvas()
    extend = canvas.extent()
    xMin = extend.xMinimum()
    xMax = extend.xMaximum()
    yMin = extend.yMinimum()
    yMax = extend.yMaximum()

    centerX = xMin + abs(xMin - xMax) / 2
    centerY = yMin + abs(yMin - yMax) / 2

    d = (nCells / 2) * cell_size
    xMin = centerX - d
    xMax = centerX + d
    yMin = centerY - d
    yMax = centerY + d

    rect = QgsRectangle(xMin, yMin, xMax, yMax)
    canvas.setExtent(rect)
    canvas.refresh()


def try_disconnect(signal, met):
    try:
        signal.disconnect(met)
    except TypeError:
        pass


def set_icon(btn, icon_file):
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    idir = os.path.join(os.path.dirname(parent_dir), "img")
    btn.setIcon(QIcon(os.path.join(idir, icon_file)))


def switch_to_selected(vlayer, combo_box, field="name", use_fid=False):
    if vlayer.selectedFeatureCount() == 1:
        feat = vlayer.selectedFeatures()[0]
        if use_fid is True:
            text = str(feat["fid"])
            idx = combo_box.findData(text)
            combo_box.setCurrentIndex(idx)
        else:
            text = feat[field]
            if text == NULL:
                text = ""
            idx = combo_box.findText(text)
            combo_box.setCurrentIndex(idx)


def field_reuse(layer):
    fields = layer.fields()
    for idx, _ in enumerate(fields):
        form_config = layer.editFormConfig()
        form_config.setReuseLastValue(idx, True)
        layer.setEditFormConfig(form_config)

