# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback

from PyQt5.QtCore import QSettings, Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import QApplication
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QInputDialog

from .table_editor_widget import StandardItemModel, StandardItem
from ..flo2d_tools.schematic_tools import FloodplainXS
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import center_canvas, load_ui, set_icon, switch_to_selected

uiDialog, qtBaseClass = load_ui("fpxsec_editor")


class FPXsecEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.fpxsec_lyr = None
        self.plot = plot
        self.uc = UserCommunication(iface, "FLO-2D")
        self.table = table
        self.tview = table.tview

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        # set button icons
        set_icon(self.add_user_fpxs_btn, "add_fpxs.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_fpxs_btn, "mActionDeleteSelected.svg")
        set_icon(self.schem_fpxs_btn, "schematize_fpxs.svg")
        set_icon(self.rename_fpxs_btn, "change_name.svg")

        self.fill_iflo_directions()

        # Buttons connections
        self.add_user_fpxs_btn.clicked.connect(self.create_user_fpxs)
        self.revert_changes_btn.clicked.connect(self.revert_fpxs_lyr_edits)
        self.delete_fpxs_btn.clicked.connect(self.delete_cur_fpxs)
        self.schem_fpxs_btn.clicked.connect(self.schematize_fpxs)
        self.del_schem_fpxs_btn.clicked.connect(self.delete_schema_fpxs)
        self.rename_fpxs_btn.clicked.connect(self.rename_fpxs)
        self.fpxs_cbo.activated.connect(self.cur_fpxs_changed)
        self.flow_dir_cbo.activated.connect(self.save_fpxs)
        self.help_btn.clicked.connect(self.show_fp_xs_widget_help)

        self.fpxsec_lyr = self.lyrs.data["user_fpxsec"]["qlyr"]

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.report_chbox.setEnabled(True)
            nxprt = self.gutils.get_cont_par("NXPRT")
            if nxprt == "0":
                self.report_chbox.setChecked(False)
            elif nxprt == "1":
                self.report_chbox.setChecked(True)
            else:
                self.report_chbox.setChecked(False)
                self.set_report()
            self.report_chbox.stateChanged.connect(self.set_report)

    def switch2selected(self):
        switch_to_selected(self.fpxsec_lyr, self.fpxs_cbo)
        self.cur_fpxs_changed()

    def populate_cbos(self, fid=None, show_last_edited=True):
        self.fpxs_cbo.clear()
        qry = """SELECT fid, name, iflo FROM user_fpxsec ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(qry).fetchall()
        if rows:
            cur_idx = 0
            for i, row in enumerate(rows):
                self.fpxs_cbo.addItem(row[1], row)
                if fid and row[0] == fid:
                    cur_idx = i
            self.fpxs_cbo.setCurrentIndex(cur_idx)
            self.cur_fpxs_changed()
        else:
            self.lyrs.clear_rubber()

    def cur_fpxs_changed(self):
        """
        Function to change the floodplain cross-section combobox
        """
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        if row is None:
            return
        self.fpxs_fid = row[0]

        fpxs_name = self.fpxs_cbo.currentText()

        if fpxs_name:
            # Get the feature associated with the combobox
            request = QgsFeatureRequest().setFilterExpression(f'"fid" = {self.fpxs_fid}')
            matching_features = self.fpxsec_lyr.getFeatures(request)
            feature = next(matching_features, None)
            geometry = feature.geometry()
            geom_poly = geometry.asPolyline()
            start, end = geom_poly[0], geom_poly[-1]
            # Calculate azimuth
            azimuth = start.azimuth(end)

            # Figure out the allowed directions
            iflo_allowed_directions = self.get_iflo_direction(azimuth)
            self.fill_iflo_directions()
            for i in range(8, 0, -1):  # Iterate in reverse (8 to 1)
                if i not in iflo_allowed_directions:
                    self.flow_dir_cbo.removeItem(i - 1)

            self.fpxs_fid, iflo = self.gutils.execute(f"SELECT fid, iflo FROM user_fpxsec WHERE name = '{fpxs_name}';").fetchone()
            index = self.flow_dir_cbo.findText(str(iflo))
            # If index equal -1, the direction is wrong. Needs to be fixed
            if index == -1:
                iflo = iflo_allowed_directions[0]
                qry = f"""UPDATE user_fpxsec SET iflo={iflo} WHERE fid={self.fpxs_fid};"""
                self.gutils.execute(qry)
            else:
                self.flow_dir_cbo.setCurrentIndex(index)

            self.lyrs.clear_rubber()
            if self.center_fpxs_chbox.isChecked():
                self.show_fpxs_rb()
                feat = next(self.fpxsec_lyr.getFeatures(QgsFeatureRequest(self.fpxs_fid)))
                x, y = feat.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)

    def show_fpxs_rb(self):
        if not self.fpxs_fid:
            return
        self.lyrs.show_feat_rubber(self.fpxsec_lyr.id(), self.fpxs_fid)

    def populate_fpxs_signal(self):
        self.add_user_fpxs_btn.setChecked(False)
        self.gutils.fill_empty_fpxs_names()
        self.populate_cbos(fid=self.gutils.get_max("user_fpxsec") - 1)

    def create_user_fpxs(self):

        if self.lyrs.any_lyr_in_edit("user_fpxsec"):
            self.save_fpxs_lyr_edits()
            self.add_user_fpxs_btn.setChecked(False)
            return

        self.add_user_fpxs_btn.setCheckable(True)
        self.add_user_fpxs_btn.setChecked(True)

        self.lyrs.enter_edit_mode("user_fpxsec")

    def save_fpxs_lyr_edits(self):
        if not self.lyrs.any_lyr_in_edit("user_fpxsec"):
            return
        has_data = self.gutils.is_table_empty("user_fpxsec")
        self.lyrs.save_lyrs_edits("user_fpxsec")
        if has_data:
            self.populate_cbos(fid=0)
        else:
            self.populate_cbos(fid=self.gutils.get_max("user_fpxsec"))

        self.cur_fpxs_changed()

        self.uc.bar_info("Floodplain cross-sections created!")
        self.uc.log_info("Floodplain cross-sections created!")

    def rename_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.fpxs_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1704: Floodplain cross-sections with name {} already exists in the database. Please, choose another name."
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return
        self.fpxs_cbo.setItemText(self.fpxs_cbo.currentIndex(), new_name)
        self.save_fpxs()

    def revert_fpxs_lyr_edits(self):
        user_fpxs_edited = self.lyrs.rollback_lyrs_edits("user_fpxsec")
        if user_fpxs_edited:
            self.populate_cbos()

    def delete_cur_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        q = "Are you sure, you want delete the current floodplain cross-section?"
        if not self.uc.question(q):
            return
        self.gutils.execute("DELETE FROM user_fpxsec WHERE fid = ?;", (self.fpxs_fid,))
        self.populate_cbos(fid=0)
        self.fpxsec_lyr.triggerRepaint()

        fpxs_name = self.fpxs_cbo.currentText()
        self.fill_iflo_directions()
        self.uc.bar_info(f"The {fpxs_name} floodplain cross-section is deleted!")
        self.uc.log_info(f"The {fpxs_name} floodplain cross-section is deleted!")

    def save_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        fid = row[0]
        name = self.fpxs_cbo.currentText()
        iflo = self.flow_dir_cbo.currentText()
        qry = "UPDATE user_fpxsec SET name = ?, iflo = ? WHERE fid = ?;"
        if fid > 0:
            self.gutils.execute(
                qry,
                (
                    name,
                    iflo,
                    fid,
                ),
            )
        self.populate_cbos(fid=fid, show_last_edited=False)

    def schematize_fpxs(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool!")
            self.uc.log_info("There is no grid! Please create it before running tool!")
            return

        try:
            if self.lyrs.any_lyr_in_edit("user_fpxsec"):
                self.save_fpxs_lyr_edits()
                self.add_user_fpxs_btn.setChecked(False)
            fpxs = FloodplainXS(self.con, self.iface, self.lyrs)
            fpxs.schematize_floodplain_xs()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1705: Process failed on schematizing floodplain cross-sections! "
                "Please check your User Layers."
            )
            return
        self.uc.bar_info("Floodplain cross-sections schematized!")
        self.uc.log_info("Floodplain cross-sections schematized!")

    def delete_schema_fpxs(self):
        """
        Function to delete the floodplain cross-section schematized data
        """
        if self.gutils.is_table_empty("fpxsec") and self.gutils.is_table_empty("fpxsec_cells"):
            self.uc.bar_warn("There is no schematized floodplain cross sections!")
            self.uc.log_info("There is no schematized floodplain cross sections!")
            return

        self.gutils.clear_tables("fpxsec", "fpxsec_cells")

        self.uc.bar_info("Schematized floodplain cross sections deleted!")
        self.uc.log_info("Schematized floodplain cross sections deleted!")

        self.lyrs.clear_rubber()
        self.lyrs.data["fpxsec"]["qlyr"].triggerRepaint()
        self.lyrs.data["fpxsec_cells"]["qlyr"].triggerRepaint()

        self.fill_iflo_directions()

    def set_report(self):
        if self.report_chbox.isChecked():
            self.gutils.set_cont_par("NXPRT", "1")
        else:
            self.gutils.set_cont_par("NXPRT", "0")

    def show_hydrograph(self, table, fid):
        """
        Function to load the hydrograph and flododplain hydraulics from HYCROSS.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        HYCROSS_file = s.value("FLO-2D/lastHYCROSSFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is an HYCROSS.OUT file on the FLO-2D QSettings
        if not os.path.isfile(HYCROSS_file):
            HYCROSS_file = GDS_dir + r"/HYCROSS.OUT"
            # Check if there is an HYCROSS.OUT file on the export folder
            if not os.path.isfile(HYCROSS_file):
                self.uc.bar_warn(
                    "No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                self.uc.log_info(
                    "No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the HYCROSS.OUT has data on it
        if os.path.getsize(HYCROSS_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(HYCROSS_file) + "'  is empty!")
            self.uc.log_info("File  '" + os.path.basename(HYCROSS_file) + "'  is empty!")
            return

        with open(HYCROSS_file, "r") as myfile:
            while True:
                time_list = []
                discharge_list = []
                flow_width_list = []
                wse_list = []
                line = next(myfile)
                if "THE MAXIMUM DISCHARGE FROM CROSS SECTION" in line:
                    if line.split()[6] == str(fid):
                        for _ in range(9):
                            line = next(myfile)
                        while True:
                            try:
                                line = next(myfile)
                                if not line.strip():
                                    break
                                line = line.split()
                                # If this line starts with the string "VELOCITY", it is a channel cross section
                                if line[0] == "VELOCITY":
                                    for _ in range(5):
                                        line = next(myfile)
                                        line = line.split()
                                time_list.append(float(line[0]))
                                discharge_list.append(float(line[5]))
                                flow_width_list.append(float(line[1]))
                                wse_list.append(float(line[3]))
                            except StopIteration:
                                break
                        break

        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Floodplain Cross Section - {fid}")
        self.plot.plot.setLabel("bottom", text="Time (hrs)")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
        self.plot.add_item(f"Flow Width ({self.system_units[units][0]})", [time_list, flow_width_list], col=QColor(Qt.black), sty=Qt.SolidLine, hide=True)
        self.plot.add_item(f"Water Surface Elevation ({self.system_units[units][0]})", [time_list, wse_list], col=QColor(Qt.darkGreen), sty=Qt.SolidLine, hide=True)

        try:  # Build table.
            discharge_data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(discharge_data_model)
            discharge_data_model.clear()
            headers = ["Time (hours)",
                        f"Discharge ({self.system_units[units][2]})",
                        f"Flow Width ({self.system_units[units][0]})",
                        f"Water Surface Elevation ({self.system_units[units][0]})"]
            discharge_data_model.setHorizontalHeaderLabels(headers)

            data = zip(time_list, discharge_list, flow_width_list, wse_list)
            for row, (time, discharge, flow, wse) in enumerate(data):
                time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                flow_item = StandardItem("{:.2f}".format(flow)) if flow is not None else StandardItem("")
                wse_item = StandardItem("{:.2f}".format(wse)) if wse is not None else StandardItem("")
                discharge_data_model.setItem(row, 0, time_item)
                discharge_data_model.setItem(row, 1, discharge_item)
                discharge_data_model.setItem(row, 2, flow_item)
                discharge_data_model.setItem(row, 3, wse_item)

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(discharge_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Error while building table for floodplain cross section!")
            self.uc.log_info("Error while building table for floodplain cross section!")
            return

        use_prs = s.value("FLO-2D/use_prs", "")
        if use_prs:
            scenario1 = s.value("FLO-2D/scenario1") + r"/HYCROSS.OUT" if s.value("FLO-2D/scenario1") != "" else None
            scenario2 = s.value("FLO-2D/scenario2") + r"/HYCROSS.OUT" if s.value("FLO-2D/scenario2") != "" else None
            scenario3 = s.value("FLO-2D/scenario3") + r"/HYCROSS.OUT" if s.value("FLO-2D/scenario3") != "" else None
            scenario4 = s.value("FLO-2D/scenario4") + r"/HYCROSS.OUT" if s.value("FLO-2D/scenario4") != "" else None
            scenario5 = s.value("FLO-2D/scenario5") + r"/HYCROSS.OUT" if s.value("FLO-2D/scenario5") != "" else None
            scenarios = [scenario1, scenario2, scenario3, scenario4, scenario5]
            j = 1
            for scenario in scenarios:
                if scenario:
                    with open(scenario, "r") as myfile:
                        while True:
                            time_list = []
                            discharge_list = []
                            flow_width_list = []
                            wse_list = []
                            line = next(myfile)
                            if "THE MAXIMUM DISCHARGE FROM CROSS SECTION" in line:
                                if line.split()[6] == str(fid):
                                    for _ in range(9):
                                        line = next(myfile)
                                    while True:
                                        try:
                                            line = next(myfile)
                                            if not line.strip():
                                                break
                                            line = line.split()
                                            time_list.append(float(line[0]))
                                            discharge_list.append(float(line[5]))
                                            flow_width_list.append(float(line[1]))
                                            wse_list.append(float(line[3]))
                                        except StopIteration:
                                            break
                                    break

                        if j == 1:
                            color1 = Qt.blue
                            color2 = Qt.darkBlue
                            color3 = "#3282F6"
                        if j == 2:
                            color1 = Qt.red
                            color2 = Qt.darkRed
                            color3 = "#3A0603"
                        if j == 3:
                            color1 = Qt.magenta
                            color2 = Qt.darkMagenta
                            color3 = "#EE8AF8"
                        if j == 4:
                            color1 = Qt.gray
                            color2 = Qt.darkGray
                            color3 = Qt.lightGray
                        if j == 5:
                            color1 = Qt.cyan
                            color2 = Qt.darkCyan
                            color3 = "#B0FBFD"

                    self.plot.add_item(f"Discharge ({self.system_units[units][2]}) - Scenario {j}", [time_list, discharge_list],
                                       col=QColor(color1), sty=Qt.SolidLine)
                    self.plot.add_item(f"Flow Width ({self.system_units[units][0]}) - Scenario {j}", [time_list, flow_width_list],
                                       col=QColor(color2), sty=Qt.SolidLine, hide=True)
                    self.plot.add_item(f"Water Surface Elevation ({self.system_units[units][0]}) - Scenario {j}",
                                       [time_list, wse_list], col=QColor(color3), sty=Qt.SolidLine, hide=True)

                    headers.extend([f"Discharge ({self.system_units[units][2]}) - Scenario {j}",
                                    f"Flow Width ({self.system_units[units][0]}) - Scenario {j}",
                                    f"Water Surface Elevation ({self.system_units[units][0]}) - Scenario {j}"])
                    discharge_data_model.setHorizontalHeaderLabels(headers)

                    new_column_index = discharge_data_model.columnCount() - 3

                    data = zip(time_list, discharge_list, flow_width_list, wse_list)
                    for row, (_, discharge, flow, wse) in enumerate(data):
                        discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                        flow_item = StandardItem("{:.2f}".format(flow)) if flow is not None else StandardItem("")
                        wse_item = StandardItem("{:.2f}".format(wse)) if wse is not None else StandardItem("")
                        discharge_data_model.setItem(row, new_column_index, discharge_item)
                        discharge_data_model.setItem(row, new_column_index + 1, flow_item)
                        discharge_data_model.setItem(row, new_column_index + 2, wse_item)

                j += 1

    def show_cells_hydrograph(self, table, fid):
        """
        Function to load the floodplain cells hydrograph from CROSSQ.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        CROSSQ_file = s.value("FLO-2D/lastCROSSQFile", "")
        GDS_dir = s.value("FLO-2D/lastGdsDir", "")
        # Check if there is a CROSSQ.OUT file on the FLO-2D QSettings
        if not os.path.isfile(CROSSQ_file):
            CROSSQ_file = GDS_dir + r"/CROSSQ.OUT"
            # Check if there is a CROSSQ.OUT file on the export folder
            if not os.path.isfile(CROSSQ_file):
                self.uc.bar_warn(
                    "No CROSSQ.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                self.uc.log_info(
                    "No CROSSQ.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                return
        # Check if the CROSSQ.OUT has data on it
        if os.path.getsize(CROSSQ_file) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("File  '" + os.path.basename(CROSSQ_file) + "'  is empty!")
            self.uc.log_info("File  '" + os.path.basename(CROSSQ_file) + "'  is empty!")
            return

        grid_fid = self.gutils.execute(f"SELECT grid_fid FROM fpxsec_cells WHERE fid = '{fid}'").fetchone()[0]

        with open(CROSSQ_file, "r") as myfile:
            while True:
                time_list = []
                discharge_list = []
                line = next(myfile)
                if len(line.split()) == 3 and line.split()[0] == str(grid_fid):
                    time_list.append(float(line.split()[1]))
                    discharge_list.append(float(line.split()[2]))
                    while True:
                        try:
                            line = next(myfile)
                            if len(line.split()) == 3:
                                break
                            time_list.append(float(line.split()[0]))
                            discharge_list.append(float(line.split()[1]))
                        except StopIteration:
                            break
                    break

        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        self.plot.plot.legend = None
        self.plot.plot.addLegend(offset=(0, 30))
        self.plot.plot.setTitle(title=f"Floodplain Cell - {grid_fid}")
        self.plot.plot.setLabel("bottom", text="Time (hrs)")
        self.plot.plot.setLabel("left", text="")
        self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)

        try:  # Build table.
            discharge_data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(discharge_data_model)
            discharge_data_model.clear()
            discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                            f"Discharge ({self.system_units[units][2]})"])

            data = zip(time_list, discharge_list)
            for time, discharge in data:
                time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                discharge_data_model.appendRow([time_item, discharge_item])

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(3):
                self.tview.setColumnWidth(col, 100)
            for i in range(discharge_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Error while building table for floodplain cells!")
            self.uc.log_info("Error while building table for floodplain cells!")
            return

    def fpxs_feature_changed(self, fid):
        """
        Function to set the fpxs_cbo index equal to the feature edited
        """
        try:
            fpxs_name = self.gutils.execute(f"SELECT name FROM user_fpxsec WHERE fid = '{fid}'").fetchone()[0]
            index = self.fpxs_cbo.findText(fpxs_name)
            self.populate_cbos(fid=index)
        except:
            return

    def show_fp_xs_widget_help(self):
        """
        Function to show the fp xs widget help
        """
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets"
                                      "/floodplain-cross-section-editor/Floodplain%20Cross%20Section%20Editor.html"))

    def fill_iflo_directions(self):
        """
        Function to fill the iflo directions on the directions combobox
        """
        self.setup_connection()
        self.flow_dir_cbo.clear()
        if self.gutils.is_table_empty("user_fpxsec"):
            return
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        idir = os.path.join(os.path.dirname(parent_dir), "img")
        for i in range(8):
            self.flow_dir_cbo.addItem(str(i + 1))
            icon_file = "arrow_{}.svg".format(i + 1)
            self.flow_dir_cbo.setItemIcon(i, QIcon(os.path.join(idir, icon_file)))

    def get_iflo_direction(self, azimuth):
        """
        Function to get the iflo directions based on the azimuth
        """

        # Ensure azimuth is positive
        if azimuth < 0:
            azimuth += 360

        perp_azimuth = (azimuth + 90) % 360

        if 337.5 <= perp_azimuth or perp_azimuth < 22.5:
            return [1, 3]
        elif 22.5 <= perp_azimuth < 67.5:
            return [5, 7]
        elif 67.5 <= perp_azimuth < 112.5:
            return [2, 4]
        elif 112.5 <= perp_azimuth < 157.5:
            return [6, 8]
        elif 157.5 <= perp_azimuth < 202.5:
            return [3, 1]
        elif 202.5 <= perp_azimuth < 247.5:
            return [7, 5]
        elif 247.5 <= perp_azimuth < 292.5:
            return [4, 2]
        elif 292.5 <= perp_azimuth < 337.5:
            return [8, 6]


