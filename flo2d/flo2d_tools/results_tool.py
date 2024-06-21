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

from qgis.core import QgsFeatureRequest, QgsWkbTypes
from qgis.gui import QgsMapToolIdentify, QgsRubberBand
from qgis.PyQt.QtCore import QPoint, pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor, QCursor, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMenu


class ResultsTool(QgsMapToolIdentify):
    feature_picked = pyqtSignal(str, int, object)  # Defines a new own signal 'feature_picked' with 2 arguments of
    # type str and int, respectively, that will be 'emmited' on the signal.
    # See self.feature_picked.emit(table, fid), where 'table' will be the table ´chan' and
    # 'fid' the id fid of the segment selected.

    def __init__(self, canvas, lyrs, uc):
        self.canvas = canvas
        self.lyrs = lyrs
        self.rb = None
        self.uc = uc
        # self.profile_tabs = ["chan"]
        self.canvas.setCursor(Qt.CrossCursor)
        QgsMapToolIdentify.__init__(self, self.canvas)

    def update_lyrs_list(self):

        self.lyrs_list = [
            self.lyrs.data["chan"]["qlyr"],
            self.lyrs.data["chan_elems"]["qlyr"],
            self.lyrs.data["fpxsec"]["qlyr"],
            self.lyrs.data["fpxsec_cells"]["qlyr"],
            self.lyrs.data["struct"]["qlyr"],
            self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"],
            self.lyrs.data["user_swmm_outlets"]["qlyr"],
            self.lyrs.data["user_swmm_conduits"]["qlyr"],
            self.lyrs.data["user_swmm_weirs"]["qlyr"],
            self.lyrs.data["user_swmm_orifices"]["qlyr"],
            self.lyrs.data["user_swmm_pumps"]["qlyr"]
        ]

    def canvasPressEvent(self, dummy):
        self.clear_rubber()

    def canvasReleaseEvent(self, e):
        """
        Function that created the submenus and add the actions
        """
        implemented = [
            "chan",
            "chan_elems",
            "fpxsec",
            "fpxsec_cells",
            "user_swmm_inlets_junctions",
            "user_swmm_conduits",
            "user_swmm_weirs",
            "user_swmm_orifices",
            "user_swmm_pumps",
            "struct"
        ]
        # Overrides inherited method from QgsMapToolIdentify.
        # Creates a submenu and shows it where the user clicks the canvas.
        res = self.identify(e.x(), e.y(), self.lyrs_list, QgsMapToolIdentify.TopDownAll)
        lyrs_found = OrderedDict()
        for i, item in enumerate(res):
            lyr_name = item.mLayer.name()
            lyr_id = item.mLayer.id()
            table = item.mLayer.dataProvider().dataSourceUri().split("=")[-1]
            if table in implemented:
                fid = item.mFeature.id()
                if lyr_name not in list(lyrs_found.keys()):
                    lyrs_found[lyr_name] = {"lid": lyr_id, "table": table, "fids": []}
                else:
                    pass
                lyrs_found[lyr_name]["fids"].append(fid)
        popup = QMenu()
        sm = {}
        ssm = {}
        actions = {}
        for i, ln in enumerate(lyrs_found.keys()):
            lid = lyrs_found[ln]["lid"]
            tab = lyrs_found[ln]["table"]
            sm[i] = QMenu(ln)
            actions[i] = {}

            if ln == "Storm Drain Nodes":
                sd_layer = self.lyrs.get_layer_by_name("Storm Drain Nodes", group=self.lyrs.group).layer()
                for j, fid in enumerate(lyrs_found[ln]["fids"]):
                    feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                    name = feat["name"]
                    grid = feat["grid"]
                    ssm = QMenu(name + " (" + str(grid) + ")")
                    sm[i].addMenu(ssm)

                    # Results
                    results_action = QAction("See Results", None)
                    results_action.hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    results_action.triggered.connect(functools.partial(self.pass_res, tab, fid, "See Results"))
                    ssm.addAction(results_action)

                    # Add "Start Node" action
                    start_action = QAction("Start Node", None)
                    start_action.hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    start_action.triggered.connect(functools.partial(self.pass_res, tab, fid, "Start"))
                    ssm.addAction(start_action)

                    # Add "End Node" action
                    end_action = QAction("End Node", None)
                    end_action.hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    end_action.triggered.connect(functools.partial(self.pass_res, tab, fid, "End"))
                    ssm.addAction(end_action)
            else:
                for j, fid in enumerate(lyrs_found[ln]["fids"]):
                    if ln == "Storm Drain Conduits":
                        sd_layer = self.lyrs.get_layer_by_name("Storm Drain Conduits", group=self.lyrs.group).layer()
                        feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                        name = feat["conduit_name"]
                        actions[i][j] = QAction(name, None)
                    elif ln == "Storm Drain Weirs":
                        sd_layer = self.lyrs.get_layer_by_name("Storm Drain Weirs", group=self.lyrs.group).layer()
                        feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                        name = feat["weir_name"]
                        actions[i][j] = QAction(name, None)
                    elif ln == "Storm Drain Orifices":
                        sd_layer = self.lyrs.get_layer_by_name("Storm Drain Orifices", group=self.lyrs.group).layer()
                        feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                        name = feat["orifice_name"]
                        actions[i][j] = QAction(name, None)
                    elif ln == "Storm Drain Pumps":
                        sd_layer = self.lyrs.get_layer_by_name("Storm Drain Pumps", group=self.lyrs.group).layer()
                        feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                        name = feat["pump_name"]
                        actions[i][j] = QAction(name, None)
                    elif ln == "Floodplain Cross Sections Cells":
                        fp_cells_layer = self.lyrs.get_layer_by_name("Floodplain Cross Sections Cells", group=self.lyrs.group).layer()
                        feat = next(fp_cells_layer.getFeatures(QgsFeatureRequest(fid)))
                        grid = feat["grid_fid"]
                        actions[i][j] = QAction(str(grid), None)
                    else:
                        actions[i][j] = QAction(str(fid), None)
                    actions[i][j].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    actions[i][j].triggered.connect(functools.partial(self.pass_res, tab, fid))
                    sm[i].addAction(actions[i][j])
            popup.addMenu(sm[i])
        popup.exec_(
            self.canvas.mapToGlobal(QPoint(e.pos().x() + 30, e.pos().y() + 30))
        )  # Shows popup menu with list of selected
        # channel left bank (shematized) (selected from table 'Chan')

    def pass_res(self, table, fid, extra=None):
        self.feature_picked.emit(table, fid, extra)
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
                if i == 0:
                    self.rb.reset(QgsWkbTypes.PointGeometry)
                elif i == 1:
                    self.rb.reset(QgsWkbTypes.LineGeometry)
                elif i == 2:
                    self.rb.reset(QgsWkbTypes.PolygonGeometry)

    def activate(self):
        self.canvas.setCursor(Qt.CrossCursor)
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
