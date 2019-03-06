# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from ..flo2dobjects import InletRatingTable
from qgis.PyQt.QtWidgets import QInputDialog, QTableWidgetItem, QDialogButtonBox, QApplication
from qgis.PyQt.QtGui import QColor
from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import m_fdata, float_or_zero, int_or_zero, is_number
from .table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan

uiDialog, qtBaseClass = load_ui('inlets')
class InletNodesDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.inlets_buttonBox.button(QDialogButtonBox.Save).setText("Save Inlet/Junctions to 'Storm Drain Nodes-Inlets/Junctions' User Layer")
        self.save_this_inlet_btn.setVisible(False)
        self.inletRT = None
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.inlet_data_model = StandardItemModel()
        self.inlet_series_data = None
        self.plot_item_name = None
        self.d1, self.d2 = [[], []]
        self.previous_type = -1

#         set_icon(self.show_table_btn, 'show_cont_table.svg')
#         set_icon(self.remove_rtable_btn, 'mActionDeleteSelected.svg')
#         set_icon(self.add_rtable_btn, 'add_bc_data.svg')
#         set_icon(self.rename_rtable_btn, 'change_name.svg')
#         self.show_table_btn.clicked.connect(self.populate_rtables_data)
#         self.remove_rtable_btn.clicked.connect(self.delete_rtables)
#         self.add_rtable_btn.clicked.connect(self.add_rtables)
#         self.rename_rtable_btn.clicked.connect(self.rename_rtables)

        

#         self.inlet_data_model.dataChanged.connect(self.save_rtables_data)
#         self.table.before_paste.connect(self.block_saving)
#         self.table.after_paste.connect(self.unblock_saving)
#         self.inlet_data_model.itemDataChanged.connect(self.itemDataChangedSlot)        
       
        self.setup_connection()
        
        
        
        self.inlet_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_inlet_in_table)
        self.inlets_buttonBox.accepted.connect(self.save_inlets)
        self.save_this_inlet_btn.clicked.connect(self.save_inlets)

        # Connections from individual controls to particular cell in inlets_tblw table widget:
        #self.grid_element.valueChanged.connect(self.grid_element_valueChanged)
        self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        self.max_depth_dbox.valueChanged.connect(self.max_depth_dbox_valueChanged)
        self.initial_depth_dbox.valueChanged.connect(self.initial_depth_dbox_valueChanged)
        self.surcharge_depth_dbox.valueChanged.connect(self.surcharge_depth_dbox_valueChanged)
        self.ponded_area_dbox.valueChanged.connect(self.ponded_area_dbox_valueChanged)
        self.inlet_drain_type_cbo.currentIndexChanged.connect(self.inlet_drain_type_cbo_currentIndexChanged)
        self.length_dbox.valueChanged.connect(self.length_dbox_valueChanged)
        self.width_dbox.valueChanged.connect(self.width_dbox_valueChanged)
        self.height_dbox.valueChanged.connect(self.height_dbox_valueChanged)
        self.weir_coeff_dbox.valueChanged.connect(self.weir_coeff_dbox_valueChanged)
        self.feature_sbox.valueChanged.connect(self.feature_sbox_valueChanged)
        self.curb_height_dbox.valueChanged.connect(self.curb_height_dbox_valueChanged)
        self.clogging_factor_dbox.valueChanged.connect(self.clogging_factor_dbox_valueChanged)
        self.time_for_clogging_dbox.valueChanged.connect(self.time_for_clogging_dbox_valueChanged)
        self.inlets_tblw.cellClicked.connect(self.inlets_tblw_cell_clicked)
        self.rating_table_cbo.currentIndexChanged.connect(self.rating_table_cbo_currentIndexChanged)
        
        self.rating_table_cbo.setDuplicatesEnabled(False)
        
        self.set_header()
        
        self.populate_inlets()
        
