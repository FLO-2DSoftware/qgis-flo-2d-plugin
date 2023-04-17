# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import functools
import os

# QgsMapToolIdentify required those functions to be self
# pylint: disable=no-self-use
from collections import OrderedDict

from qgis.core import QgsFeatureRequest
from qgis.gui import QgsMapToolIdentify, QgsRubberBand
from qgis.PyQt.QtCore import QPoint, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMenu


class ChannelProfile(QgsMapToolIdentify):
    feature_picked = pyqtSignal(str, int)  # Defines a new own signal 'feature_picked' with 2 arguments of
    # type str and int, respectively, that will be 'emmited' on the signal.
    # See self.feature_picked.emit(table, fid), where 'table' will be the table ´chan' and
    # 'fid' the id fid of the segment selected.

    def __init__(self, canvas, lyrs):
        self.canvas = canvas
        self.lyrs = lyrs
        self.rb = None
        self.profile_tabs = ["chan"]
        QgsMapToolIdentify.__init__(self, self.canvas)

    def update_lyrs_list(self):
        # lyrs_list = self.lyrs.list_group_vlayers(self.lyrs.group, skip_views=True)
        self.lyrs_list = [self.lyrs.data["chan"]["qlyr"]]

    def canvasPressEvent(self, dummy):
        self.clear_rubber()

    def canvasReleaseEvent(self, e):
        # Overrides inherited method from QgsMapToolIdentify.
        # Creates a submenu and shows it where the user clicks the canvas.
        res = self.identify(e.x(), e.y(), self.lyrs_list, QgsMapToolIdentify.TopDownAll)
        lyrs_found = OrderedDict()
        for i, item in enumerate(res):
            lyr_name = item.mLayer.name()  # Channel Segments (left Banks)
            lyr_id = item.mLayer.id()
            table = item.mLayer.dataProvider().dataSourceUri().split("=")[-1]  # 'chan': the name of  DB table.
            if not table in self.profile_tabs:
                continue
            fid = item.mFeature.id()  # fid of the selected feature of 'Chan'
            if lyr_name not in list(lyrs_found.keys()):
                lyrs_found[lyr_name] = {"lid": lyr_id, "table": table, "fids": []}
            else:
                pass
            lyrs_found[lyr_name]["fids"].append(fid)
        popup = QMenu()
        sm = {}
        actions = {}
        for i, ln in enumerate(lyrs_found.keys()):
            lid = lyrs_found[ln]["lid"]
            tab = lyrs_found[ln]["table"]
            sm[i] = QMenu(ln)
            actions[i] = {}
            if len(lyrs_found[ln]["fids"]) == 1:
                fid = lyrs_found[ln]["fids"][0]
                a_text = "{} ({})".format(ln, fid)
                actions[i][0] = QAction(a_text, None)
                actions[i][0].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                actions[i][0].triggered.connect(functools.partial(self.pass_res, tab, fid))
                popup.addAction(actions[i][0])
            else:
                for j, fid in enumerate(lyrs_found[ln]["fids"]):
                    actions[i][j] = QAction(str(fid), None)
                    actions[i][j].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    actions[i][j].triggered.connect(functools.partial(self.pass_res, tab, fid))
                    sm[i].addAction(actions[i][j])
                popup.addMenu(sm[i])
        popup.exec_(
            self.canvas.mapToGlobal(QPoint(e.pos().x() + 30, e.pos().y() + 30))
        )  # Shows popup menu with list of selected
        # channel left bank (shematized) (selected from table 'Chan')

    def pass_res(self, table, fid):
        self.feature_picked.emit(table, fid)  # Calls get_feature_profile()
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
        feat = next(lyr.getFeatures(QgsFeatureRequest(fid)))
        self.rb.setToGeometry(feat.geometry(), lyr)

    def clear_rubber(self):
        if self.rb:
            for i in range(3):
                self.rb.reset(i)

    def activate(self):
        self.canvas.setCursor(
            QCursor(QPixmap(os.path.join(os.path.dirname(__file__), "img/profile_tool_icon.svg")))
        )  # Apparently set a particular cursor pointer, but it doesn't!
        self.update_lyrs_list()  # self.lyrs_list gets current data from 'chan' layer (schematic left bank).
        self.lyrs.root.visibilityChanged.connect(self.update_lyrs_list)

    def deactivate(self):
        self.clear_rubber()
        self.lyrs.root.visibilityChanged.disconnect(self.update_lyrs_list)

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
