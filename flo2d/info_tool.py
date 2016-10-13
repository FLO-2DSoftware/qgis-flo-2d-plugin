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
from collections import OrderedDict
import functools


class InfoTool(QgsMapToolIdentify):

    feature_picked = pyqtSignal(str, int)

    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapToolIdentify.__init__(self, self.canvas)

    def canvasPressEvent(self, e):
        pass

#    def canvasReleaseEvent(self, e):
#        try:
#            pt = self.toMapCoordinates(e.pos())
#            feat = self.identify(e.x(), e.y(), QgsMapToolIdentify.LayerSelection)[0]
#            lyr_name = feat.mLayer.name()
#            lyr_id = feat.mLayer.id()
#            table = feat.mLayer.dataProvider().dataSourceUri().split('=')[-1]
#            fid = feat.mFeature.id()
#            self.pass_res(table, fid)
#        except IndexError as e:
#            print('Point outside layers extent.')
#            return

    def canvasReleaseEvent(self, e):
        pt = self.toMapCoordinates(e.pos())
        print pt.x(), pt.y()
        res = self.identify(e.x(), e.y(), QgsMapToolIdentify.TopDownAll)
        print "Found: {}".format(len(res))
        popup = QMenu()
#        popup.focusOutEvent().connect(self.clear_rubber)
        actions = {}
        lyrs_found = OrderedDict()
        for i, item in enumerate(res):
            lyr_name = item.mLayer.name()
            if not lyr_name in lyrs_found:
                lyrs_found.append(lyr_name)
            lyr_id = item.mLayer.id()
            table = item.mLayer.dataProvider().dataSourceUri().split('=')[-1]
            fid = item.mFeature.id()
            a_text = "{} {}".format(lyr_name, fid)
            print a_text
            actions[i] = QAction(a_text, None)
            actions[i].hovered.connect(functools.partial(self.show_rubber, lyr_id, fid))
            actions[i].triggered.connect(functools.partial(self.pass_res, table, fid))
            popup.addAction(actions[i])
        popup.exec_(self.canvas.mapToGlobal(QPoint(e.pos().x()+30, e.pos().y()-30)))

    def pass_res(self, table, fid):
        print('Picked: {} {}'.format(table, fid))
        self.feature_picked.emit(table, fid)

    def show_rubber(self, lyr_id, fid):
        pass

#    def activate(self):
#        pass
#
#    def deactivate(self):
#        pass

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
