# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from _ast import Or
from datetime import datetime
from math import isnan

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import NULL, QDate, QDateTime, QRegExp, QSettings, Qt, QTime
from qgis.PyQt.QtGui import QColor, QDoubleValidator, QRegExpValidator
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QStyledItemDelegate,
    QTableWidgetItem,
    QMessageBox
)

from ..flo2dobjects import InletRatingTable
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication, ScrollMessageBox, ScrollMessageBox2
from ..utils import (
    NumericDelegate,
    TimeSeriesDelegate,
    float_or_zero,
    int_or_zero,
    is_number,
    is_true,
    m_fdata,
)
from .table_editor_widget import CommandItemEdit, StandardItem, StandardItemModel
from .ui_utils import center_canvas, load_ui, set_icon, zoom
# from Cython.Includes.libcpp import functional
from fontTools.cu2qu.cu2qu import curve_to_quadratic

from .dlg_outfalls import StorageUnitTabularCurveDialog

uiDialog, qtBaseClass = load_ui("storage_units")
class StorageUnitsDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "")
        self.con = None
        self.gutils = None

        self.storages_buttonBox.button(QDialogButtonBox.Save).setText(
            "Save storage units to 'Storm Drain Storage Units' User Layer"
        )
        set_icon(self.find_storage_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.external_inflow_btn, "open_dialog.svg")
        set_icon(self.zoom_in_storage_btn, "zoom_in.svg")
        set_icon(self.zoom_out_storage_btn, "zoom_out.svg")
        set_icon(self.open_tabular_curve_btn, "open_dialog.svg")

        self.save_this_storage_btn.setVisible(False)
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.storage_data_model = StandardItemModel()
        self.block = False

        self.setup_connection()

        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.grid_count = self.gutils.count("grid", field="fid")

        self.storages_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_storage_in_table)
        self.find_storage_cell_btn.clicked.connect(self.find_storage)
        self.zoom_in_storage_btn.clicked.connect(self.zoom_in_storage_cell)
        self.zoom_out_storage_btn.clicked.connect(self.zoom_out_storage_cell)
    
        self.storages_buttonBox.accepted.connect(self.save_storages)
        # self.save_this_storage_btn.clicked.connect(self.save_inlets)

        # Connections from individual controls to particular cell in storages_tblw table widget:
        
        self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        self.max_depth_dbox.valueChanged.connect(self.max_depth_dbox_valueChanged)
        self.initial_depth_dbox.valueChanged.connect(self.initial_depth_dbox_valueChanged)
        self.external_inflow_chbox.stateChanged.connect(self.external_inflow_checked)
        self.external_inflow_btn.clicked.connect(self.show_external_inflow_dlg)
        self.ponded_area_dbox.valueChanged.connect(self.ponded_area_dbox_valueChanged)
        self.evap_factor_dbox.valueChanged.connect(self.evap_factor_dbox_valueChanged)
        self.infiltration_grp.toggled.connect(self.infiltration_grp_checked)
        self.suction_head_dbox.valueChanged.connect(self.suction_head_dbox_valueChanged)          
        self.conductivity_dbox.valueChanged.connect(self.conductivity_dbox_valueChanged)                
        self.initial_deficit_dbox.valueChanged.connect(self.initial_deficit_dbox_valueChanged) 
        self.functional_radio.toggled.connect(self.select_curve_type)
        self.tabular_radio.toggled.connect(self.select_curve_type)
        # self.functional_grp.toggled.connect(self.functional_grp_checked)
        # self.tabular_grp.toggled.connect(self.tabular_grp_checked)                 
        self.coefficient_dbox.valueChanged.connect(self.coefficient_dbox_valueChanged)                  
        self.exponent_dbox.valueChanged.connect(self.exponent_dbox_valueChanged)                
        self.constant_dbox.valueChanged.connect(self.constant_dbox_valueChanged)       
        self.tabular_curves_cbo.currentIndexChanged.connect(self.tabular_curves_cbo_currentIndexChanged) 
        self.open_tabular_curve_btn.clicked.connect(self.open_tabular_curve)        
        self.storages_tblw.cellClicked.connect(self.storages_tblw_cell_clicked)

        self.storages_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)
        self.set_header()

        self.warnings = ""
        self.populate_storages()    
               
    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            # self.inletRT = InletRatingTable(self.con, self.iface)
            # self.populate_rtables()
        
    def populate_storages(self):
        qry = """SELECT
                        name, 
                        grid, 
                        invert_elev,
                        max_depth,
                        init_depth,
                        external_inflow,
                        ponded_area,
                        evap_factor,
                        treatment,
                        infiltration,
                        infil_method,
                        suction_head,
                        conductivity,
                        initial_deficit,
                        storage_curve,
                        coefficient,
                        exponent,
                        constant,
                        curve_name           
                FROM user_swmm_storage_units ORDER BY name ASC;"""
                
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            QApplication.restoreOverrideCursor()
            self.uc.show_info(
                "WARNING 010224.0546: 'Storm Drain Storage Units' User Layer is empty!"
            )
            return

        self.block = True
        self.populate_tabular_curves()
        self.storages_tblw.setRowCount(0)
        for row_number, row_data in enumerate(rows):
            self.storages_tblw.insertRow(row_number)
            for cell, data in enumerate(row_data):
                data = self.validate_user_swmm_storage_units_cell(data,row_number, cell )
                item = QTableWidgetItem()
                if cell in [0, 1, 5, 8, 9, 10, 14, 18]:
                # if cell == 0 or cell == 1 or cell == 5 or cell == 8 or cell == 9  or cell == 10 or cell == 14 or cell == 18:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            
                # Fill the list of inlet names:
                if cell == 0:
                    self.storages_cbo.addItem(data)
            
                # Fill all text boxes with data of first feature of query (first cell in table user_swmm_storage_units):
                if row_number == 0:
                    if cell == 1:
                        self.grid_element_le.setText(str(data))
                    elif cell == 2:
                        self.invert_elevation_dbox.setValue(data if data is not None else 0)
                    elif cell == 3:
                        self.max_depth_dbox.setValue(data if data is not None else 0)
                    elif cell == 4:
                        self.initial_depth_dbox.setValue(data if data is not None else 0)
                    elif cell == 5:
                        self.external_inflow_chbox.setChecked(True if is_true(data) else False)
                    elif cell == 6:    
                        self.ponded_area_dbox.setValue(data if data is not None else 0)
                    elif cell == 7:
                        self.evap_factor_dbox.setValue(data if data is not None else 0) 
                    elif cell == 8:
                        self.treatment_cbo.setCurrentIndex(0)                                 
                    elif cell == 9:
                        self.infiltration_grp.setChecked(True)
                    elif cell == 10:
                        self.method_cbo.setCurrentIndex(0)
                    elif cell == 11:
                        self.suction_head_dbox.setValue(data if data is not None else 0)
                    elif cell == 12:
                        self.conductivity_dbox.setValue(data if data is not None else 0)
                    elif cell == 13:
                        self.initial_deficit_dbox.setValue(data if data is not None else 0)
                    elif cell == 14:
                        self.functional_radio.setChecked(True if data == "FUNCTIONAL" else False)
                        self.tabular_radio.setChecked(True if data == "TABULAR" else False)
                    elif cell == 15:
                        self.coefficient_dbox.setValue(data if data is not None else 0)
                    elif cell == 16:
                        self.exponent_dbox.setValue(data if data is not None else 0)
                    elif cell == 17:
                        self.constant_dbox.setValue(data if data is not None else 0)
                    elif cell == 18:
                        index = self.tabular_curves_cbo.findText(data)
                        if index == -1:
                            index = 0
                        self.tabular_curves_cbo.setCurrentIndex(index)                      
                                        
                item.setData(Qt.EditRole, data)
                self.storages_tblw.setItem(row_number, cell, item)

        QApplication.restoreOverrideCursor()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.storages_cbo.model().sort(Qt.AscendingOrder)
        self.storages_cbo.setCurrentIndex(0)

        self.storages_tblw.sortItems(0, Qt.AscendingOrder)
        self.storages_tblw.selectRow(0)
        self.storages_tblw.setStyleSheet("QTableWidget::item:selected { background-color: lightblue; color: black; }")
    
        self.enable_external_inflow()
 
        self.block = False
        
        if self.warnings != "":
            QApplication.restoreOverrideCursor()
            result = ScrollMessageBox2(QMessageBox.Warning,"Issues found!", "WARNING 070224.1902: wrong values found:\n" + self.warnings)      
            result.exec_()  

        # self.select_curve_type()  
        self.highlight_storage_cell(self.grid_element_le.text())
    
    def populate_tabular_curves(self):
        self.tabular_curves_cbo.clear()
        self.tabular_curves_cbo.addItem("*")
        curve = self.gutils.execute("SELECT DISTINCT name FROM swmm_other_curves WHERE type = 'Storage'")
        for c in curve:
            self.tabular_curves_cbo.addItem(c[0])
        
        
    def validate_user_swmm_storage_units_cell(self, data, row_number, cell):
        if cell == 14:
            if data not in ["FUNCTIONAL", "TABULAR"]:
                self.warnings += "\n'" + data + "' in (row, column) (" + str(row_number + 1) + ", " + str(cell +1 ) + "). Changed to 'FUNCTIONAL'\n"
                data = "FUNCTIONAL"
        return data
        
    def onVerticalSectionClicked(self, logicalIndex):
        self.storages_tblw_cell_clicked(logicalIndex, 0)

    def set_header(self):
        self.storages_tblw.setHorizontalHeaderLabels(
            [
                "Name",
                "Grid Element",
                "Invert. Elev",
                "Max. Depth",
                "Init. Depth" ,
                "External Inflow",
                "Ponded Area",
                "Evap. Factor",
                "Treatment",
                "Infiltration",
                "Infil. Method",
                "Suction Head",
                "Conductivity",
                "Initial Deficit",
                "Storage Curve",
                "Coefficient",
                "Exponent",
                "Constant",
                "Curve Name", 
            ]
        )

    def invert_connect(self):
        self.uc.show_info("Connection!")

    def invert_elevation_dbox_valueChanged(self):
        self.box_valueChanged(self.invert_elevation_dbox, 2)

    def max_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.max_depth_dbox, 3)

    def initial_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.initial_depth_dbox, 4)

    def external_inflow_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.external_inflow_chbox, 5)
        
    def ponded_area_dbox_valueChanged(self):
        self.box_valueChanged(self.ponded_area_dbox, 6)  
        
    def evap_factor_dbox_valueChanged(self):
        self.box_valueChanged(self.evap_factor_dbox, 7) 
 
    def infiltration_grp_checked(self):
        self.checkbox_valueChanged(self.infiltration_grp, 9)
        
    def suction_head_dbox_valueChanged(self):
        self.box_valueChanged(self.suction_head_dbox, 11) 
              
    def conductivity_dbox_valueChanged(self):
        self.box_valueChanged(self.conductivity_dbox, 12) 
                
    def initial_deficit_dbox_valueChanged(self):
        self.box_valueChanged(self.initial_deficit_dbox, 13) 

    def functional_radio_toggled(self):
        if self.functional_radio.isChecked():
            self.functional_grp.setEnabled(True)
            self.tabular_grp.setEnabled(False)
        else:
            self.functional_grp.setEnabled(False)
            self.tabular_grp.setEnabled(True)

    def tabular_radio_toggled(self):
        if self.tabular_radio.isChecked():
            self.tabular_grp.setEnabled(True)
            self.functional_grp.setEnabled(False)   
        else:
            self.tabular_grp.setEnabled(False)
            self.functional_grp.setEnabled(True)

    def select_curve_type(self):
        if not self.block:
            self.tabular_grp.setEnabled(self.tabular_radio.isChecked())
            self.functional_grp.setEnabled(self.functional_radio.isChecked()) 
    
            row = self.storages_cbo.currentIndex()
            item = QTableWidgetItem()
            item.setData(Qt.EditRole, "FUNCTIONAL" if self.functional_radio.isChecked() else "TABULAR")
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.storages_tblw.setItem(row, 14, item)           
  
    def coefficient_dbox_valueChanged(self):
        self.box_valueChanged(self.coefficient_dbox, 15) 
                   
    def exponent_dbox_valueChanged(self):
        self.box_valueChanged(self.exponent_dbox, 16) 
                  
    def constant_dbox_valueChanged(self):
        self.box_valueChanged(self.constant_dbox, 17) 
        
    def external_inflow_checked(self):
        self.checkbox_valueChanged(self.external_inflow_chbox, 5)
            
        if not self.block:
            # Is there an external inflow for this storage?
            inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
            node = self.storages_cbo.currentText()
            inflow = self.gutils.execute(inflow_sql, (node,)).fetchone()

            enabled = self.external_inflow_chbox.isChecked()
            self.external_inflow_btn.setEnabled(enabled)
            if enabled:
                if not inflow:
                    insert_sql = """INSERT INTO swmm_inflows 
                                    (   node_name, 
                                        constituent, 
                                        baseline, 
                                        pattern_name, 
                                        time_series_name, 
                                        scale_factor
                                    ) 
                                    VALUES (?, ?, ?, ?, ?, ?);"""
                    self.gutils.execute(insert_sql, (node, "FLOW", 0.0, "", "", 1.0))
            else:
                if inflow:
                    delete_sql = "DELETE FROM swmm_inflows WHERE node_name = ?"
                    self.gutils.execute(delete_sql, (node,))

    def enable_external_inflow(self):
        # Is there an external inflow for this storage?
        inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
        inflow = self.gutils.execute(inflow_sql, (self.storages_cbo.currentText(),)).fetchone()
        if inflow:
            self.external_inflow_chbox.setChecked(True)
            self.external_inflow_btn.setEnabled(True)
        else:
            self.external_inflow_chbox.setChecked(False)
            self.external_inflow_btn.setEnabled(False)

    def length_dbox_valueChanged(self):
        self.box_valueChanged(self.length_dbox, 8)

    def width_dbox_valueChanged(self):
        self.box_valueChanged(self.width_dbox, 9)

    def height_dbox_valueChanged(self):
        self.box_valueChanged(self.height_dbox, 10)

    def box_valueChanged(self, widget, col):
        row = self.storages_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        if col in [0, 1, 5, 8, 9, 10, 14, 18]:
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.storages_tblw.setItem(row, col, item)        
        
        
        # if not self.block:
        #     storage = self.storages_cbo.currentText()
        #     row = 0
        #     for i in range(1, self.storages_tblw.rowCount() - 1):
        #         name = self.storages_tblw.item(i, 0).text()
        #         if name == storage:
        #             row = i
        #             break
        #     item = QTableWidgetItem()
        #     item.setData(Qt.EditRole, widget.value())
        #     self.storages_tblw.setItem(row, col, item)

    def checkbox_valueChanged(self, widget, col):
        row = self.storages_cbo.currentIndex()
        item = QTableWidgetItem()
        if col in (0, 1):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.storages_tblw.setItem(row, col, item)
        self.storages_tblw.item(row, col).setText("True" if widget.isChecked() else "False")

    def tabular_curves_cbo_currentIndexChanged(self):
        row = self.storages_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, self.tabular_curves_cbo.currentText())
        self.storages_tblw.setItem(row, 18, item)

    def open_tabular_curve(self):
        tabular_curve_name = self.tabular_curves_cbo.currentText()
        dlg = StorageUnitTabularCurveDialog(self.iface, tabular_curve_name)
        while True:
            ok = dlg.exec_()
            if ok:
                if dlg.values_ok:
                    dlg.save_curve()
                    tabular_curve_name = dlg.get_curve_name()
                    if tabular_curve_name != "":
                        # Reload tabular curve list and select the one saved:
                        curves_sql = (
                            "SELECT DISTINCT name FROM swmm_other_curves WHERE type = 'Storage' GROUP BY name"
                        )
                        names = self.gutils.execute(curves_sql).fetchall()
                        if names:
                            self.tabular_curves_cbo.clear()
                            for name in names:
                                self.tabular_curves_cbo.addItem(name[0])
                            self.tabular_curves_cbo.addItem("*")

                            idx = self.tabular_curves_cbo.findText(tabular_curve_name)
                            self.tabular_curves_cbo.setCurrentIndex(idx)
                        break
                    else:
                        break
            else:
                break

    def storages_tblw_valueChanged(self, I, J):
        self.uc.show_info("TABLE CHANGED in " + str(I) + "  " + str(J))

    def storages_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.storages_cbo.blockSignals(True)
        self.block = True

        name = self.storages_tblw.item(row, 0).text().strip()
        idx = self.storages_cbo.findText(name)
        self.storages_cbo.setCurrentIndex(idx)

        self.grid_element_le.setText(self.storages_tblw.item(row, 1).text())
        self.invert_elevation_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 2)))
        self.max_depth_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 3)))
        self.initial_depth_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 4)))
        self.external_inflow_chbox.setChecked(True if self.storages_tblw.item(row, 5).text() == "True" else False)
        self.ponded_area_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 6)))
        self.evap_factor_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 7)))
        self.infiltration_grp.setChecked(True if self.storages_tblw.item(row, 9).text() == "True" else False)
        self.suction_head_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 11)))
        self.conductivity_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 12)))
        self.initial_deficit_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 13)))
        self.functional_radio.setChecked(True if self.storages_tblw.item(row, 14).text() == "FUNCTIONAL" else False)
        self.tabular_radio.setChecked(True if self.storages_tblw.item(row, 14).text() == "TABULAR" else False)
        self.coefficient_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 15)))
        self.exponent_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 16)))
        self.constant_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 17)))
        
        curve = self.storages_tblw.item(row, 18).text().strip()
        index = self.tabular_curves_cbo.findText(curve)
        if index == -1:
            index = 0
        self.tabular_curves_cbo.setCurrentIndex(index)

        self.enable_external_inflow()
        # self.select_curve_type()
        
        self.block = False
        self.storages_cbo.blockSignals(False)
        
        self.highlight_storage_cell(self.grid_element_le.text())

        # self.storages_tblw.setStyleSheet("QTableWidget::item:selected { background: rgb(135, 206, 255); }")
        QApplication.restoreOverrideCursor()

    def fill_individual_controls_with_current_storage_in_table(self):
        if not self.block:
            # Highlight row in table:
            row = self.storages_cbo.currentIndex()
            self.storages_tblw.selectRow(row)        
            
            rows = self.storages_tblw.rowCount()
            if rows <= 1:
                return
            
            storage = self.storages_cbo.currentText()
            found = False
            for row in range(0, rows):
                if self.storages_tblw.item(row, 0).text() == storage:
                    # We have found our value so we can update 'row' row
                    found = True
                    break
    
            if found:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self.storages_tblw.selectRow(row)
                self.storages_tblw.setStyleSheet("QTableWidget::item:selected { background-color: lightblue; color: black; }")
                # Load controls with selected row in table:
                item = QTableWidgetItem()
                item = self.storages_tblw.item(row, 1)
                if item is not None:
                    self.grid_element_le.setText(str(item.text()))
                self.invert_elevation_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 2)))
                self.max_depth_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 3)))
                self.initial_depth_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 4)))
                self.external_inflow_chbox.setChecked(True if self.storages_tblw.item(row, 5).text() == "True" else False)
                self.ponded_area_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 6)))
                self.evap_factor_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 7)))
                self.treatment_cbo.setCurrentIndex(0)
                self.infiltration_grp.setChecked(True if self.storages_tblw.item(row, 9).text() == "True" else False)
                self.method_cbo.setCurrentIndex(0)
                self.suction_head_dbox.setValue(int_or_zero(self.storages_tblw.item(row, 11)))
                self.conductivity_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 12)))
                self.initial_deficit_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 13)))
                self.functional_radio.setChecked(True if self.storages_tblw.item(row, 14).text() == "FUNCTIONAL" else False)
                # self.tabular_grp.setEnabled(True if self.storages_tblw.item(row, 14).text() == "True" else False)
                self.coefficient_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 16)))
                self.exponent_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 17)))
                self.constant_dbox.setValue(float_or_zero(self.storages_tblw.item(row, 18)))
                
                curve = self.storages_tblw.item(row, 18).text()
                index = self.tabular_curves_cbo.findText(curve)
                if index == -1:
                    index = 0
                self.tabular_curves_cbo.setCurrentIndex(index)            
                
                self.enable_external_inflow()
                # self.select_curve_type()
                
                self.highlight_storage_cell(self.grid_element_le.text())
                QApplication.restoreOverrideCursor()
            else:
                self.uc.bar_warn("Storage Unit not found not found!")

    def find_storage(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    storage = self.storage_to_find_le.text()
                    if storage != "":
                        indx = self.storages_cbo.findText(storage)
                        if indx != -1:
                            self.storages_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("Storage unit " + str(storage) + " not found.")
        except ValueError:
            self.uc.bar_warn("Storage unit " + str(storage) + " caused an error.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_storage_cell(self, cell):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.grid_lyr is not None:
                #                 if self.grid_lyr:
                if cell != "":
                    cell = int(cell)
                    if self.grid_count >= cell and cell > 0:
                        self.lyrs.show_feat_rubber(self.grid_lyr.id(), cell, QColor(Qt.yellow))
                        feat = next(self.grid_lyr.getFeatures(QgsFeatureRequest(cell)))
                        x, y = feat.geometry().centroid().asPoint()
                        self.lyrs.zoom_to_all()
                        center_canvas(self.iface, x, y)
                        zoom(self.iface, 0.45)

                    else:
                        self.uc.bar_warn("WARNING 221219.1140: Cell " + str(cell) + " not found.")
                        self.lyrs.clear_rubber()
                else:
                    self.uc.bar_warn("WARNING 221219.1139: Cell " + str(cell) + " not found.")
                    self.lyrs.clear_rubber()

            QApplication.restoreOverrideCursor()

        except ValueError:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 221219.1134: Cell " + str(cell) + "is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in_storage_cell(self):
        if self.grid_element_le.text() != "":
            currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_le.text()))))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            # self.update_extent()
            QApplication.restoreOverrideCursor()

    def zoom_out_storage_cell(self):
        if self.grid_element_le.text() != "":        
            currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_le.text()))))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            # self.update_extent()
            QApplication.restoreOverrideCursor()

    def save_storages(self):
        """
        Save changes of user_swmm_storage_units layer.
        """
        try:
            storages = []
            for row in range(0, self.storages_tblw.rowCount()):
                item = QTableWidgetItem()

                fid = row + 1

                item = self.storages_tblw.item(row, 0)
                if item is not None:
                    name = str(item.text()) if str(item.text()) != "" else " "

                item = self.storages_tblw.item(row, 1)
                if item is not None:
                    grid = str(item.text()) if str(item.text()) != "" else " "

                item = self.storages_tblw.item(row, 2)
                if item is not None:
                    invert_elev = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 3)
                if item is not None:
                    max_depth = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 4)
                if item is not None:
                    init_depth = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 5)
                if item is not None:
                    external_inflow = str(item.text()) if str(item.text()) in ["True", "False"]  else "False"
                    
                item = self.storages_tblw.item(row, 6)
                if item is not None:
                    ponded_area = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 7)
                if item is not None:
                    evap_fact = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 8)
                if item is not None:
                    treatment = str(item.text()) if str(item.text()) == "NO" else "NO"                   

                item = self.storages_tblw.item(row, 9)
                if item is not None:
                    infiltration = str(item.text()) if str(item.text()) in ["True", "False"]  else "False"

                item = self.storages_tblw.item(row, 10)
                if item is not None:
                    infil_method = str(item.text()) if str(item.text()) == "GREEN_AMPT" else "GREEN_AMPT"    

                item = self.storages_tblw.item(row, 11)
                if item is not None:
                    suction_head = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 12)
                if item is not None:
                    conductivity = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 13)
                if item is not None:
                    initial_deficit = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 14)
                if item is not None:
                    storage_curve = str(item.text()) if str(item.text()) in ["FUNCTIONAL", "TABULAR"] else "FUNCTIONAL"

                item = self.storages_tblw.item(row, 15)
                if item is not None:
                    coefficient = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 16)
                if item is not None:
                    exponent = str(item.text()) if str(item.text()) != "" else "0"

                item = self.storages_tblw.item(row, 17)
                if item is not None:
                    constant = str(item.text()) if str(item.text()) != "" else "0"
                    
                item = self.storages_tblw.item(row, 18)
                if item is not None:
                    curve_name = str(item.text()) if str(item.text()) != "" else "*"                    

                storages.append(
                    (
                        name,
                        grid,
                        invert_elev,
                        max_depth,
                        init_depth,
                        external_inflow,
                        treatment,
                        ponded_area,
                        evap_fact,
                        infiltration,
                        infil_method,
                        suction_head,
                        conductivity,
                        initial_deficit,
                        storage_curve,
                        coefficient,
                        exponent,
                        constant,
                        curve_name,
                        name,
                    )
                )

            # Update 'user_swmm_storage_units' table:
            update_qry = """
            UPDATE user_swmm_storage_units
            SET name= ?, 
                grid = ?, 
                invert_elev = ?,
                max_depth = ?, 
                init_depth = ?, 
                external_inflow = ?, 
                treatment = ?,
                ponded_area = ?, 
                evap_factor = ?, 
                infiltration = ?, 
                infil_method = ?, 
                suction_head = ?,
                conductivity = ?,
                initial_deficit = ?,
                storage_curve = ?,
                coefficient = ?,
                exponent = ?,
                constant = ?,
                curve_name = ?
            WHERE name = ?;"""

            self.gutils.execute_many(update_qry, storages)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 030224.1736: couldn't save storage units into User Layer 'Storm Drain Storage Units'!"
                + "\n__________________________________________________",
                e,
            )

    def show_external_inflow_dlg(self):
        dlg_external_inflow = ExternalInflowsDialog(self.iface, self.storages_cbo.currentText())
        dlg_external_inflow.setWindowTitle("Inlet/Junction " + self.storages_cbo.currentText())
        save = dlg_external_inflow.exec_()
        if save:
            inflow_sql = "SELECT baseline, pattern_name, time_series_name FROM swmm_inflows WHERE node_name = ?;"
            inflow = self.gutils.execute(inflow_sql, (self.storages_cbo.currentText(),)).fetchone()
            if inflow:
                baseline = inflow[0]
                pattern_name = inflow[1]
                time_series_name = inflow[2]
                if baseline == 0.0 and time_series_name == "":
                    self.external_inflow_chbox.setChecked(False)
                else:
                    self.external_inflow_chbox.setChecked(True)

            self.uc.bar_info("Storm Drain external inflow saved for storage unit " + self.storages_cbo.currentText())


