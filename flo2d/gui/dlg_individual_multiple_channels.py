# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from ..flo2d_tools.grid_tools import highlight_selected_segment, highlight_selected_xsection_a
from qgis.PyQt.QtWidgets import QTableWidgetItem, QApplication
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero, int_or_zero

uiDialog, qtBaseClass = load_ui('individual_multiple_channels_data')

class IndividualMultipleChannelsDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.setup_connection()
        self.individual_multiple_channel_element_cbo.currentIndexChanged.connect(self.individual_mc_element_cbo_currentIndexChanged)
        self.populate_individual_multiple_cells_dialog()


    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_individual_multiple_cells_dialog(self):
        qry_mc_cells = '''SELECT area_fid, grid_fid FROM mult_cells'''
        mc_rows = self.gutils.execute(qry_mc_cells).fetchall() 
        if not mc_rows:
            return
         
        for row in mc_rows:
            self.individual_multiple_channel_element_cbo.addItem(str(row[1]))

    def individual_mc_element_cbo_currentIndexChanged(self):
        qry_mc = '''SELECT 
                        wdr,
                        dm , 
                        nodchns , 
                        xnmult
                FROM mult_areas
                WHERE fid = ?;'''    
         
        qry_mc_cell = '''SELECT area_fid FROM mult_cells WHERE grid_fid = ?'''
         
        mc = self.gutils.execute(qry_mc_cell, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()  
        row = self.gutils.execute(qry_mc, (mc[0],)).fetchone()    
         
        if not row:
            pass
         
        self.imc_width_dbox.setValue(float_or_zero(row[0]))
        self.imc_depth_dbox.setValue(float_or_zero(row[1]))
        self.imc_number_sbox.setValue(int_or_zero(row[2]))
        self.imc_manning_dbox.setValue(float_or_zero(row[3]))
        
        
    def save_individual_breach_data(self):
        pass
#         """
#         Save changes to breach.
#         """
#         update_qry = '''
#         UPDATE breach
#         SET ibreachdir = ?,
#             zu = ? , 
#             zd  = ? , 
#             zc = ?  , 
#             crestwidth = ?  , 
#             crestlength  = ? ,
#             brbotwidmax  = ? , 
#             brtopwidmax  = ? , 
#             brbottomel = ? , 
#             d50c  = ? , 
#             porc = ?  , 
#             uwc = ?  ,
#             cnc = ? , 
#             afrc = ? , 
#             cohc = ? , 
#             unfcc  = ? ,
#             d50s = ?  , 
#             pors = ?   , 
#             uws = ?  , 
#             cns = ?  , 
#             afrs = ?  , 
#             cohs = ?  , 
#             unfcs = ?  , 
#             grasslength = ?  , 
#             grasscond = ?  , 
#             grassvmaxp = ?  ,
#             sedconmax = ?  , 
#             d50df = ?  , 
#             unfcdf = ?  
#         WHERE fid = ? ; '''
# 
# 
#         qry_breach_cell = '''SELECT breach_fid FROM breach_cells WHERE grid_fid = ?'''
#         
#                       
#         try:
#             breach = self.gutils.execute(qry_breach_cell, (self.individual_breach_element_cbo.currentText(),)).fetchone()    
#             self.gutils.execute(update_qry, (
#                 self.breach_failure_direction_cbo.currentIndex(),
#                 self.zu_dbox.value(),
#                 self.zd_dbox.value(),
#                 self.zc_dbox.value(),
#                 self.crestwidth_dbox.value(),
#                 self.crestlength_dbox.value(),
#                 self.brbotwidmax_dbox.value(),
#                 self.brtopwidmax_dbox.value(),
#                 self.brbottomel_dbox.value(),
#                 self.d50c_dbox.value(),
#                 self.porc_dbox.value(),
#                 self.uwc_dbox.value(),
#                 self.cnc_dbox.value(),
#                 self.afrc_dbox.value(),
#                 self.cohc_dbox.value(),
#                 self.unfcc_dbox.value(),
#                 self.d50s_dbox.value(),
#                 self.pors_dbox.value(),
#                 self.uws_dbox.value(),
#                 self.cns_dbox.value(),
#                 self.afrs_dbox.value(),
#                 self.cohs_dbox.value(),
#                 self.unfcs_dbox.value(),
#                 self.grasslength_dbox.value(),
#                 self.grasscond_dbox.value(),
#                 self.grassvmaxp_dbox.value(),
#                 self.sedconmax_dbox.value(),
#                 self.d50df_dbox.value(),
#                 self.unfcdf_dbox.value(),
#                 breach[0]
#                 ))
#             
#             return True
#         except Exception as e:                
#             QApplication.restoreOverrideCursor()
#             self.uc.show_error("ERROR 040219.2015: update of Individual Breach Data failed!"
#                        +'\n__________________________________________________', e)  
#             return False 

