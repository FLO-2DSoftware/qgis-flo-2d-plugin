# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from ..flo2d_tools.schema2user_tools import (
    SchemaBCConverter,
    Schema1DConverter,
    SchemaLeveesConverter,
    SchemaFPXSECConverter,
    SchemaGridConverter,
    SchemaInfiltrationConverter,
    SchemaSWMMConverter
)
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui('user2schema')


class User2SchemaDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, uc):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = uc
        self.methods = {}
        self.message = ""

        # connections
        self.user_bc_chbox.stateChanged.connect(self.convert_user_bc_checked)
        self.user_streets_chbox.stateChanged.connect(self.convert_user_streets_checked)
        self.user_channels_chbox.stateChanged.connect(self.convert_user_channels_checked)
        self.user_levees_chbox.stateChanged.connect(self.convert_user_levees_checked)
        self.user_structures_chbox.stateChanged.connect(self.convert_user_structures_checked)
        self.user_reservoirs_chbox.stateChanged.connect(self.convert_reservoirs_checked)
        self.user_fpxsec_chbox.stateChanged.connect(self.convert_user_fpxsec_checked)
        self.user_infil_chbox.stateChanged.connect(self.convert_user_infil_checked)
        self.user_storm_drains_chbox.stateChanged.connect(self.convert_user_storm_drains_checked)
        
       
    def convert_user_bc_checked(self):
        if self.user_bc_chbox.isChecked():
            self.methods[1] = self.convert_user_bc
        else:
            self.methods.pop(1)

    def convert_user_streets_checked(self):
        if self.user_streets_chbox.isChecked():
            self.methods[2] = self.convert_user_streets
        else:
            self.methods.pop(2)

    def convert_user_channels_checked(self):
        if self.user_channels_chbox.isChecked():
            self.methods[3] = self.convert_user_channels
        else:
            self.methods.pop(3)

    def convert_user_levees_checked(self):
        if self.user_levees_chbox.isChecked():
            self.methods[4] = self.convert_user_levees
        else:
            self.methods.pop(4)

    def convert_user_structures_checked(self):
        if self.user_structures_chbox.isChecked():
            self.methods[5] = self.convert_user_structures
        else:
            self.methods.pop(5)

    def convert_reservoirs_checked(self):
        if self.user_reservoirs_chbox.isChecked():
            self.methods[6] = self.convert_user_reservoirs
        else:
            self.methods.pop(6)

    def convert_user_fpxsec_checked(self):
        if self.user_fpxsec_chbox.isChecked():
            self.methods[7] = self.convert_user_fpxsec
        else:
            self.methods.pop(7)

    def convert_user_infil_checked(self):
        if self.user_infil_chbox.isChecked():
            self.methods[8] = self.convert_user_infil
        else:
            self.methods.pop(8)

    def convert_user_storm_drains_checked(self):
        if self.user_storm_drains_chbox.isChecked():
            self.methods[9] = self.convert_user_storm_drains
        else:
            self.methods.pop(9)
            
            
    def convert_user_bc (self):
        self.message += "User boundary conditions converted!\n"
        pass     
            
    def convert_user_streets (self):
        self.message += "User streets converted!\n"
        pass     
    
    def convert_user_channels (self):
        self.message += "User channels converted!\n"
        pass    
     
    def convert_user_levees (self):
        self.message += "User levees converted!\n"
        pass  
       
    def convert_user_structures (self):
        self.message += "User structures converted!\n"
        pass 
        
    def convert_user_reservoirs (self):
        self.message += "User reservoirs converted!\n"
        pass  
       
    def convert_user_fpxsec (self):
        self.message += "User floodplain xsections converted!\n"
        pass  
       
    def convert_user_infil (self):
        self.message += "User infiltration converted!\n"
        pass  
       
    def convert_user_storm_drains (self):
        self.message += "User storm drains converted!\n"
        pass     
             
            
            
            
            
            
            
            
            
            
#     def convert_domain(self):
#         pass
#         try:
#             grid_converter = SchemaGridConverter(self.con, self.iface, self.lyrs)
#             grid_converter.boundary_from_grid()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Grid to Computational Domain conversion!")
# 
#     def convert_roughness(self):
#         pass
#         try:
#             grid_converter = SchemaGridConverter(self.con, self.iface, self.lyrs)
#             grid_converter.roughness_from_grid()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Grid to Roughness conversion!")
# 
#     def convert_bc(self):
#         pass
#         try:
#             bc_converter = SchemaBCConverter(self.con, self.iface, self.lyrs)
#             bc_converter.create_user_bc()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Boundary Conditions conversion!")
# 
#     def convert_1d(self):
#         pass
#         try:
#             domain_converter = Schema1DConverter(self.con, self.iface, self.lyrs)
#             domain_converter.create_user_lbank()
#             domain_converter.create_user_xs()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on 1D Domain elements conversion!")
# 
#     def convert_levees(self):
#         pass
#         try:
#             levee_converter = SchemaLeveesConverter(self.con, self.iface, self.lyrs)
#             levee_converter.create_user_levees()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Levees conversion!")
# 
#     def convert_fpxsec(self):
#         pass
#         try:
#             fpxsec_converter = SchemaFPXSECConverter(self.con, self.iface, self.lyrs)
#             fpxsec_converter.create_user_fpxsec()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Floodplain cross-sections conversion!")
# 
#     def convert_infil(self):
#         pass
#         try:
#             infil_converter = SchemaInfiltrationConverter(self.con, self.iface, self.lyrs)
#             infil_converter.create_user_infiltration()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Infiltration conversion!")
# 
#     def convert_swmm(self):
#         pass
#         try:
#             swmm_converter = SchemaSWMMConverter(self.con, self.iface, self.lyrs)
#             swmm_converter.create_user_swmm_nodes()
#         except Exception as e:
#             self.uc.log_info(traceback.format_exc())
#             self.uc.bar_warn("Creating User Layers failed on Storm Drains conversion!")
