# -*- coding: utf-8 -*-
from qgis._core import QgsWkbTypes
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from qgis.core import QgsFieldProxyModel, QgsMapLayerProxyModel

from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("evaluate_blocked_areas")


class EvaluateReductionFactorsDialog(qtBaseClass, uiDialog):
    def __init__(self, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.lyrs = lyrs
        self.setupUi(self)
        self.collapse_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.arf_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.wrf_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)

        self.current_lyr = None

        # connections
        self.setup_src_layer_cbo()
        self.external_lyr_cbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        self.use_external_lyr_rb.toggled.connect(self.method_changed)
        self.use_user_layer_rb.setChecked(True)

    def setup_src_layer_cbo(self):
        """
        Filter src layer combo for polygons and connect field cbo.
        """
        self.external_lyr_cbo.addItem("", None)
        poly_lyrs = self.lyrs.list_group_vlayers()
        for l in poly_lyrs:
            if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                l.reload()  # force layer reload because sometimes featureCount does not work
                if l.featureCount() > 0:
                    self.external_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
            else:
                pass

    def populate_src_field_cbo(self, idx):
        if idx == 0:
            return
        uri = self.external_lyr_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.collapse_cbo.setLayer(self.current_lyr)
        self.arf_cbo.setLayer(self.current_lyr)
        self.wrf_cbo.setLayer(self.current_lyr)

    def method_changed(self):
        if self.use_external_lyr_rb.isChecked():
            self.external_grp.setEnabled(True)
        else:
            self.external_grp.setDisabled(True)

    def use_external_layer(self):
        return self.use_external_lyr_rb.isChecked()

    def external_layer_parameters(self):
        current_layer = self.lyrs.get_layer_by_name(self.external_lyr_cbo.currentText()).layer()
        collapse_field = self.collapse_cbo.currentField()
        arf_field = self.arf_cbo.currentField()
        wrf_field = self.wrf_cbo.currentField()
        return current_layer, collapse_field, arf_field, wrf_field
