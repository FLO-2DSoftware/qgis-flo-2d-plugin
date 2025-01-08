# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


import os

from qgis._core import QgsWkbTypes
from qgis.core import QgsFieldProxyModel, QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("create_grid")


class CreateGridDialog(qtBaseClass, uiDialog):
    def __init__(self, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.lyrs = lyrs
        self.setupUi(self)
        self.cell_size_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.Int)
        self.current_lyr = None
        self.method_changed()

        # connections
        self.setup_src_layer_cbo()

        self.external_lyr_cbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        self.use_external_lyr_rb.toggled.connect(self.method_changed)
        self.use_user_layer_rb.setChecked(True)
        self.browseBtn.clicked.connect(self.browse_raster_file)

    def setup_src_layer_cbo(self):
        """
        Filter src layer combo for polygons and connect field cbo.
        """
        self.external_lyr_cbo.addItem("", None)
        poly_lyrs = self.lyrs.list_group_vlayers()
        for l in poly_lyrs:
            if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                l.reload()  # force layer reload because sometimes featureCount does not work
                if l.featureCount() == 1:
                    self.external_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
            else:
                pass

    def populate_src_field_cbo(self, idx):
        if idx == 0:
            return
        uri = self.external_lyr_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.cell_size_cbo.setLayer(self.current_lyr)

    def method_changed(self):
        if self.use_external_lyr_rb.isChecked():
            self.external_grp.setEnabled(True)
        else:
            self.external_grp.setDisabled(True)

    def use_external_layer(self):
        return self.use_external_lyr_rb.isChecked()

    def external_layer_parameters(self):
        current_layer = self.lyrs.get_layer_by_name(self.external_lyr_cbo.currentText()).layer()
        cell_size_field = self.cell_size_cbo.currentField()
        raster_file = self.raster_file_lab.text().strip()
        return current_layer, cell_size_field, raster_file

    def browse_raster_file(self):
        """
        Users pick a source raster file from file explorer.
        """
        s = QSettings()
        last_elev_raster_dir = s.value("FLO-2D/lastElevRasterDir", "")
        src_file, __ = QFileDialog.getOpenFileName(
            None,
            "Choose elevation raster...",
            directory=last_elev_raster_dir,
            filter="Elev (*.tif )",
        )
        if not src_file:
            return
        s.setValue("FLO-2D/lastElevRasterDir", os.path.dirname(src_file))
        self.raster_file_lab.setText(src_file)
        self.raster_file_lab.setToolTip(src_file)
