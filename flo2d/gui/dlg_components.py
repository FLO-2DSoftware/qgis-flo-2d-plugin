# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright Â© 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from PyQt4.QtCore import QSettings
from ui_utils import load_ui
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
        self.setFixedSize(self.size())
        
        self.populate_components_dialog()

    def populate_components_dialog(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        
        if os.path.isfile(last_dir + '\CHAN.DAT'):
            self.channels_chbox.setChecked(True)
           
        if os.path.isfile(last_dir + '\ARF.DAT'):
            self.reduction_factors_chbox.setChecked(True)
           
        if os.path.isfile(last_dir + '\STREET.DAT'):
            self.streets_chbox.setChecked(True)
 
        if os.path.isfile(last_dir + '\OUTFLOW.DAT'):
            self.outflow_elements_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\INFLOW.DAT'):
            self.inflow_elements_chbox.setChecked(True)
                     
        if os.path.isfile(last_dir + '\LEVEE.DAT'):
            self.levees_chbox.setChecked(True)
                       
        if os.path.isfile(last_dir + '\MULT.DAT'):
            self.multiple_channels_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\BREACH.DAT'):
            self.breach_chbox.setChecked(True)
                       
        if os.path.isfile(last_dir + '\GUTTER.DAT'):
            self.gutters_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\INFIL.DAT'):
            self.infiltration_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\FPXSEC.DAT'):
            self.floodplain_xs_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\SED.DAT'):
            self.mud_and_sed_chbox.setChecked(True)
                       
        if os.path.isfile(last_dir + '\EVAPOR.DAT'):
            self.evaporation_chbox.setChecked(True)
                         
        if os.path.isfile(last_dir + '\HYSTRUC.DAT'):
            self.hydr_struct_chbox.setChecked(True)
                         
        # if (os.path.isfile(last_dir + '\.DAT')):
        #    self.mudflo_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\RAIN.DAT'):
            self.rain_chbox.setChecked(True)
                        
        if os.path.isfile(last_dir + '\SWMMFLO.DAT'):
            self.storm_drain_chbox.setChecked(True)

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
