# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsWkbTypes

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("sampling_tailings")


class SamplingTailingsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.current_lyr = None
        self.setup_src_layer_cbo()
        # connections
        self.srcLayerCbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        self.allGridElemsRadio.toggled.connect(self.method_changed)

    def setup_src_layer_cbo(self):
        """
        Filter src layer combo for polygons and connect field cbo.
        """
        self.srcLayerCbo.addItem("", None)
        poly_lyrs = self.lyrs.list_group_vlayers()
        for l in poly_lyrs:
            if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                l.reload()
                if l.featureCount() > 0:                 
                    self.srcLayerCbo.addItem(l.name(), l.dataProvider().dataSourceUri())
            else:
                pass

    def populate_src_field_cbo(self, idx):
        if idx == 0:
            return
        uri = self.srcLayerCbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.srcFieldCbo.setLayer(self.current_lyr)

    def method_changed(self):
        if self.allGridElemsRadio.isChecked():
            self.allGridElemsFrame.setEnabled(True)
            self.setup_src_layer_cbo()
            self.srcLayerCbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        else:
            self.srcLayerCbo.currentIndexChanged.disconnect(self.populate_src_field_cbo)
            self.srcFieldCbo.clear()
            self.srcLayerCbo.clear()
            self.allGridElemsFrame.setEnabled(False)


from qgis.core import QgsFieldProxyModel, QgsMapLayerProxyModel

uiDialog, qtBaseClass = load_ui("sampling_tailings2")


class SamplingTailingsDialog2(qtBaseClass, uiDialog):
    def __init__(self):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.external_lyr_cbo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        
        
        # non_empty = []
        # for i in range(self.external_lyr_cbo.count()):
        #     name = self.external_lyr_cbo.itemText(i)
        #     layer = QgsProject.instance().mapLayersByName(name)[0]
        #     if layer.featureCount() > 0:         
        #         non_empty.append(layer)
        #
        # self.external_lyr_cbo.clear()
        # for lyr in non_empty: 
        #     layer = QgsProject.instance().mapLayersByName(lyr)[0]     
        #     self.external_lyr_cbo.setAdditionalLayers(non_empty)
        
        
        self.tailings_cbo.setFilters(QgsFieldProxyModel.Numeric | QgsFieldProxyModel.String)
        self.external_layer_changed()
        # connections
        self.external_lyr_cbo.currentIndexChanged.connect(self.external_layer_changed)
        self.use_external_lyr_rb.toggled.connect(self.method_changed)
        self.use_user_layer_rb.setChecked(True)

    def external_layer_changed(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        self.tailings_cbo.setLayer(current_layer)

    def method_changed(self):
        if self.use_external_lyr_rb.isChecked():
            self.external_grp.setEnabled(True)
        else:
            self.external_grp.setDisabled(True)

    def use_external_layer(self):
        return self.use_external_lyr_rb.isChecked()

    def external_layer_parameters(self):
        current_layer = self.external_lyr_cbo.currentLayer()
        tailing_field = self.tailings_cbo.currentField()
        return current_layer, tailing_field
