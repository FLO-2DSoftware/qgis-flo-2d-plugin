# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from qgis.PyQt.QtCore import Qt, QSettings, NULL
from ..flo2dobjects import InletRatingTable
from qgis.PyQt.QtWidgets import QInputDialog, QTableWidgetItem, QDialogButtonBox, QApplication, QFileDialog
from qgis.PyQt.QtGui import QColor
from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import m_fdata, float_or_zero, int_or_zero, is_number
from .table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan

uiDialog, qtBaseClass = load_ui("mud_and_sediment")
class MudAndSedimentDialog(qtBaseClass, uiDialog):
    def __init__(self, con,  iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = None

        # self.inlets_buttonBox.button(QDialogButtonBox.Save).setText(
        #     "Save Inlet/Junctions to 'Storm Drain Nodes-Inlets/Junctions' User Layer"
        # )
        # self.save_this_inlet_btn.setVisible(False)
        # self.inletRT = None
        # self.plot = plot
        # self.table = table
        # self.tview = table.tview
        # self.inlet_data_model = StandardItemModel()
        # self.inlet_series_data = None
        # self.plot_item_name = None
        # self.d1, self.d2 = [[], []]
        # self.previous_type = -1
        # self.block = False
        # self.rt_previous_index = -999
        #
        # #         set_icon(self.change_name_btn, 'change_name.svg')
        # set_icon(self.external_inflow_btn, "external_inflow.svg")
        #
        # self.setup_connection()
        #
        # self.inlet_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_inlet_in_table)
        # self.inlets_buttonBox.accepted.connect(self.save_inlets)
        # self.save_this_inlet_btn.clicked.connect(self.save_inlets)
        #
        # # Connections from individual controls to particular cell in inlets_tblw table widget:
        # self.invert_elevation_dbox.valueChanged.connect(self.invert_elevation_dbox_valueChanged)
        # self.max_depth_dbox.valueChanged.connect(self.max_depth_dbox_valueChanged)
        # self.initial_depth_dbox.valueChanged.connect(self.initial_depth_dbox_valueChanged)
        # self.surcharge_depth_dbox.valueChanged.connect(self.surcharge_depth_dbox_valueChanged)
        # self.ponded_area_dbox.valueChanged.connect(self.ponded_area_dbox_valueChanged)
        # self.external_inflow_chbox.stateChanged.connect(self.external_inflow_checked)
        # self.external_inflow_btn.clicked.connect(self.show_external_inflow_dlg)
        # self.inlet_drain_type_cbo.currentIndexChanged.connect(self.inlet_drain_type_cbo_currentIndexChanged)
        # self.length_dbox.valueChanged.connect(self.length_dbox_valueChanged)
        # self.width_dbox.valueChanged.connect(self.width_dbox_valueChanged)
        # self.height_dbox.valueChanged.connect(self.height_dbox_valueChanged)
        # self.weir_coeff_dbox.valueChanged.connect(self.weir_coeff_dbox_valueChanged)
        # self.feature_sbox.valueChanged.connect(self.feature_sbox_valueChanged)
        # self.curb_height_dbox.valueChanged.connect(self.curb_height_dbox_valueChanged)
        # self.clogging_factor_dbox.valueChanged.connect(self.clogging_factor_dbox_valueChanged)
        # self.time_for_clogging_dbox.valueChanged.connect(self.time_for_clogging_dbox_valueChanged)
        # self.inlets_tblw.cellClicked.connect(self.inlets_tblw_cell_clicked)
        # self.inlet_rating_table_cbo.currentIndexChanged.connect(self.inlet_rating_table_cbo_changed)
        #
        # self.inlets_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)
        #
        # #         self.inlet_rating_table_cbo.setDuplicatesEnabled(False)
        #
        # self.set_header()
        #
        # self.populate_inlets()

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
                        rt_name          
                FROM user_swmm_nodes WHERE sd_type= 'I' or sd_type= 'J';"""
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            QApplication.restoreOverrideCursor()
            self.uc.show_info(
                "WARNING 280920.0421: No inlets/junctions defined (of type 'I' or 'J') in 'Storm Drain Nodes' User Layer!"
            )
            return

        self.block = True

        self.inlets_tblw.setRowCount(0)
        no_rt = ""
        existing_rts = []
        duplicates = []
        for row_number, row_data in enumerate(rows):
            self.inlets_tblw.insertRow(row_number)
            for cell, data in enumerate(row_data):
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
                        self.inlet_drain_type_cbo.setCurrentIndex(data - 1)
                        self.previous_type = data - 1
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
                    elif cell == 16:  # Rating table name.
                        idx = self.inlet_rating_table_cbo.findText(str(data) if data is not None else "")
                        self.inlet_rating_table_cbo.setCurrentIndex(idx)

                if cell == 1 or cell == 2:
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                # See if rating tables exist:
                if cell == 0:
                    inlet = data
                if cell == 16:
                    if data:  # data is the rating table name for cell 16.
                        data = data.strip()
                        if data != "":
                            fid = self.gutils.execute("SELECT fid FROM swmmflort WHERE name = ?", (data,)).fetchone()
                            if not fid:
                                no_rt += "'" + data + "'\t   for inlet   '" + inlet + "'\n"
                                data = ""
                            if data in existing_rts:
                                if data not in duplicates:
                                    duplicates.append(data)
                            else:
                                existing_rts.append(data)

                item.setData(Qt.DisplayRole, data)
                self.inlets_tblw.setItem(row_number, cell, item)

        if no_rt != "":
            self.uc.show_info(
                "WARNING 070120.1048:\nThe following rating tables were not found in table 'swmmflort' (Rating Tables):\n\n"
                + no_rt
            )

        if duplicates:
            txt = ""
            for d in duplicates:
                txt += "\n'" + d + "'"
            self.uc.show_info(
                "WARNING 080120.0814:\nThe following rating tables are assigned to more than one inlet:\n" + txt
            )

        self.inlet_cbo.model().sort(0)
        self.inlet_cbo.setCurrentIndex(0)

        self.inlets_tblw.sortItems(0, Qt.AscendingOrder)

        self.inlets_tblw.selectRow(0)

        self.rt_previous_index = self.inlet_rating_table_cbo.currentIndex()

        self.block = False

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
                "Ponded Area",  # INP
                "Inlet Drain Type",  # FLO-2D. SWMMFLO.DAT: INTYPE
                "Length/Perimeter *",  # FLO-2D. SWMMFLO.DAT: SWMMlenght
                "Width/Area *",  # FLO-2D. SWMMFLO.DAT: SWMMwidth
                "Height/Sag/Surch *",  # FLO-2D. SWMMFLO.DAT: SWMMheight
                "Weir Coeff *",  # FLO-2D. SWMMFLO.DAT: SWMMcoeff
                "Feature *",  # FLO-2D. SWMMFLO.DAT: FLAPGATE
                "Curb Height *",  # FLO-2D. SWMMFLO.DAT: CURBHEIGHT
                "Clogging Factor #",  # FLO-2D. SDCLOGGING.DAT
                "Time for Clogging #",  # FLO-2D. SDCLOGGING.DAT
                "Rating Table",
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

    def ponded_area_dbox_valueChanged(self):
        self.box_valueChanged(self.ponded_area_dbox, 6)

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

    def inlet_drain_type_cbo_currentIndexChanged(self):
        #         if not self.block:
        row = self.inlet_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, self.inlet_drain_type_cbo.currentIndex() + 1)
        self.inlets_tblw.setItem(row, 7, item)

        if self.inlet_drain_type_cbo.currentIndex() + 1 == 4:
            self.label_17.setEnabled(True)
            self.inlet_rating_table_cbo.setEnabled(True)
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
            self.inlet_rating_table_cbo.setEnabled(False)
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

    #             row = self.inlet_cbo.currentIndex()
    #             item = QTableWidgetItem()
    #             item.setData(Qt.EditRole, widget.value())
    #             self.inlets_tblw.setItem(row, col, item)

    def inlet_rating_table_cbo_changed(self):
        self.inlet_rating_table_cbo_currentIndexChanged(self.inlet_rating_table_cbo)

    def inlet_rating_table_cbo_currentIndexChanged(self, widget):

        if not self.block:
            # Check if rating table is already assigned:
            if self.inlet_rating_table_cbo.currentText() != "":
                grid = self.grid_element.text()
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

            #                 fid = self.gutils.execute("SELECT fid, grid_fid FROM swmmflort WHERE name = ?", (rt,)).fetchall()
            #                 if fid:
            #                     for f in fid:
            #                         grid_fid = f[1]
            #                         if grid_fid:
            #                             if grid != grid_fid:
            #                                 inlet = self.gutils.execute("SELECT name FROM user_swmm_nodes WHERE grid = ?;", (grid_fid,)).fetchone()
            #                                 if inlet:
            #                                     self.uc.show_info("Rating table  '" + rt + "'  already assigned to inlet  '" + inlet[0] +
            #                                                       "'  of grid element  '" + str(grid_fid) + "'")
            #                                     self.inlet_rating_table_cbo.setCurrentIndex(self.rt_previous_index)
            #                                     return

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

        self.inlet_cbo.blockSignals(True)
        name = self.inlets_tblw.item(row, 0).text()
        idx = self.inlet_cbo.findText(name)
        self.inlet_cbo.setCurrentIndex(idx)
        self.inlet_cbo.blockSignals(False)

        self.block = True

        self.grid_element.setText(self.inlets_tblw.item(row, 1).text())
        self.invert_elevation_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 2)))
        self.max_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 3)))
        self.initial_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 4)))
        self.surcharge_depth_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 5)))
        self.ponded_area_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 6)))

        val = self.inlets_tblw.item(row, 7).text()
        index = int(val if val != "" else 1) - 1
        index = 4 if index > 4 else 0 if index < 0 else index
        self.inlet_drain_type_cbo.setCurrentIndex(index)

        self.length_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 8)))
        self.width_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 9)))
        self.height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 10)))
        self.weir_coeff_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 11)))
        self.feature_sbox.setValue(float_or_zero(self.inlets_tblw.item(row, 12)))
        self.curb_height_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 13)))
        self.clogging_factor_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 14)))
        self.time_for_clogging_dbox.setValue(float_or_zero(self.inlets_tblw.item(row, 15)))

        rt_name = self.inlets_tblw.item(row, 16).text().strip()
        rt_name = rt_name if rt_name is not None else ""
        idx = self.inlet_rating_table_cbo.findText(rt_name)
        self.inlet_rating_table_cbo.setCurrentIndex(idx)

        # Is there an external inflow for this node?
        inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
        inflow = self.gutils.execute(inflow_sql, (self.inlet_cbo.currentText(),)).fetchone()
        if inflow:
            self.external_inflow_chbox.setChecked(True)
            self.external_inflow_btn.setEnabled(True)
        else:
            self.external_inflow_chbox.setChecked(False)
            self.external_inflow_btn.setEnabled(False)

        self.block = False

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
            row = i
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
            item = self.inlets_tblw.item(row, 7)  # Inlet type
            if item is not None:
                inlet_type_index = int(item.text() if item.text() != "" else 1)
                inlet_type_index = 4 if inlet_type_index > 4 else 0 if inlet_type_index < 0 else inlet_type_index - 1
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
                rt_name = rt_name.text() if rt_name.text() is not None else ""
                idx = self.inlet_rating_table_cbo.findText(rt_name)
                self.inlet_rating_table_cbo.setCurrentIndex(idx)
            else:
                self.inlet_rating_table_cbo.setCurrentIndex(-1)

            # Is there an external inflow for this node?
            inflow_sql = "SELECT * FROM swmm_inflows WHERE node_name = ?;"
            inflow = self.gutils.execute(inflow_sql, (self.inlet_cbo.currentText(),)).fetchone()
            if inflow:
                self.external_inflow_chbox.setChecked(True)
                self.external_inflow_btn.setEnabled(True)
            else:
                self.external_inflow_chbox.setChecked(False)
                self.external_inflow_btn.setEnabled(False)

        else:
            self.uc.bar_warn("Inlet/Junction not found!")

    def save_inlets(self):
        """
        Save changes of user_swmm_nodes layer.
        """
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
                    ponded_area = str(item.text()) if str(item.text()) != "" else "0"

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

                #                     if intype == '4': # Rating table.
                #                         rt_name = str(item.text())
                #                         idx = self.inlet_rating_table_cbo.findText(rt_name)
                #                         if idx == -1:
                #                             rt_name = ''
                #                     else:
                #                         rt_name = ''
                #                 else:
                #                     rt_name = ''

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
                            "SELECT fid FROM swmmflort_data WHERE swmm_rt_fid = ?", (swmmflort_fid[0],)
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
                                "SELECT fid FROM swmmflort_data WHERE swmm_rt_fid = ?", (swmmflort_fid[0],)
                            ).fetchone()
                            if data:
                                self.gutils.execute("UPDATE swmmflort SET grid_fid = ? WHERE name = ?", (grid, rt_name))
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
                            self.gutils.execute("UPDATE swmmflort SET grid_fid = ? WHERE fid = ?", (None, r[0]))
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
                        name,
                    )
                )

            # Update 'user_swmm_nodes' table:
            update_qry = """
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
                rt_fid = ?,
                rt_name = ?
            WHERE name = ?;"""

            self.gutils.execute_many(update_qry, inlets)

            if len(t4_but_rt_name) > 0:
                QApplication.restoreOverrideCursor()
                t4_but_rt_name.sort()
                no_rt_names = ""
                for inl, gr in t4_but_rt_name:
                    no_rt_names += "\n" + inl + "\t(grid " + gr + ")"
                self.uc.show_info(
                    "WARNING 020219.1836:\n\nThe following "
                    + str(len(t4_but_rt_name))
                    + " inlet(s) are of type 4 (stage discharge with rating table) but don't have rating table assigned:\n"
                    + no_rt_names
                )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 020219.0812: couldn't save inlets/junction into User Storm Drain Nodes!"
                + "\n__________________________________________________",
                e,
            )

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

    def populate_rtables_data(self):
        idx = self.inlet_rating_table_cbo.currentIndex()
        rt_fid = self.inlet_rating_table_cbo.itemData(idx)
        rt_name = self.inlet_rating_table_cbo.currentText()
        if rt_fid is None:
            #             self.uc.bar_warn("No rating table defined!")
            self.plot.clear()
            self.tview.undoStack.clear()
            self.tview.setModel(self.inlet_data_model)
            self.inlet_data_model.clear()
            return

        self.inlet_series_data = self.inletRT.get_rating_tables_data(rt_fid)
        if not self.inlet_series_data:
            return
        self.create_plot(rt_name)
        self.tview.undoStack.clear()
        self.tview.setModel(self.inlet_data_model)
        self.inlet_data_model.clear()
        self.inlet_data_model.setHorizontalHeaderLabels(["Depth", "Q"])
        self.d1, self.d2 = [[], []]
        for row in self.inlet_series_data:
            items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
            self.inlet_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.inlet_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ("",) * 2]
                self.inlet_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.inlet_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.update_plot()

    #     def create_plot(self):
    #         self.plot.clear()
    #         if self.plot.plot.legend is not None:
    #             self.plot.plot.legend.scene().removeItem(self.plot.plot.legend)
    #         self.plot.plot.addLegend()
    #
    #         self.plot_item_name = 'Rating Tables'
    #         self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def create_plot(self, name):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            self.plot.plot.legend.scene().removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()
        self.plot_item_name = "Rating Table:   " + name
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))
        self.plot.plot.setTitle("Rating Table   " + name)

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
            self.uc.bar_info("Storm Drain external inflow saved for inlet " + self.inlet_cbo.currentText())

