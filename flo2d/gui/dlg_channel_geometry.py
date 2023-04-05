# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidgetItem

from ..flo2d_tools.grid_tools import highlight_selected_segment, highlight_selected_xsection_a
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("channel_geometry")


class ChannelGeometryDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.feat_selection = []

        self.setup_connection()
        self.populate_channels_dialog()

        self.grid_element_cbo.currentIndexChanged.connect(self.fill_grid_element_controls_with_current_grid_number)

        self.buttonBox.accepted.connect(self.close_dialog)

    def set_header(self):
        self.segment_elements_tblw.setHorizontalHeaderLabels(
            [
                "Element",
                "Shape",
                "Manning's n",
                "Length",
                "Left Bank Elev.",
                "Right Bank Elev.",
                "Left Slope",
                "Right Slope",
                "Average Width",
                "Thalweg Depth",
                "XS Number",
                "Right Bank",
                "1st area coeff",
                "1st area exp",
                "1st wetted coeff",
                "1st wetted exp",
                "1st top width coeff",
                "1st top width exp",
                "2nd depth",
                "2nd area coeff",
                "2nd area exp",
                "2nd wetted coeff",
                "2nd wetted exp",
                "2nd top width coeff",
                "2nd top width exp",
            ]
        )

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

        #  Connections of the channel segment controls to there DB tables:
        self.channel_segment_cbo.currentIndexChanged.connect(self.fill_whole_dialog_with_selected_segment_data)
        self.initial_flow_for_all_dbox.valueChanged.connect(self.update_initial_flow_for_all)
        self.max_froude_number_dbox.valueChanged.connect(self.update_froude)
        self.roughness_adjust_coeff_dbox.valueChanged.connect(self.roughness_adjust_coeff_dbox_valueChanged)
        self.transport_eq_cbo.currentIndexChanged.connect(self.update_transport_eq)
        self.initial_flow_elems_grp.toggled.connect(self.fill_starting_and_ending_water_elevations)
        self.first_elem_box.valueChanged.connect(self.update_first)
        self.starting_water_elev_dbox.valueChanged.connect(self.update_starting)
        self.last_elem_box.valueChanged.connect(self.update_last)
        self.ending_water_elev_dbox.valueChanged.connect(self.update_ending)

        # Connections of grid elements controls to update db tables where the control's values are stored, and
        # update table segment_elements_tblw table widget:
        self.grid_type_cbo.currentIndexChanged.connect(self.grid_type_cbo_valueChanged)
        self.manning_dbox.valueChanged.connect(self.manning_dbox_valueChanged)
        self.channel_length_dbox.valueChanged.connect(self.channel_length_dbox_valueChanged)
        self.left_bank_elevation_dbox.valueChanged.connect(self.left_bank_elevation_dbox_valueChanged)
        self.right_bank_elevation_dbox.valueChanged.connect(self.right_bank_elevation_dbox_valueChanged)
        self.left_side_slope_dbox.valueChanged.connect(self.left_side_slope_dbox_valueChanged)
        self.right_side_slope_dbox.valueChanged.connect(self.right_side_slope_dbox_valueChanged)
        self.average_channel_width_dbox.valueChanged.connect(self.average_channel_width_dbox_valueChanged)
        self.thalweg_channel_depth_dbox.valueChanged.connect(self.thalweg_channel_depth_dbox_valueChanged)
        self.first_area_coeff_dbox.valueChanged.connect(self.first_area_coeff_dbox_valueChanged)
        self.first_area_exp_dbox.valueChanged.connect(self.first_area_exp_dbox_valueChanged)
        self.first_wetted_coeff_dbox.valueChanged.connect(self.first_wetted_coeff_dbox_valueChanged)
        self.first_wetted_exp_dbox.valueChanged.connect(self.first_wetted_exp_dbox_valueChanged)
        self.first_top_width_coeff_dbox.valueChanged.connect(self.first_top_width_coeff_dbox_valueChanged)
        self.first_top_width_exp_dbox.valueChanged.connect(self.first_top_width_exp_dbox_valueChanged)
        self.second_depth_dbox.valueChanged.connect(self.second_depth_dbox_valueChanged)
        self.second_area_coeff_dbox.valueChanged.connect(self.second_area_coeff_dbox_valueChanged)
        self.second_area_exp_dbox.valueChanged.connect(self.second_area_exp_dbox_valueChanged)
        self.second_wetted_coeff_dbox.valueChanged.connect(self.second_wetted_coeff_dbox_valueChanged)
        self.second_wetted_exp_dbox.valueChanged.connect(self.second_wetted_exp_dbox_valueChanged)
        self.second_top_width_coeff_dbox.valueChanged.connect(self.second_top_width_coeff_dbox_valueChanged)
        self.second_top_width_exp_dbox.valueChanged.connect(self.second_top_width_exp_dbox_valueChanged)

        self.buttonBox.clicked.connect(self.close_dialog)

        self.set_header()

        self.segment_elements_tblw.cellClicked.connect(self.segment_elements_tblw_cell_clicked)

    def populate_channels_dialog(self):
        # Fill dropdown list of segments and load global data of 1rs channel segment.
        qry_chan = """SELECT fid, name, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;"""
        qry_chan_wsel = "SELECT seg_fid, istart, wselstart, iend, wselend FROM chan_wsel"

        rows_chan = self.gutils.execute(qry_chan).fetchall()
        if not rows_chan:
            return
        self.channel_segment_cbo.clear()
        for row in rows_chan:
            self.channel_segment_cbo.addItem(str(row[1]))

            if row[0] == 1:
                self.roughness_adjust_coeff_dbox.setValue(row[4])
                self.max_froude_number_dbox.setValue(row[3])
                equation = row[5] - 1 if row[5] is not None else 0
                self.transport_eq_cbo.setCurrentIndex(equation)

        rows_chan_wsel = self.gutils.execute(qry_chan_wsel).fetchall()
        if not rows_chan_wsel:
            return
        for row in rows_chan_wsel:
            if row[0] == 1:
                self.initial_flow_elems_grp.setChecked(True)
                self.first_elem_box.setValue(row[1])
                self.starting_water_elev_dbox.setValue(row[2])
                self.last_elem_box.setValue(row[3])
                self.ending_water_elev_dbox.setValue(row[4])
                break

        self.fill_whole_dialog_with_selected_segment_data()

    def fill_whole_dialog_with_selected_segment_data(self):
        self.fill_channel_segment_global_data()
        self.fill_table_with_cell_elements_of_current_segment()

        self.grid_element_cbo.blockSignals(True)
        self.fill_grid_elements_droplist_for_this_segment()
        self.grid_element_cbo.blockSignals(False)

        self.fill_grid_element_controls_with_current_grid_number()

    def fill_table_with_cell_elements_of_current_segment(self):
        qry_chan_elems = """SELECT fid, seg_fid, rbankgrid, fcn, xlen, type, fid  FROM chan_elems WHERE seg_fid = ?;"""
        qry_chan_r = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r"""
        qry_chan_v = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2, excdep,
                                         a11, a22, b11, b22, c11, c22  FROM chan_v;"""
        qry_chan_t = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t;"""
        qry_chan_n = """SELECT elem_fid, nxsecnum FROM chan_n;"""

        # self.clear_all_individual_items_for_current_cell_element()

        elem = self.grid_element_cbo.currentText()

        segment = self.channel_segment_cbo.currentIndex() + 1

        chan_elems = self.gutils.execute(qry_chan_elems, (segment,)).fetchall()

        if chan_elems is None:
            self.uc.bar_warn("There are no Schematized Channel Cross Sections!")
            return

        chan_r = self.gutils.execute(qry_chan_r).fetchall()
        chan_v = self.gutils.execute(qry_chan_v).fetchall()
        chan_t = self.gutils.execute(qry_chan_t).fetchall()
        chan_n = self.gutils.execute(qry_chan_n).fetchall()

        chan_r = [x if x is not None else 0 for x in chan_r[0:]]
        chan_v = [x if x is not None else 0 for x in chan_v[0:]]
        chan_t = [x if x is not None else 0 for x in chan_t[0:]]
        chan_n = [x if x is not None else 0 for x in chan_n[0:]]

        self.segment_elements_tblw.setRowCount(0)

        cell_pos = {}  # Dictionary to store position (row of table) of all cells of current segment.

        # Fill table with one row for each cell of current channel segment:
        for row, (fid, seg_fid, rbankgrid, fcn, xlen, type, fid) in enumerate(chan_elems):
            self.segment_elements_tblw.insertRow(row)

            cell_values = ((rbankgrid, 11), (fcn, 2), (xlen, 3), (type, 1), (fid, 0))
            self.assign_values_to_row(cell_values, row)

            # Build dictionary to indicate in which row is a cell:
            cell_pos[fid] = row  # Add pair (cell number, table row) to dictionary.

        for elem_fid, bankell, bankelr, fcw, fcd in chan_r:
            cell_values = ((bankell, 4), (bankelr, 5), (fcw, 8), (fcd, 9))
            row = cell_pos.get(elem_fid)
            if row is not None:
                self.assign_values_to_row(cell_values, row)

        for elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2, excdep, a11, a22, b11, b22, c11, c22 in chan_v:
            cell_values = (
                (bankell, 4),
                (bankelr, 5),
                (fcd, 9),
                (a1, 12),
                (a2, 13),
                (b1, 14),
                (b2, 15),
                (c1, 16),
                (c2, 17),
                (excdep, 18),
                (a11, 19),
                (a22, 20),
                (b11, 21),
                (b22, 22),
                (c11, 23),
                (c22, 24),
            )
            row = cell_pos.get(elem_fid)
            if row is not None:
                self.assign_values_to_row(cell_values, row)

        for elem_fid, bankell, bankelr, fcw, fcd, zl, zr in chan_t:
            cell_values = ((bankell, 4), (bankelr, 5), (fcw, 8), (fcd, 9), (zl, 6), (zr, 7))
            row = cell_pos.get(elem_fid)
            if row is not None:
                self.assign_values_to_row(cell_values, row)

        for elem_fid, nxsecnum in chan_n:
            cell_values = (
                (nxsecnum, 10),
            )  # NOTE: when there is  a tuple with only one tuple, a comma "," needs to be place after the tuple.
            row = cell_pos.get(elem_fid)
            if row is not None:
                self.assign_values_to_row(cell_values, row)

    def assign_value_to_cell(self, value, row, column):
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, value)
        self.segment_elements_tblw.setItem(row, column, item)

    def assign_values_to_row(self, values, row):
        for val in values:
            item = QTableWidgetItem()
            item.setData(Qt.DisplayRole, val[0])
            self.segment_elements_tblw.setItem(row, val[1], item)

    def fill_channel_segment_global_data(self):
        if self.gutils.is_table_empty("chan"):
            self.uc.bar_warn("Schematized Channel Segments (left bank) Layer is empty!.")
            return

        idx = self.channel_segment_cbo.currentIndex() + 1

        qry_wsel = """SELECT istart, wselstart, iend, wselend FROM chan_wsel WHERE seg_fid = ?;"""
        data_wsel = self.gutils.execute(qry_wsel, (idx,)).fetchone()
        if data_wsel is None:
            self.initial_flow_elems_grp.setChecked(False)
        else:
            # Set fields:
            self.first_elem_box.setValue(data_wsel[0])
            self.starting_water_elev_dbox.setValue(data_wsel[1]),
            self.last_elem_box.setValue(data_wsel[2]),
            self.ending_water_elev_dbox.setValue(data_wsel[3])
            self.initial_flow_elems_grp.setChecked(True)

        qry_chan = """SELECT isedn, depinitial, froudc, roughadj, isedn FROM chan WHERE fid = ?;"""
        data_chan = self.gutils.execute(qry_chan, (idx,)).fetchone()
        self.initial_flow_for_all_dbox.setValue(data_chan[1])
        self.max_froude_number_dbox.setValue(data_chan[2])
        self.roughness_adjust_coeff_dbox.setValue(data_chan[3])
        equation = data_chan[4] - 1 if data_chan[4] is not None else 0
        self.transport_eq_cbo.setCurrentIndex(equation)

    def fill_starting_and_ending_water_elevations(self):
        sql_in = """INSERT INTO chan_wsel (seg_fid, istart, wselstart, iend, wselend) VALUES (?,?,?,?,?);"""
        sql_out = """DELETE from chan_wsel WHERE seg_fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        if self.initial_flow_elems_grp.isChecked():
            self.initial_flow_for_all_dbox.setEnabled(False)
            self.gutils.execute(
                sql_in,
                (
                    idx,
                    self.first_elem_box.value(),
                    self.starting_water_elev_dbox.value(),
                    self.last_elem_box.value(),
                    self.ending_water_elev_dbox.value(),
                ),
            )
        else:
            self.initial_flow_for_all_dbox.setEnabled(True)
            self.gutils.execute(sql_out, (idx,))

    def fill_grid_elements_droplist_for_this_segment(self):
        self.grid_element_cbo.blockSignals(True)
        self.grid_element_cbo.clear()
        qry_elems = """SELECT fid FROM chan_elems WHERE seg_fid = ?;"""
        segment = self.channel_segment_cbo.currentIndex() + 1
        rows = self.gutils.execute(qry_elems, (segment,)).fetchall()
        for row in rows:
            self.grid_element_cbo.addItem(str(row[0]))
        self.grid_element_cbo.blockSignals(False)

    def fill_grid_element_controls_with_current_grid_number(self):
        # Highlight row in table:
        row = self.grid_element_cbo.currentIndex()
        self.segment_elements_tblw.selectRow(row)

        qry_chan_elems = """SELECT rbankgrid, fcn, xlen, type FROM chan_elems WHERE fid = ?;"""
        qry_chan_r = """SELECT bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
        qry_chan_v = """SELECT bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2, excdep,
                               a11, a22, b11, b22, c11, c22  FROM chan_v WHERE elem_fid = ?;"""
        qry_chan_t = """SELECT bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
        qry_chan_n = """SELECT nxsecnum, xsecname FROM chan_n WHERE elem_fid = ?;"""

        # self.clear_all_individual_items_for_current_cell_element()

        elem = self.grid_element_cbo.currentText()

        chan_elems = self.gutils.execute(qry_chan_elems, (elem,)).fetchone()
        chan_r = self.gutils.execute(qry_chan_r, (elem,)).fetchone()
        chan_v = self.gutils.execute(qry_chan_v, (elem,)).fetchone()
        chan_t = self.gutils.execute(qry_chan_t, (elem,)).fetchone()
        chan_n = self.gutils.execute(qry_chan_n, (elem,)).fetchone()

        if chan_elems is None:
            self.uc.bar_warn("There are no Schematized Channel Cross Sections!")
            return

        # Common fields for all types:
        self.right_bank_cell_lbl.setText(str(chan_elems[0]))
        self.manning_dbox.setValue(chan_elems[1])
        self.channel_length_dbox.setValue(chan_elems[2])
        type = chan_elems[3]
        self.grid_type_cbo.setCurrentIndex(0 if type == "R" else 1 if type == "V" else 2 if type == "T" else 3)

        self.enable_or_disable_items_according_to_type(type)

        if type == "R":
            if chan_r is not None:
                chan_r = [x if x is not None else 0 for x in chan_r[0:]]
                self.left_bank_elevation_dbox.setValue(chan_r[0])
                self.right_bank_elevation_dbox.setValue(chan_r[1])
                self.average_channel_width_dbox.setValue(chan_r[2])
                self.thalweg_channel_depth_dbox.setValue(chan_r[3])
            else:
                self.uc.show_warn(
                    "WARNING 060319.1641: Element " + elem + " has a cross section of type 'R' without data!"
                )

        elif type == "V":
            if chan_v is not None:
                chan_v = [x if x is not None else 0 for x in chan_v[0:]]
                self.left_bank_elevation_dbox.setValue(chan_v[0])
                self.right_bank_elevation_dbox.setValue(chan_v[1])
                self.thalweg_channel_depth_dbox.setValue(chan_v[2])
                self.first_area_coeff_dbox.setValue(chan_v[3])
                self.first_area_exp_dbox.setValue(chan_v[4])
                self.first_wetted_coeff_dbox.setValue(chan_v[5])
                self.first_wetted_exp_dbox.setValue(chan_v[6])
                self.first_top_width_coeff_dbox.setValue(chan_v[7])
                self.first_top_width_exp_dbox.setValue(chan_v[8])
                self.second_depth_dbox.setValue(chan_v[9])
                self.second_area_coeff_dbox.setValue(chan_v[10])
                self.second_area_exp_dbox.setValue(chan_v[11])
                self.second_wetted_coeff_dbox.setValue(chan_v[12])
                self.second_wetted_exp_dbox.setValue(chan_v[13])
                self.second_top_width_coeff_dbox.setValue(chan_v[14])
                self.second_top_width_exp_dbox.setValue(chan_v[15])
            else:
                self.uc.show_warn(
                    "WARNING 060319.1624: Element " + elem + " has a cross section of type 'V' without data!"
                )

        elif type == "T":
            if chan_t is not None:
                chan_t = [x if x is not None else 0 for x in chan_t[0:]]
                self.left_bank_elevation_dbox.setValue(chan_t[0])
                self.right_bank_elevation_dbox.setValue(chan_t[1])
                self.average_channel_width_dbox.setValue(chan_t[2])
                self.thalweg_channel_depth_dbox.setValue(chan_t[3])
                self.left_side_slope_dbox.setValue(chan_t[4])
                self.right_side_slope_dbox.setValue(chan_t[5])
            else:
                self.uc.show_warn(
                    "WARNING 060319.1625: Element " + elem + " has a cross section of type 'T' without data!"
                )

        elif type == "N":
            if chan_n is not None:
                chan_n = [x if x is not None else 0 for x in chan_n[0:]]
                self.cross_section_number_lbl.setText(str(chan_n[0]))
                # self.cross_section_name_lbl.setText(str(chan_n[1]))
            else:
                self.uc.show_warn(
                    "WARNING 060319.1626: Element " + elem + " has a cross section of type 'N' without data!"
                )

        highlight_selected_segment(self.lyrs.data["chan"]["qlyr"], self.channel_segment_cbo.currentIndex() + 1)
        highlight_selected_xsection_a(
            self.gutils, self.lyrs.data["chan_elems"]["qlyr"], int(self.grid_element_cbo.currentText())
        )

    def clear_all_individual_items_for_current_cell_element(self):
        self.grid_type_cbo.setCurrentIndex(0)
        self.manning_dbox.setValue(0)
        self.channel_length_dbox.setValue(0)
        self.left_bank_elevation_dbox.setValue(0)
        self.right_bank_elevation_dbox.setValue(0)
        self.left_side_slope_dbox.setValue(0)
        self.right_side_slope_dbox.setValue(0)
        self.average_channel_width_dbox.setValue(0)
        self.thalweg_channel_depth_dbox.setValue(0)
        self.cross_section_number_lbl.setText("")
        self.cross_section_name_lbl.setText("")
        self.right_bank_cell_lbl.setText("")
        self.first_area_coeff_dbox.setValue(0)
        self.first_area_exp_dbox.setValue(0)
        self.first_wetted_coeff_dbox.setValue(0)
        self.first_wetted_exp_dbox.setValue(0)
        self.first_top_width_coeff_dbox.setValue(0)
        self.first_top_width_exp_dbox.setValue(0)
        self.second_depth_dbox.setValue(0)
        self.second_area_coeff_dbox.setValue(0)
        self.second_area_exp_dbox.setValue(0)
        self.second_wetted_coeff_dbox.setValue(0)
        self.second_wetted_exp_dbox.setValue(0)
        self.second_top_width_coeff_dbox.setValue(0)
        self.second_top_width_exp_dbox.setValue(0)

    def enable_or_disable_items_according_to_type(self, type):
        # First disable all:
        self.left_bank_elevation_dbox.setEnabled(False)
        self.right_bank_elevation_dbox.setEnabled(False)
        self.left_side_slope_dbox.setEnabled(False)
        self.right_side_slope_dbox.setEnabled(False)
        self.average_channel_width_dbox.setEnabled(False)
        self.thalweg_channel_depth_dbox.setEnabled(False)
        self.cross_section_number_lbl.setEnabled(False)
        self.cross_section_name_lbl.setEnabled(False)
        self.first_area_coeff_dbox.setEnabled(False)
        self.first_area_exp_dbox.setEnabled(False)
        self.first_wetted_coeff_dbox.setEnabled(False)
        self.first_wetted_exp_dbox.setEnabled(False)
        self.first_top_width_coeff_dbox.setEnabled(False)
        self.first_top_width_exp_dbox.setEnabled(False)
        self.second_depth_dbox.setEnabled(False)
        self.second_area_coeff_dbox.setEnabled(False)
        self.second_area_exp_dbox.setEnabled(False)
        self.second_wetted_coeff_dbox.setEnabled(False)
        self.second_wetted_exp_dbox.setEnabled(False)
        self.second_top_width_coeff_dbox.setEnabled(False)
        self.second_top_width_exp_dbox.setEnabled(False)

        if type == "R":
            self.left_bank_elevation_dbox.setEnabled(True)
            self.right_bank_elevation_dbox.setEnabled(True)
            self.average_channel_width_dbox.setEnabled(True)
            self.thalweg_channel_depth_dbox.setEnabled(True)

        elif type == "V":
            self.left_bank_elevation_dbox.setEnabled(True)
            self.right_bank_elevation_dbox.setEnabled(True)
            self.thalweg_channel_depth_dbox.setEnabled(True)
            self.first_area_coeff_dbox.setEnabled(True)
            self.first_area_exp_dbox.setEnabled(True)
            self.first_wetted_coeff_dbox.setEnabled(True)
            self.first_wetted_exp_dbox.setEnabled(True)
            self.first_top_width_coeff_dbox.setEnabled(True)
            self.first_top_width_exp_dbox.setEnabled(True)
            self.second_depth_dbox.setEnabled(True)
            self.second_area_coeff_dbox.setEnabled(True)
            self.second_area_exp_dbox.setEnabled(True)
            self.second_wetted_coeff_dbox.setEnabled(True)
            self.second_wetted_exp_dbox.setEnabled(True)
            self.second_top_width_coeff_dbox.setEnabled(True)
            self.second_top_width_exp_dbox.setEnabled(True)

        elif type == "T":
            self.left_bank_elevation_dbox.setEnabled(True)
            self.right_bank_elevation_dbox.setEnabled(True)
            self.average_channel_width_dbox.setEnabled(True)
            self.thalweg_channel_depth_dbox.setEnabled(True)
            self.left_side_slope_dbox.setEnabled(True)
            self.right_side_slope_dbox.setEnabled(True)

        elif type == "N":
            self.cross_section_number_lbl.setEnabled(True)
            self.cross_section_name_lbl.setEnabled(True)

    def segment_elements_tblw_cell_clicked(self, row, column):
        self.grid_element_cbo.blockSignals(True)
        self.grid_element_cbo.setCurrentIndex(row)
        self.grid_element_cbo.blockSignals(False)

        type = self.segment_elements_tblw.item(row, 1).text()
        self.grid_type_cbo.setCurrentIndex(0 if type == "R" else 1 if type == "V" else 2 if type == "T" else 3)
        self.enable_or_disable_items_according_to_type(type)

        self.manning_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 2)))
        self.channel_length_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 3)))
        self.right_bank_cell_lbl.setText(str(self.int_or_zero(self.segment_elements_tblw.item(row, 11))))

        if type == "R":
            self.left_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 4)))
            # self.right_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row,5)))
            self.average_channel_width_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 8)))
            self.thalweg_channel_depth_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 9)))

        elif type == "V":
            self.left_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 4)))
            # self.right_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row,5)))
            self.thalweg_channel_depth_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 9)))
            self.first_area_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 12)))
            self.first_area_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 13)))
            self.first_wetted_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 14)))
            self.first_wetted_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 15)))
            self.first_top_width_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 16)))
            self.first_top_width_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 17)))
            self.second_depth_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 18)))
            self.second_area_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 19)))
            self.second_area_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 20)))
            self.second_wetted_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 21)))
            self.second_wetted_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 22)))
            self.second_top_width_coeff_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 23)))
            self.second_top_width_exp_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 24)))

        elif type == "T":
            self.left_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 4)))
            # self.right_bank_elevation_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row,5)))
            self.average_channel_width_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 8)))
            self.thalweg_channel_depth_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 9)))
            self.left_side_slope_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 6)))
            self.right_side_slope_dbox.setValue(float_or_zero(self.segment_elements_tblw.item(row, 7)))

        elif type == "N":
            self.cross_section_number_lbl.setText(str(self.int_or_zero(self.segment_elements_tblw.item(row, 10))))
            # self.cross_section_name_lbl.setText(?)

        highlight_selected_segment(self.lyrs.data["chan"]["qlyr"], self.channel_segment_cbo.currentIndex() + 1)
        highlight_selected_xsection_a(
            self.gutils, self.lyrs.data["chan_elems"]["qlyr"], int(self.grid_element_cbo.currentText())
        )

    def int_or_zero(self, value):
        if value is None:
            return int(0)
        elif value.text() == "":
            return int(0)
        else:
            return int(value.text())

    def save_channels(self):
        pass

    def update_transport_eq(self):
        qry = """UPDATE chan SET isedn = ? WHERE fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.transport_eq_cbo.currentIndex() + 1
        self.gutils.execute(qry, (value, idx))

    def update_initial_flow_for_all(self):
        qry = """UPDATE chan SET depinitial = ? WHERE fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.initial_flow_for_all_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_froude(self):
        qry = """UPDATE chan SET froudc = ? WHERE fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.max_froude_number_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_roughness(self):
        qry = """UPDATE chan SET roughadj = ? WHERE fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.roughness_adjust_coeff_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_first(self):
        qry = """UPDATE chan_wsel SET istart = ? WHERE seg_fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.first_elem_box.value()
        self.gutils.execute(qry, (value, idx))

    def update_last(self):
        qry = """UPDATE chan_wsel SET iend = ? WHERE seg_fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.last_elem_box.value()
        self.gutils.execute(qry, (value, idx))

    def update_starting(self):
        qry = """UPDATE chan_wsel SET wselstart = ? WHERE seg_fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.starting_water_elev_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_ending(self):
        qry = """UPDATE chan_wsel SET wselend = ? WHERE seg_fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.ending_water_elev_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def roughness_adjust_coeff_dbox_valueChanged(self):
        qry = """UPDATE chan SET roughadj = ? WHERE fid = ?;"""
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.roughness_adjust_coeff_dbox.value()
        self.gutils.execute(qry, (value, idx))
        self.update_segment_widget_table(self.roughness_adjust_coeff_dbox, 2)

    def manning_dbox_valueChanged(self):
        self.update_chan_elem_attr("chan_elems", "fcn", self.manning_dbox.value(), "fid")
        self.update_segment_widget_table(self.manning_dbox, 2)

    def db_name(self):
        index = self.grid_type_cbo.currentIndex()
        type = "R" if index == 0 else "V" if index == 1 else "T" if index == 2 else "N"
        table = "chan_r" if type == "R" else "chan_v" if type == "V" else "chan_t" if type == "T" else "chan_n"
        return table

    def grid_type_cbo_valueChanged(self):
        pass

    def channel_length_dbox_valueChanged(self):
        self.update_chan_elem_attr("chan_elems", "xlen", self.channel_length_dbox.value(), "fid")
        self.update_segment_widget_table(self.channel_length_dbox, 3)

    def left_bank_elevation_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "bankell", self.left_bank_elevation_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.left_bank_elevation_dbox, 4)

    def right_bank_elevation_dbox_valueChanged(self):
        self.update_chan_elem_attr(
            self.db_name(),
            "bankelr",
            self.right_bank_elevation_dbox.value(),
            "elem_fid",
        )
        self.update_segment_widget_table(self.right_bank_elevation_dbox, 5)

    def left_side_slope_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "zl", self.left_side_slope_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.left_side_slope_dbox, 6)

    def right_side_slope_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "zr", self.right_side_slope_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.right_side_slope_dbox, 7)

    def average_channel_width_dbox_valueChanged(self):
        db_name = self.db_name()
        self.update_chan_elem_attr(db_name, "fcw", self.average_channel_width_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.average_channel_width_dbox, 8)

    def thalweg_channel_depth_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "fcd", self.thalweg_channel_depth_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.thalweg_channel_depth_dbox, 9)

    def first_area_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "a1", self.first_area_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_area_coeff_dbox, 12)

    def first_area_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "a2", self.first_area_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_area_exp_dbox, 13)

    def first_wetted_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "b1", self.first_wetted_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_wetted_coeff_dbox, 14)

    def first_wetted_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "b2", self.first_wetted_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_wetted_exp_dbox, 15)

    def first_top_width_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "c1", self.first_top_width_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_top_width_coeff_dbox, 16)

    def first_top_width_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "c2", self.first_top_width_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.first_top_width_exp_dbox, 17)

    def second_depth_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "excdep", self.second_depth_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_depth_dbox, 18)

    def second_area_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "a11", self.second_area_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_area_coeff_dbox, 19)

    def second_area_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "a22", self.second_area_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_area_exp_dbox, 20)

    def second_wetted_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "b11", self.second_wetted_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_wetted_coeff_dbox, 21)

    def second_wetted_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "b22", self.second_wetted_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_wetted_exp_dbox, 22)

    def second_top_width_coeff_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "c11", self.second_top_width_coeff_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_top_width_coeff_dbox, 23)

    def second_top_width_exp_dbox_valueChanged(self):
        self.update_chan_elem_attr(self.db_name(), "c22", self.second_top_width_exp_dbox.value(), "elem_fid")
        self.update_segment_widget_table(self.second_top_width_exp_dbox, 24)

    def update_chan_elem_attr(self, table, attr_name, attr_value, id_name):
        id_value = self.grid_element_cbo.currentText()
        qry = """UPDATE {0} SET {1} = ? WHERE {2} = ?;"""
        qry = qry.format(table, attr_name, id_name)
        self.gutils.execute(qry, (attr_value, id_value))

        # cur = self.con.cursor()
        # cur.execute(qry, (attr_value, id_value))
        # self.con.commit()
        #

    def update_segment_widget_table(self, widget, col):
        row = self.grid_element_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        self.segment_elements_tblw.setItem(row, col, item)

    def close_dialog(self):
        self.features = []
        self.lyrs.data["chan"]["qlyr"].selectByIds(self.features)
        self.lyrs.data["chan_elems"]["qlyr"].selectByIds(self.features)
