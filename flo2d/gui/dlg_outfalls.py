# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..utils import is_true, float_or_zero, int_or_zero, is_number
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QTableWidgetItem, QDialogButtonBox

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('outfalls')


class OutfallNodesDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.outfalls_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain Nodes-Outfalls' User Layer")
        self.outfall_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_outfall_in_table)
        self.outfalls_buttonBox.accepted.connect(self.save_outfalls)

        # Connections from individual controls to particular cell in outfalls_tblw table widget:
        #self.grid_element.valueChanged.connect(self.grid_element_valueChanged)
        self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        self.flap_gate_chbox.stateChanged.connect(self.flap_gate_chbox_stateChanged)
        self.allow_discharge_chbox.stateChanged.connect(self.allow_discharge_chbox_stateChanged)
        self.outfall_type_cbo.currentIndexChanged.connect(self.out_fall_type_cbo_currentIndexChanged)
        self.water_depth_dbox.valueChanged.connect(self.water_depth_dbox_valueChanged)
        self.tidal_curve_cbo.currentIndexChanged.connect(self.tidal_curve_cbo_currentIndexChanged)
        self.time_series_cbo.currentIndexChanged.connect(self.time_series_cbo_currentIndexChanged)

        self.outfalls_tuple = ('FIXED', 'FREE', 'NORMAL', 'TIDAL CURVE', 'TIME SERIES')
        # self.open_tidal_curve_btn.clicked.connect(self.open_tidal_curve)
        # self.open_time_series_btn.clicked.connect(self.open_time_series)
        #
        # self.set_header()
        self.setup_connection()
        self.populate_outfalls()

        self.outfalls_tblw.cellClicked.connect(self.outfalls_tblw_cell_clicked)
        self.outfalls_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)

    def set_header(self):
        self.outfalls_tblw.setHorizontalHeaderLabels(["Name",                #INP
                                                      "Node" ,               #FLO-2D
                                                      "Invert Elev.",        #INP
                                                      "Flap Gate",           #INP #FLO-2D
                                                      "Allow Discharge"      #FLO-2D                                                
                                                      "Outfall Type",        #INP
                                                      "Water Depth",         #
                                                      "Tidal Curve",         #IN P
                                                      "Time Series"])        #INP

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    # def invert_connect(self):
    #     self.uc.show_info('Connection!')
    #
    # def grid_element_valueChanged(self):
    #     self.box_valueChanged(self.grid_element, 1)

    def populate_outfalls(self):

        try:
            qry = '''SELECT fid,
                            name, 
                            grid, 
                            outfall_invert_elev,
                            flapgate, 
                            swmm_allow_discharge,
                            outfall_type, 
                            water_depth,
                            tidal_curve, 
                            time_series              
                    FROM user_swmm_nodes WHERE sd_type = 'O';'''

            rows = self.gutils.execute(qry).fetchall()  # rows is a list of tuples.
            self.outfalls_tblw.setRowCount(0)
            for row_number, row_data in enumerate(rows):       # In each iteration gets a tuple, for example:  0, ('fid'12, 'name''OUT3', 2581, 'False', 'False' 0,0,0, '', '')

                self.outfalls_tblw.insertRow(row_number)
                for col_number, data in enumerate(row_data):   # For each iteration gets, for example: first iteration:  0, 12. 2nd. iteration 1, 'OUT3', etc
                    if col_number == 6 and data not in self.outfalls_tuple:
                        data = "NORMAL"
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, data if data is not None else 0)  # item gets value of data (as QTableWidgetItem Class)

                    # Fill the list of outfall names:
                    if col_number == 1:   #We need 2nd. col_number: 'OUT3' in the example above, and its fid from row_data[0]
                        self.outfall_cbo.addItem(data, row_data[0])

                    # Fill all text boxes with data of first feature of query (first element in table user_swmm_nodes):
                    if row_number == 0:
                        data = 0 if data is None else data
                        if col_number == 2:
                            self.grid_element_txt.setText(str(data))
                        elif col_number == 3:
                            self.invert_elevation_dbox.setValue(data if data is not None else 0)
                        elif col_number == 4:
                            self.flap_gate_chbox.setChecked(True if is_true(data) else False)
                        elif col_number == 5:
                            self.allow_discharge_chbox.setChecked(True if is_true(data) else False)
                        elif col_number == 6:
                            data = str(data).upper()
                            if data in self.outfalls_tuple:
                                index = self.outfalls_tuple.index(data)
                            else:
                                index =  0
                            self.outfall_type_cbo.setCurrentIndex(index)
                            data = self.outfall_type_cbo.currentText()
                            if not data in ('FIXED', 'FREE', 'NORMAL', 'TIDAL CURVE', 'TIME SERIES'):
                               data = "NORMAL" 
                            item.setData(Qt.DisplayRole, data)
                        elif col_number == 7:
                            self.water_depth_dbox.setValue(data if data is not None else 0)
                        elif col_number == 8:
                            self.tidal_curve_cbo.setCurrentIndex(0)
                        elif col_number == 9:
                            self.time_series_cbo.setCurrentIndex(0)

                    if col_number > 0:    # For this row disable some elements and omit fid number
                        if col_number == 1 or col_number == 2 or col_number == 6 or col_number == 7 or col_number == 8 or col_number == 9:
                            item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled )
                        self.outfalls_tblw.setItem(row_number, col_number-1, item)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 100618.0846: error while loading outfalls components!", e)

    def onVerticalSectionClicked(self, logicalIndex):
        self.outfalls_tblw_cell_clicked(logicalIndex, 0)

    def invert_elevation_dbox_valueChanged(self):
        self.box_valueChanged(self.invert_elevation_dbox, 2)

    def flap_gate_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.flap_gate_chbox, 3)

    def allow_discharge_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.allow_discharge_chbox, 4)

    def out_fall_type_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.outfall_type_cbo, 5)

        self.water_depth_dbox.setEnabled(False)
        self.tidal_curve_cbo.setEnabled(False)
        self.time_series_cbo.setEnabled(False)
        self.open_tidal_curve_btn.setEnabled(False)
        self.open_time_series_btn.setEnabled(False)
        idx = self. outfall_type_cbo.currentIndex()
        if idx == 0:
            self.water_depth_dbox.setEnabled(True)
        elif idx == 3:
            self.tidal_curve_cbo.setEnabled(True)
            self.open_tidal_curve_btn.setEnabled(True)
        elif idx == 4:
            self.time_series_cbo.setEnabled(True)
            self.open_time_series_btn.setEnabled(True)

    def water_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.water_depth_dbox, 6)

    def tidal_curve_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.tidal_curve_cbo, 7)

    def time_series_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.time_series_cbo, 8)

    def open_tidal_curve(self):
        pass

    def open_time_series(self):
        pass

    def box_valueChanged(self, widget, col):
        row = self.outfall_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        self.outfalls_tblw.setItem(row, col, item)

    def checkbox_valueChanged(self, widget, col):
        row = self.outfall_cbo.currentIndex()
        item = QTableWidgetItem()
        self.outfalls_tblw.setItem(row, col, item)
        self.outfalls_tblw.item(row, col).setText( "True" if widget.isChecked() else "False")

    def combo_valueChanged(self, widget, col):
        row = self.outfall_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole,data)
        self.outfalls_tblw.setItem(row, col, item)

    def outfalls_tblw_cell_clicked(self, row, column):
        try:
            self.outfall_cbo.blockSignals(True)

            name = self.outfalls_tblw.item(row,0).text()
            idx = self.outfall_cbo.findText(name)
            self.outfall_cbo.setCurrentIndex(idx)            

            self.outfall_cbo.blockSignals(False)

            self.grid_element_txt.setText(self.outfalls_tblw.item(row, 1).text())
            self.invert_elevation_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 2)))
            self.flap_gate_chbox.setChecked(True if is_true(self.outfalls_tblw.item(row, 3).text()) else False) 
            self.allow_discharge_chbox.setChecked(True if is_true(self.outfalls_tblw.item(row, 4).text()) else False)
            # Set index of outfall_type_cbo (a combo) depending of text contents:
            item = self.outfalls_tblw.item(row, 5)
            if item is not None:
                itemTxt = item.text().upper().strip()
                itemTxt = "TIDAL CURVE" if itemTxt == "TIDAL" else "TIME SERIES" if itemTxt == "TIME" else itemTxt
                if itemTxt in self.outfalls_tuple:
                    index = self.outfall_type_cbo.findText(itemTxt)
                else:
                    itemTxt = "NORMAL"
                    index = self.outfall_type_cbo.findText(itemTxt)
