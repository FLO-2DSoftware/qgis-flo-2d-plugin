# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                              -------------------
        begin                : 2016-08-28
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import QgsMapToolIdentify
import functools


class InfoTool(QgsMapToolIdentify):

    feature_picked = pyqtSignal(str, int)

    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolIdentify.__init__(self, self.canvas)

    def canvasPressEvent(self, e):
        pass

    def canvasReleaseEvent(self, e):
        pt = self.toMapCoordinates(e.pos())
        feat = self.identify(e.x(), e.y(), QgsMapToolIdentify.LayerSelection)[0]
        lyr_name = feat.mLayer.name()
        lyr_id = feat.mLayer.id()
        table = feat.mLayer.dataProvider().dataSourceUri().split('=')[-1]
        fid = feat.mFeature.id()
        self.pass_res(table, fid)

    def pass_res(self, table, fid):
        print "Picked: {} {}".format(table, fid)
        self.feature_picked.emit(table, fid)

    def activate(self):
        pass

    def deactivate(self):
        pass

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False



