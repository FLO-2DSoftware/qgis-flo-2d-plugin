# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsWkbTypes
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("sampling_buildings_elevation")


class SamplingBuildingsElevationsDialog(qtBaseClass, uiDialog):
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
        self.setup_layer_cbo()
        # connections
        self.buildings_cbo.currentIndexChanged.connect(self.populate_fields_cbo)

    def setup_layer_cbo(self):
        """
        Filter layer combo for points and connect field cbo.
        """
        self.buildings_cbo.clear()
        try:
            layers = self.lyrs.list_group_vlayers()
            for l in layers:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    if l.featureCount() != 0:
                        self.buildings_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            self.populate_fields_cbo(self.buildings_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        uri = self.buildings_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.field_to_uniformize_cbo.setLayer(self.current_lyr)
        self.field_to_uniformize_cbo.setCurrentIndex(0)
        self.ID_field_cbo.setLayer(self.current_lyr)
        self.ID_field_cbo.setCurrentIndex(0)
