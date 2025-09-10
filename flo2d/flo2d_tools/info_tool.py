# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import functools

# QgsMapToolIdentify required those functions to be self
# pylint: disable=no-self-use
from collections import OrderedDict

from qgis.core import QgsFeatureRequest, QgsWkbTypes
from qgis.gui import QgsMapToolIdentify, QgsRubberBand
from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMenu

class InfoTool(QgsMapToolIdentify):
    feature_picked = pyqtSignal(str, int, object)

    def __init__(self, canvas, lyrs, uc):
        self.canvas = canvas
        self.canvas.setCursor(Qt.CrossCursor)
        self.lyrs = lyrs
        self.uc = uc
        self.rb = None
        QgsMapToolIdentify.__init__(self, self.canvas)

    def update_lyrs_list(self):
        self.lyrs_list = self.lyrs.list_group_vlayers(self.lyrs.group, skip_views=True)

    def canvasPressEvent(self, dummy):
        self.clear_rubber()

    def canvasReleaseEvent(self, e):
        """

        """
        # These are the tables that are currently implemented.
        implemented = [
            "chan",
            "user_levee_lines",
            "user_xsections",
            "user_streets",
            "user_centerline",
            "chan_elems",
            "user_left_bank",
            "user_right_bank",
            "user_bc_points",
            "user_bc_lines",
            "user_bc_polygons",
            "user_struct",
            "struct",
            "user_swmm_inlets_junctions",
            "user_swmm_outlets",
            "user_swmm_conduits",
            "user_swmm_pumps",
            "user_swmm_orifices",
            "user_swmm_weirs",
            "user_swmm_storage_units",
            "grid",
            "fpxsec"
        ]
        # try:
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

        sd_point_layers = [
            "Storm Drain Inlets/Junctions",
            "Storm Drain Outfalls",
            "Storm Drain Storage Units"

        ]

        sd_line_layers = [
            "Storm Drain Conduits",
            "Storm Drain Pumps",
            "Storm Drain Orifices",
            "Storm Drain Weirs",
        ]

        for i, ln in enumerate(lyrs_found.keys()):
            lid = lyrs_found[ln]["lid"]
            tab = lyrs_found[ln]["table"]
            display_name = "Realtime Rainfall" if tab == "grid" else ln
            sm[i] = QMenu(display_name)
            actions[i] = {}

            for j, fid in enumerate(lyrs_found[ln]["fids"]):
                if ln in sd_point_layers:
                    sd_layer = self.lyrs.get_layer_by_name(ln, group=self.lyrs.group).layer()
                    feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                    name = feat["name"]
                    grid = feat["grid"]
                    ssm = QMenu(name + " (" + str(grid) + ")")
                    sm[i].addMenu(ssm)

                    # Attributes
                    results_action = QAction("See Attributes", None)
                    results_action.hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    results_action.triggered.connect(functools.partial(self.pass_res, tab, fid, "See Attributes"))
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

                elif ln in sd_line_layers:
                    sd_layer = self.lyrs.get_layer_by_name(ln, group=self.lyrs.group).layer()
                    feat = next(sd_layer.getFeatures(QgsFeatureRequest(fid)))
                    feat_type = ln.split()[-1].lower()[:-1]
                    name = feat[f"{feat_type}_name"]
                    actions[i][j] = QAction(name, None)
                    actions[i][j].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    actions[i][j].triggered.connect(functools.partial(self.pass_res, tab, fid))
                    sm[i].addAction(actions[i][j])
                else:
                    actions[i][j] = QAction(str(fid), None)
                    actions[i][j].hovered.connect(functools.partial(self.show_rubber, lid, fid))
                    actions[i][j].triggered.connect(functools.partial(self.pass_res, tab, fid))
                    sm[i].addAction(actions[i][j])

            popup.addMenu(sm[i])
        popup.exec_(self.canvas.mapToGlobal(QPoint(e.pos().x() + 30, e.pos().y() + 30)))
        # except:
        #     pass

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
        # self.canvas.setCursor(QCursor(QPixmap(os.path.join(os.path.dirname(__file__), "img/info_tool_icon.svg"))))
        self.update_lyrs_list()
        self.lyrs.root.visibilityChanged.connect(self.update_lyrs_list)

    def deactivate(self):
        self.canvas.setCursor(Qt.ArrowCursor)
        self.clear_rubber()
        self.lyrs.root.visibilityChanged.disconnect(self.update_lyrs_list)

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return False
