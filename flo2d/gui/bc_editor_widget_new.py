# -*- coding: utf-8 -*-
from qgis._core import QgsMessageLog, QgsProject, QgsVectorLayer, QgsMapLayer

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("bc_editor_new")


class BCEditorWidgetNew(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.setupUi(self)

        self.lyrs = lyrs
        self.project = QgsProject.instance()
        self.con = None
        self.gutils = None
        self.setup_connection()

        self.bc_points_lyr = self.lyrs.data["user_bc_points"]["qlyr"]
        self.bc_lines_lyr = self.lyrs.data["user_bc_lines"]["qlyr"]
        self.bc_polygons_lyr = self.lyrs.data["user_bc_polygons"]["qlyr"]

        self.bc_points_lyr.setFlags(QgsMapLayer.Private)
        self.bc_lines_lyr.setFlags(QgsMapLayer.Private)
        self.bc_polygons_lyr.setFlags(QgsMapLayer.Private)

        # Connections
        self.inflow_grpbox.toggled.connect(self.add_shapes)
        self.outflow_grpbox.toggled.connect(self.add_shapes)
        # Inflow
        self.create_inflow_point_bc_btn.clicked.connect(self.create_inflow_point_bc)
        self.create_inflow_line_bc_btn.clicked.connect(self.create_inflow_line_bc)
        self.create_inflow_polygon_bc_btn.clicked.connect(self.create_inflow_polygon_bc)

        # Outflow

    def setup_connection(self):
        """
        Function to set up connection
        """
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def add_shapes(self):
        """
        Function to add the BC shapes
        """
        if self.inflow_grpbox.isChecked() or self.outflow_grpbox.isChecked():
            self.bc_points_lyr.setFlags(self.bc_points_lyr.flags() & ~QgsMapLayer.LayerFlag(QgsMapLayer.Private))
            self.bc_lines_lyr.setFlags(self.bc_lines_lyr.flags() & ~QgsMapLayer.LayerFlag(QgsMapLayer.Private))
            self.bc_polygons_lyr.setFlags(self.bc_polygons_lyr.flags() & ~QgsMapLayer.LayerFlag(QgsMapLayer.Private))
        else:
            self.bc_points_lyr.setFlags(QgsMapLayer.Private)
            self.bc_lines_lyr.setFlags(QgsMapLayer.Private)
            self.bc_polygons_lyr.setFlags(QgsMapLayer.Private)

    def create_inflow_point_bc(self):
        """
        Function to create inflow point bc
        """
        pass

    def create_inflow_line_bc(self):
        """
        Function to create inflow line bc
        """
        pass

    def create_inflow_polygon_bc(self):
        """
        Function to create inflow polygon bc
        """
        pass

