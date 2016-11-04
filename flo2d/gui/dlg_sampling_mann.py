# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QGis
from .utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('sampling_manning')


class SamplingManningDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setup_src_layer_cbo()
        # connections
        self.srcLayerCbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        self.allGridElemsRadio.toggled.connect(self.method_changed)

    def setup_src_layer_cbo(self):
        """Filter src layer combo for plygons and connect field cbo"""
        g = self.lyrs.group
        self.srcLayerCbo.addItem('', None)
        poly_lyrs = self.lyrs.list_group_vlayers(g)
        for l in poly_lyrs:
            if l.geometryType() == QGis.Polygon:
                self.srcLayerCbo.addItem(l.name(), l.dataProvider().dataSourceUri())
            else:
                pass

    def populate_src_field_cbo(self, idx):
        if idx == 0:
            return
        uri = self.srcLayerCbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri, self.lyrs.group)
        lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.srcFieldCbo.setLayer(lyr)

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