#                     if itemTxt == "":
#                         index = 0
#                     else:
#                         if not itemTxt in ('FIXED', 'FREE', 'NORMAL', 'TIDAL CURVE', 'TIME SERIES'):
#                             itemTxt = "NORMAL" 
#                         index = map(int, itemTxt)
                index = 4 if index > 4 else 0 if index < 0 else index
                self.outfall_type_cbo.setCurrentIndex(index)
                item = QTableWidgetItem()
                item.setData(Qt.EditRole, self.outfall_type_cbo.currentText())
                self.outfalls_tblw.setItem(row, 5, item)

            self.water_depth_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 6)))

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 210618.1702: error assigning outfall values!", e)

    def fill_individual_controls_with_current_outfall_in_table(self):
        # Highlight row in table:
        row = self.outfall_cbo.currentIndex()
        self.outfalls_tblw.selectRow(row)

        # Load controls (text boxes, etc.) with selected row in table:
        item = QTableWidgetItem()

        item = self.outfalls_tblw.item(row, 1)
        if item is not None:
            self.grid_element_txt.setText(str(item.text()))

        self.invert_elevation_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 2)))

        item = self.outfalls_tblw.item(row, 3)
        if item is not None:
            self.flap_gate_chbox.setChecked(True if is_true(item.text()) else False)
                