#         self.rating_table_cbo.currentIndexChanged.connect(self.populate_rtables_data)
        
        
    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.inletRT = InletRatingTable(self.con, self.iface)        
            self.populate_rtables()
            
    def set_header(self):
        self.inlets_tblw.setHorizontalHeaderLabels(["Name",                  #INP  and FLO-2D. SWMMFLO.DAT: SWMM_JT
                                                   "Grid Element",          #FLO-2D. SWMMFLO.DAT: SWMM_IDENT
                                                   "Invert Elev.",          #INP
                                                   "Max. Depth",            #INP
                                                   "Init. Depth",          #INP
                                                   "Surcharge Depth",      #INP
                                                   "Ponded Area",          #INP
                                                   "Inlet Drain Type",        #FLO-2D. SWMMFLO.DAT: INTYPE
                                                   "Length/Perimeter *",      #FLO-2D. SWMMFLO.DAT: SWMMlenght
                                                   "Width/Area *",            #FLO-2D. SWMMFLO.DAT: SWMMwidth
                                                   "Height/Sag/Surch *",      #FLO-2D. SWMMFLO.DAT: SWMMheight
                                                   "Weir Coeff *",            #FLO-2D. SWMMFLO.DAT: SWMMcoeff
                                                   "Feature *",               #FLO-2D. SWMMFLO.DAT: FLAPGATE
                                                   "Curb Height *",           #FLO-2D. SWMMFLO.DAT: CURBHEIGHT
                                                   "Clogging Factor #",       #FLO-2D. SDCLOGGING.DAT
                                                   "Time for Clogging #",     #FLO-2D. SDCLOGGING.DAT
                                                   "Rating Table"
                                                   ])    



    def invert_connect(self):
        self.uc.show_info('Connection!')

    # def grid_element_valueChanged(self):
    #     self.box_valueChanged(self.grid_element, 1)

    def invert_elevation_dbox_valueChanged(self):
        self.box_valueChanged(self.invert_elevation_dbox, 2)

    def max_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.max_depth_dbox, 3)

    def initial_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.initial_depth_dbox, 4)

    def surcharge_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.surcharge_depth_dbox, 5)

    def ponded_area_dbox_valueChanged(self):
        self.box_valueChanged(self.ponded_area_dbox, 6)

    def inlet_drain_type_cbo_currentIndexChanged(self):
        row = self.inlet_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, self.inlet_drain_type_cbo.currentIndex()+1)
        self.inlets_tblw.setItem(row, 7, item)

        if self.inlet_drain_type_cbo.currentIndex() + 1 == 4:
            self.label_17.setEnabled(True)
            self.rating_table_cbo.setEnabled(True)
#             self.show_table_btn.setEnabled(True)
#             self.add_rtable_btn.setEnabled(True)
#             self.remove_rtable_btn.setEnabled(True)
#             self.rename_rtable_btn.setEnabled(True)
            # Variables related with SWMMFLO.DAT and SDCLOGGING.DAT:
            self.length_dbox.setEnabled(False)
            self.width_dbox.setEnabled(False)
            self.height_dbox.setEnabled(False)
            self.weir_coeff_dbox.setEnabled(False)
            self.feature_sbox.setEnabled(False)
            self.curb_height_dbox.setEnabled(False)
            self.clogging_factor_dbox.setEnabled(False)
            self.time_for_clogging_dbox.setEnabled(False)        
            
        else:
            self.label_17.setEnabled(False)
            self.rating_table_cbo.setEnabled(False)
