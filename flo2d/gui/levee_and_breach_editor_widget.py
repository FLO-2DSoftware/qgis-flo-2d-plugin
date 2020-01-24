#  -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_breach import GlobalBreachDialog, IndividualBreachDialog, LeveeFragilityCurvesDialog, IndividualLeveesDialog
from ..utils import float_or_zero
from qgis.PyQt.QtWidgets import QApplication

uiDialog, qtBaseClass = load_ui('levee_and_breach_editor')

class LeveeAndBreachEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.grid_lyr = None
        
        set_icon(self.levee_elevation_tool_btn, 'set_levee_elev.svg')
        self.levee_elevation_tool_btn.clicked.connect(self.levee_elevation_tool)        
        
        set_icon(self.create_breach_location_btn, 'mActionCapturePoint.svg')
        self.create_breach_location_btn.clicked.connect(self.create_point_breach)
        
        set_icon(self.save_breach_location_btn, 'mactionsavealledits.svg')
        self.save_breach_location_btn.clicked.connect(self.save_breach_location_edits)
        
        set_icon(self.revert_breach_changes_btn, 'mactionundo.svg')
        self.revert_breach_changes_btn.clicked.connect(self.revert_breach_lyr_edits)
                
    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            
            # Widgets connections:
            self.global_breach_data_btn.clicked.connect(self.show_global_breach_dialog)
            self.individual_breach_data_btn.clicked.connect(self.show_individual_breach_dialog)
            self.levee_fragility_curves_btn.clicked.connect(self.show_levee_fragility_curves_dialog)
            self.show_levees_btn.clicked.connect(self.show_levees)
            self.no_failure_radio.clicked.connect(self.update_levee_failure_mode)
            self.prescribed_failure_radio.clicked.connect(self.update_levee_failure_mode)
            self.breach_failure_radio.clicked.connect(self.update_levee_failure_mode)
            self.crest_increment_dbox.editingFinished.connect(self.update_crest_increment)
            self.transport_eq_cbo.currentIndexChanged.connect(self.update_general_breach_data)
            self.initial_breach_width_depth_ratio_dbox.valueChanged.connect(self.update_general_breach_data)
            self.weir_coefficient_dbox.editingFinished.connect(self.update_general_breach_data)
            self.time_to_initial_failure_dbox.valueChanged.connect(self.update_general_breach_data) 
             
       
            self.populate_levee_and_breach_widget()
            
    def populate_levee_and_breach_widget(self):
 
        qry = 'SELECT ibreachsedeqn, gbratio, gweircoef, gbreachtime FROM breach_global'
        row = self.gutils.execute(qry).fetchone()
        if not row:
            return
        
        equation = row[0]-1 if row[0] is not None else 0
        self.transport_eq_cbo.setCurrentIndex(equation)        
        self.initial_breach_width_depth_ratio_dbox.setValue(float_or_zero(row[1]))
        self.weir_coefficient_dbox.setValue(float_or_zero(row[2]))
        self.time_to_initial_failure_dbox.setValue(float_or_zero(row[3]))

        qry = 'SELECT raiselev, ilevfail FROM levee_general'
        row = self.gutils.execute(qry).fetchone()
        if not row:
            return

        if row[1] == 1:
            self.prescribed_failure_radio.setChecked(True)  
        elif row[1] == 2:
            self.breach_failure_radio.setChecked(True)
        else:
            self.no_failure_radio.setChecked(True) 
                 
        self.crest_increment_dbox.setValue(float_or_zero(row[0]))

        self.enable_breach_group()

    def levee_elevation_tool(self):
        return 
    def create_point_breach(self):
        if not self.lyrs.enter_edit_mode('breach'):
            return

    def save_breach_location_edits(self):
        if not self.lyrs.any_lyr_in_edit('breach'):
            return
        self.lyrs.save_lyrs_edits('breach')
        
    def revert_breach_lyr_edits(self):
        breach_lyr_edited = self.lyrs.rollback_lyrs_edits('breach')

    def show_levees(self):
        """
        Shows individual levees dialog.

        """        
        if self.gutils.is_table_empty('levee_data'): 
            self.uc.bar_info("There aren't cells with levees defined!") 
            self.uc.show_info("There are no Levees defined in Schematic layers!\n\n" +
                              "Use the 'Levee Elevation Tool' in the FLO-2D tool bar to create Schematic levees from User levees Lines.")            
            return   
        
        QApplication.setOverrideCursor(Qt.WaitCursor) 
        dlg_individual_levees = IndividualLeveesDialog(self.iface, self.lyrs)
        QApplication.restoreOverrideCursor()
        close = dlg_individual_levees.exec_()
        self.lyrs.clear_rubber()   
                                       
    def show_global_breach_dialog(self):
        """
        Shows global breach dialog.

        """
        dlg_global_breach = GlobalBreachDialog(self.iface, self.lyrs)
        dlg_global_breach.equation = self.transport_eq_cbo.currentIndex() + 1
        dlg_global_breach.ratio = self.initial_breach_width_depth_ratio_dbox.value()
        dlg_global_breach.weird = self.weir_coefficient_dbox.value()
        dlg_global_breach.time = self.time_to_initial_failure_dbox.value()  
        
        save = dlg_global_breach.exec_()
        if save:
            try:
                if dlg_global_breach.save_breach_global_data():
                    self.uc.bar_info('Breach Global Data saved.')
                else:
                     self.uc.bar_info('Saving of Breach Global Data failed!.')    
            except Exception as e:                
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 210119.0626: assignment of Breach Global Data failed!"
                           +'\n__________________________________________________', e)               

    def show_individual_breach_dialog(self):
        """
        Shows individual breach dialog.

        """
        if self.gutils.is_table_empty('breach_cells'):
            self.uc.bar_info("There aren't individual breach cells!") 
            return
                    
        dlg_individual_breach = IndividualBreachDialog(self.iface, self.lyrs)
        save = dlg_individual_breach.exec_()
        if save:
            try:
                if dlg_individual_breach.save_individual_breach_data():
                    self.uc.bar_info('Individual Breach Data saved.')
                else:
                     self.uc.bar_info('Saving of Individual Breach Data failed!.')    
            except Exception as e:                
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 040219.2004: assignment of Individual Breach Data failed!"
                           +'\n__________________________________________________', e) 

    def show_levee_fragility_curves_dialog(self):
        """
        Shows levee fragility curves dialog.

        """
        dlg_levee_fragility = LeveeFragilityCurvesDialog(self.iface, self.lyrs)
        save = dlg_levee_fragility.exec_()
        if save:
            try:
                if dlg_levee_fragility.save_current_probability_table():
                    self.uc.bar_info('Fragility curve data saved.')
                else:
                     self.uc.bar_info('Saving of Fragility Curve Data failed!.')    
            except Exception as e:                
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 130219.0746: Saving of Fragility Curve Data failed!"
                           +'\n__________________________________________________', e) 

    def fill_levee_general_with_defauts_if_empty(self):   
         if self.gutils.is_table_empty('levee_general'):
            sql = '''INSERT INTO levee_general DEFAULT VALUES;'''
            self.gutils.execute(sql,)

    def update_levee_failure_mode(self):
        self.fill_levee_general_with_defauts_if_empty()
        qry = '''UPDATE levee_general SET ilevfail = ?;'''
        value = 0 if self.no_failure_radio.isChecked() else 1 if self.prescribed_failure_radio.isChecked() else 2 if self.breach_failure_radio.isChecked() else 0
        self.gutils.execute(qry, (value,)) 
        
        self.enable_breach_group()
        
    def enable_breach_group(self): 
        if self.no_failure_radio.isChecked():
            self.breach_grp.setDisabled(True)
