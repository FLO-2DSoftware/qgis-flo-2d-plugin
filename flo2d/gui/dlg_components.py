# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from qgis.PyQt.QtCore import QSettings
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('components')


class ComponentsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.components = []

        self.components_buttonBox.accepted.connect(self.load_selected_components)
        self.select_all_chbox.clicked.connect(self.unselect_all)
        
        self.setFixedSize(self.size())

        self.populate_components_dialog()

    def populate_components_dialog(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')

        if os.path.isfile(last_dir + '\CHAN.DAT'):
            self.channels_chbox.setChecked(True)
            self.channels_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\ARF.DAT'):
            self.reduction_factors_chbox.setChecked(True)
            self.reduction_factors_chbox.setEnabled(True)
            
        if os.path.isfile(last_dir + '\STREET.DAT'):
            self.streets_chbox.setChecked(True)
            self.streets_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\OUTFLOW.DAT'):
            self.outflow_elements_chbox.setChecked(True)
            self.outflow_elements_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\INFLOW.DAT'):
            self.inflow_elements_chbox.setChecked(True)
            self.inflow_elements_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\LEVEE.DAT'):
            self.levees_chbox.setChecked(True)
            self.levees_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\MULT.DAT'):
            self.multiple_channels_chbox.setChecked(True)
            self.multiple_channels_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\BREACH.DAT'):
            self.breach_chbox.setChecked(True)
            self.breach_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\GUTTER.DAT'):
            self.gutters_chbox.setChecked(True)
            self.gutters_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\INFIL.DAT'):
            self.infiltration_chbox.setChecked(True)
            self.infiltration_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\FPXSEC.DAT'):
            self.floodplain_xs_chbox.setChecked(True)
            self.floodplain_xs_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\SED.DAT'):
            self.mud_and_sed_chbox.setChecked(True)
            self.mud_and_sed_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\EVAPOR.DAT'):
            self.evaporation_chbox.setChecked(True)
            self.evaporation_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\HYSTRUC.DAT'):
            self.hydr_struct_chbox.setChecked(True)
            self.hydr_struct_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\RAIN.DAT'):
            self.rain_chbox.setChecked(True)
            self.rain_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\SWMMFLO.DAT'):
            self.storm_drain_chbox.setChecked(True)
            self.storm_drain_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\TOLSPATIAL.DAT'):
            self.spatial_tolerance_chbox.setChecked(True)      
            self.spatial_tolerance_chbox.setEnabled(True)      

        if os.path.isfile(last_dir + '\FPFROUDE.DAT'):
            self.spatial_froude_chbox.setChecked(True)            
            self.spatial_froude_chbox.setEnabled(True)            

    def load_selected_components(self):

        if self.channels_chbox.isChecked():
            self.components.append('Channels')

        if self.reduction_factors_chbox.isChecked():
            self.components.append('Reduction Factors')

        if self.streets_chbox.isChecked():
            self.components.append('Streets')

        if self.outflow_elements_chbox.isChecked():
            self.components.append('Outflow Elements')

        if self.inflow_elements_chbox.isChecked():
            self.components.append('Inflow Elements')

        if self.levees_chbox.isChecked():
            self.components.append('Levees')

        if self.multiple_channels_chbox.isChecked():
            self.components.append('Multiple Channels')

        if self.breach_chbox.isChecked():
            self.components.append('Breach')

        if self.gutters_chbox.isChecked():
            self.components.append('Gutters')

        if self.infiltration_chbox.isChecked():
            self.components.append('Infiltration')

        if self.floodplain_xs_chbox.isChecked():
            self.components.append('Floodplain Cross Sections')

        if self.mud_and_sed_chbox.isChecked():
            self.components.append('Mudflow and Sediment Transport')

        if self.evaporation_chbox.isChecked():
            self.components.append('Evaporation')

        if self.hydr_struct_chbox.isChecked():
            self.components.append('Hydraulic  Structures')

        if self.mudflo_chbox.isChecked():
            self.components.append('MODFLO-2D')

        if self.rain_chbox.isChecked():
            self.components.append('Rain')

        if self.storm_drain_chbox.isChecked():
            self.components.append('Storm Drain')

        if self.spatial_tolerance_chbox.isChecked():
            self.components.append('Spatial Tolerance')

        if self.spatial_froude_chbox.isChecked():
            self.components.append('Spatial Froude')            
        
            
    def unselect_all(self):
        self.select_components(self.select_all_chbox.isChecked()); 

    def select_components(self, select = True):  
        
        
#         self.reduction_factors_chbox.setChecked(select);
#         self.streets_chbox.setChecked(select);
#         self.outflow_elements_chbox.setChecked(select);
#         self.inflow_elements_chbox.setChecked(select);
#         self.levees_chbox.setChecked(select);
#         self.multiple_channels_chbox.setChecked(select);
#         self.breach_chbox.setChecked(select);
#         self.gutters_chbox.setChecked(select);
#         self.infiltration_chbox.setChecked(select);
#         self.floodplain_xs_chbox.setChecked(select);
#         self.mud_and_sed_chbox.setChecked(select);
#         self.evaporation_chbox.setChecked(select);
#         self.hydr_struct_chbox.setChecked(select);
#         self.mudflo_chbox.setChecked(select);
#         self.rain_chbox.setChecked(select);
#         self.storm_drain_chbox.setChecked(select);
#         self.spatial_tolerance_chbox.setChecked(select);
#         self.spatial_froude_chbox.setChecked(select);        
        
        
        
        if self.channels_chbox.isEnabled():  
            self.channels_chbox.setChecked(select);
        if self.reduction_factors_chbox.isEnabled():      
            self.reduction_factors_chbox.setChecked(select);
        if self.streets_chbox.isEnabled():    
            self.streets_chbox.setChecked(select);
        if self.outflow_elements_chbox.isEnabled():        
            self.outflow_elements_chbox.setChecked(select);
        if self.inflow_elements_chbox.isEnabled():        
            self.inflow_elements_chbox.setChecked(select);
        if self.levees_chbox.isEnabled():        
            self.levees_chbox.setChecked(select);
        if self.multiple_channels_chbox.isEnabled():        
            self.multiple_channels_chbox.setChecked(select);
        if self.breach_chbox.isEnabled():        
            self.breach_chbox.setChecked(select);
        if self.gutters_chbox.isEnabled():        
            self.gutters_chbox.setChecked(select);
        if self.infiltration_chbox.isEnabled():        
            self.infiltration_chbox.setChecked(select);
        if self.floodplain_xs_chbox.isEnabled():        
            self.floodplain_xs_chbox.setChecked(select);
        if self.mud_and_sed_chbox.isEnabled():        
            self.mud_and_sed_chbox.setChecked(select);
        if self.evaporation_chbox.isEnabled():        
            self.evaporation_chbox.setChecked(select);
        if self.hydr_struct_chbox.isEnabled():        
            self.hydr_struct_chbox.setChecked(select);
        if self.mudflo_chbox.isEnabled():        
            self.mudflo_chbox.setChecked(select);
        if self.rain_chbox.isEnabled():        
            self.rain_chbox.setChecked(select);
        if self.storm_drain_chbox.isEnabled():        
            self.storm_drain_chbox.setChecked(select);
        if self.spatial_tolerance_chbox.isEnabled():        
            self.spatial_tolerance_chbox.setChecked(select);
        if self.spatial_froude_chbox.isEnabled():        
            self.spatial_froude_chbox.setChecked(select);

        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        