#             self.show_table_btn.setEnabled(False)
#             self.add_rtable_btn.setEnabled(False)
#             self.remove_rtable_btn.setEnabled(False)
#             self.rename_rtable_btn.setEnabled(False)
            # Variables related with SWMMFLO.DAT and SDCLOGGING.DAT:
            self.length_dbox.setEnabled(True)
            self.width_dbox.setEnabled(True)
            self.height_dbox.setEnabled(True)
            self.weir_coeff_dbox.setEnabled(True)
            self.feature_sbox.setEnabled(True)
            self.curb_height_dbox.setEnabled(True)
            self.clogging_factor_dbox.setEnabled(True)
            self.time_for_clogging_dbox.setEnabled(True)  
            
    def length_dbox_valueChanged(self):
        self.box_valueChanged(self.length_dbox, 8)

    def width_dbox_valueChanged(self):
        self.box_valueChanged(self.width_dbox, 9)

    def height_dbox_valueChanged(self):
        self.box_valueChanged(self.height_dbox, 10)

    def weir_coeff_dbox_valueChanged(self):
        self.box_valueChanged(self.weir_coeff_dbox, 11)

    def feature_sbox_valueChanged(self):
        self.box_valueChanged(self.feature_sbox, 12)

    def curb_height_dbox_valueChanged(self):
        self.box_valueChanged(self.curb_height_dbox, 13)

    def clogging_factor_dbox_valueChanged(self):
        self.box_valueChanged(self.clogging_factor_dbox, 14)

    def time_for_clogging_dbox_valueChanged(self):
        self.box_valueChanged(self.time_for_clogging_dbox, 15)

    def box_valueChanged(self, widget, col):
        row = self.inlet_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        self.inlets_tblw.setItem(row, col, item)

    def rating_table_cbo_currentIndexChanged(self):
        row = self.inlet_cbo.currentIndex()
        rt = self.rating_table_cbo.currentText()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, rt)
        self.inlets_tblw.setItem(row, 16, item)

    def inlets_tblw_valueChanged(self, I, J):
        self.uc.show_info('TABLE CHANGED in ' + str(I) + '  ' + str(J))

    def inlets_tblw_cell_clicked(self, row, column):
        self.inlet_cbo.blockSignals(True)
        self.inlet_cbo.setCurrentIndex(row)
        self.inlet_cbo.blockSignals(False)

        self.grid_element.setText(self.inlets_tblw.item(row,1).text())
        self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,2)))
        self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,3)))
        self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,4)))
        self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,5)))
        self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,6)))
        
        val = self.inlets_tblw.item(row,7).text()
        index = int(val if val != "" else 1)-1
        index = 4 if index > 4 else 0 if index < 0 else index
        self.inlet_drain_type_cbo.setCurrentIndex(index)
        
        self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,8)))
        self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,9)))
        self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,10)))
        self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,11)))
        self.feature_sbox.setValue(float_or_zero(self.inlets_tblw.item(row,12)))
        self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,13)))
        self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,14)))
        self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row,15)))
        
        rt_name = self.inlets_tblw.item(row,16).text().strip()
        rt_name = rt_name if rt_name is not None else 0
        idx = self.rating_table_cbo.findText(rt_name)
        self.rating_table_cbo.setCurrentIndex(idx)        
         
    def populate_inlets(self):
                 
        qry = '''SELECT
                        name, 
                        grid, 
                        junction_invert_elev,
                        max_depth, 
                        init_depth, 
                        surcharge_depth, 
                        ponded_area, 
                        intype, 
                        swmm_length, 
                        swmm_width, 
                        swmm_height,
                        swmm_coeff,
                        swmm_feature,
                        curbheight,
                        swmm_clogging_factor,
                        swmm_time_for_clogging,
                        rt_name           
                FROM user_swmm_nodes WHERE sd_type= 'I';'''
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            self.uc.bar_warn("No inlets defined in 'Storm Drain Nodes' User Layer!")
            return

        self.inlets_tblw.setRowCount(0)
        for row_number, row_data in enumerate(rows):
            self.inlets_tblw.insertRow(row_number)
            for cell, data in enumerate(row_data):
#                 if cell == 17 and (data is None or data == '0'):
#                     data = "?"
#                 elif data is None:
#                     data = 0        

                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, data)
                # Fill the list of inlet names:
                if cell == 0:
                    self.inlet_cbo.addItem(data)

                # Fill all text boxes with data of first feature of query (first cell in table user_swmm_nodes):
                if row_number == 0:
                    if cell == 1:
                        self.grid_element.setText(str(data))
                    elif cell == 2:
                        self.invert_elevation_dbox.setValue(data if data is not None else 0)
                    elif cell == 3:
                        self.max_depth_dbox.setValue(data if data is not None else 0)
                    elif cell == 4:
                        self.initial_depth_dbox.setValue(data if data is not None else 0)
                    elif cell == 5:
                        self.surcharge_depth_dbox.setValue(data if data is not None else 0)
                    elif cell == 6:
                        self.ponded_area_dbox.setValue(data if data is not None else 0)
                    elif cell == 7:
                        self.inlet_drain_type_cbo.setCurrentIndex(data-1)
                        self.previous_type = data-1
                    elif cell == 8:
                        self.length_dbox.setValue(data if data is not None else 0)
                    elif cell == 9:
                        self.width_dbox.setValue(data if data is not None else 0)
                    elif cell == 10:
                        self.height_dbox.setValue(data if data is not None else 0)
                    elif cell == 11:
                        self.weir_coeff_dbox.setValue(data if data is not None else 0)
                    elif cell == 12:
                        self.feature_sbox.setValue(data if data is not None else 0)
                    elif cell == 13:
                        self.curb_height_dbox.setValue(data if data is not None else 0)
                    elif cell == 14:
                        self.clogging_factor_dbox.setValue(data if data is not None else 0)
                    elif cell == 15:
                        self.time_for_clogging_dbox.setValue(data if data is not None else 0)
                    elif cell == 16:     