#                                             True if item.text() == 'true' or item.text() == 'True' or item.text() == '1' 
#                                             or item.text() == 'Yes' or item.text() == 'yes' else False)

        item = self.outfalls_tblw.item(row, 4)
        if item is not None:
            self.allow_discharge_chbox.setChecked(True if is_true(item.text()) else False)
                
#                                             True if item.text() == 'true' or item.text() == 'True' or item.text() == '1' else False)

        item = self.outfalls_tblw.item(row, 5)
        if item is not None:
            itemTxt = item.text().upper()
            if itemTxt in self.outfalls_tuple:
                index = self.outfall_type_cbo.findText(itemTxt)
            else:
                if itemTxt == "":
                    index = 0
                else:
                    if is_number(itemTxt):
                        index = itemTxt
                    else:    
                        index = 0
            index = 4 if index > 4 else 0 if index < 0 else index
            self.outfall_type_cbo.setCurrentIndex(index)
            item = QTableWidgetItem()
            item.setData(Qt.EditRole, self.outfall_type_cbo.currentText() )
            self.outfalls_tblw.setItem(row, 5, item)

        self.water_depth_dbox.setValue(float_or_zero(self.outfalls_tblw.item(row, 6)))

    def save_outfalls(self):
        """
        Save changes of user_swmm_nodes layer.
        """
        # self.save_attrs()
        update_qry = '''
                        UPDATE user_swmm_nodes
                        SET
                            name = ?, 
                            grid = ?, 
                            outfall_invert_elev = ?,
                            flapgate = ?, 
                            swmm_allow_discharge = ?,
                            outfall_type = ?,
                            water_depth = ?,
                            tidal_curve = ?,
                            time_series = ?
                        WHERE fid = ?;'''

        for row in range(0, self.outfalls_tblw.rowCount()):
            item = QTableWidgetItem()

            fid = self.outfall_cbo.itemData(row)

            item = self.outfalls_tblw.item(row, 0)
            if item is not None:
                name = str(item.text())

            item = self.outfalls_tblw.item(row, 1)
            if item is not None:
                grid = str(item.text())

            item = self.outfalls_tblw.item(row, 2)
            if item is not None:
                invert_elev = str(item.text())

            item = self.outfalls_tblw.item(row, 3)
            if item is not None:
                flapgate= str(True if is_true(item.text()) else False)

            item = self.outfalls_tblw.item(row, 4)
            if item is not None:
                allow_discharge = str(True if is_true(item.text()) else False)

            item = self.outfalls_tblw.item(row, 5)
            if item is not None:
                outfall_type = str(item.text())
                if not outfall_type in ('FIXED', 'FREE', 'NORMAL', 'TIDAL CURVE', 'TIME SERIES'):
                    outfall_type = "NORMAL"                

            item = self.outfalls_tblw.item(row, 6)
            if item is not None:
                water_depth = str(item.text())

            item = self.outfalls_tblw.item(row, 7)
            # if item is not None:
            tidal_curve = str(item.text()) if item is not None else ""
            # tidal_curve = ""

            item = self.outfalls_tblw.item(row, 8)
            # if item is not None:
            time_series = str(item.text()) if item is not None else ""
            # time_series = ""

            self.gutils.execute(update_qry, (name,
                                             grid,
                                             invert_elev,
                                             flapgate,
                                             allow_discharge,
                                             outfall_type,
                                             water_depth,
                                             tidal_curve,
                                             time_series,
                                             fid
                                             ))