#             self.show_levees_btn.setEnabled(True)
            
        elif self.prescribed_failure_radio.isChecked(): 
            self.breach_grp.setDisabled(True)
#             self.show_levees_btn.setEnabled(True)
        else:       
            self.breach_grp.setEnabled(True)  
#             self.show_levees_btn.setEnabled(False)   
                            
    def update_crest_increment(self):
        self.fill_levee_general_with_defauts_if_empty()
        qry = '''UPDATE levee_general SET raiselev = ?;'''
        value = self.crest_increment_dbox.value()
        self.gutils.execute(qry, (value,))

    def fill_breach_global_with_defauts_if_empty(self):   
         if self.gutils.is_table_empty('breach_global'):
            sql = '''INSERT INTO breach_global DEFAULT VALUES;'''
            self.gutils.execute(sql,)       
            
       

    def update_general_breach_data(self):
        self.fill_breach_global_with_defauts_if_empty()        
        qry = '''UPDATE breach_global SET ibreachsedeqn = ?,  gbratio = ?, gweircoef = ?, gbreachtime = ?; '''
        equation = self.transport_eq_cbo.currentIndex() + 1
        ratio = self.initial_breach_width_depth_ratio_dbox.value()
        weird = self.weir_coefficient_dbox.value()
        time = self.time_to_initial_failure_dbox.value()    
        self.gutils.execute(qry, (equation, ratio, weird, time))    
        
                     
    def update_transport_eq(self):
        self.fill_breach_global_with_defauts_if_empty()
        qry = '''UPDATE breach_global SET ibreachsedeqn = ?;'''
        value = self.transport_eq_cbo.currentIndex() + 1
        self.gutils.execute(qry, (value,))

    def update_initial_breach_width_depth_ratio(self):
        self.fill_breach_global_with_defauts_if_empty()        
        qry = '''UPDATE breach_global SET gbratio = ?;'''
        value = self.initial_breach_width_depth_ratio_dbox.value()
        self.gutils.execute(qry, (value,))
        
    def update_weird_coefficient(self):
        self.fill_breach_global_with_defauts_if_empty()
        qry = '''UPDATE breach_global SET gweircoef = ?;'''
        value = self.weir_coefficient_dbox.value()
        self.gutils.execute(qry, (value,))
        
    def update_time_to_initial_failure(self):
        self.fill_breach_global_with_defauts_if_empty()        
        qry = '''UPDATE breach_global SET gbreachtime = ?;'''
        value = self.time_to_initial_failure_dbox.value()
        self.gutils.execute(qry, (value,))