#                         idx = self.rating_table_cbo.findData(data if data is not None else 0)
#                         self.rating_table_cbo.setCurrentIndex(idx)

                        idx = self.rating_table_cbo.findText(data if data is not None else 0)
                        self.rating_table_cbo.setCurrentIndex(idx)                        
                        
                if cell == 1 or cell == 2:
                        item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled )

                self.inlets_tblw.setItem(row_number, cell, item)
#         self.populate_rtables_data()    
          
    def fill_individual_controls_with_current_inlet_in_table(self):
        # Highlight row in table:
        row = self.inlet_cbo.currentIndex()
        self.inlets_tblw.selectRow(row)
        inlet_type_index = -1
        # Load controls with selected row in table:
        item = QTableWidgetItem()
        item = self.inlets_tblw.item(row, 1)
        if item is not None:
            self.grid_element.setText(str(item.text()))
        self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 2)))
        self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 3)))
        self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 4)))
        self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 5)))
        self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 6)))
        item = self.inlets_tblw.item(row, 7) # Inlet type
        if item is not None:
            inlet_type_index  = int(item.text() if item.text() != "" else 1)
            inlet_type_index = 4 if inlet_type_index > 4 else 0 if inlet_type_index < 0 else inlet_type_index-1
            self.inlet_drain_type_cbo.setCurrentIndex(inlet_type_index)
        self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 8)))
        self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 9)))
        self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 10)))
        self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 11)))
        self.feature_sbox.setValue(int_or_zero(self.inlets_tblw.item(row, 12)))
        self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 13)))
        self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 14)))
        self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 15)))
        
        if inlet_type_index == 3:
            rt_name = self.inlets_tblw.item(row, 16)
            rt_name = rt_name.text() if  rt_name.text() is not None else ""
            idx = self.rating_table_cbo.findData(rt_name)
            self.rating_table_cbo.setCurrentIndex(idx)                                                 
            
    def save_inlets(self):
        """
        Save changes of user_swmm_nodes layer.
        """
        try:
            update_qry = '''
            UPDATE user_swmm_nodes
            SET
                name = ?, 
                grid = ?, 
                junction_invert_elev = ?,
                max_depth = ?, 
                init_depth = ?, 
                surcharge_depth = ?, 
                ponded_area = ?, 
                intype = ?, 
                swmm_length = ?, 
                swmm_width = ?, 
                swmm_height = ?,
                swmm_coeff = ?,
                swmm_feature = ?,
                curbheight = ?,
                swmm_clogging_factor = ?,
                swmm_time_for_clogging = ?,
                rt_name = ?
            WHERE fid = ?;'''
    
            replace_rt = '''REPLACE INTO swmmflort (grid_fid, name) VALUES (?,?);'''  
            delete_rt = '''DELETE FROM swmmflort where grid_fid = ?;'''    
            insert_rt = '''INSERT INTO swmmflort (grid_fid, name) values (?,?);''' 
            
            inlets = []
            type4 = []
            no_rt = 0
            no_rt_names = ""
              
            for row in range(0, self.inlets_tblw.rowCount()):
                item = QTableWidgetItem()
    
                fid = row + 1
    
                item = self.inlets_tblw.item(row, 0)
                if item is not None:
                    name = str(item.text()) if str(item.text()) != "" else ' '
    
                item = self.inlets_tblw.item(row, 1)
                if item is not None:
                    grid = str(item.text()) if str(item.text()) != "" else ' '
    
                item = self.inlets_tblw.item(row, 2)
                if item is not None:
                    invert_elev = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 3)
                if item is not None:
                    max_depth= str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 4)
                if item is not None:
                    init_depth = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 5)
                if item is not None:
                    surcharge_depth = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 6)
                if item is not None:
                    ponded_area = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 7)
                if item is not None:
                    intype = str(item.text()) if str(item.text()) != "" else '1'
    
                item = self.inlets_tblw.item(row, 8)
                if item is not None:
                    swmm_length = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 9)
                if item is not None:
                    swmm_width = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 10)
                if item is not None:
                    swmm_height = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 11)
                if item is not None:
                    swmm_coeff = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 12)
                if item is not None:
                    swmm_feature = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 13)
                if item is not None:
                    curbheight = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 14)
                if item is not None:
                    swmm_clogging_factor = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 15)
                if item is not None:
                    swmm_time_for_clogging = str(item.text()) if str(item.text()) != "" else '0'
    
                item = self.inlets_tblw.item(row, 16)
                if item is not None:
                    if intype == '4': # Rating table.         
                        rt_name = str(item.text())
                        idx = self.rating_table_cbo.findText(rt_name)
                        if idx == -1:
                            rt_name = ''
                    else:
                        rt_name = ''        
                else:
                    rt_name = ''
                 
                # Append grid number to rating table name if doesn't have it already. 
                old_rt_name = rt_name 
                if rt_name != '':
                    if '.G' not in rt_name:
                        rt_name = rt_name + '.G' + grid
                    else:    
                        head, sep, tail = rt_name.partition('.G') 
                        rt_name = head + '.G' + grid
                                           
                inlets.append(( name,
                                grid,
                                invert_elev,
                                max_depth,
                                init_depth,
                                surcharge_depth,
                                ponded_area,
                                intype,
                                swmm_length,
                                swmm_width,
                                swmm_height,
                                swmm_coeff,
                                swmm_feature,
                                curbheight,
                                swmm_clogging_factor,
                                swmm_time_for_clogging,
                                rt_name,
                                fid
                            ))        
                
                # See if rating table doesn't exists in swmmflort:
                if intype == '4': # Rating table. 
                    if rt_name != '':
                        qry = 'SELECT grid_fid, name, fid FROM swmmflort WHERE grid_fid = ? AND name = ?'
                        row = self.gutils.execute(qry, (grid, rt_name)).fetchone()
                        if row:
                            if row[0]:
                                if row[1] != rt_name:
                                    type4.append((grid, rt_name))
                                else:
                                    # rating table exists in swmmflort, does it have pairs of values in swmmflort_data
                                    data_qry = 'SELECT * FROM swmmflort_data WHERE swmm_rt_fid = ?'
                                    data = self.gutils.execute(data_qry, (row[2],)).fetchone()
                                    if data is None:
                                        if self.uc.question('WARNING 060319.0640:\n\nNo data for rating table  "' + str(row[1]) + '"  of cell ' + str(row[0]) +
                                                            '\n\nWould you like to create it?'):
                                            self.add_rating_table_data(row[2], fetch=False)                                        
                            else:
                                type4.append((grid, rt_name))  
                        else:
                            type4.append((grid, rt_name))                    
                    else:
                        no_rt += 1
                        no_rt_names += "\n" + grid + "   (" + name + ")"               
            
            # Update 'user_swmm_nodes' table:
            self.gutils.execute_many(update_qry, inlets)
            
            
            # Update 'swmmflort' table:
            if type4:
                for item in type4:
                    self.gutils.execute(insert_rt, item)