uiDialog, qtBaseClass = load_ui("storm_drain_external_inflows")


class ExternalInflowsDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, node):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.node = node
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.swmm_select_pattern_btn.clicked.connect(self.select_inflow_pattern)
        self.swmm_select_time_series_btn.clicked.connect(self.select_time_series)
        self.external_inflows_buttonBox.accepted.connect(self.save_external_inflow_variables)
        self.swmm_inflow_baseline_le.setValidator(QDoubleValidator(0, 100, 2))

        self.setup_connection()
        self.populate_external_inflows()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_external_inflows(self):
        baseline_names_sql = "SELECT DISTINCT pattern_name FROM swmm_inflow_patterns GROUP BY pattern_name"
        names = self.gutils.execute(baseline_names_sql).fetchall()
        if names:
            for name in names:
                self.swmm_inflow_pattern_cbo.addItem(name[0].strip())
        self.swmm_inflow_pattern_cbo.addItem("")

        time_names_sql = "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
        names = self.gutils.execute(time_names_sql).fetchall()
        if names:
            for name in names:
                self.swmm_time_series_cbo.addItem(name[0].strip())
        self.swmm_time_series_cbo.addItem("")

        inflow_sql = "SELECT constituent, baseline, pattern_name, time_series_name, scale_factor FROM swmm_inflows WHERE node_name = ?;"
        inflow = self.gutils.execute(inflow_sql, (self.node,)).fetchone()
        if inflow:
            baseline = inflow[1]
            pattern_name = inflow[2]
            time_series_name = inflow[3]
            scale_factor = inflow[4]
            self.swmm_inflow_baseline_le.setText(str(baseline))
            if pattern_name != "" and pattern_name is not None:
                idx = self.swmm_inflow_pattern_cbo.findText(pattern_name.strip())
                if idx == -1:
                    self.uc.bar_warn(
                        '"' + pattern_name + '"' + " baseline pattern is not of HOURLY type!",
                        5,
                    )
                    self.swmm_inflow_pattern_cbo.setCurrentIndex(self.swmm_inflow_pattern_cbo.count() - 1)
                else:
                    self.swmm_inflow_pattern_cbo.setCurrentIndex(idx)
            else:
                self.swmm_inflow_pattern_cbo.setCurrentIndex(self.swmm_inflow_pattern_cbo.count() - 1)

            if time_series_name == '""':
                time_series_name = ""

            idx = self.swmm_time_series_cbo.findText(time_series_name)
            if idx == -1:
                time_series_name = ""
                idx = self.swmm_time_series_cbo.findText(time_series_name)
            self.swmm_time_series_cbo.setCurrentIndex(idx)

            self.swmm_inflow_scale_factor_dbox.setValue(scale_factor)

    def select_inflow_pattern(self):
        pattern_name = self.swmm_inflow_pattern_cbo.currentText()
        dlg_inflow_pattern = InflowPatternDialog(self.iface, pattern_name)
        save = dlg_inflow_pattern.exec_()

        pattern_name = dlg_inflow_pattern.get_name()
        if pattern_name != "":
            # Reload baseline list and select the one saved:

            baseline_names_sql = "SELECT DISTINCT pattern_name FROM swmm_inflow_patterns GROUP BY pattern_name"
            names = self.gutils.execute(baseline_names_sql).fetchall()
            if names:
                self.swmm_inflow_pattern_cbo.clear()
                for name in names:
                    self.swmm_inflow_pattern_cbo.addItem(name[0])
                self.swmm_inflow_pattern_cbo.addItem("")

                idx = self.swmm_inflow_pattern_cbo.findText(pattern_name)
                self.swmm_inflow_pattern_cbo.setCurrentIndex(idx)

    def select_time_series(self):
        time_series_name = self.swmm_time_series_cbo.currentText()
        dlg = InflowTimeSeriesDialog(self.iface, time_series_name)
        while True:
            save = dlg.exec_()
            if save:
                if dlg.values_ok:
                    dlg.save_time_series()
                    time_series_name = dlg.get_name()
                    if time_series_name != "":
                        # Reload time series list and select the one saved:
                        time_series_names_sql = (
                            "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
                        )
                        names = self.gutils.execute(time_series_names_sql).fetchall()
                        if names:
                            self.swmm_time_series_cbo.clear()
                            for name in names:
                                self.swmm_time_series_cbo.addItem(name[0])
                            self.swmm_time_series_cbo.addItem("")

                            idx = self.swmm_time_series_cbo.findText(time_series_name)
                            self.swmm_time_series_cbo.setCurrentIndex(idx)

                        # self.uc.bar_info("Storm Drain external time series saved for inlet " + "?????")
                        break
                    else:
                        break
            else:
                break

    def save_external_inflow_variables(self):
        """
        Save changes to external inflows variables.
        """

        baseline = float(self.swmm_inflow_baseline_le.text()) if self.swmm_inflow_baseline_le.text() != "" else 0.0
        pattern = self.swmm_inflow_pattern_cbo.currentText()
        file = self.swmm_time_series_cbo.currentText()
        scale = self.swmm_inflow_scale_factor_dbox.value()

        exists_sql = "SELECT fid FROM swmm_inflows WHERE node_name = ?;"
        exists = self.gutils.execute(exists_sql, (self.node,)).fetchone()
        if exists:
            update_sql = """UPDATE swmm_inflows
                        SET
                            constituent = ?,
                            baseline = ?, 
                            pattern_name = ?, 
                            time_series_name = ?,
                            scale_factor = ?
                        WHERE
                            node_name = ?;"""

            self.gutils.execute(update_sql, ("FLOW", baseline, pattern, file, scale, self.node))
        else:
            insert_sql = """INSERT INTO swmm_inflows 
                            (   node_name, 
                                constituent, 
                                baseline, 
                                pattern_name, 
                                time_series_name, 
                                scale_factor
                            ) 
                            VALUES (?,?,?,?,?,?); """
            self.gutils.execute(insert_sql, (self.node, "FLOW", baseline, pattern, file, scale))


