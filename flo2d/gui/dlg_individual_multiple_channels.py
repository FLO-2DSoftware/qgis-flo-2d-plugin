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
        qry_mc_cells = '''SELECT area_fid, grid_fid FROM mult_cells ORDER BY grid_fid'''
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
                FROM mult_cells
                WHERE grid_fid = ?;'''    
         
#         qry_mc_cell = '''SELECT area_fid FROM mult_cells WHERE grid_fid = ?'''
#          
#         mc = self.gutils.execute(qry_mc_cell, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()  
        row = self.gutils.execute(qry_mc, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()    
         
        if not row:
            pass
         
        self.imc_width_dbox.setValue(float_or_zero(row[0]))
        self.imc_depth_dbox.setValue(float_or_zero(row[1]))
        self.imc_number_sbox.setValue(int_or_zero(row[2]))
        self.imc_manning_dbox.setValue(float_or_zero(row[3]))        
        
    
#         qry_mc = '''SELECT 
#                         wdr,
#                         dm , 
#                         nodchns , 
#                         xnmult
#                 FROM mult_areas
#                 WHERE fid = ?;'''    
#          
#         qry_mc_cell = '''SELECT area_fid FROM mult_cells WHERE grid_fid = ?'''
#          
#         mc = self.gutils.execute(qry_mc_cell, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()  
#         row = self.gutils.execute(qry_mc, (mc[0],)).fetchone()    
#          
#         if not row:
#             pass
#          
#         self.imc_width_dbox.setValue(float_or_zero(row[0]))
#         self.imc_depth_dbox.setValue(float_or_zero(row[1]))
#         self.imc_number_sbox.setValue(int_or_zero(row[2]))
#         self.imc_manning_dbox.setValue(float_or_zero(row[3]))
        
        
    def save_individual_multiple_chennels_data(self):
        """
        Save changes to individual multiple channel.
        """
        update_qry = '''
        UPDATE mult_cells
        SET wdr = ?,
            dm = ? , 
            nodchns  = ? , 
            xnmult = ?
        WHERE grid_fid = ? ; '''
 
 
#         qry_mult_cell = '''SELECT area_fid FROM mult_cells WHERE grid_fid = ?'''
         
                       
        try:
#             mult_cell = self.gutils.execute(qry_mult_cell, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()    
            self.gutils.execute(update_qry, 
                                (   self.imc_width_dbox.value(),
                                    self.imc_depth_dbox.value(),
                                    self.imc_number_sbox.value(),
                                    self.imc_manning_dbox.value(),
                                    self.individual_multiple_channel_element_cbo.currentText()
                                ))
             
            return True
        except Exception as e:                
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 210319.0633: update of Individual Multiple Channel Data failed!"
                       +'\n__________________________________________________', e)  
            return False 
        
        
        
        
#         pass
#         """
#         Save changes to individual multiple channel.
#         """
#         update_qry = '''
#         UPDATE mult_areas
#         SET wdr = ?,
#             dm = ? , 
#             nodchns  = ? , 
#             xnmult = ?
#         WHERE fid = ? ; '''
#  
#  
#         qry_mult_cell = '''SELECT area_fid FROM mult_cells WHERE grid_fid = ?'''
#          
#                        
#         try:
#             mult_cell = self.gutils.execute(qry_mult_cell, (self.individual_multiple_channel_element_cbo.currentText(),)).fetchone()    
#             self.gutils.execute(update_qry, 
#                                 (   self.imc_width_dbox.value(),
#                                     self.imc_depth_dbox.value(),
#                                     self.imc_number_sbox.value(),
#                                     self.imc_manning_dbox.value(),
#                                     mult_cell[0]
#                                 ))
#              
#             return True
#         except Exception as e:                
#             QApplication.restoreOverrideCursor()
#             self.uc.show_error("ERROR 210319.0633: update of Individual Multiple Channel Data failed!"
#                        +'\n__________________________________________________', e)  
#             return False 