#                 self.gutils.execute_many(insert_rt, type4)
            
            if no_rt > 0:   
                QApplication.restoreOverrideCursor()
                self.uc.show_info("WARNING 020219.1836: The following " + str(no_rt) + 
                                  " grid element(s) have inlet of type 4 (stage discharge with rating table) but don't have rating table assigned:\n"
                                  + no_rt_names)          
            
            self.update_rating_tables_in_storm_drain_widget()
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 020219.0812: couldn't save inlets/junction into User Storm Drain Nodes!"
                       +'\n__________________________________________________', e)                      
            
    def populate_rtables(self):
#         rt_qry = '''SELECT name FROM swmmflort'''
#         rt_names = self.gutils.execute(rt_qry).fetchall()
#         list = []
#         for name in rt_names:
#             name = name[0].strip()
#             if name != '':           
#                 if name not in list:
#                     list.append(name)
#         self.rating_table_cbo.clear()  
#         self.rating_table_cbo.addItems(list)          

        self.rating_table_cbo.clear()
        for row in self.inletRT.get_rating_tables():
            rt_fid, name = [x if x is not None else '' for x in row]
            if name != '':
                self.rating_table_cbo.addItem(name, rt_fid)                
                
                          
#     def block_saving(self):
#         try_disconnect(self.inlet_data_model.dataChanged, self.save_rtables_data)
# 
#     def unblock_saving(self):
#         self.inlet_data_model.dataChanged.connect(self.save_rtables_data)
# 
#     def itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
#         """
#         Slot used to push changes of existing items onto undoStack.
#         """
#         if role == Qt.EditRole:
#             command = CommandItemEdit(self, item, old_value, new_value,
#                                       "Text changed from '{0}' to '{1}'".format(old_value, new_value))
#             self.tview.undoStack.push(command)
#             return True

