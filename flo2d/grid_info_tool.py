# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 FLO-2D Preprocessor tools for QGIS.
"""
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import QgsMapToolIdentify
from collections import OrderedDict
import functools


class GridInfoTool(QgsMapToolIdentify):

    grid_elem_picked = pyqtSignal(int)

    def __init__(self, canvas, lyrs):
        self.canvas = canvas
        self.lyrs = lyrs
        self.grid = None

        QgsMapToolIdentify.__init__(self, self.canvas)

    def canvasPressEvent(self, e):
        pass

    def canvasReleaseEvent(self, e):
        if self.grid:
            res = self.identify(e.x(), e.y(), [self.grid], QgsMapToolIdentify.ActiveLayer)
            if res:
                self.grid_elem_picked.emit(res[0].mFeature.id())
            else:
                self.grid_elem_picked.emit(-1)


    def deactivate(self):
        pass

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False