uiDialog, qtBaseClass = load_ui("storm_drain_inflow_pattern")


class InflowPatternDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, pattern_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.pattern_name = pattern_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.setup_connection()

        self.pattern_buttonBox.accepted.connect(self.save_pattern)

        self.populate_pattern_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_pattern_dialog(self):
        if self.pattern_name == "":
            SIMUL = 24
            self.multipliers_tblw.setRowCount(SIMUL)
            for i in range(SIMUL):
                itm = QTableWidgetItem()
                itm.setData(Qt.EditRole, "1.0")
                self.multipliers_tblw.setItem(i, 0, itm)
        else:
            select_sql = "SELECT * FROM swmm_inflow_patterns WHERE pattern_name = ?"
            rows = self.gutils.execute(select_sql, (self.pattern_name,)).fetchall()
            if rows:
                for i, row in enumerate(rows):
                    self.name_le.setText(row[1])
                    self.description_le.setText(row[2])
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, row[4])
                    self.multipliers_tblw.setItem(i, 0, itm)
            else:
                self.name_le.setText(self.pattern_name)
                SIMUL = 24
                self.multipliers_tblw.setRowCount(SIMUL)
                for i in range(SIMUL):
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, "1.0")
                    self.multipliers_tblw.setItem(i, 0, itm)

    def save_pattern(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Pattern name required!", 2)
            self.pattern_name = ""
        elif self.description_le.text() == "":
            self.uc.bar_warn("Pattern description required!", 2)
            self.pattern_name = ""
        else:
            delete_sql = "DELETE FROM swmm_inflow_patterns WHERE pattern_name = ?"
            self.gutils.execute(delete_sql, (self.name_le.text(),))
            insert_sql = "INSERT INTO swmm_inflow_patterns (pattern_name, pattern_description, hour, multiplier) VALUES (?, ?, ? ,?);"
            for i in range(1, 25):
                self.gutils.execute(
                    insert_sql,
                    (
                        self.name_le.text(),
                        self.description_le.text(),
                        str(i),
                        self.multipliers_tblw.item(i - 1, 0).text(),
                    ),
                )

            self.uc.bar_info("Inflow Pattern " + self.name_le.text() + " saved.", 2)
            self.pattern_name = self.name_le.text()
            self.close()

    def get_name(self):
        return self.pattern_name


uiDialog, qtBaseClass = load_ui("storm_drain_inflow_time_series")


class InflowTimeSeriesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, time_series_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.time_series_name = time_series_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_time_data_btn, "add.svg")
        set_icon(self.delete_time_data_btn, "remove.svg")

        self.setup_connection()

        delegate = TimeSeriesDelegate(self.inflow_time_series_tblw)
        self.inflow_time_series_tblw.setItemDelegate(delegate)

        self.time_series_buttonBox.accepted.connect(self.is_ok_to_save)
        self.select_time_series_btn.clicked.connect(self.select_time_series_file)
        self.inflow_time_series_tblw.itemChanged.connect(self.ts_tblw_changed)
        self.add_time_data_btn.clicked.connect(self.add_time)
        self.delete_time_data_btn.clicked.connect(self.delete_time)

        self.populate_time_series_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_time_series_dialog(self):
        self.loading = True
        if self.time_series_name == "":
            self.use_table_radio.setChecked(True)
            pass
        else:
            series_sql = "SELECT * FROM swmm_time_series WHERE time_series_name = ?"
            row = self.gutils.execute(series_sql, (self.time_series_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])
                self.file_le.setText(row[3])
                external = True if is_true(row[4]) else False

                if external:
                    self.use_table_radio.setChecked(True)
                    self.external_radio.setChecked(False)
                else:
                    self.external_radio.setChecked(True)
                    self.use_table_radio.setChecked(False)

                data_qry = """SELECT
                                date, 
                                time, 
                                value
                        FROM swmm_time_series_data WHERE time_series_name = ?;"""
                rows = self.gutils.execute(data_qry, (self.time_series_name,)).fetchall()
                if rows:
                    self.inflow_time_series_tblw.setRowCount(0)
                    for row_number, row_data in enumerate(rows):
                        self.inflow_time_series_tblw.insertRow(row_number)
                        for col, data in enumerate(row_data):
                            if col == 0:
                                if data:
                                    try:
                                        a, b, c = data.split("/")
                                        if len(a) < 2:
                                            a = "0" * (2 - len(a)) + a
                                        if len(b) < 2:
                                            b = "0" * (2 - len(b)) + b
                                        if len(c) < 4:
                                            c = "0" * (4 - len(c)) + c
                                        data = a + "/" + b + "/" + c
                                    except:
                                        data = "00/00/0000"
                                else:
                                    data = "00/00/0000"
                            if col == 1:
                                if data:
                                    try:
                                        a, b = data.split(":")
                                        if len(a) == 1:
                                            a = "0" + a
                                        data = a + ":" + b
                                    except:
                                        data = "00:00"    
                                else:
                                    data = "00:00"
                            if col == 2:
                                data = str(data)
                            item = QTableWidgetItem()
                            item.setData(Qt.DisplayRole, data)
                            self.inflow_time_series_tblw.setItem(row_number, col, item)

                    self.inflow_time_series_tblw.sortItems(0, Qt.AscendingOrder)
            else:
                self.name_le.setText(self.time_series_name)
                self.external_radio.setChecked(True)
                self.use_table_radio.setChecked(False)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def select_time_series_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        time_series_file, __ = QFileDialog.getOpenFileName(None, "Select time series data file", directory=last_dir)
        if not time_series_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(time_series_file))
        self.file_le.setText(os.path.normpath(time_series_file))

        # For future use
        try:
            pass
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140220.0807: reading time series data file failed!", e)
            return

    def is_ok_to_save(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Time Series name required!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif " " in self.name_le.text():
            self.uc.bar_warn("Spaces not allowed in Time Series name!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif self.description_le.text() == "":
            self.uc.bar_warn("Time Series description required!", 2)
            self.values_ok = False

        elif self.use_table_radio.isChecked() and self.inflow_time_series_tblw.rowCount() == 0:
            self.uc.bar_warn("Time Series table can't be empty!", 2)
            self.values_ok = False

        elif self.external_radio.isChecked() and self.file_le.text() == "":
            self.uc.bar_warn("Data file name required!", 2)
            self.values_ok = False
        else:
            self.values_ok = True

    def save_time_series(self):
        delete_sql = "DELETE FROM swmm_time_series WHERE time_series_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_time_series (time_series_name, time_series_description, time_series_file, time_series_data) VALUES (?, ?, ?, ?);"
        self.gutils.execute(
            insert_sql,
            (
                self.name_le.text(),
                self.description_le.text(),
                self.file_le.text(),
                "True" if self.use_table_radio.isChecked() else "False",
            ),
        )

        delete_data_sql = "DELETE FROM swmm_time_series_data WHERE time_series_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_time_series_data (time_series_name, date, time, value) VALUES""",
            4,
        ]
        for row in range(0, self.inflow_time_series_tblw.rowCount()):
            date = self.inflow_time_series_tblw.item(row, 0)
            if date:
                date = date.text()

            time = self.inflow_time_series_tblw.item(row, 1)
            if time:
                time = time.text()

            value = self.inflow_time_series_tblw.item(row, 2)
            if value:
                value = value.text()

            insert_data_sql += [(self.name_le.text(), date, time, value)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Inflow time series " + self.name_le.text() + " saved.", 2)
        self.time_series_name = self.name_le.text()
        self.close()

    def get_name(self):
        return self.time_series_name

    def inflow_time_series_tblw_clicked(self):
        self.uc.show_info("Clicked")

    def time_series_model_changed(self, i, j):
        self.uc.show_info("Changed")

    def ts_tblw_changed(self, Qitem):
        if not self.loading:
            text = Qitem.text()
            if "/" in text:
                a, b, c = text.split("/")
                if len(a) < 2:
                    a = "0" * (2 - len(a)) + a
                if len(b) < 2:
                    b = "0" * (2 - len(b)) + b
                if len(c) < 4:
                    c = "0" * (4 - len(c)) + c
                text = a + "/" + b + "/" + c
            if ":" in text:
                a, b = text.split(":")
                if len(a) == 1:
                    a = "0" + a
                text = a + ":" + b
            Qitem.setText(text)

    def add_time(self):
        self.inflow_time_series_tblw.insertRow(self.inflow_time_series_tblw.rowCount())
        row_number = self.inflow_time_series_tblw.rowCount() - 1

        item = QTableWidgetItem()
        d = QDate.currentDate()
        d = str(d.month()) + "/" + str(d.day()) + "/" + str(d.year())
        item.setData(Qt.DisplayRole, d)
        self.inflow_time_series_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()
        t = QTime.currentTime()
        t = str(t.hour()) + ":" + str(t.minute())
        item.setData(Qt.DisplayRole, t)
        self.inflow_time_series_tblw.setItem(row_number, 1, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.inflow_time_series_tblw.setItem(row_number, 2, item)

        self.inflow_time_series_tblw.selectRow(row_number)
        self.inflow_time_series_tblw.setFocus()

    def delete_time(self):
        self.inflow_time_series_tblw.removeRow(self.inflow_time_series_tblw.currentRow())
        self.inflow_time_series_tblw.selectRow(0)
        self.inflow_time_series_tblw.setFocus()