#     def populate_rtables(self):
#         qry = '''SELECT name FROM swmmflort '''
#         rt_names= self.gutils.execute(qry)
#         self.rating_table_cbo.clear()
#         for rt in rt_names:
#             if rt[0] is not None and rt[0] != '':
#                 self.rating_table_cbo.addItem(rt[0])

#     def add_rtables(self):
#         if not self.inletRT:
#             return
#         self.inletRT.add_rating_table()
#         self.populate_rtables()
# 
#     def delete_rtables(self):
#         if not self.inletRT:
#             return
#         idx = self.rating_table_cbo.currentIndex()
#         rt_fid = self.rating_table_cbo.itemData(idx)
#         self.inletRT.del_rating_table(rt_fid)
#         self.populate_rtables()
# 
#     def rename_rtables(self):
#         if not self.inletRT:
#             return
#         new_name, ok = QInputDialog.getText(None, 'Change rating table name', 'New name:')
#         if not ok or not new_name:
#             return
#         if not self.rating_table_cbo.findText(new_name) == -1:
#             msg = 'Rating table with name {} already exists in the database. Please, choose another name.'.format(
#                 new_name)
#             self.uc.show_warn(msg)
#             return
#         idx = self.rating_table_cbo.currentIndex()
#         rt_fid = self.rating_table_cbo.itemData(idx)
#         self.inletRT.set_rating_table_data_name(rt_fid, new_name)
#         self.populate_rtables()

    def populate_rtables_data(self):
        idx = self.rating_table_cbo.currentIndex()
        rt_fid = self.rating_table_cbo.itemData(idx)
        rt_name =  self.rating_table_cbo.itemText(idx)
        if rt_fid is None:
            self.uc.bar_warn("No rating table defined!")
            return
 
        self.inlet_series_data = self.inletRT.get_rating_tables_data(rt_fid)
        if not self.inlet_series_data:
            return
        self.create_plot()
        self.tview.undoStack.clear()
        self.tview.setModel(self.inlet_data_model)
        self.inlet_data_model.clear()
        self.inlet_data_model.setHorizontalHeaderLabels(['Depth', 'Q'])
        self.d1, self.d1 = [[], []]
        for row in self.inlet_series_data:
            items = [StandardItem('{:.4f}'.format(x)) if x is not None else StandardItem('') for x in row]
            self.inlet_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
        rc = self.inlet_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ('',) * 2]
                self.inlet_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.inlet_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.update_plot()

    def add_rating_table_data(self, rt_fid, rows=5, fetch=False):
        """
        Add new rows to swmmflort_data for a given rt_fid.
        """
        qry = 'INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, 0, 0);'
        self.gutils.execute_many(qry, ([rt_fid],) * rows)
        if fetch:
            return self.get_rating_tables_data(rt_fid)
#     def save_rtables_data(self):
#         idx = self.rating_table_cbo.currentIndex()
#         rt_fid = self.rating_table_cbo.itemData(idx)
#         self.update_plot()
#         rt_data = []
# 
#         for i in range(self.inlet_data_model.rowCount()):
#             # save only rows with a number in the first column
#             if is_number(m_fdata(self.inlet_data_model, i, 0)) and not isnan(m_fdata(self.inlet_data_model, i, 0)):
#                 rt_data.append(
#                     (
#                         rt_fid,
#                         m_fdata(self.inlet_data_model, i, 0),
#                         m_fdata(self.inlet_data_model, i, 1)
#                     )
#                 )
#             else:
#                 pass
#         data_name = self.rating_table_cbo.currentText()
#         self.inletRT.set_rating_table_data(rt_fid, data_name, rt_data)
# 
    def create_plot(self):
        self.plot.clear()
        self.plot_item_name = 'Rating Tables'
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
# 
    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
#         
    def update_rating_tables_in_storm_drain_widget(self):
        pass
        
        
        
        
        
        
        