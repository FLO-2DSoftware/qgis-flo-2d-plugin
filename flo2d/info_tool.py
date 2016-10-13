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
from qgis.gui import QgsMapToolIdentify, QgsRubberBand
from collections import OrderedDict
import functools


class InfoTool(QgsMapToolIdentify):

    feature_picked = pyqtSignal(str, int)

    def __init__(self, canvas, lyrs):
        self.canvas = canvas
        self.lyrs = lyrs
        self.rb = None
        QgsMapToolIdentify.__init__(self, self.canvas)

    def canvasPressEvent(self, e):
        self.clear_rubber()

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
        ll = self.lyrs.list_group_vlayers(self.lyrs.group)
        res = self.identify(e.x(), e.y(), ll, QgsMapToolIdentify.TopDownAll)
#        print "Found: {}".format(len(res))
        lyrs_found = OrderedDict()
        for i, item in enumerate(res):
            lyr_name = item.mLayer.name()
            lyr_id = item.mLayer.id()
            table = item.mLayer.dataProvider().dataSourceUri().split('=')[-1]
            fid = item.mFeature.id()
            if not lyr_name in lyrs_found.keys():
                lyrs_found[lyr_name] = {'lid': lyr_id, 'table': table, 'fids': []}
            else:
                pass
            lyrs_found[lyr_name]['fids'].append(fid)
        popup = QMenu()
        sm = {}
        actions = {}
        for i, ln in enumerate(lyrs_found.keys()):
            lid = lyrs_found[ln]['lid']
            tab = lyrs_found[ln]['table']
            sm[i] = QMenu(ln)
            actions[i] = {}
            if len(lyrs_found[ln]['fids']) == 1:
                fid =  lyrs_found[ln]['fids'][0]
                a_text = "{} ({})".format(ln, fid)
                actions[i][0] = QAction(a_text, None)
                actions[i][0].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                actions[i][0].triggered.connect(functools.partial(self.pass_res, tab, fid))
                popup.addAction(actions[i][0])
            else:
                for j, fid in enumerate(lyrs_found[ln]['fids']):
                    actions[i][j] = QAction(str(fid), None)
                    actions[i][j].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    actions[i][j].triggered.connect(functools.partial(self.pass_res, tab, fid))
                    sm[i].addAction(actions[i][j])
                popup.addMenu(sm[i])
        popup.exec_(self.canvas.mapToGlobal(QPoint(e.pos().x()+30, e.pos().y()+30)))

    def pass_res(self, table, fid):
        self.feature_picked.emit(table, fid)
        self.clear_rubber()

    def show_rubber(self, lyr_id, fid):
        lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        gt = lyr.geometryType()
        self.clear_rubber()
        self.rb = QgsRubberBand(self.canvas, gt)
        self.rb.setColor(QColor(255, 0, 0))
        if gt == 2:
            self.rb.setFillColor(QColor(255, 0, 0, 100))
        self.rb.setWidth(2)
        feat = lyr.getFeatures(QgsFeatureRequest(fid)).next()
        self.rb.setToGeometry(feat.geometry(), lyr)

    def clear_rubber(self):
        if self.rb:
            for i in range(3):
                self.rb.reset(i)

#    def activate(self):
#        pass
#
    def deactivate(self):
        self.clear_rubber()

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
