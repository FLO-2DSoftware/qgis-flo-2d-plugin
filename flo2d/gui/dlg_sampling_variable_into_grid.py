# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QGis
from ui_utils import load_ui
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.user_communication import UserCommunication
from PyQt4.QtGui import QApplication
from PyQt4.QtGui import QFileDialog, QDialogButtonBox

uiDialog, qtBaseClass = load_ui('sampling_variable_into_grid')


class SamplingOtherVariableDialog(qtBaseClass, uiDialog):

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
        self.current_lyr = None
        self.sampling_point_field_into_grid_field_buttonBox.button(QDialogButtonBox.Ok).setText("Assign to selected grid field")
        self.setup_layer_cbo()
        # connections
        self.points_cbo.currentIndexChanged.connect(self.populate_fields_cbo)

    def setup_layer_cbo(self):
        """
        Filter layer combo for points and connect field cbo.
        """
        try:

            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QGis.Point:
                    if l.featureCount() != 0:
                        self.points_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            
            if self.points_cbo.count():
                grid_lyr = self.lyrs.data['grid']['qlyr']
                fields = [f.name() for f in grid_lyr.fields()]
                self.grid_fields_cbo.clear()
                for f in fields:
                    if f in ["water_elevation", "flow_depth"]:
                        self.grid_fields_cbo.addItem(f)            
                self.grid_fields_cbo.setCurrentIndex(0)                 
    
                self.populate_fields_cbo(self.points_cbo.currentIndex())                
            else:    
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn('There are not any point layers selected (or visible)')             

        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):

        uri = self.points_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.points_layer_fields_cbo.setLayer(self.current_lyr)
        self.points_layer_fields_cbo.setCurrentIndex(0)
