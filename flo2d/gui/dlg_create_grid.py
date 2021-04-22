# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


import os
from .ui_utils import load_ui
from qgis.core import QgsMapLayerProxyModel, QgsFieldProxyModel
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

uiDialog, qtBaseClass = load_ui("create_grid")

class CreateGridDialog(qtBaseClass, uiDialog):
    def __init__(self):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.external_lyr_cbo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.cell_size_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.Int)
        self.external_layer_changed()
        self.method_changed()
        # connections
        self.external_lyr_cbo.currentIndexChanged.connect(self.external_layer_changed)
        self.use_external_lyr_rb.toggled.connect(self.method_changed)
        self.use_user_layer_rb.setChecked(True)
        self.browseBtn.clicked.connect(self.browse_raster_file)

    def external_layer_changed(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        self.cell_size_cbo.setLayer(current_layer)

    def method_changed(self):
        if self.use_external_lyr_rb.isChecked():
            self.external_grp.setEnabled(True)
        else:
            self.external_grp.setDisabled(True)

    def use_external_layer(self):
        return self.use_external_lyr_rb.isChecked()

    def external_layer_parameters(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        cell_size_field = self.cell_size_cbo.currentField()
        raster_file = self.raster_file_lab.text().strip()
        return current_layer, cell_size_field, raster_file

    def browse_raster_file(self):
        """
        Users pick a source raster file from file explorer.
        """
        s = QSettings()
        last_elev_raster_dir = s.value("FLO-2D/lastElevRasterDir", "")
        src_file, __ = QFileDialog.getOpenFileName(None, "Choose elevation raster...",
                                                   directory=last_elev_raster_dir,
                                                   filter='Elev (*.tif )')
        if not src_file:
            return
        s.setValue("FLO-2D/lastElevRasterDir", os.path.dirname(src_file))
        self.raster_file_lab.setText(src_file)
        self.raster_file_lab.setToolTip(src_file)
