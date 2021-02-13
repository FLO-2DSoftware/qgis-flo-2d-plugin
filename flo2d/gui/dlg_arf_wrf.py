# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui
from qgis.core import QgsMapLayerProxyModel, QgsFieldProxyModel

uiDialog, qtBaseClass = load_ui("evaluate_blocked_areas")


class EvaluateReductionFactorsDialog(qtBaseClass, uiDialog):
    def __init__(self):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.external_lyr_cbo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.collapse_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.arf_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.wrf_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.external_layer_changed()
        # connections
        self.external_lyr_cbo.currentIndexChanged.connect(self.external_layer_changed)
        self.use_external_lyr_rb.toggled.connect(self.method_changed)
        self.use_user_layer_rb.setChecked(True)

    def external_layer_changed(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        self.collapse_cbo.setLayer(current_layer)
        self.arf_cbo.setLayer(current_layer)
        self.wrf_cbo.setLayer(current_layer)

    def method_changed(self):
        if self.use_external_lyr_rb.isChecked():
            self.external_grp.setEnabled(True)
        else:
            self.external_grp.setDisabled(True)

    def use_external_layer(self):
        return self.use_external_lyr_rb.isChecked()

    def external_layer_parameters(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        collapse_field = self.collapse_cbo.currentField()
        arf_field = self.arf_cbo.currentField()
        wrf_field = self.wrf_cbo.currentField()
        return current_layer, collapse_field, arf_field, wrf_field
