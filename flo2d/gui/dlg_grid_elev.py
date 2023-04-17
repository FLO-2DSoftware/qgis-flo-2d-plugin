# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsFeatureRequest, QgsWkbTypes

from ..flo2d_tools.elevation_correctors import ExternalElevation, GridElevation
from ..geopackage_utils import GeoPackageUtils
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("grid_elevation")


class GridCorrectionDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.gutils = GeoPackageUtils(con, iface)
        self.internal_corrector = GridElevation(self.gutils, self.lyrs)
        self.selection_switch()
        self.internal_corrector.setup_layers()
        self.external_corrector = ExternalElevation(self.gutils, self.lyrs)

        self.internal_methods = {}
        self.external_method = None

        # connections
        self.elev_tin_chbox.stateChanged.connect(self.tin_checked)
        self.elev_tin_poly_chbox.stateChanged.connect(self.tin_poly_checked)
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_arf_chbox.stateChanged.connect(self.arf_checked)
        self.internal_selected_chbox.stateChanged.connect(self.selection_switch)

        self.vector_polygon_cbo.currentIndexChanged.connect(self.populate_fields)
        self.vector_polyline_cbo.currentIndexChanged.connect(self.populate_fields)

        self.populate_polygon_vectors()
        self.populate_polyline_vectors()
        self.populate_rasters()
        self.polygon_rb.toggled.connect(self.populate_fields)
        self.polyline_rb.toggled.connect(self.populate_fields)
        self.fields_grp.toggled.connect(self.fields_checked)
        self.stats_grp.toggled.connect(self.stats_checked)
        self.grid_chbox.toggled.connect(self.from_grid_checked)
        self.raster_chbox.toggled.connect(self.from_raster_checked)

    def selection_switch(self):
        if self.internal_selected_chbox.isChecked():
            self.internal_corrector.only_selected = True
        else:
            self.internal_corrector.only_selected = False

    def tin_checked(self):
        if self.elev_tin_chbox.isChecked():
            self.internal_methods[1] = self.tin_method
        else:
            self.internal_methods.pop(1)

    def tin_poly_checked(self):
        if self.elev_tin_poly_chbox.isChecked():
            self.internal_methods[2] = self.tin_poly_method
        else:
            self.internal_methods.pop(2)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.internal_methods[3] = self.polygon_method
        else:
            self.internal_methods.pop(3)

    def arf_checked(self):
        if self.elev_arf_chbox.isChecked():
            self.stats_cbx.setEnabled(True)
            self.internal_methods[4] = self.arf_method
        else:
            self.internal_methods.pop(4)
            self.stats_cbx.setDisabled(True)

    def tin_method(self):
        try:
            self.internal_corrector.set_filter()
            self.internal_corrector.elevation_from_tin()
        finally:
            self.internal_corrector.clear_filter()

    def tin_poly_method(self):
        try:
            self.internal_corrector.set_filter()
            self.internal_corrector.tin_elevation_within_polygons()
        finally:
            self.internal_corrector.clear_filter()

    def polygon_method(self):
        try:
            self.internal_corrector.set_filter()
            self.internal_corrector.elevation_from_polygons()
        finally:
            self.internal_corrector.clear_filter()

    def arf_method(self):
        self.internal_corrector.elevation_within_arf(self.stats_cbx.currentText())

    def populate_polygon_vectors(self):
        poly_lyrs = self.lyrs.list_group_vlayers()
        for lyr in poly_lyrs:
            if lyr.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.vector_polygon_cbo.addItem(lyr.name(), lyr)

    def populate_polyline_vectors(self):
        line_lyrs = self.lyrs.list_group_vlayers()
        for lyr in line_lyrs:
            if lyr.geometryType() == QgsWkbTypes.LineGeometry:
                self.vector_polyline_cbo.addItem(lyr.name(), lyr)

    def populate_rasters(self):
        try:
            rasters = self.lyrs.list_group_rlayers()
        except AttributeError:
            return
        for r in rasters:
            self.raster_cbo.addItem(r.name(), r)

    def populate_fields(self):
        self.elev_cbo.clear()
        self.correction_cbo.clear()
        if self.polygon_rb.isChecked():
            idx = self.vector_polygon_cbo.currentIndex()
            lyr = self.vector_polygon_cbo.itemData(idx)
        else:
            idx = self.vector_polyline_cbo.currentIndex()
            lyr = self.vector_polyline_cbo.itemData(idx)
        fields = [field.name() for field in lyr.fields() if field.isNumeric()]
        self.elev_cbo.addItems(fields)
        self.correction_cbo.addItems(fields)
        if self.polyline_rb.isChecked():
            self.buffer_field_cbo.clear()
            self.buffer_field_cbo.addItems(fields)

    def fields_checked(self):
        if self.fields_grp.isChecked():
            self.stats_grp.setChecked(False)

    def stats_checked(self):
        if self.stats_grp.isChecked():
            self.fields_grp.setChecked(False)
            self.grid_chbox.setChecked(True)

    def from_grid_checked(self):
        if self.grid_chbox.isChecked():
            self.raster_chbox.setChecked(False)
            self.raster_cbo.setDisabled(True)
            self.stats_per_grid_chbox.setDisabled(True)

    def from_raster_checked(self):
        if self.raster_chbox.isChecked():
            self.raster_cbo.setEnabled(True)
            self.stats_per_grid_chbox.setEnabled(True)
            self.grid_chbox.setChecked(False)

    def setup_external_method(self):
        self.external_corrector.setup_internal()
        predicate = self.predicate_cbo.currentText()
        only_selected = True if self.selected_chbox.isChecked() else False
        copy_features = True if self.copy_chbox.isChecked() else False
        if self.polygon_rb.isChecked():
            idx = self.vector_polygon_cbo.currentIndex()
            polygon_lyr = self.vector_polygon_cbo.itemData(idx)
        else:
            idx = self.vector_polyline_cbo.currentIndex()
            polyline_lyr = self.vector_polyline_cbo.itemData(idx)
            buffer_field = self.buffer_field_cbo.currentText()
            if only_selected:
                buffer_request = QgsFeatureRequest().setFilterFids(polyline_lyr.selectedFeatureIds())
                polygon_lyr = self.external_corrector.buffer_layer(polyline_lyr, buffer_field, buffer_request)
                only_selected = False
            else:
                polygon_lyr = self.external_corrector.buffer_layer(polyline_lyr, buffer_field)

        self.external_corrector.setup_external(polygon_lyr, predicate, only_selected, copy_features)

        if self.fields_grp.isChecked():
            elev_fld = self.elev_cbo.currentText()
            correction_fld = self.correction_cbo.currentText()
            self.external_corrector.setup_attributes(elev_fld, correction_fld)
            self.external_method = self.external_corrector.elevation_attributes
        elif self.stats_grp.isChecked():
            statistic = self.estats_cbo.currentText()
            if self.grid_chbox.isChecked():
                self.external_corrector.setup_statistics(statistic)
                self.external_method = self.external_corrector.elevation_grid_statistics
            elif self.raster_chbox.isChecked():
                raster_lyr = self.raster_cbo.itemData(self.raster_cbo.currentIndex())
                statistics_per_grid = self.stats_per_grid_chbox.isChecked()
                self.external_corrector.setup_statistics(statistic, raster_lyr, statistics_per_grid)
                self.external_method = self.external_corrector.elevation_raster_statistics

    def run_internal(self):
        for no in sorted(self.internal_methods):
            self.internal_methods[no]()

    def run_external(self):
        self.external_method()
