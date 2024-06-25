# -*- coding: utf-8 -*-
import csv
import io
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from _ast import Or
from datetime import datetime
from math import isnan

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QUndoStack
from qgis.PyQt import QtCore
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
)

from ..flo2dobjects import InletRatingTable
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
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
from .ui_utils import center_canvas, load_ui, set_icon, zoom, center_feature

uiDialog, qtBaseClass = load_ui("inlets")


class InletNodesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "")
        self.con = None
        self.gutils = None

        self.inlets_buttonBox.button(QDialogButtonBox.Save).setText(
            "Save Inlet/Junctions to 'Storm Drain Inlets/Junctions-Inlets/Junctions' User Layer"
        )
        set_icon(self.find_inlet_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.external_inflow_btn, "open_dialog.svg")
        set_icon(self.zoom_in_inlet_btn, "zoom_in.svg")
        set_icon(self.zoom_out_inlet_btn, "zoom_out.svg")

        self.inlets_tblw.horizontalHeader().hideSection(6)
        
        self.save_this_inlet_btn.setVisible(False)
        self.inletRT = None
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.inlet_data_model = StandardItemModel()
        self.inlet_series_data = None
        self.plot_item_name = None
        self.d1, self.d2 = [[], []]
        self.block = False
        self.rt_previous_index = -999

        self.setup_connection()

        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.grid_count = self.gutils.count("grid", field="fid")

        self.inlet_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_inlet_in_table)
        self.find_inlet_cell_btn.clicked.connect(self.find_inlet)
        self.zoom_in_inlet_btn.clicked.connect(self.zoom_in_inlet_cell)
        self.zoom_out_inlet_btn.clicked.connect(self.zoom_out_inlet_cell)

        self.inlets_buttonBox.accepted.connect(self.save_inlets)
        self.save_this_inlet_btn.clicked.connect(self.save_inlets)

        # Connections from individual controls to particular cell in inlets_tblw table widget:
        self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        self.max_depth_dbox.valueChanged.connect(self.max_depth_dbox_valueChanged)
        self.initial_depth_dbox.valueChanged.connect(self.initial_depth_dbox_valueChanged)
        self.surcharge_depth_dbox.valueChanged.connect(self.surcharge_depth_dbox_valueChanged)
        # self.ponded_area_dbox.valueChanged.connect(self.ponded_area_dbox_valueChanged)
        self.external_inflow_chbox.stateChanged.connect(self.external_inflow_checked)
        self.external_inflow_btn.clicked.connect(self.show_external_inflow_dlg)
        self.inlet_drain_type_cbo.currentIndexChanged.connect(self.inlet_drain_type_cbo_currentIndexChanged)
        self.length_dbox.valueChanged.connect(self.length_dbox_valueChanged)
        self.width_dbox.valueChanged.connect(self.width_dbox_valueChanged)
        self.height_dbox.valueChanged.connect(self.height_dbox_valueChanged)
        self.weir_coeff_dbox.valueChanged.connect(self.weir_coeff_dbox_valueChanged)
        self.feature_sbox.valueChanged.connect(self.feature_sbox_valueChanged)
        self.curb_height_dbox.valueChanged.connect(self.curb_height_dbox_valueChanged)
        self.clogging_factor_dbox.valueChanged.connect(self.clogging_factor_dbox_valueChanged)
        self.time_for_clogging_dbox.valueChanged.connect(self.time_for_clogging_dbox_valueChanged)
        self.dropbox_area_dbox.valueChanged.connect(self.dropbox_area_dbox_valueChanged)
        self.inlets_tblw.cellClicked.connect(self.inlets_tblw_cell_clicked)
        self.inlets_tblw.cellChanged.connect(self.inlets_tblw_cell_changed)
        self.inlet_rating_table_cbo.currentIndexChanged.connect(self.inlet_rating_table_cbo_changed)

        self.inlets_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)

        self.set_header()
        
        self.populate_inlets()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.inletRT = InletRatingTable(self.con, self.iface)
            self.populate_rtables()
        
    def populate_inlets(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            qry = """SELECT
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
                            external_inflow,
                            drboxarea         
                    FROM user_swmm_inlets_junctions;"""
            rows = self.gutils.execute(qry).fetchall()
            if not rows:
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_info(
                    "WARNING 280920.0421: No inlets/junctions defined in 'Storm Drain Inlets/Junctions' User Layer!"
                )
                QApplication.restoreOverrideCursor()
                return
    
            self.block = True
            self.inlets_tblw.blockSignals(self.block)

            self.inlets_tblw.setRowCount(0)
            no_rt = ""
            existing_rts = []
            duplicates = []
            wrong_type = ""
    
            for row_number, row_data in enumerate(rows):
                name = row_data[0].strip()
                typ = str(row_data[7]).strip()
    
                if name[0:2] in ["I1", "I2", "I3", "I4", "I5"]:
                    if name[1] != typ:
                        if len(wrong_type) < 1500:
                            wrong_type += name + "\tWrong type " + typ + ". Should be " + name[1] + ".\n"
                if name[0:2] == "IM":
                    if name[2] != typ:
                        if len(wrong_type) < 1500:
                            wrong_type += name + "\tWrong type " + typ + ". Should be " + name[2] + ".\n"
                self.inlets_tblw.insertRow(row_number)
                for cell, data in enumerate(row_data):
                    item = QTableWidgetItem()
                    if cell == 0 or cell == 1 or cell == 6 or cell == 7 or cell == 16:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    
                    # item.setData(Qt.DisplayRole, data)
                    # Fill the list of inlet names:
                    if cell == 0:
                        self.inlet_cbo.addItem(data)
    
                    # Fill all text boxes with data of first feature of query (first cell in table user_swmm_inlets_junctions):
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
                            self.surcharge_depth_dbox.setValue(data if data is not None else 0)
                        # elif cell == 6:
                        #     self.ponded_area_dbox.setValue(data if data is not None else 0)
                        elif cell == 7:
                            self.inlet_drain_type_cbo.setCurrentIndex(data - 1)
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
                        elif cell == 16:  # Rating table name/Culvert Eq.
                            idx = self.inlet_rating_table_cbo.findText(str(data) if data is not None else "")
                            self.inlet_rating_table_cbo.setCurrentIndex(idx)
                        elif cell == 17:
                            self.dropbox_area_dbox.setValue(data if data is not None else 0)                            
    
                    # See if rating tables or Culvert eq. exist:
                    if cell == 0:
                        inlet = data
                    if cell == 6:
                        data = 0.0  
                    if cell == 16:
                        if data:  # data is the rating table or Culvert eq. name for cell 16.
                            data = data.strip()
                            if data != "":
                                fid_rt = self.gutils.execute("SELECT fid FROM swmmflort WHERE name = ?", (data,)).fetchone()
                                if not fid_rt:
                                    fid_c = self.gutils.execute(
                                        "SELECT fid FROM swmmflo_culvert WHERE name = ?",
                                        (data,),
                                    ).fetchone()
                                    if not fid_c:
                                        no_rt += data + "\t   for inlet   " + inlet + "\n"
                                        # data = ""
                                    if data in existing_rts:
                                        if data not in duplicates:
                                            duplicates.append(data)
                                    else:
                                        existing_rts.append(data)
    
                                # if data in existing_rts:
                                #     if data not in duplicates:
                                #         duplicates.append(data)
                                # else:
                                #     existing_rts.append(data)
    
                    item.setData(Qt.EditRole, data)
                    self.inlets_tblw.setItem(row_number, cell, item)
    
            if no_rt != "":
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_info(
                    "WARNING 070120.1048:\nThe following rating tables/Culvert eq. were not found!:\n\n" + no_rt
                )
                QApplication.restoreOverrideCursor()
    
            if duplicates:
                txt = ""
                for d in duplicates:
                    txt += "\n" + d + ""
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                self.uc.show_info(
                    "WARNING 080120.0814:\nThe following rating tables/Culvert eq. are assigned to more than one inlet:\n"
                    + txt
                )
                QApplication.restoreOverrideCursor()
    
            self.inlet_cbo.model().sort(0)
            self.inlet_cbo.setCurrentIndex(0)
    
            self.inlets_tblw.sortItems(0, Qt.AscendingOrder)
            self.inlets_tblw.selectRow(0)
            self.rt_previous_index = self.inlet_rating_table_cbo.currentIndex()
    
            self.enable_external_inflow()
    
            self.block = False
            self.inlets_tblw.blockSignals(self.block)
    
            self.highlight_inlet_cell(self.grid_element_le.text())
    
        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error("ERROR 030324.0633: error while loading inlets/junctions components!", e)
            QApplication.restoreOverrideCursor()
        finally:
            QApplication.restoreOverrideCursor()              

    def onVerticalSectionClicked(self, logicalIndex):
        self.inlets_tblw_cell_clicked(logicalIndex, 0)

    def set_header(self):
        self.inlets_tblw.setHorizontalHeaderLabels(
            [
                "Name",  # INP  and FLO-2D. SWMMFLO.DAT: SWMM_JT
                "Grid Element",  # FLO-2D. SWMMFLO.DAT: SWMM_IDENT
                "Invert Elev.",  # INP
                "Max. Depth",  # INP
                "Init. Depth",  # INP
                "Surcharge Depth",  # INP
                "(Disabled)",  # INP (ponded area)
                "Inlet Drain Type",  # FLO-2D. SWMMFLO.DAT: INTYPE
                "Length/Perimeter",  # FLO-2D. SWMMFLO.DAT: SWMMlenght
                "Width/Area",  # FLO-2D. SWMMFLO.DAT: SWMMwidth
                "Height/Sag/Surch",  # FLO-2D. SWMMFLO.DAT: SWMMheight
                "Weir Coeff",  # FLO-2D. SWMMFLO.DAT: SWMMcoeff
                "Feature",  # FLO-2D. SWMMFLO.DAT: FLAPGATE
                "Curb Height",  # FLO-2D. SWMMFLO.DAT: CURBHEIGHT
                "Clogging Factor",  # FLO-2D. SDCLOGGING.DAT
                "Time for Clogging",  # FLO-2D. SDCLOGGING.DAT
                "Rat.Table/Culvert Eq.",
                "Dropbox Area",  # FLO-2D. SWMMFLODROPBOX.DAT
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

    def surcharge_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.surcharge_depth_dbox, 5)

    def external_inflow_checked(self):
        if not self.block:
            # Is there an external inflow for this node?
            inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
            node = self.inlet_cbo.currentText()
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
        # Is there an external inflow for this node?
        inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
        inflow = self.gutils.execute(inflow_sql, (self.inlet_cbo.currentText(),)).fetchone()
        if inflow:
            self.external_inflow_chbox.setChecked(True)
            self.external_inflow_btn.setEnabled(True)
        else:
            self.external_inflow_chbox.setChecked(False)
            self.external_inflow_btn.setEnabled(False)

    def inlet_drain_type_cbo_currentIndexChanged(self):
        row = self.inlet_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, self.inlet_drain_type_cbo.currentIndex() + 1)
        self.inlets_tblw.setItem(row, 7, item)

        if self.inlet_drain_type_cbo.currentIndex() + 1 in [4, 5]:
            self.label_17.setEnabled(True)
            # self.inlet_rating_table_cbo.setEnabled(True)
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
            # self.inlet_rating_table_cbo.setEnabled(False)
            self.inlet_rating_table_cbo.setCurrentIndex(-1)
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

    def dropbox_area_dbox_valueChanged(self):
        self.box_valueChanged(self.dropbox_area_dbox, 17)

    def box_valueChanged(self, widget, col):
        if not self.block:
            inlet = self.inlet_cbo.currentText()
            row = 0
            for i in range(1, self.inlets_tblw.rowCount() - 1):
                name = self.inlets_tblw.item(i, 0).text()
                if name == inlet:
                    row = i
                    break
            item = QTableWidgetItem()
            item.setData(Qt.EditRole, widget.value())
            self.inlets_tblw.setItem(row, col, item)

    def inlet_rating_table_cbo_changed(self):
        self.inlet_rating_table_cbo_currentIndexChanged(self.inlet_rating_table_cbo)

    def inlet_rating_table_cbo_currentIndexChanged(self, widget):
        if not self.block:
            # Check if rating table is already assigned:
            if self.inlet_rating_table_cbo.currentText() != "":
                grid = self.grid_element_le.text()
                inlet = self.inlet_cbo.currentText()
                rt = self.inlet_rating_table_cbo.currentText().strip()
                rti = self.inlet_rating_table_cbo.currentIndex()

                # See if rating table is already assigned in table:
                for row in range(0, self.inlets_tblw.rowCount()):
                    rating = self.inlets_tblw.item(row, 16)
                    if rating is not None and rating.text() != "":
                        if rating.text() == rt:
                            inlt = self.inlets_tblw.item(row, 0)
                            grd = self.inlets_tblw.item(row, 1)
                            self.uc.show_info(
                                "Rating table  '"
                                + rt
                                + "'  already assigned to inlet  '"
                                + inlt.text()
                                + "'  of grid element  '"
                                + grd.text()
                                + "'"
                            )
                            self.block = True
                            self.inlet_rating_table_cbo.setCurrentIndex(self.rt_previous_index)
                            self.block = False
                            return

            inlet = self.inlet_cbo.currentText()
            row = 0
            for i in range(1, self.inlets_tblw.rowCount() - 1):
                name = self.inlets_tblw.item(i, 0).text()
                if name == inlet:
                    row = i
                    break
            item = QTableWidgetItem()
            item.setData(Qt.EditRole, widget.currentText())
            self.inlets_tblw.setItem(row, 16, item)

        self.rt_previous_index = self.inlet_rating_table_cbo.currentIndex()

    def inlets_tblw_valueChanged(self, I, J):
        self.uc.show_info("TABLE CHANGED in " + str(I) + "  " + str(J))

    def inlets_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.inlet_cbo.blockSignals(True)
            name = self.inlets_tblw.item(row, 0).text().strip()
            idx = self.inlet_cbo.findText(name)
            self.inlet_cbo.setCurrentIndex(idx)
            self.inlet_cbo.blockSignals(False)

            self.block = True

            self.grid_element_le.setText(self.inlets_tblw.item(row, 1).text())
            self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 2)))
            self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 3)))
            self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 4)))
            self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 5)))
            # self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 6)))

            val = self.inlets_tblw.item(row, 7).text().strip()
            # Check that type and name are consistent:
            if (name[0:2] in ["I1", "I2", "I3", "I4", "I5"] and name[1] != val) or (name[0:3] == "IM5" and name[2] != val):
                self.uc.bar_warn("Inlet name " + name + " and type '" + val + "' do not correspond!")
            index = int(val) - 1 if val != "" else 0
            index = 5 if index == 4 else index
            if index > 5:
                self.uc.bar_warn("Inlet " + name + " has incorrect drain type!")
            # index = 5 if index > 5 else 0 if index < 0 else index

            self.inlet_drain_type_cbo.setCurrentIndex(index)

            self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 8)))
            self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 9)))
            self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 10)))
            self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 11)))
            self.feature_sbox.setValue(int_or_zero(self.inlets_tblw.item(row, 12)))
            self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 13)))
            self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 14)))
            self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 15)))
            self.dropbox_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 17)))

            rt_name = self.inlets_tblw.item(row, 16).text().strip()
            rt_name = rt_name if rt_name is not None else ""
            idx = self.inlet_rating_table_cbo.findText(rt_name)
            self.inlet_rating_table_cbo.setCurrentIndex(idx)

            self.enable_external_inflow()

            self.block = False

            self.highlight_inlet_cell(self.grid_element_le.text())

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error populating inlet values!", e)
        finally:
            QApplication.restoreOverrideCursor()

    def inlets_tblw_cell_changed(self, row, column):
        """
        Function to update the data on the dialog when anything is changed on the table
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.inlet_cbo.blockSignals(True)
            name = self.inlets_tblw.item(row, 0).text()
            self.inlet_cbo.setItemText(self.inlet_cbo.currentIndex(), name)
            self.inlet_cbo.setCurrentIndex(self.inlet_cbo.currentIndex())

            self.inlet_cbo.blockSignals(False)

            self.block = True

            self.grid_element_le.setText(self.inlets_tblw.item(row, 1).text())
            self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 2)))
            self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 3)))
            self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 4)))
            self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 5)))
            # self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 6)))

            val = self.inlets_tblw.item(row, 7).text().strip()
            # Check that type and name are consistent:
            if (name[0:2] in ["I1", "I2", "I3", "I4", "I5"] and name[1] != val) or (name[0:3] == "IM5" and name[2] != val):
                self.uc.bar_warn("Inlet name " + name + " and type '" + val + "' do not correspond!")
            index = int(val) - 1 if val != "" else 0
            index = 5 if index == 4 else index
            if index > 5:
                self.uc.bar_warn("Inlet " + name + " has incorrect drain type!")
            # index = 5 if index > 5 else 0 if index < 0 else index

            self.inlet_drain_type_cbo.setCurrentIndex(index)

            self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 8)))
            self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 9)))
            self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 10)))
            self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 11)))
            self.feature_sbox.setValue(int_or_zero(self.inlets_tblw.item(row, 12)))
            self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 13)))
            self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 14)))
            self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 15)))
            self.dropbox_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 17)))

            rt_name = self.inlets_tblw.item(row, 16).text().strip()
            rt_name = rt_name if rt_name is not None else ""
            idx = self.inlet_rating_table_cbo.findText(rt_name)
            self.inlet_rating_table_cbo.setCurrentIndex(idx)

            self.enable_external_inflow()

            self.block = False

            self.highlight_inlet_cell(self.grid_element_le.text())

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error populating inlet values!", e)
        finally:
            QApplication.restoreOverrideCursor()


    def fill_individual_controls_with_current_inlet_in_table(self):
        # Highlight row in table:
        row = self.inlet_cbo.currentIndex()

        rows = self.inlets_tblw.rowCount()
        if rows <= 1:
            return

        inlet = self.inlet_cbo.currentText()
        found = False
        for i in range(0, rows):
            if self.inlets_tblw.item(i, 0).text() == inlet:
                # We have found our value so we can update 'i' row
                found = True
                break

        if found:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            row = i
            self.inlets_tblw.selectRow(row)
            inlet_type_index = -1
            # Load controls with selected row in table:
            item = QTableWidgetItem()
            item = self.inlets_tblw.item(row, 1)
            if item is not None:
                self.grid_element_le.setText(str(item.text()))
            self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 2)))
            self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 3)))
            self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 4)))
            self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 5)))
            # self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 6)))
            item = self.inlets_tblw.item(row, 7)  # Inlet type
            if item is not None:
                inlet_type_index = int(item.text() if item.text() != "" else 1)
                inlet_type_index = 5 if inlet_type_index > 5 else 0 if inlet_type_index < 0 else inlet_type_index - 1
                self.inlet_drain_type_cbo.setCurrentIndex(inlet_type_index)
            self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 8)))
            self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 9)))
            self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 10)))
            self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 11)))
            self.feature_sbox.setValue(int_or_zero(self.inlets_tblw.item(row, 12)))
            self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 13)))
            self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 14)))
            self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 15)))
            self.dropbox_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 17)))

            if inlet_type_index == 3:
                rt_name = self.inlets_tblw.item(row, 16)
                rt_name = rt_name.text() if rt_name.text() is not None else ""
                idx = self.inlet_rating_table_cbo.findText(rt_name)
                self.inlet_rating_table_cbo.setCurrentIndex(idx)
            else:
                self.inlet_rating_table_cbo.setCurrentIndex(-1)

            self.enable_external_inflow()

            self.highlight_inlet_cell(self.grid_element_le.text())
            QApplication.restoreOverrideCursor()
        else:
            self.uc.bar_warn("Inlet/Junction not found!")

    def find_inlet(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    inlet = self.inlet_to_find_le.text()
                    if inlet != "":
                        indx = self.inlet_cbo.findText(inlet)
                        if indx != -1:
                            self.inlet_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("WARNING 071121.0746: inlet " + str(inlet) + " not found.")
                    else:
                        self.uc.bar_warn("WARNING  071121.0747: inlet " + str(inlet) + " not found.")
        except ValueError:
            self.uc.bar_warn("WARNING  071121.0748: inlet " + str(inlet) + " is not a levee cell.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_inlet_cell(self, cell):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.grid_lyr is not None:
                #                 if self.grid_lyr:
                if cell != "":
                    cell = int(cell)
                    if self.grid_count >= cell and cell > 0:
                        self.lyrs.show_feat_rubber(self.grid_lyr.id(), cell, QColor(Qt.yellow))
                        feat = next(self.grid_lyr.getFeatures(QgsFeatureRequest(cell)))
                        center_feature(self.iface, feat, 15)

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

    def zoom_in_inlet_cell(self):
        self.currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_le.text()))))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        x, y = self.currentCell.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, 0.4)
        # self.update_extent()
        QApplication.restoreOverrideCursor()

    def zoom_out_inlet_cell(self):
        self.currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(int(self.grid_element_le.text()))))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        x, y = self.currentCell.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, -0.4)
        # self.update_extent()
        QApplication.restoreOverrideCursor()

    def save_inlets(self):
        """
        Save changes of user_swmm_inlets_junctions layer.
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inlets = []
            t4_but_rt_name = []

            for row in range(0, self.inlets_tblw.rowCount()):
                item = QTableWidgetItem()

                fid = row + 1

                item = self.inlets_tblw.item(row, 0)
                if item is not None:
                    name = str(item.text()) if str(item.text()) != "" else " "

                item = self.inlets_tblw.item(row, 1)
                if item is not None:
                    grid = str(item.text()) if str(item.text()) != "" else " "

                item = self.inlets_tblw.item(row, 2)
                if item is not None:
                    invert_elev = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 3)
                if item is not None:
                    max_depth = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 4)
                if item is not None:
                    init_depth = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 5)
                if item is not None:
                    surcharge_depth = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 6)
                if item is not None:
                    # ponded_area = str(item.text()) if str(item.text()) != "" else "0"
                    ponded_area = "0"

                item = self.inlets_tblw.item(row, 7)
                if item is not None:
                    intype = str(item.text()) if str(item.text()) != "" else "1"

                item = self.inlets_tblw.item(row, 8)
                if item is not None:
                    swmm_length = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 9)
                if item is not None:
                    swmm_width = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 10)
                if item is not None:
                    swmm_height = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 11)
                if item is not None:
                    swmm_coeff = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 12)
                if item is not None:
                    swmm_feature = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 13)
                if item is not None:
                    curbheight = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 14)
                if item is not None:
                    swmm_clogging_factor = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 15)
                if item is not None:
                    swmm_time_for_clogging = str(item.text()) if str(item.text()) != "" else "0"

                item = self.inlets_tblw.item(row, 16)
                if item is not None:
                    rt_name = str(item.text())
                    
                item = self.inlets_tblw.item(row, 17)
                if item is not None:
                    drboxarea = str(item.text()) if str(item.text()) != "" else "0"                   

                # See if rating table exists in swmmflort:
                rt_fid = 0
                if intype == "4" and rt_name != "":
                    #  See if there is rating table data for this inlet (Type 4 and rating table name defined):
                    swmmflort_fid = self.gutils.execute(
                        "SELECT fid FROM swmmflort WHERE grid_fid = ? AND name = ?",
                        (
                            grid,
                            rt_name,
                        ),
                    ).fetchone()
                    if swmmflort_fid:
                        # See if data exists:
                        data = self.gutils.execute(
                            "SELECT fid FROM swmmflort_data WHERE swmm_rt_fid = ?",
                            (swmmflort_fid[0],),
                        ).fetchone()
                        if data:
                            # All Rating table data exists for this inlet.
                            rt_fid = swmmflort_fid[0]
                        else:
                            self.uc.show_info(
                                "WARNING 050121.0354:\n\nThere is no data (depth, q) for rating table  '"
                                + rt_name
                                + "'  for inlet  '"
                                + name
                                + "'"
                            )
                            self.gutils.execute(
                                "DELETE FROM swmmflort WHERE grid_fid = ? AND name = ?",
                                (
                                    grid,
                                    rt_name,
                                ),
                            )
                    else:
                        # Thre is no Rating Table associated with this RT name and grid. See if there is for the RT name (no matter the grid number):
                        swmmflort_fid = self.gutils.execute(
                            "SELECT fid FROM swmmflort WHERE name = ?", (rt_name,)
                        ).fetchone()
                        if swmmflort_fid:
                            data = self.gutils.execute(
                                "SELECT fid FROM swmmflort_data WHERE swmm_rt_fid = ?",
                                (swmmflort_fid[0],),
                            ).fetchone()
                            if data:
                                self.gutils.execute(
                                    "UPDATE swmmflort SET grid_fid = ? WHERE name = ?",
                                    (grid, rt_name),
                                )
                                rt_fid = swmmflort_fid[0]
                            else:
                                self.uc.show_info(
                                    "WARNING 050121.0354:\n\nThere is no data (depth, q) for rating table  '"
                                    + rt_name
                                    + "'  for inlet  '"
                                    + name
                                    + "'"
                                )
                                self.gutils.execute("DELETE FROM swmmflort WHERE name = ?", (rt_name,))

                elif intype == "4" and rt_name == "":
                    # Not rating table: make NULL all grid_fid fields in items of swmmflort
                    # that have this grid number:
                    rows = self.gutils.execute("SELECT fid FROM swmmflort WHERE grid_fid = ?", (grid,)).fetchall()
                    if rows:  # There may be at least one item in swmmflort for this grid, set grid to NULL:
                        for r in rows:
                            self.gutils.execute(
                                "UPDATE swmmflort SET grid_fid = ? WHERE fid = ?",
                                (None, r[0]),
                            )
                    t4_but_rt_name.append([name, grid])

                inlets.append(
                    (
                        name,
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
                        rt_fid,
                        rt_name,
                        drboxarea,
                        name,
                    )
                )

            # Update 'user_swmm_inlets_junctions' table:
            update_qry = """
            UPDATE user_swmm_inlets_junctions
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
                rt_fid = ?,
                rt_name = ?,
                drboxarea = ?
            WHERE name = ?;"""

            self.gutils.execute_many(update_qry, inlets)

            if len(t4_but_rt_name) > 0:
                t4_but_rt_name.sort()
                no_rt_names = ""
                for inl, gr in t4_but_rt_name:
                    no_rt_names += "\n" + inl + "\t(grid " + gr + ")"
                QApplication.setOverrideCursor(Qt.ArrowCursor)    
                self.uc.show_info(
                    "WARNING 020219.1836:\n\nThe following "
                    + str(len(t4_but_rt_name))
                    + " inlet(s) are of type 4 (stage discharge with rating table or Culvert equation) but don't have data assigned:\n"
                    + no_rt_names
                )
                QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error(
                "ERROR 020219.0812: couldn't save inlets/junction into User Storm Drain Inlets/Junctions!"
                + "\n__________________________________________________",
                e,
            )
            QApplication.restoreOverrideCursor()
        finally:
            QApplication.restoreOverrideCursor()           

    def populate_rtables(self):
        self.inlet_rating_table_cbo.clear()
        self.inlet_rating_table_cbo.addItem("")
        duplicates = ""
        for row in self.inletRT.get_rating_tables():
            rt_fid, name = [x if x is not None else "" for x in row]
            if name != "":
                if self.inlet_rating_table_cbo.findText(name) == -1:
                    self.inlet_rating_table_cbo.addItem(name, rt_fid)
                else:
                    duplicates += name + "\n"

    #         if duplicates:
    #             self.uc.show_warn("WARNING 301220.0451:\n\nThe following rating tables are duplicated\n\n" + duplicates)





    # def populate_rtables_data(self):
    #     idx = self.inlet_rating_table_cbo.currentIndex()
    #     rt_fid = self.inlet_rating_table_cbo.itemData(idx)
    #     rt_name = self.inlet_rating_table_cbo.currentText()
    #     if rt_fid is None:
    #         #             self.uc.bar_warn("No rating table defined!")
    #         self.plot.clear()
    #         self.tview.undoStack.clear()
    #         self.tview.setModel(self.inlet_data_model)
    #         self.inlet_data_model.clear()
    #         return
    #
    #     self.inlet_series_data = self.inletRT.get_inlet_table_data(rt_fid)
    #     if not self.inlet_series_data:
    #         return
    #     self.create_plot(rt_name)
    #     self.tview.undoStack.clear()
    #     self.tview.setModel(self.inlet_data_model)
    #     self.inlet_data_model.clear()
    #     self.inlet_data_model.setHorizontalHeaderLabels(["Depth", "Q"])
    #     self.d1, self.d2 = [[], []]
    #     for row in self.inlet_series_data:
    #         items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
    #         self.inlet_data_model.appendRow(items)
    #         self.d1.append(row[0] if not row[0] is None else float("NaN"))
    #         self.d2.append(row[1] if not row[1] is None else float("NaN"))
    #     rc = self.inlet_data_model.rowCount()
    #     if rc < 500:
    #         for row in range(rc, 500 + 1):
    #             items = [StandardItem(x) for x in ("",) * 2]
    #             self.inlet_data_model.appendRow(items)
    #     self.tview.horizontalHeader().setStretchLastSection(True)
    #     for col in range(2):
    #         self.tview.setColumnWidth(col, 100)
    #     for i in range(self.inlet_data_model.rowCount()):
    #         self.tview.setRowHeight(i, 20)
    #     self.update_plot()

    def create_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()
        self.plot_item_name = "Rating Table:   " + name
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
        self.plot.plot.setTitle("Rating Table:   " + name)

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def show_external_inflow_dlg(self):
        dlg_external_inflow = ExternalInflowsDialog(self.iface, self.inlet_cbo.currentText())
        dlg_external_inflow.setWindowTitle("Inlet/Junction " + self.inlet_cbo.currentText())
        save = dlg_external_inflow.exec_()
        if save:
            inflow_sql = "SELECT baseline, pattern_name, time_series_name FROM swmm_inflows WHERE node_name = ?;"
            inflow = self.gutils.execute(inflow_sql, (self.inlet_cbo.currentText(),)).fetchone()
            if inflow:
                baseline = inflow[0]
                pattern_name = inflow[1]
                time_series_name = inflow[2]
                if baseline == 0.0 and time_series_name == "":
                    self.external_inflow_chbox.setChecked(False)
                else:
                    self.external_inflow_chbox.setChecked(True)

            self.uc.bar_info("Storm Drain external inflow saved for inlet " + self.inlet_cbo.currentText())


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

        self.multipliers_tblw.undoStack = QUndoStack(self)

        self.setup_connection()

        self.pattern_buttonBox.accepted.connect(self.save_pattern)

        self.populate_pattern_dialog()

        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.delete_btn.clicked.connect(self.delete)

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
                if self.multipliers_tblw.item(i - 1, 0):
                    item = self.multipliers_tblw.item(i - 1, 0).text()
                else:
                    item = 1
                self.gutils.execute(
                    insert_sql,
                    (
                        self.name_le.text(),
                        self.description_le.text(),
                        str(i),
                        item,
                    ),
                )

            self.uc.bar_info("Inflow Pattern " + self.name_le.text() + " saved.", 2)
            self.pattern_name = self.name_le.text()
            self.close()

    def get_name(self):
        return self.pattern_name

    def copy_selection(self):
        selection = self.multipliers_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())

            stream = io.StringIO()
            csv.writer(stream, delimiter='\t').writerows(table)
            clipboard_text = stream.getvalue()
            clipboard_text = clipboard_text.replace("\t", "\n")  # To fix the tabulation issue
            QApplication.clipboard().setText(clipboard_text)

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.multipliers_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.multipliers_tblw.rowCount():
            self.multipliers_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.multipliers_tblw.columnCount():
            self.multipliers_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.multipliers_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def delete(self):
        selected_rows = []
        table_widget = self.multipliers_tblw

        # Get selected row indices
        for item in table_widget.selectedItems():
            if item.row() not in selected_rows:
                selected_rows.append(item.row())

        # Sort selected row indices in descending order to avoid issues with row removal
        selected_rows.sort(reverse=True)

        # Remove selected rows
        for row in selected_rows:
            table_widget.removeRow(row)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)

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
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.clear_btn.clicked.connect(self.clear)

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
            self.add_time()
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
                                        data = ""
                                else:
                                    data = ""
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
            column = Qitem.column()
            text = Qitem.text()

            if column == 0:  # First column (Date)
                if "/" in text:
                    a, b, c = text.split("/")
                    if len(a) < 2:
                        a = "0" * (2 - len(a)) + a
                    if len(b) < 2:
                        b = "0" * (2 - len(b)) + b
                    if len(c) < 4:
                        c = "0" * (4 - len(c)) + c
                    text = a + "/" + b + "/" + c

            elif column == 1:  # Second column (Time)
                if text == "":
                    text = "00:00"
                if ":" in text:
                    a, b = text.split(":")
                    if len(a) == 1:
                        a = "0" + a
                    text = a + ":" + b

            elif column == 2:  # Third column (value)
                if text == "":
                    text = "0.0"

            Qitem.setText(text)

    def add_time(self):
        self.inflow_time_series_tblw.insertRow(self.inflow_time_series_tblw.rowCount())
        row_number = self.inflow_time_series_tblw.rowCount() - 1

        item = QTableWidgetItem()

        # Code for current date
        # d = QDate.currentDate()
        # d = str(d.month()) + "/" + str(d.day()) + "/" + str(d.year())
        # item.setData(Qt.DisplayRole, d)

        # Code for empty item
        item.setData(Qt.DisplayRole, "")

        self.inflow_time_series_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()

        # Code for current time
        # t = QTime.currentTime()
        # t = str(t.hour()) + ":" + str(t.minute())
        # item.setData(Qt.DisplayRole, t)

        # Code for starting time equal 00:00
        t = "00:00"
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

    def copy_selection(self):
        selection = self.inflow_time_series_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())
            stream = io.StringIO()
            csv.writer(stream, delimiter="\t").writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.inflow_time_series_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.inflow_time_series_tblw.rowCount():
            self.inflow_time_series_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.inflow_time_series_tblw.columnCount():
            self.inflow_time_series_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.inflow_time_series_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def clear(self):
        self.inflow_time_series_tblw.setRowCount(0)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)

