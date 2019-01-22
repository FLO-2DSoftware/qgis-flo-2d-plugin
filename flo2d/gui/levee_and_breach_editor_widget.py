#  -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_breach_global import GlobalBreachDialog
from ..utils import float_or_zero

uiDialog, qtBaseClass = load_ui('levee_and_breach')

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

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.global_breach_data_btn.clicked.connect(self.show_global_breach_dialog)
            self.populate_levee_and_breach_widget()
            
            self.transport_eq_cbo.currentIndexChanged.connect(self.update_transport_eq)
            self.initial_breach_width_depth_ratio_dbox.valueChanged.connect(self.update_initial_breach_width_depth_ratio)
            self.weird_coefficient_dbox.valueChanged.connect(self.update_weird_coefficient)
            self.time_to_initial_failure_dbox.valueChanged.connect(self.update_time_to_initial_failure)
            
    def populate_levee_and_breach_widget(self):
 
        qry = 'SELECT ibreachsedeqn, gbratio, gweircoef, gbreachtime FROM breach_global'
        row = self.gutils.execute(qry).fetchone()
        if not row:
            return
        
        equation = row[0]-1 if row[0] is not None else 0
        self.transport_eq_cbo.setCurrentIndex(equation)        
        self.initial_breach_width_depth_ratio_dbox.setValue(float_or_zero(row[1]))
        self.weird_coefficient_dbox.setValue(float_or_zero(row[2]))
        self.time_to_initial_failure_dbox.setValue(float_or_zero(row[3]))


    def show_channel_segment_dependencies(self):
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('Schematized Channel Segments (left bank) Layer is empty!.')
            return

        idx = self.channel_segment_cbo.currentIndex() + 1

        qry_wsel = '''SELECT istart, wselstart, iend, wselend FROM chan_wsel WHERE seg_fid = ?;'''
        data_wsel = self.gutils.execute(qry_wsel, (idx,)).fetchone()
        if data_wsel is None:
            self.initial_flow_elements_grp.setChecked(False)
        else:
            # Set fields:
            self.first_element_box.setValue(data_wsel[0])
            self.starting_water_elev_dbox.setValue(data_wsel[1]),
            self.last_element_box.setValue(data_wsel[2]),
            self.ending_water_elev_dbox.setValue(data_wsel[3])
            self.initial_flow_elements_grp.setChecked(True)

        qry_chan = '''SELECT isedn, depinitial, froudc, roughadj, isedn FROM chan WHERE fid = ?;'''
        data_chan = self.gutils.execute(qry_chan, (idx,)).fetchone()
        self.initial_flow_for_all_dbox.setValue(data_chan[1])
        self.max_froude_number_dbox.setValue(data_chan[2])
        self.roughness_adjust_coeff_dbox.setValue(data_chan[3])
        equation = data_chan[4]-1 if data_chan[4] is not None else 0
        self.transport_eq_cbo.setCurrentIndex(equation)

    def show_global_breach_dialog(self):
        """
        Shows global breach dialog.

        """
        dlg_global_breach = GlobalBreachDialog(self.iface, self.lyrs)
        save = dlg_global_breach.exec_()
        if save:
            try:
                if dlg_global_breach.save_breach_global_data():
                    self.uc.bar_info('Breach Global Data saved.')
                else:
                     self.uc.bar_info('Saving of Breach Global Data failed!.')    
            except Exception as e:                
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 21019.0626: assignment of Breach Global Data failed!"
                           +'\n__________________________________________________', e)               

    def update_transport_eq(self):
        qry = '''UPDATE breach_global SET ibreachsedeqn = ?;'''
        value = self.transport_eq_cbo.currentIndex() + 1
        self.gutils.execute(qry, (value,))

    def update_initial_breach_width_depth_ratio(self):
        qry = '''UPDATE breach_global SET gbratio = ?;'''
        value = self.initial_breach_width_depth_ratio_dbox.value()
        self.gutils.execute(qry, (value,))
        
    def update_weird_coefficient(self):
        qry = '''UPDATE breach_global SET gweircoef = ?;'''
        value = self.weird_coefficient_dbox.value()
        self.gutils.execute(qry, (value,))
        
    def update_time_to_initial_failure(self):
        qry = '''UPDATE breach_global SET gbreachtime = ?;'''
        value = self.time_to_initial_failure_dbox.value()
        self.gutils.execute(qry, (value,))